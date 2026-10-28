"""Opt-in checks against the versioned US field catalog; no network access."""

from __future__ import annotations

from typing import Any

from .catalog import PARCEL_FIELDS

_TEXT = {"eq", "ne", "isnull", "in", "nin", "ilike"}
_ORDERED = {"eq", "ne", "isnull", "in", "nin", "between", "gt", "gte", "lt", "lte", "order"}
_BOOLEAN = {"eq", "ne", "isnull"}
_NUMERIC = {"serial primary key", "integer", "bigint", "double precision", "numeric"}


def validate_catalog_filters(
    fields: dict[str, dict[str, Any]], *, country: str, allow_unknown: bool, paging: bool
) -> None:
    """Validate known filters without echoing potentially sensitive filter values.

    The escape hatch permits fields whose queryability is unknown to this
    snapshot. Explicitly nonqueryable fields still fail. Existing structural
    validation (including the four-field maximum) always runs first.
    """
    if country != "us":
        raise ValueError("The field catalog currently covers US queries only")
    for name, filters in fields.items():
        field = PARCEL_FIELDS.get(name)
        if field is None or field.queryable is not True:
            if allow_unknown and (field is None or field.queryable is None):
                continue
            raise ValueError("Field is not queryable in the local catalog")
        boolean_like = name in {"usps_vacancy", "rdi"}
        numeric = field.datatype in _NUMERIC
        ordered = numeric or field.datatype in {"date", "timestamp with time zone"}
        operators = (
            _BOOLEAN
            if boolean_like or field.datatype == "boolean"
            else (_ORDERED if ordered else _TEXT)
        )
        # Regrid's text table omits these, but its zoning example explicitly supports them.
        if name == "zoning":
            operators = operators | {"between", "order"}
        for operator, value in filters.items():
            if operator not in operators:
                raise ValueError("Operator is not supported for this catalog field")
            if operator == "isnull":
                valid = type(value) is bool
            elif operator == "order":
                valid = isinstance(value, str) and value in {"ASC", "DESC"} and not paging
            else:
                values = value if operator in {"in", "nin", "between"} else [value]
                valid = isinstance(values, (list, tuple)) and bool(values)
                if operator == "between":
                    valid = valid and len(values) == 2
                if valid:
                    for item in values:
                        if numeric:
                            valid = type(item) in {int, float}
                        elif field.datatype == "boolean":
                            valid = type(item) is bool
                        else:
                            valid = isinstance(item, str)
                        if not valid:
                            break
            if not valid:
                raise ValueError("Invalid value or pagination combination for catalog operator")
