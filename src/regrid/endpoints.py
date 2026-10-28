"""Typed endpoint helpers for Regrid's supplied v2 OpenAPI contract.

Results remain dictionaries to preserve county-specific and premium attributes.
Only options documented for the selected endpoint are accepted.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from .requests import (
    CountryInput,
    GeometryInput,
    MethodInput,
    PointRequest,
    QueryRequest,
    TextInput,
    TokenRequest,
    safe_validate,
    validate_options,
)

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
    value = country.lower() if isinstance(country, str) else country
    country = safe_validate(CountryInput, {"value": value}).value
    return "" if country == "us" else "/ca"


def _text(value: str, name: str) -> str:
    return safe_validate(TextInput, {"value": value}).value


def _json(value: Any) -> str:
    try:
        return json.dumps(value, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("Invalid Regrid JSON request") from None


def _geometry(value: Mapping[str, Any] | str) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            raise ValueError("Invalid Regrid GeoJSON request") from None
    if isinstance(value, Mapping):
        value = dict(value)
    return safe_validate(GeometryInput, {"geojson": value}).geojson


def _options(options: dict[str, Any], allowed: set[str]) -> dict[str, Any]:
    return validate_options(options, allowed)


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
        method = safe_validate(
            MethodInput, {"value": method.upper() if isinstance(method, str) else method}
        ).value
        allowed = _parcel_options(country) | {"radius", "limit", "return_count"}
        if not prefix:
            allowed.add("return_custom_id")
        if method == "GET":
            allowed |= {"offset_id", "return_geometry"}
        params = _options(options, allowed)
        geometry = _geometry(geojson) if geojson is not None else None
        point = safe_validate(
            PointRequest, {"lat": lat, "lon": lon, "geojson": geometry, "method": method}
        )
        if point.lat is not None:
            params["lat"] = point.lat
        if point.lon is not None:
            params["lon"] = point.lon
        body = None
        if geometry is not None:
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
        method = safe_validate(
            MethodInput, {"value": method.upper() if isinstance(method, str) else method}
        ).value
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
        validate_fields: bool = False,
        allow_unknown_fields: bool = False,
        **options: Any,
    ) -> dict[str, Any]:
        """Query up to four fields, e.g. {'geoid': {'eq': '48113'}}."""
        if type(validate_fields) is not bool or type(allow_unknown_fields) is not bool:
            raise ValueError("Catalog validation flags must be booleans")
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
        if isinstance(fields, Mapping):
            fields = {
                key: dict(value) if isinstance(value, Mapping) else value
                for key, value in fields.items()
            }
        validated = safe_validate(QueryRequest, {"fields": fields}).fields
        if validate_fields:
            from .query_catalog import validate_catalog_filters

            validate_catalog_filters(
                validated,
                country=country,
                allow_unknown=allow_unknown_fields,
                paging=params.get("offset_id") is not None,
            )
        for field, operators in validated.items():
            for operator, value in operators.items():
                if isinstance(value, (list, tuple, dict, bool)) or value is None:
                    value = _json(value)
                params[f"fields[{field}][{operator}]"] = value
        return self._request("GET", f"{prefix}/parcels/query", params=params)

    def parcel(self, ll_uuid: str, *, country: str = "us", **options: Any) -> dict[str, Any]:
        """Retrieve one parcel by its Regrid UUID."""
        params = _options(options, _parcel_options(country))
        try:
            parcel_id = str(UUID(_text(ll_uuid, "ll_uuid")))
        except (ValueError, AttributeError):
            raise ValueError("ll_uuid must be a valid UUID") from None
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
        params = safe_validate(TokenRequest, {"exp": exp}).model_dump(exclude_none=True)
        return self._request("GET", "/client_token/typeahead", params=params)

    def schema(self, name: str = "parcel", **options: Any) -> dict[str, Any]:
        """Fetch a public schema; parcel accepts premium_only=True or False."""
        if name not in _SCHEMA_NAMES:
            raise ValueError("Unknown schema name")
        params = _options(options, {"premium_only"} if name == "parcel" else set())
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
