# Parity Batch 4 (Later): Count and Paging, Schema Explanations, Detailed Usage, Tiles Note, Export, CLI Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the audit:
- bounded paging (`--max-records`) and count-first guidance
- schema-backed field explanations
- detailed usage guidance
- the tiles note
- CSV and GeoJSON export in both the skill and the CLI
- the full CLI path for the skill in Claude Code

**Architecture:**
- **Export:** a `map.py export` subcommand reuses the map's validation and atomic
  writes. `regrid export` wraps it.
- **Paging:** `--max-records` is a CLI loop over `offset_id` with a precomputed request
  ceiling.
- **Request summaries:** every API-calling CLI command now prints
  `regrid: requests made: N`, so the skill's CLI path can account for each call.

**Tech Stack:** Python 3.10+, `csv`, argparse, pytest, `httpx.MockTransport`.

**Spec:** `docs/superpowers/specs/2026-11-19-plugin-cli-parity-design.md` ("Builder
questions settled" 3 and 8; Export decision). Requires Batches 1–3 merged.

## Global Constraints

- All of Batch 1's Global Constraints apply.
- **Export:**
  - **CSV core columns, in order:** `headline`, `path`, `ll_uuid`, `owner`,
    `parcelnumb`, `ll_last_refresh`, `ll_gisacre`, `ll_gissqft`, `lat`, `lon`.
  - **`--all-fields`:** appends every other field name, sorted.
  - **Values:** missing values are empty. A cell starting with `=`, `+`, `-` or `@`
    gets a `'` prefix.
  - **GeoJSON:** a `FeatureCollection` of validated features, with geometry verbatim
    and only the core properties.
  - **Requests:** no extra requests.
- **Paging:**
  - Requires `limit` in `--options`. Before the first request, print
    `regrid: up to K requests for N records` (K = ceil(N / limit)).
  - The cursor is the last feature's top-level `id` (unverified live; the spec says
    "ID from a previous query exceeding the limit").
  - Stop at N records, at a short page, or when a cursor is missing (print
    `regrid: paging stopped: no cursor in response`).
  - Output: one JSON object `{"parcels": {"type": "FeatureCollection", "features":
    [...]}, "pages": P}`.
- **Paging scope:** paging positions are not saved in checkpoints. A resumed open-ended
  search needs fresh authorization.
- **Request summaries:** every CLI command that calls the API ends stderr with
  `regrid: requests made: N`. Stdout JSON stays unchanged.
- **Versions:** plugin `0.10.0`, SDK `0.5.0`.

## Review Focus

1. **`--max-records` without `limit`:** must exit 1 before any request with
   `--max-records requires an explicit limit in --options`. Pinned in Task 2.
2. **Repeated cursor:** an API that keeps returning the same cursor must stop after
   K requests at most, never loop forever. Pinned in Task 2.
3. **Formula cells:** an owner name such as `=HYPERLINK(...)` must be written as
   `'=HYPERLINK(...)` in the CSV. Pinned in Task 1.
4. **Unicode and commas:** names with commas, quotes, newlines or non-ASCII characters
   must round-trip through `csv.reader` unchanged, apart from the formula prefix.
   Pinned in Task 1.
5. **Request summary on errors:** an HTTP error on an existing command such as
   `regrid apn` must still print `requests made: 1` to stderr, so the skill ledger stays
   accurate. Pinned in Task 3.

---

### Task 1: Export (shared helper and `regrid export`)

**Files:**
- Modify: `src/regrid/offline/map.py` (add `export` subcommand and
  `export(response_path, *, csv_path=None, geojson_path=None, all_fields=False,
  replace=False) -> dict`), then sync
- Modify: `src/regrid/cli.py` (`export RESPONSE [--csv F] [--geojson F] [--all-fields]
  [--replace]`, offline)
- Test: `tests/test_regrid_map.py`, `tests/test_cli_offline.py`

**Interfaces:**
- Produces:
  - `export` returns `{"features": n, "csv": path|None, "geojson": path|None,
    "columns": [...]}`.
  - At least one of `--csv` or `--geojson` is required; otherwise MapError
    `Choose --csv and/or --geojson`.
  - It validates every feature before writing anything, using the existing
    `validate_geometry` and the US path check.

- [ ] **Step 1: Write the failing tests**

```python
def test_csv_core_columns_and_formula_guard(tmp_path):
    f = good_feature(owner='=HYPERLINK("x")', parcelnumb='1,2 "q"\nz', lat="39.9", lon="-75.03")
    summary = parcel_map.export(write_response(tmp_path / "r.json", f), csv_path=tmp_path / "o.csv")
    rows = list(csv.reader((tmp_path / "o.csv").open(encoding="utf-8", newline="")))
    assert rows[0] == CORE_COLUMNS
    assert rows[1][3] == '\'=HYPERLINK("x")' and rows[1][4] == '1,2 "q"\nz'


def test_all_fields_appends_sorted(tmp_path): ...
def test_geojson_keeps_geometry_verbatim(tmp_path):
    f = good_feature()
    parcel_map.export(write_response(tmp_path / "r.json", f), geojson_path=tmp_path / "o.geojson")
    out = json.loads((tmp_path / "o.geojson").read_text())
    assert out["type"] == "FeatureCollection" and out["features"][0]["geometry"] == f["geometry"]


def test_export_refuses_overwrite_and_invalid_before_writing(tmp_path): ...
def test_regrid_export_cli_offline(tmp_path, monkeypatch): ...  # no client constructed
```

- [ ] **Step 2: Run them** → FAIL.
- [ ] **Step 3: Implement.** Use `csv.writer` with `lineterminator="\r\n"` and UTF-8
  with BOM (`utf-8-sig`) so Excel opens it correctly. Write through the existing
  atomic writer, then sync.
- [ ] **Step 4: Run** the tests, then `make check` → PASS.
- [ ] **Step 5: Commit** `feat: export parcel responses to CSV and GeoJSON`.

### Task 2: `--max-records` paging (CLI)

**Files:**
- Modify: `src/regrid/cli.py` (flag on `owner`, `area`, `point`, `query`; only GET
  forms, since POST point has no `offset_id`)
- Test: `tests/test_cli_paging.py`

**Interfaces:**
- Produces: the loop and output defined in the Global Constraints. It passes
  `offset_id=<cursor>` on each later request.

- [ ] **Step 1: Write the failing tests:**
  - **Normal paging:** three pages of 2 records with cursors 10 and 20, and
    `--max-records 5 --options '{"limit":2}'`. Expect 3 requests, 5 features, the
    second and third requests carrying `offset_id` 10 and 20, and stderr containing
    `up to 3 requests for 5 records` and `requests made: 3`.
  - **No `limit`:** exits 1 with 0 requests (Review Focus 1).
  - **Repeated cursor:** stops at K (Review Focus 2).
  - **Missing cursor:** stops early with the message.
  - **POST point:** `--method POST` with `--max-records` exits 1 before any request.
- [ ] **Step 2: Run them** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the tests, then `make check` → PASS.
- [ ] **Step 5: Commit** `feat: add bounded --max-records paging to search commands`.

### Task 3: Request summary on every API command

**Files:**
- Modify: `src/regrid/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Produces: a counter around the client's transport (an httpx event hook) that counts
  requests actually sent. `main` prints `regrid: requests made: N` as the last stderr
  line for every non-offline command, on success and on error. Stdout is unchanged.

- [ ] **Step 1: Write the failing tests:**
  - **Parametrized success:** extend the existing parametrized CLI test to assert the
    summary line with N = 1.
  - **Error case:** add the Review Focus 5 test, an `apn` command with an HTTP 500 that
    still prints `requests made: 1`.
  - **Tile download:** `tile` counts 1.
  - **Grid fetch:** `grid` counts its actual requests.
- [ ] **Step 2: Run them** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the tests, then `make check` and `make e2e` → PASS.
- [ ] **Step 5: Commit** `feat: report requests made on every CLI API command`.

### Task 4: Skill guidance (count first, paging, schemas, detailed usage, tiles, export, full CLI path)

**Files:**
- Modify: `SKILL.md` (search budgets: optional `return_count` call, which is one
  request and zero records, before open-ended searches; paging within the agreed budget
  and only within one task; export line)
- Modify: `references/batch.md` (paging is not saved in checkpoints; resumed
  open-ended searches need fresh authorization)
- Modify: `references/cli.md`:
  - **Executor:** the full CLI path for every lookup when MCP is unavailable or files
    are needed.
  - **Command map:** each MCP endpoint and its `regrid` command.
  - **Ledger:** reserve before, complete from `requests made: N`, and treat an
    unreadable line as uncertain.
  - **Tiles:** tile commands are CLI-only and never go in the map page.
- Modify: `references/mcp-tools.md`:
  - **Schemas:** `/schemas/*` only after `fields.py` lacks the field, one request each.
  - **Detailed usage:** `/usage/detailed` only for "how many lookups are left"
    questions, never per-token breakdowns.
- Modify: `references/map.md` (export section: `map.py export` from the saved response,
  with no extra requests)
- Modify: `plugins/regrid-research/skills/setup/SKILL.md` (mention the CLI path as an
  alternative when MCP is unavailable in Claude Code)
- Test: `tests/test_claude_plugins.py`, `tests/test_regrid_workflow_composition.py`

**Interfaces:**
- Produces: the docs described above.
- **Composition test:** a paged search of 3 pages is reserved as 3 attempts with
  `record_limit` equal to the page limit, and the ledger validates. Use the existing
  workflow API; no schema change.

- [ ] **Step 1: Write the failing tests:**
  - **Doc assertions:**
    - `cli.md` maps every endpoint in the `mcp-tools.md` table to a `regrid` command.
    - `cli.md` contains "requests made" and "never read `.env`".
    - `mcp-tools.md` contains `/usage/detailed` and "never per-token".
    - `map.md` contains `map.py export`.
    - `SKILL.md` contains `return_count`.
  - **Ledger test:** the three-attempt paged search validates.
- [ ] **Step 2: Run them** → FAIL.
- [ ] **Step 3: Write the docs.**
- [ ] **Step 4: Run all checks:**
  - `make check`
  - the build
  - `evals/run.py validate --suite all`
  - `claude plugin validate --strict`

  All must pass.
- [ ] **Step 5: Commit** `docs: complete CLI path, paging, export and usage guidance in the skill`.

### Task 5: Versions, changelog, close out the audit

- [ ] **Bump versions:** plugin to `0.10.0`, SDK to `0.5.0`. Update the changelog
  (Added: export, `--max-records`, request summaries, CLI path; Changed: the satellite
  map design non-goal on GIS export is reversed by decision). The version test changes
  first (red).
- [ ] **Close out the todos:**
  - Tick every remaining todo in `todos.md`.
  - Mark unverified items as not run with the reason: the live cursor field, host map
    checks, and any live check not authorized.
- [ ] **Run checks:** all Batch 1 gates.
- [ ] **Commit** `chore: release Regrid Research 0.10.0 and SDK 0.5.0`.
