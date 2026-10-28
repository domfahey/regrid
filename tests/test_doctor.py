import pytest

from regrid import doctor


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
    assert ("PASS .env exists" in output) == exists
    assert ("PASS REGRID_TOKEN configured" in output) == (token == "secret-value")
    assert "secret-value" not in output
    assert "replace_with_your_regrid_api_token" not in output
