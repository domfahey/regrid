"""Generated parcel field model; regenerate with scripts/generate_parcel_fields.py.

Catalog version: 2026-07-09. Values stay in their original JSON representation.
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

    ogc_fid: int | None = None
    geoid: str | None = None
    parcelnumb: str | None = None
    parcelnumb_no_formatting: str | None = None
    state_parcelnumb: str | None = None
    account_number: str | None = None
    tax_id: str | None = None
    alt_parcelnumb1: str | None = None
    alt_parcelnumb2: str | None = None
    alt_parcelnumb3: str | None = None
    usecode: str | None = None
    usedesc: str | None = None
    zoning: str | None = None
    zoning_description: str | None = None
    zoning_type: str | None = None
    zoning_subtype: str | None = None
    zoning_code_link: str | None = None
    zoning_id: int | None = None
    struct: bool | None = None
    structno: int | None = None
    yearbuilt: int | None = None
    year_built_effective_date: int | None = None
    numstories: int | float | None = None
    numunits: int | None = None
    numrooms: int | float | None = None
    num_bath: int | float | None = None
    num_bath_partial: int | float | None = None
    num_bedrooms: int | None = None
    structstyle: str | None = None
    parvaltype: str | None = None
    improvval: int | float | None = None
    landval: int | float | None = None
    parval: int | float | None = None
    agval: int | float | None = None
    homestead_exemption: str | None = None
    saleprice: int | float | None = None
    saledate: DateString | None = None
    taxamt: int | float | None = None
    taxyear: str | None = None
    last_ownership_transfer_date: DateString | None = None
    owntype: str | None = None
    owner: str | None = None
    unmodified_owner: str | None = None
    ownfrst: str | None = None
    ownlast: str | None = None
    owner2: str | None = None
    owner3: str | None = None
    owner4: str | None = None
    previous_owner: str | None = None
    mailadd: str | None = None
    mail_address2: str | None = None
    careof: str | None = None
    mail_addno: str | None = None
    mail_addpref: str | None = None
    mail_addstr: str | None = None
    mail_addsttyp: str | None = None
    mail_addstsuf: str | None = None
    mail_unit: str | None = None
    mail_city: str | None = None
    mail_state2: str | None = None
    mail_zip: str | None = None
    mail_country: str | None = None
    mail_urbanization: str | None = None
    original_mailing_address: str | None = None
    address: str | None = None
    address2: str | None = None
    saddno: str | None = None
    saddpref: str | None = None
    saddstr: str | None = None
    saddsttyp: str | None = None
    saddstsuf: str | None = None
    sunit: str | None = None
    scity: str | None = None
    original_address: str | None = None
    city: str | None = None
    county: str | None = None
    state2: str | None = None
    szip: str | None = None
    szip5: str | None = None
    urbanization: str | None = None
    ll_address_count: int | None = None
    location_name: str | None = None
    address_source: str | None = None
    legaldesc: str | None = None
    plat: str | None = None
    book: str | None = None
    page: str | None = None
    block: str | None = None
    lot: str | None = None
    neighborhood: str | None = None
    neighborhood_code: str | None = None
    subdivision: str | None = None
    lat: str | None = None
    lon: str | None = None
    fema_flood_zone: str | None = None
    fema_flood_zone_subtype: str | None = None
    fema_flood_zone_raw: str | None = None
    fema_flood_zone_data_date: DateString | None = None
    fema_nri_risk_rating: str | None = None
    qoz: str | None = None
    qoz_tract: str | None = None
    census_tract: str | None = None
    census_block: str | None = None
    census_blockgroup: str | None = None
    census_zcta: str | None = None
    census_elementary_school_district: str | None = None
    census_secondary_school_district: str | None = None
    census_unified_school_district: str | None = None
    ll_last_refresh: DateString | None = None
    sourceurl: str | None = None
    recrdareatx: str | None = None
    recrdareano: int | None = None
    area_building: int | None = None
    area_building_definition: str | None = None
    deeded_acres: int | float | None = None
    gisacre: int | float | None = None
    sqft: int | float | None = None
    ll_gisacre: int | float | None = None
    ll_gissqft: int | None = None
    ll_bldg_footprint_sqft: int | None = None
    ll_bldg_count: int | None = None
    cdl_raw: str | None = None
    cdl_majority_category: str | None = None
    cdl_majority_percent: int | float | None = None
    cdl_date: str | None = None
    insite_score: str | None = None
    plss_township: str | None = None
    plss_section: str | None = None
    plss_range: str | None = None
    reviseddate: DateString | None = None
    path: str | None = None
    ll_stable_id: str | None = None
    ll_uuid: UUIDString | None = None
    ll_stack_uuid: str | None = None
    ll_row_parcel: str | None = None
    ll_updated_at: TimestampString | None = None
    precisely_id: str | None = None
    placekey: str | None = None
    dpv_status: str | None = None
    dpv_codes: str | None = None
    dpv_notes: str | None = None
    dpv_type: str | None = None
    cass_errorno: str | None = None
    rdi: str | None = None
    usps_vacancy: str | None = None
    usps_vacancy_date: DateString | None = None
    padus_public_access: str | None = None
    lbcs_activity: int | float | None = None
    lbcs_activity_desc: str | None = None
    lbcs_function: int | float | None = None
    lbcs_function_desc: str | None = None
    lbcs_structure: int | float | None = None
    lbcs_structure_desc: str | None = None
    lbcs_site: int | float | None = None
    lbcs_site_desc: str | None = None
    lbcs_ownership: int | float | None = None
    lbcs_ownership_desc: str | None = None
    housing_affordability_index: int | float | None = None
    population_density: int | float | None = None
    population_growth_past_5_years: int | float | None = None
    population_growth_next_5_years: int | float | None = None
    housing_growth_past_5_years: int | float | None = None
    housing_growth_next_5_years: int | float | None = None
    household_income_growth_next_5_years: int | float | None = None
    median_household_income: int | float | None = None
    transmission_line_distance: int | float | None = None
    roughness_rating: int | float | None = None
    highest_parcel_elevation: int | float | None = None
    lowest_parcel_elevation: int | float | None = None
