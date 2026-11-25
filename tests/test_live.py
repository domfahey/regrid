import logging
import runpy
import sys

import httpx
import pytest

from regrid import RegridClient, live


@pytest.fixture(autouse=True)
def restore_logging():
    yield
    logging.disable(logging.NOTSET)


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


def test_empty_schema_stops_before_billable_request(capsys):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, json={"schema": {}})

    with RegridClient("private-token", transport=httpx.MockTransport(handle)) as client:
        assert live.run(client, "private-address") == 1
    assert len(calls) == 1
    assert capsys.readouterr().out.splitlines() == ["FAIL public schema: no field definitions"]


def test_schema_mismatch_note_and_unavailable_usage_counters(capsys):
    def handle(request):
        if request.url.path.endswith("/schemas/parcel"):
            return httpx.Response(200, json={"schema": {"parcelnumb": {"type": "integer"}}})
        if request.url.path.endswith("/usage"):
            return httpx.Response(200, json={"usage": {}})
        return httpx.Response(
            200,
            json={
                "parcels": {
                    "type": "FeatureCollection",
                    "features": [{"properties": {"fields": {"parcelnumb": "00123"}}}],
                }
            },
        )

    with RegridClient("private-token", transport=httpx.MockTransport(handle)) as client:
        assert live.run(client, "private-address") == 0
    output = capsys.readouterr().out.splitlines()
    assert "PASS public schema: 1 definitions; 1 type differences" in output
    assert "NOTE schema differs from local catalog; typed validation may fail" in output
    assert "PASS final usage: comparable record counters unavailable" in output


def test_missing_parcel_properties_fails_and_still_checks_final_usage(capsys):
    requests = []

    def handle(request):
        requests.append(request)
        if request.url.path.endswith("/schemas/parcel"):
            return httpx.Response(200, json={"schema": {"parcelnumb": {"type": "text"}}})
        if request.url.path.endswith("/usage"):
            return httpx.Response(200, json={"usage": {"cycle_usage": {"results": len(requests)}}})
        return httpx.Response(
            200, json={"parcels": {"type": "FeatureCollection", "features": [{"properties": None}]}}
        )

    with RegridClient("private-token", transport=httpx.MockTransport(handle)) as client:
        assert live.run(client, "private-address") == 1
    assert len(requests) == 4
    assert requests[-1].url.path.endswith("/usage")
    assert "FAIL parcel validation: missing properties or fields" in capsys.readouterr().out


def test_main_runs_with_environment_and_suppresses_logging(monkeypatch, capsys):
    seen_levels = []
    seen_queries = []

    def handle(request):
        seen_levels.append(logging.root.manager.disable)
        if request.url.path.endswith("/schemas/parcel"):
            return httpx.Response(200, json={"schema": {"parcelnumb": {"type": "text"}}})
        if request.url.path.endswith("/usage"):
            return httpx.Response(200, json={"usage": {"cycle_usage": {"results": 1}}})
        seen_queries.append(request.url.params.get("query"))
        return httpx.Response(
            200,
            json={
                "parcels": {
                    "type": "FeatureCollection",
                    "features": [{"properties": {"fields": {"parcelnumb": "00123"}}}],
                }
            },
        )

    transport = httpx.MockTransport(handle)
    real_client = live.RegridClient
    monkeypatch.setenv("REGRID_TOKEN", "private-token")
    monkeypatch.setenv("REGRID_LIVE_ADDRESS", "private-address")
    monkeypatch.setattr(
        live, "RegridClient", lambda *a, **kw: real_client(*a, transport=transport, **kw)
    )
    assert live.main() == 0
    assert seen_levels and all(level >= logging.CRITICAL for level in seen_levels)
    assert seen_queries == ["private-address"]
    output = capsys.readouterr().out
    assert "private-token" not in output
    assert "private-address" not in output


def test_main_initialization_failure_is_generic(monkeypatch, capsys):
    monkeypatch.setenv("REGRID_TOKEN", "private-token")

    def boom(*_args, **_kwargs):
        raise RuntimeError("private-token")

    monkeypatch.setattr(live, "RegridClient", boom)
    assert live.main() == 1
    assert capsys.readouterr().out.strip() == "FAIL live smoke test initialization"


def test_module_entrypoint(monkeypatch, capsys):
    monkeypatch.delenv("REGRID_TOKEN", raising=False)
    monkeypatch.delitem(sys.modules, "regrid.live", raising=False)
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("regrid.live", run_name="__main__")
    assert exc.value.code == 2
    assert "NOT RUN" in capsys.readouterr().out
