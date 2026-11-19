"""Shared local HTTPS fake Regrid server and CLI runner for e2e tests.

Import in tests with ``from e2e_support import regrid_server, run_cli  # noqa: F401``.
"""

import json as jsonlib
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from map_fixtures import square


@dataclass
class Recorded:
    method: str
    path: str
    params: dict[str, list[str]]
    body: bytes
    headers: dict[str, str]

    def json(self) -> Any:
        return jsonlib.loads(self.body)


@dataclass
class Route:
    status: int = 200
    body: bytes = b""
    content_type: str = "application/json"
    headers: dict[str, str] = field(default_factory=dict)
    delay: float = 0
    responder: Callable[[Recorded], Any] | None = None


def parcel_feature(n: int = 1) -> dict[str, Any]:
    lon = -75.03 + (n - 1) * 0.01
    return {
        "type": "Feature",
        "id": n,
        "geometry": square(lon=lon),
        "properties": {
            "ll_uuid": f"00000000-0000-4000-8000-{n:012d}",
            "path": f"/us/nj/camden/haddonfield/{122 + n}",
            "headline": f"{122 + n} Example Ave",
            "fields": {
                "owner": f"Owner {n}",
                "parcelnumb": f"09-{n:05d}",
                "lat": "39.9005",
                "lon": str(lon + 0.0005),
                "ll_gisacre": 2.5,
                "ll_gissqft": 108900,
                "ll_last_refresh": "2025-01-02",
                "ll_updated_at": "2025-03-14 09:26:53 -0400",
                "ll_uuid": f"00000000-0000-4000-8000-{n:012d}",
            },
        },
    }


def parcel_response(n: int = 1, start_id: int = 1) -> dict[str, Any]:
    features = [parcel_feature(i) for i in range(start_id, start_id + n)]
    return {"parcels": {"type": "FeatureCollection", "features": features}}


DEFAULT_USAGE = {"usage": {"requests": 1, "quota": 1000}}
DEFAULT_SCHEMA = {"schema": {"fields": {"owner": {"type": "string"}}}}


class FakeRegrid:
    def __init__(self, cert: Path, key: Path):
        self.cert = cert
        self.requests: list[Recorded] = []
        self.routes: dict[str, Route] = {}
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _handle(self):
                parsed = urlsplit(self.path)
                length = int(self.headers.get("Content-Length") or 0)
                recorded = Recorded(
                    self.command,
                    parsed.path,
                    parse_qs(parsed.query, keep_blank_values=True),
                    self.rfile.read(length) if length else b"",
                    {k.lower(): v for k, v in self.headers.items()},
                )
                fake.requests.append(recorded)
                route = fake.routes.get(parsed.path)
                if route is None:
                    status, body, ctype, headers = 404, b'{"error":"not found"}', "", {}
                    ctype = "application/json"
                else:
                    if route.delay:
                        time.sleep(route.delay)
                    status, body, ctype, headers = (
                        route.status,
                        route.body,
                        route.content_type,
                        route.headers,
                    )
                    if route.responder is not None:
                        body = jsonlib.dumps(route.responder(recorded)).encode()
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Content-Length", str(len(body)))
                    for name, value in headers.items():
                        self.send_header(name, value)
                    self.end_headers()
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # client timed out and hung up

            do_GET = do_POST = _handle

            def _reject(self):
                fake.requests.append(
                    Recorded(
                        self.command,
                        urlsplit(self.path).path,
                        {},
                        b"",
                        {k.lower(): v for k, v in self.headers.items()},
                    )
                )
                self.send_response(405)
                self.send_header("Content-Length", "0")
                self.end_headers()

            do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _reject

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        self.httpd.socket = context.wrap_socket(self.httpd.socket, server_side=True)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"https://127.0.0.1:{self.httpd.server_port}"
        self.api = self.base + "/api/v2"

    def route(
        self,
        path: str,
        status: int = 200,
        json: Any = None,
        body: bytes | None = None,
        content_type: str | None = None,
        headers: dict[str, str] | None = None,
        delay: float = 0,
    ) -> Route:
        """Configure a response for an exact path.

        ``json`` may be a callable taking a ``Recorded`` and returning the JSON payload.
        """
        responder = None
        if callable(json):
            responder, json = json, None
        if body is None:
            body = b"" if responder else jsonlib.dumps(json).encode()
            default_type = "application/json"
        else:
            default_type = "application/octet-stream"
        entry = Route(
            status, body, content_type or default_type, dict(headers or {}), delay, responder
        )
        self.routes[path] = entry
        return entry

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join()


@pytest.fixture
def regrid_server(tmp_path):
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
        ],  # fmt: skip
        check=True,
        capture_output=True,
    )
    server = FakeRegrid(cert, key)
    server.route("/api/v2/parcels/address", json=parcel_response())
    server.route("/api/v2/usage", json=DEFAULT_USAGE)
    server.route("/api/v2/schemas/parcel", json=DEFAULT_SCHEMA)
    try:
        yield server
    finally:
        server.close()


# Unreachable endpoints for offline commands: they must never fall back to the real Regrid URL.
DEAD_API = "https://127.0.0.1:9/api/v2"
DEAD_BASE = "https://127.0.0.1:9"
GLOBAL_VALUE_OPTIONS = ("--timeout", "--base-url", "--tiles-base-url")
SUBCOMMANDS_RUN: set[str] = set()  # runtime record; the inventory test parses sources instead


def subcommand_of(args: tuple[str, ...]) -> str | None:
    """First non-option token after the global options and their values."""
    items = iter(args)
    for item in items:
        if item in GLOBAL_VALUE_OPTIONS:
            next(items, None)
        elif not item.startswith("--"):
            return item
    return None


def e2e_env(
    cert: Path | None, home: Path | str, token: str | None = "secret-token"
) -> dict[str, str]:
    """Child environment: no inherited proxies, caches and home redirected into ``home``."""
    env = {k: v for k, v in os.environ.items() if not k.lower().endswith("_proxy")}
    if cert is not None:
        env["SSL_CERT_FILE"] = str(cert)
    env.pop("REGRID_TOKEN", None)
    if token is not None:
        env["REGRID_TOKEN"] = token
    # Local requests must not pass through a user's configured proxy.
    env["NO_PROXY"] = env["no_proxy"] = "127.0.0.1"
    for name in ("HOME", "USERPROFILE", "XDG_CACHE_HOME", "LOCALAPPDATA"):
        env[name] = str(home)
    return env


def _run(
    argv: tuple[str, ...],
    cert: Path | None,
    token: str | None,
    cwd: Path | str | None,
    timeout: float,
    env: dict[str, str] | None,
) -> subprocess.CompletedProcess:
    command = subcommand_of(argv)
    if command:
        SUBCOMMANDS_RUN.add(command)
    with tempfile.TemporaryDirectory() as home:
        return subprocess.run(
            [sys.executable, "-m", "regrid", *argv],
            env=env if env is not None else e2e_env(cert, home, token),
            cwd=cwd,
            capture_output=True,
            timeout=timeout,
        )


def run_cli(
    server: FakeRegrid,
    *args: str,
    token: str | None = "secret-token",
    cwd: Path | str | None = None,
    timeout: float = 20,
) -> subprocess.CompletedProcess:
    argv = ("--base-url", server.api, "--tiles-base-url", server.base, *args)
    return _run(argv, server.cert, token, cwd, timeout, None)


def run_cli_offline(
    *args: str,
    env: dict[str, str] | None = None,
    cwd: Path | str | None = None,
    timeout: float = 20,
) -> subprocess.CompletedProcess:
    """Run an offline command with dead endpoints and no token or certificate."""
    argv = ("--base-url", DEAD_API, "--tiles-base-url", DEAD_BASE, *args)
    return _run(argv, None, None, cwd, timeout, env)
