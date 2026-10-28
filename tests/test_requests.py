"""Strict request schemas reject bad values before transport without leaking data."""

import json
import traceback

import httpx
import pytest
from pydantic import ValidationError

from regrid import RegridClient
from regrid.requests import (
    GeometryInput,
    PointRequest,
    QueryRequest,
    StrictRequest,
    TextInput,
    TokenRequest,
    safe_validate,
    validate_options,
)


@pytest.fixture
def client():
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, json={"ok": True})

    with RegridClient("placeholder", transport=httpx.MockTransport(handle)) as sdk:
        yield sdk, calls


def test_request_model_configuration():
    assert StrictRequest.model_config["strict"] is True
    assert StrictRequest.model_config["extra"] == "forbid"
    assert StrictRequest.model_config["hide_input_in_errors"] is True


@pytest.mark.parametrize("value", [True, "2", 2.0, -1, 1001])
def test_limits_are_strict_and_bounded(value):
    with pytest.raises(ValueError):
        validate_options({"limit": value}, {"limit"})


@pytest.mark.parametrize("value", [1, "true", [], {}])
def test_flags_do_not_coerce(value):
    with pytest.raises(ValueError):
        validate_options({"return_geometry": value}, {"return_geometry"})


def test_model_rejects_extra_keys_even_if_they_are_known_on_other_endpoints():
    with pytest.raises(ValueError):
        validate_options({"return_count": True}, {"limit"})
    assert validate_options(
        {"limit": None, "return_parcels": False}, {"limit", "return_parcels"}
    ) == {"return_parcels": False}


@pytest.mark.parametrize(
    "model,data",
    [
        (TextInput, {"value": 123456789}),
        (TextInput, {"value": " "}),
        (TokenRequest, {"exp": True}),
        (TokenRequest, {"exp": "3600"}),
        (TokenRequest, {"exp": float("inf")}),
        (PointRequest, {"lat": True, "lon": 1}),
        (PointRequest, {"lat": "1", "lon": 1}),
        (PointRequest, {"lat": float("nan"), "lon": 1}),
        (PointRequest, {"lat": 0, "lon": 0, "method": "POST"}),
        (GeometryInput, {"geojson": {"type": 1}}),
        (GeometryInput, {"geojson": {"type": "Point", "coordinates": [float("inf"), 0]}}),
        (GeometryInput, {"geojson": {"type": "Point", "custom": object()}}),
        (QueryRequest, {"fields": {"name": {"eq": object()}}}),
    ],
)
def test_request_models_reject_invalid_inputs(model, data):
    with pytest.raises(ValueError, match="Invalid Regrid request parameters"):
        safe_validate(model, data)


def test_direct_model_error_display_hides_values():
    with pytest.raises(ValidationError) as caught:
        TextInput.model_validate({"value": {"secret-value": "private"}})
    assert "secret-value" not in str(caught.value)
    assert "private" not in str(caught.value)


@pytest.mark.parametrize(
    "method,kwargs",
    [
        ("address", {"query": "address", "sensitive-unknown-key": "sensitive-value"}),
        ("point", {"lat": "sensitive-value", "lon": 0}),
        ("area", {"geojson": {"type": "Point", "coordinates": object()}}),
        ("query", {"fields": {"sensitive-unknown-key": {"eq": "sensitive-value"}}}),
        ("apn", {"parcelnumb": {"sensitive-value": "private"}}),
    ],
)
def test_sdk_errors_are_sanitized_before_transport(client, method, kwargs):
    sdk, calls = client
    with pytest.raises(ValueError) as caught:
        getattr(sdk, method)(**kwargs)
    rendered = "".join(traceback.format_exception(caught.value))
    assert "sensitive-value" not in str(caught.value)
    assert "sensitive-unknown-key" not in str(caught.value)
    # Traceback source lines may mention fixture variable names, never the input value.
    assert "input_value=" not in rendered
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert not calls


def test_endpoint_validation_preserves_apn_and_integer_duration(client):
    sdk, calls = client
    sdk.apn("0000123-A", limit=2)
    sdk.client_token_typeahead(exp=3600)
    assert calls[0].url.params["parcelnumb"] == "0000123-A"
    assert calls[1].url.params["exp"] == "3600"


def test_feature_point_and_coordinates_are_validated_without_losing_geometry(client):
    sdk, calls = client
    geometry = {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [1, 2]},
        "properties": {"custom_id": "my-id"},
    }
    sdk.point(0, 0, geojson=geometry, method="POST", return_custom_id=True)
    assert json.loads(calls[0].content) == {"geojson": geometry}
    assert calls[0].url.params["lat"] == "0"
    assert calls[0].url.params["lon"] == "0"


def test_known_path_and_dates_require_strings(client):
    sdk, calls = client
    with pytest.raises(ValueError):
        sdk.address("Main", path=42)
    with pytest.raises(ValueError):
        sdk.usage(begin_date=20261027)
    assert not calls
