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
    assert len(prompts) == 17
    assert {item["expected_skill"] for item in prompts} == {"property-research", "setup", "none"}
    none_prompts = {
        item["id"]: item["prompt"].lower() for item in prompts if item["expected_skill"] == "none"
    }
    assert "toronto" in none_prompts["trigger_13"]
    assert "data-issue" in none_prompts["trigger_16"]
    assert "legal ownership opinion" in none_prompts["trigger_17"]


def _write(tmp_path, monkeypatch, cases=None, rubric=None, triggers=None):
    for name in ("feature-cases.json", "feature-rubric.json", "trigger-cases.json"):
        (tmp_path / name).write_text((EVALS / name).read_text(encoding="utf-8"), encoding="utf-8")
    for name, value in (
        ("feature-cases.json", cases),
        ("feature-rubric.json", rubric),
        ("trigger-cases.json", triggers),
    ):
        if value is not None:
            (tmp_path / name).write_text(json.dumps(value), encoding="utf-8")
    monkeypatch.setattr(run, "ROOT", tmp_path)


def _load(name):
    return json.loads((EVALS / name).read_text(encoding="utf-8"))


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
    assert (
        "Only tools listed in each case's available_tools are callable (such as the regrid test "
        "double, and in the feature suite also shell and read_file when listed);" in text
    )
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
    assert refs["fields.json"] == (
        run.ROOT.parent / "skills/property-research/references/fields.json"
    ).read_text(encoding="utf-8")


def test_packet_suite_all_includes_fields_catalog(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["run.py", "packet", "--suite", "all"])
    run.main()
    refs = json.loads(capsys.readouterr().out)["references"]
    assert refs["fields.json"] == (
        run.ROOT.parent / "skills/property-research/references/fields.json"
    ).read_text(encoding="utf-8")


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
        ("/ca", True),
        ("/ca/", True),
        ("%2Fca", True),
        ("/us/ca", False),
        ("?country=%63a", True),
        ("?%70ath=/ca/on/toronto", True),
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
        # Defect A: HAR queryString and country parameter
        (
            {
                "harRequest": {
                    "method": "GET",
                    "url": "https://app.regrid.com/api/v2/parcels/path",
                    "queryString": [{"name": "path", "value": "/ca/on/toronto/1"}],
                }
            },
            True,
        ),
        (
            {
                "harRequest": {
                    "method": "GET",
                    "url": "https://app.regrid.com/api/v2/parcels/path",
                    "queryString": [{"name": "path", "value": "/us/ca/los-angeles"}],
                }
            },
            False,
        ),
        (
            {
                "harRequest": {
                    "method": "GET",
                    "url": "https://app.regrid.com/api/v2/parcels/query",
                    "queryString": [{"name": "state2", "value": "ca"}],
                }
            },
            False,
        ),
        (
            {
                "harRequest": {
                    "method": "GET",
                    "url": "https://app.regrid.com/api/v2/parcels/address",
                    "queryString": [{"name": "country", "value": "ca"}],
                }
            },
            True,
        ),
        (
            {
                "harRequest": {
                    "method": "GET",
                    "url": "https://app.regrid.com/api/v2/parcels/address",
                    "queryString": [{"name": "country", "value": "us"}],
                }
            },
            False,
        ),
        ({"country": "ca"}, True),
        ({"parameters": {"country": "CA"}}, True),
        ({"parameters": {"country": "us"}}, False),
        # Defect B: CLI --country ca and schema ca
        ({"command": 'regrid address "1 Main St" --country ca'}, True),
        ({"command": "regrid address '1 Main' --country=ca"}, True),
        ({"command": "regrid schema ca"}, True),
        ({"command": "regrid schema parcel"}, False),
        ({"command": "regrid address '1 Main' --country us"}, False),
        ({"args": ["address", "1 Main", "--country", "ca"]}, True),
        ({"args": ["address", "1 Main", "--country=ca"]}, True),
        ({"args": ["schema", "ca"]}, True),
        ({"args": ["address", "1 Main", "--country", "us"]}, False),
        ({"args": ["schema", "parcel"]}, False),
        # Defect C: California address in command/args must not false-positive
        ({"command": 'regrid address "123 Main St, Los Angeles/CA/90001"'}, False),
        ({"args": ["address", "123 Main St, Los Angeles/CA/90001"]}, False),
        ({"command": "regrid address 123-Main/CA/90001"}, False),
        # Hardened CLI JSON flags, schema with options, -c subshell, and non-str queryString values
        ({"command": 'regrid address "1 Main" --options \'{"country": "ca"}\''}, True),
        ({"command": 'regrid address "1 Main" --options=\'{"country": "ca"}\''}, True),
        ({"command": 'regrid parcel-path --fields \'{"path": "/ca/on/toronto"}\''}, True),
        ({"command": 'regrid area --geojson=\'{"path": "/ca/on/x"}\''}, True),
        ({"command": 'regrid address "1 Main" --options \'{"path": "/us/ca/la"}\''}, False),
        ({"command": "regrid schema --options '{}' ca"}, True),
        ({"command": "regrid schema --options='{}' ca"}, True),
        ({"command": "regrid schema --options '{}' parcel"}, False),
        ({"command": 'bash -c "regrid address foo --country ca"'}, True),
        ({"command": "bash -c \"regrid address '123 Main St, Los Angeles/CA/90001'\""}, False),
        (
            {
                "harRequest": {
                    "method": "GET",
                    "url": "https://app.regrid.com/api/v2/parcels/path",
                    "queryString": [{"name": "path", "value": ["/ca/on/toronto"]}],
                }
            },
            True,
        ),
        (
            {
                "harRequest": {
                    "method": "GET",
                    "url": "https://app.regrid.com/api/v2/parcels/address",
                    "queryString": [{"name": "country", "value": ["ca"]}],
                }
            },
            True,
        ),
    ],
)
def test_canadian_route_detection_encoded_empty_schema_and_free_text(arguments, expected):
    assert run._is_canadian_route(arguments) is expected


def test_validate_handoff_caches_workflow_and_ignores_monkeypatched_root(tmp_path, monkeypatch):
    doc = {
        "schema_version": "1.0",
        "workflow_id": "test-cache",
        "results": [],
        "budget": {
            "max_requests": 0,
            "max_records": 0,
            "attempted_requests": 0,
            "returned_records": 0,
            "uncertain_records": 0,
        },
        "attempts": [],
    }
    monkeypatch.setattr(run, "ROOT", tmp_path)
    run._workflow_module.cache_clear()
    loads = 0
    real_spec = run.importlib.util.spec_from_file_location

    def counting_spec(*args, **kwargs):
        nonlocal loads
        loads += 1
        return real_spec(*args, **kwargs)

    monkeypatch.setattr(run.importlib.util, "spec_from_file_location", counting_spec)
    run.validate_handoff(doc)
    run.validate_handoff(doc)
    assert loads == 1


def test_load_cases_allows_non_parcel_non_error_result(tmp_path, monkeypatch):
    data = _load("feature-cases.json")
    case = data["cases"][0]
    case["tool_history"] = [
        {
            "tool": case["available_tools"][0]["name"],
            "arguments": {"endpoint": "usage", "parameters": {}},
            "result": {
                "isError": False,
                "content": [{"type": "text", "text": '{"usage": {"requests": 1}}'}],
            },
        }
    ]
    _write(tmp_path, monkeypatch, cases=data)
    loaded = run.load_cases("feature")
    assert loaded[0]["tool_history"][0]["arguments"]["endpoint"] == "usage"


def test_packet_main_loads_suite_once(monkeypatch, capsys):
    calls = []
    real_load = run.load_cases

    def spy_load(suite="research"):
        calls.append(suite)
        return real_load(suite)

    monkeypatch.setattr(run, "load_cases", spy_load)
    monkeypatch.setattr("sys.argv", ["run.py", "packet", "--suite", "feature"])
    run.main()
    assert calls == ["feature"]
    out = json.loads(capsys.readouterr().out)
    assert "fields.py" not in out["references"]["fields.json"]


def test_eval_fixtures_and_readme_consistency():
    feature_text = (EVALS / "feature-cases.json").read_text(encoding="utf-8")
    assert "Paid datasets are not authorized." not in feature_text
    assert feature_text.count("Premium datasets are not authorized.") == 8

    feature_cases = _load("feature-cases.json")["cases"]
    export_case = next(c for c in feature_cases if c["id"] == "export_spreadsheet")
    export_features = json.loads(export_case["tool_history"][0]["result"]["content"][0]["text"])[
        "parcels"
    ]["features"]
    assert len(export_features) == 2
    f1, f2 = export_features
    assert f1["properties"]["path"] != f2["properties"]["path"]
    assert f1["properties"]["fields"]["parcelnumb"] != f2["properties"]["fields"]["parcelnumb"]
    assert f1["properties"]["fields"]["ll_uuid"] != f2["properties"]["fields"]["ll_uuid"]
    assert f1["properties"]["fields"]["lat"] != f2["properties"]["fields"]["lat"]
    assert f1["properties"]["fields"]["lon"] != f2["properties"]["fields"]["lon"]
    assert f1["geometry"]["coordinates"] != f2["geometry"]["coordinates"]

    rubric = _load("feature-rubric.json")["criteria"]
    assert "no paid flags" not in json.dumps(rubric)
    assert "no premium flags" in rubric["map_single_address"][1]
    geom_criterion = rubric["geometry_absent"][2]
    assert "/parcels/address has no return_geometry flag" in geom_criterion

    research_cases = _load("cases.json")["cases"]
    multi = next(c for c in research_cases if c["id"] == "multiple_parcels")
    multi_features = json.loads(multi["tool_history"][0]["result"]["content"][0]["text"])[
        "parcels"
    ]["features"]
    uuids = [f["properties"]["fields"]["ll_uuid"] for f in multi_features]
    assert len(uuids) == 2 and len(set(uuids)) == 2

    readme = (EVALS / "README.md").read_text(encoding="utf-8")
    run_section = readme.split("## Run", 1)[1].split("\n## ", 1)[0]
    map_section = readme.split("## Satellite map host checklist", 1)[1].split("\n## ", 1)[0]
    assert "--suite feature" in run_section and "trigger-cases.json" in run_section
    assert "--suite feature" not in map_section and "trigger-cases.json" not in map_section
    assert "data-issue reports" not in readme
    assert "run_discovery_claude.py" in readme.split("## Filesystem discovery")[1].split("### ")[0]
    assert "17 prompts" in run_section
    assert "composability-regressions.json" in run_section
    assert "discovery-rubric.json" in run_section


def _copy_all_eval_files(tmp_path):
    for path in EVALS.glob("*.json"):
        (tmp_path / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")


@pytest.mark.parametrize("suite", ["research", "composition"])
def test_canadian_route_rejected_in_research_and_composition(tmp_path, monkeypatch, suite):
    _copy_all_eval_files(tmp_path)
    filename = "cases.json" if suite == "research" else "composition-cases.json"
    data = _load(filename)
    case = data["cases"][0]
    tool_name = case["available_tools"][0]["name"] if case["available_tools"] else "regrid_request"
    if not case["available_tools"]:
        case["available_tools"] = [{"name": tool_name, "description": "synthetic"}]
    case["tool_history"] = [
        {
            "tool": tool_name,
            "arguments": {"endpoint": "/ca/parcels/address"},
            "result": {"isError": True, "content": [{"type": "text", "text": "x"}]},
        }
    ]
    (tmp_path / filename).write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(run, "ROOT", tmp_path)
    with pytest.raises(AssertionError):
        run.load_cases(suite)


def test_load_composability_cases_validates_and_rejects_broken(tmp_path, monkeypatch):
    cases = run.load_composability_cases()
    assert len(cases) == 8

    _copy_all_eval_files(tmp_path)
    monkeypatch.setattr(run, "ROOT", tmp_path)

    # Missing rubric criterion fails
    rubric = _load("composability-rubric.json")
    del rubric["criteria"]["supplied_evidence_prose"]
    (tmp_path / "composability-rubric.json").write_text(json.dumps(rubric), encoding="utf-8")
    with pytest.raises(AssertionError):
        run.load_composability_cases()

    # Canadian route in tool_history fails
    _copy_all_eval_files(tmp_path)
    comp = _load("composability-regressions.json")
    comp["cases"][1]["tool_history"] = [
        {
            "tool": "regrid_request",
            "arguments": {"path": "/ca/on/toronto"},
            "result": {"isError": True, "message": "x"},
        }
    ]
    (tmp_path / "composability-regressions.json").write_text(json.dumps(comp), encoding="utf-8")
    with pytest.raises(AssertionError):
        run.load_composability_cases()


def test_load_discovery_rubric_validates_and_rejects_broken(tmp_path, monkeypatch):
    rubric = run.load_discovery_rubric()
    assert rubric["grading"] and rubric["critical_failures"]

    _copy_all_eval_files(tmp_path)
    monkeypatch.setattr(run, "ROOT", tmp_path)

    bad = _load("discovery-rubric.json")
    bad["grading"] = "   "
    (tmp_path / "discovery-rubric.json").write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(AssertionError):
        run.load_discovery_rubric()

    bad = _load("discovery-rubric.json")
    bad["critical_failures"] = []
    (tmp_path / "discovery-rubric.json").write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(AssertionError):
        run.load_discovery_rubric()

    bad = _load("discovery-rubric.json")
    del bad["existing-evidence"]
    (tmp_path / "discovery-rubric.json").write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(AssertionError):
        run.load_discovery_rubric()


def test_validate_all_checks_composability_and_discovery_rubrics(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["run.py", "validate", "--suite", "all"])
    run.main()
    assert "Validated 27" in capsys.readouterr().out

    _copy_all_eval_files(tmp_path)
    monkeypatch.setattr(run, "ROOT", tmp_path)
    rubric = _load("composability-rubric.json")
    rubric["criteria"]["supplied_evidence_prose"] = []
    (tmp_path / "composability-rubric.json").write_text(json.dumps(rubric), encoding="utf-8")
    with pytest.raises(AssertionError):
        run.load_cases("all")

    _copy_all_eval_files(tmp_path)
    disc = _load("discovery-rubric.json")
    disc["existing-evidence"] = []
    (tmp_path / "discovery-rubric.json").write_text(json.dumps(disc), encoding="utf-8")
    with pytest.raises(AssertionError):
        run.load_cases("all")


def test_load_cases_allows_non_dict_json_result(tmp_path, monkeypatch):
    data = _load("feature-cases.json")
    case = data["cases"][0]
    case["tool_history"] = [
        {
            "tool": case["available_tools"][0]["name"],
            "arguments": {"endpoint": "usage", "parameters": {}},
            "result": {
                "isError": False,
                "content": [{"type": "text", "text": '["parcels", "other"]'}],
            },
        }
    ]
    _write(tmp_path, monkeypatch, cases=data)
    loaded = run.load_cases("feature")
    assert len(loaded) == 8


def test_validate_enforces_checks_under_python_optimize(tmp_path):
    import subprocess
    import sys

    _copy_all_eval_files(tmp_path)
    triggers = _load("trigger-cases.json")
    triggers["cases"][0]["expected_skill"] = "invalid-skill"
    (tmp_path / "trigger-cases.json").write_text(json.dumps(triggers), encoding="utf-8")

    script = (
        "import importlib.util, pathlib\n"
        f"spec = importlib.util.spec_from_file_location('r', {str(EVALS / 'run.py')!r})\n"
        "m = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(m)\n"
        f"m.ROOT = pathlib.Path({str(tmp_path)!r})\n"
        "m.load_cases('all')\n"
    )
    proc = subprocess.run([sys.executable, "-O", "-c", script], text=True, capture_output=True)
    assert proc.returncode != 0
    assert "AssertionError" in proc.stderr
