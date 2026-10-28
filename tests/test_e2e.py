"""Exercise real verified TLS transport and the module CLI without contacting Regrid."""

import json
import os
import shutil
import ssl
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

from regrid import RegridClient

pytestmark = pytest.mark.e2e
TILE = b"\x00\xffmock-tile\x80"


@pytest.fixture
def server(tmp_path):
    openssl = shutil.which("openssl")
    if openssl is None:
        pytest.skip("openssl is required to generate the temporary TLS certificate")
    cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    subprocess.run(
        [
            openssl,
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-keyout",
            str(key),
            "-out",
            str(cert),
            "-subj",
            "/CN=127.0.0.1",
            "-addext",
            "subjectAltName=IP:127.0.0.1",
        ],
        check=True,
        capture_output=True,
    )
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            parsed = urlsplit(self.path)
            params = parse_qs(parsed.query)
            requests.append((parsed.path, params))
            status, body = 200, b'{"ok":true}'
            if params.get("query") == ["fail"]:
                status, body = 403, b"secret-token"
            elif params.get("query") == ["malformed"]:
                body = b"invalid JSON secret-token"
            elif parsed.path.endswith(".mvt"):
                body = TILE
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"https://127.0.0.1:{httpd.server_port}", cert, requests
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join()


def invoke(server, *args, token="secret-token"):
    base, cert, _ = server
    env = os.environ.copy()
    env["SSL_CERT_FILE"] = str(cert)
    env.pop("REGRID_TOKEN", None)
    if token is not None:
        env["REGRID_TOKEN"] = token
    # Local requests must not pass through a user's configured HTTP proxy.
    env["NO_PROXY"] = "127.0.0.1"
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "regrid",
            "--base-url",
            base + "/api/v2",
            "--tiles-base-url",
            base,
            *args,
        ],
        env=env,
        capture_output=True,
        timeout=20,
    )


def test_sdk_real_https(server, monkeypatch):
    base, cert, requests = server
    monkeypatch.setenv("SSL_CERT_FILE", str(cert))
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    with RegridClient("secret-token", base_url=base + "/api/v2", tiles_base_url=base) as client:
        assert client.address("123 Main", limit=2) == {"ok": True}
        assert client.tile(10, 0, 0) == TILE
    assert requests[0] == (
        "/api/v2/parcels/address",
        {
            "query": ["123 Main"],
            "limit": ["2"],
            "return_parcels": ["true"],
            "token": ["secret-token"],
        },
    )


def test_cli_real_https(server, tmp_path):
    result = invoke(server, "address", "123 Main", "--options", '{"limit":3}')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"ok": True}
    assert server[2][-1][1]["token"] == ["secret-token"]
    assert server[2][-1][1]["limit"] == ["3"]
    result = invoke(server, "schema", token=None)
    assert result.returncode == 0, result.stderr
    assert "token" not in server[2][-1][1]
    output = tmp_path / "tile.mvt"
    result = invoke(server, "tile", "10", "0", "0", "--output", str(output))
    assert result.returncode == 0, result.stderr
    assert result.stdout == b""
    assert output.read_bytes() == TILE


@pytest.mark.parametrize("query,message", [("fail", b"HTTP 403"), ("malformed", b"invalid JSON")])
def test_cli_errors_real_https(server, query, message):
    result = invoke(server, "address", query)
    assert result.returncode == 1
    assert message in result.stderr
    assert b"secret-token" not in result.stderr + result.stdout
    assert result.stdout == b""
