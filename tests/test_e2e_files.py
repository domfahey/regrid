"""E2E: file-producing, offline, and public-endpoint CLI commands over local verified TLS."""

import csv
import json
import time

import pytest
from e2e_support import run_cli, run_cli_offline
from map_fixtures import feature, good_feature, square, write_response

pytestmark = pytest.mark.e2e

TOKEN = "secret-token"
ADDRESS = "/api/v2/parcels/address"
POINT = "/api/v2/parcels/point"
COLLECTION = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {
                "path": "/us/nj/camden",
                "county": "Camden",
                "state": "NJ",
                "last_refresh": "2026-09-01",
                "assessor_data_date": "2026-08-15",
                "usps_data_date": None,
            },
        }
    ],
}
# The real /verse body wraps the collection under a top-level "verse" key.
VERSE = {"verse": COLLECTION}


def good_response(uuid="00000000-0000-4000-8000-000000000001", **fields):
    item = good_feature(lat="39.9005", lon="-75.0295", **fields)
    item["properties"]["ll_uuid"] = uuid
    return {"parcels": {"type": "FeatureCollection", "features": [item]}}


def no_token(result):
    assert TOKEN.encode() not in result.stdout + result.stderr


def requests_made(result):
    line = [ln for ln in result.stderr.decode().splitlines() if "requests made" in ln]
    assert len(line) == 1, result.stderr
    return int(line[0].rsplit(" ", 1)[1])


@pytest.fixture
def server(regrid_server):
    regrid_server.route(ADDRESS, json=good_response())
    return regrid_server


def test_address_map_one_request(server, tmp_path):
    out = tmp_path / "map.html"
    result = run_cli(server, "address-map", "12 Example Ave", str(out), cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    no_token(result)
    assert requests_made(result) == 1
    page = out.read_text()
    assert "leaflet" in page.lower() and "12 Example Ave" in page
    assert TOKEN not in page
    saved = json.loads((tmp_path / "map.json").read_text())
    assert saved["parcels"]["features"][0]["properties"]["ll_uuid"].endswith("01")
    assert json.loads(result.stdout)["response"].endswith("map.json")
    (req,) = server.requests
    assert (req.method, req.path) == ("GET", ADDRESS)
    assert req.params["query"] == ["12 Example Ave"]
    assert req.params["limit"] == ["1"] and req.params["token"] == [TOKEN]
    assert "path" not in req.params
    assert not (tmp_path / "map.neighbours.json").exists()


def test_address_map_options_and_replace(server, tmp_path):
    out, saved = tmp_path / "m.html", tmp_path / "resp.json"
    args = ["address-map", "12 Example Ave", str(out), "--save-response", str(saved)]
    result = run_cli(
        server, *args, "--path", "/us/nj/camden", "--retrieved-at", "2026-01-02T03:04:05Z"
    )
    assert result.returncode == 0, result.stderr
    assert "2026-01-02T03:04:05Z" in out.read_text()
    assert saved.exists() and not (tmp_path / "m.json").exists()
    assert server.requests[0].params["path"] == ["/us/nj/camden"]
    before = out.read_bytes()
    refused = run_cli(server, *args)
    assert refused.returncode != 0 and requests_made(refused) == 0
    assert b"--replace" in refused.stderr and len(server.requests) == 1
    assert out.read_bytes() == before
    again = run_cli(server, *args, "--replace")
    assert again.returncode == 0 and requests_made(again) == 1
    assert len(server.requests) == 2


def test_address_map_neighbours(server, tmp_path):
    other = good_response("00000000-0000-4000-8000-000000000002")
    server.route(POINT, json=other)
    out = tmp_path / "n.html"
    result = run_cli(server, "address-map", "12 Example Ave", str(out), "--neighbours")
    assert result.returncode == 0, result.stderr
    no_token(result)
    assert requests_made(result) == 2
    assert [r.path for r in server.requests] == [ADDRESS, POINT]
    near = server.requests[1]
    assert near.params["radius"] == ["100"] and near.params["limit"] == ["25"]
    assert near.params["lat"] == ["39.9005"] and near.params["lon"] == ["-75.0295"]
    assert near.params["token"] == [TOKEN]
    neighbours = tmp_path / "n.neighbours.json"
    assert neighbours.exists()
    assert json.loads(result.stdout)["neighbours_response"].endswith("n.neighbours.json")
    assert TOKEN not in out.read_text()


def test_map_offline_zero_requests(tmp_path):
    response = write_response(tmp_path / "r.json", good_feature())
    out = tmp_path / "o.html"
    result = run_cli_offline("map", str(response), str(out), "--retrieved-at", "2026-01-02")
    assert result.returncode == 0, result.stderr
    assert "requests made" not in result.stderr.decode()
    assert "leaflet" in out.read_text().lower()
    assert json.loads(result.stdout)["output"].endswith("o.html")
    assert "area mismatch" not in result.stdout.decode() + result.stderr.decode()
    refused = run_cli_offline("map", str(response), str(out))
    assert refused.returncode != 0 and b"--replace" in refused.stderr


def test_map_area_mismatch_warning(tmp_path):
    response = write_response(tmp_path / "r.json", feature(square(), ll_gissqft=999999))
    out = tmp_path / "o.html"
    result = run_cli_offline("map", str(response), str(out))
    assert result.returncode == 0, result.stderr
    assert "area mismatch" in result.stdout.decode() + result.stderr.decode()
    assert "area mismatch" in out.read_text()


def test_export_csv_geojson_all_fields_and_formula(tmp_path):
    item = good_feature(owner="=HYPERLINK(1)", parcelnumb="09-1", extra_field="zzz")
    response = write_response(tmp_path / "r.json", item)
    csv_path, geo = tmp_path / "o.csv", tmp_path / "o.geojson"
    cmd = [str(response)]
    result = run_cli_offline(
        "export", *cmd, "--csv", str(csv_path), "--geojson", str(geo), "--all-fields"
    )
    assert result.returncode == 0, result.stderr
    assert b"requests made" not in result.stderr
    rows = list(csv.DictReader(csv_path.open(newline="")))
    assert len(rows) == 1
    assert rows[0]["owner"] == "'=HYPERLINK(1)"
    assert rows[0]["extra_field"] == "zzz"
    collection = json.loads(geo.read_text())
    assert collection["type"] == "FeatureCollection"
    assert collection["features"][0]["geometry"]["type"] == "Polygon"
    plain = tmp_path / "p.csv"
    assert run_cli_offline("export", *cmd, "--csv", str(plain)).returncode == 0
    assert "extra_field" not in plain.read_text().splitlines()[0]
    again = run_cli_offline("export", *cmd, "--csv", str(plain))
    assert again.returncode != 0 and b"--replace" in again.stderr
    assert run_cli_offline("export", *cmd, "--csv", str(plain), "--replace").returncode == 0


def test_fields_explain_and_search_offline():
    explain = run_cli_offline("fields", "explain", "owner", "parcelnumb")
    assert explain.returncode == 0, explain.stderr
    assert "requests made" not in explain.stderr.decode()
    text = explain.stdout.decode()
    assert "owner" in text and "parcelnumb" in text
    search = run_cli_offline("fields", "search", "owner")
    assert search.returncode == 0, search.stderr
    assert "owner" in search.stdout.decode()
    assert "requests made" not in search.stderr.decode()


def test_freshness_cache_lifecycle(regrid_server, tmp_path):
    regrid_server.route("/api/v2/verse", json=VERSE)
    cache = tmp_path / "sub" / "verse.json"
    cache.parent.mkdir()
    args = ["--path", "/us/nj/camden", "--cache", str(cache)]
    first = run_cli(regrid_server, "freshness", *args)
    assert first.returncode == 0, first.stderr
    no_token(first)
    assert requests_made(first) == 1
    data = json.loads(first.stdout)
    assert data["cache"] == "miss" and data["last_refresh"] == "2026-09-01"
    req = regrid_server.requests[0]
    assert (req.method, req.path) == ("GET", "/api/v2/verse")
    assert req.params["return_geometry"] == ["false"] and req.params["token"] == [TOKEN]
    second = run_cli(regrid_server, "freshness", *args)
    assert requests_made(second) == 0 and json.loads(second.stdout)["cache"] == "hit"
    assert len(regrid_server.requests) == 1
    third = run_cli(regrid_server, "freshness", *args, "--refresh")
    assert requests_made(third) == 1 and json.loads(third.stdout)["cache"] == "miss"
    assert len(regrid_server.requests) == 2
    no_token(second)
    no_token(third)


@pytest.mark.parametrize("name", ["parcel", "building", "address", "enhanced_ownership", "zoning"])
def test_schema_every_name_is_public(regrid_server, name):
    regrid_server.route(f"/api/v2/schemas/{name}", json={"schema": name})
    result = run_cli(regrid_server, "schema", name, token=None)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"schema": name}
    assert requests_made(result) == 1
    (req,) = regrid_server.requests
    assert (req.method, req.path) == ("GET", f"/api/v2/schemas/{name}")
    assert "token" not in req.params and "authorization" not in req.headers
    with_token = run_cli(regrid_server, "schema", name)
    assert with_token.returncode == 0
    for sent in regrid_server.requests:
        assert "token" not in sent.params and TOKEN not in str(sent.headers)
    no_token(with_token)


def test_schema_premium_only_option(regrid_server):
    result = run_cli(regrid_server, "schema", "parcel", "--options", '{"premium_only":true}')
    assert result.returncode == 0, result.stderr
    (req,) = regrid_server.requests
    assert req.path == "/api/v2/schemas/parcel"
    assert req.params == {"premium_only": ["true"]}


def test_usage_and_detailed(regrid_server):
    result = run_cli(regrid_server, "usage")
    assert result.returncode == 0, result.stderr
    no_token(result)
    assert requests_made(result) == 1
    assert json.loads(result.stdout) == {"usage": {"requests": 1, "quota": 1000}}
    req = regrid_server.requests[0]
    assert (req.method, req.path) == ("GET", "/api/v2/usage")
    assert req.params == {"token": [TOKEN]}
    regrid_server.route("/api/v2/usage/detailed", json={"detail": [1]})
    detailed = run_cli(
        regrid_server,
        "usage",
        "--detailed",
        "--options",
        '{"begin_date":"2026-01-01","end_date":"2026-01-31"}',
    )
    assert detailed.returncode == 0, detailed.stderr
    no_token(detailed)
    assert json.loads(detailed.stdout) == {"detail": [1]}
    req = regrid_server.requests[1]
    assert req.path == "/api/v2/usage/detailed"
    assert req.params == {
        "begin_date": ["2026-01-01"],
        "end_date": ["2026-01-31"],
        "token": [TOKEN],
    }


def test_verse_raw(regrid_server):
    regrid_server.route("/api/v2/verse", json=VERSE)
    result = run_cli(regrid_server, "verse", "--options", '{"return_geometry":false}')
    assert result.returncode == 0, result.stderr
    no_token(result)
    assert requests_made(result) == 1
    assert json.loads(result.stdout) == VERSE
    req = regrid_server.requests[0]
    assert (req.method, req.path) == ("GET", "/api/v2/verse")
    assert req.params == {"return_geometry": ["false"], "token": [TOKEN]}


def _multi_response(tmp_path):
    first = good_feature()
    second = good_feature()
    second["properties"]["headline"] = "99 Second St"
    second["properties"]["ll_uuid"] = "00000000-0000-4000-8000-000000000002"
    return write_response(tmp_path / "multi.json", first, second)


def test_map_multi_feature_selection(tmp_path):
    response = _multi_response(tmp_path)
    bare = run_cli_offline("map", str(response), str(tmp_path / "bare.html"))
    assert bare.returncode == 1 and b"--feature or --all-candidates" in bare.stderr
    assert not (tmp_path / "bare.html").exists()

    one = tmp_path / "one.html"
    one_run = run_cli_offline("map", str(response), str(one), "--feature", "1")
    assert one_run.returncode == 0, one_run.stderr
    page = one.read_text()
    assert "99 Second St" in page and "12 Example Ave" not in page
    assert "Candidate 1" not in page

    many = tmp_path / "many.html"
    many_run = run_cli_offline("map", str(response), str(many), "--all-candidates")
    assert many_run.returncode == 0, many_run.stderr
    page = many.read_text()
    assert "Candidate 1" in page and "Candidate 2" in page
    assert "99 Second St" in page and "12 Example Ave" in page

    both = tmp_path / "both.html"
    both_run = run_cli_offline(
        "map", str(response), str(both), "--feature", "1", "--all-candidates"
    )
    assert both_run.returncode == 1 and b"not both" in both_run.stderr
    assert not both.exists()
    out_of_range = run_cli_offline("map", str(response), str(both), "--feature", "5")
    assert out_of_range.returncode == 1 and b"between 0 and 1" in out_of_range.stderr
    for run in (bare, one_run, many_run, both_run, out_of_range):
        assert b"requests made" not in run.stderr


def test_fields_unknown_and_no_match_offline():
    unknown = run_cli_offline("fields", "explain", "owner", "no_such_field")
    assert unknown.returncode == 0, unknown.stderr
    data = json.loads(unknown.stdout)
    assert data["unknown"] == ["no_such_field"]
    assert [f["name"] for f in data["found"]] == ["owner"]
    empty = run_cli_offline("fields", "search", "zzzqqqxxx")
    assert empty.returncode == 0, empty.stderr
    assert json.loads(empty.stdout) == {"matches": []}
    for run in (unknown, empty):
        assert b"requests made" not in run.stderr


def test_freshness_max_age_days_refetches_old_cache(regrid_server, tmp_path):
    regrid_server.route("/api/v2/verse", json=VERSE)
    cache = tmp_path / "verse.json"
    args = ["--path", "/us/nj/camden", "--cache", str(cache)]
    assert run_cli(regrid_server, "freshness", *args).returncode == 0
    assert len(regrid_server.requests) == 1
    fresh = run_cli(regrid_server, "freshness", *args, "--max-age-days", "5")
    assert requests_made(fresh) == 0 and json.loads(fresh.stdout)["cache"] == "hit"
    document = json.loads(cache.read_text())
    document["retrieved_at"] = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 10 * 86400)
    )
    cache.write_text(json.dumps(document))
    stale = run_cli(regrid_server, "freshness", *args, "--max-age-days", "5")
    assert stale.returncode == 0, stale.stderr
    assert requests_made(stale) == 1
    assert json.loads(stale.stdout)["cache"] == "miss"
    assert "cached verse is older than 5 days; refetching" in stale.stderr.decode()
    assert len(regrid_server.requests) == 2
    kept = run_cli(regrid_server, "freshness", *args, "--max-age-days", "30")
    assert requests_made(kept) == 0 and len(regrid_server.requests) == 2
    no_token(stale)


def test_map_offline_neighbours_file(tmp_path):
    subject = write_response(tmp_path / "r.json", good_feature())
    other = good_feature()
    other["properties"]["headline"] = "77 Neighbour Rd"
    other["properties"]["ll_uuid"] = "00000000-0000-4000-8000-000000000009"
    neighbours = write_response(tmp_path / "n.json", other)
    plain = tmp_path / "plain.html"
    assert run_cli_offline("map", str(subject), str(plain)).returncode == 0
    assert "77 Neighbour Rd" not in plain.read_text()
    out = tmp_path / "o.html"
    result = run_cli_offline("map", str(subject), str(out), "--neighbours", str(neighbours))
    assert result.returncode == 0, result.stderr
    assert b"requests made" not in result.stderr
    assert json.loads(result.stdout)["neighbours"] == 1
    assert "77 Neighbour Rd" in out.read_text()
