import traceback

import httpx
import pytest

from regrid import RegridClient, TypedRegridClient
from regrid.config import ClientSettings


@pytest.mark.parametrize("client_class", [RegridClient, TypedRegridClient])
@pytest.mark.parametrize(
    "kwargs",
    [
        {"token": {"secret-value": "do-not-print"}},
        {"base_url": "https://secret-value:do-not-print@example.com"},
        {"timeout": "secret-value"},
        {"default_limit": 10, "max_limit": 5},
        {"base_url": "https://example.com:invalid"},
    ],
)
def test_configuration_validation_does_not_retain_sensitive_errors(client_class, kwargs):
    with pytest.raises(ValueError) as caught:
        client_class(**kwargs)
    assert "secret-value" not in "".join(traceback.format_exception(caught.value))
    assert caught.value.__context__ is None
    assert caught.value.__cause__ is None


def test_token_stays_masked_until_transport():
    def handler(request):
        assert request.url.params["token"] == "private-test-placeholder"
        return httpx.Response(200, json={"usage": {}})

    with RegridClient("private-test-placeholder", transport=httpx.MockTransport(handler)) as client:
        assert "private-test-placeholder" not in repr(client._token)
        assert client.usage() == {"usage": {}}


@pytest.mark.parametrize("client_class", [RegridClient, TypedRegridClient])
@pytest.mark.parametrize("number", ["NaN", "Infinity", "-Infinity", "1e9999"])
def test_nonfinite_upstream_json_is_rejected_instead_of_lost(client_class, number):
    from regrid import RegridDecodeError

    body = '{"usage": {}, "county_extra": ' + number + "}"
    with client_class(
        "test-placeholder",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text=body)),
    ) as client:
        with pytest.raises(RegridDecodeError):
            client.usage()


def test_finite_response_numbers_are_preserved():
    with RegridClient(
        "test-placeholder",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text='{"amount": 0.125}')
        ),
    ) as client:
        assert client.usage() == {"amount": 0.125}


@pytest.mark.parametrize("field", ["base_url", "tiles_base_url"])
@pytest.mark.parametrize(
    "bad_url",
    [
        "https://app.regrid.com/api/v2?",
        "https://app.regrid.com/api/v2#",
        "https://:@app.regrid.com/api/v2",
        "https://@app.regrid.com/api/v2",
    ],
)
def test_service_url_rejects_empty_delimiters(field, bad_url):
    with pytest.raises(ValueError, match="Service URLs must be HTTPS"):
        ClientSettings(**{field: bad_url})


@pytest.mark.parametrize("field", ["base_url", "tiles_base_url"])
@pytest.mark.parametrize(
    "good_url",
    [
        "https://app.regrid.com/api/v2",
        "https://tiles.regrid.com",
        "https://app.regrid.com/api/v2/",
        "https://localhost:8443/api/v2",
    ],
)
def test_service_url_accepts_plain_https_origins(field, good_url):
    settings = ClientSettings(**{field: good_url})
    assert getattr(settings, field) == good_url.rstrip("/")
