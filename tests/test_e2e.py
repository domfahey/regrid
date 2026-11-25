"""Exercise real verified TLS transport for the SDK without contacting Regrid."""

import pytest
from e2e_support import inprocess_tls_env

from regrid import RegridClient

pytestmark = pytest.mark.e2e
TILE = b"\x00\xffmock-tile\x80"


@pytest.fixture
def server(regrid_server):
    regrid_server.route("/api/v2/parcels/address", json={"ok": True})
    regrid_server.route("/api/v2/schemas/parcel", json={"ok": True})
    regrid_server.route("/api/v1/parcels/10/0/0.mvt", body=TILE)
    return regrid_server


def test_sdk_real_https(server, monkeypatch):
    inprocess_tls_env(monkeypatch, server.cert)
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
