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


def _check(condition: bool, message: str = "") -> None:
    if not condition:
        raise AssertionError(message)


@functools.lru_cache(maxsize=1)
def _workflow_module():
    path = Path(__file__).resolve().parents[1] / "skills/property-research/scripts/workflow.py"
    spec = importlib.util.spec_from_file_location("regrid_eval_workflow", path)
    _check(bool(spec and spec.loader), f"Unable to load workflow module from {path}")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_handoff(document: dict) -> None:
    _workflow_module().validate(document)


_CLI_ROUTE_PREFIXES = ("/", "http://", "https://", "%2f", "?")
_CLI_ROUTE_FLAGS = {"--path", "--url", "--endpoint", "parcel-path"}
_CLI_PATH_KEYS = {"path", "url", "endpoint"}
_CLI_JSON_FLAGS = {"--options", "--fields", "--geojson"}
_CLI_JSON_KEYS = {"options", "fields", "geojson"}


def _split_command(value: str) -> list[str]:
    try:
        return shlex.split(value)
    except ValueError:
        return value.split()


def _has_canadian_segment(path: str) -> bool:
    decoded = unquote(path).strip().lower()
    parts = [p for p in decoded.split("/") if p]
    if decoded.startswith("/") and parts == ["ca"]:
        return True
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
            param = unquote(key).strip().lower().lstrip("-")
            if param == "country" and unquote(value).strip().lower() == "ca":
                return True
            if param != "path":
                continue
        if _has_canadian_segment(value if sep else chunk):
            return True
    return False


def _json_has_canadian_value(raw: str) -> bool:
    try:
        decoded = json.loads(raw)
    except ValueError:
        return False
    return _has_canadian_value(decoded)


def _command_is_canadian(tokens: list[str]) -> bool:
    for i, token in enumerate(tokens):
        low = token.strip().lower()
        nxt = tokens[i + 1] if i + 1 < len(tokens) else None
        if low == "--country" and nxt is not None and nxt.strip().lower() == "ca":
            return True
        if low.startswith("--country=") and low.split("=", 1)[1].strip() == "ca":
            return True
        if low == "schema":
            j = i + 1
            while j < len(tokens):
                arg = tokens[j].strip().lower()
                if arg == "--":
                    j += 1
                    continue
                if arg.startswith("-"):
                    j += 1 if "=" in arg else 2
                    continue
                if arg == "ca":
                    return True
                break
        if low == "-c" and nxt is not None and _command_is_canadian(_split_command(nxt)):
            return True
        if low in _CLI_ROUTE_FLAGS and nxt is not None and _has_canadian_path_text(nxt):
            return True
        if low in _CLI_JSON_FLAGS and nxt is not None and _json_has_canadian_value(nxt):
            return True
        if "=" in token:
            key, _, val = token.partition("=")
            norm_key = key.strip().lower().lstrip("-")
            if norm_key in _CLI_PATH_KEYS and _has_canadian_path_text(val):
                return True
            if norm_key in _CLI_JSON_KEYS and _json_has_canadian_value(val):
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
                    elif _has_canadian_value(qval, qname):
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
        _check(len({case["id"] for case in cases}) == len(cases), "Duplicate case ID across suites")
        load_composability_cases()
        load_discovery_rubric()
        return cases
    prefix = {"composition": "composition-", "feature": "feature-"}.get(suite, "")
    data = json.loads((ROOT / f"{prefix}cases.json").read_text(encoding="utf-8"))
    rubric = json.loads((ROOT / f"{prefix}rubric.json").read_text(encoding="utf-8"))
    _check(data["schema_version"] == rubric["schema_version"] == 1, "Invalid schema_version")
    _check(data["synthetic"] is True, "Fixture must be synthetic")
    cases = data["cases"]
    ids = [case["id"] for case in cases]
    _check(len(ids) == len(set(ids)), "Duplicate case IDs")
    _check(set(ids) == set(rubric["criteria"]), "Case IDs must match rubric criteria")
    for case in cases:
        _check(bool(case["user_request"] and case["context"]), "Missing user_request or context")
        _check(bool(rubric["criteria"][case["id"]]), "Empty rubric criteria")
        names = {tool["name"] for tool in case["available_tools"]}
        _check(bool(names or case.get("supplied_evidence")), "Missing tools or supplied_evidence")
        if suite == "composition":
            validate_handoff(case["supplied_evidence"])
        if suite == "feature":
            _check(case["us_only"] is True, "Feature case must set us_only=true")
            _check(bool(names), "Feature case must define available_tools")
        for event in case["tool_history"]:
            _check(event["tool"] in names, "Tool history event must reference available tool")
            _check(isinstance(event["arguments"], dict), "Tool arguments must be an object")
            _check(isinstance(event["result"]["isError"], bool), "isError must be boolean")
            _check(bool(event["result"]["content"]), "Result content must be non-empty")
            _check(not _is_canadian_route(event["arguments"]), "Canadian routes are forbidden")
            if not event["result"]["isError"]:
                result = json.loads(event["result"]["content"][0]["text"])
                if isinstance(result, dict) and "parcels" in result:
                    _check(
                        result["parcels"]["type"] == "FeatureCollection",
                        "Parcels must be a FeatureCollection",
                    )
                    _check(
                        isinstance(result["parcels"]["features"], list),
                        "Parcels features must be a list",
                    )
    if suite == "feature":
        load_trigger_cases()
    return cases


def load_composability_cases() -> list[dict]:
    data = json.loads((ROOT / "composability-regressions.json").read_text(encoding="utf-8"))
    rubric = json.loads((ROOT / "composability-rubric.json").read_text(encoding="utf-8"))
    _check(data["schema_version"] == rubric["schema_version"] == 1, "Invalid schema_version")
    _check(data["synthetic"] is True, "Fixture must be synthetic")
    cases = data["cases"]
    ids = [case["id"] for case in cases]
    _check(len(ids) == len(set(ids)), "Duplicate case IDs")
    _check(set(ids) == set(rubric["criteria"]), "Case IDs must match rubric criteria")
    for case in cases:
        _check(bool(case["user_request"] and case["context"]), "Missing user_request or context")
        criteria = rubric["criteria"][case["id"]]
        _check(
            isinstance(criteria, list)
            and bool(criteria)
            and all(isinstance(item, str) and bool(item.strip()) for item in criteria),
            "Invalid rubric criteria list",
        )
        names = {tool["name"] for tool in case["available_tools"]}
        _check(bool(names or case.get("supplied_evidence")), "Missing tools or supplied_evidence")
        for event in case["tool_history"]:
            _check(event["tool"] in names, "Tool history event must reference available tool")
            _check(isinstance(event["arguments"], dict), "Tool arguments must be an object")
            _check(isinstance(event["result"]["isError"], bool), "isError must be boolean")
            if "content" in event["result"]:
                _check(bool(event["result"]["content"]), "Result content must be non-empty")
            else:
                _check(
                    isinstance(event["result"].get("message"), str),
                    "Result message must be a string",
                )
                _check(bool(event["result"]["message"].strip()), "Result message must be non-empty")
            _check(not _is_canadian_route(event["arguments"]), "Canadian routes are forbidden")
    return cases


def load_discovery_rubric() -> dict:
    cases = json.loads((ROOT / "discovery-cases.json").read_text(encoding="utf-8"))
    rubric = json.loads((ROOT / "discovery-rubric.json").read_text(encoding="utf-8"))
    _check(
        isinstance(rubric.get("grading"), str) and bool(rubric["grading"].strip()),
        "Discovery rubric grading must be a non-empty string",
    )
    _check(
        isinstance(rubric.get("critical_failures"), list) and bool(rubric["critical_failures"]),
        "Discovery rubric critical_failures must be non-empty",
    )
    for case in cases:
        criteria = rubric.get(case["id"])
        _check(
            isinstance(criteria, list)
            and bool(criteria)
            and all(isinstance(item, str) and bool(item.strip()) for item in criteria),
            f"Invalid discovery criteria for {case['id']}",
        )
    return rubric


TRIGGER_LABELS = {"property-research", "setup", "none"}


def load_trigger_cases() -> list[dict]:
    data = json.loads((ROOT / "trigger-cases.json").read_text(encoding="utf-8"))
    _check(data["schema_version"] == 1, "Invalid schema_version")
    _check(data["synthetic"] is True, "Fixture must be synthetic")
    cases = data["cases"]
    for key in ("id", "prompt"):
        values = [case[key] for case in cases]
        _check(all(values) and len(values) == len(set(values)), f"Invalid or duplicate {key}")
    _check(
        all(case["expected_skill"] in TRIGGER_LABELS for case in cases),
        "Unknown expected_skill label",
    )
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
