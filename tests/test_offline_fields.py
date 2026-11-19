"""Offline field catalog helper, generator and bundled skill copy."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

from regrid.offline import fields

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugins/regrid-research/skills/property-research"
SKILL_FIELDS = SKILL / "references/fields.json"
OWNER = {
    "name": "owner",
    "datatype": "text",
    "tier": "standard",
    "category": "Ownership",
    "description": "Owner name",
}
# Derived from the catalog file with the documented rule (name, description or category contains
# the term, case-insensitive), so catalog refreshes do not require editing a literal list.
ASSESSMENT_HITS = sorted(
    entry["name"]
    for entry in json.loads(SKILL_FIELDS.read_text(encoding="utf-8"))["fields"]
    if "assessment"
    in " ".join(str(entry.get(k) or "") for k in ("name", "description", "category")).lower()
)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


generator = _load("generate_skill_fields", ROOT / "scripts/generate_skill_fields.py")


def test_explain_known_and_unknown():
    catalog = fields.load_catalog(SKILL_FIELDS)
    result = fields.explain(catalog, ["parval", "owner", "notafield", "owner"])
    # Found entries keep request order (and repeats); unknown names are reported separately.
    assert [f["name"] for f in result["found"]] == ["parval", "owner", "owner"]
    assert result["found"][1] == OWNER
    assert result["unknown"] == ["notafield"]


def test_search_matches_description_case_insensitive():
    catalog = fields.load_catalog(SKILL_FIELDS)
    hits = fields.search(catalog, "ASSESSMENT")
    assert ASSESSMENT_HITS and [h["name"] for h in hits] == ASSESSMENT_HITS
    assert fields.search(catalog, "no-such-field-term") == []
    # A term found only in a category (not in the name) still matches.
    assert OWNER in fields.search(catalog, "ownership")


def test_compact_and_full_catalogs_agree():
    compact = fields.load_catalog(SKILL_FIELDS)
    full = fields.load_catalog(ROOT / "src/regrid/data/parcel_fields.json")
    assert [f["name"] for f in compact] == sorted(f["name"] for f in full)
    assert len(compact) == len(full)
    assert set(compact[0]) == {"name", "datatype", "tier", "category", "description"}
    assert set(full[0]) == set(compact[0])


def test_skill_catalog_is_current():
    assert generator.main(["--check"]) == 0


def test_generator_detects_stale_and_writes(tmp_path, capsys):
    (tmp_path / "src/regrid/data").mkdir(parents=True)
    source = ROOT / "src/regrid/data/parcel_fields.json"
    (tmp_path / "src/regrid/data/parcel_fields.json").write_bytes(source.read_bytes())
    target = tmp_path / generator.TARGET
    assert generator.main(["--check"], root=tmp_path) == 1
    assert (
        "fields.json is stale; run python scripts/generate_skill_fields.py"
        in capsys.readouterr().out
    )
    assert generator.main([], root=tmp_path) == 0
    assert target.read_bytes() == SKILL_FIELDS.read_bytes()
    assert generator.main(["--check"], root=tmp_path) == 0


def test_load_catalog_rejects_bad_documents(tmp_path):
    bad = tmp_path / "bad.json"
    for body in ('{"fields": 3}', "[]", '{"fields": [1]}'):
        bad.write_text(body)
        with pytest.raises(ValueError, match="^Unrecognized field catalog format$"):
            fields.load_catalog(bad)


def test_main_explain_and_search(capsys):
    assert fields.main(["explain", "owner", "zzz", "--catalog", str(SKILL_FIELDS)]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"found": [OWNER], "unknown": ["zzz"]}
    assert captured.err == ""
    assert fields.main(["search", "assessment", "--catalog", str(SKILL_FIELDS)]) == 0
    matches = json.loads(capsys.readouterr().out)["matches"]
    assert [m["name"] for m in matches] == ASSESSMENT_HITS


def test_main_default_catalog_and_errors(tmp_path, capsys):
    missing = tmp_path / "none.json"
    assert fields.main(["explain", "owner", "--catalog", str(missing)]) == 1
    captured = capsys.readouterr()
    assert captured.err == f"fields: [Errno 2] No such file or directory: {str(missing)!r}\n"
    assert captured.out == ""


def test_default_catalog_prefers_references_then_packaged_data(tmp_path):
    here = tmp_path / "pkg" / "offline"
    here.mkdir(parents=True)
    with pytest.raises(FileNotFoundError, match="No field catalog found"):
        fields.default_catalog(here)
    data = here.parent / "data"
    data.mkdir()
    (data / "parcel_fields.json").write_text("{}")
    assert fields.default_catalog(here) == data / "parcel_fields.json"
    refs = here.parent / "references"
    refs.mkdir()
    (refs / "fields.json").write_text("{}")
    assert fields.default_catalog(here) == refs / "fields.json"


def test_main_reports_missing_default_catalog(monkeypatch, capsys):
    def missing(*args):
        raise FileNotFoundError("No field catalog found")

    monkeypatch.setattr(fields, "default_catalog", missing)
    assert fields.main(["search", "owner"]) == 1
    captured = capsys.readouterr()
    assert captured.err == "fields: No field catalog found\n"
    assert captured.out == ""


def test_sdk_copy_falls_back_to_packaged_catalog():
    assert fields.DEFAULT_CATALOG == ROOT / "src/regrid/data/parcel_fields.json"
    packaged = json.loads(fields.DEFAULT_CATALOG.read_text(encoding="utf-8"))["fields"]
    assert len(fields.load_catalog(fields.DEFAULT_CATALOG)) == len(packaged)


def test_fields_helper_runs_from_extracted_archive(tmp_path):
    builder = _load("fields_test_builder", ROOT / "scripts/build_claude_plugins.py")
    archives = builder.build(ROOT / "plugins/regrid-research", tmp_path / "archives")
    with ZipFile(archives[-1]) as archive:
        archive.extractall(tmp_path / "extracted")
    helper = tmp_path / "extracted/property-research/scripts/fields.py"
    result = subprocess.run(
        [sys.executable, "-I", str(helper), "explain", "owner"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"found": [OWNER], "unknown": []}


@pytest.mark.parametrize("name", [["x"], None, "", 5])
def test_load_catalog_requires_string_names(tmp_path, name):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"fields": [{"name": name}]}))
    with pytest.raises(ValueError, match="non-empty string"):
        fields.load_catalog(path)


def test_deeply_nested_catalog_is_a_clean_error(tmp_path, capsys):
    path = tmp_path / "deep.json"
    path.write_text("[" * 200000 + "]" * 200000)
    assert fields.main(["search", "x", "--catalog", str(path)]) == 1
    err = capsys.readouterr().err
    assert err.startswith("fields:") and len(err.strip().splitlines()) == 1
