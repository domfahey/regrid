"""Opt-in typed responses with the original dictionary client available as ``raw``."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, TypeVar, overload

import httpx
from pydantic import BaseModel, ValidationError

from .client import RegridClient, RegridDecodeError
from .models import (
    ClientTokenResponse,
    DetailedUsageResponse,
    ParcelResponse,
    ParcelSearchResponse,
    ReportResponse,
    SchemaResponse,
    TileJSON,
    TypeaheadResponse,
    UsageResponse,
    UTFGridResponse,
    VerseResponse,
    parse_parcel_response,
)

ModelT = TypeVar("ModelT", bound=BaseModel)


def _validate(model: type[ModelT], data: dict[str, Any]) -> ModelT:
    try:
        return model.model_validate(data)
    except ValidationError:
        pass
    # Raising after the handler also discards the sensitive exception context.
    raise RegridDecodeError("Regrid response failed schema validation")


def _parcels(data: dict[str, Any]) -> ParcelSearchResponse:
    try:
        return parse_parcel_response(data)
    except ValidationError:
        pass
    # Raising after the handler also discards the sensitive exception context.
    raise RegridDecodeError("Regrid response failed schema validation")


class TypedRegridClient:
    """Validate responses into Pydantic models without changing the raw SDK API.

    ``raw`` shares this client's transport and lifetime. Access it when an upstream
    response is not yet modeled, or when an unchanged response dictionary is needed.
    """

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
        self.raw = RegridClient(
            token,
            base_url=base_url,
            tiles_base_url=tiles_base_url,
            timeout=timeout,
            transport=transport,
            default_limit=default_limit,
            max_limit=max_limit,
        )

    def __enter__(self) -> TypedRegridClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the shared typed/raw HTTP transport."""
        self.raw.close()

    def point(
        self,
        lat: float | None = None,
        lon: float | None = None,
        *,
        geojson: Mapping[str, Any] | str | None = None,
        country: str = "us",
        method: str = "GET",
        **options: Any,
    ) -> ParcelSearchResponse:
        """Find parcels or retrieve a count at a point or set of points."""
        return _parcels(
            self.raw.point(lat, lon, geojson=geojson, country=country, method=method, **options)
        )

    def area(
        self,
        geojson: Mapping[str, Any] | str,
        *,
        country: str = "us",
        method: str = "GET",
        **options: Any,
    ) -> ParcelSearchResponse:
        """Find parcels or retrieve a count within a supplied geometry."""
        return _parcels(self.raw.area(geojson, country=country, method=method, **options))

    def address(self, query: str, *, country: str = "us", **options: Any) -> ParcelResponse:
        """Find parcels by address."""
        return _validate(ParcelResponse, self.raw.address(query, country=country, **options))

    def apn(self, parcelnumb: str, *, country: str = "us", **options: Any) -> ParcelResponse:
        """Find parcels by APN, preserving leading zeros and letters."""
        return _validate(ParcelResponse, self.raw.apn(parcelnumb, country=country, **options))

    def owner(self, owner: str, *, country: str = "us", **options: Any) -> ParcelResponse:
        """Find parcels by owner-name prefix."""
        return _validate(ParcelResponse, self.raw.owner(owner, country=country, **options))

    def query(
        self,
        fields: Mapping[str, Mapping[str, Any]],
        *,
        country: str = "us",
        validate_fields: bool = False,
        allow_unknown_fields: bool = False,
        **options: Any,
    ) -> ParcelSearchResponse:
        """Find parcels or a count, optionally validating US catalog filters."""
        return _parcels(
            self.raw.query(
                fields,
                country=country,
                validate_fields=validate_fields,
                allow_unknown_fields=allow_unknown_fields,
                **options,
            )
        )

    def parcel(self, ll_uuid: str, *, country: str = "us", **options: Any) -> ParcelResponse:
        """Retrieve a parcel by Regrid UUID."""
        return _validate(ParcelResponse, self.raw.parcel(ll_uuid, country=country, **options))

    def parcel_path(self, path: str, *, country: str = "us", **options: Any) -> ParcelResponse:
        """Retrieve a parcel by canonical path."""
        return _validate(ParcelResponse, self.raw.parcel_path(path, country=country, **options))

    def typeahead(self, query: str, *, country: str = "us") -> TypeaheadResponse:
        """Retrieve address autocomplete suggestions."""
        return _validate(TypeaheadResponse, self.raw.typeahead(query, country=country))

    def client_token_typeahead(self, exp: float | None = None) -> ClientTokenResponse:
        """Create a temporary token, masked in model representations."""
        return _validate(ClientTokenResponse, self.raw.client_token_typeahead(exp))

    def schema(self, name: str = "parcel", **options: Any) -> SchemaResponse:
        """Retrieve public field schema metadata."""
        return _validate(SchemaResponse, self.raw.schema(name, **options))

    def verse(self, *, country: str = "us", **options: Any) -> VerseResponse:
        """Retrieve county or Canadian administrative-area metadata."""
        return _validate(VerseResponse, self.raw.verse(country=country, **options))

    @overload
    def usage(
        self, *, country: str = "us", detailed: Literal[False] = False, **options: Any
    ) -> UsageResponse: ...

    @overload
    def usage(
        self, *, country: str = "us", detailed: Literal[True], **options: Any
    ) -> DetailedUsageResponse: ...

    @overload
    def usage(
        self, *, country: str = "us", detailed: bool, **options: Any
    ) -> UsageResponse | DetailedUsageResponse: ...

    def usage(
        self, *, country: str = "us", detailed: bool = False, **options: Any
    ) -> UsageResponse | DetailedUsageResponse:
        """Retrieve ordinary or detailed usage statistics."""
        data = self.raw.usage(country=country, detailed=detailed, **options)
        if detailed:
            return _validate(DetailedUsageResponse, data)
        return _validate(UsageResponse, data)

    def report(
        self,
        comment: str | None = None,
        *,
        path: str | None = None,
        ll_uuid: str | None = None,
        details: Mapping[str, Any] | str | None = None,
    ) -> ReportResponse:
        """Submit a data issue and validate the acknowledgement."""
        return _validate(
            ReportResponse, self.raw.report(comment, path=path, ll_uuid=ll_uuid, details=details)
        )

    def tilejson(self, *, format: str = "mvt") -> TileJSON:
        """Retrieve typed tileset metadata."""
        return _validate(TileJSON, self.raw.tilejson(format=format))

    def tile(self, z: int, x: int, y: int, *, format: str = "mvt", retina: bool = False) -> bytes:
        """Retrieve unchanged tile bytes."""
        return self.raw.tile(z, x, y, format=format, retina=retina)

    def grid(
        self, z: int, x: int, y: int, *, metadata: Mapping[str, Any] | None = None
    ) -> UTFGridResponse:
        """Fetch and validate UTFGrid JSON discovered from raster TileJSON."""
        return _validate(UTFGridResponse, self.raw.grid(z, x, y, metadata=metadata))
