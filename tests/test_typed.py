"""Typed-client contract, compatibility, and safe failure tests."""

import traceback

import httpx
import pytest

from regrid import AuthenticationError, RegridDecodeError, RegridHTTPError
from regrid.models import (
    ClientTokenResponse,
    CountResponse,
    DetailedUsageResponse,
    ParcelResponse,
    ReportResponse,
    SchemaResponse,
    TileJSON,
    TypeaheadResponse,
    UsageResponse,
    VerseResponse,
)
from regrid.typed import TypedRegridClient

UUID = "12345678-1234-5678-1234-567812345678"
POINT = {"type": "Point", "coordinates": [-105.2, 40.5]}
PARCELS = {"parcels": {"type": "FeatureCollection", "features": []}}


@pytest.mark.parametrize(
    "method,args,kwargs,payload,model,path",
    [
        ("point", (40.5, -105.2), {}, PARCELS, ParcelResponse, "/parcels/point"),
        ("area", (POINT,), {"method": "POST"}, PARCELS, ParcelResponse, "/parcels/area"),
        (
            "address",
            ("Main St",),
            {"country": "ca"},
            PARCELS,
            ParcelResponse,
            "/ca/parcels/address",
        ),
        ("apn", ("0001-A",), {}, PARCELS, ParcelResponse, "/parcels/apn"),
        ("owner", ("Smith",), {}, PARCELS, ParcelResponse, "/parcels/owner"),
        ("query", ({"geoid": {"eq": "48113"}},), {}, PARCELS, ParcelResponse, "/parcels/query"),
        ("parcel", (UUID,), {}, PARCELS, ParcelResponse, f"/parcels/{UUID}"),
        ("parcel_path", ("/us/tx/dallas/example",), {}, PARCELS, ParcelResponse, "/parcels/path"),
        (
            "typeahead",
            ("Main St",),
            {},
            {"parcel_centroids": {"type": "FeatureCollection", "features": []}},
            TypeaheadResponse,
            "/parcels/typeahead",
        ),
        (
            "client_token_typeahead",
            (),
            {"exp": 300},
            {"token": "test-returned-token", "expires_at": 1790000000},
            ClientTokenResponse,
            "/client_token/typeahead",
        ),
        ("schema", (), {}, {"schema": {}}, SchemaResponse, "/schemas/parcel"),
        (
            "verse",
            (),
            {"country": "ca"},
            {"type": "Feature", "properties": {}},
            VerseResponse,
            "/ca/verse",
        ),
        ("usage", (), {}, {"usage": {"cycle_usage": {"requests": 2}}}, UsageResponse, "/usage"),
        (
            "usage",
            (),
            {"detailed": True},
            {"usage": {"cycle_usage": [{"country": "US", "service": "api", "parcels": 2}]}},
            DetailedUsageResponse,
            "/usage/detailed",
        ),
        (
            "report",
            ("Please check",),
            {"path": "/us/tx/dallas/example"},
            {"message": "Report received", "id": 123},
            ReportResponse,
            "/report",
        ),
        (
            "tilejson",
            (),
            {"format": "png"},
            {"tiles": ["https://example.com/{z}/{x}/{y}.png"]},
            TileJSON,
            "/api/v1/parcels",
        ),
    ],
)
def test_typed_methods_return_models(method, args, kwargs, payload, model, path):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=payload)

    with TypedRegridClient("test-auth-token", transport=httpx.MockTransport(handler)) as client:
        result = getattr(client, method)(*args, **kwargs)
    assert isinstance(result, model)
    assert result.to_dict() == payload
    assert seen[0].url.path.endswith(path)
    if method == "schema":
        assert "token" not in seen[0].url.params
    else:
        assert seen[0].url.params["token"] == "test-auth-token"


@pytest.mark.parametrize(
    "method,args",
    [
        ("point", (40.5, -105.2)),
        ("area", (POINT,)),
        ("query", ({"geoid": {"eq": "48113"}},)),
    ],
)
def test_count_responses_are_not_swallowed_as_empty_parcels(method, args):
    payload = {"count": 7, "area": {"acres": 4.5}}
    with TypedRegridClient(
        "test-auth-token",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)),
    ) as client:
        result = getattr(client, method)(*args, return_count=True)
    assert isinstance(result, CountResponse)
    assert result.count == 7
    assert result.to_dict() == payload


def test_typed_attributes_preserve_county_fields_and_premium_datasets():
    payload = {
        "parcels": {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": None,
                    "properties": {"headline": "123 Main", "fields": {"county_new": "001-A"}},
                    "future_feature_attribute": {"source": "county"},
                }
            ],
        },
        "buildings": {"type": "FeatureCollection", "features": []},
        "zoning": {"type": "FeatureCollection", "features": []},
        "future_response_attribute": True,
    }
    with TypedRegridClient(
        "test-auth-token",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)),
    ) as client:
        result = client.address("123 Main")
    assert result.parcels.features[0].properties.fields["county_new"] == "001-A"
    assert result.buildings.features == []
    assert result.to_dict() == payload


def test_raw_access_preserves_unmodeled_response_and_shares_transport():
    seen = []
    payload = {"future": "unmodeled response"}

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=payload)

    with TypedRegridClient("test-auth-token", transport=httpx.MockTransport(handler)) as client:
        assert client.raw.address("Main St") == payload
        with pytest.raises(RegridDecodeError):
            client.address("Main St")
    assert len(seen) == 2


@pytest.mark.parametrize(
    "method,args,payload",
    [
        ("address", ("Main St",), {"parcels": {"features": "sensitive-response-value"}}),
        ("point", (1, 2), {"count": "sensitive-response-value"}),
        ("usage", (), {"usage": "sensitive-response-value"}),
    ],
)
def test_schema_failure_is_sanitized(method, args, payload):
    with TypedRegridClient(
        "test-auth-token",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)),
    ) as client:
        with pytest.raises(RegridDecodeError, match="response failed schema validation") as caught:
            getattr(client, method)(*args)
    rendered = "".join(traceback.format_exception(caught.value))
    assert "sensitive-response-value" not in str(caught.value)
    assert "sensitive-response-value" not in repr(caught.value)
    assert "sensitive-response-value" not in rendered
    assert "test-auth-token" not in rendered
    assert caught.value.__context__ is None
    assert caught.value.__cause__ is None


def test_http_errors_are_not_misreported_as_schema_errors():
    with TypedRegridClient(
        "test-auth-token",
        transport=httpx.MockTransport(lambda request: httpx.Response(429, text="private response")),
    ) as client:
        with pytest.raises(RegridHTTPError) as caught:
            client.address("Main St")
    assert caught.value.status_code == 429


def test_request_validation_happens_before_transport():
    def unexpected_request(request):
        pytest.fail("Invalid request was sent")

    with TypedRegridClient(
        "test-auth-token", transport=httpx.MockTransport(unexpected_request)
    ) as client:
        with pytest.raises(ValueError):
            client.address("Main St", limit=0)


def test_public_schema_without_token_and_private_missing_token():
    with TypedRegridClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"schema": {}}))
    ) as client:
        assert isinstance(client.schema(), SchemaResponse)
        with pytest.raises(AuthenticationError):
            client.usage()


def test_tile_bytes_and_close_lifecycle():
    class ClosingTransport(httpx.MockTransport):
        closed = False

        def close(self):
            self.closed = True
            super().close()

    data = b"\x00\xfftile\x80"
    transport = ClosingTransport(lambda request: httpx.Response(200, content=data))
    with TypedRegridClient("test-auth-token", transport=transport) as client:
        assert client.tile(10, 0, 0) == data
        assert not transport.closed
    assert transport.closed
    client.close()  # Closing twice is safe.
