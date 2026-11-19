"""Exercise endpoint contracts through the real client and a network-free transport."""

import json

import httpx
import pytest

from regrid import RegridClient
from regrid.endpoints import QueryPagingError

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


def test_json_error_does_not_retain_input_context(recording_client):
    client, _ = recording_client
    with pytest.raises(ValueError, match="Invalid Regrid JSON request") as excinfo:
        client.report(details={"x": float("nan")})
    assert excinfo.value.__context__ is None
    assert excinfo.value.__cause__ is None


def test_geometry_error_does_not_retain_input_context(recording_client):
    client, _ = recording_client
    with pytest.raises(ValueError, match="Invalid Regrid GeoJSON request") as excinfo:
        client.query({"geoid": {"eq": "1"}}, geojson="{not json SECRET")
    assert excinfo.value.__context__ is None
    assert excinfo.value.__cause__ is None


def test_query_validate_fields_accepts_uppercase_us(recording_client):
    client, requests = recording_client
    client.query({"geoid": {"eq": "48113"}}, country="US", validate_fields=True)
    assert len(requests) == 1


def test_query_validate_fields_still_rejects_uppercase_ca(recording_client):
    client, requests = recording_client
    with pytest.raises(ValueError, match="US queries only"):
        client.query({"postcode": {"eq": "R0B 0J0"}}, country="CA", validate_fields=True)
    assert requests == []


@pytest.mark.parametrize(
    "lat,lon",
    [(32.8, None), (None, -105.2)],
    ids=["lat-only", "lon-only"],
)
def test_point_rejects_unpaired_coordinates_with_geojson(recording_client, lat, lon):
    client, requests = recording_client
    with pytest.raises(ValueError, match="Invalid Regrid request parameters"):
        client.point(lat=lat, lon=lon, geojson={"type": "Point", "coordinates": [0, 0]})
    assert requests == []


def test_point_accepts_paired_coordinates_with_geojson(recording_client):
    client, requests = recording_client
    client.point(lat=40.5, lon=-105.2, geojson=POINT)
    assert len(requests) == 1
    assert requests[0].url.params["lat"] == "40.5"
    assert requests[0].url.params["lon"] == "-105.2"


@pytest.mark.parametrize(
    "method,args",
    [
        ("address", ("1 Main St",)),
        ("apn", ("0001-A",)),
        ("owner", ("Smith",)),
        ("query", ({"owner": {"eq": "Smith"}},)),
    ],
)
@pytest.mark.parametrize("path", ["   ", "\t", ""])
def test_blank_path_option_is_rejected_before_transport(recording_client, method, args, path):
    client, requests = recording_client
    with pytest.raises(ValueError, match="Invalid Regrid request parameters"):
        getattr(client, method)(*args, path=path)
    assert requests == []


@pytest.mark.parametrize(
    "method,args",
    [
        ("address", ("1 Main St",)),
        ("apn", ("0001-A",)),
        ("owner", ("Smith",)),
        ("query", ({"owner": {"eq": "Smith"}},)),
    ],
)
def test_normal_path_option_is_sent_unchanged(recording_client, method, args):
    client, requests = recording_client
    getattr(client, method)(*args, path="/us/tx/dallas")
    assert len(requests) == 1
    assert requests[0].url.params["path"] == "/us/tx/dallas"


def test_validate_query_sends_nothing_and_checks_like_query(recording_client):
    client, requests = recording_client
    client.validate_query({"geoid": {"eq": "48113"}}, validate_fields=True, limit=5)
    with pytest.raises(ValueError, match="Field is not queryable"):
        client.validate_query({"nope_field": {"eq": "x"}}, validate_fields=True)
    with pytest.raises(ValueError):
        client.validate_query({"geoid": {"eq": "1"}}, bogus_option=1)
    assert requests == []


def test_validate_query_paging_flags_only_paging_errors(recording_client):
    client, requests = recording_client
    order = {"yearbuilt": {"order": "ASC"}}
    client.validate_query(order, validate_fields=True)  # fine unpaged
    with pytest.raises(QueryPagingError):
        client.validate_query(order, paging=True, validate_fields=True)
    with pytest.raises(ValueError, match="Field is not queryable") as excinfo:
        client.validate_query({"nope_field": {"eq": "x"}}, paging=True, validate_fields=True)
    assert not isinstance(excinfo.value, QueryPagingError)
    assert requests == []


def test_query_paging_error_is_exported():
    import regrid

    assert regrid.QueryPagingError is QueryPagingError
    assert "QueryPagingError" in regrid.__all__
    assert issubclass(regrid.QueryPagingError, ValueError)


def test_validate_query_paging_error_has_no_context(recording_client):
    client, _ = recording_client
    with pytest.raises(QueryPagingError) as excinfo:
        client.validate_query({"yearbuilt": {"order": "ASC"}}, paging=True, validate_fields=True)
    assert excinfo.value.__context__ is None and excinfo.value.__cause__ is None


def test_deeply_nested_json_is_invalid_input_without_context(recording_client):
    client, requests = recording_client
    deep_list = "[" * 100000
    deep_map: dict = {}
    node = deep_map
    for _ in range(100000):
        node["a"] = {}
        node = node["a"]
    deep_geometry = {"type": "Point", "coordinates": deep_list, "x": deep_map}
    calls = [
        lambda: client.area(geojson=deep_list),
        lambda: client.area(geojson=deep_geometry),
        lambda: client.query({"yearbuilt": {"eq": deep_map}}),
    ]
    for call in calls:
        with pytest.raises(ValueError) as info:
            call()
        assert info.value.__context__ is None
    assert requests == []


def test_validate_query_checks_limit_and_paging_flag(recording_client):
    _, requests = recording_client
    with RegridClient(token="t", max_limit=10, transport=httpx.MockTransport(lambda r: None)) as c:
        with pytest.raises(ValueError, match="exceeds configured maximum"):
            c.validate_query({"geoid": {"eq": "1"}}, limit=50)
        c.validate_query({"geoid": {"eq": "1"}}, limit=10)
        c.validate_query({"geoid": {"eq": "1"}}, limit=None)
        for bad in ("false", 0, "x", 1):
            with pytest.raises(ValueError, match="paging"):
                c.validate_query({"geoid": {"eq": "1"}}, paging=bad)
    assert requests == []
