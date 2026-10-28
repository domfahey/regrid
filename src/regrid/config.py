"""Strict, credential-safe validation for transport and tile configuration."""

from typing import Annotated, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from .requests import safe_validate


class _StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)


class ClientSettings(_StrictModel):
    token: SecretStr | None = Field(default=None, repr=False)
    base_url: str = "https://app.regrid.com/api/v2"
    tiles_base_url: str = "https://tiles.regrid.com"
    timeout: Annotated[float, Field(gt=0, allow_inf_nan=False)] = 30
    default_limit: Annotated[int, Field(ge=1, le=1000)] = 5
    max_limit: Annotated[int, Field(ge=1, le=1000)] = 1000

    @field_validator("token")
    @classmethod
    def nonempty_token(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and not value.get_secret_value().strip():
            raise ValueError("token must not be empty")
        return value

    @field_validator("base_url", "tiles_base_url")
    @classmethod
    def https_url(cls, value: str) -> str:
        try:
            url = httpx.URL(value)
        except httpx.InvalidURL:
            raise ValueError("Invalid service URL") from None
        if (
            url.scheme != "https"
            or not url.host
            or url.query
            or url.fragment
            or url.username
            or url.password
        ):
            raise ValueError("Service URLs must be HTTPS without credentials, queries or fragments")
        return value.rstrip("/")

    @model_validator(mode="after")
    def limits(self) -> "ClientSettings":
        if self.default_limit > self.max_limit:
            raise ValueError("default_limit must not exceed max_limit")
        return self


class TileRequest(_StrictModel):
    z: Annotated[int, Field(ge=10, le=21)]
    x: Annotated[int, Field(ge=0)]
    y: Annotated[int, Field(ge=0)]
    format: Literal["mvt", "png"] = "mvt"
    retina: bool = False

    @model_validator(mode="after")
    def tile_bounds(self) -> "TileRequest":
        if self.x >= 2**self.z or self.y >= 2**self.z:
            raise ValueError("Tile coordinates exceed the zoom grid")
        if self.retina and self.format != "png":
            raise ValueError("Retina tiles require PNG")
        return self


class SearchLimit(_StrictModel):
    limit: Annotated[int, Field(ge=1, le=1000)]


def validate_limit(value: object, maximum: int) -> int:
    result = safe_validate(SearchLimit, {"limit": value}).limit
    if result > maximum:
        raise ValueError("Parcel limit exceeds configured maximum")
    return result
