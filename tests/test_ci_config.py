"""CI workflow guards for the Windows offline-helper job."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WINDOWS_TESTS = (
    "test_regrid_map.py",
    "test_regrid_workflow.py",
    "test_regrid_workflow_composition.py",
    "test_skill_helper_sync.py",
    "test_offline_fields.py",
    "test_offline_freshness.py",
    "test_cli_offline.py",
    "test_cli_freshness.py",
)


def windows_job() -> str:
    """Return the lines nested under the `windows:` job key, whatever the indentation."""
    lines = (ROOT / ".github/workflows/ci.yml").read_text().splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip() == "windows:"), None)
    assert start is not None, "ci.yml has no windows job"
    indent = len(lines[start]) - len(lines[start].lstrip())
    body = []
    for line in lines[start + 1 :]:
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            break
        body.append(line)
    return "\n".join(body)


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
