# Satellite parcel maps

Use this guide only when the user asks for a map, boundary, or parcel outline for
a US property. Scope is US parcels only.

## When to map

- Confirmed match: render the matched parcel. Pass `--feature N` (zero-based) when
  the response has several features; omit it for a single feature.
- Ambiguous match: render the candidates with `--all-candidates`, and present them
  as candidates, not as the requested property.
- Unmatched, error, or not assessed: do not render a map.

## Steps

1. Request the boundary with the lookup itself; never spend another request on it.
   On point, area, and query endpoints pass `return_geometry=true` (never `false`).
   Address, APN, owner, and Regrid ID lookups have no such flag.
2. Save the decoded `execute-request` JSON verbatim to `RESPONSE.json`. Do not
   reformat, re-indent, or trim coordinates; the helper checks the boundary against
   the recorded area.
3. Render with the bundled helper, using the skill directory:

   ```
   python3 <skill>/scripts/map.py render RESPONSE.json OUTPUT.html [--retrieved-at ISO]
   ```

   Add `--feature N` or `--all-candidates` as above; passing both is an error.
   Add `--replace` only to overwrite a file the user asked to replace.
4. Read the JSON summary on stdout. If any `area_checks[].status` is `mismatch` (each
   also appears in `warnings` as "area mismatch"), say so and do not present the
   boundary as verified. On exit 1, report the one-line stderr message; do not edit
   the saved response to make it pass.
5. Present the page:
   - Claude Code: give the absolute path to `OUTPUT.html` and offer to open it in a browser.
   - Claude apps: show the HTML as an interactive page.

Terminal users without MCP can use the CLI equivalents: `regrid address-map ADDRESS
OUTPUT.html` (one request) or `regrid map RESPONSE.json OUTPUT.html` (offline).

## Limits

- The page loads Leaflet from unpkg.com and imagery from Esri (server.arcgisonline.com).
  Those services see the map area, not record data.
- No token goes in the page, the command, or the saved response. The helper reads no
  credentials and makes no network requests.
- `"geometry": null` means no boundary is on file: the page marks the record's point
  and says so. A feature with no `geometry` field at all means boundaries were not
  returned; the helper exits 1. Report that, and re-request with geometry only if the
  user authorizes another request.
- Parcels whose Regrid path does not start with `/us/` are refused. Coordinates are
  checked against coarse US boxes that catch corruption but include border areas of
  Canada and Mexico.
- Keep geometry out of chat; the page is the deliverable.
