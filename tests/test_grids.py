"""UTFGrid discovery, exact wire contracts, and credential-boundary regressions."""

import traceback

import httpx
import pytest

from regrid import RegridClient, RegridDecodeError, RegridHTTPError
from regrid.grids import fetch_grid

TOKEN = "active-test-token"
GRID = {"grid": [" !", "!!"], "keys": ["", "parcel-1"], "data": {"parcel-1": {"apn": "001"}}}


def test_grid_discovery_and_token_replacement():
    seen = []

    def handler(request):
        seen.append(request)
        if len(seen) == 1:
            assert request.method == "GET"
            assert request.url.path == "/api/v1/parcels"
            assert dict(request.url.params) == {"token": TOKEN}
            return httpx.Response(
                200,
                json={
                    "grid": "https://tiles.regrid.com/utf/{z}/{x}/{y}.json?token=old-secret&token=other-secret&resolution=4"
                },
            )
        assert request.url.path == "/utf/10/12/34.json"
        assert request.url.params.multi_items() == [("resolution", "4"), ("token", TOKEN)]
        assert request.content == b""
        return httpx.Response(200, json=GRID)

    with RegridClient(TOKEN, transport=httpx.MockTransport(handler)) as client:
        assert fetch_grid(client, 10, 12, 34) == GRID
    assert len(seen) == 2


@pytest.mark.parametrize(
    "metadata",
    [
        {"grid": "/utf/{z}/{x}/{y}.json?token={token}"},
        {"grid": ["utf/{z}/{x}/{y}.json", "https://unused.invalid/{z}/{x}/{y}"]},
        {"grids": ["https://tiles.regrid.com/utf/{z}/{x}/{y}.json"]},
    ],
)
def test_explicit_metadata_needs_only_one_request(metadata):
    seen = []

    def handler(request):
        seen.append(request)
        assert str(request.url) == f"https://tiles.regrid.com/utf/10/0/1.json?token={TOKEN}"
        return httpx.Response(200, json=GRID)

    with RegridClient(TOKEN, transport=httpx.MockTransport(handler)) as client:
        assert fetch_grid(client, 10, 0, 1, metadata=metadata) == GRID
    assert len(seen) == 1


def test_custom_origin_relative_path_query_values_and_empty_grid():
    empty = {"grid": [], "keys": [], "data": {}}
    seen = []

    def handler(request):
        seen.append(request)
        assert request.url.scheme == "https"
        assert request.url.host == "tiles.example.test"
        assert request.url.port == 8443
        assert request.url.path == "/service/grid/10/1/0"
        assert request.url.params.multi_items() == [
            ("layer", "a"),
            ("layer", "b"),
            ("label", "parcel grid#1"),
            ("token", TOKEN),
        ]
        return httpx.Response(200, json=empty)

    metadata = {"grid": "grid/{z}/{x}/{y}?layer=a&Token=old-secret&layer=b&label=parcel%20grid%231"}
    with RegridClient(
        TOKEN,
        tiles_base_url="https://tiles.example.test:8443/service",
        transport=httpx.MockTransport(handler),
    ) as client:
        assert fetch_grid(client, 10, 1, 0, metadata=metadata) == empty
    assert len(seen) == 1


MISSING = "TileJSON must advertise a UTFGrid endpoint"
UNSAFE = "Unsafe UTFGrid endpoint in TileJSON"
NOT_OBJECT = "UTFGrid metadata must be a TileJSON object"


@pytest.mark.parametrize(
    ("metadata", "message"),
    [
        ({}, MISSING),
        ({"grid": None}, MISSING),
        ({"grid": []}, MISSING),
        ({"grid": [""]}, MISSING),
        ({"grid": [1]}, MISSING),
        ({"grid": " "}, MISSING),
        ({"grid": 42}, MISSING),
        ([], NOT_OBJECT),
        ({"grid": "https://evil.example/{z}/{x}/{y}?token=secret-marker"}, UNSAFE),
        ({"grid": "//evil.example/{z}/{x}/{y}"}, UNSAFE),
        ({"grid": "http://tiles.regrid.com/{z}/{x}/{y}"}, UNSAFE),
        ({"grid": "https://tiles.regrid.com:8443/{z}/{x}/{y}"}, UNSAFE),
        ({"grid": "https://secret-marker@tiles.regrid.com/{z}/{x}/{y}"}, UNSAFE),
        ({"grid": "https://tiles.regrid.com/{z}/{x}/{y}#secret-marker"}, UNSAFE),
        ({"grid": "https://tiles.regrid.com/{z}/{x}/{y}#"}, UNSAFE),
        ({"grid": "https://tiles.regrid.com/{z}/{x}/{y}/{unknown}"}, UNSAFE),
        ({"grid": "https://tiles.regrid.com/{z.__class__}/{x}/{y}"}, UNSAFE),
        ({"grid": "https://tiles.regrid.com/{z}/{x}/{y}/%7Bunknown%7D"}, UNSAFE),
        ({"grid": "https://tiles.regrid.com/{z}/{x}/{y}/%5Cevil"}, UNSAFE),
        ({"grid": "https://tiles.regrid.com/\n/{z}/{x}/{y}"}, UNSAFE),
        ({"grid": "https://tiles.regrid.com:bad/{z}/{x}/{y}?token=secret-marker"}, UNSAFE),
    ],
)
def test_unsafe_or_missing_template_fails_before_network(metadata, message):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=GRID)

    with RegridClient(TOKEN, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError) as caught:
            fetch_grid(client, 10, 0, 0, metadata=metadata)
    assert str(caught.value) == message
    assert "secret-marker" not in "".join(traceback.format_exception(caught.value))
    assert caught.value.__context__ is None
    assert seen == []


@pytest.mark.parametrize(
    "coords", [(9, 0, 0), (22, 0, 0), (10, -1, 0), (10, 0, 1024), (True, 0, 0)]
)
def test_invalid_coordinates_do_not_even_discover_metadata(coords):
    def unexpected(request: httpx.Request) -> httpx.Response:
        pytest.fail(f"Unexpected HTTP request: {request.url}")

    with RegridClient(TOKEN, transport=httpx.MockTransport(unexpected)) as client:
        with pytest.raises(ValueError, match="^Invalid Regrid request parameters$"):
            fetch_grid(client, *coords)


@pytest.mark.parametrize(
    "response,error",
    [
        (httpx.Response(302, headers={"Location": "https://evil.example/token"}), RegridHTTPError),
        (httpx.Response(401, text=TOKEN), RegridHTTPError),
        (httpx.Response(200, text="invalid-json " + TOKEN), RegridDecodeError),
        (httpx.Response(200, json=[]), RegridDecodeError),
    ],
)
def test_grid_transport_errors_are_safe_and_not_retried(response, error):
    seen = []

    def handler(request):
        seen.append(request)
        return response

    with RegridClient(TOKEN, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(error) as caught:
            fetch_grid(client, 10, 0, 0, metadata={"grid": "/grid/{z}/{x}/{y}"})
    assert len(seen) == 1
    assert TOKEN not in str(caught.value)


def test_null_grid_falls_back_to_grids_advertised_by_tilejson():
    seen = []

    def handler(request):
        seen.append(request)
        assert request.url.path == "/utf/10/0/1.json"
        return httpx.Response(200, json=GRID)

    metadata = {
        "grid": None,
        "grids": ["https://tiles.regrid.com/utf/{z}/{x}/{y}.json"],
    }
    with RegridClient(TOKEN, transport=httpx.MockTransport(handler)) as client:
        assert fetch_grid(client, 10, 0, 1, metadata=metadata) == GRID
    assert len(seen) == 1


@pytest.mark.parametrize("grid", ["", " ", 42, [], [""]])
def test_explicit_invalid_grid_does_not_fall_back_to_grids(grid):
    def handler(request):
        pytest.fail("Invalid explicit grid fell back to grids")

    metadata = {"grid": grid, "grids": ["https://tiles.regrid.com/utf/{z}/{x}/{y}.json"]}
    with RegridClient(TOKEN, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="TileJSON must advertise a UTFGrid endpoint"):
            fetch_grid(client, 10, 0, 1, metadata=metadata)
