"""Run read-only discovery trials through Claude CLI; grade separately."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_DISCOVERY_PATH = Path(__file__).resolve().with_name("discovery.py")
_existing_discovery = sys.modules.get("discovery")
_existing_file = getattr(_existing_discovery, "__file__", None)
if (
    _existing_discovery is not None
    and _existing_file
    and Path(_existing_file).resolve() == _DISCOVERY_PATH
):
    discovery = _existing_discovery
else:
    _discovery_spec = importlib.util.spec_from_file_location("discovery", _DISCOVERY_PATH)
    assert _discovery_spec and _discovery_spec.loader
    discovery = importlib.util.module_from_spec(_discovery_spec)
    sys.modules["discovery"] = discovery
    _discovery_spec.loader.exec_module(discovery)

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
    # CLI retains its normal OAuth store (including macOS Keychain account lookup via USER/LOGNAME
    # and Windows profile vars), while project/API credentials are never inherited.
    allowed = {
        "HOME",
        "PATH",
        "TMPDIR",
        "LANG",
        "LC_ALL",
        "USER",
        "LOGNAME",
        "USERNAME",
        "USERPROFILE",
        "LOCALAPPDATA",
        "APPDATA",
        "CLAUDE_CONFIG_DIR",
    }
    return {key: value for key, value in os.environ.items() if key in allowed}


def text_output(value: str | bytes | None) -> str:
    return value.decode(errors="replace") if isinstance(value, bytes) else value or ""


def parse_trace(raw: str) -> tuple[list[dict[str, Any]], int]:
    events, invalid = [], 0
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
            if not isinstance(event, dict):
                raise ValueError("non-object event")
            events.append(event)
        except ValueError:
            invalid += 1
    return events, invalid


AUTH_TERMS = (
    "oauth token has expired",
    "oauth session",
    "failed to refresh",
    "authentication_error",
    "not logged in",
    "please run /login",
)


def is_error_event(event: dict[str, Any]) -> bool:
    kind, subtype = event.get("type"), str(event.get("subtype") or "")
    if kind == "result":
        return bool(event.get("is_error")) or subtype != "success"
    if kind == "error":
        return True
    return kind == "system" and ("error" in event or "error" in subtype)


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
        manifest = discovery.stage(
            case,
            variant,
            workspace,
            execution_limit=(
                "Only Read, Glob, and Grep are available. Python/helper execution is unavailable. "
                "Do not claim to have executed a validator."
            ),
        )
        prompt_text = (workspace / "prompt.json").read_text(encoding="utf-8")
        (destination / "prompt.json").write_text(prompt_text, encoding="utf-8")
        command = argv(cli, model, budget)
        status, returncode = "failed", None
        try:
            process = subprocess.run(
                command,
                input=prompt_text,
                cwd=workspace,
                env=environment(),
                text=True,
                encoding="utf-8",
                errors="replace",
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
        models, calls = discovery.extract_calls(events)
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
        auth_blocked = False
        if status != "completed":
            # Scan only places failures are reported, never assistant text or tool results.
            error_text = stderr + "".join(
                json.dumps(event) for event in events if is_error_event(event)
            )
            auth_blocked = any(term in error_text.lower() for term in AUTH_TERMS)
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
            "read_paths": discovery.read_paths(calls),
            "trace_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            "helper_execution": "unavailable_read_only",
            "grading_status": "not_graded",
            "scope": "CLI navigation trial; not Cowork acceptance or executed helper validation",
        }
        with (destination / "trace.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(raw)
        (destination / "stderr.txt").write_text(stderr, encoding="utf-8")
        (destination / "record.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        return report


def run_suite(
    output: Path,
    cli: str = "claude",
    timeout: float = 90,
    budget: float = 0.50,
    models: tuple[str, ...] | None = None,
    case_ids: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    if not math.isfinite(timeout) or not 1 <= timeout <= 600:
        raise ValueError("timeout must be between 1 and 600 seconds")
    if not math.isfinite(budget) or not 0 < budget <= 5:
        raise ValueError("per-trial budget must be greater than zero and at most 5 USD")
    selected_models = MODELS if models is None else tuple(dict.fromkeys(models))
    invalid_models = [model for model in selected_models if model not in MODELS]
    if not selected_models or invalid_models:
        raise ValueError(f"Unknown model filter: {', '.join(invalid_models) or 'empty'}")
    all_cases = discovery.read_json(discovery.ROOT / "discovery-cases.json")
    cases_by_id = {case["id"]: case for case in all_cases}
    if case_ids is None:
        cases = all_cases
    else:
        selected_ids = tuple(dict.fromkeys(case_ids))
        invalid_cases = [cid for cid in selected_ids if cid not in cases_by_id]
        if not selected_ids or invalid_cases:
            raise ValueError(f"Unknown case filter: {', '.join(invalid_cases) or 'empty'}")
        cases = [cases_by_id[cid] for cid in selected_ids]
    output.mkdir(parents=True, exist_ok=False)
    try:
        version_result = subprocess.run(
            [cli, "--version"],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=10,
            check=False,
            env=environment(),
        )
        version = version_result.stdout.strip() if version_result.returncode == 0 else "unavailable"
    except (OSError, subprocess.TimeoutExpired):
        version = "unavailable"
    reports, blocked = [], version == "unavailable"
    deadline = time.monotonic() + 900  # Bound the complete suite to 15 minutes.
    for model in selected_models:
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
                (output / "summary.json").write_text(
                    json.dumps({"runs": reports}, indent=2) + "\n", encoding="utf-8"
                )
    return {"runs": reports}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New results directory")
    parser.add_argument("--cli", default="claude")
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--max-budget-usd", type=float, default=0.50)
    parser.add_argument(
        "--model",
        action="append",
        dest="models",
        choices=MODELS,
        help="Optional model filter (repeatable; defaults to all three models)",
    )
    parser.add_argument(
        "--case",
        action="append",
        dest="cases",
        help="Optional case ID filter (repeatable; defaults to all discovery cases)",
    )
    args = parser.parse_args()
    try:
        report = run_suite(
            args.output.resolve(),
            args.cli,
            args.timeout,
            args.max_budget_usd,
            models=tuple(args.models) if args.models else None,
            case_ids=tuple(args.cases) if args.cases else None,
        )
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Discovery runner failed: {exc}\n")
    completed = sum(item["status"] == "completed" for item in report["runs"])
    print(f"Completed {completed}/{len(report['runs'])} trials; grading remains separate.")
    raise SystemExit(0 if completed == len(report["runs"]) else 1)


if __name__ == "__main__":
    main()
