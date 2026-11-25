"""Packaging must preserve shared skills while keeping transport and secrets separate."""

import importlib.util
import json
import os
import re
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
    (references / "packaging-test.md").write_text(
        "Reference used by the skill.\n", encoding="utf-8"
    )
    return path


def archive_contents(path):
    with ZipFile(path) as archive:
        assert archive.testzip() is None
        return {name: archive.read(name) for name in archive.namelist()}


@pytest.fixture(scope="module")
def packaged_archives(tmp_path_factory):
    paths = builder.build(PLUGIN, tmp_path_factory.mktemp("packaged"))
    return tuple(map(archive_contents, paths))


def test_transports_share_complete_skill_and_build_reproducibly(source, tmp_path):
    paths = builder.build(source, tmp_path / "first")
    cowork, code, skill = map(archive_contents, paths)
    assert json.loads(cowork[".mcp.json"]) == {
        "mcpServers": {"regrid": {"type": "http", "url": "https://support.regrid.com/mcp"}}
    }
    server = json.loads(code[".mcp.json"])["mcpServers"]["regrid"]
    assert server == {
        "type": "http",
        "url": "https://support.regrid.com/mcp",
        "headers": {"x-regrid-token": "${REGRID_TOKEN}"},
    }
    assert not {"command", "args", "env"} & set(server)
    assert "npx" not in code[".mcp.json"].decode()
    assert set(cowork) == set(code)
    for name in cowork:
        if name != ".mcp.json":
            assert cowork[name] == code[name]
    for name, content in skill.items():
        assert name.startswith("property-research/")
        if name != "property-research/LICENSE":
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
        (source / relative).write_text("DO_NOT_PACKAGE", encoding="utf-8")
    paths = builder.build(source, tmp_path / "output")
    assert len(paths) == 3
    for path in paths:
        contents = archive_contents(path)
        assert any(name.endswith("property-research/SKILL.md") for name in contents), path
        assert all(b"DO_NOT_PACKAGE" not in data for data in contents.values())
        assert not any(
            name.rsplit("/", 1)[-1] in {".env", "credentials.json", "scratch.md", "debug.log"}
            for name in contents
        )


@pytest.mark.skipif(os.name == "nt", reason="symlinks need privilege on Windows")
@pytest.mark.parametrize("relative", ["README.md", "skills/property-research/references/linked.md"])
def test_selected_symlinks_are_rejected_without_reading_target(source, tmp_path, relative):
    target = tmp_path / "outside"
    target.write_text("DO_NOT_PACKAGE", encoding="utf-8")
    link = source / relative
    if link.exists():
        link.unlink()
    link.symlink_to(target)
    with pytest.raises(ValueError, match="Symlink"):
        builder.build(source, tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_embedded_token_is_rejected_without_echoing_it(source, tmp_path):
    token = "rg_" + "syntheticTokenForTestOnly"
    (source / "README.md").write_text(token, encoding="utf-8")
    with pytest.raises(ValueError) as caught:
        builder.build(source, tmp_path / "output")
    assert str(caught.value) == "Possible credential in package file: README.md"
    assert token not in str(caught.value)
    assert not (tmp_path / "output").exists()


def test_literal_header_secret_is_rejected(source, tmp_path):
    path = source / ".mcp.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    config["mcpServers"]["regrid"]["headers"]["x-regrid-token"] = "synthetic-secret"
    path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ValueError, match="placeholder"):
        builder.build(source, tmp_path / "output")


def test_workflow_helper_is_shared_but_scratch_scripts_are_excluded(source, tmp_path):
    scripts = source / "skills/property-research/scripts"
    scripts.mkdir(exist_ok=True)
    (scripts / "workflow.py").write_text('"""Offline workflow helper."""\n', encoding="utf-8")
    (scripts / "scratch.py").write_text("DO_NOT_PACKAGE", encoding="utf-8")
    cowork, code, standalone = map(archive_contents, builder.build(source, tmp_path / "out"))
    name = "skills/property-research/scripts/workflow.py"
    assert cowork[name] == code[name] == standalone["property-research/scripts/workflow.py"]
    assert all(b"DO_NOT_PACKAGE" not in value for value in code.values())


def test_map_helper_is_shared_across_all_archives(packaged_archives):
    cowork, code, standalone = packaged_archives
    name = "skills/property-research/scripts/map.py"
    assert name in code
    assert cowork[name] == code[name] == standalone["property-research/scripts/map.py"]


def test_mcp_examples_use_current_spec_title():
    text = (
        ROOT / "plugins/regrid-research/skills/property-research/references/mcp-tools.md"
    ).read_text(encoding="utf-8")
    titles = re.findall(r'"title":\s*"([^"]+)"', text)
    assert titles and all(t == "Regrid OpenAPI Specification (reference)" for t in titles)


def test_query_endpoint_notes_required_filter():
    endpoints = json.loads(
        (
            ROOT / "plugins/regrid-research/skills/property-research/references/endpoints.json"
        ).read_text(encoding="utf-8")
    )
    assert "fields[<field>][<op>]" in endpoints["endpoints"]["/parcels/query"]["skill_note"]


def test_command_ships_in_plugin_archives_only(packaged_archives):
    cowork, code, standalone = packaged_archives
    assert "commands/address-map.md" in code and "commands/address-map.md" in cowork
    assert not any(name.startswith("commands/") for name in standalone)


def test_command_is_bounded_and_links_map_guide():
    text = (PLUGIN / "commands/address-map.md").read_text(encoding="utf-8")
    assert text.startswith("---\n") and "argument-hint:" in text
    assert "one request" in text and "references/map.md" in text
    assert "neighbour" in text.lower() and "up to 25 records" in text
    assert "limit=1" in text and "US" in text
    assert "map the single returned parcel" in text and "token" in text
    assert "--all-candidates" not in text


def test_host_results_never_claim_unrun_checks():
    files = sorted((PLUGIN / "evals/results").glob("map-hosts-*.json"))
    assert len(files) >= 2
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        assert set(data) == {"plugin_version", "hosts", "notes"}, path.name
        assert set(data["hosts"]) == {"claude_code", "claude_apps", "cowork"}
        assert set(data["hosts"].values()) <= {"verified", "failed", "not_run"}


def test_versions():
    assert (
        json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))["version"]
        == "0.9.6"
    )
    assert regrid.__version__ == "0.4.5"


def test_premium_guide_covers_every_flag_and_requires_authorization():
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    guide = (SKILL_ROOT / "references/premium.md").read_text(encoding="utf-8")
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


def test_fields_helper_and_catalog_are_shared_across_all_archives(packaged_archives):
    cowork, code, standalone = packaged_archives
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
    endpoints = json.loads((SKILL_ROOT / "references/endpoints.json").read_text(encoding="utf-8"))[
        "endpoints"
    ]
    tools = (SKILL_ROOT / "references/mcp-tools.md").read_text(encoding="utf-8")
    for path in NEW_ENDPOINTS:
        assert path in endpoints and f"`{path}" in tools
    required = {p["name"] for p in endpoints["/parcels/path"]["parameters"] if p.get("required")}
    assert required == {"path"}
    assert "Enterprise" in endpoints["/parcels/typeahead"]["skill_note"]


def test_refresh_rule_never_unscoped():
    batch = (SKILL_ROOT / "references/batch.md").read_text(encoding="utf-8")
    assert "/parcels/path" in batch and "never fall back to an unscoped search" in batch


def test_cli_freshness_neighbours_and_suggestions_guidance():
    refs = SKILL_ROOT / "references"
    cli = (refs / "cli.md").read_text(encoding="utf-8")
    assert "requests made" in cli and "ll_last_refresh" in cli
    assert "record_limit" in (refs / "batch.md").read_text(encoding="utf-8")
    assert "cli.md" in (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    map_guide = (refs / "map.md").read_text(encoding="utf-8")
    for text in ("radius=100", "limit=25", "up to 25 records", "--neighbours"):
        assert text in map_guide
    tools = (refs / "mcp-tools.md").read_text(encoding="utf-8")
    assert "/parcels/typeahead" in tools and "never retried" in tools
    assert "requests made" in (refs / "batch.md").read_text(encoding="utf-8")


def test_neighbours_and_suggestions_are_ledger_accounted():
    refs = SKILL_ROOT / "references"
    for text in (
        (refs / "map.md").read_text(encoding="utf-8"),
        (PLUGIN / "commands/address-map.md").read_text(encoding="utf-8"),
    ):
        assert "batch.md" in text
    batch = (refs / "batch.md").read_text(encoding="utf-8")
    assert "record_limit 25" in batch and "uncertain" in batch
    assert "authorized_retry=True" in batch and "no workflow ledger" in batch
    assert "## CLI and suggestion requests" in batch
    assert "typeahead" in batch and "record_limit 1" in batch
    for line in (refs / "mcp-tools.md").read_text(encoding="utf-8").splitlines():
        assert len(line) <= 100 or line.startswith("|")


def test_cli_path_paging_schema_usage_and_export_guidance():
    refs = SKILL_ROOT / "references"
    tools = (refs / "mcp-tools.md").read_text(encoding="utf-8")
    cli = (refs / "cli.md").read_text(encoding="utf-8")
    rows = [
        line for line in tools.split("## Choosing the endpoint")[1].splitlines() if "| `/" in line
    ]
    assert len(rows) >= 13
    for row in rows:
        for path in re.findall(r"`(/[^`]+)`", row.split("|")[2]):
            assert f"`{path}`" in cli.split("## Command map")[1].split("\n## ")[0], path
    assert "requests made" in cli and "never read `.env`" in cli
    assert "CLI-only" in cli
    assert "/usage/detailed" in tools and "never per-token" in tools
    assert "fields.py" in tools and "one request each" in tools
    assert 'map.py" export' in (refs / "map.md").read_text(encoding="utf-8")
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert 'map.py" export' in skill and "return_count" in (refs / "batch.md").read_text(
        encoding="utf-8"
    )
    assert "not saved in checkpoints" in (refs / "batch.md").read_text(encoding="utf-8")
    assert "CLI" in (PLUGIN / "skills/setup/SKILL.md").read_text(encoding="utf-8")


SKILL_FILES = [SKILL_ROOT / "SKILL.md", PLUGIN / "skills/setup/SKILL.md"]
DOC_FILES = [*SKILL_FILES, *(SKILL_ROOT / "references").glob("*.md"), *PLUGIN.glob("commands/*.md")]


def test_every_reference_is_linked_directly_from_skill():
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    refs = [p for p in (SKILL_ROOT / "references").iterdir() if p.suffix in {".md", ".json"}]
    assert (SKILL_ROOT / "references/answers.md") in refs
    for ref in refs:
        assert f"](references/{ref.name}" in skill, ref.name


def test_skill_is_a_short_routing_page():
    assert len((SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8").split()) < 950


def test_budget_rules_have_one_authoritative_copy():
    batch = (SKILL_ROOT / "references/batch.md").read_text(encoding="utf-8")
    assert "## Default budgets" in batch and "## Neighbour requests" in batch
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert "reserve possible records" not in skill and "attempted_requests" not in skill


def test_mcp_tools_has_toc_and_dated_facts_only_in_history():
    text = (SKILL_ROOT / "references/mcp-tools.md").read_text(encoding="utf-8")
    head, _, history = text.partition("## Observed history")
    assert "## Contents" in head and history
    assert "November" not in head and "October" not in head
    assert not re.search(r"\b20\d\d-\d\d-\d\d\b", head)
    assert "plus return_stacked=false and the same four false premium flags" in " ".join(
        text.split()
    )
    assert "POST point and POST area with `return_parcels=true`" in history
    assert "over MCP remains unverified" in history


def test_setup_declares_property_research_dependency():
    assert "requires the property-research skill" in (PLUGIN / "skills/setup/SKILL.md").read_text(
        encoding="utf-8"
    )


def test_consistent_terminology():
    for path in DOC_FILES:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"(?i)\bneighbors?\b", text), path
        assert "paid dataset" not in text.lower(), path


def test_skill_descriptions_are_third_person_and_bounded():
    for path in SKILL_FILES:
        desc = re.search(r"^description: (.+)$", path.read_text(encoding="utf-8"), re.M).group(1)
        assert len(desc) <= 1024, path
        assert "Use when" in desc or "Use for" in desc, path
        assert not re.search(r"(?i)\b(i|you|your|my)\b", desc), path
    research = (
        re.search(r"^description: (.+)$", SKILL_FILES[0].read_text(encoding="utf-8"), re.M)
        .group(1)
        .lower()
    )
    for word in ("map", "satellite", "boundar", "export", "csv", "geojson"):
        assert word in research, word
    setup = (
        re.search(r"^description: (.+)$", SKILL_FILES[1].read_text(encoding="utf-8"), re.M)
        .group(1)
        .lower()
    )
    assert "tools" in setup and "auth" in setup


def test_map_present_step_states_match_status_with_page_path():
    map_guide = (SKILL_ROOT / "references/map.md").read_text(encoding="utf-8")
    assert "match status" in map_guide
    assert "candidates, not confirmed" in map_guide


def test_county_freshness_is_cli_only_over_mcp():
    tools = (SKILL_ROOT / "references/mcp-tools.md").read_text(encoding="utf-8")
    verse_row = next(
        line for line in tools.splitlines() if line.startswith("| County pull dates | `/verse`")
    )
    assert "CLI only" in verse_row and "ll_last_refresh" in verse_row
    skill_lines = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8").splitlines()
    cli_line = next(line for line in skill_lines if "cli.md" in line)
    assert "county pull dates" in cli_line.lower()
    assert "CLI only" in cli_line


def test_cli_is_the_fallback_route_and_freshness_script_is_routed():
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert "ZIP or city/state" in skill
    cli_line = next(line for line in skill.splitlines() if "cli.md" in line)
    for word in ("MCP", "export", "tiles"):
        assert word in cli_line
    cli = (SKILL_ROOT / "references/cli.md").read_text(encoding="utf-8")
    assert 'scripts/freshness.py" county VERSE.json --path /us/<st>/<county>' in cli
    description = skill.split("---")[1]
    assert "reports county data freshness." in description
    assert "supplied saved `/verse` file" in skill
    batch = (SKILL_ROOT / "references/batch.md").read_text(encoding="utf-8")
    assert "with the actual\n  outcome" in batch and "uncertain" in batch
    assert "MCP `/parcels/typeahead`: returns no parcel records" not in batch


def test_plugin_license_is_mit_and_identical_to_repo_license():
    assert (PLUGIN / "LICENSE").read_bytes() == (ROOT / "LICENSE").read_bytes()
    manifest = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    assert manifest["license"] == "MIT"


def test_builder_reads_license_from_source_directory(source, tmp_path):
    (source / "LICENSE").write_bytes(b"source license\n")
    cowork, code, skill = map(archive_contents, builder.build(source, tmp_path / "out"))
    assert cowork["LICENSE"] == code["LICENSE"] == skill["property-research/LICENSE"]
    assert code["LICENSE"] == b"source license\n"


def test_license_ships_in_every_archive_identical_to_repo_license(packaged_archives):
    license_text = (ROOT / "LICENSE").read_bytes()
    cowork, code, skill = packaged_archives
    assert cowork["LICENSE"] == code["LICENSE"] == license_text
    assert skill["property-research/LICENSE"] == license_text
    assert "LICENSE" not in skill


def test_manifest_carries_distribution_metadata():
    manifest = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    assert manifest["license"] == "MIT"
    assert manifest["repository"] == "https://github.com/domfahey/regrid"
    assert manifest["homepage"] == (
        "https://github.com/domfahey/regrid/tree/main/plugins/regrid-research"
    )


def test_shipped_readme_leads_with_current_status_and_omits_history():
    readme = (PLUGIN / "README.md").read_text(encoding="utf-8")
    section = readme.split("## Validation and acceptance", 1)[1]
    assert section.lstrip().startswith("Status for 0.9.6")
    assert "Historical 0.4.0" not in readme
    assert "Historical 0.3.0" not in readme
    history = (PLUGIN / "evals/README.md").read_text(encoding="utf-8")
    assert "## Historical verification" in history
    assert "Historical 0.2.0 verification" in history
    assert "results/map-hosts-0.9.6.json" in history
    assert "map-hosts-0.7.0.json" not in history


def test_descriptions_state_exclusions():
    for path, words in (
        (SKILL_FILES[0], ("batch", "data-issue", "appraisal", "legal ownership")),
        (SKILL_FILES[1], ("property lookup",)),
    ):
        desc = (
            re.search(r"^description: (.+)$", path.read_text(encoding="utf-8"), re.M)
            .group(1)
            .lower()
        )
        assert "do not use for" in desc, path
        for word in words:
            assert word in desc, (path, word)
    assert "non-us" not in re.search(
        r"do not use for.*", SKILL_FILES[0].read_text(encoding="utf-8").lower()
    ).group(0)


def test_skill_md_defines_skill_path_and_hides_fields_json():
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert "`<skill>`" in skill and "contains `SKILL.md`" in skill
    assert 'python3 "<skill>/scripts/fields.py" explain' in skill
    assert "don't open it" in skill and "](references/fields.json)" in skill


def test_one_script_path_convention():
    for path in DOC_FILES:
        text = path.read_text(encoding="utf-8")
        assert "/path/to/property-research" not in text, path
        assert "../scripts/" not in text, path
        assert not re.search(r"python3 scripts/", text), path
    for path in DOC_FILES:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"python3 <skill>/", text), path
        assert not re.search(r"python3 \$\{CLAUDE_PLUGIN_ROOT\}", text), path
        for match in re.finditer(r"python3 (\S+\.py\S*)", text):
            assert re.fullmatch(r'"<skill>/scripts/(?:[a-z_]+|<name>)\.py"', match.group(1)), (
                path,
                match.group(1),
            )


def test_command_uses_skill_prefixed_paths_and_states_hosts():
    text = (PLUGIN / "commands/address-map.md").read_text(encoding="utf-8")
    assert "`${CLAUDE_PLUGIN_ROOT}/skills/property-research`" in text
    # Quotes belong at the call site only; a quoted definition would nest quotes there.
    assert '"${CLAUDE_PLUGIN_ROOT}' not in text
    assert "elsewhere it is\nthe property-research skill folder" in text
    assert 'python3 "<skill>/scripts/map.py" render' in text
    assert not re.search(r"(?<!<skill>/)(?<![\w/.-])(scripts|references)/", text)
    assert "Claude Code and Cowork only" in (SKILL_ROOT / "references/map.md").read_text(
        encoding="utf-8"
    )


def test_skill_keeps_public_docs_vs_auth_rule():
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert "does not establish authenticated parcel access" in " ".join(skill.split())


def test_manifest_has_privacy_policy_url_and_privacy_note_ships(packaged_archives):
    manifest = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    assert manifest["privacyPolicyUrl"] == (
        "https://github.com/domfahey/regrid/blob/main/plugins/regrid-research/PRIVACY.md"
    )
    note = (PLUGIN / "PRIVACY.md").read_bytes()
    cowork, code, skill = packaged_archives
    assert cowork["PRIVACY.md"] == code["PRIVACY.md"] == note
    assert b"https://regrid.com/terms/privacy" in note


def test_token_pattern_ignores_identifiers_but_catches_tokens(tmp_path):
    root = tmp_path / "pk"
    root.mkdir()
    (root / "ok.md").write_text("org_default_value and my_rg_something_long\n", encoding="utf-8")
    assert (
        builder.read_public_file(root, "ok.md") == b"org_default_value and my_rg_something_long\n"
    )
    for text in ("key rg_abcdefgh12345", "(rg_abcdefgh12345)", "rg_abcdefgh12345"):
        (root / "bad.md").write_text(text, encoding="utf-8")
        with pytest.raises(ValueError, match="credential"):
            builder.read_public_file(root, "bad.md")


@pytest.mark.parametrize("kind", ["", "RSA ", "EC ", "OPENSSH ", "ENCRYPTED ", "PGP "])
def test_private_key_blocks_are_rejected(tmp_path, kind):
    suffix = " BLOCK" if kind == "PGP " else ""
    (tmp_path / "k.md").write_text(f"-----BEGIN {kind}PRIVATE KEY{suffix}-----\n", encoding="utf-8")
    with pytest.raises(ValueError, match="credential"):
        builder.read_public_file(tmp_path, "k.md")


def test_paging_and_refresh_guidance_match_the_workflow_helper():
    refs = SKILL_ROOT / "references"
    batch = (refs / "batch.md").read_text(encoding="utf-8")
    assert (
        "K = ceil(N / limit) requests and N records" in batch
        and "authorized_retry=True" in batch.split("Paged searches")[1].split("## Neighbour")[0]
    )
    assert "refresh" in batch.split("## Resume")[1] and (
        "authorized_retry=True" in batch.split("An explicit refresh")[1][:600]
    )
    cli = (refs / "cli.md").read_text(encoding="utf-8")
    assert cli.count('"limit":1') >= 4 and "return_stacked" in cli


def test_hidden_and_secret_command_files_are_excluded(source, tmp_path):
    commands = source / "commands"
    (commands / ".hidden.md").write_text("DO_NOT_PACKAGE", encoding="utf-8")
    (commands / "secrets.md").write_text("DO_NOT_PACKAGE", encoding="utf-8")
    (commands / "credentials-extra.md").write_text("DO_NOT_PACKAGE", encoding="utf-8")
    cowork, code, standalone = map(archive_contents, builder.build(source, tmp_path / "out"))
    for archive in (cowork, code):
        assert "commands/address-map.md" in archive
        assert "commands/.hidden.md" not in archive
        assert "commands/secrets.md" not in archive
        assert "commands/credentials-extra.md" not in archive
    assert not any(name.startswith("commands/") for name in standalone)
