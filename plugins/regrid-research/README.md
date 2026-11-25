# Regrid Research for Claude

Personal plugin wrapping Regrid's hosted MCP with property-research instructions.
Scope is US parcels only; Canadian, Global, and Batch APIs are not used.
Not an official Regrid plugin. Includes `/regrid-research:property-research` and
`/regrid-research:setup`. No SDK installation is needed. For a requested map or
boundary, the research skill renders an offline satellite page; see the
[map guide](skills/property-research/references/map.md).

## Choose a package

All packages use the same canonical `skills/property-research/` source, including
its references. Setup is separate from research; choose only one connection.

| Package in `dist/` | Use |
| --- | --- |
| `regrid-research-cowork-0.9.7.zip` | Cowork plugin with a remote HTTP connector declaration; credentials configured in Claude |
| `regrid-research-claude-code-0.9.7.zip` | Claude Code plugin with a native HTTP MCP server and environment placeholder |
| `regrid-property-research-skill-0.9.7.zip` | Standalone research skill for an already configured Regrid connector |

The two plugin packages also ship the `/regrid-research:address-map <US street
address>` command: one address request (plus one optional neighbours request), the
saved response rendered as a satellite map and summarised. The standalone skill
archive has no commands.

The two plugin packages have the same plugin name and skills; install one variant
per host rather than enabling both. Earlier archive versions are superseded.

## Connect in Cowork

Upload `regrid-research-cowork-0.9.7.zip` under Customize > Plugins > Add > Upload
plugin. Its connector declaration contains only the remote URL, not a local
process or credential. Add/connect Regrid from the plugin's Connectors tab, or
configure the same URL through Customize > Connectors:

1. Open Customize > Connectors > Add > Custom > Web.
2. Name it Regrid and enter `https://support.regrid.com/mcp`.
3. Choose **No sign-in** for API-key authentication.
4. If **Request headers** is available, add a required custom header named
   `x-regrid-token`. Enter the actual token privately in the settings value field,
   not `${REGRID_TOKEN}` and not in chat. Claude sends the value literally.
5. Save and enable the connector in a new Cowork task. Ask it to check API usage
   without retrieving parcels; public documentation access alone does not verify auth.
6. Run `/regrid-research:setup`, then ask who owns a specific address once
   authenticated access is verified. If using the standalone skill instead of
   the plugin, upload `regrid-property-research-skill-0.9.7.zip` through Claude's
   skill interface and ask for the same lookup with your connected Regrid tools.

**Request-header authentication is a limited beta.** If the section is absent,
this setup is unavailable for your organization. Custom header names also need
Anthropic approval: if `x-regrid-token` is rejected, contact Claude support or
verify a supported alternative with Regrid rather than guessing another header.
On Team/Enterprise an organization owner may need to add the connector.

Without request-header access, an OAuth-enabled remote gateway that securely
holds the Regrid token is an alternative, but it requires separate implementation
and hosting. This repository does not provide that gateway.

Cowork does not automatically inherit the repository's `.env` or the separate
Claude Desktop Developer `claude_desktop_config.json`. That JSON config is for
Desktop chat, not Cowork. Claude Code `userConfig` prompts are not a Cowork fix.
No credentials belong in the plugin archive or skill. These instructions are
based on current documentation; Cowork import and live authentication have not
been verified in this account.

## Connect in Claude Code

`regrid-research-claude-code-0.9.7.zip` contains the research and setup skills plus a native
HTTP MCP server (`"type": "http"`) for the Regrid MCP URL with the
`x-regrid-token: ${REGRID_TOKEN}` header, which Claude Code expands from the host
environment. No Node/npx or helper process is needed, and the token never appears in
process arguments. Do not enable this server alongside an equivalent active connector.

From the repository root, after installing uv and Claude Code:

```sh
uv run --no-cache --env-file .env --no-sync claude --plugin-dir ./plugins/regrid-research
```

This loads credentials into the host process without printing them or modifying
the plugin. Keep `.env` outside the plugin. Use `/mcp` and then
`/regrid-research:setup` to verify access. Do not enable a duplicate Regrid MCP server.

## Compose with other workflows

The research skill accepts existing evidence and a caller's requested output
format. Its [versioned result contract](skills/property-research/references/result.schema.json)
separates lookup success from address-match confidence, keeps one row per input,
and preserves distinct candidates and provenance. Use the
[composition guide](skills/property-research/references/composition.md) when
passing results to a spreadsheet, report, CRM, or entity-research workflow.
A research request does not authorize an external CRM write or establish an
LLC's beneficial owners.

For multi-stage or interrupted batches, use the
[batch guide](skills/property-research/references/batch.md). One shared budget
tracks attempts, returned records, and uncertain reservations across stages.
The bundled stdlib-only `scripts/workflow.py` helper validates handoffs and
supports explicit checkpoint saving and resume planning without network access.
No checkpoints are written automatically, and optional downstream skills are
not required for a direct answer.

From the repository root, prepare a real `1.0` or `1.1` result envelope and obtain
a requested save destination. Use `1.1` for tagged search queries, diagnostic
attempts, or reconciliation; explicitly upgrade existing `1.0` workflows with
`upgrade_workflow` rather than changing the version field by hand:

```sh
python3 plugins/regrid-research/skills/property-research/scripts/workflow.py validate /path/to/result.json
python3 plugins/regrid-research/skills/property-research/scripts/workflow.py save /path/to/result.json /path/to/checkpoint.json
python3 plugins/regrid-research/skills/property-research/scripts/workflow.py pending /path/to/checkpoint.json
```

Use Python 3.10+ and substitute your actual paths. Fix the reported structural
field/invariant and revalidate before resuming. Saving validates before writing;
existing destinations require an explicitly requested update with `--replace`.
`pending` lists eligible input IDs; it does not retrieve parcels. The synthetic
example is a format guide, not real property evidence.

## Contract compatibility

Handoff version `1.0` stays readable, and version `1.1` adds explicit
query types for scoped owner searches, points, bounding-box areas, and filters.
Existing workflows stay at `1.0` unless explicitly upgraded. The synthetic example
still demonstrates `1.0`; use the schema and composition guide for `1.1` shapes.

Setup inherits offline constraints and shared request limits. Diagnostic API calls
consume that same allowance without marking property inputs attempted. Reconciliation
requires a caller-verified receipt for the specific uncertain attempt, preserves
its original history, and does not retry it. The offline helper validates receipt
structure and linkage; it cannot authenticate provider evidence.

Simple evidence-based prose loads composition guidance only; schema, example, and
raw tool catalogs are conditional resources. See the skill's resource map.

## Behavior and limits

Single-property lookups start with one result, validate the address, and report
the recorded owner and source freshness. Larger searches require a bounded scope.
These are skill instructions, not server-enforced spending limits. Regrid's
account limits and permissions still apply. Returned records consume API usage.
Regrid requires disabling model training/data sharing before using its data with AI.

## MCP server coverage

A short summary. The source of truth is
[`mcp-tools.md`](skills/property-research/references/mcp-tools.md) (MCP tools and
endpoints) and [`cli.md`](skills/property-research/references/cli.md) (CLI commands);
check them when this table and a reference differ.

The plugin has two skills, `property-research` and `setup`, plus the
`/regrid-research:address-map` command (Claude Code and Cowork archives only; the
standalone skill archive has no commands), which drives `property-research`.

**MCP tools.** Only `execute-request` makes API calls; the other six use no request
allowance. `setup` inspects tool schemas, may make one documentation discovery call,
and, only when a non-billable usage operation is exposed and one request remains,
makes at most one `/usage` check through `execute-request`.

| MCP tool | What it does |
| --- | --- |
| `list-specs` | Lists the API specs. The first covers US and Canada (`/ca/...`); the skill uses only its US routes. The Global and Batch specs are not used |
| `list-endpoints`, `search-endpoints` | List the paths in one spec, or find a path across specs |
| `get-endpoint` | Gets an endpoint's exact parameters before a call |
| `search`, `fetch` | Search and read Regrid's documentation |
| `execute-request` | Makes the API call (counts toward the request budget) |

**Endpoints reached through `execute-request`** (GET only, US routes, except read-only POST geometry search on `/parcels/point` and `/parcels/area`; every other POST is forbidden):

| Endpoint | Purpose |
| --- | --- |
| `/parcels/address`, `/parcels/apn`, `/parcels/owner` | Address, APN (within a county) and owner lookups |
| `/parcels/point`, `/parcels/area`, `/parcels/query` | Point or radius, GeoJSON area, and field-filter searches |
| `/parcels/{ll_uuid}`, `/parcels/path` | Lookup by Regrid ID; refresh by Regrid path |
| `/parcels/typeahead` | Address suggestions. Enterprise product; trial tokens are limited to 7 counties |
| `/schemas/*` | Field definitions, only when the bundled catalog lacks the field |
| `/usage`, `/usage/detailed` | One setup authentication check; remaining-lookups questions only |

`/verse` (county pull dates) is CLI-only, through `regrid freshness`. Over MCP the
skill reports each parcel's `ll_last_refresh` instead.

**Options.**

| Option | Where | Notes |
| --- | --- | --- |
| Premium dataset flags (`return_zoning` and the like) | Address, APN, owner, point, area, query, Regrid ID (`/parcels/{ll_uuid}`), `/parcels/path` | Only with the user's authorization ([premium datasets](skills/property-research/references/premium.md)) |
| `return_count`, `return_geometry`, `offset_id` | Point, area and query (and `return_geometry` on `/verse`) | `return_count` counts before pulling; POST `/parcels/point` omits `offset_id` and `return_geometry`; MCP research may page with `offset_id` within the agreed budget; the CLI form is `--max-records` |

**Offered by the server but deliberately not used:** POST `/report` (files a data
issue with Regrid), `/client_token/typeahead` (creates a temporary token), the Global
and Batch specs (out of scope), and the `/ca/*` routes (existing Canadian routes
stay in the SDK but the skill does not use them).

## Validation and acceptance

Status for 0.9.7:

- Passed: structural validation (`claude plugin validate --strict`), packaging
  tests, eval fixture/rubric validation, and the offline `make check` suite.
- Earlier browser check (`0.9.3`): the satellite map rendered in a plain browser
  with synthetic data (imagery, outlines, info panel and Esri credit shown; no
  console errors). Not re-rendered in a browser for `0.9.7` after `map.py`
  hardening; see `evals/results/map-hosts-0.9.7.json`.
- Passed (live, authorized, `2026-11-24`): direct Streamable HTTP `/mcp` check
  against `https://support.regrid.com/mcp` (`x-regrid-token` header) verified
  `tools/list` (`tools.json` parity), `list-specs`, authenticated `GET /usage`, and
  `POST /parcels/area` with `return_parcels=true` (`limit=1`, returning `area` + 1
  parcel feature with geometry and fields); `make live` also passed on SDK `0.5.0`.
- Earlier live checks (authorized, `2026-11-19` / `2026-11-20`): `make live-full`
  checked every read-only endpoint (26 requests) and one POST point request
  verified `return_parcels=true`.
- Not run: Claude Code, Claude apps and Cowork host UI/map checks (and host MCP
  connector import); a fresh browser map render for `0.9.7`; and model or Cowork
  acceptance.

Earlier verification logs (0.2.0 to 0.5.0) live in the repository's
[evals README](https://github.com/domfahey/regrid/blob/main/plugins/regrid-research/evals/README.md#historical-verification).
The helper uses only the standard library; `jsonschema` is needed only for
development checks.

Build all three artifacts from the repository root:

```sh
.venv/bin/python scripts/build_claude_plugins.py
.venv/bin/python -m pytest tests/test_claude_plugins.py
claude plugin validate ./plugins/regrid-research --strict
```

The builder uses a file allowlist: the manifest, MCP config, README, `PRIVACY.md`, `LICENSE`,
both skills' `SKILL.md`, their references (`*.md`, `*.json`), the bundled helpers
`workflow.py`, `map.py`, `fields.py` and `freshness.py` under
`property-research/scripts/`, and `commands/*.md` (Claude Code and Cowork archives
only). The standalone skill archive carries the skill folder with its own
`LICENSE`. It excludes secret filenames and unrelated files, rejects selected
symlinks and recognizable embedded credentials, and produces deterministic ZIPs.
This is a packaging safeguard, not a general secret scanner. Never place a real
credential in the source tree.

Validation gates are separate:

- Archive integrity, shared skill contents, transport separation, exclusions,
  and reproducibility are covered by the offline packaging tests.
- Claude's validator checks structure; it does not establish runtime behavior.
- Cowork import, connector availability, and authenticated Cowork lookup remain
  **not verified in this account** until performed in an actual Cowork session.
- Live MCP tool-schema evidence and offline behavior evaluations do not prove
  Cowork's account-specific header beta or header-name approval is available.

After importing, check these cases:

- Setup: tools, documentation, and authentication reported separately; no parcel charged.
- Exact address: one bounded lookup, address verified, owner and freshness reported.
- Ambiguous address: clarification rather than an unsupported ownership claim.
- Missing/invalid token: sanitized failure, no retry loop or request for a chat token.
- Broad owner search: obtain geography and total record budget before retrieval.
- Missing fields: report unknown values rather than inventing them.

References checked October 27, 2026:

- [Claude plugin structure and testing](https://claude.com/docs/plugins/build)
- [Installing plugins](https://claude.com/docs/plugins/overview)
- [Claude Code plugin manifest reference](https://code.claude.com/docs/en/plugins-reference)
- [Regrid MCP documentation](https://support.regrid.com/docs/mcp-server)
- [Custom connector authentication and request-header beta](https://claude.com/docs/connectors/custom/add-unlisted#authenticate-with-request-headers)
