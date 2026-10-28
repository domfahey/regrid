"""Exercise endpoint contracts through the real client and a network-free transport."""

import json

import httpx
import pytest

from regrid import RegridClient

UUID = "12345678-1234-5678-1234-567812345678"
POINT = {"type": "Point", "coordinates": [-105.2, 40.5]}


@pytest.fixture
def recording_client():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    with RegridClient(token="test-token", transport=httpx.MockTransport(handler)) as client:
        yield client, requests


@pytest.mark.parametrize(
    "method,args,options,path,params",
    [
        (
            "address",
            ("Main St",),
            {"country": "ca", "path": "/ca/mb"},
            "/ca/parcels/address",
            {"query": "Main St", "path": "/ca/mb", "limit": "1"},
        ),
        (
            "apn",
            ("0001-A",),
            {},
            "/parcels/apn",
            {"parcelnumb": "0001-A", "limit": "5", "return_parcels": "true"},
        ),
        (
            "apn",
            ("0001-A",),
            {"country": "ca"},
            "/ca/parcels/apn",
            {"parcelnumb": "0001-A", "limit": "5"},
        ),
        (
            "owner",
            ("Smith, John",),
            {"path": "/us/tx/dallas"},
            "/parcels/owner",
            {
                "owner": "Smith, John",
                "path": "/us/tx/dallas",
                "limit": "5",
                "return_parcels": "true",
            },
        ),
        ("parcel", (UUID,), {}, f"/parcels/{UUID}", {"return_parcels": "true"}),
        ("parcel", (UUID,), {"country": "ca"}, f"/ca/parcels/{UUID}", {}),
        (
            "parcel_path",
            ("/us/tx/dallas/example",),
            {},
            "/parcels/path",
            {"path": "/us/tx/dallas/example", "return_parcels": "true"},
        ),
        (
            "parcel_path",
            ("/ca/mb/example",),
            {"country": "ca"},
            "/ca/parcels/path",
            {"path": "/ca/mb/example"},
        ),
        ("typeahead", ("Main",), {}, "/parcels/typeahead", {"query": "Main"}),
        (
            "verse",
            (),
            {"country": "ca", "return_geometry": False},
            "/ca/verse",
            {"return_geometry": "false"},
        ),
        ("verse", (), {}, "/verse", {}),
        ("usage", (), {"country": "ca"}, "/ca/usage", {}),
        ("usage", (), {"detailed": True}, "/usage/detailed", {}),
    ],
)
def test_endpoint_routes(recording_client, method, args, options, path, params):
    client, requests = recording_client
    assert getattr(client, method)(*args, **options) == {"ok": True}
    assert len(requests) == 1
    request = requests[0]
    assert request.method == "GET"
    assert request.url.host == "app.regrid.com"
    assert request.url.path == "/api/v2" + path
    expected = {**params, "token": "test-token"}
    assert dict(request.url.params) == expected
    assert len(request.url.params.multi_items()) == len(expected)
    assert request.content == b""


@pytest.mark.parametrize("endpoint", ["point", "area"])
@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize("country", ["us", "ca"])
def test_geometry_serialization(recording_client, endpoint, method, country):
    client, requests = recording_client
    getattr(client, endpoint)(geojson=POINT, method=method, country=country, limit=2)
    request = requests[0]
    prefix = "/ca" if country == "ca" else ""
    assert request.method == method
    assert request.url.path == f"/api/v2{prefix}/parcels/{endpoint}"
    assert request.url.params["limit"] == "2"
    if method == "POST":
        assert json.loads(request.content) == {"geojson": POINT}
        assert "geojson" not in request.url.params
    else:
        assert json.loads(request.url.params["geojson"]) == POINT
        assert request.content == b""


def test_query_encodes_operators_and_json_values(recording_client):
    client, requests = recording_client
    client.query(
        {"parcelnumb": {"in": ["0001-A", "0002"]}, "saleprice": {"gte": 100, "lt": 200}},
        country="ca",
        geojson=POINT,
    )
    params = requests[0].url.params
    assert requests[0].url.path == "/api/v2/ca/parcels/query"
    assert json.loads(params["fields[parcelnumb][in]"]) == ["0001-A", "0002"]
    assert params["fields[saleprice][gte]"] == "100"
    assert params["fields[saleprice][lt]"] == "200"
    assert json.loads(params["geojson"]) == POINT


@pytest.mark.parametrize(
    "name", ["parcel", "building", "address", "enhanced_ownership", "zoning", "ca"]
)
def test_schema_variants_are_public(recording_client, name):
    client, requests = recording_client
    client.schema(name)
    assert requests[0].url.path == "/api/v2/schemas/" + name
    assert "token" not in requests[0].url.params


def test_parcel_schema_premium_filter(recording_client):
    client, requests = recording_client
    client.schema(premium_only=False)
    assert requests[0].url.params["premium_only"] == "false"


def test_usage_preserves_filters(recording_client):
    client, requests = recording_client
    assert client.usage(
        begin_date="2026-10-01", end_date="2026-10-27", return_by_this_token=True
    ) == {"ok": True}
    params = requests[0].url.params
    assert params["begin_date"] == "2026-10-01"
    assert params["end_date"] == "2026-10-27"
    assert params["return_by_this_token"] == "true"


def test_temporary_client_token_duration(recording_client):
    client, requests = recording_client
    client.client_token_typeahead(exp=3600)
    assert requests[0].url.path == "/api/v2/client_token/typeahead"
    assert requests[0].url.params["exp"] == "3600"


def test_report_is_post_with_encoded_details(recording_client):
    client, requests = recording_client
    client.report("Incorrect address", ll_uuid=UUID, details={"address": "123 Main St"})
    request = requests[0]
    assert request.method == "POST"
    assert request.url.path == "/api/v2/report"
    assert request.url.params["comment"] == "Incorrect address"
    assert request.url.params["ll_uuid"] == UUID
    assert json.loads(request.url.params["details"]) == {"address": "123 Main St"}


@pytest.mark.parametrize(
    ("method", "args", "options"),
    [
        ("address", ("Main",), {"return_count": True}),
        ("address", ("Main",), {"token": "override"}),
        ("address", ("Main",), {"country": "ca", "return_zoning": True}),
        ("address", ("Main",), {"country": "uk"}),
        ("address", (" ",), {}),
        ("apn", (123,), {}),
        ("owner", ("abc",), {}),
        ("owner", ("Smith",), {"country": "ca"}),
        ("typeahead", ("Main",), {"country": "ca"}),
        ("parcel", ("../usage",), {}),
        ("point", (40, -105), {"method": "POST"}),
        ("point", (91, -105), {}),
        ("point", (40, -181), {}),
        ("point", (), {"geojson": {"type": "Polygon", "coordinates": []}}),
        ("point", (), {"geojson": POINT, "method": "POST", "offset_id": 1}),
        ("area", (POINT,), {"radius": 32001}),
        ("area", (POINT,), {"return_count": "yes"}),
        ("query", ({},), {}),
        ("query", ({f"field{i}": {"eq": 1} for i in range(5)},), {}),
        ("query", ({"bad][field": {"eq": 1}},), {}),
        ("query", ({"field": {"eq]": 1}},), {}),
        ("schema", ("building",), {"premium_only": True}),
        ("schema", ("missing",), {}),
        ("schema", (), {"premium_only": 1}),
        ("usage", (), {"country": "ca", "detailed": True}),
        ("usage", (), {"unexpected": True}),
        ("client_token_typeahead", (), {"exp": 0}),
    ],
)
def test_invalid_requests_fail_before_transport(recording_client, method, args, options):
    client, requests = recording_client
    with pytest.raises((ValueError, TypeError)):
        getattr(client, method)(*args, **options)
    assert not requests
