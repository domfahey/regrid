"""Generate the skill's compact field catalog from src/regrid/data/parcel_fields.json.

Usage: python scripts/generate_skill_fields.py [--check]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("src/regrid/data/parcel_fields.json")
TARGET = Path("plugins/regrid-research/skills/property-research/references/fields.json")
KEYS = ("name", "datatype", "tier", "category", "description")


def render(root: Path) -> str:
    document = json.loads((root / SOURCE).read_text(encoding="utf-8"))
    fields = sorted(
        ({key: entry[key] for key in KEYS} for entry in document["fields"]), key=lambda e: e["name"]
    )
    compact = {"version": document["version"], "country": document["country"], "fields": fields}
    return json.dumps(compact, indent=1, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None, *, root: Path = ROOT) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if fields.json is stale")
    args = parser.parse_args(argv)
    text = render(root)
    target = root / TARGET
    current = target.read_text(encoding="utf-8") if target.exists() else None
    if current == text:
        return 0
    if args.check:
        print("fields.json is stale; run python scripts/generate_skill_fields.py")
        return 1
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
