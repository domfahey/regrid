"""Keep references/mcp-tools.md in step with references/endpoints.json."""

from __future__ import annotations

import json
import re
from pathlib import Path

REFS = Path(__file__).resolve().parents[1] / (
    "plugins/regrid-research/skills/property-research/references"
)
DOC = (REFS / "mcp-tools.md").read_text(encoding="utf-8")
_ENDPOINTS_DATA = json.loads((REFS / "endpoints.json").read_text(encoding="utf-8"))["endpoints"]
ENDPOINTS = set(_ENDPOINTS_DATA)
FORBIDDEN = {"/report", "/client_token/typeahead"}
BACKTICKED = re.compile(r"`(/[^`\s]*)`")
# Slash-prefixed tokens in the doc that are path shapes, not endpoints.
NON_ENDPOINT_FORMS = {"/", "/{country}/...", "/<section>/<slug>", "/ca/...", "/us/nj/camden"}


def _choosing_table_paths() -> set[str]:
    section = DOC.split("## Choosing the endpoint", 1)[1].split("\n## ", 1)[0]
    paths: set[str] = set()
    for line in section.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        paths.update(BACKTICKED.findall(cells[1]))
    return paths


def test_choosing_table_matches_endpoints_json() -> None:
    table = _choosing_table_paths()
    assert table - ENDPOINTS == set(), "paths in the table but not in endpoints.json"
    assert ENDPOINTS - table == set(), "endpoints.json paths missing from the table"


def test_every_documented_path_is_known_or_forbidden() -> None:
    mentioned = set(BACKTICKED.findall(DOC)) - NON_ENDPOINT_FORMS
    assert {"/parcels/address", "/parcels/query", "/verse"} <= mentioned
    assert {"/report", "/client_token/typeahead"} <= mentioned  # forbidden paths are documented
    for path in mentioned:
        if path.endswith("/*"):  # wildcard shorthand such as `/schemas/*`
            prefix = path[:-1]
            assert any(e.startswith(prefix) for e in ENDPOINTS), path
        else:
            assert path in ENDPOINTS or path in FORBIDDEN, path


# --- tools table vs tools.json -------------------------------------------------------------
TOOLS = {
    t["name"]: t for t in json.loads((REFS / "tools.json").read_text(encoding="utf-8"))["tools"]
}
PREMIUM_DOC = (REFS / "premium.md").read_text(encoding="utf-8")
ENDPOINT_PARAMS = {
    path: {p["name"] for p in spec["parameters"]} for path, spec in _ENDPOINTS_DATA.items()
}


def _tools_table(doc: str) -> dict[str, tuple[set[str], bool]]:
    """Map tool name -> (required arguments, makes API requests) from the tools table."""
    section = doc.split("## All exposed tools", 1)[1].split("\n## ", 1)[0]
    rows: dict[str, tuple[set[str], bool]] = {}
    for line in section.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not line.startswith("|") or len(cells) < 4 or not cells[0].startswith("`regrid:"):
            continue
        name = cells[0].strip("`").removeprefix("regrid:")
        required = cells[1].split("; optional", 1)[0]  # optional arguments are not required
        rows[name] = (set(re.findall(r"`([^`]+)`", required)), "yes" in cells[-1].lower())
    return rows


def test_tools_table_matches_tools_json() -> None:
    table = _tools_table(DOC)
    assert set(table) == set(TOOLS), "tool names differ between the table and tools.json"
    for name, (required, api) in table.items():
        schema = TOOLS[name]["inputSchema"]
        assert required == set(schema.get("required", [])), f"required arguments: {name}"
        # tools.json marks the one tool that reaches the API as not read-only.
        assert api == (not TOOLS[name]["annotations"]["readOnlyHint"]), f"API request: {name}"


def test_tools_table_parser_detects_drift() -> None:
    mutated = DOC.replace("| `title`, `method`, `path` |", "| `title`, `method` |")
    assert mutated != DOC
    assert _tools_table(mutated)["get-endpoint"][0] == {"title", "method"}
    flipped = DOC.replace(
        "| No |\n| `regrid:list-endpoints`", "| **Yes** |\n| `regrid:list-endpoints`"
    )
    assert flipped != DOC and _tools_table(flipped)["list-specs"][1] is True
    assert _tools_table(DOC)["fetch"][0] == {"id"}  # optional `format` is excluded


# --- response options vs endpoints.json ----------------------------------------------------
OPTION = re.compile(r"\b(return_[a-z][a-z_]*|offset_id|radius)\b")


def _options_with_scope(doc: str) -> list[tuple[str, set[str]]]:
    """Return (option, endpoints it must exist on); an empty set means any endpoint.

    Table rows in "Choosing the endpoint" and paragraphs opened by a bold
    "**Name (`/path`).**" heading are tied to the paths they name.
    """
    found: list[tuple[str, set[str]]] = []
    table = (doc.split("## Choosing the endpoint", 1) + [""])[1].split("\n## ", 1)[0]
    for line in table.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.startswith("|") and len(cells) >= 2:
            paths = set(BACKTICKED.findall(cells[1])) & set(ENDPOINT_PARAMS)
            found += [(o, paths) for o in OPTION.findall(" ".join(cells[2:]))]
    before, sep, rest = doc.partition("## Choosing the endpoint")
    outside = (
        before + ("\n## " + rest.split("\n## ", 1)[1] if "\n## " in rest else "") if sep else doc
    )
    for para in outside.split("\n\n"):
        head = re.match(r"\*\*[^*]*\(`(/[^`]+)`\)\.\*\*", para)
        scope = {head.group(1)} if head else set()
        found += [(o, scope) for o in OPTION.findall(para)]
    return found


def _drifted(doc: str) -> list[str]:
    bad = []
    for option, paths in _options_with_scope(doc):
        targets = paths or set(ENDPOINT_PARAMS)
        if not any(option in ENDPOINT_PARAMS.get(p, set()) for p in targets):
            bad.append(f"{option} not on {sorted(paths) or 'any endpoint'}")
    return bad


def test_response_options_exist_in_endpoints_json() -> None:
    assert {"return_count", "offset_id", "radius"} <= {o for o, _ in _options_with_scope(DOC)}
    assert {"return_zoning"} <= {o for o, _ in _options_with_scope(PREMIUM_DOC)}
    assert _drifted(DOC) == []
    assert _drifted(PREMIUM_DOC) == []


def test_response_option_check_detects_drift() -> None:
    assert _drifted(DOC.replace("`return_custom_id=true`", "`return_bogus=true`")) != []
    # radius moved onto a row whose endpoint has no radius parameter
    assert (
        _drifted(
            DOC.replace(
                "| `/parcels/owner` | `owner` | `path` |",
                "| `/parcels/owner` | `owner` | `radius` |",
            )
        )
        != []
    )
    assert _drifted("## return_nonexistent\n") != []


def test_choosing_table_options_are_not_rescanned_unscoped() -> None:
    snippet = (
        "## Choosing the endpoint\n\n"
        "| Request | Path | Required | Scope parameters |\n"
        "| --- | --- | --- | --- |\n"
        "| Point/radius | `/parcels/point` | `lat` | `radius` |\n\n"
        "## Next\n\nNo options here.\n"
    )
    assert _options_with_scope(snippet) == [("radius", {"/parcels/point"})]


def test_drifted_handles_unknown_endpoint_path_without_keyerror() -> None:
    bad_doc = "**Bogus (`/parcels/nonexistent`).** `return_geometry=true`\n"
    assert _drifted(bad_doc) == ["return_geometry not on ['/parcels/nonexistent']"]


def test_post_area_example_omits_unverified_return_parcels_and_disables_stacked_and_premium() -> (
    None
):
    section = DOC.split("### Large geometry (POST search)", 1)[1].split("\n### ", 1)[0]
    match = re.search(r"```json\n(.*?)\n```", section, re.S)
    assert match is not None, "POST /parcels/area JSON example missing"
    payload = json.loads(match.group(1))
    har = payload["harRequest"]
    assert har["method"] == "POST"
    assert har["url"] == "https://app.regrid.com/api/v2/parcels/area"
    query = {item["name"]: item["value"] for item in har["queryString"]}
    assert "return_parcels" not in query
    assert query.get("return_stacked") == "false"
    for flag in (
        "return_zoning",
        "return_matched_buildings",
        "return_matched_addresses",
        "return_enhanced_ownership",
    ):
        assert query.get(flag) == "false", flag
    normalized = " ".join(section.split())
    assert "POST point accepts `return_parcels=true`; POST area remains unverified." in normalized
