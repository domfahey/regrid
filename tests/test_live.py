import httpx
import pytest

from regrid import RegridClient, live


def test_missing_configuration_makes_no_requests(monkeypatch, capsys):
    monkeypatch.delenv("REGRID_TOKEN", raising=False)
    monkeypatch.delenv("REGRID_LIVE_ADDRESS", raising=False)
    monkeypatch.setattr(live, "RegridClient", lambda *a, **kw: pytest.fail("unexpected client"))
    assert live.main() == 2
    assert "NOT RUN" in capsys.readouterr().out


@pytest.mark.parametrize("outcome", ["ok", "empty", "invalid", "http", "final-usage"])
def test_bounded_smoke_and_final_usage_even_after_parcel_failure(outcome, capsys):
    requests = []

    def handle(request):
        requests.append(request)
        if request.url.path.endswith("/schemas/parcel"):
            assert "token" not in request.url.params
            return httpx.Response(200, json={"schema": {"parcelnumb": {"type": "text"}}})
        assert request.url.params["token"] == "private-token"
        if request.url.path.endswith("/usage"):
            if len(requests) == 4 and outcome == "final-usage":
                return httpx.Response(500, text="private-token")
            return httpx.Response(200, json={"usage": {"cycle_usage": {"results": len(requests)}}})
        assert dict(request.url.params) == {
            "query": "private-address",
            "limit": "1",
            "return_parcels": "true",
            "return_stacked": "false",
            "return_zoning": "false",
            "return_matched_buildings": "false",
            "return_matched_addresses": "false",
            "return_enhanced_ownership": "false",
            "token": "private-token",
        }
        if outcome == "http":
            return httpx.Response(401, text="private-token private-address")
        features = (
            []
            if outcome == "empty"
            else [
                {
                    "properties": {
                        "fields": {
                            "parcelnumb": 123 if outcome == "invalid" else "00123",
                            "owner": "private-owner",
                        }
                    }
                }
            ]
        )
        return httpx.Response(
            200, json={"parcels": {"type": "FeatureCollection", "features": features}}
        )

    with RegridClient("private-token", transport=httpx.MockTransport(handle)) as client:
        assert live.run(client, "private-address") == (0 if outcome == "ok" else 1)
    assert len(requests) == 4
    assert requests[-1].url.path.endswith("/usage")
    output = capsys.readouterr().out
    assert all(
        secret not in output for secret in ("private-token", "private-address", "private-owner")
    )


def test_schema_failure_stops_before_billable_request(capsys):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(500, text="sensitive")

    with RegridClient("test", transport=httpx.MockTransport(handle)) as client:
        assert live.run(client, "address") == 1
    assert len(calls) == 1
    assert "sensitive" not in capsys.readouterr().out


GEOMETRY_CASES = [
    pytest.param(
        {"type": "Polygon", "coordinates": [[[-75.0123, 39.9456], [-75.0124, 39.9457]]]},
        "PASS geometry present",
        id="polygon",
    ),
    pytest.param(None, "NOTE geometry null (no boundary on file)", id="null"),
    pytest.param("absent", "NOTE geometry field absent (map would fail)", id="absent"),
]


@pytest.mark.parametrize(("geometry", "expected_line"), GEOMETRY_CASES)
def test_live_run_reports_geometry_presence_without_coordinates(geometry, expected_line, capsys):
    requests = []

    def handle(request):
        requests.append(request)
        if request.url.path.endswith("/schemas/parcel"):
            return httpx.Response(200, json={"schema": {"parcelnumb": {"type": "text"}}})
        if request.url.path.endswith("/usage"):
            return httpx.Response(200, json={"usage": {"cycle_usage": {"results": 0}}})
        feature = {"properties": {"fields": {"parcelnumb": "00123"}}}
        if geometry != "absent":
            feature["geometry"] = geometry
        return httpx.Response(
            200, json={"parcels": {"type": "FeatureCollection", "features": [feature]}}
        )

    with RegridClient("private-token", transport=httpx.MockTransport(handle)) as client:
        assert live.run(client, "private-address") == 0
    assert len(requests) == 4
    output = capsys.readouterr().out.splitlines()
    assert expected_line in output
    assert sum(line.startswith(("PASS geometry", "NOTE geometry")) for line in output) == 1
    assert "75.0123" not in "\n".join(output)
    assert "39.9456" not in "\n".join(output)
