# Regrid CLI

Use the CLI only in Claude Code, with `regrid` on PATH and `REGRID_TOKEN` already in
the environment. Inside the regrid repository, load `.env` into the child process:
`uv run --env-file .env --no-sync regrid ...`. Never read or print `.env` or the token.

## County pull dates (freshness)

`ll_last_refresh` on each parcel stays the default freshness answer over MCP. County
pull dates are not available over MCP; say they need the CLI. Report dates only and
never label data stale.

```
regrid freshness --path /us/<st>/<county> [--cache FILE] [--refresh]
```

stdout is JSON: `path`, `county`, `state`, `last_refresh`, `assessor_data_date`,
`usps_data_date`, `verse_retrieved_at`, `cache` (`hit` or `miss`). The `/verse`
response is cached in `~/.cache/regrid/verse.json` (`%LOCALAPPDATA%\regrid\verse.json`
on Windows) and reused unless `--refresh` is given or no cache exists.

## Ledger

The CLI is ledger-unaware. Before any command that can make a request, reserve an
attempt with `record_limit` 0: `reserve_attempt(doc, [], 0, kind="diagnostic")`.
The CLI prints `regrid: requests made: N` on stderr; complete the attempt from that
line (`complete_attempt(doc, attempt_id, "success", 0)`). A cache hit reports 0.
If the line is unreadable, mark the attempt `uncertain`; do not retry.
