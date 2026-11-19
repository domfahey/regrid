# Parity Batch 1 (Now): Shared Map Helper, `address-map`, Live Geometry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the CLI the satellite map, make the usual address-to-map flow a single
step in both the CLI and the plugin, and make `make live` report whether address
responses carry geometry.

**Architecture:**
- The map helper moves to `src/regrid/offline/map.py`, which becomes the one source.
- A sync script copies it, byte-identical, to the skill's `scripts/map.py`, and a test
  enforces that the copies match.
- New CLI subcommands `map` and `address-map` import it.
- The plugin gains a Claude Code command that runs the existing MCP lookup, save and
  render flow.

**Tech Stack:** Python 3.10+, argparse, httpx (SDK only), pytest with
`httpx.MockTransport`, Claude plugin commands (Markdown).

**Spec:** `docs/superpowers/specs/2026-11-19-plugin-cli-parity-design.md` (see
"Builder questions settled" 1, 2, 4–7, 9).

## Global Constraints

- US parcels only. No Canadian, Global or Batch additions.
- Shared helpers in `src/regrid/offline/` use only the standard library, are single
  self-contained files, and never import from `regrid`.
- Never display, log or write the token, request headers or token-bearing URLs: not in
  pages, saved responses, stderr summaries or test output.
- Every new command that can make API requests prints `regrid: requests made: N` to
  stderr. Existing commands are unchanged in this batch.
- Existing CLI commands, their JSON stdout and the handoff schemas stay compatible.
- Ordinary tests never contact Regrid: use `httpx.MockTransport`. Live runs only through
  opt-in `make live` with the user's authorization.
- Red-green TDD: write each test, run it and see it fail for the stated reason, then
  implement.
- Versions: plugin `0.7.0` (in `plugins/regrid-research/.claude-plugin/plugin.json` and
  the README archive names); SDK `0.2.0` (in `pyproject.toml` and
  `src/regrid/__init__.py`).
- Conventional Commits. Every commit ends with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- `make check` passes at the end of each task: ruff, format, mypy, and coverage of at
  least 90%.

## Review Focus

1. **Existing output file:** `regrid address-map ... OUT.html` when `OUT.html` or the
   saved-response file already exists must refuse before any request, so no record is
   spent. Pinned in Task 3.
2. **Failed lookup:** an API error (401, 429 or 5xx) during `address-map` must exit 1,
   write no page, still print `requests made: 1`, and never echo the token or the
   address in stderr. Pinned in Task 3.
3. **Empty result:** an address that returns zero features exits 1 with
   "Response contains no parcels". It must not crash, and the saved response is kept
   for the record. Pinned in Task 3.
4. **Edited skill copy:** if someone edits the skill copy of `map.py` instead of the
   source, `make check` fails with a message naming the sync command. Pinned in Task 1.
5. **Missing `REGRID_TOKEN`:** `regrid map` must work with no token (it is offline).
   `address-map` must fail with the SDK's missing-token error and make zero requests.
   Pinned in Tasks 2 and 3.

---

### Task 1: One source for the map helper, with a sync check

**Files:**
- Create: `src/regrid/offline/__init__.py` (empty docstring only)
- Create: `src/regrid/offline/map.py` (from `git mv` of the skill's `map.py` content; see step 3)
- Create: `scripts/sync_skill_helpers.py`
- Create: `tests/test_skill_helper_sync.py`
- Modify: `tests/test_regrid_map.py` (import the package module; subprocess tests keep using the skill copy)
- Keep: `plugins/regrid-research/skills/property-research/scripts/map.py` (now a generated copy)

**Interfaces:**
- Produces:
  - `scripts/sync_skill_helpers.py` with `HELPERS: dict[str, str] = {"map.py": "map.py"}`
    (source name to skill name).
  - `sync(root: Path, *, check: bool) -> list[str]`, which returns the names that
    differ. With `check=True` it writes nothing.
  - The CLI: `python scripts/sync_skill_helpers.py [--check]`. It exits 1 and prints
    `out of sync: map.py; run python scripts/sync_skill_helpers.py` when `--check`
    finds drift.
  - The module `regrid.offline.map`, with the same public API as today's `map.py`.

- [ ] **Step 1: Write the failing tests** in `tests/test_skill_helper_sync.py`

```python
def test_skill_copies_match_sources():
    assert sync_module.sync(ROOT, check=True) == []


def test_check_reports_drift_without_writing(tmp_path):
    fake = make_tree(tmp_path)  # copies src/regrid/offline + skill scripts into tmp
    (fake / SKILL_SCRIPTS / "map.py").write_text("# edited\n")
    assert sync_module.sync(fake, check=True) == ["map.py"]
    assert (fake / SKILL_SCRIPTS / "map.py").read_text() == "# edited\n"


def test_sync_writes_identical_copy(tmp_path):
    fake = make_tree(tmp_path)
    (fake / SKILL_SCRIPTS / "map.py").write_text("# edited\n")
    assert sync_module.sync(fake, check=False) == ["map.py"]
    assert sync_module.sync(fake, check=True) == []


def test_offline_helpers_import_nothing_from_regrid():
    for path in (ROOT / "src/regrid/offline").glob("*.py"):
        assert not re.search(r"^\s*(from|import)\s+regrid\b|^\s*from\s+\.", path.read_text(), re.M)
```

Here `SKILL_SCRIPTS = Path("plugins/regrid-research/skills/property-research/scripts")`.
`sync_module` is loaded with `importlib` from `scripts/sync_skill_helpers.py`.

- [ ] **Step 2: Run them.** `.venv/bin/python -m pytest tests/test_skill_helper_sync.py -v` → FAIL (module missing).
- [ ] **Step 3: Move the source.**
  - Run `git mv` on the skill `map.py` to `src/regrid/offline/map.py`, create
    `__init__.py`, and implement `sync_skill_helpers.py`.
  - The sync compares bytes. It writes with `newline=""` semantics (bytes copy) so
    Windows checkouts compare the same.
  - Run the sync to recreate the skill copy.
- [ ] **Step 4: Point the map tests at the package.** In `tests/test_regrid_map.py`,
  replace the `spec_from_file_location` import with
  `from regrid.offline import map as parcel_map`. Keep `SCRIPT` pointing at the skill
  copy for the subprocess and extracted-archive tests.
- [ ] **Step 5: Make typecheck pass.** Run `make typecheck`. Fix any mypy errors in
  `regrid/offline/map.py` with annotations only, with no behavior change, then re-sync.
- [ ] **Step 6: Run** `make check` → all pass, coverage ≥ 90%.
- [ ] **Step 7: Commit** `refactor: make src/regrid/offline the source of the map helper`.

### Task 2: `regrid map` (offline)

**Files:**
- Modify: `src/regrid/cli.py`
- Create: `tests/test_cli_offline.py`

**Interfaces:**
- Consumes: `regrid.offline.map.render(response_path, output_path, *, index, all_candidates, retrieved_at, replace) -> dict` and `MapError`.
- Produces:
  - The CLI subcommand `map RESPONSE OUTPUT [--feature N] [--all-candidates]
    [--retrieved-at ISO] [--replace]`.
  - It prints the `render` summary as JSON to stdout and exits 0.
  - On `MapError` or `OSError` it prints `regrid: <message>` to stderr and exits 1.
  - It never constructs `RegridClient`.

- [ ] **Step 1: Write the failing tests** in `tests/test_cli_offline.py`. Build
  fixtures by copying `square`, `feature`, `write_response` and `good_feature` from
  `tests/test_regrid_map.py` into `tests/map_fixtures.py`, and import them in both files.

```python
def test_map_renders_without_token_or_client(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("REGRID_TOKEN", raising=False)
    monkeypatch.setattr(cli, "RegridClient", lambda **kw: pytest.fail("no client for offline map"))
    response = write_response(tmp_path / "r.json", good_feature())
    assert cli.main(["map", str(response), str(tmp_path / "m.html")]) == 0
    assert json.loads(capsys.readouterr().out)["features"] == 1


def test_map_errors_are_one_line(tmp_path, capsys):
    response = write_response(tmp_path / "r.json", good_feature(), good_feature())
    assert cli.main(["map", str(response), str(tmp_path / "m.html")]) == 1
    err = capsys.readouterr().err
    assert err.startswith("regrid: Response has several parcels") and err.count("\n") == 1


def test_map_flags_pass_through(tmp_path):
    response = write_response(tmp_path / "r.json", good_feature(), good_feature())
    assert (
        cli.main(
            [
                "map",
                str(response),
                str(tmp_path / "m.html"),
                "--all-candidates",
                "--retrieved-at",
                "2026-11-19T00:00:00Z",
            ]
        )
        == 0
    )
    page = (tmp_path / "m.html").read_text(encoding="utf-8")
    assert "Candidate 2" in page and "2026-11-19T00:00:00Z" in page
    assert (
        cli.main(["map", str(response), str(tmp_path / "m.html"), "--feature", "0"]) == 1
    )  # exists
    assert (
        cli.main(["map", str(response), str(tmp_path / "m.html"), "--feature", "0", "--replace"])
        == 0
    )
```

- [ ] **Step 2: Run them** → FAIL (`invalid choice: 'map'`).
- [ ] **Step 3: Implement.** Dispatch offline commands in `main` before
  `RegridClient` is created, using a small `_OFFLINE` dict of command name to handler.
  Keep `map` out of `option_commands` and `country_commands`.
- [ ] **Step 4: Run** the tests → PASS; then `make check`.
- [ ] **Step 5: Commit** `feat: add offline regrid map command`.

### Task 3: `regrid address-map` (one request)

**Files:**
- Modify: `src/regrid/cli.py`
- Test: `tests/test_cli_address_map.py`

**Interfaces:**
- Consumes: `RegridClient.address(query, **options)` and `regrid.offline.map.render`.
- Produces:
  - **Command:** `address-map ADDRESS OUTPUT [--path SCOPE] [--save-response FILE]
    [--retrieved-at ISO] [--replace]`.
  - **Saved response:** defaults to `OUTPUT` with the suffix `.json`. It is written
    with the same no-overwrite rule, using an exclusive create unless `--replace`.
  - **Request:** exactly one `client.address(ADDRESS, limit=1, return_parcels=True,
    return_stacked=False, return_zoning=False, return_matched_buildings=False,
    return_matched_addresses=False, return_enhanced_ownership=False[, path=SCOPE])`.
  - **Retrieval time:** `--retrieved-at` defaults to the current UTC time as
    `YYYY-MM-DDTHH:MM:SSZ`.
  - **Stdout:** `{"response": <saved path>, **render summary}`.
  - **Stderr:** always `regrid: requests made: N` (N is 0 or 1), printed before any
    error line.

- [ ] **Step 1: Write the failing tests** using the `requests` fixture pattern from
  `tests/test_cli.py`. Define three fixtures in the test file, each patching
  `cli.RegridClient` with a `MockTransport` and setting `REGRID_TOKEN=secret`:
  - `seen`: returns `{"parcels": {"features": [good_feature()]}}` and records requests.
  - `failing_401`: returns 401 with body `"secret private-address"`.
  - `empty_response`: returns `{"parcels": {"features": []}}`.

```python
def test_address_map_one_request_exact_params(tmp_path, seen, capsys):
    out = tmp_path / "m.html"
    assert cli.main(["address-map", "12 Example Ave", str(out), "--path", "/us/nj/camden"]) == 0
    assert len(seen) == 1 and seen[0].url.path == "/api/v2/parcels/address"
    params = dict(seen[0].url.params)
    params.pop("token")
    assert params == {
        "query": "12 Example Ave",
        "limit": "1",
        "path": "/us/nj/camden",
        "return_parcels": "true",
        "return_stacked": "false",
        "return_zoning": "false",
        "return_matched_buildings": "false",
        "return_matched_addresses": "false",
        "return_enhanced_ownership": "false",
    }
    captured = capsys.readouterr()
    assert "regrid: requests made: 1" in captured.err
    summary = json.loads(captured.out)
    assert summary["response"] == str(tmp_path / "m.json") and out.exists()
    assert "secret" not in out.read_text(encoding="utf-8") + (tmp_path / "m.json").read_text()


def test_existing_output_refuses_before_request(tmp_path, seen, capsys):
    (tmp_path / "m.json").write_text("keep")
    assert cli.main(["address-map", "x", str(tmp_path / "m.html")]) == 1
    assert seen == [] and "requests made: 0" in capsys.readouterr().err


def test_api_error_writes_no_page_and_hides_secrets(tmp_path, failing_401, capsys):
    assert cli.main(["address-map", "private-address", str(tmp_path / "m.html")]) == 1
    err = capsys.readouterr().err
    assert "requests made: 1" in err and "secret" not in err and "private-address" not in err
    assert not (tmp_path / "m.html").exists()


def test_empty_result_keeps_response_and_fails(tmp_path, empty_response, capsys):
    assert cli.main(["address-map", "x", str(tmp_path / "m.html")]) == 1
    assert (tmp_path / "m.json").exists() and not (tmp_path / "m.html").exists()
    assert "Response contains no parcels" in capsys.readouterr().err


def test_missing_token_makes_no_request(tmp_path, seen, monkeypatch, capsys):
    monkeypatch.delenv("REGRID_TOKEN")
    assert cli.main(["address-map", "x", str(tmp_path / "m.html")]) == 1
    assert seen == [] and "requests made: 0" in capsys.readouterr().err


def test_cli_saved_response_renders_like_mcp_body(tmp_path, seen):
    # The CLI saves the raw API body; map renders it unchanged (spec builder answer 6).
    cli.main(["address-map", "x", str(tmp_path / "m.html")])
    assert regrid.offline.map.render(tmp_path / "m.json", tmp_path / "n.html")["features"] == 1
```

- [ ] **Step 2: Run them** → FAIL.
- [ ] **Step 3: Implement.**
  - Check that neither output exists before building the client.
  - Count a request only when the client actually sends one.
  - Map `RegridError` to its sanitized message and `MapError` to its own message.
  - The missing-token check happens in the SDK before sending, so the count stays 0.
- [ ] **Step 4: Run** the tests → PASS; then `make check` and `make e2e`.
- [ ] **Step 5: Commit** `feat: add regrid address-map one-request lookup and map`.

### Task 4: Live run reports geometry presence

**Files:**
- Modify: `src/regrid/live.py` (`run`)
- Test: `tests/test_live.py`

**Interfaces:**
- Produces: after a successful one-record lookup, `run` prints exactly one of these:
  - `PASS geometry present` when the feature has a non-null `geometry` object.
  - `NOTE geometry null (no boundary on file)` when it is null.
  - `NOTE geometry field absent (map would fail)` when the key is missing.

  It prints no coordinates. The request count is unchanged (still at most four).

- [ ] **Step 1: Write the failing test.** Parametrize
  `test_bounded_smoke_and_final_usage_even_after_parcel_failure`'s "ok" response
  three ways (polygon, `None`, key removed). Assert the matching line is in `capsys`
  output, that no coordinate digits from the fixture appear, and that
  `len(requests) == 4`.
- [ ] **Step 2: Run it** → FAIL.
- [ ] **Step 3: Implement.** Read the raw payload (`payload["parcels"]["features"][0]`),
  not the typed model.
- [ ] **Step 4: Run** `pytest tests/test_live.py` → PASS; then `make check`.
- [ ] **Step 5: Commit** `feat: report parcel geometry presence in make live`.
- [ ] **Step 6: Live check (authorization gate).**
  - Ask the user to run or authorize `make live`, and record the geometry line in the
    PR.
  - If not authorized, record "live geometry check: not run" in the PR and changelog,
    never "passed".
  - If the result is "absent", stop and revise `references/map.md` before the PR.

### Task 5: Plugin command, packaging, docs, versions, host checklist

**Files:**
- Create: `plugins/regrid-research/commands/address-map.md`
- Modify: `scripts/build_claude_plugins.py` (ship `commands/*.md` in the Claude Code
  and Cowork archives, not the standalone skill)
- Modify: `plugins/regrid-research/skills/property-research/SKILL.md` (one line: the
  `/regrid-research:address-map` command runs the map flow), `references/map.md`
  (mention the CLI equivalent `regrid address-map` for terminal users)
- Modify: `plugins/regrid-research/.claude-plugin/plugin.json` (`0.7.0`), plugin
  `README.md` (archive names and the command), root `README.md` (`regrid map`,
  `regrid address-map`), `pyproject.toml` and `src/regrid/__init__.py` (`0.2.0`),
  `changelog.md`, `todos.md` (tick the Batch 1 items done)
- Modify: `plugins/regrid-research/evals/README.md` (host checklist)
- Create: `plugins/regrid-research/evals/results/map-hosts-0.7.0.json`
- Test: `tests/test_claude_plugins.py`

**Interfaces:**
- Produces:
  - **Command frontmatter:** `description` and `argument-hint: <US street address>`.
  - **Command body:**
    - It runs the property-research skill's address lookup with one request and one
      record, saves the decoded response verbatim, renders it with `scripts/map.py`,
      gives a short summary, and presents the page per `references/map.md`.
    - Neighbours are not offered in this batch.
    - For non-US addresses it follows the skill's scope rule.
  - **Host results file:** `{"plugin_version": "0.7.0", "hosts": {"claude_code":
    STATUS, "claude_apps": STATUS, "cowork": STATUS}, "notes": ""}`, where STATUS is
    `verified`, `failed` or `not_run`. All three start as `not_run`.

- [ ] **Step 1: Write the failing tests** in `tests/test_claude_plugins.py`

```python
def test_command_ships_in_plugin_archives_only(source, tmp_path):
    cowork, code, standalone = map(archive_contents, builder.build(source, tmp_path / "out"))
    assert "commands/address-map.md" in code and "commands/address-map.md" in cowork
    assert not any(name.startswith("commands/") for name in standalone)


def test_command_is_bounded_and_links_map_guide():
    text = (PLUGIN / "commands/address-map.md").read_text()
    assert text.startswith("---\n") and "argument-hint:" in text
    assert "one request" in text and "references/map.md" in text and "neighbour" not in text.lower()


def test_host_results_never_claim_unrun_checks():
    data = json.loads((PLUGIN / "evals/results/map-hosts-0.7.0.json").read_text())
    assert set(data["hosts"].values()) <= {"verified", "failed", "not_run"}


def test_versions():
    assert json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text())["version"] == "0.7.0"
    assert regrid.__version__ == "0.2.0"
```

Here `PLUGIN = ROOT / "plugins/regrid-research"`.

- [ ] **Step 2: Run them** → FAIL.
- [ ] **Step 3: Implement.**
  - **Build:** add a `command_files(root)` that reads `commands/*.md` with
    `read_public_file`, and merge it into the plugin archives.
  - **Host checklist:** add a "Satellite map host checklist" section to the evals
    README: open the page, confirm the imagery, outline, info panel and Esri credit,
    check the console, and record the status in the results file.
  - **Docs:** write the docs, version bumps and changelog. The changelog gets an Added
    entry for `regrid map`, `regrid address-map` and the plugin command, with the live
    check status stated truthfully.
- [ ] **Step 4: Run all checks.**
  - `make check`
  - `make e2e`
  - `.venv/bin/python scripts/build_claude_plugins.py`
  - `.venv/bin/python plugins/regrid-research/evals/run.py validate --suite all`
  - `claude plugin validate ./plugins/regrid-research --strict`

  All must pass. Report any gate that was not run as not run.
- [ ] **Step 5: Commit** `feat: add address-map plugin command (Regrid Research 0.7.0, SDK 0.2.0)`.
- [ ] **Step 6: Manual host check (user).**
  - Ask the user to try the 0.7.0 archives in the Claude apps and Cowork, and update
    `map-hosts-0.7.0.json`.
  - Statuses stay `not_run` until there is evidence.
