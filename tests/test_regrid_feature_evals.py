"""Feature and trigger evaluation fixtures validate structurally; no model runs."""

import copy
import importlib.util
import json
from pathlib import Path

import pytest

EVALS = Path(__file__).resolve().parents[1] / "plugins/regrid-research/evals"
spec = importlib.util.spec_from_file_location("regrid_evals_run", EVALS / "run.py")
assert spec and spec.loader
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)

CASE_IDS = {
    "map_single_address",
    "map_with_neighbours",
    "export_spreadsheet",
    "explain_field",
    "freshness_mcp_only",
    "mistyped_address",
    "geometry_absent",
    "non_us_map",
}


def test_feature_suite_has_the_eight_scenarios():
    cases = run.load_cases("feature")
    assert {case["id"] for case in cases} == CASE_IDS
    assert all(case["us_only"] is True for case in cases)


def test_all_suite_includes_feature_and_unique_ids():
    ids = [case["id"] for case in run.load_cases("all")]
    assert CASE_IDS <= set(ids)
    assert len(ids) == len(set(ids))


def test_trigger_cases_cover_every_label():
    prompts = run.load_trigger_cases()
    assert len(prompts) == 12
    assert {item["expected_skill"] for item in prompts} == {"property-research", "setup", "none"}


def _write(tmp_path, monkeypatch, cases=None, rubric=None, triggers=None):
    for name in ("feature-cases.json", "feature-rubric.json", "trigger-cases.json"):
        (tmp_path / name).write_text((EVALS / name).read_text())
    for name, value in (
        ("feature-cases.json", cases),
        ("feature-rubric.json", rubric),
        ("trigger-cases.json", triggers),
    ):
        if value is not None:
            (tmp_path / name).write_text(json.dumps(value))
    monkeypatch.setattr(run, "ROOT", tmp_path)


def _load(name):
    return json.loads((EVALS / name).read_text())


def test_missing_rubric_entry_rejected(tmp_path, monkeypatch):
    rubric = _load("feature-rubric.json")
    del rubric["criteria"]["non_us_map"]
    _write(tmp_path, monkeypatch, rubric=rubric)
    with pytest.raises(AssertionError):
        run.load_cases("feature")


def test_duplicate_ids_rejected(tmp_path, monkeypatch):
    data = _load("feature-cases.json")
    data["cases"].append(copy.deepcopy(data["cases"][0]))
    _write(tmp_path, monkeypatch, cases=data)
    with pytest.raises(AssertionError):
        run.load_cases("feature")


def test_non_synthetic_rejected(tmp_path, monkeypatch):
    data = _load("feature-cases.json")
    data["synthetic"] = False
    _write(tmp_path, monkeypatch, cases=data)
    with pytest.raises(AssertionError):
        run.load_cases("feature")


def test_non_us_tool_history_rejected(tmp_path, monkeypatch):
    data = _load("feature-cases.json")
    data["cases"][0]["tool_history"] = [
        {
            "tool": data["cases"][0]["available_tools"][0]["name"],
            "arguments": {"endpoint": "/ca/parcels/address"},
            "result": {"isError": True, "content": [{"type": "text", "text": "x"}]},
        }
    ]
    _write(tmp_path, monkeypatch, cases=data)
    with pytest.raises(AssertionError):
        run.load_cases("feature")


def test_bad_trigger_label_rejected(tmp_path, monkeypatch):
    triggers = _load("trigger-cases.json")
    triggers["cases"][0]["expected_skill"] = "other"
    _write(tmp_path, monkeypatch, triggers=triggers)
    with pytest.raises(AssertionError):
        run.load_trigger_cases()


def test_trigger_duplicate_prompt_rejected(tmp_path, monkeypatch):
    triggers = _load("trigger-cases.json")
    triggers["cases"][1]["prompt"] = triggers["cases"][0]["prompt"]
    _write(tmp_path, monkeypatch, triggers=triggers)
    with pytest.raises(AssertionError):
        run.load_trigger_cases()


def test_cli_validate_feature(capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", ["run.py", "validate", "--suite", "feature"])
    run.main()
    assert "Validated 8" in capsys.readouterr().out


def test_california_us_path_is_not_flagged_non_us(tmp_path, monkeypatch):
    data = _load("feature-cases.json")
    case = data["cases"][0]
    case["tool_history"] = [
        {
            "tool": case["available_tools"][0]["name"],
            "arguments": {"endpoint": "path", "parameters": {"path": "/us/ca/los-angeles"}},
            "result": {"isError": True, "content": [{"type": "text", "text": "x"}]},
        }
    ]
    _write(tmp_path, monkeypatch, cases=data)
    run.load_cases("feature")


def test_feature_packet_allows_shell_and_read_file_doubles():
    text = run.packet(run.load_cases("feature"), False)["instructions"]
    assert "shell" in text and "read_file" in text
    assert "only simulated callable tool" not in text


def test_non_us_map_context_does_not_claim_all_us():
    case = next(c for c in run.load_cases("feature") if c["id"] == "non_us_map")
    assert "deliberately outside the US" in case["context"]
    assert "in the US." not in case["context"].replace("outside the US", "")


def test_feature_suite_validates_trigger_cases(tmp_path, monkeypatch):
    triggers = _load("trigger-cases.json")
    triggers["cases"][0]["expected_skill"] = "other"
    _write(tmp_path, monkeypatch, triggers=triggers)
    with pytest.raises(AssertionError):
        run.load_cases("feature")


def test_packet_omits_fields_json_content():
    refs = run.packet(run.load_cases("feature"), True)["references"]
    note = refs["fields.json"]
    assert "fields.py" in note and len(note) < 200 and "\n" not in note
    assert "answers.md" in refs and "result.schema.json" in refs
