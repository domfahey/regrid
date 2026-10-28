"""Offline handoffs retain identity, evidence, and one budget across resumed stages."""

import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "plugins/regrid-research/skills/property-research/scripts/workflow.py"
)
SPEC = importlib.util.spec_from_file_location("regrid_workflow", SCRIPT)
assert SPEC and SPEC.loader
workflow = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(workflow)


def request(address="12 Example Ave, Example NJ 08033"):
    return {"address": address, "parcel_id": None, "scope": None}


def state():
    return workflow.new_workflow("test-run", [request(), request("14 Example Ave")], 2, 2)


def success(row):
    result = deepcopy(row)
    result.update(lookup_status="success", match_status="confirmed")
    result["candidates"] = [
        {
            "parcel_id": "TEST-1",
            "address": row["requested"]["address"],
            "facts": {"recorded_owner": "Example LLC"},
            "provenance": {
                "provider": "Regrid",
                "retrieved_at": "2026-10-27T18:00:00Z",
                "source_refreshed_at": None,
                "source_url": None,
                "evidence_id": "e-1",
            },
        }
    ]
    return result


def test_stable_input_ids_and_duplicate_id_rejection():
    first = state()
    assert [r["input_id"] for r in first["results"]] == ["input-000001", "input-000002"]
    assert state() == first
    first["results"][1]["input_id"] = first["results"][0]["input_id"]
    with pytest.raises(ValueError, match="input"):
        workflow.validate(first)


def test_shared_budget_reserves_uncertain_records_and_does_not_mutate_on_failure():
    doc = workflow.reserve_attempt(state(), ["input-000001"], 2)
    assert doc["budget"]["attempted_requests"] == 1
    assert doc["budget"]["uncertain_records"] == 2
    uncertain = workflow.complete_attempt(doc, "attempt-000001", "uncertain")
    before = deepcopy(uncertain)
    with pytest.raises(ValueError, match="budget"):
        workflow.reserve_attempt(uncertain, ["input-000002"], 1)
    assert uncertain == before
    assert workflow.pending_input_ids(uncertain) == ["input-000002"]


def test_resume_skips_success_and_pending_without_resetting_budget(tmp_path):
    doc = workflow.reserve_attempt(state(), ["input-000001"], 1)
    doc = workflow.complete_attempt(doc, "attempt-000001", "success", 1)
    doc = workflow.set_result(doc, success(doc["results"][0]))
    path = tmp_path / "checkpoint.json"
    workflow.save_checkpoint(doc, path, requested=True)
    resumed = workflow.load_checkpoint(path)
    assert resumed == doc
    assert workflow.pending_input_ids(resumed) == ["input-000002"]
    resumed = workflow.reserve_attempt(resumed, ["input-000002"], 1)
    assert resumed["budget"]["attempted_requests"] == 2
    workflow.save_checkpoint(resumed, path, requested=True, replace=True)
    assert workflow.pending_input_ids(workflow.load_checkpoint(path)) == []


def test_supplied_evidence_and_duplicate_input_reuse_need_no_attempt():
    doc = workflow.new_workflow("supplied", [request(), request()], 1, 1)
    doc = workflow.set_result(doc, success(doc["results"][0]))
    doc = workflow.reuse_result(doc, "input-000001", "input-000002")
    assert workflow.pending_input_ids(doc) == []
    assert doc["attempts"] == []
    assert doc["budget"]["attempted_requests"] == 0
    assert doc["results"][1]["candidates"] == doc["results"][0]["candidates"]
    assert doc["results"][1]["input_id"] == "input-000002"


def test_reuse_rejects_different_requested_property():
    doc = workflow.set_result(state(), success(state()["results"][0]))
    with pytest.raises(ValueError, match="requested"):
        workflow.reuse_result(doc, "input-000001", "input-000002")


def test_checkpoint_requires_request_and_never_overwrites_implicitly(tmp_path):
    path = tmp_path / "checkpoint.json"
    with pytest.raises(ValueError, match="requested"):
        workflow.save_checkpoint(state(), path)
    assert not path.exists()
    workflow.save_checkpoint(state(), path, requested=True)
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        workflow.save_checkpoint(state(), path, requested=True)
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


def test_invalid_checkpoint_does_not_replace_existing_file(tmp_path):
    path = tmp_path / "checkpoint.json"
    workflow.save_checkpoint(state(), path, requested=True)
    original = path.read_bytes()
    invalid = state()
    invalid["budget"]["attempted_requests"] = 8
    with pytest.raises(ValueError, match="ledger"):
        workflow.save_checkpoint(invalid, path, requested=True, replace=True)
    assert path.read_bytes() == original
    path.write_text(json.dumps(invalid))
    with pytest.raises(ValueError, match="ledger"):
        workflow.load_checkpoint(path)


def test_error_is_not_unmatched_and_success_requires_evidence():
    doc = state()
    doc["results"][0].update(lookup_status="error", match_status="unmatched")
    with pytest.raises(ValueError, match="status"):
        workflow.validate(doc)
    doc = state()
    doc["results"][0].update(lookup_status="success", match_status="confirmed")
    with pytest.raises(ValueError, match="candidate"):
        workflow.validate(doc)


def test_record_overrun_is_retained_and_blocks_further_requests():
    doc = workflow.reserve_attempt(state(), ["input-000001"], 1)
    doc = workflow.complete_attempt(doc, "attempt-000001", "success", 3)
    assert doc["budget"]["returned_records"] == 3
    with pytest.raises(ValueError, match="budget"):
        workflow.reserve_attempt(doc, ["input-000002"], 1)


def test_request_cannot_be_repeated_or_settled_twice():
    doc = workflow.reserve_attempt(state(), ["input-000001"], 1)
    with pytest.raises(ValueError, match="attempted"):
        workflow.reserve_attempt(doc, ["input-000001"], 1)
    doc = workflow.complete_attempt(doc, "attempt-000001", "error", 0)
    with pytest.raises(ValueError, match="pending"):
        workflow.complete_attempt(doc, "attempt-000001", "success", 1)


def test_caller_ids_survive_reordering_and_budget_tightening_keeps_consumption():
    doc = workflow.new_workflow(
        "caller",
        [request(), request("14 Example Ave")],
        4,
        4,
        input_ids=["sheet-row-12", "sheet-row-8"],
    )
    doc = workflow.reserve_attempt(doc, ["sheet-row-12"], 1)
    doc = workflow.complete_attempt(doc, "attempt-000001", "success", 1)
    doc["results"].reverse()
    assert [r["input_id"] for r in doc["results"]] == ["sheet-row-8", "sheet-row-12"]
    narrowed = workflow.tighten_budget(doc, max_requests=1, max_records=0)
    assert narrowed["budget"]["attempted_requests"] == 1
    assert narrowed["budget"]["returned_records"] == 1
    with pytest.raises(ValueError, match="budget"):
        workflow.reserve_attempt(narrowed, ["sheet-row-8"], 1)
    with pytest.raises(ValueError, match="increase"):
        workflow.tighten_budget(narrowed, max_requests=4, max_records=4)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(extra=True),
        lambda d: d["results"][0].pop("error"),
        lambda d: d["results"][0].update(extra=True),
        lambda d: d["results"][0].update(missing_fields=["owner", "owner"]),
        lambda d: d["results"][0].update(candidates=success(d["results"][0])["candidates"]),
        lambda d: d["budget"].update(max_requests=True),
    ],
)
def test_malformed_handoff_rejected(mutate):
    doc = state()
    mutate(doc)
    with pytest.raises(ValueError):
        workflow.validate(doc)


def test_conflicting_evidence_cannot_be_silently_discarded():
    doc = workflow.set_result(state(), success(state()["results"][0]))
    conflicting = deepcopy(doc["results"][0])
    conflicting["candidates"][0]["facts"]["recorded_owner"] = "Another LLC"
    conflicting["candidates"][0]["provenance"]["evidence_id"] = "e-2"
    with pytest.raises(ValueError, match="evidence"):
        workflow.set_result(doc, conflicting)
    conflicting["candidates"].extend(doc["results"][0]["candidates"])
    retained = workflow.set_result(doc, conflicting)
    assert len(retained["results"][0]["candidates"]) == 2


def test_authorized_retry_preserves_old_attempt_and_respects_shared_budget():
    doc = workflow.reserve_attempt(state(), ["input-000001"], 1)
    doc = workflow.complete_attempt(doc, "attempt-000001", "uncertain")
    retried = workflow.reserve_attempt(doc, ["input-000001"], 1, authorized_retry=True)
    assert len(retried["attempts"]) == 2
    assert retried["attempts"][0]["state"] == "uncertain"
    assert retried["budget"]["uncertain_records"] == 2
    with pytest.raises(ValueError, match="budget"):
        workflow.reserve_attempt(retried, ["input-000001"], 1, authorized_retry=True)


def test_extracted_standalone_helper_validates_and_resumes_checkpoint(tmp_path):
    import subprocess
    import sys
    from zipfile import ZipFile

    build_path = SCRIPT.parents[5] / "scripts/build_claude_plugins.py"
    spec = importlib.util.spec_from_file_location("workflow_test_builder", build_path)
    assert spec and spec.loader
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    archives = builder.build(SCRIPT.parents[3], tmp_path / "archives")
    with ZipFile(archives[-1]) as archive:
        archive.extractall(tmp_path / "extracted")
    helper = tmp_path / "extracted/property-research/scripts/workflow.py"
    checkpoint = tmp_path / "checkpoint.json"
    doc = workflow.reserve_attempt(state(), ["input-000001"], 1)
    workflow.save_checkpoint(doc, checkpoint, requested=True)
    valid = subprocess.run(
        [sys.executable, str(helper), "validate", str(checkpoint)],
        text=True,
        capture_output=True,
        check=True,
    )
    assert valid.stdout.strip() == "Valid handoff/checkpoint"
    resumed = subprocess.run(
        [sys.executable, str(helper), "pending", str(checkpoint)],
        text=True,
        capture_output=True,
        check=True,
    )
    assert json.loads(resumed.stdout) == ["input-000002"]
    destination = tmp_path / "saved-checkpoint.json"
    saved = subprocess.run(
        [sys.executable, str(helper), "save", str(checkpoint), str(destination)],
        text=True,
        capture_output=True,
        check=True,
    )
    assert saved.stdout.strip() == "Saved checkpoint"
    assert json.loads(destination.read_text()) == doc


def test_generated_attempt_id_does_not_collide_with_caller_ledger_ids():
    doc = workflow.reserve_attempt(state(), ["input-000001"], 1)
    doc["attempts"][0]["attempt_id"] = "attempt-000002"
    next_doc = workflow.reserve_attempt(doc, ["input-000002"], 1)
    assert [attempt["attempt_id"] for attempt in next_doc["attempts"]] == [
        "attempt-000002",
        "attempt-000003",
    ]


@pytest.mark.parametrize("across_rows", [False, True])
def test_same_source_observation_cannot_have_conflicting_snapshots(across_rows):
    doc = workflow.new_workflow("evidence", [request(), request()], 1, 1)
    doc = workflow.set_result(doc, success(doc["results"][0]))
    conflicting = deepcopy(doc["results"][0]["candidates"][0])
    conflicting["facts"]["recorded_owner"] = "Conflicting LLC"
    if across_rows:
        row = success(doc["results"][1])
        row["candidates"] = [conflicting]
        with pytest.raises(ValueError, match="observation"):
            workflow.set_result(doc, row)
    else:
        row = deepcopy(doc["results"][0])
        row["candidates"].append(conflicting)
        with pytest.raises(ValueError, match="observation"):
            workflow.set_result(doc, row)


def test_one_response_id_can_cover_distinct_parcels_and_repeat_identical_observation():
    doc = workflow.new_workflow("evidence", [request(), request()], 1, 1)
    row = success(doc["results"][0])
    second = deepcopy(row["candidates"][0])
    second["parcel_id"] = "TEST-2"
    second["facts"]["recorded_owner"] = "Another Parcel LLC"
    row["candidates"].append(second)
    row["match_status"] = "ambiguous"
    doc = workflow.set_result(doc, row)
    doc = workflow.reuse_result(doc, "input-000001", "input-000002")
    workflow.validate(doc)
    assert doc["results"][0]["candidates"] == doc["results"][1]["candidates"]
    assert len(doc["results"][0]["candidates"]) == 2


def run_cli(monkeypatch, capsys, *args):
    monkeypatch.setattr("sys.argv", [str(SCRIPT), *map(str, args)])
    code = workflow.main()
    return code, capsys.readouterr().out


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (lambda d: d["results"][1].update(input_id="input-000001"), "$.results[1].input_id"),
        (
            lambda d: d["results"][0].update(lookup_status=["secret-sentinel"]),
            "$.results[0].lookup_status",
        ),
        (lambda d: d["budget"].update(attempted_requests=1), "$.budget.attempted_requests"),
    ],
)
def test_cli_actionable_redacted_validation(tmp_path, monkeypatch, capsys, mutation, expected):
    doc = state()
    mutation(doc)
    doc["workflow_id"] = "secret-sentinel"
    path = tmp_path / "secret-sentinel.json"
    path.write_text(json.dumps(doc))
    code, output = run_cli(monkeypatch, capsys, "validate", path)
    assert code == 1
    assert expected in output
    assert "secret-sentinel" not in output


def test_cli_distinguishes_json_and_unreadable_input(tmp_path, monkeypatch, capsys):
    path = tmp_path / "secret-sentinel.json"
    path.write_text('{"secret-sentinel":')
    code, output = run_cli(monkeypatch, capsys, "validate", path)
    assert code == 1 and "Malformed JSON" in output and "line 1" in output
    assert "secret-sentinel" not in output
    code, output = run_cli(monkeypatch, capsys, "validate", tmp_path / "secret-missing")
    assert code == 1 and "Cannot read input" in output
    assert "secret-missing" not in output


def test_cli_save_explicit_create_and_replace_offline(tmp_path, monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail("Checkpoint commands must not access the network")

    import socket

    monkeypatch.setattr(socket, "socket", forbidden)
    source, destination = tmp_path / "input.json", tmp_path / "checkpoint.json"
    doc = state()
    source.write_text(json.dumps(doc))
    code, output = run_cli(monkeypatch, capsys, "save", source, destination)
    assert code == 0 and "Saved checkpoint" in output
    assert workflow.load_checkpoint(destination) == doc
    original = destination.read_bytes()
    doc["workflow_id"] = "changed"
    source.write_text(json.dumps(doc))
    code, output = run_cli(monkeypatch, capsys, "save", source, destination)
    assert code == 1 and "--replace" in output
    assert destination.read_bytes() == original
    code, _ = run_cli(monkeypatch, capsys, "save", source, destination, "--replace")
    assert code == 0 and workflow.load_checkpoint(destination) == doc
    source.write_text("{}")
    code, _ = run_cli(monkeypatch, capsys, "save", source, destination, "--replace")
    assert code == 1 and workflow.load_checkpoint(destination) == doc
