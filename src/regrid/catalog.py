"""Versioned US parcel field definitions; unknown metadata is not a negative claim."""

from __future__ import annotations

from collections.abc import Mapping
from importlib.resources import files
from types import MappingProxyType
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SQLDatatype = Literal[
    "serial primary key",
    "text",
    "boolean",
    "integer",
    "double precision",
    "date",
    "bigint",
    "uuid",
    "timestamp with time zone",
    "numeric",
]


class ParcelField(BaseModel):
    """One immutable documented field; standard fields also appear in Premium."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    datatype: SQLDatatype
    tier: Literal["standard", "premium"]
    description: str = Field(min_length=1)
    documentation_url: str
    queryable: bool | None = None
    source: str | None = None
    standardized: Literal["yes", "no", "some", "not-applicable"] | None = None
    category: str | None = None
    preferred_alternatives: tuple[str, ...] = ()

    @property
    def coverage_column(self) -> str:
        """Column to inspect in the separately maintained coverage report."""
        return f"{self.name}_pct"


class ParcelCatalog(BaseModel):
    """Snapshot metadata and ordered field entries, validated when loaded."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    version: str
    metadata_reviewed_on: str
    query_documentation_url: str
    country: Literal["us"]
    source: str
    fields: tuple[ParcelField, ...]

    @model_validator(mode="after")
    def unique_names_and_known_alternatives(self) -> ParcelCatalog:
        names = {field.name for field in self.fields}
        if len(names) != len(self.fields):
            raise ValueError("Duplicate parcel field names")
        for field in self.fields:
            if not set(field.preferred_alternatives) <= names:
                raise ValueError("Unknown preferred parcel field")
        return self


def load_catalog() -> ParcelCatalog:
    """Load packaged data without a network request or working-directory dependency."""
    return ParcelCatalog.model_validate_json(
        files("regrid").joinpath("data/parcel_fields.json").read_text(encoding="utf-8")
    )


_CATALOG = load_catalog()
CATALOG_VERSION: str = _CATALOG.version
PARCEL_FIELDS: Mapping[str, ParcelField] = MappingProxyType(
    {field.name: field for field in _CATALOG.fields}
)
