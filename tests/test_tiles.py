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

    def handler(request):
        assert request.url.host == "tiles.regrid.com"
        assert request.url.path == f"/api/v1/parcels/10/123/456{suffix}"
        assert request.url.params["token"] == "tile-token"
        return httpx.Response(200, content=payload)

    with RegridClient(token="tile-token", transport=httpx.MockTransport(handler)) as client:
        assert client.tile(10, 123, 456, format=format, retina=retina) == payload


def test_tilejson_vector_metadata():
    metadata = {"tiles": ["https://tiles.example/{z}/{x}/{y}.mvt"], "minzoom": 10, "maxzoom": 21}

    def handler(request):
        assert request.url.path == "/api/v1/parcels"
        assert request.url.params["format"] == "mvt"
        assert request.url.params["token"] == "tile-token"
        return httpx.Response(200, json=metadata)

    with RegridClient(token="tile-token", transport=httpx.MockTransport(handler)) as client:
        assert client.tilejson(format="mvt") == metadata


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
    def handler(request):
        pytest.fail("Invalid tile reached transport")

    with RegridClient(token="tile-token", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises((ValueError, TypeError)):
            client.tile(z, x, y)


def test_retina_vector_is_rejected():
    with RegridClient(
        token="tile-token",
        transport=httpx.MockTransport(
            lambda request: pytest.fail("Invalid format reached transport")
        ),
    ) as client:
        with pytest.raises(ValueError):
            client.tile(10, 0, 0, format="mvt", retina=True)
