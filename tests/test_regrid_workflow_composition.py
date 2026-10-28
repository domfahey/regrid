"""Behavioral regressions for versioned, offline workflow composition."""

import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "plugins/regrid-research/skills/property-research/scripts/workflow.py"
)
SPEC = importlib.util.spec_from_file_location("composition_workflow", SCRIPT)
assert SPEC and SPEC.loader
workflow = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(workflow)


def legacy():
    return workflow.new_workflow(
        "legacy", [{"address": "12 Example Ave", "parcel_id": None, "scope": None}], 3, 2
    )


QUERIES = [
    {"query_type": "owner", "owner": "Example LLC", "scope": "us/nj/camden"},
    {"query_type": "point", "lat": 39.9, "lon": -75.1, "radius": 10},
    {"query_type": "area", "bbox": [-75.2, 39.8, -75.0, 40.0]},
    {
        "query_type": "filter",
        "scope": "us/nj/camden",
        "filters": {"owner": {"eq": "Example LLC"}},
    },
]


@pytest.mark.parametrize("query", QUERIES)
def test_versioned_query_roundtrip_without_invented_identity(query, tmp_path):
    original = deepcopy(query)
    doc = workflow.new_workflow("query", [query, query], 2, 2, schema_version="1.1")
    assert doc["results"][0]["requested"] == original
    assert query == original
    doc = workflow.reserve_attempt(doc, ["input-000001"], 1)
    workflow.save_checkpoint(doc, tmp_path / "query.json", requested=True)
    resumed = workflow.load_checkpoint(tmp_path / "query.json")
    assert resumed == doc
    assert workflow.pending_input_ids(resumed) == ["input-000002"]


def test_legacy_version_is_preserved_until_explicit_upgrade(tmp_path):
    doc = legacy()
    assert doc["schema_version"] == "1.0"
    workflow.save_checkpoint(doc, tmp_path / "old.json", requested=True)
    assert workflow.load_checkpoint(tmp_path / "old.json") == doc
    upgraded = workflow.upgrade_workflow(doc)
    assert upgraded == {**doc, "schema_version": "1.1", "reconciliations": []}
    assert doc["schema_version"] == "1.0"
    assert workflow.upgrade_workflow(upgraded) == upgraded
    with pytest.raises(ValueError):
        workflow.new_workflow("old", [QUERIES[0]], 1, 1)


@pytest.mark.parametrize(
    "query",
    [
        {"query_type": "owner", "owner": "Example LLC", "scope": None},
        {"query_type": "point", "lat": 91, "lon": 0, "radius": 1},
        {"query_type": "point", "lat": True, "lon": 0, "radius": 1},
        {"query_type": "point", "lat": 0, "lon": 0, "radius": 0},
        {"query_type": "area", "bbox": [2, 1, 1, 3]},
        {"query_type": "filter", "scope": "us/nj", "filters": []},
        {
            "query_type": "filter",
            "scope": "us/nj",
            "filters": [{"field": "owner", "operator": "sql", "value": "x"}],
        },
    ],
)
def test_query_rejects_unbounded_or_invalid_input(query):
    before = deepcopy(query)
    with pytest.raises(ValueError):
        workflow.new_workflow("invalid", [query], 1, 1, schema_version="1.1")
    assert query == before


def uncertain():
    doc = workflow.reserve_attempt(legacy(), ["input-000001"], 2)
    return workflow.complete_attempt(doc, "attempt-000001", "uncertain")


def proof(count=1):
    return {
        "provider": "Regrid",
        "evidence_id": "receipt-1",
        "retrieved_at": "2026-10-28T12:00:00Z",
        "attempt_id": "attempt-000001",
        "returned_records": count,
        "source_url": None,
    }


def test_reconciliation_preserves_attempt_history_results_and_exact_counts(tmp_path):
    old = uncertain()
    doc = workflow.upgrade_workflow(old)
    before = deepcopy(doc)
    reconciled = workflow.reconcile_attempt(doc, "attempt-000001", proof(), evidence_verified=True)
    assert doc == before
    assert reconciled["attempts"] == before["attempts"]
    assert reconciled["results"] == before["results"]
    assert reconciled["budget"] == {**doc["budget"], "returned_records": 1, "uncertain_records": 0}
    assert reconciled["reconciliations"] == [{"attempt_id": "attempt-000001", "proof": proof()}]
    assert workflow.pending_input_ids(reconciled) == []
    with pytest.raises(ValueError):
        workflow.reserve_attempt(reconciled, ["input-000001"], 1)
    workflow.save_checkpoint(reconciled, tmp_path / "receipt.json", requested=True)
    assert workflow.load_checkpoint(tmp_path / "receipt.json") == reconciled
    with pytest.raises(ValueError):
        workflow.reconcile_attempt(reconciled, "attempt-000001", proof(), evidence_verified=True)
    assert reconciled["reconciliations"] == [{"attempt_id": "attempt-000001", "proof": proof()}]


@pytest.mark.parametrize("count", [0, 7])
def test_reconciliation_retains_zero_and_provider_overshoot(count):
    doc = workflow.upgrade_workflow(uncertain())
    reconciled = workflow.reconcile_attempt(
        doc, "attempt-000001", proof(count), evidence_verified=True
    )
    assert reconciled["budget"]["returned_records"] == count
    assert reconciled["budget"]["uncertain_records"] == 0
    if count > 2:
        with pytest.raises(ValueError, match="budget"):
            workflow.reserve_attempt(reconciled, ["input-000001"], 0, authorized_retry=True)


@pytest.mark.parametrize(
    "receipt,verified",
    [
        (proof(), False),
        (None, True),
        ({}, True),
        ({**proof(), "attempt_id": "forged-other-attempt"}, True),
        ({**proof(), "provider": " "}, True),
        ({**proof(), "returned_records": -1}, True),
        ({**proof(), "returned_records": True}, True),
    ],
)
def test_reconciliation_rejects_unverified_missing_and_mismatched_proof(receipt, verified):
    doc = workflow.upgrade_workflow(uncertain())
    before = deepcopy(doc)
    with pytest.raises(ValueError):
        workflow.reconcile_attempt(doc, "attempt-000001", receipt, evidence_verified=verified)
    assert doc == before


def test_reconciliation_requires_explicit_upgrade_and_uncertain_attempt():
    old = uncertain()
    with pytest.raises(ValueError):
        workflow.reconcile_attempt(old, "attempt-000001", proof(), evidence_verified=True)
    doc = workflow.upgrade_workflow(legacy())
    doc = workflow.reserve_attempt(doc, ["input-000001"], 1)
    for state in ["pending", "success", "error"]:
        settled = (
            doc
            if state == "pending"
            else workflow.complete_attempt(doc, "attempt-000001", state, 0)
        )
        with pytest.raises(ValueError):
            workflow.reconcile_attempt(settled, "attempt-000001", proof(), evidence_verified=True)


def test_diagnostic_attempt_is_charged_without_consuming_property_input():
    doc = workflow.upgrade_workflow(legacy())
    doc = workflow.reserve_attempt(doc, [], 0, kind="diagnostic")
    assert doc["attempts"][0]["kind"] == "diagnostic"
    assert doc["budget"]["attempted_requests"] == 1
    assert workflow.pending_input_ids(doc) == ["input-000001"]
    doc = workflow.complete_attempt(doc, "attempt-000001", "success", 0)
    doc = workflow.reserve_attempt(doc, ["input-000001"], 1)
    assert doc["attempts"][1]["kind"] == "lookup"
    for inputs, count in [(["input-000001"], 0), ([], 1)]:
        with pytest.raises(ValueError):
            workflow.reserve_attempt(
                workflow.upgrade_workflow(legacy()), inputs, count, kind="diagnostic"
            )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d["reconciliations"].append(deepcopy(d["reconciliations"][0])),
        lambda d: d["reconciliations"][0]["proof"].update(attempt_id="unknown"),
        lambda d: d["reconciliations"][0]["proof"].update(returned_records=0),
        lambda d: d["attempts"][0].update(state="success", returned_records=1),
        lambda d: d["reconciliations"][0]["proof"].pop("evidence_id"),
        lambda d: d["budget"].update(uncertain_records=2),
    ],
)
def test_checkpoint_rejects_forged_reconciliation_links_and_accounting(mutate, tmp_path):
    doc = workflow.reconcile_attempt(
        workflow.upgrade_workflow(uncertain()), "attempt-000001", proof(), evidence_verified=True
    )
    mutate(doc)
    before = deepcopy(doc)
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(doc))
    with pytest.raises(ValueError):
        workflow.load_checkpoint(path)
    assert doc == before


def test_receipt_cannot_be_reused_for_another_attempt():
    doc = workflow.upgrade_workflow(uncertain())
    doc = workflow.reconcile_attempt(doc, "attempt-000001", proof(0), evidence_verified=True)
    doc = workflow.reserve_attempt(doc, ["input-000001"], 2, authorized_retry=True)
    doc = workflow.complete_attempt(doc, "attempt-000002", "uncertain")
    before = deepcopy(doc)
    second = {**proof(), "attempt_id": "attempt-000002"}
    with pytest.raises(ValueError, match="receipt"):
        workflow.reconcile_attempt(doc, "attempt-000002", second, evidence_verified=True)
    assert doc == before
    second["evidence_id"] = "receipt-2"
    reconciled = workflow.reconcile_attempt(doc, "attempt-000002", second, evidence_verified=True)
    assert reconciled["reconciliations"][:1] == doc["reconciliations"]
    assert reconciled["budget"]["attempted_requests"] == 2
    assert reconciled["budget"]["returned_records"] == 1
    assert reconciled["budget"]["uncertain_records"] == 0


def test_upgrade_and_reconciliation_preserve_existing_evidence():
    doc = uncertain()
    doc["results"][0].update(lookup_status="success", match_status="confirmed")
    doc["results"][0]["candidates"] = [
        {
            "parcel_id": "parcel-1",
            "address": None,
            "facts": {"owner": "Example LLC"},
            "provenance": {
                "provider": "Supplied",
                "retrieved_at": None,
                "source_refreshed_at": None,
                "source_url": None,
                "evidence_id": "supplied-1",
            },
        }
    ]
    before = deepcopy(doc)
    upgraded = workflow.upgrade_workflow(doc)
    assert upgraded["attempts"] == [{**doc["attempts"][0], "kind": "lookup"}]
    reconciled = workflow.reconcile_attempt(
        upgraded, "attempt-000001", proof(), evidence_verified=True
    )
    assert reconciled["results"] == doc["results"]
    assert doc == before


def test_diagnostic_error_and_uncertainty_remain_charged_without_retry():
    doc = workflow.new_workflow("diagnostic", [QUERIES[0]], 1, 2, schema_version="1.1")
    reserved = workflow.reserve_attempt(doc, [], 0, kind="diagnostic")
    before = deepcopy(reserved)
    for state, count in [("success", 1), ("error", 1)]:
        with pytest.raises(ValueError):
            workflow.complete_attempt(reserved, "attempt-000001", state, count)
        assert reserved == before
    for state, count in [("uncertain", None), ("error", 0)]:
        complete = workflow.complete_attempt(reserved, "attempt-000001", state, count)
        assert workflow.pending_input_ids(complete) == ["input-000001"]
        with pytest.raises(ValueError, match="budget"):
            workflow.reserve_attempt(complete, ["input-000001"], 1)


def test_filter_preserves_nested_json_and_defers_endpoint_operator_validation():
    query = {
        "query_type": "filter",
        "scope": "us/nj",
        "filters": {"owner": {"future_operator": ["a", {"b": None}]}},
    }
    doc = workflow.new_workflow("filter", [query], 1, 1, schema_version="1.1")
    assert doc["results"][0]["requested"] == query


def test_json_schema_and_runtime_agree_on_versioned_structural_contract():
    import jsonschema

    schema = json.loads((SCRIPT.parent.parent / "references/result.schema.json").read_text())
    validator = jsonschema.Draft202012Validator(schema)
    validator.check_schema(schema)
    old = legacy()
    new = workflow.upgrade_workflow(uncertain())
    reconciled = workflow.reconcile_attempt(new, "attempt-000001", proof(), evidence_verified=True)
    diagnostic = workflow.reserve_attempt(workflow.upgrade_workflow(old), [], 0, kind="diagnostic")
    valid = [old, new, reconciled, diagnostic] + [
        workflow.new_workflow("query", [query], 1, 1, schema_version="1.1") for query in QUERIES
    ]
    for doc in valid:
        validator.validate(doc)
        workflow.validate(doc)
    invalid = []
    for doc in valid:
        item = deepcopy(doc)
        item["extra"] = True
        invalid.append(item)
    item = deepcopy(new)
    item["schema_version"] = "1.0"
    invalid.append(item)
    item = deepcopy(new)
    del item["attempts"][0]["kind"]
    invalid.append(item)
    item = deepcopy(valid[-1])
    item["schema_version"] = "1.0"
    item.pop("reconciliations")
    invalid.append(item)
    for doc in invalid:
        assert not validator.is_valid(doc)
        with pytest.raises(ValueError):
            workflow.validate(doc)
