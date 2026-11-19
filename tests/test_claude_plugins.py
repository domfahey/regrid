"""Packaging must preserve shared skills while keeping transport and secrets separate."""

import importlib.util
import json
import shutil
from pathlib import Path
from zipfile import ZipFile

import pytest

import regrid

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins/regrid-research"
SKILL_ROOT = ROOT / "plugins/regrid-research/skills/property-research"
SPEC = importlib.util.spec_from_file_location(
    "build_claude_plugins", ROOT / "scripts" / "build_claude_plugins.py"
)
assert SPEC and SPEC.loader
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "source"
    shutil.copytree(ROOT / "plugins" / "regrid-research", path)
    references = path / "skills" / "property-research" / "references"
    references.mkdir(exist_ok=True)
    (references / "packaging-test.md").write_text("Reference used by the skill.\n")
    return path


def archive_contents(path):
    with ZipFile(path) as archive:
        assert archive.testzip() is None
        return {name: archive.read(name) for name in archive.namelist()}


def test_transports_share_complete_skill_and_build_reproducibly(source, tmp_path):
    paths = builder.build(source, tmp_path / "first")
    cowork, code, skill = map(archive_contents, paths)
    assert json.loads(cowork[".mcp.json"]) == {
        "mcpServers": {"regrid": {"type": "http", "url": "https://support.regrid.com/mcp"}}
    }
    assert json.loads(code[".mcp.json"])["mcpServers"]["regrid"]["env"] == {
        "REGRID_TOKEN": "${REGRID_TOKEN}"
    }
    assert set(cowork) == set(code)
    for name in cowork:
        if name != ".mcp.json":
            assert cowork[name] == code[name]
    for name, content in skill.items():
        assert name.startswith("property-research/")
        assert content == code["skills/" + name]
    assert "property-research/references/packaging-test.md" in skill
    second = builder.build(source, tmp_path / "second")
    assert [p.read_bytes() for p in paths] == [p.read_bytes() for p in second]


def test_unlisted_files_never_enter_archives(source, tmp_path):
    for relative in (
        ".env",
        "credentials.json",
        "scratch.md",
        "skills/property-research/.env",
        "skills/property-research/references/secrets.json",
        "skills/property-research/references/.env.json",
        "skills/property-research/references/debug.log",
    ):
        (source / relative).write_text("DO_NOT_PACKAGE")
    for path in builder.build(source, tmp_path / "output"):
        assert all(b"DO_NOT_PACKAGE" not in data for data in archive_contents(path).values())


@pytest.mark.parametrize("relative", ["README.md", "skills/property-research/references/linked.md"])
def test_selected_symlinks_are_rejected_without_reading_target(source, tmp_path, relative):
    target = tmp_path / "outside"
    target.write_text("DO_NOT_PACKAGE")
    link = source / relative
    if link.exists():
        link.unlink()
    link.symlink_to(target)
    with pytest.raises(ValueError, match="Symlink"):
        builder.build(source, tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_embedded_token_is_rejected_without_echoing_it(source, tmp_path):
    token = "rg_" + "syntheticTokenForTestOnly"
    (source / "README.md").write_text(token)
    with pytest.raises(ValueError) as caught:
        builder.build(source, tmp_path / "output")
    assert token not in str(caught.value)
    assert not (tmp_path / "output").exists()


def test_literal_header_secret_is_rejected(source, tmp_path):
    path = source / ".mcp.json"
    config = json.loads(path.read_text())
    config["mcpServers"]["regrid"]["env"]["REGRID_TOKEN"] = "synthetic-secret"
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="placeholder"):
        builder.build(source, tmp_path / "output")


def test_workflow_helper_is_shared_but_scratch_scripts_are_excluded(source, tmp_path):
    scripts = source / "skills/property-research/scripts"
    scripts.mkdir(exist_ok=True)
    (scripts / "workflow.py").write_text('"""Offline workflow helper."""\n')
    (scripts / "scratch.py").write_text("DO_NOT_PACKAGE")
    cowork, code, standalone = map(archive_contents, builder.build(source, tmp_path / "out"))
    name = "skills/property-research/scripts/workflow.py"
    assert cowork[name] == code[name] == standalone["property-research/scripts/workflow.py"]
    assert all(b"DO_NOT_PACKAGE" not in value for value in code.values())


def test_map_helper_is_shared_across_all_archives(source, tmp_path):
    cowork, code, standalone = map(archive_contents, builder.build(source, tmp_path / "out"))
    name = "skills/property-research/scripts/map.py"
    assert name in code
    assert cowork[name] == code[name] == standalone["property-research/scripts/map.py"]


def test_mcp_examples_use_current_spec_title():
    import re

    text = (
        ROOT / "plugins/regrid-research/skills/property-research/references/mcp-tools.md"
    ).read_text()
    titles = re.findall(r'"title":\s*"([^"]+)"', text)
    assert titles and all(t == "Regrid OpenAPI Specification (reference)" for t in titles)


def test_query_endpoint_notes_required_filter():
    endpoints = json.loads(
        (
            ROOT / "plugins/regrid-research/skills/property-research/references/endpoints.json"
        ).read_text()
    )
    assert "fields[<field>][<op>]" in endpoints["endpoints"]["/parcels/query"]["skill_note"]


def test_command_ships_in_plugin_archives_only(source, tmp_path):
    cowork, code, standalone = map(archive_contents, builder.build(source, tmp_path / "out"))
    assert "commands/address-map.md" in code and "commands/address-map.md" in cowork
    assert not any(name.startswith("commands/") for name in standalone)


def test_command_is_bounded_and_links_map_guide():
    text = (PLUGIN / "commands/address-map.md").read_text()
    assert text.startswith("---\n") and "argument-hint:" in text
    assert "one request" in text and "references/map.md" in text
    assert "neighbour" not in text.lower()
    assert "limit=1" in text and "US" in text
    assert "map the single returned parcel" in text and "token" in text
    assert "--all-candidates" not in text


def test_host_results_never_claim_unrun_checks():
    data = json.loads((PLUGIN / "evals/results/map-hosts-0.7.0.json").read_text())
    assert set(data["hosts"]) == {"claude_code", "claude_apps", "cowork"}
    assert set(data["hosts"].values()) <= {"verified", "failed", "not_run"}


def test_versions():
    assert json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text())["version"] == "0.7.0"
    assert regrid.__version__ == "0.2.0"


def test_premium_guide_covers_every_flag_and_requires_authorization():
    skill = (SKILL_ROOT / "SKILL.md").read_text()
    guide = (SKILL_ROOT / "references/premium.md").read_text()
    assert "references/premium.md" in skill
    for flag in (
        "return_zoning",
        "return_enhanced_ownership",
        "return_matched_buildings",
        "return_matched_addresses",
    ):
        assert flag in guide
    assert guide.lower().count("authoriz") >= 4 and "beneficial" in guide
    assert "`notes`" in guide
    assert "Premium datasets are US-only" not in guide


def test_fields_helper_and_catalog_are_shared_across_all_archives(source, tmp_path):
    cowork, code, standalone = map(archive_contents, builder.build(source, tmp_path / "out"))
    name = "skills/property-research/scripts/fields.py"
    assert cowork[name] == code[name] == standalone["property-research/scripts/fields.py"]
    catalog = "skills/property-research/references/fields.json"
    assert catalog in code


NEW_ENDPOINTS = [
    "/parcels/path",
    "/parcels/typeahead",
    "/verse",
    "/schemas/parcel",
    "/schemas/building",
    "/schemas/address",
    "/schemas/enhanced_ownership",
    "/schemas/zoning",
    "/usage/detailed",
]


def test_new_endpoints_documented():
    endpoints = json.loads((SKILL_ROOT / "references/endpoints.json").read_text())["endpoints"]
    tools = (SKILL_ROOT / "references/mcp-tools.md").read_text()
    for path in NEW_ENDPOINTS:
        assert path in endpoints and f"`{path}" in tools
    required = {p["name"] for p in endpoints["/parcels/path"]["parameters"] if p.get("required")}
    assert required == {"path"}
    assert "Enterprise" in endpoints["/parcels/typeahead"]["skill_note"]


def test_refresh_rule_never_unscoped():
    batch = (SKILL_ROOT / "references/batch.md").read_text()
    assert "/parcels/path" in batch and "never fall back to an unscoped search" in batch
