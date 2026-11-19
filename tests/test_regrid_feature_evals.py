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
    assert len(prompts) == 15
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
    loaded = run.load_cases("feature")
    assert loaded[0]["tool_history"][0]["arguments"]["parameters"]["path"] == "/us/ca/los-angeles"


def test_feature_packet_allows_shell_and_read_file_doubles():
    text = run.packet(run.load_cases("feature"), False)["instructions"]
    assert "in the feature suite also shell and read_file" in text
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


def test_packet_omits_fields_json_content_outside_feature_suite():
    refs = run.packet(run.load_cases("research"), True)["references"]
    note = refs["fields.json"]
    assert "fields.py" in note and len(note) < 200 and "\n" not in note
    assert "answers.md" in refs and "result.schema.json" in refs


def test_feature_packet_includes_fields_catalog():
    refs = run.packet(run.load_cases("feature"), True, include_fields=True)["references"]
    assert (
        refs["fields.json"]
        == (run.ROOT.parent / "skills/property-research/references/fields.json").read_text()
    )


def test_packet_suite_all_includes_fields_catalog(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["run.py", "packet", "--suite", "all"])
    run.main()
    refs = json.loads(capsys.readouterr().out)["references"]
    assert (
        refs["fields.json"]
        == (run.ROOT.parent / "skills/property-research/references/fields.json").read_text()
    )


def test_packet_research_suite_keeps_placeholder(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["run.py", "packet", "--suite", "research"])
    run.main()
    assert "omitted" in json.loads(capsys.readouterr().out)["references"]["fields.json"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("/ca/on/toronto", True),
        ("https://app.regrid.com/api/v2/ca/parcels/address?query=x", True),
        ("https://x.test/api/v2/parcels/path?path=/ca/on/toronto/1", True),
        ("/us/ca/los-angeles", False),
        ("https://x.test/api/v2/us/ca/parcels/address", False),
        ("CA/ something else", False),
        ("ca/on", True),
        ("ca/on/toronto", True),
        ("https://x.test/api/v2/ca/parcels/address", True),
        ("https://x.test/api/v2/parcels/path?path=/ca/on/x", True),
        ("path=ca/on/x", True),
        ("us/ca/los-angeles", False),
        ("path=us/ca/x", False),
        ("ca", False),
        ("https://x.test/api/v2/parcels/query?fields[state2][eq]=ca&limit=5", False),
        ("/api/v2/parcels/query?state2=ca&limit=1", False),
        ("?fields[state2][eq]=ca&limit=5", False),
        ("?path=/ca/on/x", True),
        ("https://x.test/api/v2/parcels/path?limit=1&path=/ca/on/x", True),
        ("state2=ca&limit=1", False),
    ],
)
def test_canadian_route_detection(value, expected):
    assert run._is_canadian_route({"path": value}) is expected


def test_geometry_absent_fixture_uses_the_real_map_error_text():
    case = next(c for c in run.load_cases("feature") if c["id"] == "geometry_absent")
    assert (
        "error: Parcel: response omits geometry; it was requested without boundaries"
        in (case["context"])
    )


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        ({"path": "%2Fca%2Fon%2Ftoronto"}, True),
        ({"path": "/ca//on/toronto"}, True),
        ({"url": "https://x.test/api/v2/schemas/ca"}, True),
        ({"url": "https://x.test/api/v2/parcels/path?path=%2Fca%2Fon%2Fx"}, True),
        ({"url": "https://x.test/api/v2/schemas/parcel"}, False),
        ({"query": "123 Main St, Los Angeles/CA/90001"}, False),
        ({"query": "/ca/on/toronto", "limit": 1}, False),
        ({"command": "regrid parcel-path /ca/on/x"}, True),
        ({"command": "regrid freshness --path /ca/on/x"}, True),
        ({"command": "regrid freshness --path=/ca/on/x"}, True),
        ({"command": "regrid parcel-path /us/ca/los-angeles"}, False),
        ({"args": ["parcel-path", "/ca/on/x"]}, True),
        ({"args": ["parcel-path", "/us/ca/x"]}, False),
    ],
)
def test_canadian_route_detection_encoded_empty_schema_and_free_text(arguments, expected):
    assert run._is_canadian_route(arguments) is expected
