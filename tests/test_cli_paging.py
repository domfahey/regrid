import json

import httpx
import pytest

from regrid import cli
from regrid.client import RegridClient

POINT = ["point", "--lat", "30", "--lon", "-90"]


def feats(*ids):
    return [{"type": "Feature", "id": i, "properties": {}} for i in ids]


def install(monkeypatch, pages):
    seen = []

    def handle(request):
        seen.append(request)
        body = pages[min(len(seen), len(pages)) - 1]
        return httpx.Response(
            200, json={"parcels": {"type": "FeatureCollection", "features": body}}
        )

    monkeypatch.setenv("REGRID_TOKEN", "secret")
    monkeypatch.setattr(
        cli, "RegridClient", lambda **kw: RegridClient(**kw, transport=httpx.MockTransport(handle))
    )
    return seen


def test_normal_paging(monkeypatch, capsys):
    seen = install(monkeypatch, [feats(1, 10), feats(11, 20), feats(21, 30)])
    code = cli.main([*POINT, "--max-records", "5", "--options", '{"limit":2}'])
    out, err = capsys.readouterr()
    assert code == 0
    data = json.loads(out)
    assert data["pages"] == 3 and data["complete"] is True
    assert [f["id"] for f in data["parcels"]["features"]] == [1, 10, 11, 20, 21]
    assert data["parcels"]["type"] == "FeatureCollection"
    assert len(seen) == 3
    assert "offset_id" not in seen[0].url.params
    assert seen[1].url.params["offset_id"] == "10"
    assert seen[2].url.params["offset_id"] == "20"
    assert "regrid: up to 3 requests for 5 records" in err
    assert "regrid: requests made: 3" in err
    assert "secret" not in err


def test_requires_limit(monkeypatch, capsys):
    seen = install(monkeypatch, [feats(1)])
    assert cli.main([*POINT, "--max-records", "5"]) == 1
    assert seen == []
    assert "limit" in capsys.readouterr().err


def test_repeated_cursor_stops_at_k(monkeypatch, capsys):
    seen = install(monkeypatch, [feats(1, 7), feats(7, 7)])
    code = cli.main([*POINT, "--max-records", "6", "--options", '{"limit":2}'])
    assert code == 0
    assert len(seen) == 2
    assert "requests made: 2" in capsys.readouterr().err


def test_missing_cursor_stops(monkeypatch, capsys):
    seen = install(monkeypatch, [[{"type": "Feature", "properties": {}}, {"type": "Feature"}]])
    code = cli.main([*POINT, "--max-records", "6", "--options", '{"limit":2}'])
    out, err = capsys.readouterr()
    assert code == 0
    assert len(seen) == 1
    assert "regrid: paging stopped: no cursor in response" in err
    assert json.loads(out)["pages"] == 1


def test_short_page_stops(monkeypatch):
    seen = install(monkeypatch, [feats(1, 2), feats(3)])
    assert cli.main([*POINT, "--max-records", "9", "--options", '{"limit":2}']) == 0
    assert len(seen) == 2


@pytest.mark.parametrize(
    "argv",
    [
        ["point", "--geojson", '{"type":"Point","coordinates":[0,0]}', "--method", "POST"],
        ["owner", "smith"],
        ["address", "1 Main"],
    ],
)
def test_unsupported_rejected_before_request(monkeypatch, argv):
    seen = install(monkeypatch, [feats(1)])
    assert cli.main([*argv, "--max-records", "5", "--options", '{"limit":2}']) in (1, 2)
    assert seen == []


@pytest.mark.parametrize("value", ["0", "-1", "x"])
def test_bad_max_records(monkeypatch, value):
    seen = install(monkeypatch, [feats(1)])
    assert cli.main([*POINT, "--max-records", value, "--options", '{"limit":2}']) in (1, 2)
    assert seen == []


@pytest.mark.parametrize("limit", ['"2"', "0", "true"])
def test_bad_limit(monkeypatch, limit):
    seen = install(monkeypatch, [feats(1)])
    assert cli.main([*POINT, "--max-records", "5", "--options", '{"limit":%s}' % limit]) == 1
    assert seen == []


def test_area_and_query(monkeypatch):
    seen = install(monkeypatch, [feats(1, 2), feats(3, 4)])
    geo = '{"type":"Point","coordinates":[1,2]}'
    area = ["area", "--geojson", geo, "--max-records", "4", "--options", '{"limit":2}']
    assert cli.main(area) == 0
    query = ["query", "--fields", '{"geoid":{"eq":"48113"}}', "--max-records", "2"]
    assert cli.main([*query, "--options", '{"limit":2}']) == 0
    assert len(seen) == 3


def test_mid_paging_error_prints_partial(monkeypatch, capsys):
    seen = []

    def handle(request):
        seen.append(request)
        if len(seen) == 2:
            return httpx.Response(500, text="boom")
        return httpx.Response(
            200, json={"parcels": {"type": "FeatureCollection", "features": feats(1, 10)}}
        )

    monkeypatch.setenv("REGRID_TOKEN", "secret")
    monkeypatch.setattr(
        cli, "RegridClient", lambda **kw: RegridClient(**kw, transport=httpx.MockTransport(handle))
    )
    code = cli.main([*POINT, "--max-records", "6", "--options", '{"limit":2}'])
    out, err = capsys.readouterr()
    assert code == 1
    data = json.loads(out)
    assert data["complete"] is False and data["pages"] == 1
    assert [f["id"] for f in data["parcels"]["features"]] == [1, 10]
    assert err.count("regrid: requests made:") == 1
    assert err.rstrip().splitlines()[-1] == f"regrid: requests made: {len(seen)}"
    assert "secret" not in err


def test_cursor_not_advancing_stops(monkeypatch, capsys):
    seen = install(monkeypatch, [feats(1, 7), feats(2, 7), feats(3, 4)])
    code = cli.main([*POINT, "--max-records", "6", "--options", '{"limit":2}'])
    out, err = capsys.readouterr()
    assert code == 0 and len(seen) == 2
    assert "regrid: paging stopped: cursor did not advance" in err
    assert json.loads(out)["complete"] is True


def test_repeated_first_feature_stops(monkeypatch, capsys):
    seen = install(monkeypatch, [feats(1, 7), feats(1, 8), feats(3, 4)])
    assert cli.main([*POINT, "--max-records", "6", "--options", '{"limit":2}']) == 0
    assert len(seen) == 2
    assert "cursor did not advance" in capsys.readouterr().err
