"""Typed response envelopes that retain upstream and county-specific fields.

Known fields are validated without string/boolean coercion. Optional fields are
not manufactured by ``to_dict``; absent and explicitly null values stay distinct.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

Number: TypeAlias = int | float
Position: TypeAlias = Annotated[list[Number], Field(min_length=2, max_length=3)]


class RegridModel(BaseModel):
    """Forward-compatible response model with strict known-field validation."""

    model_config = ConfigDict(
        extra="allow", strict=True, hide_input_in_errors=True, allow_inf_nan=False
    )

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-compatible data, retaining unknown fields and explicit nulls."""
        return self.model_dump(mode="json", by_alias=True, exclude_unset=True)


class Point(RegridModel):
    type: Literal["Point"]
    coordinates: Position


class MultiPoint(RegridModel):
    type: Literal["MultiPoint"]
    coordinates: list[Position]


class LineString(RegridModel):
    type: Literal["LineString"]
    coordinates: list[Position]


class MultiLineString(RegridModel):
    type: Literal["MultiLineString"]
    coordinates: list[list[Position]]


class Polygon(RegridModel):
    type: Literal["Polygon"]
    coordinates: list[list[Position]]


class MultiPolygon(RegridModel):
    type: Literal["MultiPolygon"]
    coordinates: list[list[list[Position]]]


class GeometryCollection(RegridModel):
    type: Literal["GeometryCollection"]
    geometries: list[Geometry]


Geometry: TypeAlias = Annotated[
    Point | MultiPoint | LineString | MultiLineString | Polygon | MultiPolygon | GeometryCollection,
    Field(discriminator="type"),
]
GeometryCollection.model_rebuild()


class ParcelProperties(RegridModel):
    headline: str | None = None
    path: str | None = None
    ll_uuid: str | None = None
    fields: dict[str, Any] | None = None
    field_labels: dict[str, Any] | None = None
    context: dict[str, Any] | None = None
    addresses: list[dict[str, Any]] | None = None
    score: Number | None = None


class ParcelFeature(RegridModel):
    type: Literal["Feature"] = "Feature"
    geometry: Geometry | None = None
    properties: ParcelProperties | None = None
    id: int | str | None = None
    ll_uuid: str | None = None


class ParcelCollection(RegridModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[ParcelFeature]


class Feature(RegridModel):
    """A feature for extensible building, zoning, metadata, or centroid properties."""

    type: Literal["Feature"] = "Feature"
    geometry: Geometry | None = None
    properties: dict[str, Any] | None = None
    id: int | str | None = None


class FeatureCollection(RegridModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[Feature]


class ParcelResponse(RegridModel):
    parcels: ParcelCollection | None = None
    buildings: FeatureCollection | None = None
    zoning: FeatureCollection | None = None

    @model_validator(mode="before")
    @classmethod
    def require_dataset(cls, value: Any) -> Any:
        if isinstance(value, dict) and not {"parcels", "buildings", "zoning"}.intersection(value):
            raise ValueError("Parcel response must include a dataset")
        return value


class AreaMeasurements(RegridModel):
    sq_meters: Number | None = None
    acres: Number | None = None
    sq_miles: Number | None = None


class CountResponse(RegridModel):
    count: int = Field(ge=0)
    area: AreaMeasurements | None = None


ParcelSearchResponse: TypeAlias = ParcelResponse | CountResponse


def parse_parcel_response(data: dict[str, Any]) -> ParcelSearchResponse:
    """Select count responses explicitly instead of losing count-only semantics."""
    if "count" in data and not {"parcels", "buildings", "zoning"}.intersection(data):
        return CountResponse.model_validate(data)
    return ParcelResponse.model_validate(data)


class TypeaheadResponse(RegridModel):
    parcel_centroids: FeatureCollection


class SchemaField(RegridModel):
    type: str | None = None
    human: str | None = None
    tier: str | None = None
    description: str | None = None
    examples: list[Any] | None = None


class SchemaResponse(RegridModel):
    """Schema envelopes and direct schema maps both retain their original keys."""

    schema_: dict[str, SchemaField] | None = Field(default=None, alias="schema")


class CycleDates(RegridModel):
    begin: Number | None = None
    end: Number | None = None


class UsageData(RegridModel):
    requests: int | None = None
    results: int | None = None
    tiles: int | None = None
    features: int | None = None
    typeahead: int | None = None
    addresses: int | None = None
    buildings: int | None = None
    ownership: int | None = None
    zoning: int | None = None
    area: AreaMeasurements | None = None


class DateRangeUsage(RegridModel):
    begin_ts: Number | None = None
    begin: str | None = None
    end: str | None = None
    total: UsageData | None = None


class TokenUsage(RegridModel):
    name: str | None = None
    token_fragment: str | None = Field(default=None, repr=False)
    cycle_usage: UsageData | None = None
    full_history: list[DateRangeUsage] | None = None


class UsageSummary(RegridModel):
    cycle_dates: CycleDates | None = None
    cycle_usage: UsageData | None = None
    date_range: DateRangeUsage | None = None
    full_history: list[DateRangeUsage] | None = None
    by_token: list[TokenUsage] | None = None


class UsageResponse(RegridModel):
    usage: UsageSummary


class DetailedUsageRow(RegridModel):
    country: str | None = None
    service: str | None = None
    requests: int | None = None
    buildings: int | None = None
    addresses: int | None = None
    ownership: int | None = None
    zoning: int | None = None
    parcels: int | None = None
    area: AreaMeasurements | None = None
    date: str | None = None


class DetailedDateRange(RegridModel):
    begin_ts: Number | None = None
    begin: str | None = None
    end: str | None = None
    total: list[DetailedUsageRow] | None = None
    counts: list[DetailedUsageRow] | None = None


class DetailedUsageSummary(RegridModel):
    cycle_dates: CycleDates | None = None
    cycle_usage: list[DetailedUsageRow] | None = None
    date_range: DetailedDateRange | None = None
    full_history: list[DetailedDateRange] | None = None


class DetailedUsageResponse(RegridModel):
    usage: DetailedUsageSummary


class VerseProperties(RegridModel):
    """Common US and Canada source metadata; date strings retain upstream formatting."""

    id: int | None = None
    path: str | None = None
    canonical_path: str | None = None
    county: str | None = None
    state: str | None = None
    city: str | None = None
    seat: str | None = None
    admin0: str | None = None
    admin1: str | None = None
    admin2: str | None = None
    admin3: str | None = None
    geoid: str | None = None
    total_objects: int | None = None
    last_refresh: str | None = None
    assessor_data_date: str | None = None
    usps_data_date: str | None = None
    date_added: str | None = None
    filename_stem: str | None = None
    table_name: str | None = None
    # The two supplied country schemas disagree on population's numeric type.
    population: int | str | None = None
    sqmi: Number | None = None
    sqkm: Number | None = None


class VerseFeature(RegridModel):
    type: Literal["Feature"] = "Feature"
    geometry: Geometry | None = None
    properties: VerseProperties | None = None
    id: int | str | None = None


class VerseResponse(RegridModel):
    """County metadata, supporting both documented Feature and collection envelopes."""

    type: Literal["Feature", "FeatureCollection"]
    geometry: Geometry | None = None
    properties: VerseProperties | None = None
    features: list[VerseFeature] | None = None
    id: int | str | None = None

    @model_validator(mode="before")
    @classmethod
    def require_shape_content(cls, value: Any) -> Any:
        if isinstance(value, dict):
            if value.get("type") == "FeatureCollection" and not isinstance(
                value.get("features"), list
            ):
                raise ValueError("FeatureCollection metadata requires features")
            if value.get("type") == "Feature" and "properties" not in value:
                raise ValueError("Feature metadata requires properties")
        return value


class ClientTokenResponse(RegridModel):
    """Token values stay masked except through explicit ``to_dict`` or get_secret_value."""

    token: SecretStr = Field(repr=False)
    expires_at: Number

    def to_dict(self) -> dict[str, Any]:
        """Explicitly export the temporary token; treat the result as a credential."""
        result = super().to_dict()
        result["token"] = self.token.get_secret_value()
        return result


class ReportResponse(RegridModel):
    message: str
    id: int


class TileJSON(RegridModel):
    tiles: list[str]
    tilejson: str | None = None
    name: str | None = None
    attribution: str | None = None
    minzoom: int | None = None
    maxzoom: int | None = None
    bounds: list[Number] | None = None
    center: list[Number] | None = None
