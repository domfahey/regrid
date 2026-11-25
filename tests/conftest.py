from collections.abc import Iterator
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from e2e_support import FakeRegrid


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path_factory, monkeypatch):
    """Keep every test away from the real home and cache directories."""
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("XDG_CACHE_HOME", str(home / ".cache"))
    monkeypatch.setenv("LOCALAPPDATA", str(home / "AppData" / "Local"))


@pytest.fixture
def regrid_server() -> Iterator["FakeRegrid"]:
    """Start a local verified-HTTPS fake Regrid server for E2E tests."""
    from e2e_support import start_regrid_server

    server = start_regrid_server()
    try:
        yield server
    finally:
        server.close()
