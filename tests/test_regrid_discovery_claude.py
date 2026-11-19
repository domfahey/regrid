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


def auth_phrase_trace():
    phrases = "You are not logged in. authentication_error: please run /login"
    return "\n".join(
        json.dumps(item)
        for item in [
            {
                "type": "assistant",
                "message": {
                    "model": "claude-test-20261028",
                    "content": [{"type": "text", "text": phrases}],
                },
            },
            {
                "type": "user",
                "message": {
                    "content": [
                        {"type": "tool_result", "content": "OAuth token has expired " + phrases}
                    ]
                },
            },
            {"type": "result", "subtype": "success", "is_error": False, "result": phrases},
        ]
    )


def test_successful_trial_mentioning_auth_phrases_stays_completed(tmp_path, monkeypatch):
    def fake_run(command, **kwargs):
        return SimpleNamespace(stdout=auth_phrase_trace(), stderr="", returncode=0)

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    report = runner.run_trial(
        "claude", "haiku", "checkpoint-correction", "skill", tmp_path, "2.test", 1, 0.25
    )
    assert report["status"] == "completed"
    assert report["auth_blocked"] is False


def test_suite_continues_after_successful_trial_mentioning_auth_phrases(tmp_path, monkeypatch):
    def fake_run(command, **kwargs):
        if command[-1] == "--version":
            return SimpleNamespace(stdout="2.test", returncode=0)
        return SimpleNamespace(stdout=auth_phrase_trace(), stderr="", returncode=0)

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    report = runner.run_suite(tmp_path / "results")
    assert len(report["runs"]) == 24
    assert all(item["status"] == "completed" for item in report["runs"])


def test_error_result_event_auth_failure_is_blocked(tmp_path, monkeypatch):
    trace = "\n".join(
        json.dumps(item)
        for item in [
            {"type": "assistant", "message": {"model": "claude-test-20261028", "content": []}},
            {
                "type": "result",
                "subtype": "error_during_execution",
                "is_error": True,
                "result": "Not logged in - Please run /login",
            },
        ]
    )

    def fake_run(command, **kwargs):
        return SimpleNamespace(stdout=trace, stderr="", returncode=1)

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    report = runner.run_trial(
        "claude", "haiku", "checkpoint-correction", "skill", tmp_path, "2.test", 1, 0.25
    )
    assert report["status"] == "blocked"
    assert report["auth_blocked"] is True


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


def test_observed_logged_out_cli_trace_is_blocked(tmp_path, monkeypatch):
    # Shape recorded from Claude CLI 2.1.327 with no login: exit 1, empty stderr, a synthetic
    # assistant message, and an error result that still reports subtype "success".
    trace = "\n".join(
        json.dumps(item)
        for item in [
            {"type": "system", "subtype": "init", "model": "claude-haiku-5-5"},
            {
                "type": "assistant",
                "error": "authentication_failed",
                "message": {
                    "model": "<synthetic>",
                    "content": [{"type": "text", "text": "Not logged in · Please run /login"}],
                },
            },
            {
                "type": "result",
                "subtype": "success",
                "is_error": True,
                "terminal_reason": "api_error",
                "result": "Not logged in · Please run /login",
            },
        ]
    )

    def fake_run(command, **kwargs):
        return SimpleNamespace(stdout=trace, stderr="", returncode=1)

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    report = runner.run_trial(
        "claude", "haiku", "checkpoint-correction", "skill", tmp_path, "2.test", 1, 0.25
    )
    assert report["status"] == "blocked"
    assert report["auth_blocked"] is True


def test_parse_trace_ignores_blank_lines():
    events, invalid = runner.parse_trace('{"type": "a"}\n\n   \n{"type": "b"}\n\n')
    assert [event["type"] for event in events] == ["a", "b"]
    assert invalid == 0


def test_blank_trace_lines_do_not_fail_successful_trial(tmp_path, monkeypatch):
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(
            stdout="\n" + success_trace() + "\n\n", stderr="", returncode=0
        ),
    )
    report = runner.run_trial(
        "claude", "haiku", "existing-evidence", "skill", tmp_path, "2.test", 90, 0.5
    )
    assert report["status"] == "completed"
    assert report["invalid_trace_lines"] == 0


NULL_EVENTS = [
    {"type": "assistant", "message": None},
    {"type": "assistant", "message": {"model": None, "content": None}},
    {"type": "assistant", "message": {"content": [{"type": "tool_use"}]}},
    {
        "type": "assistant",
        "message": {"content": [{"type": "tool_use", "name": "Read", "input": None}]},
    },
    {"type": "assistant", "message": {"content": [None, "text"]}},
]


def test_extract_calls_tolerates_null_fields():
    models, calls = sys.modules["discovery"].extract_calls(NULL_EVENTS)
    assert models == set()
    assert calls == [{"name": None, "input": {}}, {"name": "Read", "input": {}}]


def test_record_tolerates_null_fields(tmp_path):
    trace = tmp_path / "trace.jsonl"
    trace.write_text("\n".join(json.dumps(event) for event in NULL_EVENTS) + "\n")
    report = sys.modules["discovery"].record({}, trace, "claude-test-1", "2.test")
    assert report["read_paths"] == [None]
    assert len(report["tool_calls"]) == 2


def test_non_object_tool_input_is_preserved():
    events = [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Read", "input": '{"file_path": "x.md"}'},
                    {"type": "tool_use", "name": "Read", "input": {"file_path": "y.md"}},
                ]
            },
        }
    ]
    _, calls = sys.modules["discovery"].extract_calls(events)
    assert calls[0]["input"] == '{"file_path": "x.md"}'
    assert sys.modules["discovery"].read_paths(calls) == [None, "y.md"]
