"""Exercise real verified TLS transport and the module CLI without contacting Regrid."""

import json

import pytest
from e2e_support import regrid_server, run_cli  # noqa: F401

from regrid import RegridClient

pytestmark = pytest.mark.e2e
TILE = b"\x00\xffmock-tile\x80"


@pytest.fixture
def server(regrid_server):  # noqa: F811
    regrid_server.route("/api/v2/parcels/address", json={"ok": True})
    regrid_server.route("/api/v2/schemas/parcel", json={"ok": True})
    regrid_server.route("/api/v1/parcels/10/0/0.mvt", body=TILE)
    return regrid_server


def test_sdk_real_https(server, monkeypatch):
    monkeypatch.setenv("SSL_CERT_FILE", str(server.cert))
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    with RegridClient("secret-token", base_url=server.api, tiles_base_url=server.base) as client:
        assert client.address("123 Main", limit=2) == {"ok": True}
        assert client.tile(10, 0, 0) == TILE
    first = server.requests[0]
    assert (first.method, first.path) == ("GET", "/api/v2/parcels/address")
    assert first.params == {
        "query": ["123 Main"],
        "limit": ["2"],
        "return_parcels": ["true"],
        "token": ["secret-token"],
    }


def test_cli_real_https(server, tmp_path):
    result = run_cli(server, "address", "123 Main", "--options", '{"limit":3}')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"ok": True}
    assert server.requests[-1].params["token"] == ["secret-token"]
    assert server.requests[-1].params["limit"] == ["3"]
    result = run_cli(server, "schema", token=None)
    assert result.returncode == 0, result.stderr
    assert "token" not in server.requests[-1].params
    output = tmp_path / "tile.mvt"
    result = run_cli(server, "tile", "10", "0", "0", "--output", str(output))
    assert result.returncode == 0, result.stderr
    assert result.stdout == b""
    assert output.read_bytes() == TILE


@pytest.mark.parametrize("query,message", [("fail", b"HTTP 403"), ("malformed", b"invalid JSON")])
def test_cli_errors_real_https(server, query, message):
    def address(request):
        return None

    if query == "fail":
        server.route("/api/v2/parcels/address", status=403, body=b"secret-token")
    else:
        server.route("/api/v2/parcels/address", body=b"invalid JSON secret-token")
    result = run_cli(server, "address", query)
    assert result.returncode == 1
    assert message in result.stderr
    assert b"secret-token" not in result.stderr + result.stdout
    assert result.stdout == b""
