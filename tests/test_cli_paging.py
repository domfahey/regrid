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
    assert "regrid: up to 4 requests for 5 records" in err
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
    assert json.loads(out)["complete"] is False


def test_page_adding_nothing_new_stops_incomplete(monkeypatch, capsys):
    seen = install(monkeypatch, [feats(1, 7), feats(1, 7), feats(3, 4)])
    assert cli.main([*POINT, "--max-records", "6", "--options", '{"limit":2}']) == 0
    out, err = capsys.readouterr()
    assert len(seen) == 2 and "cursor did not advance" in err
    data = json.loads(out)
    assert data["complete"] is False and [f["id"] for f in data["parcels"]["features"]] == [1, 7]


def test_inclusive_offset_page_is_deduplicated(monkeypatch, capsys):
    seen = install(monkeypatch, [feats(1, 10), feats(10, 11)])
    assert cli.main([*POINT, "--max-records", "3", "--options", '{"limit":2}']) == 0
    data = json.loads(capsys.readouterr().out)
    assert [f["id"] for f in data["parcels"]["features"]] == [1, 10, 11]
    assert data["complete"] is True and len(seen) == 2


def test_features_without_id_are_kept(monkeypatch, capsys):
    bare = [{"type": "Feature"}, {"type": "Feature", "id": 5}]
    install(monkeypatch, [bare, [{"type": "Feature"}]])
    assert cli.main([*POINT, "--max-records", "9", "--options", '{"limit":2}']) == 0
    assert len(json.loads(capsys.readouterr().out)["parcels"]["features"]) == 3


def test_incomplete_when_request_cap_reached_short_of_total(monkeypatch, capsys):
    install(monkeypatch, [feats(1, 2), feats(2, 3)])
    assert cli.main([*POINT, "--max-records", "4", "--options", '{"limit":2}']) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["complete"] is False and len(data["parcels"]["features"]) == 3


def test_missing_cursor_is_incomplete(monkeypatch, capsys):
    install(monkeypatch, [[{"type": "Feature"}, {"type": "Feature"}]])
    assert cli.main([*POINT, "--max-records", "6", "--options", '{"limit":2}']) == 0
    assert json.loads(capsys.readouterr().out)["complete"] is False


def test_short_and_full_results_are_complete(monkeypatch, capsys):
    install(monkeypatch, [feats(1, 2), feats(3)])
    assert cli.main([*POINT, "--max-records", "9", "--options", '{"limit":2}']) == 0
    assert json.loads(capsys.readouterr().out)["complete"] is True


def install_bodies(monkeypatch, bodies):
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(200, json=bodies[min(len(seen), len(bodies)) - 1])

    monkeypatch.setenv("REGRID_TOKEN", "secret")
    monkeypatch.setattr(
        cli, "RegridClient", lambda **kw: RegridClient(**kw, transport=httpx.MockTransport(handle))
    )
    return seen


def test_other_top_level_keys_are_preserved(monkeypatch, capsys):
    def body(ids, buildings):
        return {
            "parcels": {"type": "FeatureCollection", "features": feats(*ids), "extra": 1},
            "zoning": {"note": "first"},
            "buildings": buildings,
            "status": "ok",
        }

    install_bodies(monkeypatch, [body((1, 2), [{"b": 1}]), body((3, 4), [{"b": 2}])])
    assert cli.main([*POINT, "--max-records", "4", "--options", '{"limit":2}']) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["zoning"] == {"note": "first"} and data["status"] == "ok"
    assert data["buildings"] == [{"b": 1}, {"b": 2}]
    assert data["parcels"]["extra"] == 1 and data["parcels"]["type"] == "FeatureCollection"
    assert [f["id"] for f in data["parcels"]["features"]] == [1, 2, 3, 4]
    assert data["pages"] == 2 and data["complete"] is True


@pytest.mark.parametrize(
    "bad",
    [
        {"parcels": "oops"},
        {"parcels": {"features": "oops"}},
        {"parcels": {"features": [{"id": [1]}]}},
    ],
)
def test_malformed_later_page_returns_partial(monkeypatch, capsys, bad):
    good = {"parcels": {"type": "FeatureCollection", "features": feats(1, 10)}}
    seen = install_bodies(monkeypatch, [good, bad])
    code = cli.main([*POINT, "--max-records", "6", "--options", '{"limit":2}'])
    out, err = capsys.readouterr()
    assert code == 1 and len(seen) == 2
    data = json.loads(out)
    assert data["complete"] is False and data["pages"] == 1
    assert [f["id"] for f in data["parcels"]["features"]] == [1, 10]
    assert err.count("requests made:") == 1 and "Traceback" not in err
    assert err.rstrip().splitlines()[-1] == "regrid: requests made: 2"


def test_malformed_first_page_prints_no_partial(monkeypatch, capsys):
    install_bodies(monkeypatch, [{"parcels": []}])
    code = cli.main([*POINT, "--max-records", "6", "--options", '{"limit":2}'])
    out, err = capsys.readouterr()
    assert code == 1 and out == "" and "requests made: 1" in err


@pytest.mark.parametrize("body", [{}, {"parcels": {"type": "FeatureCollection"}}])
def test_page_without_parcels_or_features_is_empty(monkeypatch, capsys, body):
    install_bodies(monkeypatch, [body])
    assert cli.main([*POINT, "--max-records", "6", "--options", '{"limit":2}']) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["parcels"]["features"] == [] and data["complete"] is True


def fc(ids):
    return {"type": "FeatureCollection", "features": feats(*ids)}


def test_top_level_feature_collections_merge_across_pages(monkeypatch, capsys):
    bodies = [
        {"parcels": fc([1, 2]), "buildings": fc([11]), "zoning": None},
        {"parcels": fc([3, 4]), "buildings": fc([12]), "zoning": fc([21])},
    ]
    install_bodies(monkeypatch, bodies)
    assert cli.main([*POINT, "--max-records", "4", "--options", '{"limit":2}']) == 0
    data = json.loads(capsys.readouterr().out)
    assert [f["id"] for f in data["buildings"]["features"]] == [11, 12]
    assert [f["id"] for f in data["zoning"]["features"]] == [21]


@pytest.mark.parametrize("bad", ["a", -5, True, 1.5])
def test_invalid_cursor_id_stops_with_partial(monkeypatch, capsys, bad):
    seen = install(monkeypatch, [feats(5, bad), feats(3, 4)])
    assert cli.main([*POINT, "--max-records", "4", "--options", '{"limit":2}']) == 0
    out, err = capsys.readouterr()
    assert len(seen) == 1
    assert "regrid: paging stopped: no cursor in response" in err
    data = json.loads(out)
    assert data["complete"] is False and len(data["parcels"]["features"]) == 2


def test_order_filter_with_paging_rejected_before_request(monkeypatch, capsys):
    seen = install(monkeypatch, [feats(1, 2)])
    argv = ["query", "--fields", '{"geoid":{"order":"ASC"}}', "--validate-fields"]
    assert cli.main([*argv, "--max-records", "4", "--options", '{"limit":2}']) == 1
    err = capsys.readouterr().err
    assert seen == [] and err.count("regrid: requests made:") == 1
    assert "requests made: 0" in err and len(err.strip().splitlines()) == 2


def test_request_limit_capped_to_remaining(monkeypatch, capsys):
    seen = install(monkeypatch, [feats(1, 2), feats(3)])
    assert cli.main([*POINT, "--max-records", "3", "--options", '{"limit":2}']) == 0
    assert [r.url.params["limit"] for r in seen] == ["2", "2"]  # later pages: remaining + 1
    seen = install(monkeypatch, [feats(1, 2, 3, 4, 5)])
    assert cli.main([*POINT, "--max-records", "5", "--options", '{"limit":100}']) == 0
    assert seen[0].url.params["limit"] == "5"
    assert "up to 1 requests for 5 records" in capsys.readouterr().err


def test_return_count_with_max_records_rejected(monkeypatch, capsys):
    seen = install(monkeypatch, [feats(1, 2)])
    opts = '{"limit":2,"return_count":true}'
    assert cli.main([*POINT, "--max-records", "4", "--options", opts]) == 1
    err = capsys.readouterr().err
    assert seen == [] and err.count("regrid: requests made:") == 1
    assert "requests made: 0" in err


def test_duplicate_ids_within_page_deduplicated(monkeypatch, capsys):
    install(monkeypatch, [feats(1, 1)])
    assert cli.main([*POINT, "--max-records", "4", "--options", '{"limit":2}']) == 0
    data = json.loads(capsys.readouterr().out)
    assert [f["id"] for f in data["parcels"]["features"]] == [1]


def test_inclusive_cursor_still_reaches_exact_total(monkeypatch, capsys):
    ids = list(range(1, 20))
    seen = []

    def handle(request):
        seen.append(request)
        start = request.url.params.get("offset_id")
        rows = [i for i in ids if start is None or i >= int(start)]
        rows = rows[: int(request.url.params["limit"])]
        return httpx.Response(
            200, json={"parcels": {"type": "FeatureCollection", "features": feats(*rows)}}
        )

    monkeypatch.setenv("REGRID_TOKEN", "secret")
    monkeypatch.setattr(
        cli, "RegridClient", lambda **kw: RegridClient(**kw, transport=httpx.MockTransport(handle))
    )
    assert cli.main([*POINT, "--max-records", "5", "--options", '{"limit":2}']) == 0
    data = json.loads(capsys.readouterr().out)
    assert [f["id"] for f in data["parcels"]["features"]] == [1, 2, 3, 4, 5]
    assert data["complete"] is True
    assert seen[0].url.params["limit"] == "2"
    assert all(int(r.url.params["limit"]) <= 2 for r in seen)
    remaining = 5
    for r, got in zip(seen, (2, 1, 1, 1)):
        assert int(r.url.params["limit"]) <= remaining + 1 or r is seen[0]
        remaining -= got


def _counting(monkeypatch, handler):
    seen = []

    def handle(request):
        seen.append(request)
        return handler(request, len(seen))

    monkeypatch.setenv("REGRID_TOKEN", "secret")
    monkeypatch.setattr(
        cli, "RegridClient", lambda **kw: RegridClient(**kw, transport=httpx.MockTransport(handle))
    )
    return seen


def _inclusive(request, _n, inclusive=True):
    start = request.url.params.get("offset_id")
    low = 0 if start is None else int(start) + (0 if inclusive else 1)
    rows = [i for i in range(1, 5000) if i >= low][: int(request.url.params["limit"])]
    body = {"parcels": {"type": "FeatureCollection", "features": feats(*rows)}}
    return httpx.Response(200, json=body)


@pytest.mark.parametrize("inclusive", [True, False])
@pytest.mark.parametrize(("total", "limit"), [(5, 2), (1000, 2), (7, 3), (3, 5)])
def test_printed_cap_is_enforced_maximum(monkeypatch, capsys, inclusive, total, limit):
    seen = _counting(monkeypatch, lambda r, n: _inclusive(r, n, inclusive))
    opts = json.dumps({"limit": limit})
    assert cli.main([*POINT, "--max-records", str(total), "--options", opts]) == 0
    out, err = capsys.readouterr()
    cap = int(err.split("regrid: up to ")[1].split()[0])
    assert len(seen) <= cap
    assert json.loads(out)["complete"] is True
    if inclusive and total > limit:
        assert len(seen) == cap
    assert cap <= max(total, 1)


def test_limit_one_inclusive_cursor_stops_after_two_requests(monkeypatch, capsys):
    seen = _counting(monkeypatch, _inclusive)
    assert cli.main([*POINT, "--max-records", "5", "--options", '{"limit":1}']) == 0
    out, err = capsys.readouterr()
    assert len(seen) == 2
    assert "cursor did not advance" in err and json.loads(out)["complete"] is False
