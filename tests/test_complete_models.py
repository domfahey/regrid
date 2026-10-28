"""Response contracts for the documented premium and metadata datasets."""

import httpx
import pytest
from pydantic import ValidationError

from regrid import RegridDecodeError, TypedRegridClient
from regrid.models import (
    BuildingProperties,
    EnhancedOwnership,
    MatchedAddress,
    ParcelResponse,
    SchemaField,
    SchemaResponse,
    TypeaheadResponse,
    VerseResponse,
    ZoningProperties,
)

# Explicit source field inventories catch accidentally untyped extras: an invalid
# value must fail for every documented field, even with extra="allow".
ADDRESS_FIELDS = """
a_id a_address a_saddno a_saddpref a_saddstr a_saddsttyp a_saddstsuf a_sunit
 a_szip5 a_szip a_carte a_crtype a_scity a_state2 a_county a_delvseqno
 a_usps_elotseq a_usps_elotsort a_resbus a_pmbdesc a_pmbno a_dpv_confirm
 a_dpv_footnotes a_default_match a_lacsflag a_usps_vacancy a_nostats a_error_code
 a_extrainfo a_dpv_type a_geocodetype a_moddate a_census_blockgroup a_lat a_lon
 a_geoid ll_uuid
""".split()
OWNERSHIP_FIELDS = """
attom_id eo_deedowner eo_deedowner2 eo_deedowner2first eo_deedowner2last
 eo_deedowner2middle eo_deedowner2suffix eo_deedowner3 eo_deedowner3first
 eo_deedowner3last eo_deedowner3middle eo_deedowner3suffix eo_deedowner4
 eo_deedowner4first eo_deedowner4last eo_deedowner4middle eo_deedowner4suffix
 eo_deedownerfirst eo_deedownerlast eo_deedownermiddle eo_deedownersuffix
 eo_geoid eo_last_refresh eo_mail_adddir eo_mail_addno eo_mail_addpref
 eo_mail_address eo_mail_addressinfoformat eo_mail_addstr eo_mail_addstsuf
 eo_mail_carte eo_mail_city eo_mail_county eo_mail_geoid eo_mail_state2
 eo_mail_unit eo_mail_unitpref eo_mail_zip eo_mail_zip4 eo_owner eo_owner2
 eo_owner2first eo_owner2last eo_owner2middle eo_owner2suffix eo_owner3
 eo_owner3first eo_owner3last eo_owner3middle eo_owner3suffix eo_owner4
 eo_owner4first eo_owner4last eo_owner4middle eo_owner4suffix eo_ownerfirst
 eo_ownerlast eo_ownermiddle eo_ownersuffix ll_uuid
""".split()
BUILDING = {
    "ed_str_uuid": "structure-id",
    "ed_bld_uuid": "building-id",
    "ed_geoid": "00123",
    "ed_lat": 32.5,
    "ed_lon": -96.5,
    "ed_bldg_footprint_sqft": 1200.25,
    "ed_largest": 1,
    "ed_source": "imagery",
    "ed_source_date": "01/02/2026",
    "ll_uuids": ["parcel-one", "parcel-two"],
    "ed_mean_height": 25.5,
    "ed_max_object_height": 27,
    "ed_lag": 100,
    "ed_hag": 102,
    "ed_mean_elevation": 101,
    "ed_mean_slope": 3,
    "ed_stories": 2,
    "ed_gross_area": 2400.5,
    "ed_volume": 30000,
}
ZONING = {
    "ogc_fid": 1,
    "zoning_id": 2,
    "municipality_id": 3,
    "municipality_name": "Example",
    "zoning": "R1",
    "zoning_description": "Residential",
    "zoning_type": "Residential",
    "zoning_subtype": "Single family",
    "zoning_guide": "Guide",
    "zoning_code_link": "https://example.test/code",
    "land_use_flags_permitted": "residential",
    "land_use_flags_conditional": "office",
    "landuse_classes": {"permitted": ["house", "garage"], "conditional": []},
    "min_lot_area_sq_ft": 5000,
    "min_lot_width_ft": 50,
    "max_building_height_ft": 35,
    "max_far": 0.5,
    "max_coverage_pct": 40,
    "min_front_setback_ft": 20,
    "min_rear_setback_ft": 10,
    "max_impervious_coverage_pct": 60,
    "min_side_setback_ft": 5,
    "min_landscaped_space_pct": 20,
    "min_open_space_pct": 30,
    "max_density_du_per_acre": 4,
    "zoning_data_date": "2026-01-02",
}


@pytest.mark.parametrize("field", ADDRESS_FIELDS)
def test_each_matched_address_field_rejects_lossy_coercion(field):
    with pytest.raises(ValidationError):
        MatchedAddress.model_validate({field: 123})


@pytest.mark.parametrize("field", OWNERSHIP_FIELDS)
def test_each_ownership_field_rejects_lossy_coercion(field):
    with pytest.raises(ValidationError):
        EnhancedOwnership.model_validate({field: 123})


@pytest.mark.parametrize("field", list(BUILDING))
def test_each_building_field_has_a_validated_type(field):
    with pytest.raises(ValidationError):
        BuildingProperties.model_validate({field: False})


@pytest.mark.parametrize("field", list(ZONING))
def test_each_zoning_field_has_a_validated_type(field):
    with pytest.raises(ValidationError):
        ZoningProperties.model_validate({field: False})


def test_premium_datasets_are_typed_without_losing_nested_fields():
    address = {field: "0001" for field in ADDRESS_FIELDS}
    address.update(a_sunit=None, upstream_new_address=[1, None])
    ownership = {field: "0002" for field in OWNERSHIP_FIELDS}
    ownership.update(eo_last_refresh="2026-01-02", eo_owner2=None, upstream_new_owner=True)
    building = {**BUILDING, "upstream_new_building": {"value": None}}
    zoning = {**ZONING, "upstream_new_zone": "future"}
    payload = {
        "parcels": {
            "features": [
                {
                    "properties": {
                        "fields": {"county_identifier": "0003"},
                        "addresses": [address],
                        "enhanced_ownership": [ownership],
                    }
                }
            ]
        },
        "buildings": {"features": [{"id": 1, "geometry": None, "properties": building}]},
        "zoning": {"features": [{"id": 2, "properties": zoning}]},
    }
    seen = []

    def handler(request):
        seen.append(request)
        assert request.url.params["return_enhanced_ownership"] == "true"
        return httpx.Response(200, json=payload)

    with TypedRegridClient("test-token", transport=httpx.MockTransport(handler)) as client:
        result = client.address("Main St", return_enhanced_ownership=True)
    assert len(seen) == 1
    properties = result.parcels.features[0].properties
    assert isinstance(properties.addresses[0], MatchedAddress)
    assert properties.addresses[0].a_szip5 == "0001"
    assert properties.addresses[0].a_sunit is None
    assert isinstance(properties.enhanced_ownership[0], EnhancedOwnership)
    assert properties.enhanced_ownership[0].attom_id == "0002"
    assert properties.enhanced_ownership[0].eo_last_refresh == "2026-01-02"
    assert isinstance(result.buildings.features[0].properties, BuildingProperties)
    assert result.buildings.features[0].properties.ll_uuids == ["parcel-one", "parcel-two"]
    assert result.buildings.features[0].properties.ed_gross_area == 2400.5
    assert isinstance(result.zoning.features[0].properties, ZoningProperties)
    assert result.zoning.features[0].properties.landuse_classes["permitted"] == ["house", "garage"]
    assert result.to_dict() == payload


@pytest.mark.parametrize("field", ["addresses", "enhanced_ownership"])
def test_missing_null_and_empty_parcel_datasets_stay_distinct(field):
    for value in [None, []]:
        payload = {"parcels": {"features": [{"properties": {field: value}}]}}
        assert ParcelResponse.model_validate(payload).to_dict() == payload
    absent = {"parcels": {"features": [{"properties": {}}]}}
    assert ParcelResponse.model_validate(absent).to_dict() == absent


@pytest.mark.parametrize(
    "payload",
    [
        {"parcels": {"features": [{"properties": {"addresses": [{"a_szip5": 123}]}}]}},
        {"parcels": {"features": [{"properties": {"enhanced_ownership": [{"eo_owner": 123}]}}]}},
        {"buildings": {"features": [{"properties": {"ll_uuids": [1]}}]}},
        {"buildings": {"features": [{"properties": {"ed_stories": 1.5}}]}},
        {"zoning": {"features": [{"properties": {"landuse_classes": {"permitted": [1]}}}]}},
    ],
)
def test_invalid_premium_values_fail_at_typed_boundary(payload):
    with TypedRegridClient(
        "test-token",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)),
    ) as client:
        with pytest.raises(RegridDecodeError) as caught:
            client.address("Main")
    assert caught.value.__context__ is None


@pytest.mark.parametrize(
    "geometry",
    [
        {"type": "Point", "coordinates": [-97, 32]},
        {"type": "Polygon", "coordinates": [[[-97, 32], [-96, 32], [-97, 33], [-97, 32]]]},
        {"type": "MultiPolygon", "coordinates": [[[[-97, 32], [-96, 32], [-97, 33], [-97, 32]]]]},
    ],
)
def test_typeahead_properties_and_geometry_are_typed(geometry):
    payload = {
        "parcel_centroids": {
            "features": [
                {
                    "id": 42,
                    "geometry": geometry,
                    "properties": {
                        "ll_uuid": "parcel-id",
                        "score": 86.75966,
                        "context": {"path": "/us/tx/dallas"},
                        "path": "/us/tx/dallas/example",
                        "address": "123 Main",
                        "future": None,
                    },
                }
            ]
        }
    }
    result = TypeaheadResponse.model_validate(payload)
    properties = result.parcel_centroids.features[0].properties
    assert properties.ll_uuid == "parcel-id"
    assert properties.score == 86.75966
    assert properties.context["path"] == "/us/tx/dallas"
    assert properties.path == "/us/tx/dallas/example"
    assert properties.address == "123 Main"
    assert result.to_dict() == payload


@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("ll_uuid", 1),
        ("score", "99"),
        ("context", []),
        ("path", 1),
        ("address", 1),
    ],
)
def test_typeahead_known_properties_are_validated(field, bad_value):
    with pytest.raises(ValidationError):
        TypeaheadResponse.model_validate(
            {"parcel_centroids": {"features": [{"properties": {field: bad_value}}]}}
        )


@pytest.mark.parametrize("wrapped", [False, True])
def test_schema_fields_have_same_typed_access_in_both_wire_shapes(wrapped):
    fields = {
        "parcelnumb": {
            "type": "text",
            "human": "APN",
            "tier": "premium",
            "description": "Parcel number",
            "examples": ["0001"],
            "future": None,
        },
        "reserved": {},
    }
    payload = {"schema": fields, "revision": 2} if wrapped else {**fields, "revision": 2}
    result = SchemaResponse.model_validate(payload)
    assert isinstance(result.field_definitions["parcelnumb"], SchemaField)
    assert result.field_definitions["parcelnumb"].human == "APN"
    assert result.field_definitions["parcelnumb"].examples == ["0001"]
    assert result.field_definitions["reserved"].type is None
    assert result.to_dict() == payload
    if not wrapped:
        assert result.model_extra["parcelnumb"] == fields["parcelnumb"]


@pytest.mark.parametrize("wrapped", [False, True])
def test_schema_field_types_validated_for_direct_and_wrapped_maps(wrapped):
    fields = {"known_field": {"description": 123}}
    with pytest.raises(ValidationError):
        SchemaResponse.model_validate({"schema": fields} if wrapped else fields)


def test_single_schema_description_response_remains_lossless():
    payload = {"type": "numeric", "description": "Source field", "future": None}
    result = SchemaResponse.model_validate(payload)
    assert result.field_definitions == {}
    assert result.to_dict() == payload


def test_country_metadata_includes_remaining_documented_fields():
    payload = {
        "type": "Feature",
        "properties": {
            "admin0": "ca",
            "admin1": "mb",
            "admin2": "Division 22",
            "admin2_slug": 22,
            "admin2_center": None,
            "shapefile_size_flag": "large",
            "population": "00123",
            "date_added": None,
            "sqkm": 12.5,
            "extra": False,
        },
    }
    result = VerseResponse.model_validate(payload)
    assert result.properties.admin2_slug == 22
    assert result.properties.admin2_center is None
    assert result.properties.shapefile_size_flag == "large"
    assert result.to_dict() == payload
