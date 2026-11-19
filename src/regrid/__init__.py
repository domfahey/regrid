"""Regrid Parcel and Tileserver API client."""

from .client import (
    AuthenticationError,
    RegridClient,
    RegridDecodeError,
    RegridError,
    RegridHTTPError,
)
from .endpoints import QueryPagingError
from .typed import TypedRegridClient

__all__ = [
    "RegridClient",
    "TypedRegridClient",
    "RegridError",
    "RegridHTTPError",
    "AuthenticationError",
    "RegridDecodeError",
    "QueryPagingError",
]
__version__ = "0.4.1"
