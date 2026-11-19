"""Copy src/regrid/offline helpers into the skill's scripts directory.

Usage: python scripts/sync_skill_helpers.py [--check]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = Path("src/regrid/offline")
SKILL_SCRIPTS = Path("plugins/regrid-research/skills/property-research/scripts")

# source name -> skill name
HELPERS: dict[str, str] = {
    "map.py": "map.py",
    "fields.py": "fields.py",
    "freshness.py": "freshness.py",
}


def sync(root: Path, *, check: bool) -> list[str]:
    """Return helper names whose skill copy differs; write them unless ``check``."""
    differing: list[str] = []
    for source_name, skill_name in HELPERS.items():
        source = root / SOURCE_DIR / source_name
        target = root / SKILL_SCRIPTS / skill_name
        data = source.read_bytes()
        if target.exists() and target.read_bytes() == data:
            continue
        differing.append(source_name)
        if not check:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    return differing


def main(argv: list[str] | None = None, *, root: Path = ROOT) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if copies are out of sync")
    args = parser.parse_args(argv)
    differing = sync(root, check=args.check)
    if args.check and differing:
        print(f"out of sync: {', '.join(differing)}; run python scripts/sync_skill_helpers.py")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
