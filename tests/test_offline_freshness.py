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
    with pytest.raises(freshness.FreshnessError, match="^Expected a US path with state and county"):
        freshness.county_path(bad)


def test_county_dates_reports_dates_only():
    result = freshness.county_dates(VERSE, "/us/nj/camden/haddonfield/123")
    assert result == {
        "path": "/us/nj/camden",
        "county": "Camden",
        "state": "NJ",
        "last_refresh": "2026-09-01",
        "assessor_data_date": "2026-08-15",
        "usps_data_date": None,
    }


def test_county_dates_accepts_single_feature():
    result = freshness.county_dates(VERSE["features"][0], "/us/nj/camden")
    assert result["path"] == "/us/nj/camden"
    assert result["county"] == "Camden" and result["last_refresh"] == "2026-09-01"


def test_county_dates_non_string_values_become_none():
    feature = {"properties": {"path": "/us/nj/camden", "last_refresh": 5, "county": ["x"]}}
    result = freshness.county_dates(feature, "/us/nj/camden")
    assert result == {
        "path": "/us/nj/camden",
        "county": None,
        "state": None,
        "last_refresh": None,
        "assessor_data_date": None,
        "usps_data_date": None,
    }


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
    with pytest.raises(freshness.FreshnessError, match="^No verse entry found for /us/nj/camden$"):
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
    captured = capsys.readouterr()
    assert json.loads(captured.out) == freshness.county_dates(VERSE, "/us/nj/camden")
    assert json.loads(captured.out)["state"] == "NJ" and captured.err == ""


def test_helper_cli_errors(tmp_path, capsys):
    verse = tmp_path / "v.json"
    verse.write_text(json.dumps(VERSE))
    assert freshness.main(["county", str(verse), "--path", "/us/nj/other"]) == 1
    captured = capsys.readouterr()
    assert captured.err == "freshness: No verse entry found for /us/nj/other\n"
    assert captured.out == ""
    missing = tmp_path / "missing.json"
    assert freshness.main(["county", str(missing), "--path", "/us/nj/a"]) == 1
    captured = capsys.readouterr()
    assert captured.err == f"freshness: [Errno 2] No such file or directory: {str(missing)!r}\n"
    assert captured.out == ""
    verse.write_text("not json")
    assert freshness.main(["county", str(verse), "--path", "/us/nj/camden"]) == 1
    captured = capsys.readouterr()
    assert captured.err.startswith("freshness: Expecting value")
    assert captured.err.count("\n") == 1 and captured.out == ""


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
    assert result.returncode == 0 and result.stderr == ""
    assert json.loads(result.stdout) == freshness.county_dates(VERSE, "/us/nj/camden")


def test_cache_base_url_round_trip_and_mismatch(tmp_path):
    cache = tmp_path / "verse.json"
    freshness.write_cache(cache, "2026-11-19T00:00:00Z", VERSE, "https://a.example")
    assert freshness.read_cache(cache, "https://a.example") == ("2026-11-19T00:00:00Z", VERSE)
    assert freshness.read_cache(cache, "https://b.example") is None
    assert freshness.read_cache(cache) == ("2026-11-19T00:00:00Z", VERSE)


def test_is_stale():
    from datetime import datetime, timezone

    now = datetime(2026, 11, 19, tzinfo=timezone.utc)
    assert not freshness.is_stale("2026-10-25T00:00:00Z", 30, now)
    assert freshness.is_stale("2026-10-19T00:00:00Z", 30, now)
    assert freshness.is_stale("garbage", 30, now)
    assert not freshness.is_stale("2026-10-19T00:00:00Z", 60, now)
    assert freshness.is_stale("2026-10-19T00:00:00", 30, now) is True  # naive treated as UTC


@pytest.mark.parametrize("age", [float("inf"), float("nan"), 1e18, -1e18])
def test_is_stale_rejects_unusable_max_age(age):
    from datetime import datetime, timezone

    now = datetime(2026, 11, 19, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="max_age_days"):
        freshness.is_stale("2026-10-19T00:00:00Z", age, now)


def test_is_stale_validates_max_age_before_parsing():
    with pytest.raises(ValueError, match="max_age_days"):
        freshness.is_stale("garbage", float("nan"))
    with pytest.raises(ValueError, match="max_age_days"):
        freshness.is_stale("garbage", -1)
    with pytest.raises(ValueError, match="max_age_days"):
        freshness.is_stale("garbage", freshness.MAX_AGE_DAYS_LIMIT + 1)
    assert freshness.is_stale("garbage", 0) is True


@pytest.mark.parametrize("bad", ["abc", None, float("inf"), -0.1, 36501, "nan", True, False])
def test_check_max_age_days_rejects(bad):
    with pytest.raises(ValueError, match="36500"):
        freshness.check_max_age_days(bad)


def test_check_max_age_days_accepts_bounds():
    assert freshness.check_max_age_days("0") == 0.0
    assert freshness.check_max_age_days(36500) == 36500.0


def test_cache_normalises_trailing_slash_in_base_url(tmp_path):
    cache = tmp_path / "verse.json"
    freshness.write_cache(cache, "2026-11-19T00:00:00Z", VERSE, "https://a.example/")
    assert json.loads(cache.read_text())["base_url"] == "https://a.example"
    expected = ("2026-11-19T00:00:00Z", VERSE)
    assert freshness.read_cache(cache, "https://a.example//") == expected
    assert freshness.read_cache(cache, "https://a.example") == expected


def test_future_retrieved_at_is_stale():
    from datetime import datetime, timezone

    now = datetime(2026, 11, 1, tzinfo=timezone.utc)
    assert freshness.is_stale("2999-01-01T00:00:00Z", 30, now)
    assert freshness.is_stale("2026-11-01T00:10:00Z", 30, now)
    assert not freshness.is_stale("2026-11-01T00:02:00Z", 30, now)  # small clock skew


def test_read_cache_treats_deeply_nested_json_as_corrupt(tmp_path):
    path = tmp_path / "verse.json"
    path.write_text("[" * 200000 + "]" * 200000)
    assert freshness.read_cache(path) is None


def test_main_treats_deeply_nested_verse_as_clean_error(tmp_path, capsys):
    path = tmp_path / "verse.json"
    path.write_text("[" * 200000 + "]" * 200000)
    assert freshness.main(["county", str(path), "--path", "/us/nj/camden"]) == 1
    err = capsys.readouterr().err
    assert err.startswith("freshness:") and len(err.strip().splitlines()) == 1
