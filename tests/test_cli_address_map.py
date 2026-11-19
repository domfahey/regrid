import json

import httpx
import pytest
from map_fixtures import good_feature

import regrid.offline.map
from regrid import cli
from regrid.client import RegridClient


def _install(monkeypatch, handler):
    seen = []

    def handle(request):
        seen.append(request)
        return handler(request)

    monkeypatch.setenv("REGRID_TOKEN", "secret")
    monkeypatch.setattr(
        cli, "RegridClient", lambda **kw: RegridClient(**kw, transport=httpx.MockTransport(handle))
    )
    return seen


@pytest.fixture
def seen(monkeypatch):
    body = {"parcels": {"features": [good_feature()]}}
    return _install(monkeypatch, lambda request: httpx.Response(200, json=body))


@pytest.fixture
def failing_401(monkeypatch):
    return _install(monkeypatch, lambda request: httpx.Response(401, text="secret private-address"))


@pytest.fixture
def empty_response(monkeypatch):
    body = {"parcels": {"features": []}}
    return _install(monkeypatch, lambda request: httpx.Response(200, json=body))


def test_address_map_one_request_exact_params(tmp_path, seen, capsys):
    out = tmp_path / "m.html"
    assert cli.main(["address-map", "12 Example Ave", str(out), "--path", "/us/nj/camden"]) == 0
    assert len(seen) == 1 and seen[0].url.path == "/api/v2/parcels/address"
    params = dict(seen[0].url.params)
    params.pop("token")
    assert params == {
        "query": "12 Example Ave",
        "limit": "1",
        "path": "/us/nj/camden",
        "return_parcels": "true",
        "return_stacked": "false",
        "return_zoning": "false",
        "return_matched_buildings": "false",
        "return_matched_addresses": "false",
        "return_enhanced_ownership": "false",
    }
    captured = capsys.readouterr()
    assert "regrid: requests made: 1" in captured.err
    summary = json.loads(captured.out)
    assert summary["response"] == str(tmp_path / "m.json") and out.exists()
    assert "secret" not in out.read_text(encoding="utf-8") + (tmp_path / "m.json").read_text()


def test_existing_output_refuses_before_request(tmp_path, seen, capsys):
    (tmp_path / "m.json").write_text("keep")
    assert cli.main(["address-map", "x", str(tmp_path / "m.html")]) == 1
    assert seen == [] and "requests made: 0" in capsys.readouterr().err
    assert (tmp_path / "m.json").read_text() == "keep"


def test_existing_html_refuses_before_request(tmp_path, seen, capsys):
    (tmp_path / "m.html").write_text("keep")
    assert cli.main(["address-map", "x", str(tmp_path / "m.html")]) == 1
    assert seen == [] and "requests made: 0" in capsys.readouterr().err


def test_same_response_and_output_refused(tmp_path, seen, capsys):
    assert cli.main(["address-map", "x", str(tmp_path / "m.json")]) == 1
    assert seen == [] and "different files" in capsys.readouterr().err


def test_replace_overwrites_and_custom_response_path(tmp_path, seen, capsys):
    (tmp_path / "m.html").write_text("old")
    (tmp_path / "r.json").write_text("old")
    argv = [
        "address-map",
        "x",
        str(tmp_path / "m.html"),
        "--save-response",
        str(tmp_path / "r.json"),
    ]
    argv += ["--replace", "--retrieved-at", "2026-01-02T03:04:05Z"]
    assert cli.main(argv) == 0
    assert "2026-01-02T03:04:05Z" in (tmp_path / "m.html").read_text()
    assert json.loads((tmp_path / "r.json").read_text())["parcels"]
    assert json.loads(capsys.readouterr().out)["response"] == str(tmp_path / "r.json")


def test_default_retrieved_at_is_utc_timestamp(tmp_path, seen):
    import re

    cli.main(["address-map", "x", str(tmp_path / "m.html")])
    assert re.search(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", (tmp_path / "m.html").read_text())


def test_api_error_writes_no_page_and_hides_secrets(tmp_path, failing_401, capsys):
    assert cli.main(["address-map", "private-address", str(tmp_path / "m.html")]) == 1
    err = capsys.readouterr().err
    assert "requests made: 1" in err and "secret" not in err and "private-address" not in err
    assert err.index("requests made") < err.index("regrid:", err.index("requests made") + 1)
    assert not (tmp_path / "m.html").exists()


def test_empty_result_keeps_response_and_fails(tmp_path, empty_response, capsys):
    assert cli.main(["address-map", "x", str(tmp_path / "m.html")]) == 1
    assert (tmp_path / "m.json").exists() and not (tmp_path / "m.html").exists()
    assert "Response contains no parcels" in capsys.readouterr().err


def test_missing_token_makes_no_request(tmp_path, seen, monkeypatch, capsys):
    monkeypatch.delenv("REGRID_TOKEN")
    assert cli.main(["address-map", "x", str(tmp_path / "m.html")]) == 1
    assert seen == [] and "requests made: 0" in capsys.readouterr().err


def test_missing_output_directory_refuses_before_request(tmp_path, seen, capsys):
    assert cli.main(["address-map", "x", str(tmp_path / "no" / "dir" / "m.html")]) == 1
    err = capsys.readouterr().err
    assert seen == [] and "requests made: 0" in err and "directory does not exist" in err


def test_missing_response_directory_refuses_before_request(tmp_path, seen, capsys):
    argv = [
        "address-map",
        "x",
        str(tmp_path / "m.html"),
        "--save-response",
        str(tmp_path / "n/r.json"),
    ]
    assert cli.main(argv) == 1
    assert seen == [] and "requests made: 0" in capsys.readouterr().err


def test_same_file_via_relative_spelling_refused(tmp_path, seen, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "m.json").write_text("keep")
    argv = ["address-map", "x", "m.json", "--save-response", str(tmp_path / "m.json"), "--replace"]
    assert cli.main(argv) == 1
    assert seen == [] and "different files" in capsys.readouterr().err
    assert (tmp_path / "m.json").read_text() == "keep"


def test_render_failure_reports_saved_response(tmp_path, empty_response, capsys):
    assert cli.main(["address-map", "x", str(tmp_path / "m.html")]) == 1
    err = capsys.readouterr().err
    saved = f"regrid: response saved to {tmp_path / 'm.json'}"
    assert err.index("requests made") < err.index(saved) < err.index("no parcels")


def test_type_error_is_sanitized(tmp_path, seen, monkeypatch, capsys):
    def boom(*a, **k):
        raise TypeError("secret private-address")

    monkeypatch.setattr(cli.parcel_map, "render", boom)
    assert cli.main(["address-map", "x", str(tmp_path / "m.html")]) == 1
    err = capsys.readouterr().err
    assert "Invalid input or output file" in err and "private-address" not in err


def test_cli_saved_response_renders_like_mcp_body(tmp_path, seen):
    cli.main(["address-map", "x", str(tmp_path / "m.html")])
    assert regrid.offline.map.render(tmp_path / "m.json", tmp_path / "n.html")["features"] == 1


def test_transport_failure_counts_one(tmp_path, monkeypatch, capsys):
    def boom(request):
        raise httpx.ConnectError("secret private-address")

    seen = _install(monkeypatch, boom)
    assert cli.main(["address-map", "x", str(tmp_path / "m.html")]) == 1
    err = capsys.readouterr().err
    assert len(seen) == 1 and "requests made: 1" in err and "secret" not in err


def _two_stage(monkeypatch, subject_fields, neighbour_status=200):
    subject = good_feature(**subject_fields)
    other = good_feature()
    other["properties"]["ll_uuid"] = "00000000-0000-4000-8000-000000000002"

    def handler(request):
        if request.url.path.endswith("/parcels/point"):
            return httpx.Response(
                neighbour_status, json={"parcels": {"features": [subject, other]}}
            )
        return httpx.Response(200, json={"parcels": {"features": [subject]}})

    return _install(monkeypatch, handler)


def test_neighbours_second_request_exact_params(tmp_path, monkeypatch, capsys):
    seen = _two_stage(monkeypatch, {"lat": 39.9, "lon": -75.03})
    out = tmp_path / "m.html"
    assert cli.main(["address-map", "x", str(out), "--neighbours"]) == 0
    assert len(seen) == 2 and seen[1].url.path == "/api/v2/parcels/point"
    params = dict(seen[1].url.params)
    params.pop("token")
    assert params == {
        "lat": "39.9",
        "lon": "-75.03",
        "radius": "100",
        "limit": "25",
        "return_geometry": "true",
        "return_parcels": "true",
        "return_stacked": "false",
        "return_zoning": "false",
        "return_matched_buildings": "false",
        "return_matched_addresses": "false",
        "return_enhanced_ownership": "false",
    }
    captured = capsys.readouterr()
    assert "requests made: 2" in captured.err
    assert json.loads((tmp_path / "m.neighbours.json").read_text())["parcels"]
    summary = json.loads(captured.out)
    assert summary["neighbours"] == 1
    assert summary["neighbours_response"] == str(tmp_path / "m.neighbours.json")


def test_neighbours_string_coordinates_count_as_numeric(tmp_path, monkeypatch, capsys):
    seen = _two_stage(monkeypatch, {"lat": "39.9", "lon": "-75.03"})
    assert cli.main(["address-map", "x", str(tmp_path / "m.html"), "--neighbours"]) == 0
    assert len(seen) == 2 and dict(seen[1].url.params)["lat"] == "39.9"


def test_neighbours_skipped_without_coordinates(tmp_path, monkeypatch, capsys):
    seen = _two_stage(monkeypatch, {"lat": "n/a"})
    assert cli.main(["address-map", "x", str(tmp_path / "m.html"), "--neighbours"]) == 0
    err = capsys.readouterr().err
    assert len(seen) == 1 and "requests made: 1" in err
    assert "regrid: neighbours skipped: subject has no coordinates" in err
    assert not (tmp_path / "m.neighbours.json").exists()


@pytest.mark.parametrize("fields", [{"lat": 0, "lon": 0}, {"lat": 95, "lon": -75}])
def test_neighbours_skipped_for_out_of_us_coordinates(tmp_path, monkeypatch, capsys, fields):
    seen = _two_stage(monkeypatch, fields)
    assert cli.main(["address-map", "x", str(tmp_path / "m.html"), "--neighbours"]) == 0
    err = capsys.readouterr().err
    assert len(seen) == 1 and "regrid: neighbours skipped: subject has no coordinates" in err


def test_no_flag_makes_one_request(tmp_path, monkeypatch, capsys):
    seen = _two_stage(monkeypatch, {"lat": 39.9, "lon": -75.03})
    assert cli.main(["address-map", "x", str(tmp_path / "m.html")]) == 0
    assert len(seen) == 1 and "requests made: 1" in capsys.readouterr().err
    assert not (tmp_path / "m.neighbours.json").exists()


def test_existing_neighbours_file_refuses_before_request(tmp_path, monkeypatch, capsys):
    seen = _two_stage(monkeypatch, {"lat": 39.9, "lon": -75.03})
    (tmp_path / "m.neighbours.json").write_text("keep")
    assert cli.main(["address-map", "x", str(tmp_path / "m.html"), "--neighbours"]) == 1
    assert seen == [] and "requests made: 0" in capsys.readouterr().err
    assert (tmp_path / "m.neighbours.json").read_text() == "keep"


def test_neighbours_file_ignored_without_flag(tmp_path, monkeypatch):
    seen = _two_stage(monkeypatch, {"lat": 39.9, "lon": -75.03})
    (tmp_path / "m.neighbours.json").write_text("keep")
    assert cli.main(["address-map", "x", str(tmp_path / "m.html")]) == 0
    assert len(seen) == 1


def test_neighbours_path_colliding_with_response_refused(tmp_path, monkeypatch, capsys):
    seen = _two_stage(monkeypatch, {"lat": 39.9, "lon": -75.03})
    argv = ["address-map", "x", str(tmp_path / "m.html"), "--neighbours"]
    argv += ["--save-response", str(tmp_path / "m.neighbours.json")]
    assert cli.main(argv) == 1
    assert seen == [] and "different files" in capsys.readouterr().err


def test_neighbours_without_parcels_makes_no_second_request(tmp_path, monkeypatch, capsys):
    seen = _install(
        monkeypatch, lambda request: httpx.Response(200, json={"parcels": {"features": []}})
    )
    assert cli.main(["address-map", "x", str(tmp_path / "m.html"), "--neighbours"]) == 1
    err = capsys.readouterr().err
    assert len(seen) == 1 and "requests made: 1" in err
    assert "Response contains no parcels" in err and "neighbours skipped" not in err
    assert not (tmp_path / "m.neighbours.json").exists()


def test_neighbours_failure_still_renders_subject(tmp_path, monkeypatch, capsys):
    seen = _two_stage(monkeypatch, {"lat": 39.9, "lon": -75.03}, neighbour_status=500)
    out = tmp_path / "m.html"
    assert cli.main(["address-map", "x", str(out), "--neighbours"]) == 0
    captured = capsys.readouterr()
    assert len(seen) == 2 and "requests made: 2" in captured.err
    assert "regrid: neighbours skipped: request failed" in captured.err
    assert out.exists() and not (tmp_path / "m.neighbours.json").exists()
    assert "neighbours_response" not in json.loads(captured.out)
    assert "secret" not in captured.err


def test_render_failure_reports_neighbours_file(tmp_path, monkeypatch, capsys):
    _two_stage(monkeypatch, {"lat": 39.9, "lon": -75.03})

    def boom(*a, **k):
        raise regrid.offline.map.MapError("render exploded")

    monkeypatch.setattr(cli.parcel_map, "render", boom)
    assert cli.main(["address-map", "x", str(tmp_path / "m.html"), "--neighbours"]) == 1
    err = capsys.readouterr().err
    assert f"response saved to {tmp_path / 'm.json'}" in err
    assert f"neighbours saved to {tmp_path / 'm.neighbours.json'}" in err
