import json
import os
import stat
import sys

import pytest

from regrid.offline import freshness

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


def test_county_path_trims_parcel_path():
    assert freshness.county_path("/us/nj/camden/haddonfield/123") == "/us/nj/camden"


@pytest.mark.parametrize("bad", ["/ca/on/toronto", "/us/nj", "nj/camden", "", "/us//camden"])
def test_county_path_rejects(bad):
    with pytest.raises(freshness.FreshnessError):
        freshness.county_path(bad)


def test_county_dates_reports_dates_only():
    result = freshness.county_dates(VERSE, "/us/nj/camden/haddonfield/123")
    assert result["last_refresh"] == "2026-09-01" and "stale" not in json.dumps(result).lower()
    assert result["usps_data_date"] is None and result["county"] == "Camden"
    assert set(result) == {
        "path",
        "county",
        "state",
        "last_refresh",
        "assessor_data_date",
        "usps_data_date",
    }


def test_county_dates_accepts_single_feature():
    result = freshness.county_dates(VERSE["features"][0], "/us/nj/camden")
    assert result["path"] == "/us/nj/camden"


def test_county_dates_non_string_values_become_none():
    feature = {"properties": {"path": "/us/nj/camden", "last_refresh": 5, "county": ["x"]}}
    result = freshness.county_dates(feature, "/us/nj/camden")
    assert result["last_refresh"] is None and result["county"] is None


@pytest.mark.parametrize(
    "document",
    [
        [],
        {"features": "x"},
        {"features": [{"properties": {"path": "/us/nj/other"}}, "junk", {"properties": 3}]},
        {"foo": 1},
    ],
)
def test_county_dates_unknown_county(document):
    with pytest.raises(freshness.FreshnessError):
        freshness.county_dates(document, "/us/nj/camden")


def test_default_cache_path_posix():
    env = {"XDG_CACHE_HOME": "/x/cache"}
    assert freshness.default_cache_path(env, "posix").as_posix() == "/x/cache/regrid/verse.json"
    home = freshness.default_cache_path({}, "posix")
    assert home.parts[-3:] == (".cache", "regrid", "verse.json")


def test_default_cache_path_windows():
    path = freshness.default_cache_path({"LOCALAPPDATA": "C:/Users/a/AppData/Local"}, "nt")
    assert path.parts[-2:] == ("regrid", "verse.json")


def test_cache_round_trip_is_private_and_atomic(tmp_path):
    cache = tmp_path / "new" / "verse.json"
    freshness.write_cache(cache, "2026-11-19T00:00:00Z", VERSE)
    assert freshness.read_cache(cache) == ("2026-11-19T00:00:00Z", VERSE)
    assert list(cache.parent.iterdir()) == [cache]
    if sys.platform != "win32":
        assert stat.S_IMODE(os.stat(cache.parent).st_mode) == 0o700


@pytest.mark.parametrize("text", ["nope", "[]", '{"retrieved_at": 1, "response": {}}', "{}"])
def test_read_cache_invalid_returns_none(tmp_path, text):
    cache = tmp_path / "v.json"
    cache.write_text(text)
    assert freshness.read_cache(cache) is None


def test_read_cache_missing_returns_none(tmp_path):
    assert freshness.read_cache(tmp_path / "none.json") is None


def test_helper_cli_county(tmp_path, capsys):
    verse = tmp_path / "v.json"
    verse.write_text(json.dumps(VERSE))
    assert freshness.main(["county", str(verse), "--path", "/us/nj/camden/x/1"]) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "NJ"


def test_helper_cli_errors(tmp_path, capsys):
    verse = tmp_path / "v.json"
    verse.write_text(json.dumps(VERSE))
    assert freshness.main(["county", str(verse), "--path", "/us/nj/other"]) == 1
    assert freshness.main(["county", str(tmp_path / "missing.json"), "--path", "/us/nj/a"]) == 1
    verse.write_text("not json")
    assert freshness.main(["county", str(verse), "--path", "/us/nj/camden"]) == 1
    assert capsys.readouterr().err.count("freshness:") == 3


def test_write_cache_failure_cleans_temp(tmp_path, monkeypatch):
    def boom(*args):
        raise OSError("disk")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        freshness.write_cache(tmp_path / "v.json", "t", VERSE)
    assert list(tmp_path.iterdir()) == []


def test_helper_cli_main_guard(tmp_path):
    import subprocess

    verse = tmp_path / "v.json"
    verse.write_text(json.dumps(VERSE))
    result = subprocess.run(
        [sys.executable, freshness.__file__, "county", str(verse), "--path", "/us/nj/camden"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0 and "Camden" in result.stdout
