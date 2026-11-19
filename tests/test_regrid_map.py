"""Parcel geometry is validated offline and cross-checked against the recorded area."""

import csv
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest
from map_fixtures import expected_sqft, feature, good_feature, square, write_response

from regrid.offline import map as parcel_map

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "plugins/regrid-research/skills/property-research/scripts/map.py"
)

MapError = parcel_map.MapError


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
    bad = _other({"type": "Point", "coordinates": [-75.03, 39.9]})
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


def test_footer_does_not_overlap_map_attribution(tmp_path):
    response = write_response(tmp_path / "r.json", good_feature())
    parcel_map.render(response, tmp_path / "m.html")
    html = (tmp_path / "m.html").read_text(encoding="utf-8")
    rule = re.search(r"footer\s*\{([^}]*)\}", html)
    assert rule
    assert "position" not in rule.group(1)
    assert "z-index" not in rule.group(1)
    assert html.index('<div id="map">') < html.index("<footer>")


def test_candidate_banner_names_the_candidate(tmp_path):
    null_point = feature(None, lat="39.9", lon="-75.03")
    response = write_response(tmp_path / "r.json", good_feature(), null_point)
    parcel_map.render(response, tmp_path / "m.html", all_candidates=True)
    html = (tmp_path / "m.html").read_text(encoding="utf-8")
    assert "Candidate 2: No boundary on file for this parcel" in html


def test_index_and_all_candidates_conflict(tmp_path):
    response = write_response(tmp_path / "r.json", good_feature(), good_feature())
    with pytest.raises(MapError, match="not both"):
        parcel_map.render(response, tmp_path / "m.html", index=0, all_candidates=True)


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions")
def test_output_respects_umask(tmp_path):
    response = write_response(tmp_path / "r.json", good_feature())
    old = os.umask(0o022)
    try:
        parcel_map.render(response, tmp_path / "m.html")
    finally:
        os.umask(old)
    assert stat.S_IMODE((tmp_path / "m.html").stat().st_mode) == 0o644


def test_extracted_map_helper_renders(tmp_path):
    from zipfile import ZipFile

    build_path = SCRIPT.parents[5] / "scripts/build_claude_plugins.py"
    spec = importlib.util.spec_from_file_location("map_test_builder", build_path)
    assert spec and spec.loader
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    archives = builder.build(SCRIPT.parents[3], tmp_path / "archives")
    with ZipFile(archives[-1]) as archive:
        archive.extractall(tmp_path / "extracted")
    helper = tmp_path / "extracted/property-research/scripts/map.py"
    response = write_response(tmp_path / "r.json", good_feature(owner="Example LLC"))
    output = tmp_path / "map.html"
    result = subprocess.run(
        [sys.executable, "-I", str(helper), "render", str(response), str(output)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert output.exists()
    assert json.loads(result.stdout)["features"] == 1


def test_skill_links_map_reference():
    skill = (SCRIPT.parents[1] / "SKILL.md").read_text(encoding="utf-8")
    guide = (SCRIPT.parents[1] / "references/map.md").read_text(encoding="utf-8")
    assert "references/map.md" in skill
    assert "scripts/map.py" in guide
    assert "--all-candidates" in guide
    assert "verbatim" in guide


def test_render_does_not_touch_process_umask(tmp_path, monkeypatch):
    def forbidden(*args):
        raise AssertionError("os.umask must not be called")

    monkeypatch.setattr(parcel_map.os, "umask", forbidden)
    response = write_response(tmp_path / "r.json", good_feature())
    parcel_map.render(response, tmp_path / "m.html")
    assert (tmp_path / "m.html").exists()


def test_single_feature_all_candidates_is_labelled_candidate(tmp_path):
    response = write_response(tmp_path / "r.json", good_feature())
    parcel_map.render(response, tmp_path / "m.html", all_candidates=True)
    assert "Candidate 1" in (tmp_path / "m.html").read_text(encoding="utf-8")
    parcel_map.render(response, tmp_path / "n.html")
    assert "Candidate" not in (tmp_path / "n.html").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "properties",
    ["x", {"fields": [1]}, {"fields": "x"}, [1]],
)
def test_malformed_properties_do_not_traceback(tmp_path, properties):
    bad = {"type": "Feature", "geometry": square(), "properties": properties}
    assert parcel_map.area_check(bad)["status"] == "unavailable"
    response = write_response(tmp_path / "r.json", bad)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "render", str(response), str(tmp_path / "m.html")],
        capture_output=True,
        text=True,
    )
    assert "Traceback" not in result.stderr


def test_missing_fact_renders_not_in_record(tmp_path):
    response = write_response(tmp_path / "r.json", good_feature())
    parcel_map.render(response, tmp_path / "m.html")
    assert "not in record" in (tmp_path / "m.html").read_text(encoding="utf-8")


def test_mismatch_is_named_in_warning_and_guide(tmp_path):
    response = write_response(tmp_path / "r.json", good_feature(ll_gissqft=1.0))
    summary = parcel_map.render(response, tmp_path / "m.html")
    assert "mismatch" in summary["warnings"][0].lower()
    guide = (SCRIPT.parents[1] / "references/map.md").read_text(encoding="utf-8")
    assert "area_checks" in guide


def test_missing_geometry_field_is_rejected(tmp_path):
    bare = feature(None, lat="39.9", lon="-75.03")
    del bare["geometry"]
    with pytest.raises(MapError, match="omits geometry"):
        parcel_map.render(write_response(tmp_path / "r.json", bare), tmp_path / "m.html")
    assert not (tmp_path / "m.html").exists()


def test_skill_keeps_geometry_when_mapping():
    skill = (SCRIPT.parents[1] / "SKILL.md").read_text(encoding="utf-8")
    guide = (SCRIPT.parents[1] / "references/map.md").read_text(encoding="utf-8")
    assert "return_geometry=true" in skill and "return_geometry=true" in guide
    assert "stop and report it as an open risk" not in guide


@pytest.mark.parametrize(("lon", "lat"), [(-114.07, 51.05), (-99.13, 19.43)])  # Calgary, CDMX
def test_bounds_reject_canada_and_mexico(lon, lat):
    with pytest.raises(MapError, match="outside the United States"):
        parcel_map.validate_geometry(square(lon=lon, lat=lat))


def test_non_us_path_is_rejected(tmp_path):
    toronto = feature(square(lon=-79.4, lat=43.7))
    toronto["properties"]["path"] = "/ca/on/toronto/1"
    with pytest.raises(MapError, match="outside the United States"):
        parcel_map.render(write_response(tmp_path / "r.json", toronto), tmp_path / "m.html")


def test_positions_with_altitude_are_accepted(tmp_path):
    geometry = square()
    geometry["coordinates"][0] = [[*p, 12.5] for p in geometry["coordinates"][0]]
    parcel_map.validate_geometry(geometry)
    assert parcel_map.geometry_area_sqft(geometry) == pytest.approx(expected_sqft(), rel=1e-6)
    response = write_response(tmp_path / "r.json", feature(geometry, ll_gissqft=expected_sqft()))
    assert parcel_map.render(response, tmp_path / "m.html")["warnings"] == []


def test_antimeridian_ring_area_and_display(tmp_path):
    ring = [[179.95, 52.0], [-179.95, 52.0], [-179.95, 52.1], [179.95, 52.1], [179.95, 52.0]]
    geometry = {"type": "Polygon", "coordinates": [ring]}
    parcel_map.validate_geometry(geometry)
    expected = expected_sqft(lon=179.95, lat=52.0, size=0.1)
    assert parcel_map.geometry_area_sqft(geometry) == pytest.approx(expected, rel=1e-3)
    response = write_response(tmp_path / "r.json", feature(geometry, ll_gissqft=expected))
    parcel_map.render(response, tmp_path / "m.html")
    page = (tmp_path / "m.html").read_text(encoding="utf-8")
    data = json.loads(re.search(r'id="parcel-data">(.*?)</script>', page, re.S).group(1))
    lons = [p[0] for p in data[0]["geometry"]["coordinates"][0]]
    assert max(lons) - min(lons) < 1


def test_no_replace_never_overwrites_a_file_created_after_the_check(tmp_path, monkeypatch):
    output = tmp_path / "m.html"
    output.write_text("keep", encoding="utf-8")
    monkeypatch.setattr(parcel_map.os.path, "lexists", lambda path: False)
    with pytest.raises(MapError, match="exists"):
        parcel_map.render(write_response(tmp_path / "r.json", good_feature()), output)
    assert output.read_text(encoding="utf-8") == "keep"
    assert [p.name for p in tmp_path.iterdir() if p.name.startswith(".map-")] == []


def test_main_prints_summary_json(tmp_path, capsys):
    response = write_response(tmp_path / "r.json", good_feature())
    assert parcel_map.main(["render", str(response), str(tmp_path / "m.html")]) == 0
    assert json.loads(capsys.readouterr().out)["features"] == 1


def test_main_reports_map_error_on_one_line(tmp_path, capsys):
    response = write_response(tmp_path / "r.json", good_feature(), good_feature())
    assert parcel_map.main(["render", str(response), str(tmp_path / "m.html")]) == 1
    err = capsys.readouterr().err
    assert err.startswith("error: ") and err.count("\n") == 1


def test_main_reports_os_error(tmp_path, capsys):
    assert (
        parcel_map.main(["render", str(tmp_path / "missing.json"), str(tmp_path / "m.html")]) == 1
    )
    assert capsys.readouterr().err.startswith("error: ")


def _render_doc(tmp_path, document):
    response = tmp_path / "r.json"
    response.write_text(
        document if isinstance(document, str) else json.dumps(document), encoding="utf-8"
    )
    return parcel_map.render(response, tmp_path / "m.html")


def test_render_rejects_invalid_json_and_non_object_features(tmp_path):
    with pytest.raises(MapError, match="not valid JSON"):
        _render_doc(tmp_path, "{nope")
    with pytest.raises(MapError, match="Expected a Regrid parcel response"):
        _render_doc(tmp_path, {"parcels": {"features": [1]}})


@pytest.mark.parametrize(
    "geometry",
    [
        "x",
        {"type": "MultiPolygon", "coordinates": []},
        {"type": "Polygon", "coordinates": [[[1], [2, 3], [4, 5], [1]]]},
        {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [float("nan"), 1], [0, 0]]]},
    ],
)
def test_render_rejects_bad_geometry(tmp_path, geometry):
    with pytest.raises(MapError):
        _render_doc(tmp_path, {"parcels": {"features": [feature(geometry)]}})


def test_render_accepts_numeric_string_area(tmp_path):
    doc = {"parcels": {"features": [good_feature(ll_gissqft=str(expected_sqft()))]}}
    assert _render_doc(tmp_path, doc)["area_checks"][0]["status"] == "ok"
    assert parcel_map._parse_finite("abc") is None


def test_write_falls_back_without_hard_links(tmp_path, monkeypatch):
    def no_link(*args, **kwargs):
        raise OSError("links unsupported")

    monkeypatch.setattr(os, "link", no_link)
    response = write_response(tmp_path / "r.json", good_feature())
    parcel_map.render(response, tmp_path / "m.html")
    assert (tmp_path / "m.html").exists()
    with pytest.raises(MapError, match="exists"):
        parcel_map.render(response, tmp_path / "m.html")


def test_temp_name_collision_is_retried(tmp_path, monkeypatch):
    names = iter(["aa", "aa", "bb"])
    monkeypatch.setattr(parcel_map.secrets, "token_hex", lambda n: next(names))
    (tmp_path / ".map-aa.tmp").write_bytes(b"")
    response = write_response(tmp_path / "r.json", good_feature())
    parcel_map.render(response, tmp_path / "m.html")
    assert (tmp_path / "m.html").exists()


def test_module_runs_as_script(tmp_path):
    import subprocess

    response = write_response(tmp_path / "r.json", good_feature())
    proc = subprocess.run(
        [sys.executable, "-W", "error", "-m", "regrid.offline.map", "render", str(response)]
        + [str(tmp_path / "m.html")],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "m.html").exists()


def _other(geometry, n=2, **fields):
    """A neighbour: the fixture feature with a different ll_uuid than the subject."""
    item = feature(geometry, **fields)
    item["properties"]["ll_uuid"] = f"00000000-0000-4000-8000-00000000000{n}"
    return item


def _page_blocks(page_path):
    page = page_path.read_text(encoding="utf-8")
    blocks = {}
    for name in ("parcel-data", "neighbour-data"):
        match = re.search(rf'<script type="application/json" id="{name}">(.*?)</script>', page)
        blocks[name] = None if match is None else match.group(1)
    return page, blocks


def test_neighbours_drawn_and_subject_excluded(tmp_path):
    subject = good_feature()
    others = [_other(square(lon=-75.0289, lat=39.9)), subject]
    response = write_response(tmp_path / "r.json", subject)
    near = write_response(tmp_path / "n.json", *others)
    summary = parcel_map.render(response, tmp_path / "m.html", neighbours_path=near)
    assert summary["neighbours"] == 1 and summary["features"] == 1
    assert len(summary["area_checks"]) == 1
    _, blocks = _page_blocks(tmp_path / "m.html")
    assert len(json.loads(blocks["neighbour-data"])) == 1


def test_bad_neighbour_is_skipped_with_warning(tmp_path):
    bad = _other({"type": "Point", "coordinates": [-75.03, 39.9]})
    response = write_response(tmp_path / "r.json", good_feature())
    near = write_response(tmp_path / "n.json", bad)
    summary = parcel_map.render(response, tmp_path / "m.html", neighbours_path=near)
    assert summary["neighbours"] == 0 and summary["warnings"][0].startswith("Neighbour 0 skipped")


def test_neighbour_data_is_escaped_and_styled(tmp_path):
    hostile = _other(square(lon=-75.0289), owner="</script><b>&x")
    response = write_response(tmp_path / "r.json", good_feature())
    near = write_response(tmp_path / "n.json", hostile)
    parcel_map.render(response, tmp_path / "m.html", neighbours_path=near)
    page, blocks = _page_blocks(tmp_path / "m.html")
    raw = blocks["neighbour-data"]
    assert "<" not in raw and ">" not in raw and "&" not in raw
    assert '"#ffffff"' in page and "fillOpacity: 0.05" in page


def test_no_neighbours_keeps_summary_and_page_compatible(tmp_path):
    response = write_response(tmp_path / "r.json", good_feature())
    summary = parcel_map.render(response, tmp_path / "m.html")
    assert summary["neighbours"] == 0
    _, blocks = _page_blocks(tmp_path / "m.html")
    assert json.loads(blocks["neighbour-data"]) == []


def test_non_feature_neighbour_entries_and_bad_file(tmp_path):
    response = write_response(tmp_path / "r.json", good_feature())
    near = tmp_path / "n.json"
    near.write_text(json.dumps({"parcels": {"features": ["x", None]}}), encoding="utf-8")
    summary = parcel_map.render(response, tmp_path / "m.html", neighbours_path=near)
    assert summary["neighbours"] == 0 and len(summary["warnings"]) == 2
    near.write_text("not json", encoding="utf-8")
    summary = parcel_map.render(response, tmp_path / "m2.html", neighbours_path=near)
    assert summary["features"] == 1 and summary["neighbours"] == 0
    assert summary["warnings"] == ["Neighbours skipped: Neighbours file is not valid JSON"]
    assert (tmp_path / "m2.html").exists()
    near.write_text("{}", encoding="utf-8")
    summary = parcel_map.render(response, tmp_path / "m3.html", neighbours_path=near)
    assert summary["warnings"][0].startswith("Neighbours skipped: Expected a Regrid")


def test_missing_neighbours_file_keeps_subject_map(tmp_path):
    response = write_response(tmp_path / "r.json", good_feature())
    summary = parcel_map.render(
        response, tmp_path / "m.html", neighbours_path=tmp_path / "absent.json"
    )
    assert summary["features"] == 1 and summary["neighbours"] == 0
    assert len(summary["warnings"]) == 1
    assert summary["warnings"][0].startswith("Neighbours skipped: ")
    assert "\n" not in summary["warnings"][0]


def test_neighbours_cli_flag_from_extracted_skill(tmp_path):
    from zipfile import ZipFile

    build_path = SCRIPT.parents[5] / "scripts/build_claude_plugins.py"
    spec = importlib.util.spec_from_file_location("map_test_builder_nb", build_path)
    assert spec and spec.loader
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    archives = builder.build(SCRIPT.parents[3], tmp_path / "archives")
    with ZipFile(archives[-1]) as archive:
        archive.extractall(tmp_path / "extracted")
    helper = tmp_path / "extracted/property-research/scripts/map.py"
    response = write_response(tmp_path / "r.json", good_feature())
    near = write_response(tmp_path / "n.json", _other(square(lon=-75.0289)))
    output = tmp_path / "map.html"
    result = subprocess.run(
        [sys.executable, "-I", str(helper), "render", str(response), str(output)]
        + ["--neighbours", str(near)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["neighbours"] == 1


CORE_COLUMNS = [
    "headline",
    "path",
    "ll_uuid",
    "owner",
    "parcelnumb",
    "ll_last_refresh",
    "ll_gisacre",
    "ll_gissqft",
    "lat",
    "lon",
]


def _rows(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.reader(handle))


def test_csv_core_columns_and_formula_guard(tmp_path):
    f = good_feature(owner='=HYPERLINK("x")', parcelnumb='1,2 "q"\nz', lat="39.9", lon="-75.03")
    summary = parcel_map.export(write_response(tmp_path / "r.json", f), csv_path=tmp_path / "o.csv")
    raw = (tmp_path / "o.csv").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf") and b"\r\n" in raw
    rows = _rows(tmp_path / "o.csv")
    rows[0][0] = rows[0][0].lstrip("\ufeff")
    assert rows[0] == CORE_COLUMNS
    assert rows[1][3] == '\'=HYPERLINK("x")' and rows[1][4] == '1,2 "q"\nz'
    assert rows[1][5] == "" and rows[1][9] == "-75.03"
    assert summary == {
        "features": 1,
        "csv": str(tmp_path / "o.csv"),
        "geojson": None,
        "columns": CORE_COLUMNS,
    }


def test_all_fields_appends_sorted(tmp_path):
    f = good_feature(zeta="z", alpha={"a": 1}, owner="O", flag=True, nothing=None)
    summary = parcel_map.export(
        write_response(tmp_path / "r.json", f), csv_path=tmp_path / "o.csv", all_fields=True
    )
    rows = _rows(tmp_path / "o.csv")
    extras = ["alpha", "flag", "ll_gissqft", "nothing", "zeta"]
    extras = [name for name in extras if name not in CORE_COLUMNS]
    assert summary["columns"] == CORE_COLUMNS + extras
    assert rows[0][1:] == (CORE_COLUMNS + extras)[1:]
    record = dict(zip(summary["columns"], rows[1]))
    assert record["alpha"] == '{"a": 1}' and record["flag"] == "True" and record["nothing"] == ""


def test_geojson_keeps_geometry_verbatim(tmp_path):
    f = good_feature(owner="=X")
    parcel_map.export(write_response(tmp_path / "r.json", f), geojson_path=tmp_path / "o.geojson")
    out = json.loads((tmp_path / "o.geojson").read_text())
    assert out["type"] == "FeatureCollection" and out["features"][0]["geometry"] == f["geometry"]
    props = out["features"][0]["properties"]
    assert (
        list(props) == CORE_COLUMNS and props["owner"] == "=X" and props["ll_last_refresh"] is None
    )


def test_export_requires_an_output(tmp_path):
    response = write_response(tmp_path / "r.json", good_feature())
    with pytest.raises(MapError, match="Choose --csv and/or --geojson"):
        parcel_map.export(response)


def test_export_refuses_overwrite_and_invalid_before_writing(tmp_path):
    response = write_response(tmp_path / "r.json", good_feature())
    existing = tmp_path / "o.csv"
    existing.write_text("keep")
    with pytest.raises(MapError, match="--replace"):
        parcel_map.export(response, csv_path=existing, geojson_path=tmp_path / "o.geojson")
    assert existing.read_text() == "keep" and not (tmp_path / "o.geojson").exists()
    parcel_map.export(response, csv_path=existing, replace=True)
    assert existing.read_bytes().startswith(b"\xef\xbb\xbf")

    same = tmp_path / "same"
    with pytest.raises(MapError, match="different files"):
        parcel_map.export(response, csv_path=same, geojson_path=same)

    bad = good_feature()
    bad["properties"]["path"] = "/ca/on/x"
    outside = good_feature()
    outside["geometry"] = square(lon=-100.0, lat=60.0)  # not in any US box
    broken = good_feature()
    broken["geometry"] = {"type": "Point", "coordinates": [-75, 39.9]}
    for number, invalid in enumerate((bad, outside, broken)):
        r = write_response(tmp_path / f"bad{number}.json", good_feature(), invalid)
        with pytest.raises(MapError):
            parcel_map.export(
                r, csv_path=tmp_path / f"b{number}.csv", geojson_path=tmp_path / f"b{number}.gj"
            )
        assert not (tmp_path / f"b{number}.csv").exists()
        assert not (tmp_path / f"b{number}.gj").exists()


def test_export_geometry_requirements(tmp_path):
    null_geo = good_feature()
    null_geo["geometry"] = None
    r = write_response(tmp_path / "n.json", null_geo)
    parcel_map.export(r, csv_path=tmp_path / "n.csv")  # CSV needs no boundary
    parcel_map.export(r, geojson_path=tmp_path / "n.geojson")
    assert json.loads((tmp_path / "n.geojson").read_text())["features"][0]["geometry"] is None
    omitted = good_feature()
    del omitted["geometry"]
    r = write_response(tmp_path / "o.json", omitted)
    parcel_map.export(r, csv_path=tmp_path / "o.csv")
    with pytest.raises(MapError, match="omits geometry"):
        parcel_map.export(r, geojson_path=tmp_path / "o.geojson")
    r = write_response(tmp_path / "x.json", "not a feature")
    with pytest.raises(MapError, match="Expected a Regrid parcel response"):
        parcel_map.export(r, csv_path=tmp_path / "x.csv")
    (tmp_path / "junk.json").write_text("{")
    with pytest.raises(MapError, match="not valid JSON"):
        parcel_map.export(tmp_path / "junk.json", csv_path=tmp_path / "j.csv")


def test_export_main_subcommand(tmp_path, capsys):
    response = write_response(tmp_path / "r.json", good_feature())
    args = ["export", str(response), "--csv", str(tmp_path / "o.csv"), "--all-fields"]
    assert parcel_map.main(args) == 0
    assert json.loads(capsys.readouterr().out)["features"] == 1
    assert parcel_map.main(["export", str(response)]) == 1
    assert "Choose --csv and/or --geojson" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("-75.03", "-75.03"),
        ("-1e3", "-1e3"),
        (-75.03, "-75.03"),
        ("+.5", "+.5"),
        ("-SUM(A1)", "'-SUM(A1)"),
        ("+1-2", "'+1-2"),
        ("\t=x", "'\t=x"),
        ("\r=x", "'\r=x"),
        ("=1", "'=1"),
        ("@a", "'@a"),
        ("-nan", "'-nan"),
        ("-1e999", "'-1e999"),
    ],
)
def test_csv_cell_numbers_unprefixed(value, expected):
    assert parcel_map._csv_cell(value) == expected


def test_export_precheck_leaves_no_partial_csv(tmp_path):
    response = write_response(tmp_path / "r.json", good_feature())
    csv_target = tmp_path / "o.csv"
    with pytest.raises(MapError, match="directory"):
        parcel_map.export(
            response, csv_path=csv_target, geojson_path=tmp_path / "missing" / "o.geojson"
        )
    assert not csv_target.exists()
    with pytest.raises(MapError, match="different files"):
        parcel_map.export(
            response, csv_path=tmp_path / "x.csv", geojson_path=tmp_path / "sub" / ".." / "x.csv"
        )
    assert not (tmp_path / "x.csv").exists()


def test_export_all_fields_header_is_formula_guarded(tmp_path):
    response = write_response(tmp_path / "r.json", good_feature(**{"=cmd": "x", "plain": "y"}))
    out = tmp_path / "o.csv"
    parcel_map.export(response, csv_path=out, all_fields=True)
    header = next(csv.reader(out.read_text(encoding="utf-8-sig").splitlines()))
    assert "'=cmd" in header and "=cmd" not in header and "plain" in header


def test_export_non_finite_reports_one_line_and_writes_nothing(tmp_path, capsys):
    response = tmp_path / "r.json"
    response.write_text(
        '{"parcels":{"features":[{"type":"Feature","geometry":null,'
        '"properties":{"path":"/us/nj/x","headline":NaN,"fields":{}}}]}}',
        encoding="utf-8",
    )
    gj = tmp_path / "o.geojson"
    csv_out = tmp_path / "o.csv"
    assert (
        parcel_map.main(["export", str(response), "--csv", str(csv_out), "--geojson", str(gj)]) == 1
    )
    err = capsys.readouterr().err
    assert err.startswith("error: ") and err.count("\n") == 1 and "Traceback" not in err
    assert not gj.exists() and not csv_out.exists()


@pytest.mark.parametrize("replace", [False, True])
def test_export_refuses_output_equal_to_response(tmp_path, replace):
    response = write_response(tmp_path / "r.json", good_feature())
    before = response.read_text()
    alias = tmp_path / "sub" / ".." / "r.json"
    (tmp_path / "sub").mkdir()
    with pytest.raises(MapError, match="response"):
        parcel_map.export(response, csv_path=alias, replace=replace)
    with pytest.raises(MapError, match="response"):
        parcel_map.export(response, geojson_path=response, replace=replace)
    assert response.read_text() == before
