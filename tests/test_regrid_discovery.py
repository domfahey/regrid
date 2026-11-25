"""Discovery trials remain blinded and filesystem-only."""

import hashlib
import importlib.util
import json
import os
import re
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
    packet = json.loads((destination / "prompt.json").read_text(encoding="utf-8"))
    assert "execution_limit" not in packet
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
        p.relative_to(destination / "skills/property-research").as_posix()
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


@pytest.mark.skipif(os.name == "nt", reason="symlinks need privilege on Windows")
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
    fixture = json.loads((tmp_path / "trial/data/evidence.json").read_text(encoding="utf-8"))
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
        + "\n",
        encoding="utf-8",
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
    assert skill["trace"] == [json.loads(trace.read_text(encoding="utf-8"))]
    assert skill["trace_sha256"] == hashlib.sha256(trace.read_bytes()).hexdigest()
    assert skill["tool_calls"] == [
        {"name": "Read", "input": {"file_path": "skills/property-research/SKILL.md"}}
    ]
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


def packaged_property_research():
    """Return the packager's property-research file set, relative to the skill directory."""
    spec = importlib.util.spec_from_file_location(
        "build_claude_plugins",
        Path(__file__).resolve().parents[1] / "scripts/build_claude_plugins.py",
    )
    assert spec and spec.loader
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    plugin = Path(__file__).resolve().parents[1] / "plugins/regrid-research"
    prefix = "skills/property-research/"
    return {
        name.removeprefix(prefix)
        for name in builder.skill_files(plugin, "property-research")
        if name.startswith(prefix)
    }


def test_allowlist_matches_packaged_property_research():
    assert set(discovery.ALLOWLIST) == packaged_property_research()


def test_every_skill_link_is_staged():
    text = discovery.SKILL.joinpath("SKILL.md").read_text(encoding="utf-8")
    targets = set()
    for target in re.findall(r"\]\(([^)\s]+)\)", text):
        if "://" in target or target.startswith(("mailto:", "#")):
            continue
        path = target.split("#", 1)[0]
        if path:
            targets.add(path)
    assert targets, "SKILL.md should link to its references"
    missing = sorted(t for t in targets if t not in discovery.ALLOWLIST)
    assert missing == []


def test_metadata_missing_frontmatter_raises_value_error(tmp_path):
    bad = tmp_path / "SKILL.md"
    bad.write_text("# No frontmatter here\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Missing YAML frontmatter"):
        discovery.metadata(bad)


NULL_EVENTS = [
    {"type": "assistant", "message": None},
    {"type": "assistant", "message": {"model": None, "content": None}},
    {"type": "assistant", "message": {"content": [{"type": "tool_use"}]}},
    {
        "type": "assistant",
        "message": {"content": [{"type": "tool_use", "name": "Read", "input": None}]},
    },
    {"type": "assistant", "message": {"content": [None, "text"]}},
]


def test_extract_calls_tolerates_null_fields():
    models, calls = discovery.extract_calls(NULL_EVENTS)
    assert models == set()
    assert calls == [{"name": None, "input": {}}, {"name": "Read", "input": {}}]


def test_record_tolerates_null_fields(tmp_path):
    trace = tmp_path / "trace.jsonl"
    trace.write_text("\n".join(json.dumps(event) for event in NULL_EVENTS) + "\n", encoding="utf-8")
    report = discovery.record({}, trace, "claude-test-1", "2.test")
    assert report["read_paths"] == [None]
    assert len(report["tool_calls"]) == 2


def test_non_object_tool_input_is_preserved():
    events = [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Read", "input": '{"file_path": "x.md"}'},
                    {"type": "tool_use", "name": "Read", "input": {"file_path": "y.md"}},
                ]
            },
        }
    ]
    _, calls = discovery.extract_calls(events)
    assert calls[0]["input"] == '{"file_path": "x.md"}'
    assert discovery.read_paths(calls) == [None, "y.md"]


def test_stage_optional_execution_limit(tmp_path):
    limit = "Only Read, Glob, and Grep are available."
    destination = tmp_path / "trial"
    manifest = discovery.stage("existing-evidence", "skill", destination, execution_limit=limit)
    prompt_path = destination / "prompt.json"
    packet = json.loads(prompt_path.read_text(encoding="utf-8"))
    assert packet["execution_limit"] == limit
    assert manifest["files"]["prompt.json"] == hashlib.sha256(prompt_path.read_bytes()).hexdigest()


def test_metadata_rejects_horizontal_rules_without_frontmatter(tmp_path):
    bad = tmp_path / "SKILL.md"
    bad.write_text("# Heading\n\n---\nname: fake\ndescription: fake\n---\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Missing YAML frontmatter"):
        discovery.metadata(bad)


def test_stage_normalizes_relative_paths_with_as_posix(tmp_path, monkeypatch):
    real_relative_to = Path.relative_to

    class WindowsLikeRel:
        def __init__(self, rel: Path):
            self._posix = rel.as_posix()

        def as_posix(self) -> str:
            return self._posix

        def __str__(self) -> str:
            return self._posix.replace("/", "\\")

    def windows_relative_to(self, *other):
        rel = real_relative_to(self, *other)
        if tmp_path in self.parents or self == tmp_path:
            return WindowsLikeRel(rel)
        return rel

    monkeypatch.setattr(Path, "relative_to", windows_relative_to)
    destination = tmp_path / "trial"
    manifest = discovery.stage("structured-handoff", "skill", destination)
    packet = json.loads((destination / "prompt.json").read_text(encoding="utf-8"))
    assert all("\\" not in item["path"] for item in packet["available_skills"])
    assert "data/evidence.json" in manifest["files"]
    assert "support/workflow.py" in manifest["files"]
    assert all("\\" not in key for key in manifest["files"])


def test_record_hashes_raw_crlf_trace_bytes(tmp_path):
    trace = tmp_path / "trace.jsonl"
    line = json.dumps(
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
    raw_bytes = (line + "\r\n").encode("utf-8")
    trace.write_bytes(raw_bytes)
    report = discovery.record(
        {"case_id": "existing-evidence", "variant": "skill"},
        trace,
        "claude-sonnet-test-1",
        "2.test",
    )
    assert report["trace_sha256"] == hashlib.sha256(raw_bytes).hexdigest()
    assert report["read_paths"] == ["skills/property-research/SKILL.md"]
