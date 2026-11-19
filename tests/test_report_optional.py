import httpx

from regrid import RegridClient


def test_report_all_parameters_optional():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"message": "Report received", "id": 123})

    with RegridClient(token="test-token", transport=httpx.MockTransport(handler)) as client:
        assert client.report() == {"message": "Report received", "id": 123}
    (request,) = seen
    assert request.method == "POST"
    assert request.url.path == "/api/v2/report"
    # Omitted optionals are not sent as empty values, in the query or in a body.
    assert request.url.params.multi_items() == [("token", "test-token")]
    assert request.content == b""
