"""No real models or credentials are accessed by these runner tests."""

import hashlib
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
EXPECTED_RUNS = (
    len(runner.MODELS)
    * len(
        sys.modules["discovery"].read_json(sys.modules["discovery"].ROOT / "discovery-cases.json")
    )
    * 2  # skill and baseline variants
)


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
    assert len(calls) == EXPECTED_RUNS + 1  # plus --version
    assert len(report["runs"]) == EXPECTED_RUNS
    assert all(item["status"] == "completed" for item in report["runs"])
    assert report["runs"][0]["resolved_model_ids"] == ["claude-test-20261028"]
    assert report["runs"][0]["grading_status"] == "not_graded"


def test_auth_failure_stops_remaining_runs(tmp_path, monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if command[-1] == "--version":
            return SimpleNamespace(stdout="2.test", returncode=0)
        return SimpleNamespace(
            stdout="", stderr="OAuth session expired; failed to refresh", returncode=1
        )

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    report = runner.run_suite(tmp_path / "results")
    assert report["runs"][0]["status"] == "blocked"
    assert report["runs"][0]["resolved_model_ids"] == []
    assert report["runs"][0]["auth_blocked"] is True
    assert len(report["runs"]) == EXPECTED_RUNS
    assert all(item["status"] == "not_run" for item in report["runs"][1:])
    assert len(calls) == 2  # --version plus the single blocked trial; nothing after it runs


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
    assert len(report["runs"]) == EXPECTED_RUNS
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


@pytest.mark.parametrize(
    ("timeout", "budget", "message"),
    [
        (0, 1, "timeout must be between 1 and 600 seconds"),
        (601, 1, "timeout must be between 1 and 600 seconds"),
        (1, 0, "per-trial budget must be greater than zero"),
        (1, float("nan"), "per-trial budget must be greater than zero"),
    ],
)
def test_invalid_limits(tmp_path, monkeypatch, timeout, budget, message):
    def forbidden(*args, **kwargs):
        pytest.fail("invalid limits must be rejected before any CLI process starts")

    monkeypatch.setattr(runner.subprocess, "run", forbidden)
    with pytest.raises(ValueError, match=message):
        runner.run_suite(tmp_path / "results", timeout=timeout, budget=budget)
    assert not (tmp_path / "results").exists()


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


def test_run_discovery_claude_imports_without_preseeded_discovery(tmp_path, monkeypatch):
    monkeypatch.delitem(sys.modules, "discovery", raising=False)
    monkeypatch.setattr(sys, "path", [entry for entry in sys.path if Path(entry).resolve() != ROOT])
    monkeypatch.chdir(tmp_path)
    fresh_spec = importlib.util.spec_from_file_location(
        "fresh_run_discovery_claude", ROOT / "run_discovery_claude.py"
    )
    assert fresh_spec and fresh_spec.loader
    fresh_module = importlib.util.module_from_spec(fresh_spec)
    fresh_spec.loader.exec_module(fresh_module)
    assert fresh_module.discovery.ROOT == ROOT


def test_run_trial_includes_trace_sha256_and_is_directly_comparable(tmp_path, monkeypatch):
    trace = success_trace()
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(stdout=trace, stderr="", returncode=0),
    )
    skill_report = runner.run_trial(
        "claude", "haiku", "existing-evidence", "skill", tmp_path, "2.test", 90, 0.5
    )
    baseline_report = runner.run_trial(
        "claude", "haiku", "existing-evidence", "baseline", tmp_path, "2.test", 90, 0.5
    )
    expected_sha = hashlib.sha256(trace.encode("utf-8")).hexdigest()
    assert skill_report["trace_sha256"] == expected_sha
    assert baseline_report["trace_sha256"] == expected_sha
    saved_record = json.loads(
        (tmp_path / "haiku-existing-evidence-skill/record.json").read_text(encoding="utf-8")
    )
    assert saved_record["trace_sha256"] == expected_sha
    prompt_bytes = (tmp_path / "haiku-existing-evidence-skill/prompt.json").read_bytes()
    assert skill_report["files"]["prompt.json"] == hashlib.sha256(prompt_bytes).hexdigest()
    comparison = sys.modules["discovery"].compare(skill_report, baseline_report)
    assert comparison["comparison_status"] == "comparable"
    assert comparison["case_id"] == "existing-evidence"
    assert comparison["model"] == "haiku"


def test_run_discovery_claude_ignores_shadowing_discovery_on_sys_path(tmp_path, monkeypatch):
    (tmp_path / "discovery.py").write_text('raise RuntimeError("shadowed")\n', encoding="utf-8")
    monkeypatch.delitem(sys.modules, "discovery", raising=False)
    monkeypatch.setattr(
        sys, "path", [str(tmp_path), *[e for e in sys.path if Path(e).resolve() != ROOT]]
    )
    monkeypatch.chdir(tmp_path)
    fresh_spec = importlib.util.spec_from_file_location(
        "shadow_safe_run_discovery_claude", ROOT / "run_discovery_claude.py"
    )
    assert fresh_spec and fresh_spec.loader
    fresh_module = importlib.util.module_from_spec(fresh_spec)
    fresh_spec.loader.exec_module(fresh_module)
    assert Path(fresh_module.discovery.__file__).resolve() == (ROOT / "discovery.py").resolve()


def test_subprocess_calls_use_utf8_replace_and_lf_trace(tmp_path, monkeypatch):
    sub_kwargs = []
    open_calls = []
    real_open = Path.open

    def fake_run(command, **kwargs):
        sub_kwargs.append((command[-1] == "--version", kwargs))
        if command[-1] == "--version":
            return SimpleNamespace(stdout="2.test", returncode=0)
        return SimpleNamespace(stdout=success_trace(), stderr="", returncode=0)

    def spy_open(self, *args, **kwargs):
        if self.name == "trace.jsonl":
            open_calls.append((args, kwargs))
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    monkeypatch.setattr(Path, "open", spy_open)
    report = runner.run_suite(tmp_path / "results")
    assert report["runs"][0]["status"] == "completed"
    assert len(sub_kwargs) == EXPECTED_RUNS + 1
    for _, kwargs in sub_kwargs:
        assert kwargs.get("encoding") == "utf-8"
        assert kwargs.get("errors") == "replace"
    assert len(open_calls) == EXPECTED_RUNS
    for _, kwargs in open_calls:
        assert kwargs.get("encoding") == "utf-8"
        assert kwargs.get("newline") == "\n"


def test_environment_preserves_os_identity_vars_but_strips_credentials(monkeypatch):
    monkeypatch.setenv("USER", "tester")
    monkeypatch.setenv("LOGNAME", "tester")
    monkeypatch.setenv("REGRID_TOKEN", "rg_secret_token_never_forward")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-never-forward")
    env = runner.environment()
    assert env.get("USER") == "tester"
    assert env.get("LOGNAME") == "tester"
    assert "REGRID_TOKEN" not in env
    assert "ANTHROPIC_API_KEY" not in env


def test_suite_defaults_to_half_dollar_budget_and_supports_filters(tmp_path, monkeypatch):
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        if command[-1] == "--version":
            return SimpleNamespace(stdout="2.test", returncode=0)
        return SimpleNamespace(stdout=success_trace(), stderr="", returncode=0)

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    report = runner.run_suite(
        tmp_path / "filtered",
        models=("opus", "opus"),
        case_ids=("structured-handoff",),
    )
    assert len(report["runs"]) == 2
    assert {(r["requested_model"], r["case_id"], r["variant"]) for r in report["runs"]} == {
        ("opus", "structured-handoff", "skill"),
        ("opus", "structured-handoff", "baseline"),
    }
    trial_commands = [cmd for cmd in commands if "--max-budget-usd" in cmd]
    assert len(trial_commands) == 2
    assert all(cmd[cmd.index("--max-budget-usd") + 1] == "0.5" for cmd in trial_commands)


@pytest.mark.parametrize(
    ("models", "case_ids", "message"),
    [
        (("unknown",), None, "Unknown model filter"),
        ((), None, "Unknown model filter"),
        (None, ("missing-case",), "Unknown case filter"),
        (None, (), "Unknown case filter"),
    ],
)
def test_invalid_suite_filters_fail_before_creating_output(
    tmp_path, monkeypatch, models, case_ids, message
):
    def forbidden(*args, **kwargs):
        pytest.fail("invalid filters must be rejected before starting CLI")

    monkeypatch.setattr(runner.subprocess, "run", forbidden)
    with pytest.raises(ValueError, match=message):
        runner.run_suite(tmp_path / "out", models=models, case_ids=case_ids)
    assert not (tmp_path / "out").exists()
