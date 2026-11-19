"""Parcel geometry is validated offline and cross-checked against the recorded area."""

import importlib.util
import math
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "plugins/regrid-research/skills/property-research/scripts/map.py"
)
SPEC = importlib.util.spec_from_file_location("regrid_map", SCRIPT)
assert SPEC and SPEC.loader
parcel_map = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(parcel_map)

MapError = parcel_map.MapError


def square(lon=-75.03, lat=39.9, size=0.001):
    ring = [[lon, lat], [lon + size, lat], [lon + size, lat + size], [lon, lat + size], [lon, lat]]
    return {"type": "Polygon", "coordinates": [ring]}


def expected_sqft(lon=-75.03, lat=39.9, size=0.001):
    r = 6378137.0
    m2 = (
        r
        * r
        * math.radians(size)
        * (math.sin(math.radians(lat + size)) - math.sin(math.radians(lat)))
    )
    return m2 * 10.763910416709722


def feature(geometry, **fields):
    return {
        "type": "Feature",
        "geometry": geometry,
        "properties": {
            "headline": "12 Example Ave",
            "path": "/us/nj/camden/haddonfield/1",
            "ll_uuid": "00000000-0000-4000-8000-000000000001",
            "fields": fields,
        },
    }


@pytest.mark.parametrize("document", [{}, [], {"parcels": {}}])
def test_load_features_rejects_non_response(document):
    with pytest.raises(MapError, match="Expected a Regrid parcel response"):
        parcel_map.load_features(document)


def test_load_features_rejects_empty_response():
    with pytest.raises(MapError, match="no parcels"):
        parcel_map.load_features({"parcels": {"features": []}})


def test_square_area_matches_spherical_formula():
    actual = parcel_map.geometry_area_sqft(square())
    assert abs(actual - expected_sqft()) / expected_sqft() < 1e-6


def test_hole_and_multipolygon_area():
    outer = square()
    hole = square(lon=-75.03 + 0.00025, lat=39.9 + 0.00025, size=0.0005)["coordinates"][0]
    with_hole = {"type": "Polygon", "coordinates": [outer["coordinates"][0], hole]}
    hole_area = expected_sqft(lat=39.90025, size=0.0005)
    reduced = parcel_map.geometry_area_sqft(with_hole)
    assert abs((expected_sqft() - hole_area) - reduced) / reduced < 1e-6

    second = square(lon=-75.0, lat=39.95)
    multi = {"type": "MultiPolygon", "coordinates": [outer["coordinates"], second["coordinates"]]}
    total = parcel_map.geometry_area_sqft(multi)
    expected_total = expected_sqft() + expected_sqft(lon=-75.0, lat=39.95)
    assert abs(total - expected_total) / total < 1e-6


@pytest.mark.parametrize(
    "geometry",
    [
        {"type": "Point", "coordinates": [-75.03, 39.9]},
        {
            "type": "Polygon",
            "coordinates": [[[-75.03, 39.9], [-75.029, 39.9], [-75.029, 39.901], [-75.03, 39.901]]],
        },
        {"type": "Polygon", "coordinates": [[[-75.03, 39.9], [-75.029, 39.9], [-75.03, 39.9]]]},
        {
            "type": "Polygon",
            "coordinates": [[[-75.03, 39.9], ["nan", 39.9], [-75.029, 39.901], [-75.03, 39.9]]],
        },
        {
            "type": "Polygon",
            "coordinates": [
                [[-75.03, 39.9], [float("inf"), 39.9], [-75.029, 39.901], [-75.03, 39.9]]
            ],
        },
        {
            "type": "Polygon",
            "coordinates": [[[-75.03, 39.9], ["-75.029", 39.9], [-75.029, 39.901], [-75.03, 39.9]]],
        },
        {"type": "Polygon", "coordinates": None},
    ],
)
def test_validate_geometry_rejects_malformed(geometry):
    with pytest.raises(MapError):
        parcel_map.validate_geometry(geometry)


def test_validate_geometry_rejects_non_us():
    with pytest.raises(MapError, match="outside the United States"):
        parcel_map.validate_geometry(square(lon=2.35, lat=48.85))


@pytest.mark.parametrize(
    ("lon", "lat"),
    [
        (-66.1, 18.4),  # Puerto Rico
        (-157.9, 21.3),  # Hawaii
        (-149.9, 61.2),  # Alaska
        (173.2, 52.8),  # Aleutians
        (144.75, 13.45),  # Guam
        (-170.7, -14.3),  # American Samoa
    ],
)
def test_us_bounds_accept_territories_and_aleutians(lon, lat):
    parcel_map.validate_geometry(square(lon=lon, lat=lat))


def test_area_check_ok_mismatch_unavailable():
    ok = parcel_map.area_check(feature(square(), ll_gissqft=expected_sqft()))
    assert ok["status"] == "ok"
    assert ok["computed_sqft"] == pytest.approx(expected_sqft())
    assert ok["recorded_sqft"] == pytest.approx(expected_sqft())
    assert ok["ratio"] == pytest.approx(1.0)

    as_text = parcel_map.area_check(feature(square(), ll_gissqft=str(expected_sqft())))
    assert as_text["status"] == "ok"

    missing = parcel_map.area_check(feature(square()))
    assert missing["status"] == "unavailable"
    assert missing["recorded_sqft"] is None

    no_geometry = parcel_map.area_check(feature(None, ll_gissqft=expected_sqft()))
    assert no_geometry["status"] == "unavailable"
    assert no_geometry["computed_sqft"] is None


def test_area_check_flags_mismatch():
    corrupted = square()
    corrupted["coordinates"][0][2][1] = 39.911  # ring stays closed: only index 2 changes
    result = parcel_map.area_check(feature(corrupted, ll_gissqft=expected_sqft()))
    assert result["status"] == "mismatch"


def test_oversized_integer_coordinates_raise_map_error():
    huge = 10**400
    geometry = {
        "type": "Polygon",
        "coordinates": [[[-75.03, 39.9], [huge, 39.9], [-75.029, 39.901], [-75.03, 39.9]]],
    }
    with pytest.raises(MapError, match="finite numbers"):
        parcel_map.validate_geometry(geometry)


def test_oversized_integer_recorded_area_is_unavailable():
    result = parcel_map.area_check(feature(square(), ll_gissqft=10**400))
    assert result["status"] == "unavailable"
    assert result["recorded_sqft"] is None
