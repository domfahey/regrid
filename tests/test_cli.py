import json
import os
import runpy
import sys

import httpx
import pytest

from regrid import cli
from regrid.client import RegridClient

TILE_BYTES = b"\x00\xffparcel-tile\x80"
RESPONSE = {
    "parcels": {"features": []},
    "county_extra": {"apn": "000123", "label": "Müller", "optional": None},
}


@pytest.fixture
def requests(monkeypatch):
    seen = []

    def handle(request):
        seen.append(request)
        if request.url.path.endswith((".png", ".mvt")):
            return httpx.Response(200, content=TILE_BYTES)
        return httpx.Response(200, json=RESPONSE)

    monkeypatch.setenv("REGRID_TOKEN", "secret")
    monkeypatch.setattr(
        cli, "RegridClient", lambda **kw: RegridClient(**kw, transport=httpx.MockTransport(handle))
    )
    return seen


@pytest.mark.parametrize(
    "argv,host,path,method,params,body",
    [
        (
            ["point", "--lat", "30", "--lon", "-90"],
            "app.regrid.com",
            "/api/v2/parcels/point",
            "GET",
            {"lat": "30.0", "lon": "-90.0", "limit": "5", "return_parcels": "true"},
            None,
        ),
        (
            ["point", "--geojson", '{"type":"Point","coordinates":[0,0]}', "--method", "POST"],
            "app.regrid.com",
            "/api/v2/parcels/point",
            "POST",
            {"limit": "5", "return_parcels": "true"},
            {"geojson": {"type": "Point", "coordinates": [0, 0]}},
        ),
        (
            ["area", "--geojson", '{"type":"Point","coordinates":[1,2]}'],
            "app.regrid.com",
            "/api/v2/parcels/area",
            "GET",
            {
                "geojson": '{"type":"Point","coordinates":[1,2]}',
                "limit": "5",
                "return_parcels": "true",
            },
            None,
        ),
        (
            ["address", "123 Main"],
            "app.regrid.com",
            "/api/v2/parcels/address",
            "GET",
            {"query": "123 Main", "limit": "1", "return_parcels": "true"},
            None,
        ),
        (
            ["apn", "000123"],
            "app.regrid.com",
            "/api/v2/parcels/apn",
            "GET",
            {"parcelnumb": "000123", "limit": "5", "return_parcels": "true"},
            None,
        ),
        (
            ["owner", "Smith"],
            "app.regrid.com",
            "/api/v2/parcels/owner",
            "GET",
            {"owner": "Smith", "limit": "5", "return_parcels": "true"},
            None,
        ),
        (
            ["query", "--fields", '{"geoid":{"eq":"123"}}'],
            "app.regrid.com",
            "/api/v2/parcels/query",
            "GET",
            {"fields[geoid][eq]": "123", "limit": "5", "return_parcels": "true"},
            None,
        ),
        (
            ["parcel", "00000000-0000-0000-0000-000000000000"],
            "app.regrid.com",
            "/api/v2/parcels/00000000-0000-0000-0000-000000000000",
            "GET",
            {"return_parcels": "true"},
            None,
        ),
        (
            ["parcel-path", "/us/test"],
            "app.regrid.com",
            "/api/v2/parcels/path",
            "GET",
            {"path": "/us/test", "return_parcels": "true"},
            None,
        ),
        (
            ["typeahead", "123 Main"],
            "app.regrid.com",
            "/api/v2/parcels/typeahead",
            "GET",
            {"query": "123 Main"},
            None,
        ),
        (
            ["client-token-typeahead", "--exp", "60"],
            "app.regrid.com",
            "/api/v2/client_token/typeahead",
            "GET",
            {"exp": "60.0"},
            None,
        ),
        (["schema"], "app.regrid.com", "/api/v2/schemas/parcel", "GET", {}, None),
        (["verse", "--country", "ca"], "app.regrid.com", "/api/v2/ca/verse", "GET", {}, None),
        (["usage", "--detailed"], "app.regrid.com", "/api/v2/usage/detailed", "GET", {}, None),
        (
            ["report", "--comment", "wrong", "--details", '{"field":"owner"}'],
            "app.regrid.com",
            "/api/v2/report",
            "POST",
            {"comment": "wrong", "details": '{"field":"owner"}'},
            None,
        ),
        (["tilejson"], "tiles.regrid.com", "/api/v1/parcels", "GET", {"format": "mvt"}, None),
    ],
)
def test_commands(argv, host, path, method, params, body, requests, capsys):
    assert cli.main(argv) == 0
    assert len(requests) == 1
    request = requests[0]
    assert request.url.scheme == "https"
    assert request.url.host == host
    assert request.url.path == path
    assert request.method == method
    expected = params if argv[0] == "schema" else {**params, "token": "secret"}
    assert dict(request.url.params) == expected
    assert len(request.url.params.multi_items()) == len(expected)
    if body is None:
        assert request.content == b""
    else:
        assert json.loads(request.content) == body
        assert request.headers["content-type"] == "application/json"
    captured = capsys.readouterr()
    assert json.loads(captured.out) == RESPONSE
    assert captured.err == "regrid: requests made: 1\n"


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
    assert len(requests) == 1
    assert dict(requests[0].url.params) == {
        "fields[geoid][eq]": "123",
        "limit": "2",
        "return_parcels": "true",
        "token": "secret",
    }
    assert requests[0].extensions["timeout"] == {
        "connect": 2.0,
        "read": 2.0,
        "write": 2.0,
        "pool": 2.0,
    }
    captured = capsys.readouterr()
    assert json.loads(captured.out) == RESPONSE
    assert captured.err == "regrid: requests made: 1\n"


def test_api_error_still_reports_requests_made(monkeypatch, capsys):
    monkeypatch.setenv("REGRID_TOKEN", "secret")
    monkeypatch.setattr(
        cli,
        "RegridClient",
        lambda **kw: RegridClient(
            **kw, transport=httpx.MockTransport(lambda req: httpx.Response(500))
        ),
    )
    assert cli.main(["apn", "000123"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.splitlines() == [
        "regrid: Regrid returned HTTP 500",
        "regrid: requests made: 1",
    ]
    assert "secret" not in captured.err


def test_client_request_count_counts_every_sent_request():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={}))
    with RegridClient("t", transport=transport) as client:
        assert client.request_count == 0
        client.schema()
        client.address("x")
        assert client.request_count == 2


def test_tile(requests, tmp_path, capsys):
    dest = tmp_path / "tile.png"
    assert (
        cli.main(["tile", "10", "0", "0", "--format", "png", "--retina", "--output", str(dest)])
        == 0
    )
    assert len(requests) == 1
    assert dest.read_bytes() == TILE_BYTES
    assert requests[0].url.host == "tiles.regrid.com"
    assert requests[0].url.path == "/api/v1/parcels/10/0/0@2x.png"
    assert dict(requests[0].url.params) == {"token": "secret"}
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "regrid: requests made: 1\n"


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
    assert captured.err == "regrid: Invalid input or output file\nregrid: requests made: 0\n"
    assert captured.out == ""
    assert not requests


def test_bad_output(requests, tmp_path, capsys):
    assert cli.main(["tile", "10", "0", "0", "--output", str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "regrid: Output path is a directory\nregrid: requests made: 0\n"
    assert str(tmp_path) not in captured.err
    assert tmp_path.is_dir()
    assert list(tmp_path.iterdir()) == []
    assert not requests


@pytest.mark.parametrize("target", ["", "missing"])
def test_tile_empty_or_missing_parent_output_makes_no_request(requests, tmp_path, capsys, target):
    output = "" if target == "" else str(tmp_path / "missing" / "tile.mvt")
    expected = "Output path cannot be empty" if target == "" else "Output directory does not exist"
    assert cli.main(["tile", "10", "0", "0", "--output", output]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == f"regrid: {expected}\nregrid: requests made: 0\n"
    assert str(tmp_path) not in captured.err
    assert not requests


def test_tile_existing_output_requires_replace(requests, tmp_path, capsys):
    dest = tmp_path / "tile.png"
    dest.write_bytes(b"keep")
    assert cli.main(["tile", "10", "0", "0", "--format", "png", "--output", str(dest)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert (
        captured.err
        == "regrid: Output file exists; pass --replace to overwrite it\nregrid: requests made: 0\n"
    )
    assert str(dest) not in captured.err
    assert not requests
    assert dest.read_bytes() == b"keep"

    assert (
        cli.main(["tile", "10", "0", "0", "--format", "png", "--output", str(dest), "--replace"])
        == 0
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "regrid: requests made: 1\n"
    assert len(requests) == 1
    assert dest.read_bytes() == TILE_BYTES


@pytest.mark.skipif(os.name == "nt", reason="symlinks need privilege on Windows")
def test_tile_replace_does_not_write_through_symlink(requests, tmp_path, capsys):
    target = tmp_path / "victim.bin"
    target.write_bytes(b"keep")
    link = tmp_path / "tile.mvt"
    link.symlink_to(target)

    assert cli.main(["tile", "10", "0", "0", "--output", str(link)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert (
        captured.err
        == "regrid: Output file exists; pass --replace to overwrite it\nregrid: requests made: 0\n"
    )
    assert str(link) not in captured.err
    assert not requests
    assert link.is_symlink()
    assert target.read_bytes() == b"keep"

    assert cli.main(["tile", "10", "0", "0", "--output", str(link), "--replace"]) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "regrid: requests made: 1\n"
    assert len(requests) == 1
    assert not link.is_symlink()
    assert link.read_bytes() == TILE_BYTES
    assert target.read_bytes() == b"keep"


def test_tile_atomic_write_map_error_surfaces_safe_message(requests, monkeypatch, tmp_path, capsys):
    dest = tmp_path / "tile.mvt"

    def fail_write(*args, **kwargs):
        raise cli.parcel_map.MapError(cli.parcel_map.EXISTS)

    monkeypatch.setattr(cli.parcel_map, "write_atomic_bytes", fail_write)
    assert cli.main(["tile", "10", "0", "0", "--output", str(dest)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert (
        captured.err
        == "regrid: Output file exists; pass --replace to overwrite it\nregrid: requests made: 1\n"
    )
    assert str(dest) not in captured.err


@pytest.mark.parametrize("response", [httpx.Response(403), httpx.Response(200, text="broken")])
def test_http_error(monkeypatch, response, capsys):
    monkeypatch.setenv("REGRID_TOKEN", "secret")
    monkeypatch.setattr(
        cli,
        "RegridClient",
        lambda **kw: RegridClient(**kw, transport=httpx.MockTransport(lambda req: response)),
    )
    assert cli.main(["usage"]) == 1
    captured = capsys.readouterr()
    expected = (
        "Regrid returned HTTP 403"
        if response.status_code == 403
        else "Regrid returned invalid JSON"
    )
    assert captured.err == f"regrid: {expected}\nregrid: requests made: 1\n"
    assert captured.out == ""


@pytest.mark.parametrize("token", ["", "   "])
def test_blank_token_is_treated_as_unset(token, monkeypatch, capsys):
    seen = []
    monkeypatch.setattr(
        cli,
        "RegridClient",
        lambda **kw: RegridClient(
            **kw,
            transport=httpx.MockTransport(lambda req: seen.append(req) or httpx.Response(200)),
        ),
    )
    monkeypatch.delenv("REGRID_TOKEN", raising=False)
    assert cli.main(["address", "123 Main"]) == 1
    unset_err = capsys.readouterr().err
    monkeypatch.setenv("REGRID_TOKEN", token)
    assert cli.main(["address", "123 Main"]) == 1
    captured = capsys.readouterr()
    assert (
        captured.err
        == unset_err
        == ("regrid: Regrid returned HTTP 401\nregrid: requests made: 0\n")
    )
    assert captured.out == ""
    assert not seen


@pytest.mark.parametrize("token", ["", "   "])
def test_blank_token_public_schema_succeeds(requests, monkeypatch, token, capsys):
    monkeypatch.setenv("REGRID_TOKEN", token)
    assert cli.main(["schema"]) == 0
    assert len(requests) == 1
    assert requests[0].url.path == "/api/v2/schemas/parcel"
    assert dict(requests[0].url.params) == {}
    captured = capsys.readouterr()
    assert json.loads(captured.out) == RESPONSE
    assert captured.err == "regrid: requests made: 1\n"


def test_parser_help_error(capsys):
    assert cli.main(["--help"]) == 0
    captured = capsys.readouterr()
    assert captured.out.startswith("usage: ")
    assert "REGRID_TOKEN" in captured.out
    assert captured.err == ""
    assert cli.main([]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.rstrip().endswith("error: the following arguments are required: command")


def test_module_entry(monkeypatch, requests, capsys):
    monkeypatch.setattr(sys, "argv", ["regrid", "schema"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("regrid", run_name="__main__")
    assert exc.value.code == 0
    assert len(requests) == 1
    assert requests[0].url.path == "/api/v2/schemas/parcel"
    assert dict(requests[0].url.params) == {}
    assert json.loads(capsys.readouterr().out) == RESPONSE


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
    assert requests[0].method == "POST"
    assert requests[0].url.params["details"] == "Please check this parcel"
    assert cli.main(["--tiles-base-url", "https://tiles.example.test", "tilejson"]) == 0
    assert len(requests) == 2
    assert requests[1].url.host == "tiles.example.test"
    assert requests[1].url.path == "/api/v1/parcels"


def test_json_argument_error_does_not_retain_input_context():
    with pytest.raises(ValueError) as caught:
        cli._object('{"owner": "SECRET"')
    assert caught.value.__context__ is None
    assert caught.value.__cause__ is None


def test_surrounding_whitespace_is_trimmed_from_token(requests, monkeypatch, capsys):
    monkeypatch.setenv("REGRID_TOKEN", "  padded-token\n")
    assert cli.main(["address", "123 Main"]) == 0
    assert requests[-1].url.params["token"] == "padded-token"


def test_file_input_reads_utf8_json(requests, tmp_path, capsys):
    fields = tmp_path / "utf8-fields.json"
    fields.write_text('{"owner":{"eq":"Café — Straße"}}', encoding="utf-8")
    assert cli.main(["query", "--fields", "@" + str(fields)]) == 0
    assert requests[-1].url.params["fields[owner][eq]"] == "Café — Straße"
    assert json.loads(capsys.readouterr().out) == RESPONSE


def test_fields_command_rejects_nan_values(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.parcel_fields, "search", lambda catalog, term: [{"name": "x", "bad": float("nan")}]
    )
    assert cli.main(["fields", "search", "x"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Traceback" not in captured.err
    assert captured.err.startswith("regrid: ")
