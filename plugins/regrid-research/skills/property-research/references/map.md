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

1. Save the decoded `execute-request` JSON verbatim to `RESPONSE.json`. Do not
   reformat, re-indent, or trim coordinates; the helper checks the boundary against
   the recorded area.
2. Render with the bundled helper, using the skill directory:

   ```
   python3 <skill>/scripts/map.py render RESPONSE.json OUTPUT.html [--retrieved-at ISO]
   ```

   Add `--feature N` or `--all-candidates` as above; passing both is an error.
   Add `--replace` only to overwrite a file the user asked to replace.
3. Read the JSON summary on stdout. If `warnings` reports an area `mismatch`, say so
   and do not present the boundary as verified. On exit 1, report the one-line stderr
   message; do not edit the saved response to make it pass.
4. Present the page:
   - Claude Code: give the absolute path to `OUTPUT.html` and offer to open it in a browser.
   - Claude apps: show the HTML as an interactive page.

## Limits

- The page loads Leaflet from unpkg.com and imagery from Esri (server.arcgisonline.com).
  Those services see the map area, not record data.
- No token goes in the page, the command, or the saved response. The helper reads no
  credentials and makes no network requests.
- If the first live response lacks `geometry`, stop and report it as an open risk.
  Do not assume a boundary exists.
- Keep geometry out of chat; the page is the deliverable.
