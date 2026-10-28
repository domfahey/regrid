import httpx

from regrid import RegridClient


def test_report_all_parameters_optional():
    def handler(request):
        assert request.method == "POST"
        assert request.url.path == "/api/v2/report"
        assert dict(request.url.params) == {"token": "test-token"}
        return httpx.Response(200, json={"message": "Report received", "id": 123})

    with RegridClient(token="test-token", transport=httpx.MockTransport(handler)) as client:
        assert client.report() == {"message": "Report received", "id": 123}
