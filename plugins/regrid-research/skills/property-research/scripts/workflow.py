"""Offline, immutable handoff and checkpoint helpers. Never calls APIs or reads credentials."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

Document = dict[str, Any]


class ValidationError(ValueError):
    """A diagnostic containing only fixed invariants and structural field paths."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def _integer(value: Any) -> bool:
    return type(value) is int and value >= 0


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _keys(value: Any, expected: set[str], message: str) -> None:
    _require(isinstance(value, dict) and set(value) == expected, message)


def validate(document: Document) -> None:
    """Check identity, evidence, status, and ledger invariants without changing data."""
    path = "$"

    def require(condition: bool, message: str, field: str = "") -> None:
        _require(condition, f"{path}{'.' + field if field else ''}: {message}")

    def keys(value: Any, expected: set[str], message: str) -> None:
        require(isinstance(value, dict) and set(value) == expected, message)

    keys(
        document,
        {"schema_version", "workflow_id", "results", "budget", "attempts"},
        "Invalid handoff fields",
    )
    try:
        json.dumps(document, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValidationError("$: Handoff must contain finite JSON values") from exc
    require(document.get("schema_version") == "1.0", "Unsupported schema version", "schema_version")
    require(_text(document.get("workflow_id")), "Missing workflow ID", "workflow_id")
    rows = document.get("results")
    require(isinstance(rows, list), "Invalid results", "results")
    ids: set[str] = set()
    observations: dict[tuple[str, str, str | None, str | None], Document] = {}
    for row_index, row in enumerate(rows):
        path = f"$.results[{row_index}]"
        keys(
            row,
            {
                "input_id",
                "requested",
                "lookup_status",
                "match_status",
                "candidates",
                "missing_fields",
                "error",
                "notes",
            },
            "Invalid result fields",
        )
        key = row.get("input_id")
        require(_text(key) and key not in ids, "Invalid or duplicate input ID", "input_id")
        ids.add(key)
        request = row.get("requested")
        require(isinstance(request, dict), "Invalid requested identity")
        require(set(request) == {"address", "parcel_id", "scope"}, "Invalid requested fields")
        require(all(v is None or _text(v) for v in request.values()), "Invalid requested value")
        require(bool(request["address"] or request["parcel_id"]), "Missing requested identity")
        lookup, match = row.get("lookup_status"), row.get("match_status")
        require(
            isinstance(lookup, str) and lookup in {"success", "error", "not_attempted"},
            "Invalid lookup status; expected success, error, or not_attempted",
            "lookup_status",
        )
        require(
            isinstance(match, str)
            and match in {"confirmed", "ambiguous", "unmatched", "not_assessed"},
            "Invalid match status; expected confirmed, ambiguous, unmatched, or not_assessed",
            "match_status",
        )
        require((lookup == "success") == (match != "not_assessed"), "Inconsistent status pair")
        candidates = row.get("candidates")
        require(isinstance(candidates, list), "Invalid candidates")
        if lookup == "not_attempted":
            require(not candidates, "Not-attempted status cannot contain candidate evidence")
        if match in {"confirmed", "ambiguous"}:
            require(bool(candidates), "Match requires candidate evidence")
        for candidate_index, candidate in enumerate(candidates):
            path = f"$.results[{row_index}].candidates[{candidate_index}]"
            keys(
                candidate,
                {"parcel_id", "address", "facts", "provenance"},
                "Invalid candidate fields",
            )
            for field in ("parcel_id", "address"):
                require(
                    field in candidate and (candidate[field] is None or _text(candidate[field])),
                    "Invalid candidate identity",
                )
            require(isinstance(candidate.get("facts"), dict), "Invalid candidate facts")
            provenance = candidate.get("provenance")
            keys(
                provenance,
                {"provider", "retrieved_at", "source_refreshed_at", "source_url", "evidence_id"},
                "Invalid evidence provenance fields",
            )
            for field in ("provider", "evidence_id"):
                require(_text(provenance.get(field)), "Missing evidence provenance")
            for field in ("retrieved_at", "source_refreshed_at", "source_url"):
                require(
                    field in provenance and (provenance[field] is None or _text(provenance[field])),
                    "Invalid evidence provenance",
                )
            observation_key = (
                provenance["provider"],
                provenance["evidence_id"],
                candidate["parcel_id"],
                candidate["address"],
            )
            previous = observations.get(observation_key)
            require(
                previous is None or previous == candidate,
                "Conflicting snapshots share one source observation",
            )
            observations[observation_key] = candidate
        path = f"$.results[{row_index}]"
        for field in ("missing_fields", "notes"):
            require(
                isinstance(row.get(field), list) and all(_text(x) for x in row[field]),
                "Invalid result annotations",
            )
        require(
            len(set(row["missing_fields"])) == len(row["missing_fields"]),
            "Duplicate missing fields",
        )
        error = row.get("error")
        if lookup == "error":
            keys(error, {"category", "message", "outcome_uncertain"}, "Invalid error fields")
            require(
                isinstance(error, dict)
                and _text(error.get("category"))
                and _text(error.get("message"))
                and type(error.get("outcome_uncertain")) is bool,
                "Missing error details",
            )
        else:
            require(error is None, "Error details conflict with lookup status")
    path = "$.budget"
    budget = document.get("budget")
    fields = {
        "max_requests",
        "max_records",
        "attempted_requests",
        "returned_records",
        "uncertain_records",
    }
    require(isinstance(budget, dict) and set(budget) == fields, "Invalid budget")
    require(all(_integer(v) for v in budget.values()), "Invalid budget counters")
    path = "$.attempts"
    attempts = document.get("attempts")
    require(isinstance(attempts, list), "Invalid attempt ledger")
    attempt_ids: set[str] = set()
    consumed = uncertain = 0
    for attempt_index, attempt in enumerate(attempts):
        path = f"$.attempts[{attempt_index}]"
        keys(
            attempt,
            {"attempt_id", "input_ids", "state", "record_limit", "returned_records"},
            "Invalid attempt ledger entry",
        )
        key = attempt.get("attempt_id")
        require(_text(key) and key not in attempt_ids, "Invalid attempt ID", "attempt_id")
        attempt_ids.add(key)
        inputs = attempt.get("input_ids")
        require(
            isinstance(inputs, list) and bool(inputs) and all(_text(x) for x in inputs),
            "Invalid attempt input IDs",
        )
        require(len(set(inputs)) == len(inputs) and set(inputs) <= ids, "Unknown attempt input IDs")
        state = attempt.get("state")
        require(
            isinstance(state, str) and state in {"pending", "success", "error", "uncertain"},
            "Invalid attempt state; expected pending, success, error, or uncertain",
            "state",
        )
        limit, returned = attempt.get("record_limit"), attempt.get("returned_records")
        require(_integer(limit), "Invalid record reservation")
        if state in {"pending", "uncertain"}:
            require(returned is None, "Uncertain result cannot claim known consumption")
            uncertain += limit
        else:
            require(_integer(returned), "Settled result requires known consumption")
            consumed += returned
    path = "$.budget"
    for field, expected in (
        ("attempted_requests", len(attempts)),
        ("returned_records", consumed),
        ("uncertain_records", uncertain),
    ):
        require(budget[field] == expected, "Budget does not match attempt ledger", field)


def new_workflow(
    workflow_id: str,
    requests: list[Document],
    max_requests: int,
    max_records: int,
    *,
    input_ids: list[str] | None = None,
) -> Document:
    """Keep caller IDs, or assign positional IDs once and retain them on every handoff."""
    if input_ids is not None:
        _require(len(input_ids) == len(requests), "Input ID count does not match requests")
    document = {
        "schema_version": "1.0",
        "workflow_id": workflow_id,
        "results": [],
        "budget": {
            "max_requests": max_requests,
            "max_records": max_records,
            "attempted_requests": 0,
            "returned_records": 0,
            "uncertain_records": 0,
        },
        "attempts": [],
    }
    for index, requested in enumerate(requests, 1):
        document["results"].append(
            {
                "input_id": input_ids[index - 1] if input_ids is not None else f"input-{index:06}",
                "requested": deepcopy(requested),
                "lookup_status": "not_attempted",
                "match_status": "not_assessed",
                "candidates": [],
                "missing_fields": [],
                "error": None,
                "notes": [],
            }
        )
    validate(document)
    return document


def pending_input_ids(document: Document) -> list[str]:
    """Return only untouched inputs; pending/uncertain/error attempts never auto-retry."""
    validate(document)
    attempted = {key for attempt in document["attempts"] for key in attempt["input_ids"]}
    return [
        row["input_id"]
        for row in document["results"]
        if row["lookup_status"] == "not_attempted" and row["input_id"] not in attempted
    ]


def tighten_budget(document: Document, *, max_requests: int, max_records: int) -> Document:
    """Honor a narrower caller budget without refunding historical consumption."""
    validate(document)
    _require(_integer(max_requests) and _integer(max_records), "Invalid budget limits")
    _require(
        max_requests <= document["budget"]["max_requests"]
        and max_records <= document["budget"]["max_records"],
        "Cannot increase caller budget",
    )
    result = deepcopy(document)
    result["budget"].update(max_requests=max_requests, max_records=max_records)
    validate(result)
    return result


def reserve_attempt(
    document: Document, input_ids: list[str], record_limit: int, *, authorized_retry: bool = False
) -> Document:
    """Reserve before dispatch. Persist this copy before a call when checkpoints are requested."""
    validate(document)
    _require(_integer(record_limit), "Invalid record limit")
    _require(bool(input_ids) and len(set(input_ids)) == len(input_ids), "Invalid input IDs")
    allowed = (
        {row["input_id"] for row in document["results"]}
        if authorized_retry
        else set(pending_input_ids(document))
    )
    _require(set(input_ids) <= allowed, "Input unknown, already attempted or resolved")
    budget = document["budget"]
    _require(budget["attempted_requests"] < budget["max_requests"], "Request budget exhausted")
    _require(
        budget["returned_records"] + budget["uncertain_records"] + record_limit
        <= budget["max_records"],
        "Record budget exhausted",
    )
    result = deepcopy(document)
    existing_ids = {attempt["attempt_id"] for attempt in result["attempts"]}
    serial = len(result["attempts"]) + 1
    while f"attempt-{serial:06}" in existing_ids:
        serial += 1
    result["attempts"].append(
        {
            "attempt_id": f"attempt-{serial:06}",
            "input_ids": list(input_ids),
            "state": "pending",
            "record_limit": record_limit,
            "returned_records": None,
        }
    )
    result["budget"]["attempted_requests"] += 1
    result["budget"]["uncertain_records"] += record_limit
    validate(result)
    return result


def complete_attempt(
    document: Document, attempt_id: str, state: str, returned_records: int | None = None
) -> Document:
    """Settle known counts, or retain the reservation for an uncertain outcome."""
    validate(document)
    _require(state in {"success", "error", "uncertain"}, "Invalid completion state")
    result = deepcopy(document)
    attempt = next((a for a in result["attempts"] if a["attempt_id"] == attempt_id), None)
    _require(attempt is not None and attempt["state"] == "pending", "Attempt is not pending")
    attempt["state"] = state
    attempt["returned_records"] = returned_records
    if state != "uncertain":
        _require(_integer(returned_records), "Known returned record count required")
        result["budget"]["uncertain_records"] -= attempt["record_limit"]
        result["budget"]["returned_records"] += returned_records
    validate(result)
    return result


def set_result(document: Document, row: Document) -> Document:
    """Attach supplied/retrieved evidence without creating or refunding an API attempt."""
    validate(document)
    result = deepcopy(document)
    for index, current in enumerate(result["results"]):
        if current["input_id"] == row.get("input_id"):
            _require(
                current["requested"] == row.get("requested"), "Cannot change requested identity"
            )
            _require(
                isinstance(row.get("candidates"), list)
                and all(old in row["candidates"] for old in current["candidates"]),
                "Cannot discard existing candidate evidence",
            )
            result["results"][index] = deepcopy(row)
            validate(result)
            return result
    raise ValueError("Unknown input ID")


def reuse_result(document: Document, source_id: str, target_id: str) -> Document:
    """Reuse success evidence only for identical requested identities; preserve output rows."""
    validate(document)
    rows = {row["input_id"]: row for row in document["results"]}
    _require(source_id in rows and target_id in rows, "Unknown input ID")
    source, target = rows[source_id], rows[target_id]
    _require(source["lookup_status"] == "success", "Only successful evidence can be reused")
    _require(
        source["requested"] == target["requested"], "Cannot reuse different requested identity"
    )
    _require(target_id in pending_input_ids(document), "Target already attempted or resolved")
    copied = deepcopy(source)
    copied["input_id"] = target_id
    return set_result(document, copied)


def save_checkpoint(
    document: Document, path: Path, *, requested: bool = False, replace: bool = False
) -> None:
    """Write atomically only on explicit request; no implicit overwrite or directory creation."""
    _require(requested, "Checkpoint must be explicitly requested")
    validate(document)
    data = json.dumps(document, indent=2, allow_nan=False) + "\n"
    path = Path(path)
    _require(not path.is_symlink(), "Checkpoint destination cannot be a symlink")
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=".regrid-checkpoint-", delete=False
        ) as stream:
            temporary = stream.name
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temporary, path)
        else:
            os.link(temporary, path)
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)


def load_checkpoint(path: Path) -> Document:
    """Load a caller-selected checkpoint; never reset its ledger or issue requests."""
    with Path(path).open(encoding="utf-8") as stream:
        document = json.load(stream)
    validate(document)
    return document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("validate", "pending", "save"):
        subparser = commands.add_parser(command)
        subparser.add_argument("checkpoint", type=Path, help="Input contract JSON")
        if command == "save":
            subparser.add_argument("destination", type=Path, help="Explicit checkpoint destination")
            subparser.add_argument(
                "--replace", action="store_true", help="Replace an existing file"
            )
    args = parser.parse_args()
    try:
        document = load_checkpoint(args.checkpoint)
    except json.JSONDecodeError as exc:
        print(f"Malformed JSON at line {exc.lineno}, column {exc.colno}; repair JSON syntax")
        return 1
    except UnicodeError:
        print("Malformed JSON encoding; save input as UTF-8")
        return 1
    except OSError:
        print("Cannot read input; check that the file exists and is readable")
        return 1
    except ValidationError as exc:
        print(f"Invalid handoff/checkpoint: {exc}")
        return 1
    except (ValueError, TypeError, KeyError, RecursionError):
        print("Invalid handoff/checkpoint at $; check JSON types and nesting")
        return 1
    if args.command == "save":
        try:
            save_checkpoint(document, args.destination, requested=True, replace=args.replace)
        except FileExistsError:
            print(
                "Checkpoint already exists; choose another destination or explicitly use --replace"
            )
            return 1
        except ValidationError as exc:
            print(f"Cannot save checkpoint: {exc}")
            return 1
        except OSError:
            print("Cannot write checkpoint; check the destination parent exists and is writable")
            return 1
        print("Saved checkpoint")
    else:
        print(
            json.dumps(pending_input_ids(document))
            if args.command == "pending"
            else "Valid handoff/checkpoint"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
