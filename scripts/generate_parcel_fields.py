"""Generate statically discoverable ParcelFields attributes from the versioned catalog."""

from __future__ import annotations

import argparse
from pathlib import Path

HEADER = '''"""Generated parcel field model; regenerate with scripts/generate_parcel_fields.py.

Catalog version: {version}. Values stay in their original JSON representation.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict


def _date_string(value: str) -> str:
    if len(value) != 10 or value[4] != "-" or value[7] != "-":
        raise ValueError("Expected an ISO calendar date")
    date.fromisoformat(value)
    return value


def _timestamp_string(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Expected a timestamp with time zone")
    return value


def _uuid_string(value: str) -> str:
    UUID(value)
    return value


DateString = Annotated[str, AfterValidator(_date_string)]
TimestampString = Annotated[str, AfterValidator(_timestamp_string)]
UUIDString = Annotated[str, AfterValidator(_uuid_string)]


class ParcelFields(BaseModel):
    """Opt-in US fields with strict known types and lossless unknown attributes."""

    model_config = ConfigDict(
        extra="allow", strict=True, hide_input_in_errors=True, allow_inf_nan=False
    )

    def to_dict(self) -> dict[str, Any]:
        """Preserve aliases, unknown fields, and missing versus explicit null values."""
        return self.model_dump(mode="json", by_alias=True, exclude_unset=True)

'''

TYPES = {
    "text": "str",
    "serial primary key": "int",
    "integer": "int",
    "bigint": "int",
    "boolean": "bool",
    "double precision": "int | float",
    "numeric": "int | float",
    "date": "DateString",
    "timestamp with time zone": "TimestampString",
    "uuid": "UUIDString",
}


def render() -> str:
    from regrid.catalog import CATALOG_VERSION, PARCEL_FIELDS

    return HEADER.format(version=CATALOG_VERSION) + "".join(
        f"    {name}: {TYPES[field.datatype]} | None = None\n"
        for name, field in PARCEL_FIELDS.items()
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if generated fields are stale")
    args = parser.parse_args()
    target = Path(__file__).resolve().parents[1] / "src/regrid/parcel_fields.py"
    generated = render()
    if args.check:
        if not target.exists() or target.read_text() != generated:
            print("ParcelFields is stale; run scripts/generate_parcel_fields.py")
            return 1
    else:
        target.write_text(generated)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
