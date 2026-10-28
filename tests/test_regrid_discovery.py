"""Discovery trials remain blinded and filesystem-only."""

import importlib.util
import json
from pathlib import Path

import pytest

MODULE = Path(__file__).resolve().parents[1] / "plugins/regrid-research/evals/discovery.py"
spec = importlib.util.spec_from_file_location("discovery", MODULE)
assert spec and spec.loader
discovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(discovery)


@pytest.mark.parametrize(
    "case",
    ["existing-evidence", "structured-handoff", "checkpoint-correction", "irrelevant-request"],
)
def test_stage_blinded_metadata_and_allowlist(tmp_path, case):
    destination = tmp_path / "trial"
    manifest = discovery.stage(case, "skill", destination)
    packet = json.loads((destination / "prompt.json").read_text())
    assert len(packet["available_skills"]) == 3
    assert all(
        set(skill) == {"name", "description", "path"} for skill in packet["available_skills"]
    )
    assert "# Regrid property research" not in json.dumps(packet)
    assert not any(
        "rubric" in name or ".env" in name or name.endswith(".mcp.json")
        for name in manifest["files"]
    )
    assert set(
        str(p.relative_to(destination / "skills/property-research"))
        for p in (destination / "skills/property-research").rglob("*")
        if p.is_file()
    ) == set(discovery.ALLOWLIST)


def test_baseline_keeps_task_dependencies_but_no_target_skill(tmp_path):
    for variant in ("skill", "baseline"):
        discovery.stage("structured-handoff", variant, tmp_path / variant)
    assert not (tmp_path / "baseline/skills/property-research").exists()
    for filename in ("result.schema.json", "workflow.py"):
        assert (tmp_path / "skill/support" / filename).read_bytes() == (
            tmp_path / "baseline/support" / filename
        ).read_bytes()
    assert (tmp_path / "skill/data/evidence.json").read_bytes() == (
        tmp_path / "baseline/data/evidence.json"
    ).read_bytes()


def test_no_overwrite_and_no_symlink_sources(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="already exists"):
        discovery.stage("existing-evidence", "skill", tmp_path)
    root = tmp_path / "source"
    root.mkdir()
    (root / "SKILL.md").symlink_to(discovery.SKILL / "SKILL.md")
    monkeypatch.setattr(discovery, "SKILL", root)
    with pytest.raises(ValueError, match="symlinks"):
        discovery.stage("existing-evidence", "skill", tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_checkpoint_contains_real_inconsistency(tmp_path):
    discovery.stage("checkpoint-correction", "skill", tmp_path / "trial")
    fixture = json.loads((tmp_path / "trial/data/evidence.json").read_text())
    assert fixture["budget"]["attempted_requests"] == 0
    assert len(fixture["attempts"]) == 1
    assert fixture["budget"]["max_requests"] == 1


def test_trace_recording_and_comparison(tmp_path):
    trace = tmp_path / "trace.jsonl"
    trace.write_text(
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "model": "claude-sonnet-test-1",
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Read",
                            "input": {"file_path": "skills/property-research/SKILL.md"},
                        }
                    ],
                },
            }
        )
        + "\n"
    )
    skill = discovery.record(
        {"case_id": "existing-evidence", "variant": "skill"},
        trace,
        "claude-sonnet-test-1",
        "2.test",
    )
    baseline = discovery.record(
        {"case_id": "existing-evidence", "variant": "baseline"},
        trace,
        "claude-sonnet-test-1",
        "2.test",
    )
    assert skill["observed_models"] == ["claude-sonnet-test-1"]
    assert skill["read_paths"] == ["skills/property-research/SKILL.md"]
    assert skill["trace"] and skill["trace_sha256"]
    assert discovery.compare(skill, baseline)["verdict"] == "not_graded"
    baseline["requested_model"] = "other-model"
    with pytest.raises(ValueError, match="requested_model"):
        discovery.compare(skill, baseline)
    with pytest.raises(ValueError, match="explicit model"):
        discovery.record({}, trace, "sonnet", "2.test")


def test_comparison_requires_observed_models_and_identical_shared_inputs():
    base = {
        "case_id": "existing-evidence",
        "requested_model": "claude-test",
        "cli_version": "2",
        "observed_models": ["claude-test-resolved"],
        "files": {"data/evidence.json": "abc"},
        "read_paths": [],
        "tool_calls": [],
    }
    skill, baseline = {**base, "variant": "skill"}, {**base, "variant": "baseline"}
    assert discovery.compare(skill, baseline)["comparison_status"] == "comparable"
    baseline["observed_models"] = ["claude-other"]
    with pytest.raises(ValueError, match="observed_models"):
        discovery.compare(skill, baseline)
    baseline["observed_models"] = []
    assert discovery.compare(skill, baseline)["comparison_status"] == "incomplete"
    baseline["files"] = {"data/evidence.json": "different"}
    with pytest.raises(ValueError, match="input hashes"):
        discovery.compare(skill, baseline)
