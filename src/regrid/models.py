"""Typed response envelopes that retain upstream and county-specific fields.

Known fields are validated without string/boolean coercion. Optional fields are
not manufactured by ``to_dict``; absent and explicitly null values stay distinct.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, model_validator

from .parcel_fields import ParcelFields

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


class MatchedAddress(RegridModel):
    """Matched secondary-address fields retain source strings and leading zeros."""

    a_id: str | None = None
    a_address: str | None = None
    a_saddno: str | None = None
    a_saddpref: str | None = None
    a_saddstr: str | None = None
    a_saddsttyp: str | None = None
    a_saddstsuf: str | None = None
    a_sunit: str | None = None
    a_szip5: str | None = None
    a_szip: str | None = None
    a_carte: str | None = None
    a_crtype: str | None = None
    a_scity: str | None = None
    a_state2: str | None = None
    a_county: str | None = None
    a_delvseqno: str | None = None
    a_usps_elotseq: str | None = None
    a_usps_elotsort: str | None = None
    a_resbus: str | None = None
    a_pmbdesc: str | None = None
    a_pmbno: str | None = None
    a_dpv_confirm: str | None = None
    a_dpv_footnotes: str | None = None
    a_default_match: str | None = None
    a_lacsflag: str | None = None
    a_nostats: str | None = None
    a_error_code: str | None = None
    a_extrainfo: str | None = None
    a_dpv_type: str | None = None
    a_geocodetype: str | None = None
    a_moddate: str | None = None
    a_census_blockgroup: str | None = None
    a_lat: str | None = None
    a_lon: str | None = None
    a_geoid: str | None = None
    ll_uuid: str | None = None
    a_usps_vacancy: str | None = None


class EnhancedOwnership(RegridModel):
    """Enhanced ownership fields; date values retain the upstream string format."""

    attom_id: str | None = None
    eo_deedowner: str | None = None
    eo_deedowner2: str | None = None
    eo_deedowner2first: str | None = None
    eo_deedowner2last: str | None = None
    eo_deedowner2middle: str | None = None
    eo_deedowner2suffix: str | None = None
    eo_deedowner3: str | None = None
    eo_deedowner3first: str | None = None
    eo_deedowner3last: str | None = None
    eo_deedowner3middle: str | None = None
    eo_deedowner3suffix: str | None = None
    eo_deedowner4: str | None = None
    eo_deedowner4first: str | None = None
    eo_deedowner4last: str | None = None
    eo_deedowner4middle: str | None = None
    eo_deedowner4suffix: str | None = None
    eo_deedownerfirst: str | None = None
    eo_deedownerlast: str | None = None
    eo_deedownermiddle: str | None = None
    eo_deedownersuffix: str | None = None
    eo_geoid: str | None = None
    eo_last_refresh: str | None = None
    eo_mail_adddir: str | None = None
    eo_mail_addno: str | None = None
    eo_mail_addpref: str | None = None
    eo_mail_address: str | None = None
    eo_mail_addressinfoformat: str | None = None
    eo_mail_addstr: str | None = None
    eo_mail_addstsuf: str | None = None
    eo_mail_carte: str | None = None
    eo_mail_city: str | None = None
    eo_mail_county: str | None = None
    eo_mail_geoid: str | None = None
    eo_mail_state2: str | None = None
    eo_mail_unit: str | None = None
    eo_mail_unitpref: str | None = None
    eo_mail_zip: str | None = None
    eo_mail_zip4: str | None = None
    eo_owner: str | None = None
    eo_owner2: str | None = None
    eo_owner2first: str | None = None
    eo_owner2last: str | None = None
    eo_owner2middle: str | None = None
    eo_owner2suffix: str | None = None
    eo_owner3: str | None = None
    eo_owner3first: str | None = None
    eo_owner3last: str | None = None
    eo_owner3middle: str | None = None
    eo_owner3suffix: str | None = None
    eo_owner4: str | None = None
    eo_owner4first: str | None = None
    eo_owner4last: str | None = None
    eo_owner4middle: str | None = None
    eo_owner4suffix: str | None = None
    eo_ownerfirst: str | None = None
    eo_ownerlast: str | None = None
    eo_ownermiddle: str | None = None
    eo_ownersuffix: str | None = None
    ll_uuid: str | None = None


class ParcelProperties(RegridModel):
    headline: str | None = None
    path: str | None = None
    ll_uuid: str | None = None
    fields: dict[str, Any] | None = None
    field_labels: dict[str, Any] | None = None
    context: dict[str, Any] | None = None
    addresses: list[MatchedAddress] | None = None
    enhanced_ownership: list[EnhancedOwnership] | None = None
    score: Number | None = None

    @property
    def typed_fields(self) -> ParcelFields | None:
        """Validate US parcel fields on demand without changing their raw dictionary."""
        if self.fields is None:
            return None
        try:
            return ParcelFields.model_validate(self.fields)
        except ValidationError:
            pass
        # Import lazily to avoid coupling model imports to transport initialization.
        from .client import RegridDecodeError

        raise RegridDecodeError("Parcel fields failed schema validation")


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


class BuildingProperties(RegridModel):
    ed_str_uuid: str | None = None
    ed_bld_uuid: str | None = None
    ed_geoid: str | None = None
    ed_lat: Number | None = None
    ed_lon: Number | None = None
    ed_bldg_footprint_sqft: Number | None = None
    ed_largest: Number | None = None
    ed_source: str | None = None
    ed_source_date: str | None = None
    ll_uuids: list[str] | None = None
    ed_mean_height: Number | None = None
    ed_max_object_height: Number | None = None
    ed_lag: Number | None = None
    ed_hag: Number | None = None
    ed_mean_elevation: Number | None = None
    ed_mean_slope: int | None = None
    ed_stories: int | None = None
    ed_gross_area: Number | None = None
    ed_volume: Number | None = None


class BuildingFeature(RegridModel):
    type: Literal["Feature"] = "Feature"
    geometry: Geometry | None = None
    properties: BuildingProperties | None = None
    id: int | None = None


class BuildingCollection(RegridModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[BuildingFeature]


class ZoningProperties(RegridModel):
    ogc_fid: int | None = None
    zoning_id: int | None = None
    municipality_id: int | None = None
    municipality_name: str | None = None
    zoning: str | None = None
    zoning_description: str | None = None
    zoning_type: str | None = None
    zoning_subtype: str | None = None
    zoning_guide: str | None = None
    zoning_code_link: str | None = None
    land_use_flags_permitted: str | None = None
    land_use_flags_conditional: str | None = None
    landuse_classes: dict[str, list[str]] | None = None
    min_lot_area_sq_ft: Number | None = None
    min_lot_width_ft: Number | None = None
    max_building_height_ft: Number | None = None
    max_far: Number | None = None
    max_coverage_pct: Number | None = None
    min_front_setback_ft: Number | None = None
    min_rear_setback_ft: Number | None = None
    max_impervious_coverage_pct: Number | None = None
    min_side_setback_ft: Number | None = None
    min_landscaped_space_pct: Number | None = None
    min_open_space_pct: Number | None = None
    max_density_du_per_acre: Number | None = None
    zoning_data_date: str | None = None


class ZoningFeature(RegridModel):
    type: Literal["Feature"] = "Feature"
    geometry: Geometry | None = None
    properties: ZoningProperties | None = None
    id: int | None = None


class ZoningCollection(RegridModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[ZoningFeature]


class ParcelResponse(RegridModel):
    parcels: ParcelCollection | None = None
    buildings: BuildingCollection | None = None
    zoning: ZoningCollection | None = None

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


class TypeaheadProperties(RegridModel):
    ll_uuid: str | None = None
    score: Number | None = None
    context: dict[str, Any] | None = None
    path: str | None = None
    address: str | None = None


class TypeaheadFeature(RegridModel):
    type: Literal["Feature"] = "Feature"
    # The supplied centroid schema says Polygon/MultiPolygon; actual centroids
    # may be Points. Keep the common geometry union to preserve both contracts.
    geometry: Geometry | None = None
    properties: TypeaheadProperties | None = None
    id: int | None = None


class TypeaheadCollection(RegridModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[TypeaheadFeature]


class TypeaheadResponse(RegridModel):
    parcel_centroids: TypeaheadCollection


class SchemaField(RegridModel):
    type: str | None = None
    human: str | None = None
    tier: str | None = None
    description: str | None = None
    examples: list[Any] | None = None


class SchemaResponse(RegridModel):
    """Schema envelopes and direct schema maps both retain their original keys."""

    schema_: dict[str, SchemaField] | None = Field(default=None, alias="schema")

    @property
    def field_definitions(self) -> dict[str, SchemaField]:
        """Typed fields from either a schema envelope or a direct field map.

        Direct-map object values are validated while scalar metadata remains
        available in model_extra and to_dict().
        """
        if self.schema_ is not None:
            return self.schema_
        return {
            key: SchemaField.model_validate(value)
            for key, value in (self.model_extra or {}).items()
            if isinstance(value, dict)
        }

    @model_validator(mode="after")
    def validate_direct_fields(self) -> SchemaResponse:
        self.field_definitions
        return self


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
    admin2_slug: int | None = None
    admin2_center: int | None = None
    admin3: str | None = None
    geoid: str | None = None
    total_objects: int | None = None
    last_refresh: str | None = None
    assessor_data_date: str | None = None
    usps_data_date: str | None = None
    date_added: str | None = None
    filename_stem: str | None = None
    shapefile_size_flag: str | None = None
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


class UTFGridResponse(RegridModel):
    """UTFGrid rows, index keys, and feature data with unknown fields retained."""

    grid: list[str]
    keys: list[str]
    data: dict[str, Any]
