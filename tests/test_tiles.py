import httpx
import pytest

from regrid import RegridClient


@pytest.mark.parametrize(
    ("format", "retina", "suffix"),
    [
        ("mvt", False, ".mvt"),
        ("png", False, ".png"),
        ("png", True, "@2x.png"),
    ],
)
def test_tile_paths_and_binary_response(format, retina, suffix):
    payload = b"\x00\xff\x01tile"
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, content=payload)

    with RegridClient(token="tile-token", transport=httpx.MockTransport(handler)) as client:
        assert client.tile(10, 123, 456, format=format, retina=retina) == payload
    (request,) = seen
    assert request.method == "GET"
    assert request.url.host == "tiles.regrid.com"
    assert request.url.path == f"/api/v1/parcels/10/123/456{suffix}"
    assert request.url.params.multi_items() == [("token", "tile-token")]


@pytest.mark.parametrize(("z", "edge"), [(10, 1023), (21, 2**21 - 1)])
def test_largest_valid_tile_coordinate_is_accepted(z, edge):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, content=b"t")

    with RegridClient(token="tile-token", transport=httpx.MockTransport(handler)) as client:
        assert client.tile(z, edge, edge) == b"t"
    assert seen[0].url.path == f"/api/v1/parcels/{z}/{edge}/{edge}.mvt"


def test_tilejson_vector_metadata():
    metadata = {"tiles": ["https://tiles.example/{z}/{x}/{y}.mvt"], "minzoom": 10, "maxzoom": 21}

    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=metadata)

    with RegridClient(token="tile-token", transport=httpx.MockTransport(handler)) as client:
        assert client.tilejson(format="mvt") == metadata
    (request,) = seen
    assert request.url.host == "tiles.regrid.com"
    assert request.url.path == "/api/v1/parcels"
    assert dict(request.url.params) == {"format": "mvt", "token": "tile-token"}


def test_tilejson_png_sends_no_format_and_unknown_format_sends_nothing():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"tiles": []})

    with RegridClient(token="tile-token", transport=httpx.MockTransport(handler)) as client:
        client.tilejson(format="png")
        with pytest.raises(ValueError, match="format must be mvt or png"):
            client.tilejson(format="jpg")
    assert [dict(request.url.params) for request in seen] == [{"token": "tile-token"}]


@pytest.mark.parametrize(
    ("z", "x", "y"),
    [
        (9, 0, 0),
        (22, 0, 0),
        (10, -1, 0),
        (10, 0, -1),
        (10, 1024, 0),
        (10, 0, 1024),
        (10.5, 0, 0),
        (10, True, 0),
    ],
)
def test_invalid_tile_coordinates_never_send_request(z, x, y):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, content=b"")

    with RegridClient(token="tile-token", transport=httpx.MockTransport(handler)) as client:
        # Always the sanitized ValueError, never a raw TypeError/ValidationError leaking input.
        with pytest.raises(ValueError, match="^Invalid Regrid request parameters$"):
            client.tile(z, x, y)
    assert seen == []


def test_retina_vector_is_rejected():
    seen = []
    transport = httpx.MockTransport(lambda request: seen.append(request))
    with RegridClient(token="tile-token", transport=transport) as client:
        with pytest.raises(ValueError, match="^Invalid Regrid request parameters$"):
            client.tile(10, 0, 0, format="mvt", retina=True)
    assert seen == []
