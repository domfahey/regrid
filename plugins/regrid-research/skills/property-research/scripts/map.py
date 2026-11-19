"""Offline parcel geometry validation and area cross-checks. Never calls APIs or reads credentials."""

from __future__ import annotations

import math
from typing import Any

R = 6378137.0
SQFT_PER_SQM = 10.763910416709722
US_BOUNDS: tuple[tuple[float, float, float, float], ...] = (
    (-180.0, 17.5, -64.0, 72.0),
    (172.0, 51.0, 180.0, 53.5),
    (144.5, 13.0, 146.5, 21.0),
    (-171.2, -14.7, -168.0, -11.0),
)


class MapError(ValueError):
    """A diagnostic containing only fixed invariants."""


def load_features(document: object) -> list[dict]:
    if not isinstance(document, dict):
        raise MapError("Expected a Regrid parcel response with parcels.features")
    parcels = document.get("parcels")
    features = parcels.get("features") if isinstance(parcels, dict) else None
    if not isinstance(features, list):
        raise MapError("Expected a Regrid parcel response with parcels.features")
    if not features:
        raise MapError("Response contains no parcels")
    return features


def _finite_number(value: object) -> bool:
    return type(value) in {int, float} and math.isfinite(value)


def _validate_position(position: object) -> None:
    if not isinstance(position, list) or len(position) != 2:
        raise MapError("Geometry positions must be [longitude, latitude] pairs")
    if not all(_finite_number(value) for value in position):
        raise MapError("Geometry coordinates must be finite numbers")
    lon, lat = position
    if not any(
        west <= lon <= east and south <= lat <= north for west, south, east, north in US_BOUNDS
    ):
        raise MapError("Geometry lies outside the United States")


def _validate_ring(ring: object) -> None:
    if not isinstance(ring, list) or len(ring) < 4:
        raise MapError("Polygon rings need at least four positions")
    for position in ring:
        _validate_position(position)
    if ring[0] != ring[-1]:
        raise MapError("Polygon rings must be closed")


def _validate_polygon(polygon: object) -> None:
    if not isinstance(polygon, list) or not polygon:
        raise MapError("Invalid geometry coordinates")
    for ring in polygon:
        _validate_ring(ring)


def validate_geometry(geometry: object) -> None:
    if not isinstance(geometry, dict):
        raise MapError("Unsupported geometry type")
    kind = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if kind == "Polygon":
        _validate_polygon(coordinates)
    elif kind == "MultiPolygon":
        if not isinstance(coordinates, list) or not coordinates:
            raise MapError("Invalid geometry coordinates")
        for polygon in coordinates:
            _validate_polygon(polygon)
    else:
        raise MapError("Unsupported geometry type")


def _ring_area_m2(ring: list[list[float]]) -> float:
    total = 0.0
    for (lon1, lat1), (lon2, lat2) in zip(ring, ring[1:]):
        total += math.radians(lon2 - lon1) * (
            2 + math.sin(math.radians(lat1)) + math.sin(math.radians(lat2))
        )
    return abs(total) * R * R / 2


def _polygon_area_m2(polygon: list[list[list[float]]]) -> float:
    outer, *holes = polygon
    return _ring_area_m2(outer) - sum(_ring_area_m2(hole) for hole in holes)


def geometry_area_sqft(geometry: dict) -> float:
    polygons = (
        geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
    )
    return sum(_polygon_area_m2(polygon) for polygon in polygons) * SQFT_PER_SQM


def _recorded_sqft(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            return None
    if not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) and number > 0 else None


def area_check(feature: dict, tolerance: float = 0.05) -> dict[str, Any]:
    geometry = feature.get("geometry")
    fields = (feature.get("properties") or {}).get("fields") or {}
    recorded = _recorded_sqft(fields.get("ll_gissqft"))
    computed = None if geometry is None else geometry_area_sqft(geometry)
    if computed is None or recorded is None:
        return {
            "status": "unavailable",
            "computed_sqft": computed,
            "recorded_sqft": recorded,
            "ratio": None,
        }
    ratio = computed / recorded
    status = "ok" if abs(ratio - 1) <= tolerance else "mismatch"
    return {"status": status, "computed_sqft": computed, "recorded_sqft": recorded, "ratio": ratio}
