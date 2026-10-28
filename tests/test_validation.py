"""Boundary and invalid-response checks that prevent accidental API calls."""

import httpx
import pytest

from regrid import RegridClient, RegridDecodeError, RegridError


@pytest.mark.parametrize(
    "kwargs",
    [
        {"token": ""},
        {"token": "   "},
        {"token": 123},
        {"timeout": True},
        {"timeout": float("inf")},
        {"timeout": -1},
        {"base_url": "http://example.com"},
        {"base_url": "https://example.com?token=x"},
        {"base_url": "https://example.com#fragment"},
        {"tiles_base_url": "https://user:password@example.com"},
        {"default_limit": 0},
        {"max_limit": 1001},
    ],
)
def test_reject_invalid_client_configuration(kwargs):
    with pytest.raises((ValueError, TypeError)):
        RegridClient(**kwargs)


@pytest.mark.parametrize(
    "payload,error",
    [
        ([], RegridDecodeError),
        ({"status": "error", "message": "sensitive upstream message"}, RegridError),
    ],
)
def test_reject_unexpected_response_without_disclosing_body(payload, error):
    with RegridClient(
        "test-placeholder",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)),
    ) as client:
        with pytest.raises(error) as caught:
            client.usage()
    assert "sensitive upstream message" not in str(caught.value)


@pytest.mark.parametrize(
    "method,kwargs",
    [
        ("tilejson", {"format": "jpg"}),
        ("tile", {"z": 10, "x": 0, "y": 0, "format": "jpg"}),
        ("tile", {"z": 10, "x": 0, "y": 0, "retina": "yes"}),
        ("area", {"geojson": "broken"}),
        ("area", {"geojson": "[]"}),
        ("area", {"geojson": {}}),
        ("area", {"geojson": {"type": "Point"}, "method": "DELETE"}),
        ("point", {"lat": 1, "lon": 2, "method": "DELETE"}),
        ("point", {"lat": 1, "lon": 2, "offset_id": -1}),
        ("point", {"lat": 1, "lon": 2, "offset_id": True}),
        ("query", {"fields": {"owner": {"eq": float("inf")}}}),
        ("query", {"fields": {"owner": {"illegal[eq]": "name"}}}),
        ("query", {"fields": {"owner": {}}}),
        ("schema", {"premium_only": "true"}),
        ("usage", {"detailed": "yes"}),
    ],
)
def test_invalid_arguments_never_reach_transport(method, kwargs):
    def unexpected_request(request):
        pytest.fail("Invalid arguments reached the network")

    with RegridClient(
        "test-placeholder", transport=httpx.MockTransport(unexpected_request)
    ) as client:
        with pytest.raises((ValueError, TypeError)):
            getattr(client, method)(**kwargs)


def test_string_geometry_roundtrips_and_null_options_are_omitted():
    def handler(request):
        assert request.url.params["geojson"] == '{"type":"Point","coordinates":[0,0]}'
        assert "radius" not in request.url.params
        assert request.url.params["offset_id"] == "0"
        return httpx.Response(200, json={"count": 1})

    with RegridClient("test-placeholder", transport=httpx.MockTransport(handler)) as client:
        assert client.area(
            '{"type":"Point","coordinates":[0,0]}', radius=None, offset_id=0, return_count=True
        ) == {"count": 1}
