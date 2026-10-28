"""Public SDK, typed validation, and CLI UTFGrid integration contracts."""

import json

import httpx
import pytest

from regrid import RegridClient, RegridDecodeError, TypedRegridClient, cli
from regrid.models import UTFGridResponse

METADATA = {"grid": "/interactive/{z}/{x}/{y}?token=stale"}
PAYLOAD = {"grid": [" !"], "keys": ["", "parcel-1"], "data": {"parcel-1": {"owner": None}}}


@pytest.mark.parametrize("typed", [False, True])
def test_public_grid_discovers_template_and_retains_response(typed):
    seen = []
    payload = {**PAYLOAD, "future": {"nullable": None}}

    def handle(request):
        seen.append(request)
        return httpx.Response(200, json=METADATA if len(seen) == 1 else payload)

    client_type = TypedRegridClient if typed else RegridClient
    with client_type("current", transport=httpx.MockTransport(handle)) as client:
        result = client.grid(10, 3, 4)
    assert (result.to_dict() if typed else result) == payload
    if typed:
        assert isinstance(result, UTFGridResponse)
        assert result.data["parcel-1"]["owner"] is None
    assert [str(request.url) for request in seen] == [
        "https://tiles.regrid.com/api/v1/parcels?token=current",
        "https://tiles.regrid.com/interactive/10/3/4?token=current",
    ]


@pytest.mark.parametrize("payload", [{}, {**PAYLOAD, "grid": [123]}, {**PAYLOAD, "keys": "bad"}])
def test_typed_grid_rejects_malformed_payload_without_sensitive_context(payload):
    payload = {**payload, "private": "response-secret"}
    with TypedRegridClient(
        "current", transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    ) as client:
        with pytest.raises(RegridDecodeError) as caught:
            client.grid(10, 3, 4, metadata=METADATA)
    assert "response-secret" not in str(caught.value)
    assert caught.value.__context__ is None


@pytest.mark.parametrize("source", ["discovery", "inline", "file"])
def test_cli_grid_runs_real_sdk_and_outputs_json(source, monkeypatch, capsys, tmp_path):
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(
            200, json=METADATA if request.url.path == "/api/v1/parcels" else PAYLOAD
        )

    monkeypatch.setenv("REGRID_TOKEN", "current")
    monkeypatch.setattr(
        cli,
        "RegridClient",
        lambda **kwargs: RegridClient(**kwargs, transport=httpx.MockTransport(handle)),
    )
    argv = ["grid", "10", "3", "4"]
    if source == "inline":
        argv += ["--metadata", json.dumps(METADATA)]
    elif source == "file":
        file = tmp_path / "metadata.json"
        file.write_text(json.dumps(METADATA))
        argv += ["--metadata", "@" + str(file)]
    assert cli.main(argv) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == PAYLOAD
    assert captured.err == ""
    assert len(seen) == (2 if source == "discovery" else 1)
    assert str(seen[-1].url) == "https://tiles.regrid.com/interactive/10/3/4?token=current"


def test_cli_grid_rejects_cross_origin_metadata_before_network(monkeypatch, capsys):
    seen = []
    monkeypatch.setenv("REGRID_TOKEN", "current")
    monkeypatch.setattr(
        cli,
        "RegridClient",
        lambda **kwargs: RegridClient(
            **kwargs, transport=httpx.MockTransport(lambda request: seen.append(request))
        ),
    )
    assert (
        cli.main(
            [
                "grid",
                "10",
                "3",
                "4",
                "--metadata",
                '{"grid":"https://evil.example/{z}/{x}/{y}?token=metadata-secret"}',
            ]
        )
        == 1
    )
    assert seen == []
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "regrid: Invalid input or output file\n"
