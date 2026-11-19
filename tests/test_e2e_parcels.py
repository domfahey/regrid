"""End-to-end US parcel commands over real verified TLS against the local fake server."""

import json

import pytest
from e2e_support import parcel_response, regrid_server, run_cli  # noqa: F401

from regrid import RegridClient, TypedRegridClient

pytestmark = pytest.mark.e2e
TOKEN = "secret-token"
UUID = "00000000-0000-4000-8000-000000000001"
POINT = {"type": "Point", "coordinates": [-75.03, 39.9]}
POLYGON = {
    "type": "Polygon",
    "coordinates": [[[-75.1, 39.9], [-75.0, 39.9], [-75.0, 40.0], [-75.1, 39.9]]],
}


def ok(result, count):
    assert result.returncode == 0, result.stderr
    assert TOKEN.encode() not in result.stdout + result.stderr
    assert result.stderr.decode().splitlines()[-1] == f"regrid: requests made: {count}"
    return json.loads(result.stdout)


def feature_ids(data):
    return [f["id"] for f in data["parcels"]["features"]]


@pytest.fixture
def server(regrid_server):  # noqa: F811
    for path in (
        "/parcels/point",
        "/parcels/area",
        "/parcels/apn",
        "/parcels/owner",
        "/parcels/query",
        "/parcels/path",
        f"/parcels/{UUID}",
        "/parcels/typeahead",
    ):
        regrid_server.route("/api/v2" + path, json=parcel_response())
    return regrid_server


def last(server):
    request = server.requests[-1]
    assert request.params["token"] == [TOKEN]
    assert TOKEN not in request.headers.get("authorization", "")
    return request


def test_address_options_file_and_path(server, tmp_path):
    options = tmp_path / "options.json"
    options.write_text('{"limit": 3, "path": "/us/nj/camden"}')
    data = ok(run_cli(server, "address", "123 Main St", "--options", f"@{options}"), 1)
    assert feature_ids(data) == [1]
    request = last(server)
    assert (request.method, request.path) == ("GET", "/api/v2/parcels/address")
    assert request.params["query"] == ["123 Main St"]
    assert request.params["limit"] == ["3"]
    assert request.params["path"] == ["/us/nj/camden"]


def test_apn_preserves_leading_zeros(server):
    ok(run_cli(server, "apn", "0012-AB"), 1)
    request = last(server)
    assert (request.method, request.path) == ("GET", "/api/v2/parcels/apn")
    assert request.params["parcelnumb"] == ["0012-AB"]


def test_owner(server):
    ok(run_cli(server, "owner", "Smith John"), 1)
    request = last(server)
    assert (request.method, request.path) == ("GET", "/api/v2/parcels/owner")
    assert request.params["owner"] == ["Smith John"]


def test_point_lat_lon_and_geojson_get(server):
    ok(run_cli(server, "point", "--lat", "39.9", "--lon", "-75.03"), 1)
    request = last(server)
    assert (request.method, request.path) == ("GET", "/api/v2/parcels/point")
    assert (request.params["lat"], request.params["lon"]) == (["39.9"], ["-75.03"])
    ok(run_cli(server, "point", "--geojson", json.dumps(POINT)), 1)
    request = server.requests[-1]
    assert request.method == "GET"
    assert json.loads(request.params["geojson"][0]) == POINT
    assert "lat" not in request.params


def test_point_post_body_and_query_options(server):
    result = run_cli(
        server,
        "point",
        "--method",
        "POST",
        "--geojson",
        json.dumps(POINT),
        "--options",
        '{"limit": 4, "radius": 25}',
    )
    ok(result, 1)
    request = last(server)
    assert (request.method, request.path) == ("POST", "/api/v2/parcels/point")
    assert request.json() == {"geojson": POINT}
    assert request.params["limit"] == ["4"]
    assert request.params["radius"] == ["25"]


def test_area_get_geojson_from_file_and_post(server, tmp_path):
    geo = tmp_path / "area.json"
    geo.write_text(json.dumps(POLYGON))
    ok(run_cli(server, "area", "--geojson", f"@{geo}", "--options", '{"limit": 2}'), 1)
    request = last(server)
    assert (request.method, request.path) == ("GET", "/api/v2/parcels/area")
    assert json.loads(request.params["geojson"][0]) == POLYGON
    assert request.params["limit"] == ["2"]
    ok(run_cli(server, "area", "--geojson", json.dumps(POLYGON), "--method", "POST"), 1)
    request = last(server)
    assert (request.method, request.path) == ("POST", "/api/v2/parcels/area")
    assert request.json() == {"geojson": POLYGON}
    assert "geojson" not in request.params


def test_query_fields_and_validated_fields(server):
    fields = '{"geoid":{"eq":"34007"}}'
    ok(run_cli(server, "query", "--fields", fields, "--options", '{"limit": 2}'), 1)
    request = last(server)
    assert (request.method, request.path) == ("GET", "/api/v2/parcels/query")
    assert request.params["fields[geoid][eq]"] == ["34007"]
    assert request.params["limit"] == ["2"]
    ok(run_cli(server, "query", "--fields", fields, "--validate-fields"), 1)
    assert server.requests[-1].params["fields[geoid][eq]"] == ["34007"]


def test_query_rejected_field_makes_no_request(server):
    bad = '{"not_a_real_field_zz":{"eq":"1"}}'
    result = run_cli(server, "query", "--fields", bad, "--validate-fields")
    assert result.returncode != 0
    assert result.stderr.decode().splitlines()[-1] == "regrid: requests made: 0"
    assert TOKEN.encode() not in result.stdout + result.stderr
    assert server.requests == []
    ok(run_cli(server, "query", "--fields", bad, "--validate-fields", "--allow-unknown-fields"), 1)
    assert last(server).params["fields[not_a_real_field_zz][eq]"] == ["1"]


def test_parcel_by_uuid_and_path(server):
    ok(run_cli(server, "parcel", UUID), 1)
    request = last(server)
    assert (request.method, request.path) == ("GET", f"/api/v2/parcels/{UUID}")
    ok(run_cli(server, "parcel-path", "/us/nj/camden/haddonfield/123"), 1)
    request = last(server)
    assert request.path == "/api/v2/parcels/path"
    assert request.params["path"] == ["/us/nj/camden/haddonfield/123"]


def test_typeahead(server):
    ok(run_cli(server, "typeahead", "123 Ma"), 1)
    request = last(server)
    assert (request.method, request.path) == ("GET", "/api/v2/parcels/typeahead")
    assert request.params["query"] == ["123 Ma"]


def test_country_default_us_and_ca_paths(server):
    server.routes["/api/v2/ca/parcels/address"] = server.routes["/api/v2/parcels/address"]
    ok(run_cli(server, "address", "1 Main"), 1)
    assert server.requests[-1].path == "/api/v2/parcels/address"
    ok(run_cli(server, "address", "1 Main", "--country", "ca"), 1)
    assert server.requests[-1].path == "/api/v2/ca/parcels/address"


def _serve_cursor_pages(server, path, total=5):
    def pages(request):
        limit = int(request.params["limit"][0])
        start = int(request.params.get("offset_id", ["0"])[0]) + 1  # exclusive cursor
        count = max(0, min(limit, total - start + 1))
        return parcel_response(count, start)

    server.route(path, json=pages)


def _assert_three_pages(server, result):
    data = ok(result, 3)
    assert "regrid: up to 3 requests for 5 records" in result.stderr.decode()
    assert (data["pages"], data["complete"]) == (3, True)
    assert feature_ids(data) == [1, 2, 3, 4, 5]
    assert [r.params["limit"] for r in server.requests] == [["2"], ["2"], ["1"]]
    assert [r.params.get("offset_id") for r in server.requests] == [None, ["2"], ["4"]]


def test_max_records_pages_over_https(server):
    _serve_cursor_pages(server, "/api/v2/parcels/point")
    result = run_cli(
        server,
        "point",
        "--lat",
        "39.9",
        "--lon",
        "-75.03",
        "--max-records",
        "5",
        "--options",
        '{"limit": 2}',
    )
    _assert_three_pages(server, result)


def test_max_records_pages_area_get(server):
    _serve_cursor_pages(server, "/api/v2/parcels/area")
    result = run_cli(
        server,
        "area",
        "--geojson",
        json.dumps(POLYGON),
        "--max-records",
        "5",
        "--options",
        '{"limit": 2}',
    )
    _assert_three_pages(server, result)
    assert {r.method for r in server.requests} == {"GET"}
    assert all(json.loads(r.params["geojson"][0]) == POLYGON for r in server.requests)


def test_max_records_pages_query(server):
    _serve_cursor_pages(server, "/api/v2/parcels/query")
    result = run_cli(
        server,
        "query",
        "--fields",
        '{"geoid":{"eq":"34007"}}',
        "--max-records",
        "5",
        "--options",
        '{"limit": 2}',
    )
    _assert_three_pages(server, result)
    assert all(r.params["fields[geoid][eq]"] == ["34007"] for r in server.requests)


def test_option_rejected_before_any_request(server):
    result = run_cli(server, "parcel", UUID, "--options", '{"limit": 5}')
    assert result.returncode != 0
    assert result.stderr.decode().splitlines()[-1] == "regrid: requests made: 0"
    assert TOKEN.encode() not in result.stdout + result.stderr
    assert server.requests == []


def test_typed_client_validates_live_shapes(server, monkeypatch):
    monkeypatch.setenv("SSL_CERT_FILE", str(server.cert))
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    with TypedRegridClient(TOKEN, base_url=server.api, tiles_base_url=server.base) as client:
        response = client.address("123 Main", limit=1)
        assert isinstance(client.raw, RegridClient)
    feature = response.parcels.features[0]
    assert feature.id == 1
    assert feature.properties.path == "/us/nj/camden/haddonfield/123"
    fields = feature.properties.fields
    assert fields["owner"] == "Owner 1"
    assert fields["ll_updated_at"] == "2025-03-14 09:26:53 -0400"
    typed = feature.properties.typed_fields
    assert typed is not None
    assert typed.ll_updated_at == "2025-03-14 09:26:53 -0400"
    assert typed.owner == "Owner 1"
    assert server.requests[-1].params["limit"] == ["1"]
