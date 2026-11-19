# Parity Batch 2 (Next): Paid-Dataset Guidance, Field Catalog, Refresh by Path, Windows CI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship small, low-risk improvements in both the skill and the CLI:
- paid-dataset guidance
- an offline field catalog (`fields.py`, `regrid fields`)
- refresh by Regrid path
- a Windows CI job

**Architecture:**
- **Field catalog:** `fields.py` joins `src/regrid/offline/`, reusing Batch 1's sync
  mechanism. A generator writes the compact `references/fields.json` from
  `src/regrid/data/parcel_fields.json`.
- **Skill references:** the skill gains `references/premium.md` and new endpoint
  entries.
- **Refresh by path:** the CLI's existing `parcel-path` covers it; this batch adds
  documentation only.

**Tech Stack:** Python 3.10+, argparse, pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-11-19-plugin-cli-parity-design.md`. Requires
Batch 1 merged (`src/regrid/offline/`, `scripts/sync_skill_helpers.py`,
`tests/test_skill_helper_sync.py`).

## Global Constraints

- All of Batch 1's Global Constraints apply: US only, standard-library-only helpers,
  no token exposure, red-green TDD, Conventional Commits with the co-author line, and
  `make check` at each task.
- `fields.py` and `fields.json` work offline and make no requests.
- Paid datasets (`return_zoning`, `return_enhanced_ownership`,
  `return_matched_buildings`, `return_matched_addresses`) are requested only with the
  user's authorization.
- Through MCP, `/schemas/*` calls count as requests, so the bundled catalog comes first.
- Versions: plugin `0.8.0`, SDK `0.3.0`.

## Review Focus

1. **Unknown field:** `regrid fields explain notafield` must return
   `{"found": [], "unknown": ["notafield"]}` with exit 0, not a traceback. The guidance
   then says to try `/schemas/parcel`. Pinned in Task 2.
2. **Search matching:** a search term that matches a description but not a name
   (`fields search "assessed"`) must find it; search is case-insensitive. Pinned in
   Task 2.
3. **Stale catalog:** if `src/regrid/data/parcel_fields.json` changes and
   `fields.json` is not regenerated, `make check` fails, naming the generator command.
   Pinned in Task 2.
4. **Refresh by path:** a saved result missing `path` must not lead to an unscoped
   lookup. The guidance says to stop and ask. Pinned in Task 3.
5. **POSIX-only tests on Windows:** the umask test is POSIX-only and must be skipped
   on Windows, with the reason stated, not failed. Pinned in Task 4.

---

### Task 1: Paid-dataset guidance (skill)

**Files:**
- Create: `plugins/regrid-research/skills/property-research/references/premium.md`
- Modify: `SKILL.md` (resource list: "Zoning, enhanced ownership, matched buildings
  or addresses requested: [premium datasets](references/premium.md)"),
  `references/mcp-tools.md` (one link line)
- Test: `tests/test_claude_plugins.py`

**Interfaces:**
- Produces: `premium.md` has one section per flag, each with:
  - what it answers
  - that it needs user authorization and may cost extra
  - how to record it in the handoff (the flag sent)

  The enhanced-ownership section repeats that recorded owner is not beneficial owner,
  unless the dataset says otherwise.

- [ ] **Step 1: Write the failing test**

```python
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
```

Here `SKILL_ROOT = ROOT / "plugins/regrid-research/skills/property-research"`.

- [ ] **Step 2: Run it** → FAIL.
- [ ] **Step 3: Write** `premium.md` (under 60 lines) and the links.
- [ ] **Step 4: Run** the test, then `make check` and
  `evals/run.py validate --suite all` → PASS.
- [ ] **Step 5: Commit** `docs: add paid-dataset guidance to property research`.

### Task 2: Offline field catalog (shared helper, skill and CLI)

**Files:**
- Create: `src/regrid/offline/fields.py`
- Create: `scripts/generate_skill_fields.py`
- Create: `plugins/regrid-research/skills/property-research/references/fields.json` (generated)
- Create (by sync): `plugins/regrid-research/skills/property-research/scripts/fields.py`
- Modify: `scripts/sync_skill_helpers.py` (`HELPERS` adds `"fields.py"`),
  `scripts/build_claude_plugins.py` (ship `fields.py`), discovery `ALLOWLIST` in
  `plugins/regrid-research/evals/discovery.py` (add `scripts/fields.py`),
  `src/regrid/cli.py` (`fields` subcommand), `SKILL.md` (resource line:
  "Field meaning: run `scripts/fields.py explain FIELD`; only fields it lacks justify a
  `/schemas/*` request")
- Test: `tests/test_offline_fields.py`, `tests/test_cli_offline.py`, `tests/test_claude_plugins.py`

**Interfaces:**
- Produces:
  - **`fields.json` format:** `{"version": <catalog version>, "country": "us",
    "fields": [{"name", "datatype", "tier", "category", "description"}]}`, sorted by
    name, `ensure_ascii=False`, indent 1.
  - **`fields.py` functions:**
    - `load_catalog(path: Path) -> list[dict]` accepts either this compact format or
      the full `parcel_fields.json`.
    - `explain(catalog: list[dict], names: list[str]) -> dict` returns
      `{"found": [...], "unknown": [...]}`.
    - `search(catalog, term: str) -> list[dict]` matches name, description or
      category, case-insensitive, in name order.
  - **`fields.py` CLI:** `python3 fields.py explain NAME... [--catalog PATH]` and
    `python3 fields.py search TERM [--catalog PATH]`. The default catalog is
    `../references/fields.json` relative to the script. Output is JSON on stdout,
    exit 0.
  - **`regrid fields explain NAME...` / `regrid fields search TERM`:** the same output,
    using the package's `parcel_fields.json` via `importlib.resources`. Offline; no
    client.
  - **Generator:** `scripts/generate_skill_fields.py [--check]` exits 1 with
    `fields.json is stale; run python scripts/generate_skill_fields.py` when stale.

- [ ] **Step 1: Write the failing tests**

```python
def test_explain_known_and_unknown():
    catalog = fields.load_catalog(SKILL_FIELDS)
    result = fields.explain(catalog, ["owner", "notafield"])
    assert [f["name"] for f in result["found"]] == ["owner"] and result["unknown"] == ["notafield"]


def test_search_matches_description_case_insensitive():
    hits = fields.search(fields.load_catalog(SKILL_FIELDS), "ASSESSED")
    assert hits and all(
        "assessed" in (h["name"] + h["description"] + h["category"]).lower() for h in hits
    )


def test_compact_and_full_catalogs_agree():
    compact = fields.load_catalog(SKILL_FIELDS)
    full = fields.load_catalog(ROOT / "src/regrid/data/parcel_fields.json")
    assert [f["name"] for f in compact] == sorted(f["name"] for f in full)
    assert len(compact) == 169


def test_skill_catalog_is_current():
    assert generator.main(["--check"]) == 0


def test_regrid_fields_cli(capsys):
    assert cli.main(["fields", "explain", "owner", "zzz"]) == 0
    assert json.loads(capsys.readouterr().out)["unknown"] == ["zzz"]


def test_fields_helper_runs_from_extracted_archive(tmp_path):
    ...  # same pattern as test_extracted_map_helper_renders: extract the standalone ZIP,
    # run `python -I scripts/fields.py explain owner` from the extracted dir, assert found
```

- [ ] **Step 2: Run them** → FAIL.
- [ ] **Step 3: Implement.**
  - Write the generator, `fields.py`, the sync entry, the CLI subcommand (dispatched
    with Batch 1's offline handlers), the build entry and the allowlist entry.
  - Run the generator and the sync.
- [ ] **Step 4: Run** the tests, then `make check`, the build, and
  `claude plugin validate --strict` → PASS.
- [ ] **Step 5: Commit** `feat: add offline parcel field catalog to skill and CLI`.

### Task 3: Refresh by path and new endpoint references

**Files:**
- Modify: `references/endpoints.json` (add `/parcels/path`, `/parcels/typeahead`,
  `/verse`, `/schemas/parcel`, `/schemas/building`, `/schemas/address`,
  `/schemas/enhanced_ownership`, `/schemas/zoning`, `/usage/detailed` in the existing
  per-endpoint format; parameters come from free `get-endpoint` documentation calls
  with no token)
- Modify: `references/mcp-tools.md` (endpoint table rows: Regrid path → `/parcels/path`,
  `path` required; address suggestions → `/parcels/typeahead`, `query` required,
  Enterprise only; county pull dates → `/verse`, every county per call; field
  definitions → `/schemas/*`, no token but counts as a request)
- Modify: `references/batch.md` (refresh rule)
- Modify: root `README.md` (CLI example:
  `regrid parcel-path /us/nj/camden/haddonfield/123 --options '{"return_parcels":true}'`)
- Test: `tests/test_claude_plugins.py`

**Interfaces:**
- Produces:
  - **`batch.md` refresh rule:** "An explicit refresh of a saved result uses
    `/parcels/path` with the saved `path`: one request, one record. If the saved
    result has no `path`, stop and ask; never fall back to an unscoped search."
  - **`endpoints.json`:** the `/parcels/typeahead` entry carries a `skill_note` saying
    it is Enterprise-only and that trial tokens cover 7 counties. The `/verse` entry
    notes it returns all counties.

- [ ] **Step 1: Write the failing test**

```python
NEW = [
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
    for path in NEW:
        assert path in endpoints and f"`{path}" in tools
    required = {p["name"] for p in endpoints["/parcels/path"]["parameters"] if p.get("required")}
    assert required == {"path"}
    assert "Enterprise" in endpoints["/parcels/typeahead"]["skill_note"]


def test_refresh_rule_never_unscoped():
    batch = (SKILL_ROOT / "references/batch.md").read_text()
    assert "/parcels/path" in batch and "never fall back to an unscoped search" in batch
```

- [ ] **Step 2: Run it** → FAIL.
- [ ] **Step 3: Implement.** Fetch the parameters with documentation-only MCP calls
  (no token, no `execute-request`) and write the docs.
- [ ] **Step 4: Run** `make check` → PASS.
- [ ] **Step 5: Commit** `docs: document refresh by path and newly covered endpoints`.

### Task 4: Windows CI job

**Files:**
- Modify: `.github/workflows/ci.yml` (add a `windows` job: `windows-latest`, Python
  3.12, `pip install uv`, `uv sync --extra dev` (match `make install`), then
  `uv run pytest tests/test_regrid_map.py tests/test_regrid_workflow.py
  tests/test_regrid_workflow_composition.py tests/test_skill_helper_sync.py
  tests/test_cli_offline.py tests/test_offline_fields.py`. Pin actions to the same SHAs
  as the existing job.)
- Modify: tests that are POSIX-only (`test_output_respects_umask`, and any others the
  first Windows run reveals) to use
  `pytest.mark.skipif(os.name == "nt", reason="POSIX permissions")`.
- Test: `tests/test_ci_config.py`

**Interfaces:**
- Produces: a CI job named `windows` that must pass on PRs.

- [ ] **Step 1: Write the failing test**

```python
def test_windows_job_runs_offline_helper_tests():
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "windows-latest" in ci
    for name in ("test_regrid_map.py", "test_skill_helper_sync.py", "test_offline_fields.py"):
        assert name in ci
```

- [ ] **Step 2: Run it** → FAIL.
- [ ] **Step 3: Add the job and the skip markers.**
- [ ] **Step 4: Run** `make check` locally → PASS. Push the branch and confirm the
  `windows` job is green.
  - Fix real Windows failures in `src/regrid/offline/` (then re-sync); don't skip them.
  - Report the CI result in the PR. If CI can't run, say so.
- [ ] **Step 5: Commit** `ci: run offline helper tests on Windows`.

### Task 5: Versions and changelog

- [ ] **Bump versions:** plugin to `0.8.0` and SDK to `0.3.0`. Update the changelog
  (Added: field catalog, `regrid fields`, paid-dataset guidance, refresh by path;
  Changed: Windows CI) and tick the items in `todos.md`.
- [ ] **Update the version test:** change the `test_versions` expectations in
  `tests/test_claude_plugins.py` first (red), then bump (green).
- [ ] **Run checks:**
  - `make check`
  - `make e2e`
  - the build
  - `evals/run.py validate --suite all`
  - `claude plugin validate --strict`
- [ ] **Commit** `chore: release Regrid Research 0.8.0 and SDK 0.3.0`.
