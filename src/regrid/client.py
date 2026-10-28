"""Synchronous transport for Regrid; retries and pagination are always explicit."""

from __future__ import annotations

import math
from typing import Any

import httpx

from .config import ClientSettings, TileRequest, validate_limit
from .endpoints import EndpointsMixin
from .requests import safe_validate


class RegridError(Exception):
    """Base SDK error. Messages never include request URLs or credentials."""


class RegridHTTPError(RegridError):
    def __init__(self, status_code: int):
        self.status_code = status_code
        super().__init__(f"Regrid returned HTTP {status_code}")


class AuthenticationError(RegridHTTPError):
    """Authentication failed or no token was provided."""


class RegridDecodeError(RegridError):
    """An endpoint returned an invalid JSON response."""


def _finite_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Non-finite JSON number")
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError("Nonstandard JSON number")


class RegridClient(EndpointsMixin):
    """Reusable, context-managed client. Dict responses preserve county-specific data."""

    def __init__(
        self,
        token: str | None = None,
        *,
        base_url: str = "https://app.regrid.com/api/v2",
        tiles_base_url: str = "https://tiles.regrid.com",
        timeout: float = 30,
        transport: httpx.BaseTransport | None = None,
        default_limit: int = 5,
        max_limit: int = 1000,
    ):
        settings = safe_validate(
            ClientSettings,
            {
                "token": token,
                "base_url": base_url,
                "tiles_base_url": tiles_base_url,
                "timeout": timeout,
                "default_limit": default_limit,
                "max_limit": max_limit,
            },
        )
        self.max_limit = settings.max_limit
        self.default_limit = settings.default_limit
        self._token = settings.token
        self._base_url = settings.base_url
        self._tiles_base_url = settings.tiles_base_url
        self._http = httpx.Client(
            timeout=settings.timeout, transport=transport, follow_redirects=False
        )

    def __enter__(self) -> RegridClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def _send(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any],
        json: Any = None,
        public: bool = False,
    ) -> httpx.Response:
        params = {key: value for key, value in params.items() if value is not None}
        if "token" in params:
            raise ValueError("Pass credentials to RegridClient, not endpoint options")
        if not public:
            if self._token is None:
                raise AuthenticationError(401)
            params["token"] = self._token.get_secret_value()
        try:
            response = self._http.request(method, url, params=params, json=json)
        except httpx.HTTPError:
            raise RegridError("Regrid transport request failed") from None
        if not 200 <= response.status_code < 300:
            error = AuthenticationError if response.status_code in (401, 403) else RegridHTTPError
            raise error(response.status_code)
        return response

    @staticmethod
    def _decode(response: httpx.Response) -> dict[str, Any]:
        try:
            data = response.json(parse_float=_finite_float, parse_constant=_reject_json_constant)
        except (ValueError, UnicodeError):
            raise RegridDecodeError("Regrid returned invalid JSON") from None
        if not isinstance(data, dict):
            raise RegridDecodeError("Expected a JSON object from Regrid")
        if data.get("status") == "error":
            raise RegridError("Regrid reported an API error")
        return data

    def _request(
        self, method: str, path: str, params: dict[str, Any] | None = None, json: Any = None
    ) -> dict[str, Any]:
        params = dict(params or {})
        if path.rsplit("/", 1)[-1] in {"point", "area", "address", "apn", "owner", "query"}:
            limit = params.get("limit")
            if limit is None:
                limit = 1 if path.endswith("/address") else self.default_limit
            params["limit"] = validate_limit(limit, self.max_limit)
        response = self._send(
            method,
            self._base_url + path,
            params=params,
            json=json,
            public=path.startswith("/schemas/"),
        )
        return self._decode(response)

    def tilejson(self, *, format: str = "mvt") -> dict[str, Any]:
        """Return TileJSON metadata for vector (mvt) or raster (png) tiles."""
        if format not in {"mvt", "png"}:
            raise ValueError("format must be mvt or png")
        params = {"format": "mvt"} if format == "mvt" else {}
        return self._decode(
            self._send("GET", self._tiles_base_url + "/api/v1/parcels", params=params)
        )

    def tile(self, z: int, x: int, y: int, *, format: str = "mvt", retina: bool = False) -> bytes:
        """Fetch a tile without decoding it. Empty successful responses return b''."""
        safe_validate(TileRequest, {"z": z, "x": x, "y": y, "format": format, "retina": retina})
        suffix = "@2x" if retina else ""
        url = f"{self._tiles_base_url}/api/v1/parcels/{z}/{x}/{y}{suffix}.{format}"
        return self._send("GET", url, params={}).content
