"""Stage blinded filesystem discovery trials; never invoke a model or network."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
SKILL = ROOT.parent / "skills/property-research"
ALLOWLIST = (
    "SKILL.md",
    "references/mcp-tools.md",
    "references/tools.json",
    "references/endpoints.json",
    "references/composition.md",
    "references/batch.md",
    "references/result.schema.json",
    "references/result-example.json",
    "scripts/workflow.py",
)
DISTRACTORS = {
    "editing-spreadsheets": "Edits spreadsheet files and formats cells. Use when creating or changing spreadsheet files.",
    "planning-meetings": "Plans meeting agendas. Use for meeting preparation and discussion topics.",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def metadata(path: Path) -> dict[str, str]:
    text = path.read_text()
    front = text.split("---", 2)[1]
    result = {}
    for key in ("name", "description"):
        match = re.search(rf"^{key}:\s*(.+)$", front, re.MULTILINE)
        if not match:
            raise ValueError(f"Missing {key} metadata")
        result[key] = match.group(1).strip().strip("\"'")
    return result


def stage(case_id: str, variant: str, output: Path) -> dict[str, Any]:
    """Create a new workspace. An existing directory is never overwritten."""
    if variant not in {"skill", "baseline"}:
        raise ValueError("variant must be skill or baseline")
    cases = read_json(ROOT / "discovery-cases.json")
    case = next((item for item in cases if item["id"] == case_id), None)
    if case is None:
        raise ValueError("Unknown case")
    if output.exists():
        raise ValueError("Output directory already exists")
    # Check all sources before creating any workspace; never follow symlinks.
    for relative in ALLOWLIST:
        source = SKILL / relative
        if source.is_symlink() or any(p.is_symlink() for p in source.parents):
            raise ValueError("Skill source symlinks are not permitted")
        if not source.is_file():
            raise ValueError(f"Missing allowlisted source: {relative}")
    output.mkdir(parents=True)
    catalog = []
    if variant == "skill":
        for relative in ALLOWLIST:
            destination = output / "skills/property-research" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SKILL / relative, destination)
        catalog.append(
            {**metadata(SKILL / "SKILL.md"), "path": "skills/property-research/SKILL.md"}
        )
    for name, description in DISTRACTORS.items():
        path = output / "skills" / name / "SKILL.md"
        path.parent.mkdir(parents=True)
        path.write_text(
            f"---\nname: {name}\ndescription: {description}\n---\n\nUse only for the described task.\n"
        )
        catalog.append(
            {"name": name, "description": description, "path": str(path.relative_to(output))}
        )
    data = output / "data"
    data.mkdir()
    fixture = read_json(SKILL / "references/result-example.json")
    if case["fixture"] == "checkpoint":
        fixture["budget"]["attempted_requests"] = 0  # Deliberately inconsistent ledger.
    (data / "evidence.json").write_text(json.dumps(fixture, indent=2) + "\n")
    # Baselines receive the same public contract/helper, but no skill instructions.
    # This isolates instruction discovery from unavailable task dependencies.
    if case["fixture"] in {"handoff", "checkpoint"}:
        support = output / "support"
        support.mkdir()
        for relative in ("references/result.schema.json", "scripts/workflow.py"):
            shutil.copyfile(SKILL / relative, support / Path(relative).name)
    packet = {
        "task": case["query"],
        "available_skills": catalog,
        "constraints": "Offline trial. Use only files within this workspace. No MCP, network, credentials, or external writes. Read skill bodies only when relevant. Return your answer and describe any validation performed.",
        "inputs": ["data/evidence.json"],
    }
    if case["fixture"] in {"handoff", "checkpoint"}:
        packet["task_dependencies"] = ["support/result.schema.json", "support/workflow.py"]
    (output / "prompt.json").write_text(json.dumps(packet, indent=2) + "\n")
    hashes = {
        str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(output.rglob("*"))
        if p.is_file()
    }
    return {"case_id": case_id, "variant": variant, "files": hashes}


def record(manifest: dict[str, Any], trace: Path, model: str, cli_version: str) -> dict[str, Any]:
    """Preserve raw stream-json and extract observed tool calls without grading."""
    if not model.strip() or model in {"haiku", "sonnet", "opus"} or not cli_version.strip():
        raise ValueError("An explicit model ID and CLI version are required")
    raw = trace.read_text()
    events = [json.loads(line) for line in raw.splitlines() if line.strip()]
    calls = []
    observed_models = set()
    for event in events:
        message = event.get("message", {})
        if message.get("model"):
            observed_models.add(message["model"])
        for block in message.get("content", []):
            if isinstance(block, dict) and block.get("type") == "tool_use":
                calls.append({"name": block["name"], "input": block.get("input", {})})
    return {
        **manifest,
        "requested_model": model,
        "observed_models": sorted(observed_models),
        "cli_version": cli_version,
        "tool_calls": calls,
        "read_paths": [c["input"].get("file_path") for c in calls if c["name"] == "Read"],
        "trace_sha256": hashlib.sha256(raw.encode()).hexdigest(),
        "trace": events,
        "grading_status": "not_graded",
        "read_paths_semantics": "requested reads; verify successful tool_result evidence separately",
    }


def compare(skill: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    if (skill["variant"], baseline["variant"]) != ("skill", "baseline"):
        raise ValueError("Expected skill and baseline records")
    for key in ("case_id", "requested_model", "cli_version"):
        if skill[key] != baseline[key]:
            raise ValueError(f"Comparison requires matching {key}")
    skill_models = set(skill.get("observed_models", []))
    baseline_models = set(baseline.get("observed_models", []))
    if skill_models and baseline_models and skill_models != baseline_models:
        raise ValueError("Comparison requires matching observed_models")

    def shared_inputs(record: dict[str, Any]) -> dict[str, str]:
        return {
            key: value
            for key, value in record.get("files", {}).items()
            if key.startswith("data/") or key.startswith("support/")
        }

    skill_inputs, baseline_inputs = shared_inputs(skill), shared_inputs(baseline)
    if skill_inputs != baseline_inputs:
        raise ValueError("Comparison requires matching shared input hashes")
    comparable = bool(skill_models and baseline_models and skill_inputs)
    return {
        "comparison_status": "comparable" if comparable else "incomplete",
        "read_paths_semantics": "requested reads; verify successful tool_result evidence separately",
        "case_id": skill["case_id"],
        "model": skill["requested_model"],
        "skill_reads": skill["read_paths"],
        "baseline_reads": baseline["read_paths"],
        "skill_tool_calls": len(skill["tool_calls"]),
        "baseline_tool_calls": len(baseline["tool_calls"]),
        "verdict": "not_graded",
        "note": "Apply discovery-rubric.json independently; counts do not imply quality.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    staging = commands.add_parser("stage")
    staging.add_argument("--case", required=True)
    staging.add_argument("--variant", choices=("skill", "baseline"), required=True)
    staging.add_argument("--output", type=Path, required=True)
    recording = commands.add_parser("record")
    recording.add_argument("--manifest", type=Path, required=True)
    recording.add_argument("--trace", type=Path, required=True)
    recording.add_argument("--model", required=True)
    recording.add_argument("--cli-version", required=True)
    comparison = commands.add_parser("compare")
    comparison.add_argument("--skill", type=Path, required=True)
    comparison.add_argument("--baseline", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "stage":
            result = stage(args.case, args.variant, args.output)
        elif args.command == "record":
            result = record(read_json(args.manifest), args.trace, args.model, args.cli_version)
        else:
            result = compare(read_json(args.skill), read_json(args.baseline))
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(2, f"Discovery evaluation failed: {exc}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
