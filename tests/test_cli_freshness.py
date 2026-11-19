import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from regrid import cli
from regrid.client import RegridClient
from regrid.offline import freshness

COLLECTION = {
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
# The real /verse body wraps the collection under a top-level "verse" key.
VERSE = {"verse": COLLECTION}


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
    assert cli.main(args) == 0
    first = json.loads(capsys.readouterr().out)
    assert cli.main([*args, "--refresh"]) == 0
    second = json.loads(capsys.readouterr().out)
    assert len(verse_server) == 2
    assert first["cache"] == "miss" and second["cache"] == "miss"


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
    # The default directory comes from LOCALAPPDATA on Windows and XDG_CACHE_HOME elsewhere.
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
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


def test_freshness_keeps_result_when_cache_cannot_be_serialized(tmp_path, monkeypatch, capsys):
    nan_verse = json.loads(json.dumps(VERSE))
    nan_verse["verse"]["features"][0]["properties"]["extra"] = float("nan")

    class NanClient(RegridClient):
        def verse(self, **kwargs):
            self.request_count += 1
            return nan_verse

    monkeypatch.setenv("REGRID_TOKEN", "secret")
    monkeypatch.setattr(cli, "RegridClient", NanClient)
    cache = tmp_path / "verse.json"
    assert cli.main(["freshness", "--path", "/us/nj/camden", "--cache", str(cache)]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["last_refresh"] == "2026-09-01"
    assert "verse cache not saved" in captured.err
    assert captured.err.count("requests made") == 1 and "requests made: 1" in captured.err
    assert not cache.exists() and list(tmp_path.iterdir()) == []


DEFAULT_BASE = "https://app.regrid.com/api/v2"


def _aged(days):
    when = datetime.now(timezone.utc) - timedelta(days=days)
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_cache_stores_base_url(tmp_path, verse_server, capsys):
    cache = tmp_path / "verse.json"
    assert cli.main(["freshness", "--path", "/us/nj/camden", "--cache", str(cache)]) == 0
    assert json.loads(cache.read_text())["base_url"] == DEFAULT_BASE


def test_old_cache_is_refetched_and_reported(tmp_path, verse_server, capsys):
    cache = tmp_path / "verse.json"
    freshness.write_cache(cache, _aged(40), VERSE, DEFAULT_BASE)
    assert cli.main(["freshness", "--path", "/us/nj/camden", "--cache", str(cache)]) == 0
    captured = capsys.readouterr()
    assert len(verse_server) == 1 and "requests made: 1" in captured.err
    assert "older than 30 days" in captured.err
    out = json.loads(captured.out)
    assert out["cache"] == "miss" and out["verse_retrieved_at"] != _aged(40)


def test_max_age_days_extends_cache_lifetime(tmp_path, verse_server, capsys):
    cache = tmp_path / "verse.json"
    freshness.write_cache(cache, _aged(40), VERSE, DEFAULT_BASE)
    args = ["freshness", "--path", "/us/nj/camden", "--cache", str(cache)]
    assert cli.main([*args, "--max-age-days", "60"]) == 0
    captured = capsys.readouterr()
    assert verse_server == [] and json.loads(captured.out)["cache"] == "hit"
    assert "requests made: 0" in captured.err
    assert cli.main([*args, "--max-age-days", "10"]) == 0
    assert len(verse_server) == 1


def test_recent_cache_is_a_hit(tmp_path, verse_server, capsys):
    cache = tmp_path / "verse.json"
    freshness.write_cache(cache, _aged(29), VERSE, DEFAULT_BASE)
    assert cli.main(["freshness", "--path", "/us/nj/camden", "--cache", str(cache)]) == 0
    assert verse_server == [] and json.loads(capsys.readouterr().out)["cache"] == "hit"


def test_unparseable_timestamp_is_refetched(tmp_path, verse_server, capsys):
    cache = tmp_path / "verse.json"
    freshness.write_cache(cache, "yesterday", VERSE, DEFAULT_BASE)
    assert cli.main(["freshness", "--path", "/us/nj/camden", "--cache", str(cache)]) == 0
    captured = capsys.readouterr()
    assert len(verse_server) == 1 and json.loads(captured.out)["cache"] == "miss"
    assert "requests made: 1" in captured.err
    assert json.loads(cache.read_text())["retrieved_at"] != "yesterday"


def test_different_base_url_is_a_miss(tmp_path, verse_server, capsys):
    cache = tmp_path / "verse.json"
    freshness.write_cache(cache, _aged(1), VERSE, "https://other.example/api/v2")
    assert cli.main(["freshness", "--path", "/us/nj/camden", "--cache", str(cache)]) == 0
    assert len(verse_server) == 1 and json.loads(capsys.readouterr().out)["cache"] == "miss"
    assert json.loads(cache.read_text())["base_url"] == DEFAULT_BASE


def test_cache_without_base_url_is_a_miss(tmp_path, verse_server, capsys):
    cache = tmp_path / "verse.json"
    cache.write_text(json.dumps({"retrieved_at": _aged(1), "response": VERSE}))
    assert cli.main(["freshness", "--path", "/us/nj/camden", "--cache", str(cache)]) == 0
    assert len(verse_server) == 1 and json.loads(capsys.readouterr().out)["cache"] == "miss"
    assert json.loads(cache.read_text())["base_url"] == DEFAULT_BASE


@pytest.mark.parametrize("value", ["inf", "-inf", "nan", "1e10", "-1", "36501", "abc"])
def test_max_age_days_rejects_unsafe_values(tmp_path, verse_server, capsys, value):
    cache = tmp_path / "verse.json"
    stamp = _aged(1)
    freshness.write_cache(cache, stamp, VERSE, DEFAULT_BASE)
    argv = ["freshness", "--path", "/us/nj/camden", "--cache", str(cache), "--max-age-days", value]
    assert cli.main(argv) == 2
    captured = capsys.readouterr()
    assert verse_server == [] and captured.out == ""
    assert "--max-age-days" in captured.err and "secret" not in captured.err
    assert json.loads(cache.read_text())["retrieved_at"] == stamp


@pytest.mark.parametrize("value", ["0", "36500", "0.5"])
def test_max_age_days_accepts_bounds(tmp_path, verse_server, capsys, value):
    cache = tmp_path / "verse.json"
    argv = ["freshness", "--path", "/us/nj/camden", "--cache", str(cache), "--max-age-days", value]
    assert cli.main(argv) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["last_refresh"] == "2026-09-01"
    assert len(verse_server) == 1 and "requests made: 1" in captured.err


def test_trailing_slash_base_url_shares_cache(tmp_path, verse_server, capsys):
    cache = tmp_path / "verse.json"
    base = ["--base-url", DEFAULT_BASE + "/"]
    args = [*base, "freshness", "--path", "/us/nj/camden", "--cache", str(cache)]
    assert cli.main(args) == 0
    assert json.loads(cache.read_text())["base_url"] == DEFAULT_BASE
    capsys.readouterr()
    assert cli.main(args) == 0
    assert len(verse_server) == 1 and json.loads(capsys.readouterr().out)["cache"] == "hit"
