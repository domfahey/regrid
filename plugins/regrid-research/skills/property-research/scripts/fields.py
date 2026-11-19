"""Offline parcel field catalog: explain and search field definitions.

Uses only the standard library, makes no network requests, and never reads credentials.
Accepts the compact skill catalog (references/fields.json) or the full parcel_fields.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

DEFAULT_CATALOG = Path(__file__).resolve().parent.parent / "references" / "fields.json"
KEYS = ("name", "datatype", "tier", "category", "description")


def load_catalog(path: Path) -> list[dict]:
    """Load field definitions, reduced to the compact keys and sorted by name."""
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    entries = document.get("fields") if isinstance(document, dict) else None
    if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
        raise ValueError("Unrecognized field catalog format")
    compact = [{key: entry.get(key) for key in KEYS} for entry in entries]
    return sorted(compact, key=lambda entry: str(entry["name"]))


def explain(catalog: list[dict], names: list[str]) -> dict:
    """Return the definitions of ``names`` and the names absent from the catalog."""
    by_name = {entry["name"]: entry for entry in catalog}
    found = [by_name[name] for name in names if name in by_name]
    unknown = [name for name in names if name not in by_name]
    return {"found": found, "unknown": unknown}


def search(catalog: list[dict], term: str) -> list[dict]:
    """Return fields whose name, description or category contains ``term``."""
    needle = term.lower()
    hits = [
        entry
        for entry in catalog
        if any(
            needle in str(entry.get(key) or "").lower()
            for key in ("name", "description", "category")
        )
    ]
    return sorted(hits, key=lambda entry: str(entry["name"]))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Explain or search Regrid parcel fields offline.")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG, help="Catalog JSON file")
    commands = parser.add_subparsers(dest="command", required=True)
    explain_parser = commands.add_parser(
        "explain", parents=[common], help="Show definitions of named fields"
    )
    explain_parser.add_argument("names", nargs="+", metavar="NAME")
    search_parser = commands.add_parser(
        "search", parents=[common], help="Find fields by name, description or category"
    )
    search_parser.add_argument("term")
    args = parser.parse_args(argv)
    try:
        catalog = load_catalog(args.catalog)
    except (OSError, ValueError) as exc:
        print(f"fields: {' '.join(str(exc).split())}", file=sys.stderr)
        return 1
    if args.command == "explain":
        result: dict = explain(catalog, args.names)
    else:
        result = {"matches": search(catalog, args.term)}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
