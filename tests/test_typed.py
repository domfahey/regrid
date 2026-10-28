"""Typed-client contract, compatibility, and safe failure tests."""

import json
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
            {"country": "ca", "path": "/ca/mb", "limit": 2},
            PARCELS,
            ParcelResponse,
            "/ca/parcels/address",
        ),
        (
            "apn",
            ("0001-A",),
            {"limit": 3, "return_custom": True},
            PARCELS,
            ParcelResponse,
            "/parcels/apn",
        ),
        (
            "owner",
            ("Smith",),
            {"path": "/us/tx/dallas", "limit": 4},
            PARCELS,
            ParcelResponse,
            "/parcels/owner",
        ),
        (
            "query",
            ({"geoid": {"eq": "48113"}},),
            {"offset_id": 42, "limit": 2},
            PARCELS,
            ParcelResponse,
            "/parcels/query",
        ),
        ("parcel", (UUID,), {"return_custom": True}, PARCELS, ParcelResponse, f"/parcels/{UUID}"),
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
    assert len(seen) == 1  # Conversion must not refetch data.
    request = seen[0]
    assert request.method == ("POST" if method in {"area", "report"} else "GET")
    assert request.url.host == ("tiles.regrid.com" if method == "tilejson" else "app.regrid.com")
    assert request.url.path == (path if method == "tilejson" else "/api/v2" + path)
    expected = {
        "point": {"lat": "40.5", "lon": "-105.2", "limit": "5", "return_parcels": "true"},
        "area": {"limit": "5", "return_parcels": "true"},
        "address": {"query": "Main St", "path": "/ca/mb", "limit": "2"},
        "apn": {
            "parcelnumb": "0001-A",
            "limit": "3",
            "return_custom": "true",
            "return_parcels": "true",
        },
        "owner": {
            "owner": "Smith",
            "path": "/us/tx/dallas",
            "limit": "4",
            "return_parcels": "true",
        },
        "query": {
            "fields[geoid][eq]": "48113",
            "offset_id": "42",
            "limit": "2",
            "return_parcels": "true",
        },
        "parcel": {"return_custom": "true", "return_parcels": "true"},
        "parcel_path": {"path": "/us/tx/dallas/example", "return_parcels": "true"},
        "typeahead": {"query": "Main St"},
        "client_token_typeahead": {"exp": "300"},
        "schema": {},
        "verse": {},
        "usage": {},
        "report": {"comment": "Please check", "path": "/us/tx/dallas/example"},
        "tilejson": {},
    }[method]
    if method != "schema":
        expected = {**expected, "token": "test-auth-token"}
    assert dict(request.url.params) == expected
    assert len(request.url.params.multi_items()) == len(expected)
    if method == "area":
        assert json.loads(request.content) == {"geojson": POINT}
    else:
        assert request.content == b""


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
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=payload)

    with TypedRegridClient(
        "test-auth-token",
        transport=httpx.MockTransport(handler),
    ) as client:
        result = getattr(client, method)(*args, return_count=True)
    assert isinstance(result, CountResponse)
    assert len(seen) == 1
    assert seen[0].url.params["return_count"] == "true"
    assert seen[0].url.params["limit"] == "5"
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
    seen = []

    def handler(request):
        seen.append(request)
        assert request.url.path == "/api/v1/parcels/10/2/3@2x.png"
        assert dict(request.url.params) == {"token": "test-auth-token"}
        return httpx.Response(200, content=data)

    transport = ClosingTransport(handler)
    with TypedRegridClient("test-auth-token", transport=transport) as client:
        assert client.tile(10, 2, 3, format="png", retina=True) == data
        assert not transport.closed
    assert transport.closed
    client.close()  # Closing twice is safe.
    with pytest.raises(RuntimeError, match="client has been closed"):
        client.raw.usage()
    assert len(seen) == 1
