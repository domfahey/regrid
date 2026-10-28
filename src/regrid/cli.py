"""Command line access to the synchronous Regrid SDK."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from .client import RegridClient, RegridError


def _object(value: str) -> dict[str, Any]:
    """Load an object without including possibly sensitive input in errors."""
    try:
        raw = Path(value[1:]).read_text() if value.startswith("@") else value
        result = json.loads(raw)
    except (OSError, ValueError, UnicodeError):
        raise ValueError("Expected valid JSON or @file containing JSON") from None
    if not isinstance(result, dict):
        raise ValueError("JSON input must be an object")
    return result


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
            sub.add_argument("--detailed", action="store_true")
        if name == "report":
            for field in ("comment", "path", "ll-uuid"):
                sub.add_argument(
                    "--" + field, help=("JSON object or @file" if field == "details" else None)
                )
            details = sub.add_mutually_exclusive_group()
            details.add_argument("--details", help="Details JSON object or @file")
            details.add_argument("--details-text", help="Plain text report details")
        if name in {"tile", "tilejson"}:
            sub.add_argument("--format", choices=["mvt", "png"], default="mvt")
        if name == "tile":
            for field in ("z", "x", "y"):
                sub.add_argument(field, type=int)
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
    timeout = args.pop("timeout")
    base_url = args.pop("base_url")
    tiles_base_url = args.pop("tiles_base_url")
    output = args.pop("output", None)
    try:
        options = _object(args.pop("options", "{}"))
        for name in ("geojson", "fields", "details"):
            if args.get(name) is not None:
                args[name] = _object(args[name])
        details_text = args.pop("details_text", None)
        if details_text is not None:
            args["details"] = details_text
        if options.keys() & args.keys():
            raise ValueError("--options conflicts with an explicit command argument")
        with RegridClient(
            token=os.environ.get("REGRID_TOKEN"),
            timeout=timeout,
            base_url=base_url,
            tiles_base_url=tiles_base_url,
        ) as client:
            result = getattr(client, command)(**args, **options)
        if output is not None:
            Path(output).write_bytes(result)
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
    except (RegridError, ValueError, TypeError, OSError) as exc:
        # SDK messages are sanitized; local messages may contain supplied option names/paths.
        message = str(exc) if isinstance(exc, RegridError) else "Invalid input or output file"
        print(f"regrid: {message}", file=sys.stderr)
        return 1
    return 0
