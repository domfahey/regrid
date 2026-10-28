"""Operation and parameter inventory transcribed from the supplied OpenAPI 2.0.0.

Expected URLs/parameters are contract fixtures, never obtained from SDK internals.
Query-string example paths in the document normalize to the ordinary query route.
"""

import json
from dataclasses import dataclass
from typing import Any

import httpx
import pytest

from regrid import RegridClient, cli

TOKEN = "contract-test-placeholder"
UUID = "8b6f4f51-58ad-4969-93b3-fdfb348a7084"
POINT = {"type": "Point", "coordinates": [-96.563861, 32.834967]}
POINT_JSON = '{"type":"Point","coordinates":[-96.563861,32.834967]}'
# All values are explicit: false flags must not disappear and custom fields must pass.
COMMON_INPUT = {"return_custom": True, "return_field_labels": True, "return_stacked": False}
COMMON_WIRE = {"return_custom": "true", "return_field_labels": "true", "return_stacked": "false"}
PREMIUM_INPUT = {
    "return_zoning": False,
    "return_matched_buildings": False,
    "return_matched_addresses": False,
    "return_enhanced_ownership": False,
    "return_parcels": False,
}
PREMIUM_WIRE = {
    "return_zoning": "false",
    "return_matched_buildings": "false",
    "return_matched_addresses": "false",
    "return_enhanced_ownership": "false",
    "return_parcels": "false",
}
US_INPUT = {**COMMON_INPUT, **PREMIUM_INPUT}
US_WIRE = {**COMMON_WIRE, **PREMIUM_WIRE}
SPATIAL_INPUT = {"radius": 10, "limit": 2, "return_count": False}
SPATIAL_WIRE = {"radius": "10", "limit": "2", "return_count": "false"}
CURSOR_INPUT = {"offset_id": 17, "return_geometry": False}
CURSOR_WIRE = {"offset_id": "17", "return_geometry": "false"}
US_PATH = "/us/tx/dallas"
CA_PATH = "/ca/mb/division-no-22"
US_PARCEL_PATH = "/us/tx/dallas/northeast-dallas/6471"
CA_PARCEL_PATH = "/ca/mb/division-no-22/division-no-22-unorganized/2082"
US_FIELDS = {"geoid": {"eq": "48113"}, "landval": {"between": [100000, 200000]}}
CA_FIELDS = {"geoid": {"eq": "4622"}, "postcode": {"eq": "R0B 0J0"}}
US_FIELD_WIRE = {"fields[geoid][eq]": "48113", "fields[landval][between]": "[100000,200000]"}
CA_FIELD_WIRE = {"fields[geoid][eq]": "4622", "fields[postcode][eq]": "R0B 0J0"}
USAGE_INPUT = {
    "return_full_history": True,
    "begin_date": "2026-10-01",
    "end_date": "2026-10-27",
    "return_by_token": True,
    "return_by_this_token": False,
}
USAGE_WIRE = {
    "return_full_history": "true",
    "begin_date": "2026-10-01",
    "end_date": "2026-10-27",
    "return_by_token": "true",
    "return_by_this_token": "false",
}


@dataclass(frozen=True)
class Operation:
    verb: str
    path: str
    sdk: str
    kwargs: dict[str, Any]
    command: tuple[str, ...]
    options: dict[str, Any]
    expected: dict[str, str]
    body: dict[str, Any] | None = None
    public: bool = False

    @property
    def id(self):
        return f"{self.verb} {self.path}"


OPERATIONS = [
    Operation(
        "GET",
        "/parcels/point",
        "point",
        {"lat": 32.834967, "lon": -96.563861, "geojson": POINT},
        ("point", "--lat", "32.834967", "--lon", "-96.563861", "--geojson", POINT_JSON),
        {**US_INPUT, **SPATIAL_INPUT, **CURSOR_INPUT, "return_custom_id": True},
        {
            **US_WIRE,
            **SPATIAL_WIRE,
            **CURSOR_WIRE,
            "return_custom_id": "true",
            "lat": "32.834967",
            "lon": "-96.563861",
            "geojson": POINT_JSON,
        },
    ),
    Operation(
        "POST",
        "/parcels/point",
        "point",
        {"lat": 32.834967, "lon": -96.563861, "geojson": POINT, "method": "POST"},
        (
            "point",
            "--lat",
            "32.834967",
            "--lon",
            "-96.563861",
            "--geojson",
            POINT_JSON,
            "--method",
            "POST",
        ),
        {**US_INPUT, **SPATIAL_INPUT, "return_custom_id": True},
        {
            **US_WIRE,
            **SPATIAL_WIRE,
            "return_custom_id": "true",
            "lat": "32.834967",
            "lon": "-96.563861",
        },
        {"geojson": POINT},
    ),
    Operation(
        "GET",
        "/parcels/address",
        "address",
        {"query": "5818 Diana Dr"},
        ("address", "5818 Diana Dr"),
        {**US_INPUT, "path": US_PATH, "limit": 2},
        {**US_WIRE, "query": "5818 Diana Dr", "path": US_PATH, "limit": "2"},
    ),
    Operation(
        "GET",
        "/parcels/apn",
        "apn",
        {"parcelnumb": "000123-A"},
        ("apn", "000123-A"),
        {**US_INPUT, "path": US_PATH, "limit": 2},
        {**US_WIRE, "parcelnumb": "000123-A", "path": US_PATH, "limit": "2"},
    ),
    Operation(
        "GET",
        "/parcels/owner",
        "owner",
        {"owner": "7 ELEVEN INC"},
        ("owner", "7 ELEVEN INC"),
        {**US_INPUT, "path": US_PATH, "limit": 2},
        {**US_WIRE, "owner": "7 ELEVEN INC", "path": US_PATH, "limit": "2"},
    ),
    Operation(
        "GET",
        "/parcels/query",
        "query",
        {"fields": US_FIELDS},
        ("query", "--fields", json.dumps(US_FIELDS)),
        {
            **US_INPUT,
            **SPATIAL_INPUT,
            **CURSOR_INPUT,
            "geojson": POINT,
            "path": US_PATH,
            "return_custom_id": True,
        },
        {
            **US_WIRE,
            **SPATIAL_WIRE,
            **CURSOR_WIRE,
            **US_FIELD_WIRE,
            "geojson": POINT_JSON,
            "path": US_PATH,
            "return_custom_id": "true",
        },
    ),
    Operation(
        "GET",
        "/parcels/area",
        "area",
        {"geojson": POINT},
        ("area", "--geojson", POINT_JSON),
        {**US_INPUT, **SPATIAL_INPUT, **CURSOR_INPUT, "return_custom_id": True},
        {
            **US_WIRE,
            **SPATIAL_WIRE,
            **CURSOR_WIRE,
            "geojson": POINT_JSON,
            "return_custom_id": "true",
        },
    ),
    Operation(
        "POST",
        "/parcels/area",
        "area",
        {"geojson": POINT, "method": "POST"},
        ("area", "--geojson", POINT_JSON, "--method", "POST"),
        {**US_INPUT, **SPATIAL_INPUT, **CURSOR_INPUT, "return_custom_id": True},
        {**US_WIRE, **SPATIAL_WIRE, **CURSOR_WIRE, "return_custom_id": "true"},
        {"geojson": POINT},
    ),
    Operation(
        "GET",
        "/parcels/typeahead",
        "typeahead",
        {"query": "5818 Diana"},
        ("typeahead", "5818 Diana"),
        {},
        {"query": "5818 Diana"},
    ),
    Operation(
        "GET",
        "/parcels/path",
        "parcel_path",
        {"path": US_PARCEL_PATH},
        ("parcel-path", US_PARCEL_PATH),
        US_INPUT,
        {**US_WIRE, "path": US_PARCEL_PATH},
    ),
    Operation(
        "GET", f"/parcels/{UUID}", "parcel", {"ll_uuid": UUID}, ("parcel", UUID), US_INPUT, US_WIRE
    ),
    Operation(
        "GET",
        "/client_token/typeahead",
        "client_token_typeahead",
        {"exp": 14400.0},
        ("client-token-typeahead", "--exp", "14400"),
        {},
        {"exp": "14400.0"},
    ),
    Operation(
        "GET",
        "/schemas/parcel",
        "schema",
        {"name": "parcel"},
        ("schema", "parcel"),
        {"premium_only": True},
        {"premium_only": "true"},
        public=True,
    ),
    Operation(
        "GET",
        "/schemas/building",
        "schema",
        {"name": "building"},
        ("schema", "building"),
        {},
        {},
        public=True,
    ),
    Operation(
        "GET",
        "/schemas/address",
        "schema",
        {"name": "address"},
        ("schema", "address"),
        {},
        {},
        public=True,
    ),
    Operation(
        "GET",
        "/schemas/enhanced_ownership",
        "schema",
        {"name": "enhanced_ownership"},
        ("schema", "enhanced_ownership"),
        {},
        {},
        public=True,
    ),
    Operation(
        "GET",
        "/schemas/zoning",
        "schema",
        {"name": "zoning"},
        ("schema", "zoning"),
        {},
        {},
        public=True,
    ),
    Operation(
        "GET",
        "/verse",
        "verse",
        {},
        ("verse",),
        {"return_geometry": False},
        {"return_geometry": "false"},
    ),
    Operation("GET", "/usage", "usage", {}, ("usage",), USAGE_INPUT, USAGE_WIRE),
    Operation(
        "GET",
        "/usage/detailed",
        "usage",
        {"detailed": True},
        ("usage", "--detailed"),
        USAGE_INPUT,
        USAGE_WIRE,
    ),
    Operation(
        "POST",
        "/report",
        "report",
        {
            "comment": "Please check",
            "path": US_PARCEL_PATH,
            "ll_uuid": UUID,
            "details": {"owner": "Changed"},
        },
        (
            "report",
            "--comment",
            "Please check",
            "--path",
            US_PARCEL_PATH,
            "--ll-uuid",
            UUID,
            "--details",
            '{"owner":"Changed"}',
        ),
        {},
        {
            "comment": "Please check",
            "path": US_PARCEL_PATH,
            "ll_uuid": UUID,
            "details": '{"owner":"Changed"}',
        },
    ),
    Operation(
        "GET", "/schemas/ca", "schema", {"name": "ca"}, ("schema", "ca"), {}, {}, public=True
    ),
    Operation(
        "GET",
        "/ca/parcels/point",
        "point",
        {"country": "ca", "lat": 32.834967, "lon": -96.563861, "geojson": POINT},
        (
            "point",
            "--country",
            "ca",
            "--lat",
            "32.834967",
            "--lon",
            "-96.563861",
            "--geojson",
            POINT_JSON,
        ),
        {**COMMON_INPUT, **SPATIAL_INPUT, **CURSOR_INPUT},
        {
            **COMMON_WIRE,
            **SPATIAL_WIRE,
            **CURSOR_WIRE,
            "lat": "32.834967",
            "lon": "-96.563861",
            "geojson": POINT_JSON,
        },
    ),
    Operation(
        "POST",
        "/ca/parcels/point",
        "point",
        {"country": "ca", "lat": 32.834967, "lon": -96.563861, "geojson": POINT, "method": "POST"},
        (
            "point",
            "--country",
            "ca",
            "--lat",
            "32.834967",
            "--lon",
            "-96.563861",
            "--geojson",
            POINT_JSON,
            "--method",
            "POST",
        ),
        {**COMMON_INPUT, **SPATIAL_INPUT},
        {**COMMON_WIRE, **SPATIAL_WIRE, "lat": "32.834967", "lon": "-96.563861"},
        {"geojson": POINT},
    ),
    Operation(
        "GET",
        "/ca/parcels/area",
        "area",
        {"country": "ca", "geojson": POINT},
        ("area", "--country", "ca", "--geojson", POINT_JSON),
        {**COMMON_INPUT, **SPATIAL_INPUT, **CURSOR_INPUT},
        {**COMMON_WIRE, **SPATIAL_WIRE, **CURSOR_WIRE, "geojson": POINT_JSON},
    ),
    Operation(
        "POST",
        "/ca/parcels/area",
        "area",
        {"country": "ca", "geojson": POINT, "method": "POST"},
        ("area", "--country", "ca", "--geojson", POINT_JSON, "--method", "POST"),
        {**COMMON_INPUT, **SPATIAL_INPUT, **CURSOR_INPUT},
        {**COMMON_WIRE, **SPATIAL_WIRE, **CURSOR_WIRE},
        {"geojson": POINT},
    ),
    Operation(
        "GET",
        "/ca/parcels/address",
        "address",
        {"country": "ca", "query": "500 CHASTELAINE ST"},
        ("address", "500 CHASTELAINE ST", "--country", "ca"),
        {**COMMON_INPUT, "path": CA_PATH, "limit": 2},
        {**COMMON_WIRE, "query": "500 CHASTELAINE ST", "path": CA_PATH, "limit": "2"},
    ),
    Operation(
        "GET",
        f"/ca/parcels/{UUID}",
        "parcel",
        {"country": "ca", "ll_uuid": UUID},
        ("parcel", UUID, "--country", "ca"),
        COMMON_INPUT,
        COMMON_WIRE,
    ),
    Operation(
        "GET",
        "/ca/parcels/apn",
        "apn",
        {"country": "ca", "parcelnumb": "00096376"},
        ("apn", "00096376", "--country", "ca"),
        {**COMMON_INPUT, "path": CA_PATH, "limit": 2},
        {**COMMON_WIRE, "parcelnumb": "00096376", "path": CA_PATH, "limit": "2"},
    ),
    Operation(
        "GET",
        "/ca/parcels/query",
        "query",
        {"country": "ca", "fields": CA_FIELDS},
        ("query", "--country", "ca", "--fields", json.dumps(CA_FIELDS)),
        {**COMMON_INPUT, **SPATIAL_INPUT, **CURSOR_INPUT, "geojson": POINT, "path": CA_PATH},
        {
            **COMMON_WIRE,
            **SPATIAL_WIRE,
            **CURSOR_WIRE,
            **CA_FIELD_WIRE,
            "geojson": POINT_JSON,
            "path": CA_PATH,
        },
    ),
    Operation(
        "GET",
        "/ca/parcels/path",
        "parcel_path",
        {"country": "ca", "path": CA_PARCEL_PATH},
        ("parcel-path", CA_PARCEL_PATH, "--country", "ca"),
        COMMON_INPUT,
        {**COMMON_WIRE, "path": CA_PARCEL_PATH},
    ),
    Operation(
        "GET",
        "/ca/verse",
        "verse",
        {"country": "ca"},
        ("verse", "--country", "ca"),
        {"return_geometry": False},
        {"return_geometry": "false"},
    ),
    Operation(
        "GET",
        "/ca/usage",
        "usage",
        {"country": "ca"},
        ("usage", "--country", "ca"),
        USAGE_INPUT,
        USAGE_WIRE,
    ),
]


def assert_contract(request, operation):
    expected = operation.expected if operation.public else {**operation.expected, "token": TOKEN}
    assert request.method == operation.verb
    assert request.url.scheme == "https"
    assert request.url.host == "app.regrid.com"
    assert request.url.path == "/api/v2" + operation.path
    assert sorted(request.url.params.multi_items()) == sorted(expected.items())
    if operation.body is None:
        assert request.content == b""
    else:
        assert request.headers["content-type"] == "application/json"
        assert json.loads(request.content) == operation.body


@pytest.mark.parametrize("operation", OPERATIONS, ids=lambda case: case.id)
def test_all_openapi_operations_through_sdk(operation):
    seen = []
    response = {"contract": operation.id, "future_metadata": {"nullable": None}}

    def handler(request):
        seen.append(request)
        assert_contract(request, operation)
        return httpx.Response(200, json=response)

    with RegridClient(TOKEN, transport=httpx.MockTransport(handler)) as client:
        assert getattr(client, operation.sdk)(**operation.kwargs, **operation.options) == response
    assert len(seen) == 1


@pytest.mark.parametrize("operation", OPERATIONS, ids=lambda case: case.id)
def test_all_openapi_operations_through_cli(operation, monkeypatch, capsys):
    seen = []
    response = {"contract": operation.id, "future_metadata": {"nullable": None}}

    def handler(request):
        seen.append(request)
        assert_contract(request, operation)
        return httpx.Response(200, json=response)

    monkeypatch.setenv("REGRID_TOKEN", TOKEN)
    monkeypatch.setattr(
        cli,
        "RegridClient",
        lambda **kwargs: RegridClient(**kwargs, transport=httpx.MockTransport(handler)),
    )
    argv = list(operation.command)
    if operation.options:
        argv += ["--options", json.dumps(operation.options)]
    assert cli.main(argv) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out) == response
    assert len(seen) == 1


@pytest.mark.parametrize(
    "method,country,verb,forbidden",
    [
        ("point", "us", "POST", "offset_id"),
        ("point", "us", "POST", "return_geometry"),
        ("point", "ca", "POST", "offset_id"),
        ("point", "ca", "POST", "return_geometry"),
        ("point", "ca", "GET", "return_custom_id"),
        ("point", "ca", "GET", "return_matched_buildings"),
        ("area", "ca", "GET", "return_custom_id"),
        ("area", "ca", "POST", "return_zoning"),
        ("query", "ca", "GET", "return_enhanced_ownership"),
        ("address", "us", "GET", "return_count"),
        ("address", "us", "GET", "return_geometry"),
        ("address", "ca", "GET", "return_parcels"),
        ("apn", "us", "GET", "offset_id"),
        ("owner", "us", "GET", "return_count"),
        ("parcel", "us", "GET", "limit"),
        ("parcel_path", "ca", "GET", "return_custom_id"),
    ],
)
def test_endpoint_specific_parameter_exclusions(method, country, verb, forbidden):
    calls = []

    def handler(request):
        calls.append(request)
        pytest.fail("Undocumented option reached the API")

    arguments = {
        "point": {"geojson": POINT, "method": verb},
        "area": {"geojson": POINT, "method": verb},
        "query": {"fields": US_FIELDS},
        "address": {"query": "Main"},
        "apn": {"parcelnumb": "0001"},
        "owner": {"owner": "Smith"},
        "parcel": {"ll_uuid": UUID},
        "parcel_path": {"path": US_PARCEL_PATH},
    }[method]
    with RegridClient(TOKEN, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError):
            getattr(client, method)(country=country, **arguments, **{forbidden: True})
    assert calls == []
