"""Run read-only discovery trials through Claude CLI; grade separately."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import discovery

MODELS = ("haiku", "sonnet", "opus")


def argv(cli: str, model: str, budget: float) -> list[str]:
    return [
        cli,
        "--print",
        "--model",
        model,
        "--safe-mode",
        "--restricted",
        "--tools",
        "Read,Glob,Grep",
        "--allowedTools",
        "Read,Glob,Grep",
        "--strict-mcp-config",
        "--mcp-config",
        '{"mcpServers":{}}',
        "--no-session-persistence",
        "--permission-mode",
        "dontAsk",
        "--permission-prompts",
        "none",
        "--setting-sources",
        "",
        "--output-format",
        "stream-json",
        "--verbose",
        "--max-budget-usd",
        str(budget),
    ]


def environment() -> dict[str, str]:
    # CLI retains its normal OAuth store, but no project/API credentials are inherited.
    return {
        key: value
        for key, value in os.environ.items()
        if key in {"HOME", "PATH", "TMPDIR", "LANG", "LC_ALL", "CLAUDE_CONFIG_DIR"}
    }


def text_output(value: str | bytes | None) -> str:
    return value.decode(errors="replace") if isinstance(value, bytes) else value or ""


def parse_trace(raw: str) -> tuple[list[dict[str, Any]], int]:
    events, invalid = [], 0
    for line in raw.splitlines():
        try:
            event = json.loads(line)
            if not isinstance(event, dict):
                raise ValueError("non-object event")
            events.append(event)
        except ValueError:
            invalid += 1
    return events, invalid


def run_trial(
    cli: str,
    model: str,
    case: str,
    variant: str,
    output: Path,
    version: str,
    timeout: float,
    budget: float,
) -> dict[str, Any]:
    destination = output / f"{model}-{case}-{variant}"
    destination.mkdir()
    with tempfile.TemporaryDirectory(prefix="regrid-discovery-") as temporary:
        workspace = Path(temporary) / "trial"
        manifest = discovery.stage(case, variant, workspace)
        prompt = json.loads((workspace / "prompt.json").read_text())
        prompt["execution_limit"] = (
            "Only Read, Glob, and Grep are available. Python/helper execution is unavailable. Do not claim to have executed a validator."
        )
        prompt_text = json.dumps(prompt)
        (workspace / "prompt.json").write_text(prompt_text)
        (destination / "prompt.json").write_text(prompt_text)
        manifest["files"]["prompt.json"] = hashlib.sha256(prompt_text.encode()).hexdigest()
        command = argv(cli, model, budget)
        status, returncode = "failed", None
        try:
            process = subprocess.run(
                command,
                input=prompt_text,
                cwd=workspace,
                env=environment(),
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
            raw, stderr, returncode = process.stdout, process.stderr, process.returncode
        except subprocess.TimeoutExpired as exc:
            raw, stderr = text_output(exc.stdout), text_output(exc.stderr)
            status = "timed_out"
        except OSError as exc:
            raw, stderr = "", str(exc)
        events, invalid = parse_trace(raw)
        models, calls = set(), []
        for event in events:
            message = event.get("message", {})
            if message.get("model"):
                models.add(message["model"])
            for block in message.get("content", []):
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    calls.append({"name": block.get("name"), "input": block.get("input", {})})
        results = [event for event in events if event.get("type") == "result"]
        if (
            returncode == 0
            and results
            and results[-1].get("subtype") == "success"
            and not results[-1].get("is_error")
            and models
            and not invalid
        ):
            status = "completed"
        auth_blocked = any(
            term in (raw + stderr).lower()
            for term in (
                "oauth token has expired",
                "oauth session",
                "failed to refresh",
                "authentication_error",
                "not logged in",
                "please run /login",
            )
        )
        if auth_blocked or (not models and status != "timed_out"):
            status = "blocked"
        report = {
            **manifest,
            "requested_model": model,
            "resolved_model_ids": sorted(models),
            "observed_models": sorted(models),
            "read_paths_semantics": "requested reads; verify successful tool_result evidence separately",
            "cli_version": version,
            "argv": command,
            "timeout_seconds": timeout,
            "max_budget_usd": budget,
            "status": status,
            "returncode": returncode,
            "auth_blocked": auth_blocked,
            "invalid_trace_lines": invalid,
            "tool_calls": calls,
            "read_paths": [c["input"].get("file_path") for c in calls if c["name"] == "Read"],
            "helper_execution": "unavailable_read_only",
            "grading_status": "not_graded",
            "scope": "CLI navigation trial; not Cowork acceptance or executed helper validation",
        }
        (destination / "trace.jsonl").write_text(raw)
        (destination / "stderr.txt").write_text(stderr)
        (destination / "record.json").write_text(json.dumps(report, indent=2) + "\n")
        return report


def run_suite(
    output: Path, cli: str = "claude", timeout: float = 90, budget: float = 0.25
) -> dict[str, Any]:
    if not math.isfinite(timeout) or not 1 <= timeout <= 600:
        raise ValueError("timeout must be between 1 and 600 seconds")
    if not math.isfinite(budget) or not 0 < budget <= 5:
        raise ValueError("per-trial budget must be greater than zero and at most 5 USD")
    output.mkdir(parents=True, exist_ok=False)
    try:
        version_result = subprocess.run(
            [cli, "--version"],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
            env=environment(),
        )
        version = version_result.stdout.strip() if version_result.returncode == 0 else "unavailable"
    except (OSError, subprocess.TimeoutExpired):
        version = "unavailable"
    cases = discovery.read_json(discovery.ROOT / "discovery-cases.json")
    reports, blocked = [], version == "unavailable"
    deadline = time.monotonic() + 900  # Bound the complete suite to 15 minutes.
    for model in MODELS:
        for case in cases:
            for variant in ("skill", "baseline"):
                remaining = deadline - time.monotonic()
                if blocked or remaining < 1:
                    report = {
                        "requested_model": model,
                        "case_id": case["id"],
                        "variant": variant,
                        "status": "not_run",
                        "reason": "CLI unavailable, earlier authentication failure, or suite time limit",
                    }
                else:
                    report = run_trial(
                        cli,
                        model,
                        case["id"],
                        variant,
                        output,
                        version,
                        min(timeout, remaining),
                        budget,
                    )
                    blocked = report["auth_blocked"] or report["status"] == "blocked"
                reports.append(report)
                (output / "summary.json").write_text(json.dumps({"runs": reports}, indent=2) + "\n")
    return {"runs": reports}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New results directory")
    parser.add_argument("--cli", default="claude")
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--max-budget-usd", type=float, default=0.25)
    args = parser.parse_args()
    try:
        report = run_suite(args.output.resolve(), args.cli, args.timeout, args.max_budget_usd)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Discovery runner failed: {exc}\n")
    completed = sum(item["status"] == "completed" for item in report["runs"])
    print(f"Completed {completed}/{len(report['runs'])} trials; grading remains separate.")
    raise SystemExit(0 if completed == len(report["runs"]) else 1)


if __name__ == "__main__":
    main()
