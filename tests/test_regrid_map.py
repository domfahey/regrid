"""Parcel geometry is validated offline and cross-checked against the recorded area."""

import importlib.util
import json
import math
import re
import subprocess
import sys
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


def write_response(path, *features):
    path.write_text(json.dumps({"parcels": {"features": list(features)}}), encoding="utf-8")
    return path


def good_feature(**fields):
    fields.setdefault("ll_gissqft", expected_sqft())
    return feature(square(), **fields)


def test_render_writes_page_and_summary(tmp_path):
    response = write_response(tmp_path / "r.json", good_feature(owner="Example LLC"))
    output = tmp_path / "map.html"
    summary = parcel_map.render(response, output)
    assert summary["features"] == 1
    assert summary["area_checks"][0]["status"] == "ok"
    assert summary["warnings"] == []
    html = output.read_text(encoding="utf-8")
    for needle in ("leaflet@1.9.4", 'integrity="sha256-', "World_Imagery", "Esri", "Example LLC"):
        assert needle in html


def test_page_has_no_token_and_only_allowed_hosts(tmp_path):
    response = write_response(tmp_path / "r.json", good_feature(owner="Example LLC"))
    output = tmp_path / "map.html"
    parcel_map.render(response, output)
    html = output.read_text(encoding="utf-8")
    hosts = set(re.findall(r"https?://([^/\"'\s]+)", html))
    assert hosts <= {"unpkg.com", "server.arcgisonline.com"}
    assert "token" not in html.lower()


def test_hostile_record_text_is_inert(tmp_path):
    hostile = "</script><img src=x onerror=alert(1)>\"'"
    response = write_response(tmp_path / "r.json", good_feature(owner=hostile))
    output = tmp_path / "map.html"
    parcel_map.render(response, output)
    html = output.read_text(encoding="utf-8")
    assert "</script><img" not in html
    assert "<img" not in html


def test_multiple_features_require_explicit_choice(tmp_path):
    second = feature(square(lon=-75.0, lat=39.95), ll_gissqft=expected_sqft(-75.0, 39.95))
    response = write_response(tmp_path / "r.json", good_feature(), second)
    with pytest.raises(MapError, match="--feature or --all-candidates"):
        parcel_map.render(response, tmp_path / "a.html")
    with pytest.raises(MapError):
        parcel_map.render(response, tmp_path / "b.html", index=5)
    single = parcel_map.render(response, tmp_path / "c.html", index=1)
    assert single["features"] == 1
    assert "Candidate 2" not in (tmp_path / "c.html").read_text(encoding="utf-8")
    both = parcel_map.render(response, tmp_path / "d.html", all_candidates=True)
    assert both["features"] == 2
    assert "Candidate 2" in (tmp_path / "d.html").read_text(encoding="utf-8")


def test_null_geometry_with_point_and_without(tmp_path):
    with_point = write_response(
        tmp_path / "p.json", feature(None, lat="39.9", lon="-75.03", owner="Example LLC")
    )
    output = tmp_path / "map.html"
    summary = parcel_map.render(with_point, output)
    assert summary["features"] == 1
    assert "No boundary on file for this parcel" in output.read_text(encoding="utf-8")

    without = write_response(tmp_path / "n.json", feature(None, owner="Example LLC"))
    with pytest.raises(MapError, match="no boundary"):
        parcel_map.render(without, tmp_path / "n.html")
    assert not (tmp_path / "n.html").exists()


def test_invalid_geometry_is_rejected_before_rendering(tmp_path):
    bad = feature({"type": "Point", "coordinates": [-75.03, 39.9]})
    with pytest.raises(MapError, match="Unsupported geometry"):
        parcel_map.render(write_response(tmp_path / "r.json", bad), tmp_path / "m.html")


def test_mismatch_adds_warning(tmp_path):
    response = write_response(tmp_path / "r.json", good_feature(ll_gissqft=1.0))
    output = tmp_path / "map.html"
    summary = parcel_map.render(response, output)
    assert summary["warnings"]
    html = output.read_text(encoding="utf-8")
    assert summary["warnings"][0] in html


def test_render_refuses_overwrite(tmp_path):
    response = write_response(tmp_path / "r.json", good_feature())
    output = tmp_path / "map.html"
    output.write_bytes(b"original")
    with pytest.raises(MapError, match="exists"):
        parcel_map.render(response, output)
    assert output.read_bytes() == b"original"
    parcel_map.render(response, output, replace=True)
    assert output.read_bytes() != b"original"
    assert [p.name for p in tmp_path.iterdir() if p.name.startswith(".")] == []


def test_cli_render_and_errors(tmp_path):
    response = write_response(tmp_path / "r.json", good_feature())
    output = tmp_path / "map.html"
    ok = subprocess.run(
        [sys.executable, str(SCRIPT), "render", str(response), str(output)],
        capture_output=True,
        text=True,
    )
    assert ok.returncode == 0
    assert json.loads(ok.stdout)["features"] == 1

    broken = tmp_path / "broken.json"
    broken.write_text("{not json")
    bad = subprocess.run(
        [sys.executable, str(SCRIPT), "render", str(broken), str(tmp_path / "x.html")],
        capture_output=True,
        text=True,
    )
    assert bad.returncode == 1
    assert bad.stdout == ""
    assert len(bad.stderr.strip().splitlines()) == 1
    assert "Traceback" not in bad.stderr
