import json

import httpx
import pytest
from map_fixtures import good_feature

from regrid import cli
from regrid.client import RegridClient, RegridDecodeError

POINT = ["point", "--lat", "30", "--lon", "-90"]


def _nested(depth):
    value = []
    for _ in range(depth):
        value = [value]
    return value


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


# Deep enough to exceed the recursion limit on every supported Python: 3.10 fails near 1000
# frames, while 3.12/3.13 only fail past the ~10k C-stack limit for the parser and encoder.
DEEP_LEVELS = 20_000


def _deep_body(depth, wrap='{"parcels":{"features":[]},"x":%s}'):
    return (wrap % ("[" * depth + "]" * depth)).encode()


# Which message appears depends on where the parser gives up (RecursionError vs invalid JSON).
DEEP = (
    "Response or input is nested too deeply",
    "Regrid returned invalid JSON",
)
# Only the freshness command can reach a decodable body that is not a verse listing.
DEEP_FRESHNESS = (*DEEP, "No verse entry found for /us/nj/camden")
BAD_INPUT = "Invalid input or output file"


def _assert_clean_failure(capsys, requests_made, message):
    out, err = capsys.readouterr()
    lines = err.splitlines()
    assert out == ""
    assert "Traceback" not in err and "secret" not in err
    assert lines.count(f"regrid: requests made: {requests_made}") == 1
    assert sum("requests made" in line for line in lines) == 1
    messages = (message,) if isinstance(message, str) else message
    assert sum(lines.count(f"regrid: {m}") for m in messages) == 1


def test_decode_deep_json_raises_decode_error():
    response = httpx.Response(200, content=_deep_body(100_000))
    with pytest.raises(RegridDecodeError) as info:
        RegridClient._decode(response)
    assert info.value.__context__ is None


@pytest.mark.parametrize("depth", [DEEP_LEVELS, 100_000])
@pytest.mark.parametrize(
    "argv",
    [
        POINT,
        ["address-map", "1 Main St", "OUTPATH"],
        ["freshness", "--path", "/us/nj/camden", "--cache", "CACHE"],
        [*POINT, "--max-records", "3", "--options", '{"limit":2}'],
    ],
    ids=["plain", "address-map", "freshness", "paging"],
)
def test_deep_response_body(monkeypatch, capsys, tmp_path, argv, depth):
    seen = _install(monkeypatch, lambda r: httpx.Response(200, content=_deep_body(depth)))
    argv = [str(tmp_path / "m.html") if a == "OUTPATH" else a for a in argv]
    argv = [str(tmp_path / "c.json") if a == "CACHE" else a for a in argv]
    assert cli.main(argv) == 1
    _assert_clean_failure(capsys, 1, DEEP_FRESHNESS if argv[0] == "freshness" else DEEP)
    assert len(seen) == 1


@pytest.mark.parametrize(
    "argv",
    [
        POINT,
        ["address-map", "1 Main St", "OUTPATH"],
        [*POINT, "--max-records", "3", "--options", '{"limit":2}'],
    ],
    ids=["plain", "address-map", "paging"],
)
def test_deep_decoded_result_fails_at_output(monkeypatch, capsys, tmp_path, argv):
    """A result that decodes but cannot be serialized still fails cleanly."""
    seen = _install(monkeypatch, lambda r: httpx.Response(200, json={}))
    deep = {"parcels": {"features": [{"id": 1, "properties": {"x": _nested(DEEP_LEVELS)}}]}}
    deep["features"] = [{"properties": {"path": "/us/nj/camden"}}]
    monkeypatch.setattr(RegridClient, "_decode", staticmethod(lambda response: deep))
    argv = [str(tmp_path / "m.html") if a == "OUTPATH" else a for a in argv]
    argv = [str(tmp_path / "c.json") if a == "CACHE" else a for a in argv]
    assert cli.main(argv) == 1
    _assert_clean_failure(capsys, 1, DEEP)
    assert len(seen) == 1


def test_freshness_deep_verse_cache_failure_is_a_warning(monkeypatch, capsys, tmp_path):
    verse = {"features": [{"properties": {"path": "/us/nj/camden", "x": _nested(100_000)}}]}
    seen = _install(monkeypatch, lambda r: httpx.Response(200, json={}))
    monkeypatch.setattr(RegridClient, "_decode", staticmethod(lambda response: verse))
    cache = tmp_path / "c.json"
    assert cli.main(["freshness", "--path", "/us/nj/camden", "--cache", str(cache)]) == 0
    out, err = capsys.readouterr()
    assert "regrid: warning: verse cache not saved" in err
    assert err.count("requests made: 1") == 1 and len(seen) == 1


@pytest.mark.parametrize("flag", ["--options", "--fields", "--geojson"])
@pytest.mark.parametrize("depth", [DEEP_LEVELS, 100_000])
def test_deep_json_argument_makes_no_request(monkeypatch, capsys, flag, depth):
    seen = _install(monkeypatch, lambda r: httpx.Response(200, json={}))
    deep = "[" * depth + "]" * depth
    command = {
        "--options": [*POINT, "--options", '{"a":' + deep + "}"],
        "--fields": ["query", "--fields", '{"a":' + deep + "}"],
        "--geojson": ["area", "--geojson", '{"a":' + deep + "}"],
    }[flag]
    assert cli.main(command) == 1
    _assert_clean_failure(capsys, 0, BAD_INPUT)
    assert seen == []


def test_address_map_case_insensitive_collision(monkeypatch, tmp_path, capsys):
    seen = _install(
        monkeypatch,
        lambda r: httpx.Response(200, json={"parcels": {"features": [good_feature()]}}),
    )
    out = tmp_path / "map.html"
    response = tmp_path / "MAP.html"
    code = cli.main(["address-map", "1 Main St", str(out), "--save-response", str(response)])
    assert code == 1
    assert seen == []
    err = capsys.readouterr().err
    assert "must be different files" in err
    assert "regrid: requests made: 0" in err


def test_paging_preserves_response_pages_and_complete(monkeypatch, capsys):
    def handle(request):
        return httpx.Response(
            200,
            json={
                "parcels": {"type": "FeatureCollection", "features": _feats(1, 2)},
                "pages": "server-pages",
                "complete": "server-complete",
            },
        )

    _install(monkeypatch, handle)
    code = cli.main([*POINT, "--max-records", "2", "--options", '{"limit":2}'])
    out, err = capsys.readouterr()
    assert code == 0
    data = json.loads(out)
    assert data["pages"] == 1 and data["complete"] is True
    assert data["response_pages"] == "server-pages"
    assert data["response_complete"] == "server-complete"
    note = "regrid: paging note: response pages/complete kept as response_pages/response_complete"
    assert err.splitlines().count(note) == 1


def _feats(*ids):
    return [{"type": "Feature", "id": i, "properties": {}} for i in ids]


def test_paging_dedupe_distinguishes_id_types(monkeypatch, capsys):
    pages = [_feats(True, 1), _feats(1, 1.0, 5)]
    seen = []

    def handle(request):
        seen.append(request)
        body = pages[len(seen) - 1]
        return httpx.Response(200, json={"parcels": {"features": body}})

    _install(monkeypatch, handle)
    code = cli.main([*POINT, "--max-records", "4", "--options", '{"limit":2}'])
    data = json.loads(capsys.readouterr().out)
    assert code == 0
    ids = [f["id"] for f in data["parcels"]["features"]]
    assert ids == [True, 1, 1.0, 5]
    assert [type(i) for i in ids] == [bool, int, float, int]
