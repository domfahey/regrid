"""No real models or credentials are accessed by these runner tests."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1] / "plugins/regrid-research/evals"
for name in ("discovery", "run_discovery_claude"):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
runner = sys.modules["run_discovery_claude"]


def success_trace():
    return "\n".join(
        json.dumps(item)
        for item in [
            {
                "type": "assistant",
                "message": {
                    "model": "claude-test-20261028",
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Read",
                            "input": {"file_path": "data/evidence.json"},
                        }
                    ],
                },
            },
            {"type": "result", "subtype": "success", "is_error": False},
        ]
    )


def test_suite_uses_restricted_argv_and_records_models(tmp_path, monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if command[-1] == "--version":
            return SimpleNamespace(stdout="2.test", returncode=0)
        assert kwargs["cwd"].is_dir()
        assert "REGRID_TOKEN" not in kwargs["env"]
        assert "execution is unavailable" in kwargs["input"]
        assert "--safe-mode" in command and "--restricted" in command
        assert command[command.index("--tools") + 1] == "Read,Glob,Grep"
        assert command[command.index("--mcp-config") + 1] == '{"mcpServers":{}}'
        assert kwargs["timeout"] == 90
        return SimpleNamespace(stdout=success_trace(), stderr="", returncode=0)

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    monkeypatch.setenv("REGRID_TOKEN", "test-secret-not-forwarded")
    report = runner.run_suite(tmp_path / "results")
    assert len(calls) == 25
    assert len(report["runs"]) == 24
    assert all(item["status"] == "completed" for item in report["runs"])
    assert report["runs"][0]["resolved_model_ids"] == ["claude-test-20261028"]
    assert report["runs"][0]["grading_status"] == "not_graded"


def test_auth_failure_stops_remaining_runs(tmp_path, monkeypatch):
    def fake_run(command, **kwargs):
        if command[-1] == "--version":
            return SimpleNamespace(stdout="2.test", returncode=0)
        return SimpleNamespace(
            stdout="", stderr="OAuth session expired; failed to refresh", returncode=1
        )

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    report = runner.run_suite(tmp_path / "results")
    assert report["runs"][0]["status"] == "blocked"
    assert report["runs"][0]["resolved_model_ids"] == []
    assert all(item["status"] == "not_run" for item in report["runs"][1:])


def test_timeout_is_not_success(tmp_path, monkeypatch):
    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, 1, output=b'{"type":"system"}\n')

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    report = runner.run_trial(
        "claude", "haiku", "checkpoint-correction", "skill", tmp_path, "2.test", 1, 0.25
    )
    assert report["status"] == "timed_out"
    assert report["helper_execution"] == "unavailable_read_only"


@pytest.mark.parametrize("timeout,budget", [(0, 1), (601, 1), (1, 0), (1, float("nan"))])
def test_invalid_limits(tmp_path, timeout, budget):
    with pytest.raises(ValueError):
        runner.run_suite(tmp_path / "results", timeout=timeout, budget=budget)
