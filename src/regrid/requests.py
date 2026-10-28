"""Strict, endpoint-scoped request validation for the Regrid API.

Only safe SDK errors cross the validation boundary. Raw Pydantic errors can
contain user-provided values in ``errors()`` even when their display is hidden.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from functools import lru_cache
from typing import Annotated, Any, Literal, TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
    StringConstraints,
    ValidationError,
    create_model,
    field_validator,
    model_validator,
)

NonemptyText = Annotated[str, StringConstraints(strict=True, min_length=1)]
Number = Annotated[StrictInt | StrictFloat, Field(allow_inf_nan=False)]
Latitude = Annotated[Number, Field(ge=-90, le=90)]
Longitude = Annotated[Number, Field(ge=-180, le=180)]
Limit = Annotated[int, Field(strict=True, ge=1, le=1000)]
Radius = Annotated[int, Field(strict=True, ge=0, le=32000)]
Offset = Annotated[int, Field(strict=True, ge=0)]
FieldName = Annotated[str, StringConstraints(strict=True, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")]
Operator = Annotated[str, StringConstraints(strict=True, pattern=r"^[a-z_]+$")]


class StrictRequest(BaseModel):
    """Request values cannot be coerced and undeclared keys cannot be sent."""

    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)


RequestT = TypeVar("RequestT", bound=BaseModel)


def safe_validate(model: type[RequestT], data: Any) -> RequestT:
    """Validate without exposing input values, error locations, or error context."""
    try:
        return model.model_validate(data)
    except ValidationError:
        pass
    # Raise outside the except block: even __context__ must not retain raw input.
    raise ValueError("Invalid Regrid request parameters")


class TextInput(StrictRequest):
    value: NonemptyText

    @field_validator("value")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Text must not be blank")
        return value


class CountryInput(StrictRequest):
    value: Literal["us", "ca"]


class GeometryInput(StrictRequest):
    """Preserve GeoJSON fields while validating the object envelope and JSON values.

    Topology and area limits are checked by Regrid rather than guessed from its
    inconsistent example polygons.
    """

    geojson: dict[str, Any]

    @field_validator("geojson")
    @classmethod
    def geometry_object(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(value.get("type"), str) or not value["type"]:
            raise ValueError("GeoJSON requires a type")
        try:
            json.dumps(value, allow_nan=False)
        except (TypeError, ValueError, OverflowError):
            raise ValueError("GeoJSON must contain finite JSON values") from None
        return value


class PointRequest(StrictRequest):
    lat: Latitude | None = None
    lon: Longitude | None = None
    geojson: dict[str, Any] | None = None
    method: Literal["GET", "POST"] = "GET"

    @model_validator(mode="after")
    def valid_point(self) -> PointRequest:
        if self.geojson is None:
            if self.lat is None or self.lon is None or self.method == "POST":
                raise ValueError("Coordinates or GeoJSON are required; POST requires GeoJSON")
        else:
            shape = (
                self.geojson.get("geometry")
                if self.geojson.get("type") == "Feature"
                else self.geojson
            )
            if not isinstance(shape, Mapping) or shape.get("type") not in {"Point", "MultiPoint"}:
                raise ValueError("Point search requires Point or MultiPoint geometry")
        return self


class MethodInput(StrictRequest):
    value: Literal["GET", "POST"]


class TokenRequest(StrictRequest):
    exp: Annotated[Number, Field(gt=0)] | None = None


class QueryRequest(StrictRequest):
    fields: Annotated[dict[FieldName, dict[Operator, Any]], Field(min_length=1, max_length=4)]

    @field_validator("fields")
    @classmethod
    def valid_filters(cls, value: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        for operators in value.values():
            if not operators:
                raise ValueError("Each field requires an operator")
        try:
            json.dumps(value, allow_nan=False)
        except (TypeError, ValueError, OverflowError):
            raise ValueError("Filters require finite JSON values") from None
        return value


# Each endpoint's existing allowlist selects an exact model from this registry.
# Models are cached so repeated SDK calls do not rebuild Pydantic schemas.
_OPTION_TYPES: dict[str, Any] = {
    "limit": Limit,
    "radius": Radius,
    "offset_id": Offset,
    "path": NonemptyText,
    "geojson": dict[str, Any] | str,
    "begin_date": Annotated[str, StringConstraints(strict=True, pattern=r"^\d{4}-\d{2}-\d{2}$")],
    "end_date": Annotated[str, StringConstraints(strict=True, pattern=r"^\d{4}-\d{2}-\d{2}$")],
}
for _name in (
    "return_custom",
    "return_field_labels",
    "return_stacked",
    "return_zoning",
    "return_matched_buildings",
    "return_matched_addresses",
    "return_enhanced_ownership",
    "return_parcels",
    "return_count",
    "return_geometry",
    "return_custom_id",
    "return_full_history",
    "return_by_token",
    "return_by_this_token",
    "premium_only",
):
    _OPTION_TYPES[_name] = bool


@lru_cache(maxsize=32)
def _option_model(allowed: frozenset[str]) -> type[BaseModel]:
    fields: dict[str, Any] = {name: (_OPTION_TYPES[name] | None, None) for name in sorted(allowed)}
    return create_model("EndpointOptions", __base__=StrictRequest, **fields)


def validate_options(options: dict[str, Any], allowed: set[str]) -> dict[str, Any]:
    model = safe_validate(_option_model(frozenset(allowed)), options)
    result = model.model_dump(exclude_none=True, exclude_unset=True)
    if "return_parcels" in allowed:
        result.setdefault("return_parcels", True)
    return result
