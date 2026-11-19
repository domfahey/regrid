"""E2E: tile/grid/report commands and transport-safety behaviour over local HTTPS."""

import json
import time

import pytest
from e2e_support import regrid_server, run_cli  # noqa: F401

pytestmark = pytest.mark.e2e
TOKEN = "secret-token"
TILE = b"\x00\xffmock-tile\x80"


def assert_clean(proc, server=None):
    assert TOKEN.encode() not in proc.stdout
    assert TOKEN.encode() not in proc.stderr


def requests_made(proc):
    line = proc.stderr.decode().strip().splitlines()[-1]
    assert line.startswith("regrid: requests made: ")
    return int(line.rsplit(": ", 1)[1])


def test_tilejson_mvt(regrid_server):  # noqa: F811
    regrid_server.route("/api/v1/parcels", json={"tilejson": "2.2.0", "tiles": ["x"]})
    proc = run_cli(regrid_server, "tilejson", "--format", "mvt")
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["tilejson"] == "2.2.0"
    assert requests_made(proc) == 1
    (req,) = regrid_server.requests
    assert (req.method, req.path) == ("GET", "/api/v1/parcels")
    assert req.params["format"] == ["mvt"]
    assert req.params["token"] == [TOKEN]
    assert_clean(proc)


def test_tilejson_png(regrid_server):  # noqa: F811
    regrid_server.route("/api/v1/parcels", json={"tilejson": "2.2.0"})
    proc = run_cli(regrid_server, "tilejson", "--format", "png")
    assert proc.returncode == 0, proc.stderr
    (req,) = regrid_server.requests
    assert "format" not in req.params
    assert req.params["token"] == [TOKEN]
    assert_clean(proc)


@pytest.mark.parametrize(
    ("args", "path"),
    [
        (["--format", "mvt"], "/api/v1/parcels/10/1/2.mvt"),
        (["--format", "png"], "/api/v1/parcels/10/1/2.png"),
        (["--format", "png", "--retina"], "/api/v1/parcels/10/1/2@2x.png"),
    ],
)
def test_tile_writes_bytes(regrid_server, tmp_path, args, path):  # noqa: F811
    regrid_server.route(path, body=TILE)
    out = tmp_path / "tile.bin"
    proc = run_cli(regrid_server, "tile", *args, "--output", str(out), "10", "1", "2")
    assert proc.returncode == 0, proc.stderr
    assert out.read_bytes() == TILE
    assert requests_made(proc) == 1
    (req,) = regrid_server.requests
    assert (req.method, req.path) == ("GET", path)
    assert req.params["token"] == [TOKEN]
    assert_clean(proc)


def raster_tilejson(server, template="{base}/grid/{{z}}/{{x}}/{{y}}.json?token={{token}}"):
    meta = {"tilejson": "2.2.0", "grids": [template.format(base=server.base)]}
    server.route("/api/v1/parcels", json=meta)
    server.route("/grid/12/6/7.json", json={"grid": ["  "], "keys": ["", "1"], "data": {}})
    return meta


def test_grid_discovers_tilejson(regrid_server):  # noqa: F811
    raster_tilejson(regrid_server)
    proc = run_cli(regrid_server, "grid", "12", "6", "7")
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["keys"] == ["", "1"]
    assert requests_made(proc) == 2
    meta_req, grid_req = regrid_server.requests
    assert meta_req.path == "/api/v1/parcels"
    assert "format" not in meta_req.params
    assert grid_req.method == "GET"
    assert grid_req.path == "/grid/12/6/7.json"
    # The client's own token replaces the advertised placeholder.
    assert grid_req.params["token"] == [TOKEN]
    assert_clean(proc)


def test_grid_with_metadata_file(regrid_server, tmp_path):  # noqa: F811
    meta = raster_tilejson(regrid_server)
    path = tmp_path / "meta.json"
    path.write_text(json.dumps(meta))
    proc = run_cli(regrid_server, "grid", "--metadata", f"@{path}", "12", "6", "7")
    assert proc.returncode == 0, proc.stderr
    assert requests_made(proc) == 1
    (req,) = regrid_server.requests
    assert req.path == "/grid/12/6/7.json"
    assert req.params["token"] == [TOKEN]
    assert_clean(proc)


def test_grid_rejects_foreign_origin(regrid_server):  # noqa: F811
    meta = {"grids": ["https://evil.example/grid/{z}/{x}/{y}.json"]}
    proc = run_cli(regrid_server, "grid", "--metadata", json.dumps(meta), "12", "6", "7")
    assert proc.returncode != 0
    assert regrid_server.requests == []
    assert requests_made(proc) == 0
    assert_clean(proc)


def test_report_posts_to_local_server_only(regrid_server):  # noqa: F811
    regrid_server.route("/api/v2/report", json={"status": "ok"})
    proc = run_cli(
        regrid_server,
        "report",
        "--comment",
        "wrong owner",
        "--path",
        "/us/nj/camden/haddonfield/123",
        "--details",
        '{"field": "owner"}',
    )
    assert proc.returncode == 0, proc.stderr
    assert requests_made(proc) == 1
    (req,) = regrid_server.requests
    assert (req.method, req.path) == ("POST", "/api/v2/report")
    assert req.params["comment"] == ["wrong owner"]
    assert req.params["path"] == ["/us/nj/camden/haddonfield/123"]
    assert json.loads(req.params["details"][0]) == {"field": "owner"}
    assert req.params["token"] == [TOKEN]
    assert_clean(proc)


def test_report_details_text(regrid_server):  # noqa: F811
    regrid_server.route("/api/v2/report", json={"status": "ok"})
    proc = run_cli(regrid_server, "report", "--ll-uuid", "abc", "--details-text", "plain words")
    assert proc.returncode == 0, proc.stderr
    (req,) = regrid_server.requests
    assert req.method == "POST"
    assert req.params["ll_uuid"] == ["abc"]
    assert req.params["details"] == ["plain words"]
    assert_clean(proc)


def test_client_token_typeahead(regrid_server):  # noqa: F811
    regrid_server.route("/api/v2/client_token/typeahead", json={"token": "client-xyz"})
    proc = run_cli(regrid_server, "client-token-typeahead", "--exp", "600")
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == {"token": "client-xyz"}
    assert requests_made(proc) == 1
    (req,) = regrid_server.requests
    assert req.path == "/api/v2/client_token/typeahead"
    assert float(req.params["exp"][0]) == 600
    assert req.params["token"] == [TOKEN]
    assert_clean(proc)


def test_redirect_not_followed(regrid_server):  # noqa: F811
    regrid_server.route(
        "/api/v2/parcels/address",
        status=302,
        body=b"",
        headers={"Location": regrid_server.base + "/elsewhere"},
    )
    regrid_server.route("/elsewhere", json={"parcels": {}})
    proc = run_cli(regrid_server, "address", "1 Main St")
    assert proc.returncode != 0
    assert len(regrid_server.requests) == 1
    assert all(r.path != "/elsewhere" for r in regrid_server.requests)
    assert requests_made(proc) == 1
    assert_clean(proc)


@pytest.mark.parametrize("status", [500, 429])
def test_http_errors_are_clean(regrid_server, status):  # noqa: F811
    regrid_server.route(
        "/api/v2/parcels/address",
        status=status,
        json={"error": f"boom {TOKEN}"},
    )
    proc = run_cli(regrid_server, "address", "1 Main St")
    assert proc.returncode != 0
    assert f"HTTP {status}" in proc.stderr.decode()
    assert proc.stdout == b""
    assert len(regrid_server.requests) == 1
    assert_clean(proc)


def test_timeout_exits_quickly(regrid_server):  # noqa: F811
    regrid_server.route("/api/v2/parcels/address", json={"parcels": {}}, delay=3)
    start = time.monotonic()
    proc = run_cli(regrid_server, "--timeout", "1", "address", "1 Main St")
    assert time.monotonic() - start < 2.9
    assert proc.returncode != 0
    assert "transport request failed" in proc.stderr.decode()
    assert proc.stdout == b""
    assert_clean(proc)


def test_non_json_body(regrid_server):  # noqa: F811
    regrid_server.route(
        "/api/v2/parcels/address", body=b"<html>oops</html>", content_type="text/html"
    )
    proc = run_cli(regrid_server, "address", "1 Main St")
    assert proc.returncode != 0
    assert "invalid JSON" in proc.stderr.decode()
    assert b"oops" not in proc.stderr and b"oops" not in proc.stdout
    assert requests_made(proc) == 1
    assert_clean(proc)


def test_missing_token_makes_no_request(regrid_server):  # noqa: F811
    proc = run_cli(regrid_server, "address", "1 Main St", token=None)
    assert proc.returncode != 0
    assert regrid_server.requests == []
    assert requests_made(proc) == 0


def test_tile_retina_mvt_rejected_before_request(regrid_server, tmp_path):  # noqa: F811
    out = tmp_path / "tile.bin"
    proc = run_cli(regrid_server, "tile", "--retina", "--output", str(out), "10", "1", "2")
    assert proc.returncode != 0
    assert regrid_server.requests == []
    assert not out.exists()
    assert requests_made(proc) == 0
