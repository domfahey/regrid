"""Keep references/mcp-tools.md in step with references/endpoints.json."""

from __future__ import annotations

import json
import re
from pathlib import Path

REFS = Path(__file__).resolve().parents[1] / (
    "plugins/regrid-research/skills/property-research/references"
)
DOC = (REFS / "mcp-tools.md").read_text(encoding="utf-8")
ENDPOINTS = set(json.loads((REFS / "endpoints.json").read_text(encoding="utf-8"))["endpoints"])
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
    assert mentioned
    for path in mentioned:
        if path.endswith("/*"):  # wildcard shorthand such as `/schemas/*`
            prefix = path[:-1]
            assert any(e.startswith(prefix) for e in ENDPOINTS), path
        else:
            assert path in ENDPOINTS or path in FORBIDDEN, path
