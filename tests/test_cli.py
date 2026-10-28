import json
import runpy
import sys

import httpx
import pytest

from regrid import cli
from regrid.client import RegridClient


@pytest.fixture
def requests(monkeypatch):
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setenv("REGRID_TOKEN", "secret")
    monkeypatch.setattr(
        cli, "RegridClient", lambda **kw: RegridClient(**kw, transport=httpx.MockTransport(handle))
    )
    return seen


@pytest.mark.parametrize(
    "argv,path",
    [
        (["point", "--lat", "30", "--lon", "-90"], "/parcels/point"),
        (
            ["point", "--geojson", '{"type":"Point","coordinates":[0,0]}', "--method", "POST"],
            "/parcels/point",
        ),
        (["area", "--geojson", '{"type":"Polygon","coordinates":[]}'], "/parcels/area"),
        (["address", "123 Main"], "/parcels/address"),
        (["apn", "000123"], "/parcels/apn"),
        (["owner", "Smith"], "/parcels/owner"),
        (["query", "--fields", '{"geoid":{"eq":"123"}}'], "/parcels/query"),
        (
            ["parcel", "00000000-0000-0000-0000-000000000000"],
            "/parcels/00000000-0000-0000-0000-000000000000",
        ),
        (["parcel-path", "/us/test"], "/parcels/path"),
        (["typeahead", "123 Main"], "/parcels/typeahead"),
        (["client-token-typeahead", "--exp", "60"], "/client_token/typeahead"),
        (["schema"], "/schemas/parcel"),
        (["verse", "--country", "ca"], "/ca/verse"),
        (["usage", "--detailed"], "/usage/detailed"),
        (["report", "--comment", "wrong", "--details", '{"field":"owner"}'], "/report"),
        (["tilejson"], "/api/v1/parcels"),
    ],
)
def test_commands(argv, path, requests, capsys):
    assert cli.main(argv) == 0
    assert requests[0].url.path.endswith(path)
    assert json.loads(capsys.readouterr().out) == {"ok": True}


def test_file_inputs_options_timeout(requests, tmp_path, capsys):
    fields = tmp_path / "fields.json"
    fields.write_text('{"geoid":{"eq":"123"}}')
    options = tmp_path / "options.json"
    options.write_text('{"limit":2}')
    assert (
        cli.main(
            [
                "--timeout",
                "2",
                "query",
                "--fields",
                "@" + str(fields),
                "--options",
                "@" + str(options),
            ]
        )
        == 0
    )
    assert requests[0].url.params["limit"] == "2"


def test_tile(requests, tmp_path, capsys):
    dest = tmp_path / "tile.png"
    assert (
        cli.main(["tile", "10", "0", "0", "--format", "png", "--retina", "--output", str(dest)])
        == 0
    )
    assert dest.read_bytes()
    assert requests[0].url.path.endswith("/10/0/0@2x.png")
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    "argv",
    [
        ["query", "--fields", "bad"],
        ["query", "--fields", "[]"],
        ["query", "--fields", "@/does/not/exist"],
        ["point"],
        ["point", "--lat", "1", "--lon", "2", "--options", '{"country":"ca"}'],
        ["address", "x", "--options", '{"token":"secret"}'],
        ["--timeout", "0", "schema"],
    ],
)
def test_invalid(argv, requests, capsys):
    assert cli.main(argv) == 1
    captured = capsys.readouterr()
    assert "secret" not in captured.err
    assert captured.out == ""
    assert not requests


def test_bad_output(requests, tmp_path):
    assert cli.main(["tile", "10", "0", "0", "--output", str(tmp_path)]) == 1


@pytest.mark.parametrize("response", [httpx.Response(403), httpx.Response(200, text="broken")])
def test_http_error(monkeypatch, response, capsys):
    monkeypatch.setenv("REGRID_TOKEN", "secret")
    monkeypatch.setattr(
        cli,
        "RegridClient",
        lambda **kw: RegridClient(**kw, transport=httpx.MockTransport(lambda req: response)),
    )
    assert cli.main(["usage"]) == 1
    assert "secret" not in capsys.readouterr().err


def test_parser_help_error(capsys):
    assert cli.main(["--help"]) == 0
    assert "REGRID_TOKEN" in capsys.readouterr().out
    assert cli.main([]) == 2
    assert "required" in capsys.readouterr().err


def test_module_entry(monkeypatch, requests):
    monkeypatch.setattr(sys, "argv", ["regrid", "schema"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("regrid", run_name="__main__")
    assert exc.value.code == 0


def test_base_urls_and_report_text(requests):
    assert (
        cli.main(
            [
                "--base-url",
                "https://example.test/v2",
                "--tiles-base-url",
                "https://tiles.example.test",
                "report",
                "--details-text",
                "Please check this parcel",
            ]
        )
        == 0
    )
    assert str(requests[0].url).startswith("https://example.test/v2/report?")
    assert requests[0].url.params["details"] == "Please check this parcel"
    assert cli.main(["--tiles-base-url", "https://tiles.example.test", "tilejson"]) == 0
    assert requests[1].url.host == "tiles.example.test"
