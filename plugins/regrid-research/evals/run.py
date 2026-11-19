"""Validate synthetic eval fixtures or prepare a blinded, offline agent packet."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shlex
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent


def validate_handoff(document: dict) -> None:
    path = ROOT.parent / "skills/property-research/scripts/workflow.py"
    spec = importlib.util.spec_from_file_location("regrid_eval_workflow", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.validate(document)


def _route_strings(value: object, key: str = ""):
    """Yield route strings: url/path/endpoint values and whitespace tokens of command/args.

    Free text such as query is skipped.
    """
    if isinstance(value, str):
        name = key.lower()
        if name in {"url", "path", "endpoint"}:
            yield value
        elif name in {"command", "args"}:
            try:
                tokens = shlex.split(value)
            except ValueError:
                tokens = value.split()
            for token in tokens:
                yield from token.split()
    elif isinstance(value, dict):
        for name, item in value.items():
            yield from _route_strings(item, str(name))
    elif isinstance(value, list):
        for item in value:
            yield from _route_strings(item, key)


def _has_canadian_segment(path: str) -> bool:
    parts = [p for p in unquote(path).strip().lower().split("/") if p]
    for i, part in enumerate(parts):
        if part != "ca" or (i and parts[i - 1] == "us"):
            continue
        if i + 1 < len(parts):
            if parts[i + 1][:1].strip():
                return True
        elif i and parts[i - 1] == "schemas":
            return True
    return False


def _is_canadian_route(arguments: dict) -> bool:
    """True when a `ca` path segment is followed by more segments and is not /us/ca/ (California).

    Checks only route-bearing fields (url, path, endpoint): their paths and path= parameter values, with
    percent-encoding decoded and empty segments ignored. `/schemas/ca` is the Canadian schema.
    Other query values (state2=ca, fields[state2][eq]=ca) are California filters, and free-text
    fields such as an address query are never routes.
    """
    for text in _route_strings(arguments):
        for chunk in re.split(r"[?&#]", text):
            key, sep, value = chunk.partition("=")
            if sep and key.strip().lower().lstrip("-") != "path":
                continue
            if _has_canadian_segment(value if sep else chunk):
                return True
    return False


def load_cases(suite: str = "research") -> list[dict]:
    if suite == "all":
        cases = load_cases("research") + load_cases("composition") + load_cases("feature")
        assert len({case["id"] for case in cases}) == len(cases)
        return cases
    prefix = {"composition": "composition-", "feature": "feature-"}.get(suite, "")
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
        if suite == "feature":
            assert case["us_only"] is True
            assert names
        for event in case["tool_history"]:
            assert event["tool"] in names
            assert isinstance(event["arguments"], dict)
            assert isinstance(event["result"]["isError"], bool)
            assert event["result"]["content"]
            if suite == "feature":
                assert not _is_canadian_route(event["arguments"])
            if not event["result"]["isError"]:
                result = json.loads(event["result"]["content"][0]["text"])
                assert result["parcels"]["type"] == "FeatureCollection"
                assert isinstance(result["parcels"]["features"], list)
    if suite == "feature":
        load_trigger_cases()
    return cases


TRIGGER_LABELS = {"property-research", "setup", "none"}


def load_trigger_cases() -> list[dict]:
    data = json.loads((ROOT / "trigger-cases.json").read_text())
    assert data["schema_version"] == 1
    assert data["synthetic"] is True
    cases = data["cases"]
    for key in ("id", "prompt"):
        values = [case[key] for case in cases]
        assert all(values) and len(values) == len(set(values))
    assert all(case["expected_skill"] in TRIGGER_LABELS for case in cases)
    return cases


FIELDS_NOTE = "Large data file read only by scripts/fields.py; content omitted from this packet."


def packet(cases: list[dict], include_skill: bool, include_fields: bool = False) -> dict:
    instructions = (
        "Offline behavioral evaluation. Do not call live tools, read .env, or use the network. "
        "Only the supplied test doubles are callable (the regrid test double, and in the feature "
        "suite also shell and read_file); their names are not production MCP names. Treat tool_history as results already retrieved in the current "
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
            path.name: (
                FIELDS_NOTE
                if path.name == "fields.json" and not include_fields
                else path.read_text()
            )
            for path in sorted((skill / "references").iterdir())
            if path.suffix in {".md", ".json"}
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["validate", "packet"])
    parser.add_argument("--case", action="append", dest="selected")
    parser.add_argument("--without-skill", action="store_true")
    parser.add_argument(
        "--suite", choices=["research", "composition", "feature", "all"], default="research"
    )
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
        feature_ids = {case["id"] for case in load_cases("feature")}
        include_fields = any(case["id"] in feature_ids for case in cases)
        print(json.dumps(packet(cases, not args.without_skill, include_fields), indent=2))


if __name__ == "__main__":
    main()
