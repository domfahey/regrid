---
description: Look up a US property by address and show its parcel on a satellite map
argument-hint: <US street address>
---

Map the US property at: $ARGUMENTS

In Claude Code, `<skill>` is `${CLAUDE_PLUGIN_ROOT}/skills/property-research` (quote the full script path when you run it); elsewhere it is
the property-research skill folder (the folder that holds `SKILL.md`).
Use the property-research skill and its Regrid MCP tools. Scope is US parcels only; for
a non-US address, follow the skill's scope rule and stop.

1. Make one request: the skill's address lookup with one record (`limit=1`). Do not
   add searches, retries or other requests, and map only the matched parcel.
2. Check the match as the skill requires. If the result is unmatched or an error, say
   so and stop; do not render a map.
3. Save the decoded `execute-request` JSON verbatim to a response file.
4. Render it with `python3 "<skill>/scripts/map.py" render`, following
   `<skill>/references/map.md` and map the single returned parcel.
5. Give a short summary: matched address, owner and parcel identifiers if present, the
   data date, and any warning from the helper (including an area mismatch).
6. Present the page as `<skill>/references/map.md` describes: the absolute path in Claude Code,
   or the interactive page in the Claude apps.

With neighbours: only if the user asked. State "one request, up to 25 records", then follow
the neighbours section of `<skill>/references/map.md` and the ledger rules in
`<skill>/references/batch.md` (neighbour requests), and render with `--neighbours`.

Never put the Regrid token in chat, command arguments, the saved response, or the page.

If no address was given, ask for one.
