"""Opt-in, bounded live check of every read-only endpoint; never imported by ordinary checks.

Output is one status line per step and contains only counts, types, booleans and HTTP
status codes: never the token, address, coordinates, identifiers, parcel numbers, owner
names, paths below county level, response bodies or exception details.
"""

from __future__ import annotations

import datetime
import logging
import math
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .client import RegridClient, RegridHTTPError
from .live import DEFAULT_ADDRESS
from .models import (
    DetailedUsageResponse,
    ParcelResponse,
    SchemaResponse,
    TileJSON,
    TypeaheadResponse,
    UsageResponse,
    UTFGridResponse,
    VerseResponse,
)
from .offline.map import feature_uuid

MAX_REQUESTS = 30
BAD_TOKEN = "invalid-token-for-live-check"
SCHEMA_NAMES = ("parcel", "building", "address", "enhanced_ownership", "zoning")
TILE_ZOOM = 16
# Searches never request premium data or stacked parcels.
FLAGS: dict[str, Any] = {
    "return_stacked": False,
    "return_zoning": False,
    "return_matched_buildings": False,
    "return_matched_addresses": False,
    "return_enhanced_ownership": False,
}


class CheckFailed(Exception):
    """A step's own check failed; the message is a fixed, non-sensitive string."""


@dataclass
class Outcome:
    detail: str
    notes: list[str] = field(default_factory=list)


@dataclass
class Subject:
    feature_id: Any = None
    ll_uuid: str | None = None
    path: str | None = None
    county: str | None = None
    parcelnumb: str | None = None
    owner: str | None = None
    lat: float | None = None
    lon: float | None = None
    geoid: str | None = None


def _features(payload: dict[str, Any]) -> list[dict[str, Any]]:
    features = payload["parcels"]["features"]
    if not isinstance(features, list):
        raise CheckFailed("malformed feature list")
    return features


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _number(value: Any, limit: float = 180) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) and abs(result) <= limit else None


def county_path(path: str | None) -> str | None:
    """The first four segments of a canonical path: /us/st/county."""
    if not path:
        return None
    parts = path.strip("/").split("/")
    return "/" + "/".join(parts[:3]) if len(parts) >= 3 else None


def tile_xy(lat: float, lon: float, zoom: int) -> tuple[int, int]:
    """Slippy-map tile indices containing a coordinate."""
    n = 2**zoom
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)
    return min(max(x, 0), n - 1), min(max(y, 0), n - 1)


def square(lat: float, lon: float, half_metres: float = 10.0) -> dict[str, Any]:
    """A closed GeoJSON square of roughly 2 * half_metres per side."""
    dlat = half_metres / 111_320.0
    dlon = half_metres / (111_320.0 * max(math.cos(math.radians(lat)), 0.01))
    ring = [
        [round(lon - dlon, 7), round(lat - dlat, 7)],
        [round(lon + dlon, 7), round(lat - dlat, 7)],
        [round(lon + dlon, 7), round(lat + dlat, 7)],
        [round(lon - dlon, 7), round(lat + dlat, 7)],
    ]
    ring.append(ring[0])
    return {"type": "Polygon", "coordinates": [ring]}


def _cursor(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, str) and value.isascii() and value.isdigit():
        return int(value)
    return None


class Runner:
    def __init__(
        self,
        client: RegridClient,
        bad_client: RegridClient,
        address: str,
        enterprise: bool,
        max_requests: int,
    ):
        self.client = client
        self.bad_client = bad_client
        self.address = address
        self.enterprise = enterprise
        self.max_requests = max_requests
        self.failed = False
        self.exhausted = False
        self.subject: Subject | None = None
        self.baseline: UsageResponse | None = None
        self.point_id: Any = None
        self.area_id: Any = None

    def requests_made(self) -> int:
        return self.client.request_count + self.bad_client.request_count

    def step(self, name: str, cost: int, fn: Callable[[], Outcome | None]) -> bool:
        """Run one isolated step; True when it passed. Reserves one request for final usage."""
        if self.exhausted or self.requests_made() + cost > self.max_requests - 1:
            self.exhausted = True
            self.skip(name, "request cap reached")
            return False
        try:
            outcome = fn()
        except CheckFailed as error:
            print(f"FAIL {name}: {error}")
        except RegridHTTPError as error:
            print(f"FAIL {name}: HTTP {error.status_code}")
        except Exception:
            print(f"FAIL {name}: request or response validation failed")
        else:
            if outcome is None:
                return False
            print(f"PASS {name}: {outcome.detail}")
            for note in outcome.notes:
                print(f"NOTE {name}: {note}")
            return True
        self.failed = True
        return False

    @staticmethod
    def skip(name: str, reason: str) -> None:
        print(f"SKIP {name}: {reason}")

    def needs(self, name: str, **required: Any) -> Subject | None:
        """The subject if every named attribute is present, else a SKIP and None."""
        subject = self.subject
        if subject is None:
            self.skip(name, "no subject parcel")
            return None
        missing = [key for key in required if getattr(subject, key) in (None, "")]
        if missing:
            self.skip(name, "subject lacks " + ", ".join(missing))
            return None
        return subject

    # Steps -------------------------------------------------------------------------------

    def schemas(self) -> None:
        def parcel() -> Outcome:
            schema = SchemaResponse.model_validate(self.client.schema("parcel"))
            count = len(schema.field_definitions)
            if not count:
                raise CheckFailed("no field definitions")
            return Outcome(f"{count} definitions")

        def other(name: str) -> Callable[[], Outcome]:
            def check() -> Outcome:
                payload = self.client.schema(name)
                if not isinstance(payload, dict) or not payload:
                    raise CheckFailed("empty schema")
                body = payload.get("schema")
                count = len(body) if isinstance(body, dict) else len(payload)
                return Outcome(f"{count} definitions")

            return check

        self.step("schema parcel", 1, parcel)
        for name in SCHEMA_NAMES[1:]:
            self.step(f"schema {name}", 1, other(name))

    def usage_baseline(self) -> None:
        def check() -> Outcome:
            self.baseline = UsageResponse.model_validate(self.client.usage())
            return Outcome("validated")

        self.step("usage baseline", 1, check)

    def address_step(self) -> None:
        def check() -> Outcome:
            payload = self.client.address(self.address, limit=1, return_parcels=True, **FLAGS)
            response = ParcelResponse.model_validate(payload)
            if response.parcels is None or len(response.parcels.features) != 1:
                raise CheckFailed("expected exactly one result")
            properties = response.parcels.features[0].properties
            if properties is None or properties.typed_fields is None:
                raise CheckFailed("missing properties or fields")
            raw = payload["parcels"]["features"][0]
            fields = raw["properties"]["fields"]
            path = _text(raw["properties"].get("path"))
            self.subject = Subject(
                feature_id=raw.get("id"),
                ll_uuid=feature_uuid(raw),
                path=path,
                county=county_path(path),
                parcelnumb=_text(fields.get("parcelnumb")),
                owner=_text(fields.get("owner")),
                lat=_number(fields.get("lat"), 90),
                lon=_number(fields.get("lon")),
                geoid=_text(fields.get("geoid")),
            )
            if "geometry" not in raw:
                geometry = "absent"
            else:
                geometry = "null" if raw["geometry"] is None else "present"
            return Outcome(
                "1 feature; typed fields valid", [f"geometry {geometry}", "match not confirmed"]
            )

        self.step("address", 1, check)

    def by_uuid(self) -> None:
        subject = self.needs("parcel", ll_uuid=True)
        if subject is None:
            return

        def check() -> Outcome:
            payload = self.client.parcel(subject.ll_uuid or "", **FLAGS)
            return self._same_parcel(payload, subject)

        self.step("parcel", 1, check)

    def by_path(self) -> None:
        subject = self.needs("parcel-path", path=True)
        if subject is None:
            return

        def check() -> Outcome:
            payload = self.client.parcel_path(subject.path or "", **FLAGS)
            return self._same_parcel(payload, subject)

        self.step("parcel-path", 1, check)

    @staticmethod
    def _same_parcel(payload: dict[str, Any], subject: Subject) -> Outcome:
        features = _features(payload)
        if len(features) != 1:
            raise CheckFailed(f"expected one feature, got {len(features)}")
        if feature_uuid(features[0]) != subject.ll_uuid:
            raise CheckFailed("returned a different parcel")
        return Outcome("1 feature; same parcel")

    def apn(self) -> None:
        subject = self.needs("apn", county=True, parcelnumb=True)
        if subject is None:
            return

        def check() -> Outcome:
            payload = self.client.apn(
                subject.parcelnumb or "", path=subject.county, limit=1, **FLAGS
            )
            features = _features(payload)
            if not features:
                raise CheckFailed("no features")
            match = feature_uuid(features[0]) == subject.ll_uuid
            return Outcome(f"{len(features)} feature(s)", [f"match: {str(match).lower()}"])

        self.step("apn", 1, check)

    def owner(self) -> None:
        subject = self.needs("owner", county=True, owner=True)
        if subject is None:
            return
        if len((subject.owner or "").strip()) < 4:
            self.skip("owner", "subject owner name too short")
            return

        def check() -> Outcome:
            payload = self.client.owner(subject.owner or "", path=subject.county, limit=1, **FLAGS)
            features = _features(payload)
            if not features:
                raise CheckFailed("no features")
            match = feature_uuid(features[0]) == subject.ll_uuid
            return Outcome(
                f"{len(features)} feature(s)", [f"first is subject: {str(match).lower()}"]
            )

        self.step("owner", 1, check)

    def point_get(self) -> None:
        subject = self.needs("point GET", lat=True, lon=True)
        if subject is None:
            return

        def check() -> Outcome:
            payload = self.client.point(
                subject.lat, subject.lon, radius=1, limit=1, return_geometry=False, **FLAGS
            )
            features = _features(payload)
            if not features:
                raise CheckFailed("no features")
            self.point_id = features[0].get("id")
            return Outcome(f"{len(features)} feature(s)")

        self.step("point GET", 1, check)

    def point_post(self) -> None:
        subject = self.needs("point POST", lat=True, lon=True)
        if subject is None:
            return

        def check() -> Outcome:
            geojson = {"type": "Point", "coordinates": [subject.lon, subject.lat]}
            payload = self.client.point(geojson=geojson, method="POST", radius=1, limit=1, **FLAGS)
            features = _features(payload)
            if not features:
                raise CheckFailed("no features")
            same = self.point_id is not None and features[0].get("id") == self.point_id
            return Outcome(
                f"{len(features)} feature(s)", [f"same first id as GET: {str(same).lower()}"]
            )

        self.step("point POST", 1, check)

    def area(self, method: str) -> None:
        name = f"area {method}"
        subject = self.needs(name, lat=True, lon=True)
        if subject is None:
            return

        def check() -> Outcome:
            polygon = square(subject.lat or 0.0, subject.lon or 0.0)
            payload = self.client.area(
                polygon, method=method, limit=1, return_geometry=True, **FLAGS
            )
            features = _features(payload)
            if not features:
                raise CheckFailed("no features")
            if not features[0].get("geometry"):
                raise CheckFailed("geometry missing")
            notes = []
            if method == "GET":
                self.area_id = features[0].get("id")
            else:
                same = self.area_id is not None and features[0].get("id") == self.area_id
                notes.append(f"same first id as GET: {str(same).lower()}")
            return Outcome(f"{len(features)} feature(s); geometry present", notes)

        self.step(name, 1, check)

    def query(self) -> None:
        subject = self.needs("query", county=True, geoid=True)
        if subject is None:
            return

        def check() -> Outcome:
            payload = self.client.query(
                {"geoid": {"eq": subject.geoid}},
                path=subject.county,
                limit=1,
                return_geometry=False,
                **FLAGS,
            )
            features = _features(payload)
            if not features:
                raise CheckFailed("no features")
            return Outcome(f"{len(features)} feature(s)")

        self.step("query", 1, check)

    def paging(self) -> None:
        subject = self.needs("paging", lat=True, lon=True)
        if subject is None:
            return

        def check() -> Outcome:
            options: dict[str, Any] = {"radius": 50, "limit": 2, "return_geometry": False, **FLAGS}
            first = _features(self.client.point(subject.lat, subject.lon, offset_id=0, **options))
            ids = [_cursor(feature.get("id")) for feature in first]
            if not first or None in ids:
                raise CheckFailed("page 1 has no usable cursor")
            usable = [i for i in ids if i is not None]
            last = usable[-1]
            second = _features(
                self.client.point(subject.lat, subject.lon, offset_id=last, **options)
            )
            second_ids = [_cursor(feature.get("id")) for feature in second]
            if None in second_ids:
                raise CheckFailed("page 2 has unusable ids")
            later = [i for i in second_ids if i is not None]
            if set(usable) & set(later):
                raise CheckFailed("cursor record repeated; pager assumptions broke")
            ordered = (
                usable == sorted(set(usable))
                and later == sorted(set(later))
                and all(i > max(usable) for i in later)
            )
            if not ordered:
                raise CheckFailed("pages not in ascending id order from offset_id=0")
            return Outcome(
                f"page 1: {len(first)}, page 2: {len(second)}",
                [f"ordered: {str(ordered).lower()}"],
            )

        self.step("paging", 2, check)

    def verse(self) -> None:
        def check() -> Outcome:
            payload = self.client.verse(return_geometry=False)
            response = VerseResponse.model_validate(payload)
            entries = response.features if response.features is not None else [response]
            notes = []
            county = self.subject.county if self.subject else None
            if county:
                paths = {
                    str(value).rstrip("/")
                    for item in entries
                    if item.properties is not None
                    for value in (item.properties.path, item.properties.canonical_path)
                    if value
                }
                notes.append(f"subject county present: {str(county in paths).lower()}")
            return Outcome(f"{len(entries)} entries", notes)

        self.step("verse", 1, check)

    def usage_detailed(self) -> None:
        def check() -> Outcome:
            today = datetime.date.today()
            payload = self.client.usage(
                detailed=True,
                begin_date=today.replace(day=1).isoformat(),
                end_date=today.isoformat(),
            )
            try:
                detailed = DetailedUsageResponse.model_validate(payload)
            except Exception as exc:
                raise CheckFailed("response did not validate as DetailedUsageResponse") from exc
            rows = detailed.usage.cycle_usage
            if rows is None:
                raise CheckFailed("response has no cycle_usage rows")
            return Outcome(f"{len(rows)} cycle rows")

        self.step("usage detailed", 1, check)

    def tilejson(self) -> None:
        def check() -> Outcome:
            metadata = TileJSON.model_validate(self.client.tilejson(format="mvt"))
            if not metadata.tiles:
                raise CheckFailed("no tile template")
            return Outcome(f"{len(metadata.tiles)} template(s)")

        self.step("tilejson", 1, check)

    def tiles(self) -> None:
        subject = self.subject
        if subject is None or subject.lat is None or subject.lon is None:
            self.skip("tile", "no subject coordinates")
            self.skip("grid", "no subject coordinates")
            return
        x, y = tile_xy(subject.lat or 0.0, subject.lon or 0.0, TILE_ZOOM)

        def tile() -> Outcome:
            data = self.client.tile(TILE_ZOOM, x, y, format="mvt")
            return Outcome(f"{len(data)} bytes", [] if data else ["empty tile"])

        def grid() -> Outcome:
            response = UTFGridResponse.model_validate(self.client.grid(TILE_ZOOM, x, y))
            return Outcome(f"{len(response.grid)} rows, {len(response.keys)} keys")

        self.step("tile", 1, tile)
        self.step("grid", 2, grid)

    def bad_token(self) -> None:
        def check() -> Outcome | None:
            try:
                self.bad_client.usage()
            except RegridHTTPError as error:
                if error.status_code in (401, 403):
                    return Outcome(f"rejected with HTTP {error.status_code}")
                raise
            raise CheckFailed("invalid token was accepted")

        self.step("bad token", 1, check)

    def typeahead(self) -> None:
        if not self.enterprise:
            self.skip("typeahead", "needs an Enterprise token")
            return

        def check() -> Outcome:
            try:
                payload = self.client.typeahead(self.address)
            except RegridHTTPError as error:
                if error.status_code == 403:
                    raise CheckFailed("token lacks typeahead") from None
                raise
            response = TypeaheadResponse.model_validate(payload)
            return Outcome(f"{len(response.parcel_centroids.features)} suggestions")

        self.step("typeahead", 1, check)

    def final_usage(self) -> None:
        # Always attempted after billable requests; the cap reserves one request for it.
        try:
            final = UsageResponse.model_validate(self.client.usage())
        except Exception:
            print("FAIL final usage: consumption could not be checked")
            self.failed = True
            return
        baseline = self.baseline
        before = baseline.usage.cycle_usage if baseline else None
        after = final.usage.cycle_usage
        if (
            baseline is not None
            and before is not None
            and after is not None
            and before.results is not None
            and after.results is not None
            and baseline.usage.cycle_dates == final.usage.cycle_dates
        ):
            print(f"PASS final usage: observed record delta {after.results - before.results}")
        else:
            print("PASS final usage: comparable record counters unavailable")
        print("NOTE usage may lag or include other clients; delta is not a billing guarantee")

    def run(self) -> int:
        self.schemas()
        self.usage_baseline()
        self.address_step()
        self.by_uuid()
        self.by_path()
        self.apn()
        self.owner()
        self.point_get()
        self.point_post()
        self.area("GET")
        self.area("POST")
        self.query()
        self.paging()
        self.verse()
        self.usage_detailed()
        self.tilejson()
        self.tiles()
        self.bad_token()
        self.typeahead()
        self.final_usage()
        print(f"NOTE requests made: {self.requests_made()}")
        return 1 if self.failed else 0


def run(
    client: RegridClient,
    address: str,
    *,
    enterprise: bool = False,
    bad_client: RegridClient | None = None,
    max_requests: int | None = None,
) -> int:
    """Run every step; print status and aggregate counts only. Exit 0 only if nothing failed."""
    own = bad_client is None
    bad = bad_client or RegridClient(BAD_TOKEN, max_limit=2, default_limit=1)
    try:
        runner = Runner(
            client, bad, address, enterprise, MAX_REQUESTS if max_requests is None else max_requests
        )
        return runner.run()
    finally:
        if own:
            bad.close()


def main() -> int:
    """Require explicit configuration; never read .env or print exception details."""
    token = os.environ.get("REGRID_TOKEN", "").strip()
    address = os.environ.get("REGRID_LIVE_ADDRESS", "").strip() or DEFAULT_ADDRESS
    enterprise = os.environ.get("REGRID_LIVE_ENTERPRISE", "").strip() == "1"
    if not token or token == "replace_with_your_regrid_api_token":
        print("NOT RUN: set REGRID_TOKEN in your environment")
        return 2
    # HTTPX logging can reveal query-string credentials. Suppress it for this process.
    logging.disable(logging.CRITICAL)
    try:
        with RegridClient(token, max_limit=2, default_limit=1) as client:
            return run(client, address, enterprise=enterprise)
    except Exception:
        print("FAIL live full check initialization")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
