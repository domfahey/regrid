"""Command line access to the synchronous Regrid SDK."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path
from typing import Any

from .client import RegridClient, RegridError
from .config import validate_limit
from .endpoints import QueryPagingError
from .offline import fields as parcel_fields
from .offline import freshness as county_freshness
from .offline import map as parcel_map


def _max_age_days(value: str) -> float:
    try:
        return county_freshness.check_max_age_days(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"must be a finite number between 0 and {county_freshness.MAX_AGE_DAYS_LIMIT}"
        ) from None


def _object(value: str) -> dict[str, Any]:
    """Load an object without including possibly sensitive input in errors."""
    valid = True
    result: Any = None
    try:
        raw = Path(value[1:]).read_text() if value.startswith("@") else value
        result = json.loads(raw)
    except (OSError, ValueError, UnicodeError, RecursionError):
        valid = False
    # Raise outside the except block: __context__ would retain the raw input.
    if not valid:
        raise ValueError("Expected valid JSON or @file containing JSON")
    if not isinstance(result, dict):
        raise ValueError("JSON input must be an object")
    return result


def _run_map(args: dict[str, Any]) -> None:
    summary = parcel_map.render(
        Path(args["response"]),
        Path(args["output"]),
        index=args["feature"],
        all_candidates=args["all_candidates"],
        retrieved_at=args["retrieved_at"],
        replace=args["replace"],
        neighbours_path=args["neighbours"],
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False))


def _run_export(args: dict[str, Any]) -> None:
    summary = parcel_map.export(
        Path(args["response"]),
        csv_path=Path(args["csv"]) if args["csv"] else None,
        geojson_path=Path(args["geojson"]) if args["geojson"] else None,
        all_fields=args["all_fields"],
        replace=args["replace"],
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False))


def _run_fields(args: dict[str, Any]) -> None:
    catalog = parcel_fields.load_catalog(
        Path(str(files("regrid").joinpath("data/parcel_fields.json")))
    )
    if args["action"] == "explain":
        result: dict[str, Any] = parcel_fields.explain(catalog, args["names"])
    else:
        result = {"matches": parcel_fields.search(catalog, args["term"])}
    print(json.dumps(result, indent=2, ensure_ascii=False))


def _client(args: dict[str, Any]) -> RegridClient:
    """Build the client from global options; the token comes only from REGRID_TOKEN."""
    return RegridClient(
        token=(os.environ.get("REGRID_TOKEN") or "").strip() or None,
        timeout=args["timeout"],
        base_url=args["base_url"],
        tiles_base_url=args["tiles_base_url"],
    )


def _error_message(exc: Exception, *, os_error: str, type_error: str) -> str:
    """One credential-free line: SDK messages verbatim, local errors fixed or whitespace-folded."""
    if isinstance(exc, RegridError):
        return str(exc)
    if isinstance(exc, RecursionError):
        return "Response or input is nested too deeply"
    if isinstance(exc, OSError):
        return os_error
    if isinstance(exc, TypeError):
        return type_error
    return " ".join(str(exc).split())


def _save_json(path: Path, text: str, *, replace: bool) -> None:
    """Write atomically (umask-respecting, never following a symlink at ``path``)."""
    parcel_map.write_atomic_bytes(path, text.encode("utf-8"), replace=replace)


def _subject_feature(result: Any) -> Any:
    """The first parcel feature of a response, or None when there is none."""
    try:
        return parcel_map.load_features(result)[0]
    except ValueError:
        return None


def _subject_point(subject: Any) -> list[float] | None:
    """The subject's in-US (lat, lon), or None."""
    return parcel_map.fallback_point(subject) if isinstance(subject, dict) else None


def _subject_mappable(subject: Any) -> bool:
    if not isinstance(subject, dict):
        return False
    try:
        parcel_map.check_mappable(subject)
    except parcel_map.MapError:
        return False
    return True


def _address_map(
    args: dict[str, Any], sent: list[int], saved: list[Path], notes: list[str]
) -> None:
    output = Path(args["output"])
    response_path = Path(args["save_response"] or output.with_suffix(".json"))
    neighbours_path = output.with_name(f"{output.stem}.neighbours.json")
    replace = args["replace"]
    targets = [response_path, output] + ([neighbours_path] if args["neighbours"] else [])
    if len({parcel_map.same_file_key(target) for target in targets}) != len(targets):
        raise ValueError("Saved response and map output must be different files")
    for target in targets:
        if not target.parent.is_dir():
            raise ValueError("Output directory does not exist")
    for target in targets:
        if target.is_dir():
            raise ValueError(f"{target} is a directory")
    for target in targets:
        if not replace and os.path.lexists(target):
            raise ValueError(f"{target} exists; pass --replace to overwrite it")
    options: dict[str, Any] = {
        "limit": 1,
        "return_parcels": True,
        "return_stacked": False,
        "return_zoning": False,
        "return_matched_buildings": False,
        "return_matched_addresses": False,
        "return_enhanced_ownership": False,
    }
    if args["path"] is not None:
        options["path"] = args["path"]
    with _client(args) as client:
        neighbours_file: Path | None = None
        try:
            result = client.address(args["address"], **options)
            body = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
            _save_json(response_path, body, replace=replace)
            saved.append(response_path)
            if args["neighbours"]:
                subject = _subject_feature(result)
                point = _subject_point(subject)
                if point is None:
                    if subject is not None:
                        notes.append("neighbours skipped: subject has no coordinates")
                elif not _subject_mappable(subject):
                    notes.append("neighbours skipped: subject is not mappable")
                else:
                    try:
                        around = client.point(
                            lat=point[0],
                            lon=point[1],
                            radius=100,
                            limit=25,
                            return_geometry=True,
                            return_parcels=True,
                            return_stacked=False,
                            return_zoning=False,
                            return_matched_buildings=False,
                            return_matched_addresses=False,
                            return_enhanced_ownership=False,
                        )
                    except RegridError:
                        notes.append("neighbours skipped: request failed")
                    else:
                        text = (
                            json.dumps(around, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
                        )
                        _save_json(neighbours_path, text, replace=replace)
                        neighbours_file = neighbours_path
                        saved.append(neighbours_path)
        finally:
            sent.append(client.request_count)
    retrieved_at = args["retrieved_at"] or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    summary = parcel_map.render(
        response_path,
        output,
        retrieved_at=retrieved_at,
        replace=replace,
        neighbours_path=neighbours_file,
    )
    print(
        json.dumps(
            {
                "response": str(response_path),
                **({"neighbours_response": str(neighbours_file)} if neighbours_file else {}),
                **summary,
            },
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
    )


def _run_address_map(args: dict[str, Any]) -> int:
    sent: list[int] = []
    saved: list[Path] = []
    notes: list[str] = []
    message = None
    try:
        _address_map(args, sent, saved, notes)
    except (
        RegridError,
        ValueError,
        TypeError,
        OSError,
        RecursionError,
    ) as exc:  # MapError is a ValueError
        message = _error_message(
            exc, os_error="Could not write output file", type_error="Invalid input or output file"
        )
    print(f"regrid: requests made: {sent[0] if sent else 0}", file=sys.stderr)
    for note in notes:
        print(f"regrid: {note}", file=sys.stderr)
    if message is not None and saved:
        print(f"regrid: response saved to {saved[0]}", file=sys.stderr)
        if len(saved) > 1:
            print(f"regrid: neighbours saved to {saved[1]}", file=sys.stderr)
    if message is not None:
        print(f"regrid: {message}", file=sys.stderr)
        return 1
    return 0


class _PagingError(ValueError):
    """Fixed, credential-free paging usage message."""


def _parse_page(result: Any) -> list[Any]:
    """Return a page's features, or raise _PagingError when its shape is unusable."""
    parcels = result.get("parcels") if isinstance(result, dict) else None
    if isinstance(result, dict) and parcels is None:
        return []
    page = parcels.get("features") if isinstance(parcels, dict) else None
    if page is None and isinstance(parcels, dict):
        return []
    if not isinstance(page, list):
        raise _PagingError("paging stopped: malformed page in response")
    return page


def _is_collection(value: Any) -> bool:
    return isinstance(value, dict) and isinstance(value.get("features"), list)


def _identity(item: Any) -> str:
    """A feature's id when it has one, else the item's JSON form."""
    if isinstance(item, dict) and item.get("id") is not None:
        return "id:" + json.dumps(item["id"], sort_keys=True, default=str)
    return "json:" + json.dumps(item, sort_keys=True, default=str)


def _extend_new(current: list[Any], incoming: list[Any]) -> None:
    """Append items not already merged; an inclusive cursor repeats the previous page's tail.

    Only dict items (features, objects) are de-duplicated; other items are always kept.
    """
    known = {_identity(item) for item in current if isinstance(item, dict)}
    for item in incoming:
        if isinstance(item, dict):
            identity = _identity(item)
            if identity in known:
                continue
            known.add(identity)
        current.append(item)


def _dedupe(items: list[Any]) -> list[Any]:
    unique: list[Any] = []
    _extend_new(unique, items)
    return unique


def _merge_page(merged: dict[str, Any], result: dict[str, Any], noted: set[str]) -> None:
    """Fold a later page's top-level lists and FeatureCollections into the merged response."""
    for key, value in result.items():
        if key == "parcels":
            continue
        current = merged.get(key)
        if isinstance(value, list):
            if merged.get(key) is None:
                merged[key] = _dedupe(value)
            elif isinstance(current, list):
                _extend_new(current, value)
            else:
                _shape_note(key, noted)
        elif _is_collection(value):
            if merged.get(key) is None:
                merged[key] = {**value, "features": _dedupe(value["features"])}
            elif isinstance(current, dict) and _is_collection(current):
                _extend_new(current["features"], value["features"])
            else:
                _shape_note(key, noted)
        elif isinstance(current, list) or _is_collection(current):
            _shape_note(key, noted)


def _shape_note(key: str, noted: set[str]) -> None:
    if key not in noted:
        noted.add(key)
        print(
            f"regrid: paging note: {key} shape changed; later pages ignored for it",
            file=sys.stderr,
        )


def _copy_first_page(result: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for key, value in result.items():
        if key != "parcels" and isinstance(value, list):
            merged[key] = _dedupe(value)
        elif key != "parcels" and _is_collection(value):
            merged[key] = {**value, "features": _dedupe(value["features"])}
        else:
            merged[key] = value
    return merged


def _validate_paging(
    client: RegridClient, command: str, args: dict[str, Any], options: dict[str, Any]
) -> None:
    """Run page 2's validation up front so it cannot fail after page 1 is billed."""
    if options.get("return_count"):
        raise _PagingError("--max-records conflicts with return_count")
    if command == "query":
        try:
            client.validate_query(**args, paging=True, **options)
        except QueryPagingError:
            raise _PagingError("--max-records is incompatible with these query filters") from None
        except ValueError as exc:
            raise _PagingError(_error_message(exc, os_error="", type_error="")) from None


def _cursor(feature: Any) -> int | None:
    """A usable offset_id from a feature id: a non-negative int or ASCII decimal digits."""
    value = _feature_id(feature)
    if type(value) is int and value >= 0:
        return value
    if isinstance(value, str) and value.isascii() and value.isdigit():
        return int(value)
    return None


def _drop_trimmed_siblings(merged: dict[str, Any], kept: list[Any], trimmed: list[Any]) -> None:
    """Remove sibling features that belong to parcels trimmed off the end."""

    def uuids(features: list[Any], *, parcels: bool = False) -> set[Any]:
        found = set()
        for feature in features:
            if parcels and (own := parcel_map.feature_uuid(feature)) is not None:
                found.add(own)
            properties = feature.get("properties") if isinstance(feature, dict) else None
            if not isinstance(properties, dict):
                continue
            single, many = properties.get("ll_uuid"), properties.get("ll_uuids")
            if isinstance(single, str):
                found.add(single)
            if isinstance(many, list):
                found.update(u for u in many if isinstance(u, str))
        return found

    kept_uuids = uuids(kept, parcels=True)
    dropped = uuids(trimmed, parcels=True) - kept_uuids
    if not dropped:
        return
    for key, value in merged.items():
        if key != "parcels" and _is_collection(value):
            value["features"] = [
                f for f in value["features"] if not _only_dropped(uuids([f]), dropped, kept_uuids)
            ]


def _only_dropped(referenced: set[Any], dropped: set[Any], kept: set[Any]) -> bool:
    """True when a feature references a dropped parcel and no kept one."""
    return bool(referenced & dropped) and not referenced & kept


def _feature_id(feature: Any) -> Any:
    return feature.get("id") if isinstance(feature, dict) else None


def _paged_search(
    client: RegridClient,
    command: str,
    args: dict[str, Any],
    options: dict[str, Any],
    total: int,
    progress: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Follow the last feature's id as offset_id until total records, a short page or no cursor."""
    limit = options.get("limit")
    if total < 1 or type(limit) is not int or limit < 1:
        raise _PagingError(
            "--max-records requires a positive count and an integer limit in --options"
        )
    if limit < 2:
        raise _PagingError("--max-records paging needs a limit of at least 2 in --options")
    if command == "point" and args.get("method") == "POST":
        raise _PagingError("--max-records is not supported for POST point searches")
    if "offset_id" in options:
        raise _PagingError("--max-records conflicts with offset_id")
    try:
        validate_limit(limit, client.max_limit)
    except ValueError as exc:
        raise _PagingError(_error_message(exc, os_error="", type_error="")) from None
    _validate_paging(client, command, args, options)
    # Worst case under an inclusive cursor: later pages add at least limit - 1 new records.
    first = min(limit, total)
    requests_cap = 1 + -(-(total - first) // (limit - 1))
    print(f"regrid: up to {requests_cap} requests for {total} records", file=sys.stderr)
    features: list[Any] = []
    seen_ids: set[str] = set()
    merged: dict[str, Any] = {}
    noted: set[str] = set()
    pages = 0
    cursor: Any = None
    complete = False
    state = progress if progress is not None else {}
    while pages < requests_cap and len(features) < total:
        remaining = total - len(features)
        # An inclusive offset_id repeats the cursor feature, so later pages ask for one extra.
        page_options = {**options, "limit": min(limit, remaining + (1 if pages else 0))}
        if cursor is not None:
            page_options["offset_id"] = cursor
        result = getattr(client, command)(**args, **page_options)
        page = _parse_page(result)
        pages += 1
        if pages == 1:
            merged = _copy_first_page(result)
            present = [key for key in ("pages", "complete") if key in merged]
            lost = [key for key in present if f"response_{key}" in merged]
            moved = [key for key in present if key not in lost]
            for keys, text in ((lost, "not kept"), (moved, "kept")):
                if keys:
                    names = "/".join(keys)
                    renamed = "/".join(f"response_{key}" for key in keys)
                    detail = f"({renamed} already present)" if keys is lost else f"as {renamed}"
                    print(
                        f"regrid: paging note: response {names} {text} {detail}",
                        file=sys.stderr,
                    )
        else:
            _merge_page(merged, result, noted)
        new = []
        for feature in page:
            if _feature_id(feature) is not None:
                identity = _identity(feature)
                if identity in seen_ids:
                    continue
                seen_ids.add(identity)
            new.append(feature)
        features.extend(new)
        _drop_trimmed_siblings(merged, features[:total], features[total:])
        state.update(merged=merged, features=features[:total], pages=pages)
        if len(page) < page_options["limit"] or len(features) >= total:
            complete = True
            break
        if not new:
            print("regrid: paging stopped: cursor did not advance", file=sys.stderr)
            break
        last = _cursor(page[-1])
        if last is None:
            print("regrid: paging stopped: no cursor in response", file=sys.stderr)
            break
        if last == cursor:
            print("regrid: paging stopped: cursor did not advance", file=sys.stderr)
            break
        cursor = last
    return _paged_result(merged, features[:total], pages, complete or len(features) >= total)


def _paged_result(
    merged: dict[str, Any], features: list[Any], pages: int, complete: bool
) -> dict[str, Any]:
    """The first page's response with parcels.features replaced by the merged features."""
    parcels = merged.get("parcels")
    collection = {**(parcels if isinstance(parcels, dict) else {}), "features": features}
    collection.setdefault("type", "FeatureCollection")
    result = {**merged, "parcels": collection}
    for key in ("pages", "complete"):
        if key in merged and f"response_{key}" not in merged:
            result[f"response_{key}"] = merged[key]
    return {**result, "pages": pages, "complete": complete}


def _freshness(args: dict[str, Any], sent: list[int]) -> None:
    county = county_freshness.county_path(args["path"])
    cache_path = Path(args["cache"]) if args["cache"] else county_freshness.default_cache_path()
    base_url = args["base_url"]
    cached = None if args["refresh"] else county_freshness.read_cache(cache_path, base_url)
    max_age = args["max_age_days"]
    if cached is not None and county_freshness.is_stale(cached[0], max_age):
        print(f"regrid: cached verse is older than {max_age:g} days; refetching", file=sys.stderr)
        cached = None
    if cached is not None:
        (retrieved_at, verse), state = cached, "hit"
    else:
        with _client(args) as client:
            try:
                verse = client.verse(return_geometry=False)
            finally:
                sent.append(client.request_count)
        retrieved_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        state = "miss"
        try:
            county_freshness.write_cache(cache_path, retrieved_at, verse, base_url)
        except (OSError, ValueError, RecursionError):
            print("regrid: warning: verse cache not saved", file=sys.stderr)
    try:
        dates = county_freshness.county_dates(verse, county)
    except county_freshness.FreshnessError as exc:
        if state == "hit":
            raise ValueError(
                "County not found in cached verse response; use --refresh to refetch"
            ) from exc
        raise
    print(
        json.dumps(
            {**dates, "verse_retrieved_at": retrieved_at, "cache": state},
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
    )


def _run_freshness(args: dict[str, Any]) -> int:
    sent: list[int] = []
    message = None
    try:
        _freshness(args, sent)
    except (RegridError, ValueError, TypeError, OSError, RecursionError) as exc:
        message = _error_message(
            exc,
            os_error="Could not read or write the verse cache",
            type_error="Invalid verse response",
        )
    print(f"regrid: requests made: {sent[0] if sent else 0}", file=sys.stderr)
    if message is not None:
        print(f"regrid: {message}", file=sys.stderr)
        return 1
    return 0


# Commands that run locally: no token, no HTTP client.
_OFFLINE = {"map": _run_map, "fields": _run_fields, "export": _run_export}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Regrid API CLI. Authentication uses REGRID_TOKEN; schemas are public."
    )
    parser.add_argument("--timeout", type=float, default=30, help="Request timeout in seconds")
    parser.add_argument(
        "--base-url", default="https://app.regrid.com/api/v2", help="HTTPS API base URL"
    )
    parser.add_argument(
        "--tiles-base-url", default="https://tiles.regrid.com", help="HTTPS tiles base URL"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    offline = commands.add_parser(
        "map",
        help="Render a saved parcel response as an offline satellite map (no API call)",
        description="Render a saved parcel response as a self-contained satellite map HTML file.",
    )
    offline.add_argument("response", help="Saved parcel response JSON file")
    offline.add_argument("output", help="Destination HTML file")
    offline.add_argument("--feature", type=int, metavar="N", help="Zero-based feature index")
    offline.add_argument("--all-candidates", action="store_true", help="Map every feature")
    offline.add_argument("--retrieved-at", metavar="ISO", help="Retrieval timestamp to display")
    offline.add_argument(
        "--neighbours", type=Path, metavar="FILE", help="Saved neighbouring parcels response"
    )
    offline.add_argument("--replace", action="store_true", help="Overwrite an existing output")
    export = commands.add_parser(
        "export",
        help="Export a saved parcel response to CSV and/or GeoJSON (offline, no API call)",
        description="Write core parcel columns as CSV and/or a GeoJSON FeatureCollection.",
    )
    export.add_argument("response", help="Saved parcel response JSON file")
    export.add_argument("--csv", metavar="FILE", help="Destination CSV file")
    export.add_argument("--geojson", metavar="FILE", help="Destination GeoJSON file")
    export.add_argument("--all-fields", action="store_true", help="Append every other field")
    export.add_argument("--replace", action="store_true", help="Overwrite existing outputs")
    field_catalog = commands.add_parser(
        "fields",
        help="Explain or search US parcel field definitions (offline, no API call)",
        description="Explain or search the packaged parcel field catalog without any API call.",
    )
    field_actions = field_catalog.add_subparsers(dest="action", required=True)
    field_explain = field_actions.add_parser("explain", help="Show definitions of named fields")
    field_explain.add_argument("names", nargs="+", metavar="NAME")
    field_search = field_actions.add_parser(
        "search", help="Find fields by name, description or category"
    )
    field_search.add_argument("term")
    freshness = commands.add_parser(
        "freshness",
        help="Show a county's published data dates from /verse (cached)",
        description="Report county data dates from a cached /verse response; dates only.",
    )
    freshness.add_argument("--path", required=True, help="Regrid path, e.g. /us/nj/camden")
    freshness.add_argument("--cache", metavar="FILE", help="Verse cache file")
    freshness.add_argument("--refresh", action="store_true", help="Ignore the cache and refetch")
    freshness.add_argument(
        "--max-age-days",
        type=_max_age_days,
        default=30,
        metavar="N",
        help="Refetch a cache older than N days (default 30)",
    )
    address_map = commands.add_parser(
        "address-map",
        help=(
            "Look up one address (one API request; two with --neighbours) "
            "and render it as an offline satellite map"
        ),
        description="Make one address lookup, save the response, and render a satellite map.",
    )
    address_map.add_argument("address")
    address_map.add_argument("output", help="Destination HTML file")
    address_map.add_argument("--path", help="Regrid path scope, e.g. /us/nj/camden")
    address_map.add_argument("--save-response", metavar="FILE", help="Response JSON destination")
    address_map.add_argument("--retrieved-at", metavar="ISO", help="Retrieval timestamp to show")
    address_map.add_argument(
        "--neighbours",
        action="store_true",
        help="Also fetch neighbouring parcels (one extra request, up to 25 records)",
    )
    address_map.add_argument("--replace", action="store_true", help="Overwrite existing outputs")
    option_commands = {
        "point",
        "area",
        "address",
        "apn",
        "owner",
        "query",
        "parcel",
        "parcel-path",
        "schema",
        "verse",
        "usage",
    }
    country_commands = option_commands - {"schema"} | {"typeahead"}
    descriptions = {
        "point": "Find parcels by coordinates or Point/MultiPoint GeoJSON",
        "area": "Find parcels intersecting GeoJSON geometry",
        "query": 'Query 1-4 fields: --fields \'{"geoid":{"eq":"48113"}}\'',
        "schema": "Fetch public schema: parcel, building, address, enhanced_ownership, zoning, ca",
        "report": "Submit a data issue report (creates an external report)",
        "tile": "Download binary tile to a file",
        "grid": "Fetch UTFGrid JSON using raster TileJSON metadata",
    }
    for name in (
        "point",
        "area",
        "address",
        "apn",
        "owner",
        "query",
        "parcel",
        "parcel-path",
        "typeahead",
        "client-token-typeahead",
        "schema",
        "verse",
        "usage",
        "report",
        "tilejson",
        "tile",
        "grid",
    ):
        sub = commands.add_parser(
            name, help=descriptions.get(name, name), description=descriptions.get(name)
        )
        if name in option_commands:
            sub.add_argument(
                "--options",
                default="{}",
                help=(
                    "SDK keyword options as JSON object or @file; e.g. "
                    '\'{"limit":5,"return_geometry":true}\'. Endpoint-specific validation applies.'
                ),
            )
        if name in country_commands:
            sub.add_argument("--country", choices=["us", "ca"], default="us")
        if name in {"point", "area"}:
            sub.add_argument(
                "--geojson", required=name == "area", help="GeoJSON object as JSON string or @file"
            )
            sub.add_argument("--method", choices=["GET", "POST"], default="GET")
        if name in {"point", "area", "query"}:
            sub.add_argument(
                "--max-records",
                type=int,
                help="Follow offset_id cursors for up to N records; requires limit in --options",
            )
        if name == "point":
            sub.add_argument("--lat", type=float)
            sub.add_argument("--lon", type=float)
        positional = {
            "address": "query",
            "apn": "parcelnumb",
            "owner": "owner",
            "parcel": "ll_uuid",
            "parcel-path": "path",
            "typeahead": "query",
        }
        if name in positional:
            sub.add_argument(positional[name])
        if name == "query":
            sub.add_argument(
                "--validate-fields",
                action="store_true",
                help="Validate against the US field catalog",
            )
            sub.add_argument(
                "--allow-unknown-fields",
                action="store_true",
                help="Allow fields absent from the queryability snapshot",
            )
            sub.add_argument(
                "--fields",
                required=True,
                help='JSON object or @file: {"field":{"operator":"value"}}',
            )
        if name == "schema":
            sub.add_argument(
                "name",
                nargs="?",
                default="parcel",
                choices=["parcel", "building", "address", "enhanced_ownership", "zoning", "ca"],
            )
        if name == "client-token-typeahead":
            sub.add_argument("--exp", type=float, help="Token lifetime in seconds")
        if name == "usage":
            sub.add_argument(
                "--detailed", action="store_true", help="Include per-endpoint usage detail"
            )
        if name == "report":
            for field in ("comment", "path", "ll-uuid"):
                sub.add_argument("--" + field)
            details = sub.add_mutually_exclusive_group()
            details.add_argument("--details", help="Details JSON object or @file")
            details.add_argument("--details-text", help="Plain text report details")
        if name in {"tile", "tilejson"}:
            sub.add_argument("--format", choices=["mvt", "png"], default="mvt")
        if name in {"tile", "grid"}:
            for field in ("z", "x", "y"):
                sub.add_argument(field, type=int)
        if name == "grid":
            sub.add_argument("--metadata", help="Raster TileJSON object as JSON or @file")
        if name == "tile":
            sub.add_argument("--retina", action="store_true")
            sub.add_argument("--output", required=True, help="Destination for binary tile bytes")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return its process exit status."""
    parser = _parser()
    try:
        args = vars(parser.parse_args(argv))
    except SystemExit as exc:
        return int(exc.code or 0)
    command = args.pop("command").replace("-", "_")
    offline_handler = _OFFLINE.get(command)
    if offline_handler is not None:
        try:
            offline_handler(args)
        except (ValueError, OSError) as exc:  # MapError is a ValueError
            print(f"regrid: {' '.join(str(exc).split())}", file=sys.stderr)
            return 1
        return 0
    if command == "freshness":
        return _run_freshness(args)
    if command == "address_map":
        return _run_address_map(args)
    timeout = args.pop("timeout")
    base_url = args.pop("base_url")
    tiles_base_url = args.pop("tiles_base_url")
    output = args.pop("output", None)
    max_records = args.pop("max_records", None)
    count = 0
    progress: dict[str, Any] = {}
    try:
        options = _object(args.pop("options", "{}"))
        for name in ("geojson", "fields", "details", "metadata"):
            if args.get(name) is not None:
                args[name] = _object(args[name])
        details_text = args.pop("details_text", None)
        if details_text is not None:
            args["details"] = details_text
        if options.keys() & args.keys():
            raise ValueError("--options conflicts with an explicit command argument")
        with _client(
            {"timeout": timeout, "base_url": base_url, "tiles_base_url": tiles_base_url}
        ) as client:
            try:
                if max_records is None:
                    result = getattr(client, command)(**args, **options)
                else:
                    result = _paged_search(client, command, args, options, max_records, progress)
            finally:
                count = client.request_count
        if output is not None:
            Path(output).write_bytes(result)
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
    except (RegridError, ValueError, TypeError, OSError, RecursionError) as exc:
        # SDK messages are sanitized; local messages may contain supplied option names/paths.
        generic = "Invalid input or output file"
        if isinstance(exc, (RegridError, _PagingError, RecursionError)):
            message = _error_message(exc, os_error=generic, type_error=generic)
        else:
            message = generic
        if isinstance(exc, (RegridError, _PagingError)) and progress.get("pages"):
            partial = _paged_result(
                progress["merged"], progress["features"], progress["pages"], False
            )
            try:
                text = json.dumps(partial, indent=2, ensure_ascii=False, allow_nan=False)
            except (ValueError, RecursionError):
                text = None
            if text is not None:
                print(text)
        print(f"regrid: {message}", file=sys.stderr)
        print(f"regrid: requests made: {count}", file=sys.stderr)
        return 1
    print(f"regrid: requests made: {count}", file=sys.stderr)
    return 0
