"""Typed endpoint helpers for Regrid's supplied v2 OpenAPI contract.

Results remain dictionaries to preserve county-specific and premium attributes.
Only options documented for the selected endpoint are accepted.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from typing import Any
from uuid import UUID

_COMMON = {"return_custom", "return_field_labels", "return_stacked"}
_PREMIUM = {
    "return_zoning",
    "return_matched_buildings",
    "return_matched_addresses",
    "return_enhanced_ownership",
    "return_parcels",
}
_USAGE = {
    "return_full_history",
    "begin_date",
    "end_date",
    "return_by_token",
    "return_by_this_token",
}
_SCHEMA_NAMES = {"parcel", "building", "address", "enhanced_ownership", "zoning", "ca"}


def _country(country: str) -> str:
    if not isinstance(country, str) or country.lower() not in {"us", "ca"}:
        raise ValueError("country must be 'us' or 'ca'")
    return "" if country.lower() == "us" else "/ca"


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")
    return value


def _json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), allow_nan=False)


def _geometry(value: Mapping[str, Any] | str) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError) as exc:
            raise ValueError("geojson must be valid JSON") from exc
    if not isinstance(value, Mapping) or "type" not in value:
        raise ValueError("geojson must be an object with a type")
    result = dict(value)
    _json(result)  # Reject NaN/Infinity before transport.
    return result


def _options(options: dict[str, Any], allowed: set[str]) -> dict[str, Any]:
    unknown = options.keys() - allowed
    if unknown:
        raise ValueError("Unsupported options: " + ", ".join(sorted(unknown)))
    result = {key: value for key, value in options.items() if value is not None}
    if "return_parcels" in allowed:
        # The supplied contract disagrees on this default; make it explicit.
        result.setdefault("return_parcels", True)
    for key, value in result.items():
        if key.startswith("return_") and not isinstance(value, bool):
            raise ValueError(f"{key} must be a boolean")
    if "radius" in result:
        radius = result["radius"]
        if isinstance(radius, bool) or not isinstance(radius, int) or not 0 <= radius <= 32000:
            raise ValueError("radius must be an integer from 0 through 32000 meters")
    if "offset_id" in result:
        cursor = result["offset_id"]
        if isinstance(cursor, bool) or not isinstance(cursor, int) or cursor < 0:
            raise ValueError("offset_id must be a nonnegative integer")
    return result


def _parcel_options(country: str) -> set[str]:
    return _COMMON | (_PREMIUM if not _country(country) else set())


class EndpointsMixin:
    """Endpoint methods used by the synchronous client transport."""

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    def point(
        self,
        lat: float | None = None,
        lon: float | None = None,
        *,
        geojson: Mapping[str, Any] | str | None = None,
        country: str = "us",
        method: str = "GET",
        **options: Any,
    ) -> dict[str, Any]:
        """Find parcels at coordinates or GeoJSON points; POST requires GeoJSON."""
        prefix = _country(country)
        method = method.upper()
        if method not in {"GET", "POST"}:
            raise ValueError("method must be GET or POST")
        allowed = _parcel_options(country) | {"radius", "limit", "return_count"}
        if not prefix:
            allowed.add("return_custom_id")
        if method == "GET":
            allowed |= {"offset_id", "return_geometry"}
        params = _options(options, allowed)
        if geojson is None and (lat is None or lon is None):
            raise ValueError("provide both lat and lon, or geojson")
        for name, value, bound in (("lat", lat, 90), ("lon", lon, 180)):
            if value is not None:
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    or not -bound <= value <= bound
                ):
                    raise ValueError(f"{name} is outside its coordinate range")
                params[name] = value
        if method == "POST" and geojson is None:
            raise ValueError("POST point requires geojson")
        body = None
        if geojson is not None:
            geometry = _geometry(geojson)
            shape = geometry.get("geometry") if geometry.get("type") == "Feature" else geometry
            if not isinstance(shape, Mapping) or shape.get("type") not in {"Point", "MultiPoint"}:
                raise ValueError("point accepts Point or MultiPoint geometry")
            if method == "POST":
                body = {"geojson": geometry}
            else:
                params["geojson"] = _json(geometry)
        return self._request(method, f"{prefix}/parcels/point", params=params, json=body)

    def area(
        self,
        geojson: Mapping[str, Any] | str,
        *,
        country: str = "us",
        method: str = "GET",
        **options: Any,
    ) -> dict[str, Any]:
        """Search geometry using GET query JSON or a POST JSON body."""
        prefix = _country(country)
        method = method.upper()
        if method not in {"GET", "POST"}:
            raise ValueError("method must be GET or POST")
        allowed = _parcel_options(country) | {
            "radius",
            "offset_id",
            "limit",
            "return_geometry",
            "return_count",
        }
        if not prefix:
            allowed.add("return_custom_id")
        params = _options(options, allowed)
        geometry = _geometry(geojson)
        if method == "POST":
            return self._request(
                method, f"{prefix}/parcels/area", params=params, json={"geojson": geometry}
            )
        params["geojson"] = _json(geometry)
        return self._request(method, f"{prefix}/parcels/area", params=params)

    def address(self, query: str, *, country: str = "us", **options: Any) -> dict[str, Any]:
        """Search an address; use path to disambiguate its geography."""
        params = _options(options, _parcel_options(country) | {"path", "limit"})
        params["query"] = _text(query, "query")
        return self._request("GET", f"{_country(country)}/parcels/address", params=params)

    def apn(self, parcelnumb: str, *, country: str = "us", **options: Any) -> dict[str, Any]:
        """Search an APN as a string, preserving leading zeros and letters."""
        params = _options(options, _parcel_options(country) | {"path", "limit"})
        params["parcelnumb"] = _text(parcelnumb, "parcelnumb")
        return self._request("GET", f"{_country(country)}/parcels/apn", params=params)

    def owner(self, owner: str, *, country: str = "us", **options: Any) -> dict[str, Any]:
        """Search an owner-name prefix (US only, at least four characters)."""
        if _country(country):
            raise ValueError("owner search is only documented for the US")
        owner = _text(owner, "owner")
        if len(owner.strip()) < 4:
            raise ValueError("owner must contain at least four characters")
        params = _options(options, _parcel_options(country) | {"path", "limit"})
        params["owner"] = owner
        return self._request("GET", "/parcels/owner", params=params)

    def query(
        self,
        fields: Mapping[str, Mapping[str, Any]],
        *,
        country: str = "us",
        **options: Any,
    ) -> dict[str, Any]:
        """Query up to four fields, e.g. {'geoid': {'eq': '48113'}}."""
        prefix = _country(country)
        allowed = _parcel_options(country) | {
            "offset_id",
            "geojson",
            "radius",
            "limit",
            "path",
            "return_count",
            "return_geometry",
        }
        if not prefix:
            allowed.add("return_custom_id")
        params = _options(options, allowed)
        if "geojson" in params:
            params["geojson"] = _json(_geometry(params["geojson"]))
        if not isinstance(fields, Mapping) or not 1 <= len(fields) <= 4:
            raise ValueError("fields must contain one through four field names")
        for field, operators in fields.items():
            if not isinstance(field, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", field):
                raise ValueError("invalid field name")
            if not isinstance(operators, Mapping) or not operators:
                raise ValueError("each field requires an operator mapping")
            for operator, value in operators.items():
                if not isinstance(operator, str) or not re.fullmatch(r"[a-z_]+", operator):
                    raise ValueError("invalid field operator")
                if isinstance(value, (list, tuple, dict, bool)) or value is None:
                    value = _json(value)
                elif isinstance(value, float) and not math.isfinite(value):
                    raise ValueError("field values must be finite")
                params[f"fields[{field}][{operator}]"] = value
        return self._request("GET", f"{prefix}/parcels/query", params=params)

    def parcel(self, ll_uuid: str, *, country: str = "us", **options: Any) -> dict[str, Any]:
        """Retrieve one parcel by its Regrid UUID."""
        params = _options(options, _parcel_options(country))
        try:
            parcel_id = str(UUID(_text(ll_uuid, "ll_uuid")))
        except (ValueError, AttributeError) as exc:
            raise ValueError("ll_uuid must be a valid UUID") from exc
        return self._request("GET", f"{_country(country)}/parcels/{parcel_id}", params=params)

    def parcel_path(self, path: str, *, country: str = "us", **options: Any) -> dict[str, Any]:
        """Retrieve one parcel by its full canonical path."""
        params = _options(options, _parcel_options(country))
        params["path"] = _text(path, "path")
        return self._request("GET", f"{_country(country)}/parcels/path", params=params)

    def typeahead(self, query: str, *, country: str = "us") -> dict[str, Any]:
        """Enterprise US address autocomplete; accepts a client token at client creation."""
        if _country(country):
            raise ValueError("typeahead is only documented for the US")
        return self._request("GET", "/parcels/typeahead", params={"query": _text(query, "query")})

    def client_token_typeahead(self, exp: float | None = None) -> dict[str, Any]:
        """Create a temporary typeahead-only token; exp is a duration in seconds."""
        params: dict[str, Any] = {}
        if exp is not None:
            if (
                isinstance(exp, bool)
                or not isinstance(exp, (int, float))
                or not math.isfinite(exp)
                or exp <= 0
            ):
                raise ValueError("exp must be a positive finite number of seconds")
            params["exp"] = exp
        return self._request("GET", "/client_token/typeahead", params=params)

    def schema(self, name: str = "parcel", **options: Any) -> dict[str, Any]:
        """Fetch a public schema; parcel accepts premium_only=True or False."""
        if name not in _SCHEMA_NAMES:
            raise ValueError("Unknown schema name")
        params = _options(options, {"premium_only"} if name == "parcel" else set())
        if "premium_only" in params and not isinstance(params["premium_only"], bool):
            raise ValueError("premium_only must be a boolean")
        return self._request("GET", f"/schemas/{name}", params=params)

    def verse(self, *, country: str = "us", **options: Any) -> dict[str, Any]:
        """Retrieve county or Canadian administrative-area source metadata."""
        params = _options(options, {"return_geometry"})
        return self._request("GET", f"{_country(country)}/verse", params=params)

    def usage(
        self, *, country: str = "us", detailed: bool = False, **options: Any
    ) -> dict[str, Any]:
        """Retrieve usage; detailed breakdown is available at the global US-base route."""
        prefix = _country(country)
        if not isinstance(detailed, bool):
            raise TypeError("detailed must be a boolean")
        if prefix and detailed:
            raise ValueError("/ca/usage/detailed is not documented; use usage(detailed=True)")
        params = _options(options, _USAGE)
        path = f"{prefix}/usage" + ("/detailed" if detailed else "")
        return self._request("GET", path, params=params)

    def report(
        self,
        comment: str | None = None,
        *,
        path: str | None = None,
        ll_uuid: str | None = None,
        details: Mapping[str, Any] | str | None = None,
    ) -> dict[str, Any]:
        """Submit a data issue to Regrid. This method creates an external report."""
        params: dict[str, Any] = {}
        if comment is not None:
            params["comment"] = _text(comment, "comment")
        if path is not None:
            params["path"] = _text(path, "path")
        if ll_uuid is not None:
            params["ll_uuid"] = _text(ll_uuid, "ll_uuid")
        if details is not None:
            params["details"] = (
                _json(dict(details)) if isinstance(details, Mapping) else _text(details, "details")
            )
        return self._request("POST", "/report", params=params)
