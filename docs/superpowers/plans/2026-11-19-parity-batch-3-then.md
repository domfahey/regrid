# Parity Batch 3 (Then): County Freshness, Address Suggestions, Neighbouring Outlines Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add county pull dates (`/verse`), address suggestions (typeahead, then
path), and opt-in neighbouring parcel outlines on the map, in both the skill and the CLI.

**Architecture:**
- **Freshness:** a new standard-library helper, `src/regrid/offline/freshness.py`
  (synced into the skill), reads a saved `/verse` response. `regrid freshness` fetches
  and caches that response. The skill uses county pull dates only through the CLI,
  because `/verse` returns every county, which is too large for chat. The first part of
  `references/cli.md` covers this.
- **Neighbours:** `map.py render --neighbours FILE` draws a second, muted layer.
  `regrid address-map --neighbours` and the plugin command make the one extra point
  search.
- **Address suggestions:** skill guidance only. The CLI's existing `typeahead` and
  `parcel-path` already cover it.

**Tech Stack:** Python 3.10+, argparse, pytest, `httpx.MockTransport`, Leaflet (page only).

**Spec:** `docs/superpowers/specs/2026-11-19-plugin-cli-parity-design.md` (design
decisions: freshness is date only; neighbours are off unless asked, 100 m, at most 25;
"Builder questions settled" 2 and 3). Requires Batches 1–2 merged.

## Global Constraints

- All of Batch 1's Global Constraints apply.
- **Freshness:** report dates only and never label data stale. Each parcel's
  `ll_last_refresh` remains the default freshness answer over MCP.
- **Neighbours:**
  - Off unless the user asks.
  - When asked: exactly one `/parcels/point` request with the subject's `lat` and
    `lon`, `radius=100`, `limit=25` and `return_geometry=true`, and paid datasets off.
  - State the cost (one request, up to 25 records) before the call.
- **Verse cache:** `~/.cache/regrid/verse.json`, or
  `%LOCALAPPDATA%\regrid\verse.json` on Windows, overridable with `--cache`. It holds
  `{"retrieved_at": ISO, "response": <verse body>}` and never the token.
- **Freshness request:** `regrid freshness` requests `/verse` with
  `return_geometry=false`. It reuses the cache unless `--refresh` is given or no cache
  exists.
- **Ledger:** the CLI is ledger-unaware and prints `regrid: requests made: N` on
  stderr. The skill reserves a ledger attempt before each CLI command that can make a
  request and completes it from that line; an unreadable line leaves the attempt
  uncertain.
- **Typeahead:** Enterprise only. A permission or 403 error is recorded once, never
  retried, and the skill asks the user to clarify the address instead.
- **Versions:** plugin `0.9.0`, SDK `0.4.0`.

## Review Focus

1. **County not in the verse response:** `regrid freshness --path /us/zz/nowhere` must
   exit 1 with `county not found in verse response: /us/zz/nowhere`, and make no
   second request. Pinned in Task 1.
2. **Path deeper than county level:** a parcel path such as
   `/us/nj/camden/haddonfield/123` passed to freshness must resolve to the county
   `/us/nj/camden`. Pinned in Task 1.
3. **Subject among its neighbours:** the subject parcel appears in the neighbours
   response. It must be drawn once, as the subject, matched by `ll_uuid`. Pinned in
   Task 2.
4. **Subject without a point:** `address-map --neighbours` when the subject has no
   `lat`/`lon` must skip the neighbour request, print
   `regrid: neighbours skipped: subject has no coordinates`, and still write the map
   with `requests made: 1`. Pinned in Task 3.
5. **Bad neighbour geometry:** one corrupt neighbour must be dropped, with a warning
   naming its index, while the subject still renders. A bad neighbour must not abort
   the whole map. Pinned in Task 2.

---

### Task 1: Freshness helper and `regrid freshness`

**Files:**
- Create: `src/regrid/offline/freshness.py` (+ sync entry, build entry, discovery `ALLOWLIST` entry)
- Modify: `src/regrid/cli.py`
- Test: `tests/test_offline_freshness.py`, `tests/test_cli_freshness.py`

**Interfaces:**
- Produces:
  - `county_path(path: str) -> str` returns the first three segments,
    `/us/<state>/<county>`. A path that doesn't start with `/us/` or has fewer than
    three segments raises `FreshnessError(ValueError)`.
  - `county_dates(verse: dict, path: str) -> dict` returns `{"path", "county",
    "state", "last_refresh", "assessor_data_date", "usps_data_date"}`. Values are
    copied as strings or `None`. It accepts both the FeatureCollection and single
    Feature envelopes, and matches `properties.path`.
  - **Helper CLI:** `python3 freshness.py county VERSE.json --path PATH` prints the
    JSON dict.
  - **`regrid freshness --path PATH [--cache FILE] [--refresh]`:** prints
    `{**county_dates, "verse_retrieved_at": ISO, "cache": "hit"|"miss"}`. Stderr
    always shows `regrid: requests made: 0|1`.

- [ ] **Step 1: Write the failing tests**

```python
VERSE = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {
                "path": "/us/nj/camden",
                "county": "Camden",
                "state": "NJ",
                "last_refresh": "2026-09-01",
                "assessor_data_date": "2026-08-15",
                "usps_data_date": None,
            },
        }
    ],
}


def test_county_path_trims_parcel_path():
    assert freshness.county_path("/us/nj/camden/haddonfield/123") == "/us/nj/camden"


@pytest.mark.parametrize("bad", ["/ca/on/toronto", "/us/nj", "nj/camden"])
def test_county_path_rejects(bad):
    with pytest.raises(freshness.FreshnessError):
        freshness.county_path(bad)


def test_county_dates_reports_dates_only():
    result = freshness.county_dates(VERSE, "/us/nj/camden/haddonfield/123")
    assert result["last_refresh"] == "2026-09-01" and "stale" not in json.dumps(result).lower()


def test_freshness_caches_and_reuses(tmp_path, verse_server, capsys):
    cache = tmp_path / "verse.json"
    assert cli.main(["freshness", "--path", "/us/nj/camden", "--cache", str(cache)]) == 0
    first = capsys.readouterr()
    assert "requests made: 1" in first.err and json.loads(first.out)["cache"] == "miss"
    assert dict(verse_server[0].url.params)["return_geometry"] == "false"
    assert cli.main(["freshness", "--path", "/us/nj/camden", "--cache", str(cache)]) == 0
    assert "requests made: 0" in capsys.readouterr().err and len(verse_server) == 1
    assert "secret" not in cache.read_text()


def test_refresh_forces_request(tmp_path, verse_server): ...  # 2 requests after --refresh
def test_unknown_county_exits_1_without_retry(tmp_path, verse_server, capsys): ...  # Review Focus 1
```

- [ ] **Step 2: Run them** → FAIL.
- [ ] **Step 3: Implement.**
  - **Cache location:** resolve the default with `os.environ.get("LOCALAPPDATA")` on
    Windows, otherwise `XDG_CACHE_HOME` or `~/.cache`.
  - **Writing:** write the cache atomically. Create the directory with mode `0o700`
    where supported.
  - **Sync:** run the helper sync.
- [ ] **Step 4: Run** the tests, then `make check` → PASS.
- [ ] **Step 5: Commit** `feat: add county freshness helper and regrid freshness`.

### Task 2: Neighbours layer in `map.py`

**Files:**
- Modify: `src/regrid/offline/map.py` (then sync)
- Test: `tests/test_regrid_map.py`

**Interfaces:**
- Produces:
  - **Function:** `render(..., neighbours_path: Path | None = None)`.
  - **Helper CLI:** `render ... --neighbours FILE`.
  - **Drawing:**
    - Neighbours are drawn first, in style `{color: "#ffffff", weight: 1,
      fillOpacity: 0.05}`, with popups (address, owner, parcel number).
    - A feature with the subject's `ll_uuid` is excluded.
    - Invalid neighbour features are dropped, each with the warning
      `Neighbour N skipped: <MapError message>`, where N is the zero-based index.
    - Neighbours get no area check.
  - **Summary:** adds `"neighbours": <drawn count>`.

- [ ] **Step 1: Write the failing tests**

```python
def test_neighbours_drawn_and_subject_excluded(tmp_path):
    subject = good_feature()
    others = [feature(square(lon=-75.0289, lat=39.9)), subject]
    response = write_response(tmp_path / "r.json", subject)
    near = write_response(tmp_path / "n.json", *others)
    summary = parcel_map.render(response, tmp_path / "m.html", neighbours_path=near)
    assert summary["neighbours"] == 1 and summary["features"] == 1


def test_bad_neighbour_is_skipped_with_warning(tmp_path):
    bad = feature({"type": "Point", "coordinates": [-75.03, 39.9]})
    response = write_response(tmp_path / "r.json", good_feature())
    near = write_response(tmp_path / "n.json", bad)
    summary = parcel_map.render(response, tmp_path / "m.html", neighbours_path=near)
    assert summary["neighbours"] == 0 and summary["warnings"][0].startswith("Neighbour 0 skipped")


def test_neighbours_cli_flag_from_extracted_skill(tmp_path): ...  # subprocess `render --neighbours`
```

- [ ] **Step 2: Run them** → FAIL.
- [ ] **Step 3: Implement.** Add a second JSON data block (`neighbour-data`) with the
  same escaping, then sync.
- [ ] **Step 4: Run** the tests, then `make check` → PASS.
- [ ] **Step 5: Commit** `feat: draw neighbouring parcel outlines on the satellite map`.

### Task 3: `address-map --neighbours` (CLI)

**Files:**
- Modify: `src/regrid/cli.py`
- Test: `tests/test_cli_address_map.py`

**Interfaces:**
- Consumes: `render(..., neighbours_path=...)` from Task 2.
- Produces:
  - **Requests:** after the address response, if `--neighbours` is set and the subject
    has numeric `lat` and `lon` fields, make one
    `client.point(lat=..., lon=..., radius=100, limit=25, return_geometry=True,
    return_parcels=True, return_stacked=False, return_zoning=False,
    return_matched_buildings=False, return_matched_addresses=False,
    return_enhanced_ownership=False)`.
  - **Saved file:** the neighbours response goes to `<OUTPUT stem>.neighbours.json`,
    under the same no-overwrite rule, checked before any request.
  - **Stderr:** `requests made: 2`, or `1` when skipped (Review Focus 4).

- [ ] **Step 1: Write the failing tests:**
  - **Exact params:** the second request's params equal the dict above (minus the
    token).
  - **Request counts:** 2 with neighbours, 1 when skipped, 1 without the flag.
  - **Existing neighbours file:** refuses with 0 requests.
- [ ] **Step 2: Run them** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the tests, then `make check` and `make e2e` → PASS.
- [ ] **Step 5: Commit** `feat: add opt-in neighbouring outlines to regrid address-map`.

### Task 4: Skill guidance (freshness via CLI, address suggestions, neighbours)

**Files:**
- Create: `plugins/regrid-research/skills/property-research/references/cli.md`
  (freshness section only)
- Modify: `SKILL.md` (resource lines for `cli.md`, neighbours and suggestions),
  `references/map.md` (neighbours flow), `references/mcp-tools.md` (address
  suggestions flow), `references/batch.md` (ledger rule for CLI attempts),
  `plugins/regrid-research/commands/address-map.md` (adds "with neighbours" handling)
- Test: `tests/test_claude_plugins.py`, `tests/test_regrid_workflow_composition.py`

**Interfaces:**
- Produces:
  - **`cli.md` (freshness):**
    - When to use the CLI: Claude Code only, `regrid` on PATH, and `REGRID_TOKEN`
      already in the environment, or inside this repo with `.env` via
      `uv run --env-file .env --no-sync regrid ...`.
    - Never read `.env` or the token.
    - Reserve an attempt with `record_limit` 0 for `regrid freshness`, and complete
      it from `requests made: N`.
    - Over MCP, report `ll_last_refresh` and say county pull dates need the CLI.
  - **`map.md` (neighbours):**
    - Only on request: state "one request, up to 25 records" first.
    - Make one `/parcels/point` request with the exact options from the Global
      Constraints, save it verbatim, then run `render --neighbours`.
  - **`mcp-tools.md` (address suggestions):**
    - For ambiguous or mistyped addresses: `/parcels/typeahead` (`query`), then
      `/parcels/path` for the chosen path. Each is one request.
    - Permission errors are recorded once and never retried; ask the user instead.
  - **Composition test:** reserving and completing a 0-record CLI freshness attempt
    keeps the ledger valid, using the existing `reserve_attempt` and
    `complete_attempt` with a `kind="diagnostic"` attempt.

- [ ] **Step 1: Write the failing tests:**
  - **Doc assertions:**
    - `cli.md` mentions `requests made`.
    - `map.md` mentions `radius=100`, `limit=25` and "up to 25 records".
    - `mcp-tools.md` mentions `/parcels/typeahead` and "never retried".
    - The command file mentions neighbours.
  - **Ledger test:** a diagnostic 0-record attempt completed with
    `returned_records=0` validates.
- [ ] **Step 2: Run them** → FAIL.
- [ ] **Step 3: Write the docs.** The ledger behavior is already supported by
  `workflow.py`; if the test exposes a gap, fix it there with its own red test.
- [ ] **Step 4: Run** `make check`, the build, `evals/run.py validate --suite all` and
  `claude plugin validate --strict` → PASS.
- [ ] **Step 5: Commit** `docs: add CLI freshness, address suggestions and neighbours to the skill`.

### Task 5: Versions and changelog

- [ ] **Bump versions:** plugin to `0.9.0`, SDK to `0.4.0`, changelog, README CLI
  examples (`regrid freshness`, `address-map --neighbours`), and tick the items in
  `todos.md`. The version test changes first (red).
- [ ] **Run checks:** all Batch 1 gates.
- [ ] **Commit** `chore: release Regrid Research 0.9.0 and SDK 0.4.0`.
