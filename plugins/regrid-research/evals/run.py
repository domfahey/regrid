"""Validate synthetic eval fixtures or prepare a blinded, offline agent packet."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def validate_handoff(document: dict) -> None:
    path = ROOT.parent / "skills/property-research/scripts/workflow.py"
    spec = importlib.util.spec_from_file_location("regrid_eval_workflow", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.validate(document)


def load_cases(suite: str = "research") -> list[dict]:
    if suite == "all":
        cases = load_cases("research") + load_cases("composition")
        assert len({case["id"] for case in cases}) == len(cases)
        return cases
    prefix = "composition-" if suite == "composition" else ""
    data = json.loads((ROOT / f"{prefix}cases.json").read_text())
    rubric = json.loads((ROOT / f"{prefix}rubric.json").read_text())
    assert data["schema_version"] == rubric["schema_version"] == 1
    assert data["synthetic"] is True
    cases = data["cases"]
    ids = [case["id"] for case in cases]
    assert len(ids) == len(set(ids))
    assert set(ids) == set(rubric["criteria"])
    for case in cases:
        assert case["user_request"] and case["context"]
        assert rubric["criteria"][case["id"]]
        names = {tool["name"] for tool in case["available_tools"]}
        assert names or case.get("supplied_evidence")
        if suite == "composition":
            validate_handoff(case["supplied_evidence"])
        for event in case["tool_history"]:
            assert event["tool"] in names
            assert isinstance(event["arguments"], dict)
            assert isinstance(event["result"]["isError"], bool)
            assert event["result"]["content"]
            if not event["result"]["isError"]:
                result = json.loads(event["result"]["content"][0]["text"])
                assert result["parcels"]["type"] == "FeatureCollection"
                assert isinstance(result["parcels"]["features"], list)
    return cases


def packet(cases: list[dict], include_skill: bool) -> dict:
    instructions = (
        "Offline behavioral evaluation. Do not call live tools, read .env, or use the network. "
        "The only simulated callable tool is the supplied test double; its name is not a "
        "production MCP name. Treat tool_history as results already retrieved in the current "
        "task. For each case, decide the next action and answer the user using only the "
        "evidence supplied. If more retrieval is needed, propose the exact tool call but "
        "do not fabricate its result. Return JSON with a results array; each item has id, "
        "match_status (confirmed, ambiguous, unmatched, or not_assessed), proposed_tool_calls "
        "(array of {tool, arguments}), continuation_plan (string), and answer (string). "
        "For composition cases, also return handoff (a result-contract object, or null when "
        "not requested), presentation (the requested output, as a string or structured "
        "object), and proposed_writes (array; do not actually write CRM records, "
        "checkpoints, spreadsheets, or other external artifacts). A proposed call has "
        "not happened: do not count it as completed or invent a result. "
        "Do not read any rubric files or prior evaluation reports."
    )
    result = {"instructions": instructions, "cases": cases}
    if include_skill:
        skill = ROOT.parent / "skills/property-research"
        result["skill"] = (skill / "SKILL.md").read_text()
        result["references"] = {
            path.name: path.read_text()
            for path in sorted((skill / "references").iterdir())
            if path.suffix in {".md", ".json"}
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["validate", "packet"])
    parser.add_argument("--case", action="append", dest="selected")
    parser.add_argument("--without-skill", action="store_true")
    parser.add_argument("--suite", choices=["research", "composition", "all"], default="research")
    args = parser.parse_args()
    cases = load_cases(args.suite)
    if args.selected:
        unknown = set(args.selected) - {case["id"] for case in cases}
        if unknown:
            parser.error(f"Unknown case IDs: {', '.join(sorted(unknown))}")
        cases = [case for case in cases if case["id"] in args.selected]
    if args.mode == "validate":
        print(
            f"Validated {len(cases)} synthetic fixtures and matching rubrics (not model behavior)"
        )
    else:
        print(json.dumps(packet(cases, not args.without_skill), indent=2))


if __name__ == "__main__":
    main()
