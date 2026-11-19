# Parcel Satellite Map: Design

Date: 2026-11-18. Status: draft for approval. Scope: Regrid Research plugin, US parcels only.

## Intent

The typical task is: search by street address, pull the property record, get the parcel
boundary, and look at that boundary on satellite imagery in an interactive map the user
clicks around in themselves. Today the property-research skill discards the boundary
("omit geometry", "avoid geometry dumps") and has no way to draw anything. This makes
address → record → boundary → satellite map the skill's primary path.

## Goals

- One bounded address lookup supplies both the record and the boundary. The `/parcels/address`
  response already carries `parcels.features[].geometry` (Polygon or MultiPolygon, nullable),
  so the map costs no extra API request.
- A self-contained interactive HTML page: satellite basemap, parcel outlined, zoomed to fit,
  click popup with key facts.
- Works in Claude Code (file opened in a browser) and in Claude apps (same HTML shown as an
  interactive page).
- Coordinates on the map are exactly those in the response, and corruption is detected.

## Non-goals

- Non-US parcels (project scope).
- Static images, PDFs, or GIS export files.
- Regrid's parcel-line tile overlay for neighbouring lots (requires a token in the page; revisit
  separately with Regrid's temporary typeahead token).
- Maps of many parcels from batch runs.

## Anti-goals (failure even if it "works")

- Any Regrid token, header, or token-bearing URL in the page or helper output.
- Sending property data to third parties. The page loads Leaflet from a CDN and imagery tiles
  from Esri; tile requests reveal the viewed area but no record data. Nothing else is fetched.
- Drawing a wrong or silently altered boundary, or presenting an unconfirmed candidate as the
  requested property.
- An extra billable request just to get geometry.

## Constraint: the response passes through Claude once

Through MCP, `execute-request` output lands in Claude's context; the helper cannot read it
directly. Claude must save the decoded response JSON to a file verbatim, once. The skill tells
it to copy the response unchanged (no reformatting, no trimming of coordinates). The helper then
guards against transcription errors:

- Valid GeoJSON Polygon/MultiPolygon structure, closed rings, finite numbers.
- Every coordinate within a US bounding box (including Alaska, Hawaii, territories).
- Computed geodesic area compared with the record's `ll_gissqft` (Regrid computes it from the same
  geometry). A mismatch beyond tolerance is reported prominently and the page shows a warning
  banner; it is not silently drawn as authoritative.

## Approaches considered

- **A. Bundled map helper script (chosen by the user).** Standard-library Python, like
  `workflow.py`, renders the page from the saved response. Exact coordinates, testable,
  consistent output.
- B. Claude hand-writes the page from a template each time. No new code, but coordinates are
  re-typed, output varies, and nothing is testable.
- Ruled out: Regrid tile overlay in the page (token leak); posting GeoJSON to an online viewer
  (third-party disclosure).

## Design

**Helper:** `skills/property-research/scripts/map.py`, Python 3.10+, standard library only, no
network or credential access.

```sh
python3 scripts/map.py render RESPONSE.json OUTPUT.html [--feature N] [--replace]
```

- Input: the decoded `/parcels/address` response (object with `parcels.features`).
- Refuses to overwrite `OUTPUT.html` unless `--replace` (mirrors `workflow.py save`); writes atomically.
- Prints a short JSON summary to stdout: features drawn, area check result, warnings. Exit code is
  non-zero for unusable input; a failed area check is a warning, not a failure.
- All record text is HTML-escaped; record content is untrusted data.

**Page:**

- Leaflet pinned to an exact version from a CDN with subresource integrity.
- Esri World Imagery basemap (no API key) with its required attribution.
- Parcel outline in a high-contrast colour with a light translucent fill, map fit to its bounds.
- Popup/side panel: headline address, recorded owner, parcel number, Regrid path, data refresh
  date, GIS acreage, and retrieval time when supplied. Missing values read "not in record".
- Footer note: imagery date differs from the parcel data date; recorded owner is not beneficial owner.
- Null geometry: page still renders centred on the record's point if one exists, with a clear
  "No boundary on file for this parcel" banner; otherwise the helper reports it and writes no map.

**Match status governs the map:**

- Confirmed match: one outlined parcel.
- Ambiguous (several plausible parcels or unresolved unit): every returned candidate drawn in
  distinct colours, labelled "candidate", none presented as the requested property.
- Unmatched or error: no map; the answer explains why.

**Skill changes:**

- `SKILL.md`: map requests become part of the main lookup path; keep geometry when a map is
  requested; never dump raw geometry into the chat answer.
- New `references/map.md`, loaded only when a map is requested: how to save the response
  verbatim, run the helper, present the result in each host, and read its warnings.
- Packaging: `build_claude_plugins.py` and the discovery `ALLOWLIST` ship `scripts/map.py`.
- Plugin version 0.6.0 (new feature); README and changelog updated.

**Tests:** synthetic Polygon, MultiPolygon, hole, null geometry, malformed geometry, out-of-US
coordinate, area mismatch, multi-candidate, HTML-escaping of hostile record text, overwrite
refusal, no token-like strings in output, and running the helper extracted from the packaged ZIP.

## Open risk

The address endpoint does not list `return_geometry`; the response schema includes geometry, but
whether it is returned by default has not been observed live. The first authenticated lookup
(user-authorised, billable) must confirm it. If geometry is absent, stop and revisit.

## Left to the builder

Outline styling, exact area tolerance (start around 5%), US bounding-box values, output file naming
convention, and whether to add Esri's place-label overlay.
