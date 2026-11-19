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
    seen = install(monkeypatch, [feats(1, 10), feats(11, 20), feats(21)])
    code = cli.main([*POINT, "--max-records", "5", "--options", '{"limit":2}'])
    out, err = capsys.readouterr()
    assert code == 0
    data = json.loads(out)
    assert data["pages"] == 3 and data["complete"] is True
    assert [f["id"] for f in data["parcels"]["features"]] == [1, 10, 11, 20, 21]
    assert data["parcels"]["type"] == "FeatureCollection"
    assert len(seen) == 3
    assert seen[0].url.params["offset_id"] == "0"
    assert seen[1].url.params["offset_id"] == "10"
    assert seen[2].url.params["offset_id"] == "20"
    assert [r.url.params["limit"] for r in seen] == ["2", "2", "1"]
    assert "regrid: up to 3 requests for 5 records" in err
    assert "regrid: requests made: 3" in err
    assert "secret" not in err


def test_requires_limit(monkeypatch, capsys):
    seen = install(monkeypatch, [feats(1)])
    assert cli.main([*POINT, "--max-records", "5"]) == 1
    assert seen == []
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        "regrid: --max-records requires a positive count and an integer limit in --options\n"
        "regrid: requests made: 0\n"
    )


def test_repeated_cursor_stops_at_k(monkeypatch, capsys):
    seen = install(monkeypatch, [feats(1, 7), feats(7, 7)])
    code = cli.main([*POINT, "--max-records", "6", "--options", '{"limit":2}'])
    out, err = capsys.readouterr()
    assert code == 0
    assert len(seen) == 2
    assert seen[1].url.params["offset_id"] == "7"
    data = json.loads(out)
    assert [f["id"] for f in data["parcels"]["features"]] == [1, 7]
    assert data["complete"] is False and data["pages"] == 2
    assert "regrid: paging stopped: results not in cursor order" in err
    assert err.splitlines()[-1] == "regrid: requests made: 2"


def test_missing_cursor_stops(monkeypatch, capsys):
    seen = install(monkeypatch, [[{"type": "Feature", "properties": {}}, {"type": "Feature"}]])
    code = cli.main([*POINT, "--max-records", "6", "--options", '{"limit":2}'])
    out, err = capsys.readouterr()
    assert code == 0
    assert len(seen) == 1
    assert "regrid: paging stopped: no cursor in response" in err
    data = json.loads(out)
    assert data["pages"] == 1 and data["complete"] is False
    assert len(data["parcels"]["features"]) == 2


def test_short_page_stops_and_is_complete(monkeypatch, capsys):
    seen = install(monkeypatch, [feats(1, 2), feats(3), feats(4, 5)])
    assert cli.main([*POINT, "--max-records", "9", "--options", '{"limit":2}']) == 0
    out, err = capsys.readouterr()
    assert len(seen) == 2
    assert seen[1].url.params["offset_id"] == "2"
    data = json.loads(out)
    assert [f["id"] for f in data["parcels"]["features"]] == [1, 2, 3]
    assert data["complete"] is True and data["pages"] == 2
    assert err.splitlines()[-1] == "regrid: requests made: 2"


def test_post_point_rejected_before_request(monkeypatch, capsys):
    seen = install(monkeypatch, [feats(1)])
    argv = ["point", "--geojson", '{"type":"Point","coordinates":[0,0]}', "--method", "POST"]
    assert cli.main([*argv, "--max-records", "5", "--options", '{"limit":2}']) == 1
    captured = capsys.readouterr()
    assert seen == [] and captured.out == ""
    assert captured.err == (
        "regrid: --max-records is not supported for POST point searches\nregrid: requests made: 0\n"
    )


@pytest.mark.parametrize("argv", [["owner", "smith"], ["address", "1 Main"]])
def test_max_records_unavailable_on_other_commands(monkeypatch, capsys, argv):
    seen = install(monkeypatch, [feats(1)])
    assert cli.main([*argv, "--max-records", "5", "--options", '{"limit":2}']) == 2
    captured = capsys.readouterr()
    assert seen == [] and captured.out == ""
    assert "unrecognized arguments: --max-records 5" in captured.err


@pytest.mark.parametrize("value", ["0", "-1"])
def test_non_positive_max_records(monkeypatch, capsys, value):
    seen = install(monkeypatch, [feats(1)])
    assert cli.main([*POINT, "--max-records", value, "--options", '{"limit":2}']) == 1
    captured = capsys.readouterr()
    assert seen == [] and captured.out == ""
    assert captured.err == (
        "regrid: --max-records requires a positive count and an integer limit in --options\n"
        "regrid: requests made: 0\n"
    )


def test_non_integer_max_records(monkeypatch, capsys):
    seen = install(monkeypatch, [feats(1)])
    assert cli.main([*POINT, "--max-records", "x", "--options", '{"limit":2}']) == 2
    captured = capsys.readouterr()
    assert seen == [] and captured.out == ""
    assert "argument --max-records: invalid int value: 'x'" in captured.err


@pytest.mark.parametrize("limit", ['"2"', "0", "true"])
def test_bad_limit(monkeypatch, capsys, limit):
    seen = install(monkeypatch, [feats(1)])
    assert cli.main([*POINT, "--max-records", "5", "--options", '{"limit":%s}' % limit]) == 1
    captured = capsys.readouterr()
    assert seen == [] and captured.out == ""
    assert captured.err == (
        "regrid: --max-records requires a positive count and an integer limit in --options\n"
        "regrid: requests made: 0\n"
    )


def test_area_and_query(monkeypatch, capsys):
    seen = install(monkeypatch, [feats(1, 2), feats(3, 4)])
    geo = '{"type":"Point","coordinates":[1,2]}'
    area = ["area", "--geojson", geo, "--max-records", "4", "--options", '{"limit":2}']
    assert cli.main(area) == 0
    area_data = json.loads(capsys.readouterr().out)
    assert [f["id"] for f in area_data["parcels"]["features"]] == [1, 2, 3, 4]
    query = ["query", "--fields", '{"geoid":{"eq":"48113"}}', "--max-records", "2"]
    assert cli.main([*query, "--options", '{"limit":2}']) == 0
    assert len(seen) == 3
    assert [r.url.path for r in seen] == ["/api/v2/parcels/area"] * 2 + ["/api/v2/parcels/query"]
    assert [r.url.params["limit"] for r in seen] == ["2", "2", "2"]
    assert [r.url.params.get("offset_id") for r in seen] == ["0", "2", "0"]
    assert seen[0].url.params["geojson"] == geo
    assert seen[2].url.params["fields[geoid][eq]"] == "48113"


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
    assert "regrid: paging stopped: results not in cursor order" in err
    assert json.loads(out)["complete"] is False


def test_page_adding_nothing_new_stops_incomplete(monkeypatch, capsys):
    seen = install(monkeypatch, [feats(1, 7), feats(1, 7), feats(3, 4)])
    assert cli.main([*POINT, "--max-records", "6", "--options", '{"limit":2}']) == 0
    out, err = capsys.readouterr()
    assert len(seen) == 2 and "results not in cursor order" in err
    data = json.loads(out)
    assert data["complete"] is False and [f["id"] for f in data["parcels"]["features"]] == [1, 7]


def test_inclusive_offset_page_is_deduplicated_and_flagged(monkeypatch, capsys):
    """A server that (unexpectedly) repeats the cursor record is de-duplicated and flagged."""
    seen = install(monkeypatch, [feats(1, 10), feats(10, 11)])
    assert cli.main([*POINT, "--max-records", "3", "--options", '{"limit":2}']) == 0
    out, err = capsys.readouterr()
    data = json.loads(out)
    assert [f["id"] for f in data["parcels"]["features"]] == [1, 10, 11]
    assert data["complete"] is False and len(seen) == 2
    assert "regrid: paging stopped: results not in cursor order" in err


def test_short_page_of_only_repeats_stops_incomplete(monkeypatch, capsys):
    seen = install(monkeypatch, [feats(1, 2), feats(2)])
    assert cli.main([*POINT, "--max-records", "4", "--options", '{"limit":2}']) == 0
    out, err = capsys.readouterr()
    data = json.loads(out)
    assert [f["id"] for f in data["parcels"]["features"]] == [1, 2]
    assert data["complete"] is False and len(seen) == 2
    assert "results not in cursor order" in err


def test_features_without_id_are_kept(monkeypatch, capsys):
    bare = [{"type": "Feature"}, {"type": "Feature", "id": 5}]
    install(monkeypatch, [bare, [{"type": "Feature"}]])
    assert cli.main([*POINT, "--max-records", "9", "--options", '{"limit":2}']) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["parcels"]["features"] == [
        {"type": "Feature"},
        {"type": "Feature", "id": 5},
        {"type": "Feature"},
    ]


def test_incomplete_when_request_cap_reached_short_of_total(monkeypatch, capsys):
    install(monkeypatch, [feats(1, 2), feats(2, 3)])
    assert cli.main([*POINT, "--max-records", "4", "--options", '{"limit":2}']) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["complete"] is False and len(data["parcels"]["features"]) == 3


def test_full_result_at_requested_total_is_complete(monkeypatch, capsys):
    seen = install(monkeypatch, [feats(1, 2), feats(3, 4)])
    assert cli.main([*POINT, "--max-records", "4", "--options", '{"limit":2}']) == 0
    data = json.loads(capsys.readouterr().out)
    assert len(seen) == 2 and data["complete"] is True and data["pages"] == 2
    assert [f["id"] for f in data["parcels"]["features"]] == [1, 2, 3, 4]


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


@pytest.mark.parametrize("bad", ["a", -5, True, 1.5, "", "-5", "+5", "1e3", " 5", "\u0663", None])
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
    assert [r.url.params["limit"] for r in seen] == ["2", "1"]  # never more than still needed
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


def test_exclusive_cursor_reaches_exact_total(monkeypatch, capsys):
    ids = list(range(1, 20))
    seen = []

    def handle(request):
        seen.append(request)
        start = request.url.params.get("offset_id")
        rows = [i for i in ids if start is None or i > int(start)]
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
    assert [r.url.params["limit"] for r in seen] == ["2", "2", "1"]
    assert [r.url.params["offset_id"] for r in seen] == ["0", "2", "4"]


def _spatial_server(ids, order_after=None):
    """Fake API: no offset_id => descending ids (spatial); offset_id => ascending ids > it."""

    def handle(request):
        start = request.url.params.get("offset_id")
        limit = int(request.url.params["limit"])
        if start is None:
            rows = sorted(ids, reverse=True)[:limit]
        else:
            rows = [i for i in sorted(ids) if i > int(start)][:limit]
            if order_after is not None:
                rows = order_after(rows)
        body = {"parcels": {"type": "FeatureCollection", "features": feats(*rows)}}
        return httpx.Response(200, json=body)

    return handle


@pytest.mark.parametrize("command", ["point", "area", "query"])
def test_first_page_starts_at_zero_so_no_gaps(monkeypatch, capsys, command):
    seen = _counting(monkeypatch, lambda request, _n: _spatial_server(range(1, 8))(request))
    geo = '{"type":"Point","coordinates":[1,2]}'
    extra = {
        "point": POINT,
        "area": ["area", "--geojson", geo],
        "query": ["query", "--fields", '{"geoid":{"eq":"48113"}}'],
    }[command]
    assert cli.main([*extra, "--max-records", "7", "--options", '{"limit":3}']) == 0
    data = json.loads(capsys.readouterr().out)
    assert [f["id"] for f in data["parcels"]["features"]] == [1, 2, 3, 4, 5, 6, 7]
    assert data["complete"] is True
    assert [r.url.params["offset_id"] for r in seen] == ["0", "3", "6"]


@pytest.mark.parametrize("scramble", [lambda rows: rows[::-1], lambda rows: [rows[0]] * 2])
def test_unordered_pages_stop_incomplete(monkeypatch, capsys, scramble):
    _counting(monkeypatch, lambda request, _n: _spatial_server(range(1, 8), scramble)(request))
    assert cli.main([*POINT, "--max-records", "6", "--options", '{"limit":2}']) == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["complete"] is False
    assert "regrid: paging stopped: results not in cursor order" in captured.err
    assert captured.err.rstrip().splitlines()[-1].startswith("regrid: requests made: ")


def test_page_not_after_cursor_stops_incomplete(monkeypatch, capsys):
    install(monkeypatch, [feats(5, 6), feats(3, 4)])
    assert cli.main([*POINT, "--max-records", "4", "--options", '{"limit":2}']) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["complete"] is False
    assert "regrid: paging stopped: results not in cursor order" in captured.err


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
    # A server that repeats the cursor yields fewer new records than asked: never claim complete.
    assert json.loads(out)["complete"] is (not inclusive or total <= limit)
    assert cap == -(-total // limit)
    if not inclusive:
        assert len(seen) == cap


def test_limit_one_rejected_before_any_request(monkeypatch, capsys):
    seen = _counting(monkeypatch, _inclusive)
    assert cli.main([*POINT, "--max-records", "5", "--options", '{"limit":1}']) == 1
    err = capsys.readouterr().err
    assert seen == [] and "limit of at least 2" in err and "requests made: 0" in err


def test_paging_validation_surfaces_non_paging_errors(monkeypatch, capsys):
    seen = install(monkeypatch, [feats(1, 2)])
    argv = ["query", "--fields", '{"nope_field":{"eq":"x"}}', "--validate-fields"]
    assert cli.main([*argv, "--max-records", "4", "--options", '{"limit":2}']) == 1
    err = capsys.readouterr().err
    assert seen == [] and "requests made: 0" in err
    assert "Field is not queryable in the local catalog" in err
    assert "incompatible" not in err and "nope_field" not in err
    order = ["query", "--fields", '{"yearbuilt":{"order":"ASC"}}', "--validate-fields"]
    assert cli.main([*order, "--max-records", "4", "--options", '{"limit":2}']) == 1
    assert "--max-records is incompatible with these query filters" in capsys.readouterr().err


def _paged(monkeypatch, first, second):
    pages = [first, second]
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(200, json=pages[min(len(seen), 2) - 1])

    monkeypatch.setenv("REGRID_TOKEN", "secret")
    monkeypatch.setattr(
        cli, "RegridClient", lambda **kw: RegridClient(**kw, transport=httpx.MockTransport(handle))
    )


def _page(ids, **extra):
    return {"parcels": {"type": "FeatureCollection", "features": feats(*ids)}, **extra}


def test_merge_adds_keys_first_seen_on_later_pages(monkeypatch, capsys):
    coll = {"type": "FeatureCollection", "features": [{"id": 9}]}
    _paged(monkeypatch, _page([1, 2]), _page([2, 3], extras=[1], buildings=coll))
    assert cli.main([*POINT, "--max-records", "3", "--options", '{"limit":2}']) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["extras"] == [1] and data["buildings"]["features"] == [{"id": 9}]


def test_merge_shape_mismatch_keeps_first_and_notes_once(monkeypatch, capsys):
    first = _page([1, 2], extras=[1], buildings={"features": [{"id": 8}]})
    second = _page([2, 3], extras={"a": 1}, buildings=[5])
    _paged(monkeypatch, first, second)
    assert cli.main([*POINT, "--max-records", "3", "--options", '{"limit":2}']) == 0
    out, err = capsys.readouterr()
    data = json.loads(out)
    assert data["extras"] == [1] and data["buildings"]["features"] == [{"id": 8}]
    assert "regrid: paging note: extras shape changed; later pages ignored for it" in err
    assert "regrid: paging note: buildings shape changed; later pages ignored for it" in err
    assert err.count("paging note: extras") == 1


def test_string_digit_cursor_is_accepted(monkeypatch, capsys):
    seen = install(monkeypatch, [feats(1, "10"), feats("11", "12")])
    assert cli.main([*POINT, "--max-records", "3", "--options", '{"limit":2}']) == 0
    data = json.loads(capsys.readouterr().out)
    assert [f["id"] for f in data["parcels"]["features"]] == [1, "10", "11"]
    assert seen[1].url.params["offset_id"] == "10" and data["complete"] is True


def _uuid_feature(fid, uuid):
    return {"type": "Feature", "id": fid, "properties": {"ll_uuid": uuid}}


def test_inclusive_cursor_does_not_duplicate_siblings(monkeypatch, capsys):
    """Safety net for a server that (unexpectedly) repeats the cursor record and its siblings."""

    def fcoll(*features):
        return {"type": "FeatureCollection", "features": list(features)}

    b1, b10, b11 = ({"type": "Feature", "id": f"b{n}", "properties": {}} for n in (1, 10, 11))
    z10 = {"type": "Feature", "properties": {"ll_uuid": "u10"}}  # no id: matched by JSON form
    two_in_one = {"type": "Feature", "properties": {"ll_uuid": "u11", "n": 1}}
    other = {"type": "Feature", "properties": {"ll_uuid": "u11", "n": 2}}
    bodies = [
        {
            "parcels": fcoll(*feats(1, 10)),
            "buildings": fcoll(b1, b10),
            "zoning": fcoll(z10),
            "tags": ["a", {"k": 1}],
        },
        {
            "parcels": fcoll(*feats(10, 11)),
            "buildings": fcoll(b10, b11),
            "zoning": fcoll(z10, two_in_one, other),
            "tags": [{"k": 1}, "b"],
        },
    ]
    install_bodies(monkeypatch, bodies)
    assert cli.main([*POINT, "--max-records", "3", "--options", '{"limit":2}']) == 0
    data = json.loads(capsys.readouterr().out)
    assert [f["id"] for f in data["buildings"]["features"]] == ["b1", "b10", "b11"]
    assert data["zoning"]["features"] == [z10, two_in_one, other]
    assert data["tags"] == ["a", {"k": 1}, "b"]


def test_siblings_of_trimmed_parcels_are_dropped(monkeypatch, capsys):
    def body(parcels, buildings):
        return {
            "parcels": {"type": "FeatureCollection", "features": parcels},
            "buildings": {"type": "FeatureCollection", "features": buildings},
        }

    def building(bid, uuid):
        return {"type": "Feature", "id": bid, "properties": {"ll_uuid": uuid}}

    first = body([_uuid_feature(1, "u1"), _uuid_feature(2, "u2")], [building("a", "u1")])
    second = body(
        [_uuid_feature(3, "u3"), _uuid_feature(4, "u4")],
        [building("b", "u3"), building("c", "u4"), {"type": "Feature", "id": "d"}],
    )
    install_bodies(monkeypatch, [first, second])
    assert cli.main([*POINT, "--max-records", "3", "--options", '{"limit":2}']) == 0
    data = json.loads(capsys.readouterr().out)
    assert [f["id"] for f in data["parcels"]["features"]] == [1, 2, 3]
    assert [f["id"] for f in data["buildings"]["features"]] == ["a", "b", "d"]


def test_building_ll_uuids_list_links_siblings(monkeypatch, capsys):
    def body(parcels, buildings):
        return {
            "parcels": {"type": "FeatureCollection", "features": parcels},
            "buildings": {"type": "FeatureCollection", "features": buildings},
        }

    def building(bid, uuids):
        return {"type": "Feature", "id": bid, "properties": {"ll_uuids": uuids}}

    first = body([_uuid_feature(1, "u1"), _uuid_feature(2, "u2")], [building("a", ["u1"])])
    second = body(
        [_uuid_feature(3, "u3"), _uuid_feature(4, "u4")],
        [
            building("b", ["u3"]),
            building("gone", ["u4"]),
            building("straddle", ["u3", "u4"]),
            building("empty", []),
        ],
    )
    install_bodies(monkeypatch, [first, second])
    assert cli.main([*POINT, "--max-records", "3", "--options", '{"limit":2}']) == 0
    data = json.loads(capsys.readouterr().out)
    ids = [f["id"] for f in data["buildings"]["features"]]
    assert ids == ["a", "b", "straddle", "empty"]


def test_extend_new_skips_duplicates_within_incoming_page():
    current = [{"id": 1}]
    cli._extend_new(current, [{"id": 1}, {"id": 2}, {"id": 2}, {"id": 3}])
    assert current == [{"id": 1}, {"id": 2}, {"id": 3}]


def test_return_count_false_is_allowed(monkeypatch, capsys):
    seen = install(monkeypatch, [feats(1, 2)])
    opts = '{"limit":2,"return_count":false}'
    assert cli.main([*POINT, "--max-records", "2", "--options", opts]) == 0
    assert len(seen) == 1 and seen[0].url.params["return_count"] == "false"


def test_first_page_is_deduplicated_like_later_pages(monkeypatch, capsys):
    def fcoll(*features):
        return {"type": "FeatureCollection", "features": list(features)}

    b1 = {"type": "Feature", "id": "b1", "properties": {}}
    bodies = [
        {
            "parcels": fcoll(*feats(1, 2)),
            "buildings": fcoll(b1, dict(b1)),
            "tags": ["a", "a", {"k": 1}, {"k": 1}],
        }
    ]
    install_bodies(monkeypatch, bodies)
    assert cli.main([*POINT, "--max-records", "2", "--options", '{"limit":2}']) == 0
    data = json.loads(capsys.readouterr().out)
    assert [f["id"] for f in data["buildings"]["features"]] == ["b1"]
    assert data["tags"] == ["a", "a", {"k": 1}]


def test_later_pages_keep_repeated_non_dict_items():
    current = ["a"]
    cli._extend_new(current, ["a", "b", {"id": 1}, {"id": 1}])
    assert current == ["a", "a", "b", {"id": 1}]


def _building(uuid_list):
    return {"type": "Feature", "properties": {"ll_uuids": uuid_list}}


def _trim_siblings(buildings, kept, trimmed):
    merged = {"buildings": {"type": "FeatureCollection", "features": list(buildings)}}
    cli._drop_trimmed_siblings(merged, kept, trimmed)
    return merged["buildings"]["features"]


def test_sibling_dropped_only_when_it_references_dropped_and_no_kept_uuid():
    kept, trimmed = [_uuid_feature(3, "u3")], [_uuid_feature(4, "u4")]
    mixed_unfetched = _building(["u4", "u9"])
    straddle = _building(["u3", "u4"])
    assert _trim_siblings([mixed_unfetched, straddle], kept, trimmed) == [straddle]
    assert _trim_siblings([straddle], kept, trimmed) == [straddle]


def test_parcel_dedupe_handles_unhashable_ids(monkeypatch, capsys):
    def with_ids(*ids):
        return {
            "parcels": {
                "type": "FeatureCollection",
                "features": [{"type": "Feature", "id": i, "properties": {}} for i in ids],
            }
        }

    first, second = with_ids({"k": 1}, 5), with_ids(5, 6)
    _paged(monkeypatch, first, second)
    code = cli.main([*POINT, "--max-records", "3", "--options", '{"limit":2}'])
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert [f["id"] for f in data["parcels"]["features"]] == [{"k": 1}, 5, 6]


def test_existing_response_keys_are_never_overwritten(monkeypatch, capsys):
    page = _page([1, 2], pages="s", complete="c", response_pages="mine", response_complete="mine-c")
    _paged(monkeypatch, page, page)
    assert cli.main([*POINT, "--max-records", "2", "--options", '{"limit":2}']) == 0
    out, err = capsys.readouterr()
    data = json.loads(out)
    assert data["response_pages"] == "mine"
    assert data["pages"] == 1 and data["complete"] is True
    assert data["response_complete"] == "mine-c"
    note = (
        "regrid: paging note: response pages/complete not kept "
        "(response_pages/response_complete already present)"
    )
    assert err.splitlines().count(note) == 1


@pytest.mark.parametrize(
    ("existing", "kept", "dropped"),
    [("response_pages", "complete", "pages"), ("response_complete", "pages", "complete")],
)
def test_paging_note_names_only_the_key_not_kept(monkeypatch, capsys, existing, kept, dropped):
    page = _page([1, 2], pages="s", complete="c", **{existing: "mine"})
    _paged(monkeypatch, page, page)
    assert cli.main([*POINT, "--max-records", "2", "--options", '{"limit":2}']) == 0
    lines = capsys.readouterr().err.splitlines()
    assert (
        f"regrid: paging note: response {dropped} not kept (response_{dropped} already present)"
        in lines
    )
    assert f"regrid: paging note: response {kept} kept as response_{kept}" in lines


def test_trimmed_siblings_use_fields_only_parcel_uuids():
    def parcel(uuid):
        return {"id": 1, "properties": {"fields": {"ll_uuid": uuid}}}

    kept, trimmed = [parcel("u3")], [parcel("u4")]
    assert _trim_siblings([_building(["u3", "u4"])], kept, trimmed) == [_building(["u3", "u4"])]
    assert _trim_siblings([_building(["u4"])], kept, trimmed) == []


def test_paged_search_rejects_limit_above_client_max_before_requests(monkeypatch, capsys):
    seen = install(monkeypatch, [feats(1, 10)])
    code = cli.main([*POINT, "--max-records", "5", "--options", '{"limit":5000}'])
    assert code == 1 and seen == []
    assert "Invalid Regrid request parameters" in capsys.readouterr().err


def test_cli_paging_uses_client_max_limit(monkeypatch, capsys):
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(
            200, json={"parcels": {"type": "FeatureCollection", "features": feats(1, 10)}}
        )

    monkeypatch.setenv("REGRID_TOKEN", "secret")
    monkeypatch.setattr(
        cli,
        "RegridClient",
        lambda **kw: RegridClient(**{**kw, "max_limit": 10}, transport=httpx.MockTransport(handle)),
    )
    code = cli.main([*POINT, "--max-records", "20", "--options", '{"limit":50}'])
    assert code == 1 and seen == []
    assert "limit exceeds configured maximum" in capsys.readouterr().err
    assert cli.main([*POINT, "--max-records", "2", "--options", '{"limit":10}']) == 0
    assert len(seen) == 1


def test_trimmed_siblings_never_collect_empty_uuids():
    def parcel(uuid):
        return {"id": 1, "properties": {"ll_uuid": uuid}}

    kept, trimmed = [parcel("u3")], [parcel("")]
    # an empty parcel ll_uuid is not collected, so a sibling listing "" is not dropped
    assert _trim_siblings([_building([""])], kept, trimmed) == [_building([""])]
    kept, trimmed = [parcel("")], [parcel("u4")]
    assert _trim_siblings([_building(["", "u4"])], kept, trimmed) == []
    assert _trim_siblings([_building(["u4"])], kept, trimmed) == []


def test_paging_note_reflects_response_pages_added_on_later_page(monkeypatch, capsys):
    first = _page([1, 2], pages="s")
    second = _page([2, 3], response_pages=[1])
    _paged(monkeypatch, first, second)
    assert cli.main([*POINT, "--max-records", "3", "--options", '{"limit":2}']) == 0
    out, err = capsys.readouterr()
    data = json.loads(out)
    assert data["response_pages"] == [1] and data["pages"] == 2
    lines = err.splitlines()
    assert "regrid: paging note: response pages not kept (response_pages already present)" in lines
    assert not any("kept as response_pages" in line for line in lines)
    assert sum("paging note: response" in line for line in lines) == 1


def test_paging_note_for_pages_first_seen_on_later_page(monkeypatch, capsys):
    _paged(monkeypatch, _page([1, 2]), _page([3], pages=[7], complete=[8]))
    assert cli.main([*POINT, "--max-records", "3", "--options", '{"limit":2}']) == 0
    out, err = capsys.readouterr()
    data = json.loads(out)
    assert data["response_pages"] == [7] and data["response_complete"] == [8]
    assert data["pages"] == 2 and data["complete"] is True
    note = "regrid: paging note: response pages/complete kept as response_pages/response_complete"
    assert err.splitlines().count(note) == 1
