"""CI workflow guards for the Windows offline-helper job."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WINDOWS_TESTS = (
    "test_regrid_map.py",
    "test_skill_helper_sync.py",
    "test_offline_fields.py",
    "test_offline_freshness.py",
    "test_cli_offline.py",
    "test_cli_freshness.py",
)


def windows_job() -> str:
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    match = re.search(r"^  windows:\n(.*?)(?=^  \S|\Z)", ci, re.DOTALL | re.MULTILINE)
    assert match, "ci.yml has no windows job"
    return match.group(1)


def test_windows_job_runs_on_windows():
    assert "runs-on: windows-latest" in windows_job()


@pytest.mark.parametrize("name", WINDOWS_TESTS)
def test_windows_job_pytest_command_lists_offline_test(name):
    # Scoped to the windows job (not the whole file) and to the pytest invocation itself.
    command = windows_job().split("uv run pytest", 1)[1]
    assert f"tests/{name}" in command.split()


def test_windows_job_only_lists_test_files_that_exist():
    listed = re.findall(r"tests/(\S+\.py)", windows_job())
    assert set(WINDOWS_TESTS) <= set(listed)
    assert [name for name in listed if not (ROOT / "tests" / name).is_file()] == []
