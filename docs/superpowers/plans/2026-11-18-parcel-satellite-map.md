# Parcel Satellite Map Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render a saved Regrid `/parcels/address` response as a self-contained interactive satellite map of the parcel boundary.

**Architecture:** A standard-library helper `map.py` beside `workflow.py` validates the response geometry (structure, US bounds, area vs `ll_gissqft`) and writes one HTML page using Leaflet + Esri World Imagery. The skill gains a conditionally loaded `references/map.md`; packaging ships the helper in all three archives.

**Tech Stack:** Python 3.10+ standard library only (helper); pytest; Leaflet 1.9.4 from unpkg with SRI.

**Spec:** `docs/superpowers/specs/2026-11-18-parcel-satellite-map-design.md`

## Global Constraints

- Helper: Python 3.10+, standard library only, no network access, never reads `.env` or credentials.
- Helper path: `plugins/regrid-research/skills/property-research/scripts/map.py`.
- Output page must contain no Regrid token, `x-regrid-token`, or `token=`; external URLs only from `unpkg.com` and `server.arcgisonline.com`.
- Leaflet `1.9.4` from `https://unpkg.com/leaflet@1.9.4/dist/` with `integrity` + `crossorigin=""`.
- Imagery URL `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}`, attribution `Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community`.
- Record text is untrusted: never interpolated into HTML/JS unescaped.
- US scope only. Plugin version becomes `0.6.0`. 100-char lines, Ruff-formatted, type-annotated.
- Run tests with `.venv/bin/python -m pytest`; tests must not contact the network.

## Review Focus

- Hostile record text (`</script>`, quotes, `<img onerror>`) in owner/address: must render inert. → Task 2 test `test_hostile_record_text_is_inert`.
- Response with several features and no selection flag: must refuse rather than guess. → Task 2 test `test_multiple_features_require_explicit_choice`.
- Geometry lightly corrupted by transcription (one coordinate digit changed): area check must flag it. → Task 1 test `test_area_check_flags_mismatch`.
- Parcel crossing the antimeridian or in a territory (Aleutians, Guam): must not be rejected as non-US. → Task 1 test `test_us_bounds_accept_territories_and_aleutians`.
- Output path already exists: must refuse without `--replace` and leave the file untouched. → Task 2 test `test_render_refuses_overwrite`.

---

### Task 1: Geometry validation and area check

**Files:**
- Create: `plugins/regrid-research/skills/property-research/scripts/map.py`
- Test: `tests/test_regrid_map.py`

**Interfaces:**
- Produces:
  - `class MapError(ValueError)`
  - `load_features(document: object) -> list[dict]` — returns `document["parcels"]["features"]`; raises `MapError("Expected a Regrid parcel response with parcels.features")` on any other shape, `MapError("Response contains no parcels")` when empty.
  - `validate_geometry(geometry: object) -> None` — accepts GeoJSON `Polygon`/`MultiPolygon`; raises `MapError` for: other types, rings with < 4 positions, unclosed rings, non-finite/non-numeric coordinates, any position outside `US_BOUNDS`.
  - `US_BOUNDS: tuple[tuple[float, float, float, float], ...]` (west, south, east, north): `(-180.0, 17.5, -64.0, 72.0)`, `(172.0, 51.0, 180.0, 53.5)`, `(144.5, 13.0, 146.5, 21.0)`, `(-171.2, -14.7, -168.0, -11.0)`.
  - `geometry_area_sqft(geometry: dict) -> float` — spherical area, outer ring minus holes, summed over polygons.
  - `area_check(feature: dict, tolerance: float = 0.05) -> dict` — keys `status` (`"ok"`, `"mismatch"`, `"unavailable"`), `computed_sqft` (float or None), `recorded_sqft` (float or None), `ratio` (float or None). Recorded value from `feature["properties"]["fields"]["ll_gissqft"]` (number or numeric string). `unavailable` when geometry is null or recorded value missing/non-positive.

Test fixture helper (put in the test file, reused by Task 2):

```python
def square(lon=-75.03, lat=39.9, size=0.001):
    ring = [[lon, lat], [lon + size, lat], [lon + size, lat + size], [lon, lat + size], [lon, lat]]
    return {"type": "Polygon", "coordinates": [ring]}


def expected_sqft(lon=-75.03, lat=39.9, size=0.001):
    r = 6378137.0
    m2 = (
        r
        * r
        * math.radians(size)
        * (math.sin(math.radians(lat + size)) - math.sin(math.radians(lat)))
    )
    return m2 * 10.763910416709722


def feature(geometry, **fields):
    return {
        "type": "Feature",
        "geometry": geometry,
        "properties": {
            "headline": "12 Example Ave",
            "path": "/us/nj/camden/haddonfield/1",
            "ll_uuid": "00000000-0000-4000-8000-000000000001",
            "fields": fields,
        },
    }
```

- [ ] **Step 1: Write failing tests** in `tests/test_regrid_map.py`, loading `map.py` via `importlib.util.spec_from_file_location` (same pattern as `tests/test_regrid_workflow.py:10-17`):
  - `test_load_features_rejects_non_response` — `{}`, `[]`, `{"parcels": {}}` raise `MapError`; `{"parcels": {"features": []}}` raises `MapError` matching `"no parcels"`.
  - `test_square_area_matches_spherical_formula` — `abs(geometry_area_sqft(square()) - expected_sqft()) / expected_sqft() < 1e-6`.
  - `test_hole_and_multipolygon_area` — polygon with inner ring `square(size=0.0005)` offset inside reduces area by that hole's area (rel. 1e-6); MultiPolygon of two disjoint squares sums both.
  - `test_validate_geometry_rejects_malformed` — parametrized: `{"type": "Point", ...}`, unclosed ring, 3-position ring, `"nan"` coordinate, `float("inf")`, string coordinate, `None` coordinates → `MapError`.
  - `test_validate_geometry_rejects_non_us` — `square(lon=2.35, lat=48.85)` raises `MapError` matching `"outside the United States"`.
  - `test_us_bounds_accept_territories_and_aleutians` — squares at `(-66.1, 18.4)` PR, `(-157.9, 21.3)` HI, `(-149.9, 61.2)` AK, `(173.2, 52.8)` Aleutians, `(144.75, 13.45)` Guam, `(-170.7, -14.3)` Samoa all pass.
  - `test_area_check_ok_mismatch_unavailable` — `ll_gissqft=expected_sqft()` → `ok`; numeric string accepted; `ll_gissqft` missing → `unavailable`; geometry `None` → `unavailable` with `computed_sqft is None`.
  - `test_area_check_flags_mismatch` — change one coordinate of `square()` from `39.901` to `39.911` (corrupted digit, ring stays closed by also changing the matching point if needed) with `ll_gissqft=expected_sqft()` → `status == "mismatch"`.
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_regrid_map.py -q` — expected: FAIL (module missing).
- [ ] **Step 3: Implement** the Interfaces above. Area algorithm (radians, `R = 6378137.0`, ft² factor `10.763910416709722`):

```python
def _ring_area_m2(ring):
    total = 0.0
    for (lon1, lat1), (lon2, lat2) in zip(ring, ring[1:]):
        total += math.radians(lon2 - lon1) * (
            2 + math.sin(math.radians(lat1)) + math.sin(math.radians(lat2))
        )
    return abs(total) * R * R / 2
```

  `ratio = computed / recorded`; mismatch when `abs(ratio - 1) > tolerance`. Booleans are not numbers.
- [ ] **Step 4: Run** the same command — expected: all pass. Then `.venv/bin/ruff check tests/test_regrid_map.py plugins/regrid-research/skills/property-research/scripts/map.py && .venv/bin/ruff format --check` on both — clean.
- [ ] **Step 5: Commit** `git add` both files; `git commit -m "feat: add parcel geometry validation for satellite maps"`.

### Task 2: HTML rendering and CLI

**Files:**
- Modify: `plugins/regrid-research/skills/property-research/scripts/map.py`
- Test: `tests/test_regrid_map.py`

**Interfaces:**
- Consumes: everything from Task 1.
- Produces:
  - `select_features(features: list[dict], *, index: int | None, all_candidates: bool) -> list[dict]` — one feature and no flags → `[it]`; several features with neither flag → `MapError` matching `"--feature or --all-candidates"`; out-of-range index → `MapError`.
  - `render_html(features: list[dict], *, candidates: bool, retrieved_at: str | None) -> str`.
  - `render(response_path: Path, output_path: Path, *, index: int | None = None, all_candidates: bool = False, retrieved_at: str | None = None, replace: bool = False) -> dict` — returns summary `{"output": str, "features": int, "area_checks": [area_check results], "warnings": [str]}`; writes atomically (temp file in same dir + `os.replace`); refuses existing output unless `replace is True` (`MapError` matching `"exists"`).
  - CLI: `python3 map.py render RESPONSE OUTPUT [--feature N] [--all-candidates] [--retrieved-at ISO] [--replace]`; prints summary JSON to stdout; exit 0 on success, 1 on `MapError`/`OSError`/invalid JSON with a one-line message on stderr.

Page requirements (`render_html`):
- `<!doctype html>`, `<meta charset="utf-8">`, viewport meta, `<title>Parcel map</title>`, full-viewport map.
- Leaflet CSS/JS per Global Constraints. Implementer computes the `sha256` SRI values by downloading the two files once (`curl -s URL | openssl dgst -sha256 -binary | openssl base64 -A`) and hard-codes them; tests do not hit the network.
- Data embedded once as JSON in `<script type="application/json" id="parcel-data">` with every `<`, `>`, `&` emitted as `<`, `>`, `&`.
- Facts per feature: headline, `owner`, `parcelnumb`, `path`, `ll_last_refresh`, `ll_gisacre`, plus `retrieved_at`; missing values show `not in record`. JS builds popups/panel with `textContent` only.
- Outline `#ffeb3b`, weight 3, fill opacity 0.15; candidates use distinct colours and labels `Candidate 1..n`; `fitBounds` to all drawn geometry.
- Feature with null geometry: if `fields.lat`/`fields.lon` parse as numbers inside `US_BOUNDS`, centre a marker there with banner `No boundary on file for this parcel`; otherwise `render` raises `MapError` matching `"no boundary"`.
- Any `area_check` `mismatch` adds a visible warning banner and a `warnings` entry.
- Footer: `Imagery date may differ from the parcel record. Recorded owner is not necessarily the beneficial owner.`

- [ ] **Step 1: Write failing tests**:
  - `test_render_writes_page_and_summary(tmp_path)` — single feature with `ll_gissqft=expected_sqft()`, `owner="Example LLC"`; summary `features == 1`, area status `ok`; HTML contains `leaflet@1.9.4`, `integrity="sha256-`, `World_Imagery`, `Esri`, `Example LLC`.
  - `test_page_has_no_token_and_only_allowed_hosts` — `re.findall(r"https?://([^/\"'\s]+)", html)` ⊆ `{"unpkg.com", "server.arcgisonline.com"}`; `"token" not in html.lower()`.
  - `test_hostile_record_text_is_inert` — owner `'</script><img src=x onerror=alert(1)>"\''`; HTML contains no `</script><img` and no `<img`.
  - `test_multiple_features_require_explicit_choice` — two features, no flags → `MapError`; `index=1` draws one; `all_candidates=True` draws two and HTML contains `Candidate 2`.
  - `test_null_geometry_with_point_and_without` — `geometry=None, lat="39.9", lon="-75.03"` → banner text present; neither → `MapError` matching `"no boundary"`.
  - `test_mismatch_adds_warning` — `ll_gissqft=1.0` → `warnings` non-empty and banner in HTML.
  - `test_render_refuses_overwrite(tmp_path)` — pre-existing output stays byte-identical; `replace=True` overwrites.
  - `test_cli_render_and_errors(tmp_path)` — `subprocess.run([sys.executable, MAP, "render", ...])`: exit 0 and stdout JSON parses; invalid JSON input → exit 1, stderr one line, no traceback.
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_regrid_map.py -q` — expected: new tests FAIL.
- [ ] **Step 3: Implement** the Interfaces and page requirements.
- [ ] **Step 4: Run** tests — all pass; Ruff check/format clean; manually open one generated page is **not** required.
- [ ] **Step 5: Commit** `git commit -m "feat: render interactive satellite parcel maps"`.

### Task 3: Skill, packaging, docs, version

**Files:**
- Create: `plugins/regrid-research/skills/property-research/references/map.md`
- Modify: `plugins/regrid-research/skills/property-research/SKILL.md`, `scripts/build_claude_plugins.py:47-49`, `plugins/regrid-research/evals/discovery.py:15-25`, `plugins/regrid-research/.claude-plugin/plugin.json`, `plugins/regrid-research/README.md`, `README.md`, `changelog.md`
- Test: `tests/test_claude_plugins.py`, `tests/test_regrid_map.py`

**Interfaces:**
- Consumes: CLI from Task 2.

- [ ] **Step 1: Write failing tests**:
  - In `tests/test_claude_plugins.py`, extend the workflow-helper packaging test pattern: `map.py` present and identical in all three archives (`skills/property-research/scripts/map.py`, standalone `property-research/scripts/map.py`).
  - `test_extracted_map_helper_renders(tmp_path)` in `tests/test_regrid_map.py` — build archives (pattern at `tests/test_regrid_workflow.py:249-262`), run extracted standalone `map.py render` on a fixture; exit 0, output exists.
  - `test_skill_links_map_reference` — `SKILL.md` contains `references/map.md`; `map.md` mentions `scripts/map.py`, `--all-candidates`, and `verbatim`.
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_claude_plugins.py tests/test_regrid_map.py -q` — new tests FAIL.
- [ ] **Step 3: Implement**:
  - Builder ships `scripts/map.py` alongside `workflow.py`; add `"scripts/map.py"` to discovery `ALLOWLIST`.
  - `SKILL.md` (stay concise): in the resource list add "Map or boundary requested: [map guide](references/map.md)"; amend step 3 so geometry is kept when a map is requested; keep "no geometry dumps in chat".
  - `map.md` (≤ ~60 lines): when to map (confirmed → `--feature`/single; ambiguous → `--all-candidates`; unmatched/error → no map); save the decoded `execute-request` JSON **verbatim** to a file (no reformatting or coordinate trimming); run `python3 <skill>/scripts/map.py render RESPONSE.json OUTPUT.html [--retrieved-at ISO]`; read the stdout summary and report any area `mismatch` warning instead of presenting the boundary as verified; present the page (Claude Code: give the file path / open in browser; Claude apps: show the HTML as an interactive page); the page loads Leaflet from unpkg and imagery from Esri, which see the map area but no record data; no token ever goes in the page; if the first live response lacks `geometry`, stop and report it (open risk in spec).
  - Version `0.6.0` in `plugin.json`, both READMEs (archive names), changelog line 5; changelog `### Added` entry for the map helper; plugin README feature line.
- [ ] **Step 4: Run** `make check`, `.venv/bin/python scripts/build_claude_plugins.py`, `.venv/bin/python plugins/regrid-research/evals/run.py validate --suite all`, `claude plugin validate ./plugins/regrid-research --strict` — all pass.
- [ ] **Step 5: Commit** `git commit -m "feat: add satellite parcel maps to Regrid Research 0.6.0"`.
