import json

import httpx
import pytest

from regrid import RegridClient


def test_catalog_query_preserves_wire_values_and_does_not_send_sdk_flags():
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"parcels": {"features": []}})

    with RegridClient("test", transport=httpx.MockTransport(respond)) as client:
        client.query(
            {"geoid": {"eq": "00123"}, "ll_gisacre": {"between": [1, 2.5]}}, validate_fields=True
        )
    assert len(requests) == 1
    assert dict(requests[0].url.params) == {
        "token": "test",
        "limit": "5",
        "return_parcels": "true",
        "fields[geoid][eq]": "00123",
        "fields[ll_gisacre][between]": "[1,2.5]",
    }


NOT_QUERYABLE = "Field is not queryable in the local catalog"
BAD_OPERATOR = "Operator is not supported for this catalog field"
BAD_VALUE = "Invalid value or pagination combination for catalog operator"


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"new_field": {"eq": "value"}}, NOT_QUERYABLE),
        ({"geoid": {"gt": "00123"}}, BAD_OPERATOR),
        ({"ll_gisacre": {"eq": True}}, BAD_VALUE),
        ({"ll_gisacre": {"between": [1]}}, BAD_VALUE),
        ({"ll_gisacre": {"between": [1, 2, 3]}}, BAD_VALUE),
        ({"owner": {"in": "SMITH"}}, BAD_VALUE),
        ({"owner": {"isnull": "true"}}, BAD_VALUE),
        ({"rdi": {"ilike": "R"}}, BAD_OPERATOR),
        ({"struct": {"eq": "true"}}, BAD_VALUE),
    ],
)
def test_invalid_catalog_queries_never_send(fields, message):
    seen = []

    def respond(request):
        seen.append(request)
        return httpx.Response(200, json={})

    with RegridClient("test", transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(ValueError) as error:
            client.query(fields, validate_fields=True)
    assert str(error.value) == message
    assert error.value.__context__ is None
    assert seen == []


def test_unknown_escape_hatch_and_legacy_queries_still_work():
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={})

    with RegridClient("test", transport=httpx.MockTransport(respond)) as client:
        client.query({"future": {"eq": "x"}}, validate_fields=True, allow_unknown_fields=True)
        client.query({"future": {"future_operator": "x"}})
    # SDK-only flags are consumed locally; the wire sees just the filter and defaults.
    assert [request.url.params.multi_items() for request in calls] == [
        [
            ("return_parcels", "true"),
            ("fields[future][eq]", "x"),
            ("limit", "5"),
            ("token", "test"),
        ],
        [
            ("return_parcels", "true"),
            ("fields[future][future_operator]", "x"),
            ("limit", "5"),
            ("token", "test"),
        ],
    ]


def test_catalog_is_not_applied_to_canadian_fields():
    with RegridClient("test", transport=httpx.MockTransport(lambda r: pytest.fail())) as client:
        with pytest.raises(ValueError, match="US"):
            client.query({"postcode": {"eq": "R0B 0J0"}}, country="ca", validate_fields=True)


@pytest.mark.parametrize(
    ("fields", "wire"),
    [
        ({"ll_gisacre": {"order": "ASC"}}, {"fields[ll_gisacre][order]": "ASC"}),
        (
            {"zoning": {"between": ["RS-1", "RS-9"], "order": "DESC"}},
            {"fields[zoning][between]": '["RS-1","RS-9"]', "fields[zoning][order]": "DESC"},
        ),
        (
            {"struct": {"eq": False, "isnull": True}},
            {"fields[struct][eq]": "false", "fields[struct][isnull]": "true"},
        ),
        ({"owner": {"in": ["SMITH", "JONES"]}}, {"fields[owner][in]": '["SMITH","JONES"]'}),
        (
            {"saledate": {"between": ["2020", "2021/04/22"]}},
            {"fields[saledate][between]": '["2020","2021/04/22"]'},
        ),
    ],
)
def test_documented_operator_shapes_are_accepted(fields, wire):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={})

    with RegridClient("test", transport=httpx.MockTransport(respond)) as client:
        client.query(fields, validate_fields=True)
    (request,) = calls
    assert dict(request.url.params) == {
        "token": "test",
        "limit": "5",
        "return_parcels": "true",
        **wire,
    }


def test_order_and_pagination_are_incompatible():
    seen = []
    transport = httpx.MockTransport(lambda r: seen.append(r))
    with RegridClient("test", transport=transport) as client:
        with pytest.raises(ValueError, match="pagination"):
            client.query({"ll_gisacre": {"order": "ASC"}}, offset_id=0, validate_fields=True)
    assert seen == []


@pytest.mark.parametrize("flag", ["validate_fields", "allow_unknown_fields"])
def test_catalog_flags_require_real_booleans(flag):
    seen = []
    transport = httpx.MockTransport(lambda r: seen.append(r))
    with RegridClient("test", transport=transport) as client:
        with pytest.raises(ValueError, match="booleans"):
            client.query({"owner": {"eq": "SMITH"}}, **{flag: "true"})
    assert seen == []


def test_unknown_escape_does_not_disable_four_field_maximum():
    seen = []
    transport = httpx.MockTransport(lambda r: (seen.append(r), httpx.Response(200, json={}))[1])
    with RegridClient("test", transport=transport) as client:
        with pytest.raises(ValueError, match="^Invalid Regrid request parameters$"):
            client.query(
                {f"future_{i}": {"eq": "x"} for i in range(5)},
                validate_fields=True,
                allow_unknown_fields=True,
            )
        assert seen == []
        # Four unknown fields are the documented maximum and still go out.
        client.query(
            {f"future_{i}": {"eq": "x"} for i in range(4)},
            validate_fields=True,
            allow_unknown_fields=True,
        )
    assert len(seen) == 1


def test_explicit_nonqueryable_field_cannot_bypass_catalog():
    with RegridClient("test", transport=httpx.MockTransport(lambda r: pytest.fail())) as client:
        with pytest.raises(ValueError, match="not queryable"):
            client.query({"tax_id": {"eq": "001"}}, validate_fields=True, allow_unknown_fields=True)


def test_typed_client_and_cli_expose_same_catalog_validation(monkeypatch, capsys):
    from regrid import TypedRegridClient, cli

    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={"parcels": {"type": "FeatureCollection", "features": []}})

    transport = httpx.MockTransport(respond)
    with TypedRegridClient("test", transport=transport) as client:
        result = client.query({"geoid": {"eq": "00123"}}, validate_fields=True)
        assert result.parcels.features == []
    monkeypatch.setenv("REGRID_TOKEN", "test")
    monkeypatch.setattr(
        cli, "RegridClient", lambda **kw: RegridClient(**kw, transport=httpx.MockTransport(respond))
    )
    assert cli.main(["query", "--fields", '{"geoid":{"eq":"00123"}}', "--validate-fields"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"parcels": {"type": "FeatureCollection", "features": []}}
    assert captured.err == "regrid: requests made: 1\n"
    assert len(calls) == 2
    assert all(call.url.params["fields[geoid][eq]"] == "00123" for call in calls)
    assert (
        cli.main(
            ["query", "--fields", '{"new_field":{"eq":"sensitive-value"}}', "--validate-fields"]
        )
        == 1
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "sensitive-value" not in captured.err
    assert captured.err.endswith("regrid: requests made: 0\n")
    assert len(calls) == 2
