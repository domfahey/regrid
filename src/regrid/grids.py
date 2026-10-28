"""Retrieve UTFGrid metadata using the endpoint advertised by raster TileJSON."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol
from urllib.parse import unquote, urljoin

import httpx

from .config import TileRequest
from .requests import safe_validate


class _GridClient(Protocol):
    _tiles_base_url: str

    def tilejson(self, *, format: str = "mvt") -> dict[str, Any]: ...

    def _send(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any],
        json: Any = None,
        public: bool = False,
    ) -> httpx.Response: ...

    def _decode(self, response: httpx.Response) -> dict[str, Any]: ...


def _template(metadata: Mapping[str, Any]) -> str:
    """Select one advertised endpoint without guessing a server path."""
    value = metadata.get("grid", metadata.get("grids"))
    if isinstance(value, list):
        if not value or not all(isinstance(item, str) and item.strip() for item in value):
            raise ValueError("TileJSON must advertise a UTFGrid endpoint")
        value = value[0]
    if not isinstance(value, str) or not value.strip():
        raise ValueError("TileJSON must advertise a UTFGrid endpoint")
    return value


def _grid_request(
    template: str, base_url: str, z: int, x: int, y: int
) -> tuple[str, dict[str, Any]]:
    """Resolve coordinates while ensuring credentials never cross an origin."""
    for field, coordinate in (("z", z), ("x", x), ("y", y)):
        template = template.replace("{" + field + "}", str(coordinate))
    # Some TileJSON producers advertise a token placeholder rather than its value.
    template = template.replace("{token}", "")
    decoded = unquote(template)
    if (
        "#" in template
        or any(character in decoded for character in "{}\\")
        or any(character.isspace() for character in template)
        or any(ord(character) < 32 or ord(character) == 127 for character in decoded)
    ):
        raise ValueError("Unsafe UTFGrid endpoint in TileJSON")
    try:
        base = httpx.URL(base_url)
        url = httpx.URL(urljoin(base_url.rstrip("/") + "/", template))
    except (ValueError, httpx.InvalidURL):
        pass
    else:
        if (
            url.scheme == base.scheme == "https"
            and url.host == base.host
            and url.port == base.port
            and not url.username
            and not url.password
            and not url.fragment
        ):
            params: dict[str, Any] = {}
            for key, value in url.params.multi_items():
                if key.lower() == "token":
                    continue
                if key in params:
                    if not isinstance(params[key], list):
                        params[key] = [params[key]]
                    params[key].append(value)
                else:
                    params[key] = value
            return str(url.copy_with(query=None)), params
    # Do not retain the parser exception or echo a token-bearing URL.
    raise ValueError("Unsafe UTFGrid endpoint in TileJSON")


def fetch_grid(
    client: _GridClient,
    z: int,
    x: int,
    y: int,
    *,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Fetch one UTFGrid, optionally reusing previously retrieved raster TileJSON.

    Discovery uses one TileJSON request when ``metadata`` is omitted. The grid
    request is always limited to the configured tileserver origin. Metadata
    credentials are discarded in favor of the client's own account token.
    """
    safe_validate(TileRequest, {"z": z, "x": x, "y": y})
    if metadata is None:
        metadata = client.tilejson(format="png")
    if not isinstance(metadata, Mapping):
        raise ValueError("UTFGrid metadata must be a TileJSON object")
    url, params = _grid_request(_template(metadata), client._tiles_base_url, z, x, y)
    return client._decode(client._send("GET", url, params=params))
