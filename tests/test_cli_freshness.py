import json

import httpx
import pytest

from regrid import cli
from regrid.client import RegridClient

VERSE = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {
                "path": "/us/nj/camden",
                "county": "Camden",
                "state": "NJ",
                "last_refresh": "2026-09-01",
                "assessor_data_date": "2026-08-15",
                "usps_data_date": None,
            },
        }
    ],
}


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
def verse_server(monkeypatch):
    return _install(monkeypatch, lambda request: httpx.Response(200, json=VERSE))


def test_freshness_caches_and_reuses(tmp_path, verse_server, capsys):
    cache = tmp_path / "verse.json"
    assert cli.main(["freshness", "--path", "/us/nj/camden", "--cache", str(cache)]) == 0
    first = capsys.readouterr()
    out = json.loads(first.out)
    assert "requests made: 1" in first.err and out["cache"] == "miss"
    assert out["last_refresh"] == "2026-09-01" and out["verse_retrieved_at"]
    assert verse_server[0].url.path == "/api/v2/verse"
    assert dict(verse_server[0].url.params)["return_geometry"] == "false"
    assert cli.main(["freshness", "--path", "/us/nj/camden/x/1", "--cache", str(cache)]) == 0
    second = capsys.readouterr()
    assert "requests made: 0" in second.err and len(verse_server) == 1
    assert json.loads(second.out)["cache"] == "hit"
    assert "secret" not in cache.read_text()


def test_refresh_forces_request(tmp_path, verse_server, capsys):
    cache = tmp_path / "verse.json"
    args = ["freshness", "--path", "/us/nj/camden", "--cache", str(cache)]
    cli.main(args)
    cli.main([*args, "--refresh"])
    assert len(verse_server) == 2
    assert '"cache": "miss"' in capsys.readouterr().out.split("}\n{")[-1]


def test_unknown_county_exits_1_without_retry(tmp_path, verse_server, capsys):
    cache = tmp_path / "verse.json"
    args = ["freshness", "--path", "/us/nj/nowhere", "--cache", str(cache)]
    assert cli.main(args) == 1
    captured = capsys.readouterr()
    assert len(verse_server) == 1 and "requests made: 1" in captured.err
    assert "/us/nj/nowhere" in captured.err and captured.out == ""
    # A cached unknown county is reported without another request.
    assert cli.main(args) == 1
    assert len(verse_server) == 1
    err = capsys.readouterr().err
    assert "requests made: 0" in err and "use --refresh" in err


def test_bad_path_makes_no_request(tmp_path, verse_server, capsys):
    assert cli.main(["freshness", "--path", "/ca/on/x", "--cache", str(tmp_path / "v.json")]) == 1
    assert verse_server == [] and "requests made: 0" in capsys.readouterr().err


def test_api_error_reports_count(tmp_path, monkeypatch, capsys):
    seen = _install(monkeypatch, lambda request: httpx.Response(401, text="secret"))
    assert cli.main(["freshness", "--path", "/us/nj/camden", "--cache", str(tmp_path / "v")]) == 1
    err = capsys.readouterr().err
    assert len(seen) == 1 and err.index("requests made: 1") < err.index("HTTP 401")
    assert "secret" not in err and not (tmp_path / "v").exists()


def test_corrupt_cache_is_refetched(tmp_path, verse_server, capsys):
    cache = tmp_path / "verse.json"
    cache.write_text("garbage")
    assert cli.main(["freshness", "--path", "/us/nj/camden", "--cache", str(cache)]) == 0
    assert json.loads(capsys.readouterr().out)["cache"] == "miss" and len(verse_server) == 1


def test_default_cache_location_from_environment(tmp_path, verse_server, monkeypatch, capsys):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    assert cli.main(["freshness", "--path", "/us/nj/camden"]) == 0
    capsys.readouterr()
    assert (tmp_path / "regrid" / "verse.json").exists()


def test_unwritable_cache_keeps_result(tmp_path, verse_server, capsys):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    args = ["freshness", "--path", "/us/nj/camden", "--cache", str(blocker / "sub" / "v.json")]
    assert cli.main(args) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["cache"] == "miss"
    assert "requests made: 1" in captured.err
    assert "regrid: warning: verse cache not saved" in captured.err
    assert str(tmp_path) not in captured.err


def test_missing_token_makes_no_request(tmp_path, verse_server, monkeypatch, capsys):
    monkeypatch.delenv("REGRID_TOKEN")
    assert cli.main(["freshness", "--path", "/us/nj/camden", "--cache", str(tmp_path / "v")]) == 1
    assert verse_server == [] and "requests made: 0" in capsys.readouterr().err
