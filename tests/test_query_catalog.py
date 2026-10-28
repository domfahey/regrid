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


@pytest.mark.parametrize(
    "fields",
    [
        {"new_field": {"eq": "value"}},
        {"geoid": {"gt": "00123"}},
        {"ll_gisacre": {"eq": True}},
        {"ll_gisacre": {"between": [1]}},
        {"owner": {"in": "SMITH"}},
        {"owner": {"isnull": "true"}},
        {"rdi": {"ilike": "R"}},
        {"struct": {"eq": "true"}},
    ],
)
def test_invalid_catalog_queries_never_send(fields):
    def forbidden(request):
        pytest.fail("invalid query reached transport")

    with RegridClient("test", transport=httpx.MockTransport(forbidden)) as client:
        with pytest.raises(ValueError) as error:
            client.query(fields, validate_fields=True)
    assert error.value.__context__ is None


def test_unknown_escape_hatch_and_legacy_queries_still_work():
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={})

    with RegridClient("test", transport=httpx.MockTransport(respond)) as client:
        client.query({"future": {"eq": "x"}}, validate_fields=True, allow_unknown_fields=True)
        client.query({"future": {"future_operator": "x"}})
    assert len(calls) == 2
    assert all("validate_fields" not in request.url.params for request in calls)


def test_catalog_is_not_applied_to_canadian_fields():
    with RegridClient("test", transport=httpx.MockTransport(lambda r: pytest.fail())) as client:
        with pytest.raises(ValueError, match="US"):
            client.query({"postcode": {"eq": "R0B 0J0"}}, country="ca", validate_fields=True)


@pytest.mark.parametrize(
    "fields",
    [
        {"ll_gisacre": {"order": "ASC"}},
        {"zoning": {"between": ["RS-1", "RS-9"], "order": "DESC"}},
        {"struct": {"eq": False, "isnull": True}},
        {"owner": {"in": ["SMITH", "JONES"]}},
        {"saledate": {"between": ["2020", "2021/04/22"]}},
    ],
)
def test_documented_operator_shapes_are_accepted(fields):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={})

    with RegridClient("test", transport=httpx.MockTransport(respond)) as client:
        client.query(fields, validate_fields=True)
    assert len(calls) == 1


def test_order_and_pagination_are_incompatible():
    with RegridClient("test", transport=httpx.MockTransport(lambda r: pytest.fail())) as client:
        with pytest.raises(ValueError, match="pagination"):
            client.query({"ll_gisacre": {"order": "ASC"}}, offset_id=0, validate_fields=True)


@pytest.mark.parametrize("flag", ["validate_fields", "allow_unknown_fields"])
def test_catalog_flags_require_real_booleans(flag):
    with RegridClient("test") as client:
        with pytest.raises(ValueError, match="booleans"):
            client.query({"owner": {"eq": "SMITH"}}, **{flag: "true"})


def test_unknown_escape_does_not_disable_four_field_maximum():
    with RegridClient("test", transport=httpx.MockTransport(lambda r: pytest.fail())) as client:
        with pytest.raises(ValueError):
            client.query(
                {f"future_{i}": {"eq": "x"} for i in range(5)},
                validate_fields=True,
                allow_unknown_fields=True,
            )


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
    assert "features" in capsys.readouterr().out
    assert len(calls) == 2
    assert (
        cli.main(
            ["query", "--fields", '{"new_field":{"eq":"sensitive-value"}}', "--validate-fields"]
        )
        == 1
    )
    assert "sensitive-value" not in capsys.readouterr().err
    assert len(calls) == 2
