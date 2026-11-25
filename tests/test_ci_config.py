"""CI workflow guards for the Ubuntu check matrix and Windows offline-helper job."""

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


def ci_text() -> str:
    """Return the raw contents of `.github/workflows/ci.yml`."""
    return (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")


def job_section(name: str) -> str:
    """Return the lines nested under the named job key, whatever the indentation."""
    lines = ci_text().splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip() == f"{name}:"), None)
    assert start is not None, f"ci.yml has no {name} job"
    indent = len(lines[start]) - len(lines[start].lstrip())
    body = []
    for line in lines[start + 1 :]:
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            break
        body.append(line)
    return "\n".join(body)


def job_steps(job_body: str) -> list[str]:
    """Split a job body's `steps:` block into individual `- ...` step blocks."""
    lines = job_body.splitlines()
    steps_idx = next((i for i, line in enumerate(lines) if line.strip() == "steps:"), None)
    assert steps_idx is not None, "job has no steps block"
    steps_indent = len(lines[steps_idx]) - len(lines[steps_idx].lstrip())
    blocks: list[list[str]] = []
    for line in lines[steps_idx + 1 :]:
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= steps_indent:
            break
        if line.lstrip().startswith("- "):
            blocks.append([line])
        elif blocks:
            blocks[-1].append(line)
    return ["\n".join(block) for block in blocks]


def test_pip_install_uv_pins_exact_version():
    lines = [line.strip() for line in ci_text().splitlines() if "pip install uv" in line]
    assert len(lines) >= 2
    for line in lines:
        assert re.search(r"\bpip install uv==\d+\.\d+\.\d+\b", line), f"unpinned uv install: {line}"


def test_check_job_matrix_python_versions():
    check_body = job_section("check")
    match = re.search(r"^\s*python:\s*\[([^\]]+)\]", check_body, re.M)
    assert match is not None, "check job has no python matrix"
    versions = [item.strip().strip("'\"") for item in match.group(1).split(",")]
    assert versions == ["3.10", "3.12", "3.13"]


def test_check_job_gates_lint_typecheck_and_build_to_python_312():
    steps = job_steps(job_section("check"))

    def step_for(command_fragment: str) -> str:
        matches = [step for step in steps if command_fragment in step]
        assert len(matches) == 1, f"expected 1 step containing {command_fragment!r}, got {matches}"
        return matches[0]

    assert "if:" not in step_for("make install")
    assert "if: matrix.python == '3.12'" in step_for("make check")
    assert "if: matrix.python != '3.12'" in step_for("make test")
    assert "if:" not in step_for("make e2e")
    assert "if: matrix.python == '3.12'" in step_for("scripts/build_claude_plugins.py")
    assert "if: matrix.python == '3.12'" in step_for("uv build")


def test_windows_job_runs_on_windows():
    assert "runs-on: windows-latest" in job_section("windows")


@pytest.mark.parametrize("name", WINDOWS_TESTS)
def test_windows_job_pytest_command_lists_offline_test(name):
    # Scoped to the windows job (not the whole file) and to the pytest invocation itself.
    command = job_section("windows").split("uv run pytest", 1)[1]
    assert f"tests/{name}" in command.split()


def test_windows_job_only_lists_test_files_that_exist():
    listed = re.findall(r"tests/(\S+\.py)", job_section("windows"))
    assert set(WINDOWS_TESTS) <= set(listed)
    assert [name for name in listed if not (ROOT / "tests" / name).is_file()] == []
