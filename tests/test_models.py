import pytest
from pydantic import ValidationError

from regrid.models import (
    ClientTokenResponse,
    CountResponse,
    DetailedUsageResponse,
    ParcelResponse,
    ReportResponse,
    SchemaResponse,
    TileJSON,
    TypeaheadResponse,
    UsageResponse,
    VerseResponse,
    parse_parcel_response,
)


@pytest.mark.parametrize(
    "geometry",
    [
        None,
        {"type": "Point", "coordinates": [1, 2]},
        {"type": "MultiPoint", "coordinates": [[1, 2, 3]]},
        {"type": "LineString", "coordinates": [[1, 2], [3, 4]]},
        {"type": "MultiLineString", "coordinates": [[[1, 2], [3, 4]]]},
        {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [0, 1], [0, 0]]]},
        {"type": "MultiPolygon", "coordinates": [[[[0, 0], [1, 0], [0, 1], [0, 0]]]]},
        {"type": "GeometryCollection", "geometries": [{"type": "Point", "coordinates": [1, 2]}]},
    ],
)
def test_parcels_preserve_geometry_custom_fields_and_nulls(geometry):
    payload = {
        "parcels": {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": geometry,
                    "properties": {
                        "headline": None,
                        "fields": {"parcelnumb": "00001", "custom": [1, None]},
                        "new_property": {"nested": True},
                    },
                    "new_feature_key": "new value",
                }
            ],
        },
        "upstream_new": [1, 2],
    }
    result = ParcelResponse.model_validate(payload)
    assert result.parcels.features[0].properties.fields["parcelnumb"] == "00001"
    assert result.to_dict() == payload


def test_optional_fields_are_not_manufactured():
    result = ParcelResponse.model_validate({"parcels": {"features": []}})
    assert result.buildings is None
    assert result.to_dict() == {"parcels": {"features": []}}
    assert ParcelResponse.model_validate({"parcels": None}).to_dict() == {"parcels": None}


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"unrelated": 1},
        {"parcels": {"features": "secret-input"}},
        {"parcels": {"features": [{"properties": {"fields": []}}]}},
        {"parcels": {"features": [{"geometry": {"type": "Point", "coordinates": ["1", 2]}}]}},
        {"parcels": {"features": [{"geometry": {"type": "Point", "coordinates": [True, 2]}}]}},
        {"parcels": {"features": [{"geometry": {"type": "Unknown", "coordinates": [1, 2]}}]}},
    ],
)
def test_invalid_parcel_known_fields_are_rejected(payload):
    with pytest.raises(ValidationError) as caught:
        ParcelResponse.model_validate(payload)
    assert "secret-input" not in str(caught.value)


def test_premium_only_response():
    payload = {
        "buildings": {"features": [{"properties": {"ed_mean_height": 10}}]},
        "zoning": {"features": [{"geometry": None, "properties": {"zoning": "R1"}}]},
    }
    assert ParcelResponse.model_validate(payload).to_dict() == payload


def test_count_selection_and_mixed_payload_preservation():
    payload = {"count": 2, "area": {"sq_meters": 10, "acres": 0.25}, "extra": None}
    count = parse_parcel_response(payload)
    assert isinstance(count, CountResponse)
    assert count.to_dict() == payload
    mixed = {"parcels": {"features": []}, "count": 0}
    assert isinstance(parse_parcel_response(mixed), ParcelResponse)
    assert parse_parcel_response(mixed).to_dict() == mixed


@pytest.mark.parametrize("count", [True, "1", -1, 1.5])
def test_count_is_nonnegative_integer(count):
    with pytest.raises(ValidationError):
        CountResponse.model_validate({"count": count})


def test_typeahead_accepts_real_point_and_documented_polygon():
    payload = {
        "parcel_centroids": {
            "features": [
                {
                    "geometry": {"type": "Point", "coordinates": [-97, 32]},
                    "properties": {"address": "Main St"},
                }
            ]
        }
    }
    assert TypeaheadResponse.model_validate(payload).to_dict() == payload


@pytest.mark.parametrize(
    "payload",
    [
        {
            "schema": {
                "parcelnumb": {"type": "text", "tier": "future", "examples": ["0001"], "new": True}
            }
        },
        {"field_name": {"type": "text", "description": "County-specific field"}},
    ],
)
def test_schema_formats_preserve_fields(payload):
    assert SchemaResponse.model_validate(payload).to_dict() == payload


def test_usage_history_token_and_unknown_counters():
    payload = {
        "usage": {
            "cycle_dates": {"begin": 1, "end": 2},
            "cycle_usage": {"results": 5, "tiles": 10, "future_counter": 1},
            "date_range": {"begin": "2026-01-01", "total": {"requests": 1}},
            "full_history": [{"total": {"area": {"acres": 0.5}}}],
            "by_token": [
                {
                    "name": "token1",
                    "token_fragment": "fragment",
                    "cycle_usage": {"addresses": 2},
                    "full_history": [],
                }
            ],
        }
    }
    model = UsageResponse.model_validate(payload)
    assert model.usage.cycle_usage.results == 5
    assert model.to_dict() == payload
    assert "fragment" not in repr(model.usage.by_token[0])


def test_detailed_usage():
    payload = {
        "usage": {
            "cycle_usage": [{"country": "US", "service": "api", "parcels": 5}],
            "full_history": [{"total": [], "counts": [{"date": "2026-01-01", "requests": 2}]}],
        }
    }
    assert DetailedUsageResponse.model_validate(payload).to_dict() == payload


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "Feature", "geometry": None, "properties": {"county": "Dallas", "custom": 3}},
        {"type": "FeatureCollection", "features": [{"properties": {"admin2": "Division 22"}}]},
    ],
)
def test_metadata_feature_and_collection(payload):
    assert VerseResponse.model_validate(payload).to_dict() == payload


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"type": "Feature"},
        {"type": "FeatureCollection"},
        {"type": "FeatureCollection", "features": None},
    ],
)
def test_metadata_shape_must_have_content(payload):
    with pytest.raises(ValidationError):
        VerseResponse.model_validate(payload)


def test_client_token_is_masked_except_explicit_export():
    payload = {"token": "sensitive-token", "expires_at": 12345, "custom": None}
    model = ClientTokenResponse.model_validate(payload)
    assert "sensitive-token" not in repr(model)
    assert "sensitive-token" not in model.model_dump_json()
    assert model.to_dict() == payload


def test_report_and_tilejson_roundtrip():
    report = {"message": "Report received", "id": 123, "future": True}
    tiles = {
        "tiles": ["https://tiles.example/{z}/{x}/{y}.mvt"],
        "minzoom": 10,
        "maxzoom": 21,
        "vector_layers": [{"id": "parcels"}],
    }
    assert ReportResponse.model_validate(report).to_dict() == report
    assert TileJSON.model_validate(tiles).to_dict() == tiles


@pytest.mark.parametrize(
    "model,payload",
    [
        (UsageResponse, {"usage": {"cycle_usage": {"results": "2"}}}),
        (DetailedUsageResponse, {"usage": {"cycle_usage": {"parcels": 1}}}),
        (TypeaheadResponse, {}),
        (ReportResponse, {}),
        (ClientTokenResponse, {}),
        (TileJSON, {"tiles": "https://tiles.example"}),
    ],
)
def test_response_envelopes_validate_known_fields(model, payload):
    with pytest.raises(ValidationError):
        model.model_validate(payload)
