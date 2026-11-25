import json
import logging
from urllib.parse import urlparse

import httpx
import pytest

from regrid import RegridClient, live_full

TOKEN = "private-token"
UUID = "123e4567-e89b-42d3-a456-426614174000"
PATH = "/us/nj/private-county/private-city/private-parcel"
COUNTY = "/us/nj/private-county"
LAT, LON = "39.123456", "-75.654321"
PRIVATE = (
    TOKEN,
    "private-address",
    UUID,
    "private-parcel",
    "private-city",
    "private-county",
    "private-apn",
    "private-owner",
    "123456",
    "654321",
    "34007",
)

SUBJECT = {
    "id": 100,
    "type": "Feature",
    "geometry": {"type": "Polygon", "coordinates": [[[-75.65, 39.12]]]},
    "properties": {
        "ll_uuid": UUID,
        "path": PATH,
        "fields": {
            "parcelnumb": "private-apn",
            "owner": "private-owner",
            "lat": LAT,
            "lon": LON,
            "geoid": "34007",
        },
    },
}


DETAILED_USAGE = {
    "usage": {
        "cycle_dates": {"begin": 1, "end": 2},
        "cycle_usage": [
            {"country": "us", "service": "parcels", "requests": 3, "parcels": 7, "area": 12}
        ],
        "date_range": {"begin_ts": 1, "begin": "a", "end": "b", "total": []},
    }
}


def collection(*ids, geometry=True):
    features = []
    for feature_id in ids:
        feature = {"id": feature_id, "type": "Feature", "properties": {"ll_uuid": UUID}}
        if geometry:
            feature["geometry"] = {"type": "Point", "coordinates": [0, 0]}
        features.append(feature)
    return {"parcels": {"type": "FeatureCollection", "features": features}}


def usage(results):
    return {"usage": {"cycle_usage": {"results": results}, "cycle_dates": {"begin": 1, "end": 2}}}


class Server:
    def __init__(self, overrides=None):
        self.requests = []
        self.overrides = overrides or {}
        self.usage_calls = 0

    def __call__(self, request):
        self.requests.append(request)
        route = (request.method, request.url.path.removeprefix("/api/v2"))
        if route in self.overrides:
            override = self.overrides[route]
            return override(request) if callable(override) else override
        return self.respond(request, route)

    def respond(self, request, route):
        params = request.url.params
        method, path = route
        if request.url.host == "tiles.regrid.com":
            if path == "/api/v1/parcels":
                if params.get("format") == "mvt":
                    return httpx.Response(200, json={"tiles": ["https://tiles.regrid.com/{z}.mvt"]})
                template = "https://tiles.regrid.com/api/v1/parcels/{z}/{x}/{y}.json"
                return httpx.Response(200, json={"tiles": ["x"], "grid": template})
            if path.endswith(".mvt"):
                return httpx.Response(200, content=b"tile-bytes")
            return httpx.Response(200, json={"grid": [" "], "keys": [""], "data": {}})
        if params.get("token") == live_full.BAD_TOKEN:
            return httpx.Response(401, text="bad")
        if path.startswith("/schemas/"):
            if path.endswith("/parcel"):
                return httpx.Response(200, json={"schema": {"parcelnumb": {"type": "text"}}})
            return httpx.Response(200, json={"schema": {"a": {"type": "text"}, "b": {}}})
        if path == "/usage":
            self.usage_calls += 1
            return httpx.Response(200, json=usage(10 * self.usage_calls))
        if path == "/usage/detailed":
            return httpx.Response(200, json=DETAILED_USAGE)
        if path == "/verse":
            # Live shape (verified 2026-11-19): {"verse": FeatureCollection}.
            features = [
                {"type": "Feature", "properties": {"path": "/us/pa/elsewhere"}},
                {"type": "Feature", "properties": {"path": COUNTY + "/"}},
            ]
            body = {"verse": {"type": "FeatureCollection", "features": features}}
            return httpx.Response(200, json=body)
        if path == "/parcels/address":
            return httpx.Response(
                200, json={"parcels": {"type": "FeatureCollection", "features": [SUBJECT]}}
            )
        if path == "/parcels/point" and params.get("radius") == "50":
            if params.get("offset_id") == "0":
                return httpx.Response(200, json=collection(5, 7))
            return httpx.Response(200, json=collection(9, 11))
        if path == "/parcels/typeahead":
            return httpx.Response(
                200, json={"parcel_centroids": {"type": "FeatureCollection", "features": [{}, {}]}}
            )
        return httpx.Response(200, json=collection(100))


def run_full(server, **kwargs):
    transport = httpx.MockTransport(server)
    bad = RegridClient(live_full.BAD_TOKEN, transport=transport, max_limit=2, default_limit=1)
    with RegridClient(TOKEN, transport=transport, max_limit=2, default_limit=1) as client:
        status = live_full.run(client, "private-address", bad_client=bad, **kwargs)
    bad.close()
    return status


def lines(capsys):
    output = capsys.readouterr()
    assert output.err == ""
    for secret in PRIVATE:
        assert secret not in output.out
    return output.out.splitlines()


def statuses(output):
    return {
        line.split(":")[0]: line.split(" ")[0] for line in output if not line.startswith("NOTE")
    }


def test_missing_configuration_makes_no_requests(monkeypatch, capsys):
    monkeypatch.delenv("REGRID_TOKEN", raising=False)
    monkeypatch.setattr(live_full, "RegridClient", lambda *a, **kw: pytest.fail("client"))
    assert live_full.main() == 2
    assert "NOT RUN" in capsys.readouterr().out


def test_happy_path(capsys):
    server = Server()
    assert run_full(server) == 0
    output = lines(capsys)
    assert [line for line in output if line.startswith(("FAIL", "SKIP"))] == [
        "SKIP typeahead: needs an Enterprise token"
    ]
    calls = {(r.method, r.url.path.removeprefix("/api/v2")): r for r in server.requests}
    assert len(server.requests) == 26
    assert "NOTE requests made: 26" in output
    flags = {
        "return_stacked": "false",
        "return_zoning": "false",
        "return_matched_buildings": "false",
        "return_matched_addresses": "false",
        "return_enhanced_ownership": "false",
    }
    searches = [
        r for r in server.requests if "/parcels/" in r.url.path and r.url.host != "tiles.regrid.com"
    ]
    assert len(searches) == 12
    for request in searches:
        params = request.url.params
        if request.url.path.endswith(f"/{UUID}") or request.url.path.endswith("/path"):
            assert "limit" not in params
        else:
            assert params["limit"] in ("1", "2")
        assert {key: params[key] for key in flags} == flags
    for request in server.requests:
        if request.method == "POST":
            assert request.url.path.removeprefix("/api/v2") in ("/parcels/point", "/parcels/area")
        assert "/report" not in request.url.path
        assert "/client_token" not in request.url.path
    assert calls[("GET", "/parcels/apn")].url.params["path"] == COUNTY
    assert calls[("GET", "/parcels/owner")].url.params["path"] == COUNTY
    assert calls[("GET", "/parcels/query")].url.params["path"] == COUNTY
    assert calls[("GET", "/parcels/query")].url.params["fields[geoid][eq]"] == "34007"
    assert calls[("GET", "/parcels/area")].url.params["return_geometry"] == "true"
    body = json.loads(calls[("POST", "/parcels/area")].content)
    assert body["geojson"]["type"] == "Polygon"
    assert json.loads(calls[("POST", "/parcels/point")].content)["geojson"]["type"] == "Point"
    assert calls[("POST", "/parcels/point")].url.params["limit"] == "1"
    point_gets = [
        r for r in server.requests if r.method == "GET" and r.url.path.endswith("/parcels/point")
    ]
    assert point_gets[0].url.params["radius"] == "1"
    assert point_gets[0].url.params["return_geometry"] == "false"
    assert point_gets[1].url.params["limit"] == "2" and point_gets[1].url.params["offset_id"] == "0"
    assert point_gets[2].url.params["offset_id"] == "7"
    detailed = calls[("GET", "/usage/detailed")].url.params
    assert detailed["begin_date"].endswith("-01")
    assert {
        r.url.params.get("token") for r in server.requests if r.url.host != "tiles.regrid.com"
    } == {TOKEN, live_full.BAD_TOKEN, None}
    assert "NOTE paging: ordered: true" in output
    assert "NOTE apn: match: true" in output
    assert "PASS verse: 2 entries" in output
    assert "NOTE verse: subject county present: true" in output
    assert "PASS bad token: rejected with HTTP 401" in output
    assert "SKIP typeahead: needs an Enterprise token" in output
    assert "PASS final usage: observed record delta 10" in output


def test_expected_order_is_exact():
    # The happy path makes exactly this ordered sequence (tile and grid hosts included).
    server = Server()
    run_full(server)
    sequence = [
        (r.method, urlparse(str(r.url)).path.removeprefix("/api/v2")) for r in server.requests
    ]
    assert sequence[:7] == [
        ("GET", "/schemas/parcel"),
        ("GET", "/schemas/building"),
        ("GET", "/schemas/address"),
        ("GET", "/schemas/enhanced_ownership"),
        ("GET", "/schemas/zoning"),
        ("GET", "/usage"),
        ("GET", "/parcels/address"),
    ]
    assert sequence[7:19] == [
        ("GET", f"/parcels/{UUID}"),
        ("GET", "/parcels/path"),
        ("GET", "/parcels/apn"),
        ("GET", "/parcels/owner"),
        ("GET", "/parcels/point"),
        ("POST", "/parcels/point"),
        ("GET", "/parcels/area"),
        ("POST", "/parcels/area"),
        ("GET", "/parcels/query"),
        ("GET", "/parcels/point"),
        ("GET", "/parcels/point"),
        ("GET", "/verse"),
    ]
    assert sequence[19:21] == [("GET", "/usage/detailed"), ("GET", "/api/v1/parcels")]
    assert sequence[21].__getitem__(1).endswith(".mvt")
    assert sequence[22] == ("GET", "/api/v1/parcels")
    assert sequence[23][1].endswith(".json")
    assert sequence[24:] == [("GET", "/usage"), ("GET", "/usage")]


def test_empty_address_skips_dependent_steps(capsys):
    server = Server({("GET", "/parcels/address"): httpx.Response(200, json=collection())})
    assert run_full(server) == 1
    output = lines(capsys)
    results = statuses(output)
    assert results["FAIL address"] == "FAIL"
    for name in (
        "parcel",
        "parcel-path",
        "apn",
        "owner",
        "point GET",
        "point POST",
        "area GET",
        "area POST",
        "query",
        "paging",
        "tile",
        "grid",
    ):
        assert results[f"SKIP {name}"] == "SKIP"
    for name in (
        "PASS schema parcel",
        "PASS verse",
        "PASS tilejson",
        "PASS bad token",
        "PASS usage baseline",
        "PASS final usage",
    ):
        assert name in results
    assert all("subject county present" not in line for line in output)
    assert not [r for r in server.requests if r.url.path.endswith("/parcels/point")]


def test_middle_failure_is_isolated(capsys):
    server = Server({("POST", "/parcels/area"): httpx.Response(500, text=TOKEN)})
    assert run_full(server) == 1
    output = lines(capsys)
    assert "FAIL area POST: HTTP 500" in output
    assert "PASS query: 1 feature(s)" in output
    assert any(line.startswith("PASS final usage") for line in output)
    assert any(line.startswith("PASS bad token") for line in output)


@pytest.mark.parametrize("cap", [3, 8, 12])
def test_request_cap(cap, capsys):
    server = Server()
    assert run_full(server, max_requests=cap) == 0
    output = lines(capsys)
    assert len(server.requests) <= cap
    assert any(line.startswith("SKIP") and "request cap" in line for line in output)
    assert output[-1] == f"NOTE requests made: {len(server.requests)}"
    if cap >= 8:
        assert any(line.startswith(("PASS final usage")) for line in output)


@pytest.mark.parametrize("repeat", [True, False])
def test_cursor_overlap(repeat, capsys):
    def page(request):
        if request.url.params.get("offset_id") == "0":
            return httpx.Response(200, json=collection(5, 7))
        return httpx.Response(200, json=collection(*((7, 9) if repeat else (6, 9))))

    server = Server()
    original = server.respond

    def respond(request, route):
        if route[1] == "/parcels/point" and request.url.params.get("radius") == "50":
            return page(request)
        return original(request, route)

    server.respond = respond
    status = run_full(server)
    output = lines(capsys)
    if repeat:
        assert status == 1
        assert "FAIL paging: cursor record repeated; pager assumptions broke" in output
    else:
        assert status == 1
        assert any(line.startswith("FAIL paging: pages not in ascending") for line in output)


def test_unordered_pages_fail(capsys):
    server = Server()
    original = server.respond

    def respond(request, route):
        if route[1] == "/parcels/point" and request.url.params.get("radius") == "50":
            ids = (7, 5) if request.url.params.get("offset_id") == "0" else (9, 11)
            return httpx.Response(200, json=collection(*ids))
        return original(request, route)

    server.respond = respond
    assert run_full(server) == 1
    assert "FAIL paging: pages not in ascending id order from offset_id=0" in lines(capsys)


def test_single_record_page_and_empty_second_page(capsys):
    server = Server()
    original = server.respond

    def respond(request, route):
        if route[1] == "/parcels/point" and request.url.params.get("radius") == "50":
            if request.url.params.get("offset_id") == "0":
                return httpx.Response(200, json=collection("7"))
            return httpx.Response(200, json=collection())
        return original(request, route)

    server.respond = respond
    assert run_full(server) == 0
    assert "PASS paging: page 1: 1, page 2: 0" in lines(capsys)


@pytest.mark.parametrize("enabled", [True, False])
def test_typeahead_opt_in(enabled, capsys):
    server = Server()
    assert run_full(server, enterprise=enabled) == 0
    output = lines(capsys)
    asked = any(r.url.path.endswith("/typeahead") for r in server.requests)
    assert asked is enabled
    assert ("PASS typeahead: 2 suggestions" in output) is enabled
    assert ("SKIP typeahead: needs an Enterprise token" in output) is not enabled


def test_typeahead_forbidden_is_a_failure(capsys):
    server = Server({("GET", "/parcels/typeahead"): httpx.Response(403, text="no")})
    assert run_full(server, enterprise=True) == 1
    assert "FAIL typeahead: token lacks typeahead" in lines(capsys)


def test_bad_token_accepted_fails(capsys):
    def accept(request):
        return httpx.Response(200, json=usage(1))

    server = Server()
    original = server.respond

    def respond(request, route):
        if request.url.params.get("token") == live_full.BAD_TOKEN:
            return accept(request)
        return original(request, route)

    server.respond = respond
    assert run_full(server) == 1
    assert "FAIL bad token: invalid token was accepted" in lines(capsys)


def test_bad_token_unexpected_status_fails(capsys):
    server = Server()
    original = server.respond

    def respond(request, route):
        if request.url.params.get("token") == live_full.BAD_TOKEN:
            return httpx.Response(500, text="x")
        return original(request, route)

    server.respond = respond
    assert run_full(server) == 1
    assert "FAIL bad token: HTTP 500" in lines(capsys)


def test_subject_with_missing_pieces_skips_dependents(capsys):
    bare = {"id": 1, "properties": {"fields": {"owner": "abc"}}}
    server = Server(
        {
            ("GET", "/parcels/address"): httpx.Response(
                200, json={"parcels": {"type": "FeatureCollection", "features": [bare]}}
            )
        }
    )
    assert run_full(server) == 0
    output = lines(capsys)
    assert "SKIP parcel: subject lacks ll_uuid" in output
    assert "SKIP parcel-path: subject lacks path, ll_uuid" in output
    assert "SKIP apn: subject lacks county, parcelnumb" in output
    assert "SKIP owner: subject lacks county" in output
    assert "SKIP point GET: subject lacks lat, lon" in output
    assert "SKIP tile: no subject coordinates" in output
    assert any(line == "NOTE address: geometry absent" for line in output)


def test_short_owner_and_mismatches_are_reported(capsys):
    subject = json.loads(json.dumps(SUBJECT))
    subject["properties"]["fields"]["owner"] = "abc"
    subject["geometry"] = None
    other = {
        "parcels": {
            "type": "FeatureCollection",
            "features": [{"id": 2, "properties": {"ll_uuid": "other"}}],
        }
    }
    server = Server(
        {
            ("GET", "/parcels/address"): httpx.Response(
                200, json={"parcels": {"type": "FeatureCollection", "features": [subject]}}
            ),
            ("GET", "/parcels/apn"): httpx.Response(200, json=other),
            ("GET", f"/parcels/{UUID}"): httpx.Response(200, json=other),
            ("GET", "/parcels/area"): httpx.Response(200, json=collection(1, geometry=False)),
        }
    )
    assert run_full(server) == 1
    output = lines(capsys)
    assert "SKIP owner: subject owner name too short" in output
    assert "NOTE address: geometry null" in output
    assert "NOTE apn: match: false" in output
    assert "FAIL parcel: returned a different parcel" in output
    assert "FAIL area GET: geometry missing" in output


@pytest.mark.parametrize(
    ("route", "fragment"),
    [
        (("GET", "/schemas/parcel"), "FAIL schema parcel"),
        (("GET", "/schemas/zoning"), "FAIL schema zoning"),
        (("GET", "/usage/detailed"), "FAIL usage detailed"),
        (("GET", "/parcels/query"), "FAIL query"),
        (("GET", "/verse"), "FAIL verse"),
        (("GET", "/api/v1/parcels/16/18995/25017.mvt"), "FAIL tile"),
    ],
)
def test_malformed_responses_fail_step(route, fragment, capsys):
    bad = httpx.Response(200, json={"parcels": {"features": []}, "schema": {}, "x": 1})
    if route[1] == "/usage/detailed":
        bad = httpx.Response(200, json={"nothing": 1})
    if route[1] == "/verse":
        bad = httpx.Response(200, json={"type": "Feature"})
    if route[1].endswith(".mvt"):
        route = ("GET", "/api/v1/parcels/16/18995/25017.mvt")
        bad = httpx.Response(500)
    if route[1] == "/schemas/zoning":
        bad = httpx.Response(200, json={})
    if route[1] == "/schemas/parcel":
        bad = httpx.Response(200, json={"schema": {}})
    server = Server({route: bad})
    assert run_full(server) == 1
    assert any(line.startswith(fragment) for line in lines(capsys))


def test_final_usage_failure_and_unavailable_counters(capsys):
    server = Server()
    calls = {"n": 0}
    original = server.respond

    def respond(request, route):
        if route[1] == "/usage" and request.url.params.get("token") == TOKEN:
            calls["n"] += 1
            if calls["n"] == 2:
                return httpx.Response(500, text=TOKEN)
        return original(request, route)

    server.respond = respond
    assert run_full(server) == 1
    assert "FAIL final usage: consumption could not be checked" in lines(capsys)

    def only_good(request):
        if request.url.params.get("token") == live_full.BAD_TOKEN:
            return httpx.Response(401)
        return httpx.Response(200, json={"usage": {}})

    server = Server({("GET", "/usage"): only_good})
    assert run_full(server) == 0
    assert "PASS final usage: comparable record counters unavailable" in lines(capsys)


@pytest.fixture(autouse=True)
def restore_logging():
    yield
    logging.disable(logging.NOTSET)


def test_main_runs_with_environment(monkeypatch, capsys):
    server = Server()
    seen = []
    inner = server.respond

    def respond(request, route):
        seen.append(logging.root.manager.disable)
        return inner(request, route)

    server.respond = respond
    transport = httpx.MockTransport(server)
    real = live_full.RegridClient
    monkeypatch.setenv("REGRID_TOKEN", TOKEN)
    monkeypatch.setenv("REGRID_LIVE_ADDRESS", "private-address")
    monkeypatch.setenv("REGRID_LIVE_ENTERPRISE", "1")
    monkeypatch.setattr(
        live_full, "RegridClient", lambda *a, **kw: real(*a, transport=transport, **kw)
    )
    assert live_full.main() == 0
    assert seen and all(level >= logging.CRITICAL for level in seen)
    output = lines(capsys)
    assert "PASS typeahead: 2 suggestions" in output
    assert server.requests[0].url.path.endswith("/schemas/parcel")
    assert any(r.url.params.get("query") == "private-address" for r in server.requests)


def test_main_initialization_failure_is_generic(monkeypatch, capsys):
    monkeypatch.setenv("REGRID_TOKEN", TOKEN)

    def boom(*args, **kwargs):
        raise RuntimeError(TOKEN)

    monkeypatch.setattr(live_full, "RegridClient", boom)
    assert live_full.main() == 1
    assert capsys.readouterr().out.strip() == "FAIL live full check initialization"


def test_run_builds_and_closes_its_own_bad_client(monkeypatch, capsys):
    server = Server()
    transport = httpx.MockTransport(server)
    real = live_full.RegridClient
    monkeypatch.setattr(
        live_full, "RegridClient", lambda *a, **kw: real(*a, transport=transport, **kw)
    )
    with real(TOKEN, transport=transport, max_limit=2, default_limit=1) as client:
        assert live_full.run(client, "private-address") == 0
    assert "PASS bad token: rejected with HTTP 401" in lines(capsys)


def test_run_preserves_custom_base_urls_for_bad_client(monkeypatch, capsys):
    server = Server()
    transport = httpx.MockTransport(server)
    real = live_full.RegridClient
    calls = []
    closed = []

    def fake_client(*args, **kwargs):
        bad = real(*args, transport=transport, **kwargs)
        orig_close = bad.close

        def tracked_close():
            closed.append(bad)
            orig_close()

        bad.close = tracked_close
        calls.append((args, kwargs, bad))
        return bad

    monkeypatch.setattr(live_full, "RegridClient", fake_client)
    with real(
        TOKEN,
        base_url="https://staging.example/api/v2",
        tiles_base_url="https://tiles.staging.example",
        transport=transport,
        max_limit=2,
        default_limit=1,
    ) as client:
        live_full.run(client, "private-address")
    assert len(calls) == 1
    args, kwargs, bad = calls[0]
    assert args == (live_full.BAD_TOKEN,)
    assert kwargs["base_url"] == "https://staging.example/api/v2"
    assert kwargs["tiles_base_url"] == "https://tiles.staging.example"
    assert closed == [bad]
    assert bad._http.is_closed
    bad_requests = [r for r in server.requests if r.url.params.get("token") == live_full.BAD_TOKEN]
    assert bad_requests and bad_requests[0].url.host == "staging.example"
    assert "PASS bad token: rejected with HTTP 401" in lines(capsys)


def test_run_forwards_public_client_settings_without_private_attrs(monkeypatch, capsys):
    server = Server()
    transport = httpx.MockTransport(server)
    real = live_full.RegridClient
    calls = []

    def fake_client(*args, **kwargs):
        bad = real(*args, transport=transport, **kwargs)
        calls.append(kwargs)
        return bad

    class PublicSettingsView:
        def __init__(self, inner):
            self._inner = inner

        def __getattr__(self, name):
            if name in {"_base_url", "_tiles_base_url", "_timeout"}:
                raise AssertionError(f"accessed private attribute {name}")
            return getattr(self._inner, name)

    monkeypatch.setattr(live_full, "RegridClient", fake_client)
    with real(
        TOKEN,
        base_url="https://staging.example/api/v2",
        tiles_base_url="https://tiles.staging.example",
        timeout=12.5,
        transport=transport,
        max_limit=2,
        default_limit=1,
    ) as client:
        assert client.base_url == "https://staging.example/api/v2"
        assert client.tiles_base_url == "https://tiles.staging.example"
        assert client.timeout == 12.5
        with pytest.raises(AttributeError):
            client.base_url = "https://other.example"  # type: ignore[misc]
        with pytest.raises(AttributeError):
            client.tiles_base_url = "https://other.example"  # type: ignore[misc]
        with pytest.raises(AttributeError):
            client.timeout = 1.0  # type: ignore[misc]
        live_full.run(PublicSettingsView(client), "private-address")  # type: ignore[arg-type]
    assert len(calls) == 1
    assert calls[0]["base_url"] == "https://staging.example/api/v2"
    assert calls[0]["tiles_base_url"] == "https://tiles.staging.example"
    assert calls[0]["timeout"] == 12.5
    assert "PASS bad token: rejected with HTTP 401" in lines(capsys)


def test_by_path_skips_when_subject_lacks_ll_uuid(capsys):
    subject = json.loads(json.dumps(SUBJECT))
    del subject["properties"]["ll_uuid"]
    server = Server(
        {
            ("GET", "/parcels/address"): httpx.Response(
                200, json={"parcels": {"type": "FeatureCollection", "features": [subject]}}
            )
        }
    )
    assert run_full(server) == 0
    output = lines(capsys)
    assert "SKIP parcel-path: subject lacks ll_uuid" in output
    assert not any(r.url.path.endswith("/parcels/path") for r in server.requests)


def test_geometry_helpers():
    assert live_full.county_path(PATH) == COUNTY
    assert live_full.county_path("/us/nj") is None
    assert live_full.county_path(None) is None
    assert live_full.tile_xy(39.123456, -75.654321, 16) == (18995, 25017)
    assert live_full.tile_xy(89.0, 200.0, 2) == (3, 0)
    ring = live_full.square(39.0, -75.0)["coordinates"][0]
    assert ring[0] == ring[-1] and len(ring) == 5
    assert live_full._number(True) is None
    assert live_full._number("x") is None
    assert live_full._number("500") is None
    assert live_full._number("91", 90) is None
    assert live_full._number("89", 90) == 89.0
    assert live_full._cursor(True) is None
    assert live_full._cursor(-1) is None
    assert live_full._cursor("12") == 12
    assert live_full._cursor("1x") is None
    with pytest.raises(live_full.CheckFailed):
        live_full._features({"parcels": {"features": "x"}})


def test_string_uuid_ids_have_no_usable_cursor(capsys):
    def uuids(request):
        return httpx.Response(200, json=collection("123e4567-e89b-42d3-a456-426614174000"))

    server = Server()
    original = server.respond

    def respond(request, route):
        if route[1] == "/parcels/point" and request.url.params.get("radius") == "50":
            return uuids(request)
        return original(request, route)

    server.respond = respond
    assert run_full(server) == 1
    assert "FAIL paging: page 1 has no usable cursor" in lines(capsys)
