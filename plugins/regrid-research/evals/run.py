"""Validate synthetic eval fixtures or prepare a blinded, offline agent packet."""

from __future__ import annotations

import argparse
import functools
import importlib.util
import json
import re
import shlex
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent


@functools.lru_cache(maxsize=1)
def _workflow_module():
    path = Path(__file__).resolve().parents[1] / "skills/property-research/scripts/workflow.py"
    spec = importlib.util.spec_from_file_location("regrid_eval_workflow", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_handoff(document: dict) -> None:
    _workflow_module().validate(document)


_CLI_ROUTE_PREFIXES = ("/", "http://", "https://", "%2f", "?")
_CLI_ROUTE_FLAGS = {"--path", "--url", "--endpoint", "parcel-path"}
_CLI_PATH_KEYS = {"path", "url", "endpoint"}


def _split_command(value: str) -> list[str]:
    try:
        return shlex.split(value)
    except ValueError:
        return value.split()


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


def _has_canadian_path_text(text: str) -> bool:
    for chunk in re.split(r"[?&#]", text):
        key, sep, value = chunk.partition("=")
        if sep:
            param = key.strip().lower().lstrip("-")
            if param == "country" and value.strip().lower() == "ca":
                return True
            if param != "path":
                continue
        if _has_canadian_segment(value if sep else chunk):
            return True
    return False


def _command_is_canadian(tokens: list[str]) -> bool:
    for i, token in enumerate(tokens):
        low = token.strip().lower()
        nxt = tokens[i + 1] if i + 1 < len(tokens) else None
        if low == "--country" and nxt is not None and nxt.strip().lower() == "ca":
            return True
        if low.startswith("--country=") and low.split("=", 1)[1].strip() == "ca":
            return True
        if low == "schema" and nxt is not None and nxt.strip().lower() == "ca":
            return True
        if low in _CLI_ROUTE_FLAGS and nxt is not None and _has_canadian_path_text(nxt):
            return True
        if "=" in token:
            key, _, val = token.partition("=")
            if key.strip().lower().lstrip("-") in _CLI_PATH_KEYS and _has_canadian_path_text(val):
                return True
        if not any(ch.isspace() for ch in token) and low.startswith(_CLI_ROUTE_PREFIXES):
            if _has_canadian_path_text(token):
                return True
    return False


def _has_canadian_value(value: object, key: str = "") -> bool:
    name = key.lower()
    if isinstance(value, str):
        if name in _CLI_PATH_KEYS:
            return _has_canadian_path_text(value)
        if name == "country":
            return value.strip().lower() == "ca"
        if name in {"command", "args"}:
            return _command_is_canadian(_split_command(value))
        return False
    if isinstance(value, dict):
        return any(_has_canadian_value(item, str(k)) for k, item in value.items())
    if isinstance(value, list):
        if name == "args":
            str_tokens = [item for item in value if isinstance(item, str)]
            if str_tokens and _command_is_canadian(str_tokens):
                return True
            return any(_has_canadian_value(item) for item in value if not isinstance(item, str))
        if name == "querystring":
            for item in value:
                if isinstance(item, dict) and "name" in item and "value" in item:
                    qname = str(item["name"]).strip().lower()
                    qval = item["value"]
                    if isinstance(qval, str):
                        if qname in _CLI_PATH_KEYS and _has_canadian_path_text(qval):
                            return True
                        if qname == "country" and qval.strip().lower() == "ca":
                            return True
                elif _has_canadian_value(item, key):
                    return True
            return False
        return any(_has_canadian_value(item, key) for item in value)
    return False


def _is_canadian_route(arguments: dict) -> bool:
    """True when a `ca` path segment or Canadian country/schema selector targets Canada.

    Checks route-bearing fields (url, path, endpoint), country parameters, HAR queryString
    name/value entries, and CLI command/args tokens without treating free-text address queries
    or `/us/ca/` (California) as Canadian routes. `/schemas/ca` is the Canadian schema.
    """
    return _has_canadian_value(arguments)


def load_cases(suite: str = "research") -> list[dict]:
    if suite == "all":
        cases = load_cases("research") + load_cases("composition") + load_cases("feature")
        assert len({case["id"] for case in cases}) == len(cases)
        load_composability_cases()
        load_discovery_rubric()
        return cases
    prefix = {"composition": "composition-", "feature": "feature-"}.get(suite, "")
    data = json.loads((ROOT / f"{prefix}cases.json").read_text(encoding="utf-8"))
    rubric = json.loads((ROOT / f"{prefix}rubric.json").read_text(encoding="utf-8"))
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
            assert not _is_canadian_route(event["arguments"])
            if not event["result"]["isError"]:
                result = json.loads(event["result"]["content"][0]["text"])
                if "parcels" in result:
                    assert result["parcels"]["type"] == "FeatureCollection"
                    assert isinstance(result["parcels"]["features"], list)
    if suite == "feature":
        load_trigger_cases()
    return cases


def load_composability_cases() -> list[dict]:
    data = json.loads((ROOT / "composability-regressions.json").read_text(encoding="utf-8"))
    rubric = json.loads((ROOT / "composability-rubric.json").read_text(encoding="utf-8"))
    assert data["schema_version"] == rubric["schema_version"] == 1
    assert data["synthetic"] is True
    cases = data["cases"]
    ids = [case["id"] for case in cases]
    assert len(ids) == len(set(ids))
    assert set(ids) == set(rubric["criteria"])
    for case in cases:
        assert case["user_request"] and case["context"]
        criteria = rubric["criteria"][case["id"]]
        assert (
            isinstance(criteria, list)
            and criteria
            and all(isinstance(item, str) and item.strip() for item in criteria)
        )
        names = {tool["name"] for tool in case["available_tools"]}
        assert names or case.get("supplied_evidence")
        for event in case["tool_history"]:
            assert event["tool"] in names
            assert isinstance(event["arguments"], dict)
            assert isinstance(event["result"]["isError"], bool)
            if "content" in event["result"]:
                assert event["result"]["content"]
            else:
                assert isinstance(event["result"].get("message"), str)
                assert event["result"]["message"].strip()
            assert not _is_canadian_route(event["arguments"])
    return cases


def load_discovery_rubric() -> dict:
    cases = json.loads((ROOT / "discovery-cases.json").read_text(encoding="utf-8"))
    rubric = json.loads((ROOT / "discovery-rubric.json").read_text(encoding="utf-8"))
    assert isinstance(rubric.get("grading"), str) and rubric["grading"].strip()
    assert isinstance(rubric.get("critical_failures"), list) and rubric["critical_failures"]
    for case in cases:
        criteria = rubric.get(case["id"])
        assert (
            isinstance(criteria, list)
            and criteria
            and all(isinstance(item, str) and item.strip() for item in criteria)
        )
    return rubric


TRIGGER_LABELS = {"property-research", "setup", "none"}


def load_trigger_cases() -> list[dict]:
    data = json.loads((ROOT / "trigger-cases.json").read_text(encoding="utf-8"))
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
        "Only tools listed in each case's available_tools are callable (such as the regrid test "
        "double, and in the feature suite also shell and read_file when listed); their names are "
        "not production MCP names. Treat tool_history as results already retrieved in the current "
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
        result["skill"] = (skill / "SKILL.md").read_text(encoding="utf-8")
        result["references"] = {
            path.name: (
                FIELDS_NOTE
                if path.name == "fields.json" and not include_fields
                else path.read_text(encoding="utf-8")
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
        include_fields = any(case.get("us_only") for case in cases)
        print(json.dumps(packet(cases, not args.without_skill, include_fields), indent=2))


if __name__ == "__main__":
    main()
