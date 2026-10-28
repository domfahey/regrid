import httpx
import pytest

from regrid import (
    AuthenticationError,
    RegridClient,
    RegridDecodeError,
    RegridError,
    RegridHTTPError,
)

TOKEN = "secret-token-that-must-not-leak"


def client_for(handler, **kwargs):
    return RegridClient(token=TOKEN, transport=httpx.MockTransport(handler), **kwargs)


def test_address_sends_auth_scope_and_bounded_default():
    def handler(request):
        assert request.url.path == "/api/v2/parcels/address"
        assert request.url.params["token"] == TOKEN
        assert request.url.params["query"] == "123 Main St"
        assert request.url.params["path"] == "/us/tx/dallas"
        assert request.url.params["limit"] == "1"
        return httpx.Response(200, json={"parcels": {"features": []}})

    with client_for(handler) as client:
        assert client.address("123 Main St", path="/us/tx/dallas") == {"parcels": {"features": []}}


def test_public_schema_requires_no_token_and_never_sends_one():
    requests = []

    def handler(request):
        requests.append(request)
        assert request.url.path == "/api/v2/schemas/parcel"
        assert "token" not in request.url.params
        return httpx.Response(200, json={"fields": []})

    for token in (None, TOKEN):
        with RegridClient(token=token, transport=httpx.MockTransport(handler)) as client:
            assert client.schema() == {"fields": []}
    assert len(requests) == 2


def test_authenticated_endpoint_rejects_missing_token_before_network():
    def handler(request):
        pytest.fail("Unauthenticated request reached transport")

    with RegridClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AuthenticationError):
            client.address("123 Main St")


@pytest.mark.parametrize("limit", [0, -1, 1001, True, 1.5])
def test_invalid_limit_rejected_before_network(limit):
    def handler(request):
        pytest.fail("Invalid limit reached transport")

    with client_for(handler) as client:
        with pytest.raises((ValueError, TypeError)):
            client.address("123 Main St", limit=limit)


def test_custom_max_limit_is_enforced():
    with client_for(
        lambda request: pytest.fail("Exceeded configured maximum"), max_limit=10
    ) as client:
        with pytest.raises(ValueError):
            client.address("123 Main St", limit=11)


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_http_errors_are_redacted_and_not_retried(status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, text=f"Failed token={TOKEN} URL={request.url}")

    with client_for(handler) as client:
        with pytest.raises(RegridHTTPError) as caught:
            client.address("123 Main St")
    assert isinstance(caught.value, RegridError)
    assert caught.value.status_code == status
    assert TOKEN not in str(caught.value)
    assert TOKEN not in repr(caught.value)
    assert len(calls) == 1


def test_transport_failure_is_redacted_and_not_retried():
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ConnectError(f"Failed URL {request.url}", request=request)

    with client_for(handler) as client:
        with pytest.raises(RegridError) as caught:
            client.address("123 Main St")
    assert TOKEN not in str(caught.value)
    assert TOKEN not in repr(caught.value)
    assert len(calls) == 1


def test_malformed_json_is_wrapped_without_exposing_response():
    with client_for(lambda request: httpx.Response(200, text=f"not json {TOKEN}")) as client:
        with pytest.raises(RegridDecodeError) as caught:
            client.address("123 Main St")
    assert TOKEN not in str(caught.value)
    assert TOKEN not in repr(caught.value)


def test_point_preserves_coordinate_order():
    def handler(request):
        assert request.url.path == "/api/v2/parcels/point"
        assert request.url.params["lat"] == "40.5"
        assert request.url.params["lon"] == "-105.2"
        assert request.url.params["limit"] == "1"
        return httpx.Response(200, json={"parcels": {"features": []}})

    with client_for(handler) as client:
        client.point(40.5, -105.2, limit=1)


def test_redirect_is_not_followed_or_forwarded():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(302, headers={"Location": "https://other.example/collect"})

    with client_for(handler) as client:
        with pytest.raises(RegridHTTPError) as caught:
            client.address("123 Main St")
    assert caught.value.status_code == 302
    assert len(requests) == 1
    assert requests[0].url.host == "app.regrid.com"


@pytest.mark.parametrize("exception_type", [httpx.ReadTimeout, httpx.RemoteProtocolError])
def test_network_error_traceback_does_not_disclose_token(exception_type):
    import traceback

    def handler(request):
        raise exception_type(f"Failed {request.url}", request=request)

    with client_for(handler) as client:
        with pytest.raises(RegridError) as caught:
            client.address("123 Main St")
    rendered = "".join(traceback.format_exception(caught.value))
    assert TOKEN not in rendered
