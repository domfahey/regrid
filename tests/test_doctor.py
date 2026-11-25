import runpy
import sys

import pytest

from regrid import doctor

FOOTER = "Local check only; API authentication was not tested"


@pytest.mark.parametrize("exists", [False, True])
@pytest.mark.parametrize(
    "token", [None, "", "  ", "replace_with_your_regrid_api_token", "secret-value"]
)
def test_configuration_checks(tmp_path, monkeypatch, capsys, exists, token):
    monkeypatch.chdir(tmp_path)
    if exists:
        (tmp_path / ".env").touch()
    if token is None:
        monkeypatch.delenv("REGRID_TOKEN", raising=False)
    else:
        monkeypatch.setenv("REGRID_TOKEN", token)
    assert doctor.main() == (0 if exists and token == "secret-value" else 1)
    output = capsys.readouterr().out
    assert output.splitlines() == [
        "PASS .env exists" if exists else "FAIL .env missing",
        "PASS REGRID_TOKEN configured"
        if token == "secret-value"
        else "FAIL REGRID_TOKEN missing or placeholder",
        FOOTER,
    ]
    assert "secret-value" not in output
    assert "replace_with_your_regrid_api_token" not in output


def test_module_entrypoint(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").touch()
    monkeypatch.setenv("REGRID_TOKEN", "secret-value")
    monkeypatch.delitem(sys.modules, "regrid.doctor", raising=False)
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("regrid.doctor", run_name="__main__")
    assert exc.value.code == 0
    output = capsys.readouterr().out
    assert output.splitlines() == [
        "PASS .env exists",
        "PASS REGRID_TOKEN configured",
        FOOTER,
    ]
    assert "secret-value" not in output
