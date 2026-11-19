"""Offline CLI commands never need a token or an HTTP client."""

import json

import pytest
from map_fixtures import good_feature, write_response

from regrid import cli


def test_map_renders_without_token_or_client(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("REGRID_TOKEN", raising=False)
    monkeypatch.setattr(cli, "RegridClient", lambda **kw: pytest.fail("no client for offline map"))
    response = write_response(tmp_path / "r.json", good_feature())
    assert cli.main(["map", str(response), str(tmp_path / "m.html")]) == 0
    assert json.loads(capsys.readouterr().out)["features"] == 1


def test_map_errors_are_one_line(tmp_path, capsys):
    response = write_response(tmp_path / "r.json", good_feature(), good_feature())
    assert cli.main(["map", str(response), str(tmp_path / "m.html")]) == 1
    err = capsys.readouterr().err
    assert err.startswith("regrid: Response has several parcels") and err.count("\n") == 1


def test_map_os_error_is_one_line(tmp_path, capsys):
    assert cli.main(["map", str(tmp_path / "missing.json"), str(tmp_path / "m.html")]) == 1
    err = capsys.readouterr().err
    assert err.startswith("regrid: ") and err.count("\n") == 1


def test_map_flags_pass_through(tmp_path):
    response = write_response(tmp_path / "r.json", good_feature(), good_feature())
    assert (
        cli.main(
            [
                "map",
                str(response),
                str(tmp_path / "m.html"),
                "--all-candidates",
                "--retrieved-at",
                "2026-11-19T00:00:00Z",
            ]
        )
        == 0
    )
    page = (tmp_path / "m.html").read_text(encoding="utf-8")
    assert "Candidate 2" in page and "2026-11-19T00:00:00Z" in page
    assert cli.main(["map", str(response), str(tmp_path / "m.html"), "--feature", "0"]) == 1
    assert (
        cli.main(["map", str(response), str(tmp_path / "m.html"), "--feature", "0", "--replace"])
        == 0
    )


def test_regrid_fields_cli(monkeypatch, capsys):
    monkeypatch.delenv("REGRID_TOKEN", raising=False)
    monkeypatch.setattr(cli, "RegridClient", lambda **kw: pytest.fail("no client for fields"))
    assert cli.main(["fields", "explain", "owner", "zzz"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["found"][0]["name"] == "owner" and out["unknown"] == ["zzz"]


def test_regrid_fields_search_cli(capsys):
    assert cli.main(["fields", "search", "ASSESSMENT"]) == 0
    assert json.loads(capsys.readouterr().out)["matches"]


def test_export_cli_offline(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("REGRID_TOKEN", raising=False)
    monkeypatch.setattr(cli, "RegridClient", lambda **kw: pytest.fail("no client for export"))
    response = write_response(tmp_path / "r.json", good_feature())
    argv = ["export", str(response), "--csv", str(tmp_path / "o.csv")]
    assert cli.main([*argv, "--geojson", str(tmp_path / "o.geojson"), "--all-fields"]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["features"] == 1 and summary["geojson"] == str(tmp_path / "o.geojson")
    assert cli.main(argv) == 1
    assert "--replace" in capsys.readouterr().err
    assert cli.main([*argv, "--replace"]) == 0
    assert cli.main(["export", str(response)]) == 1
    assert "Choose --csv and/or --geojson" in capsys.readouterr().err


def test_export_cli_non_finite_is_one_line(tmp_path, capsys):
    response = tmp_path / "r.json"
    response.write_text(
        '{"parcels":{"features":[{"type":"Feature","geometry":null,'
        '"properties":{"path":"/us/nj/x","headline":Infinity,"fields":{}}}]}}',
        encoding="utf-8",
    )
    argv = ["export", str(response), "--geojson", str(tmp_path / "o.geojson")]
    assert cli.main(argv) == 1
    err = capsys.readouterr().err
    assert err.startswith("regrid: ") and err.count("\n") == 1
    assert not (tmp_path / "o.geojson").exists()


def test_map_neighbours_passthrough(tmp_path, capsys):
    response = write_response(tmp_path / "r.json", good_feature())
    other = good_feature()
    other["properties"]["ll_uuid"] = "00000000-0000-4000-8000-000000000002"
    neighbours = write_response(tmp_path / "n.json", good_feature(), other)
    out = tmp_path / "m.html"
    assert cli.main(["map", str(response), str(out), "--neighbours", str(neighbours)]) == 0
    assert json.loads(capsys.readouterr().out)["neighbours"] == 1
