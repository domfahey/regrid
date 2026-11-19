"""Offline CLI commands never need a token or an HTTP client."""

import json
import os

import pytest
from map_fixtures import good_feature, write_response
from test_offline_fields import ASSESSMENT_HITS

from regrid import cli


def test_map_renders_without_token_or_client(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("REGRID_TOKEN", raising=False)
    monkeypatch.setattr(cli, "RegridClient", lambda **kw: pytest.fail("no client for offline map"))
    response = write_response(tmp_path / "r.json", good_feature())
    assert cli.main(["map", str(response), str(tmp_path / "m.html")]) == 0
    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert summary["features"] == 1 and summary["output"] == str(tmp_path / "m.html")
    assert (tmp_path / "m.html").exists()
    # Offline commands never print the request counter.
    assert "requests made" not in captured.err


def test_map_errors_are_one_line(tmp_path, capsys):
    response = write_response(tmp_path / "r.json", good_feature(), good_feature())
    assert cli.main(["map", str(response), str(tmp_path / "m.html")]) == 1
    err = capsys.readouterr().err
    assert err.startswith("regrid: Response has several parcels") and err.count("\n") == 1
    assert not (tmp_path / "m.html").exists()


def test_map_os_error_is_one_line(tmp_path, capsys):
    assert cli.main(["map", str(tmp_path / "missing.json"), str(tmp_path / "m.html")]) == 1
    err = capsys.readouterr().err
    missing = tmp_path / "missing.json"
    assert err == f"regrid: [Errno 2] No such file or directory: {str(missing)!r}\n"
    assert not (tmp_path / "m.html").exists()


def test_map_flags_pass_through(tmp_path, capsys):
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
    assert "exists" in capsys.readouterr().err
    assert (
        cli.main(["map", str(response), str(tmp_path / "m.html"), "--feature", "0", "--replace"])
        == 0
    )


def test_regrid_fields_cli(monkeypatch, capsys):
    monkeypatch.delenv("REGRID_TOKEN", raising=False)
    monkeypatch.setattr(cli, "RegridClient", lambda **kw: pytest.fail("no client for fields"))
    assert cli.main(["fields", "explain", "owner", "zzz"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert [f["name"] for f in out["found"]] == ["owner"] and out["unknown"] == ["zzz"]
    assert out["found"][0]["description"] == "Owner name"


def test_regrid_fields_search_cli(capsys):
    assert cli.main(["fields", "search", "ASSESSMENT"]) == 0
    matches = json.loads(capsys.readouterr().out)["matches"]
    assert [m["name"] for m in matches] == ASSESSMENT_HITS


def test_export_cli_offline(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("REGRID_TOKEN", raising=False)
    monkeypatch.setattr(cli, "RegridClient", lambda **kw: pytest.fail("no client for export"))
    response = write_response(tmp_path / "r.json", good_feature())
    argv = ["export", str(response), "--csv", str(tmp_path / "o.csv")]
    assert cli.main([*argv, "--geojson", str(tmp_path / "o.geojson"), "--all-fields"]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["features"] == 1 and summary["geojson"] == str(tmp_path / "o.geojson")
    assert summary["csv"] == str(tmp_path / "o.csv") and "ll_gissqft" in summary["columns"]
    assert (tmp_path / "o.csv").exists() and (tmp_path / "o.geojson").exists()
    assert cli.main(argv) == 1
    assert "--replace" in capsys.readouterr().err
    assert cli.main([*argv, "--replace"]) == 0
    assert json.loads(capsys.readouterr().out)["geojson"] is None
    assert cli.main(["export", str(response)]) == 1
    assert capsys.readouterr().err == "regrid: Choose --csv and/or --geojson\n"


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
    assert out.exists()


def _loop(tmp_path):
    (tmp_path / "a").symlink_to(tmp_path / "b")
    (tmp_path / "b").symlink_to(tmp_path / "a")
    return tmp_path / "a"


@pytest.mark.skipif(os.name == "nt", reason="symlinks need privilege on Windows")
@pytest.mark.parametrize("command", ["map", "export"])
def test_symlink_loop_output_is_one_clean_line(tmp_path, capsys, command):
    response = write_response(tmp_path / "r.json", good_feature())
    loop = _loop(tmp_path)
    args = [command, str(response), str(loop)]
    if command == "export":
        args.insert(2, "--csv")
    assert cli.main(args) == 1
    err = capsys.readouterr().err
    assert err == "regrid: Path contains a symlink loop\n"


def test_map_onto_directory_is_one_clean_line(tmp_path, capsys):
    response = write_response(tmp_path / "r.json", good_feature())
    (tmp_path / "out").mkdir()
    assert cli.main(["map", str(response), str(tmp_path / "out"), "--replace"]) == 1
    assert capsys.readouterr().err == "regrid: Output path is a directory\n"
