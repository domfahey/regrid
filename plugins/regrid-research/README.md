# Regrid Research for Claude

Personal plugin wrapping Regrid's hosted MCP with property-research instructions.
Not an official Regrid plugin. Includes `/regrid-research:property-research` and
`/regrid-research:setup`. No SDK installation is needed.

## Choose a package

All packages use the same canonical `skills/property-research/` source, including
its references. Setup is separate from research; choose only one connection.

| Package in `dist/` | Use |
| --- | --- |
| `regrid-research-cowork-0.4.0.zip` | Cowork plugin with a remote HTTP connector declaration; credentials configured in Claude |
| `regrid-research-claude-code-0.4.0.zip` | Claude Code plugin with the local `mcp-remote` bridge and environment placeholder |
| `regrid-property-research-skill-0.4.0.zip` | Standalone research skill for an already configured Regrid connector |

The two plugin packages have the same plugin name and skills; install one variant
per host rather than enabling both. The old `0.1.0` and `0.2.0` archives are superseded.

## Connect in Cowork

Upload `regrid-research-cowork-0.4.0.zip` under Customize > Plugins > Add > Upload
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
   the plugin, upload `regrid-property-research-skill-0.4.0.zip` through Claude's
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

`regrid-research-claude-code-0.4.0.zip` contains the research and setup skills plus a local
stdio bridge using `npx -y mcp-remote`, the Regrid MCP URL, and the
`x-regrid-token: ${REGRID_TOKEN}` header. Node/npx and the host environment token
are required. Do not enable this bridge alongside an equivalent active connector.

From the repository root, after installing uv and Claude Code:

```sh
uv run --no-cache --env-file .env --no-sync claude --plugin-dir ./plugins/regrid-research
```

This loads credentials into the host process without printing them or modifying
the plugin. Keep `.env` outside the plugin. Use `/mcp` and then
`/regrid-research:setup` to verify access. Do not enable a duplicate Regrid bridge.

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

## Behavior and limits

Single-property lookups start with one result, validate the address, and report
the recorded owner and source freshness. Larger searches require a bounded scope.
These are skill instructions, not server-enforced spending limits. Regrid's
account limits and permissions still apply. Returned records consume API usage.
Regrid requires disabling model training/data sharing before using its data with AI.

## Validation and acceptance

Build all three artifacts from the repository root:

```sh
.venv/bin/python scripts/build_claude_plugins.py
.venv/bin/python -m pytest tests/test_claude_plugins.py
claude plugin validate ./plugins/regrid-research --strict
```

The builder uses a file allowlist: manifest, MCP config, README, the two skill
entrypoints, Markdown/JSON references, and the explicitly selected offline
`property-research/scripts/workflow.py` helper. It excludes secret
filenames and unrelated files, rejects selected symlinks and recognizable embedded
credentials, and produces deterministic ZIPs. This is a packaging safeguard, not
a general secret scanner. Never place a real credential in the source tree.

Version 0.4.0 adds metadata-first filesystem discovery trials, without-skill
baselines, distractor skills, model/CLI identifiers, and read traces. See the
[discovery evaluation instructions](evals/README.md). Checkpoint diagnostics now
identify structural paths without exposing values; `workflow.py save INPUT DEST`
validates before writing and requires `--replace` to overwrite. Python 3.10+
and the standard library are sufficient.

Validation gates are separate:

- Archive integrity, shared skill contents, transport separation, exclusions,
  and reproducibility are covered by the offline packaging tests.
- Claude's validator checks structure; it does not establish runtime behavior.
- Cowork import, connector availability, and authenticated Cowork lookup remain
  **not verified in this account** until performed in an actual Cowork session.
- Live MCP tool-schema evidence and offline behavior evaluations do not prove
  Cowork's account-specific header beta or header-name approval is available.

For 0.4.0, `make check` passes 692 tests, including 29 helper tests and 16
discovery/runner tests. SDK coverage is 98.16% (it excludes bundled scripts).
Both extracted plugins and the standalone skill pass strict Claude structural
validation. The four local HTTPS E2E tests were not run for this skill change.

The [0.4.0 acceptance report](evals/results/authoring-0.4.0-report.json) records
the current external blockers: Claude CLI OAuth has expired and cannot refresh;
Claude Desktop inspection failed with `cgWindowNotFound`. No new Claude model
trial, baseline comparison, Cowork import, or authenticated Cowork lookup is
claimed. After local `claude auth login`, use the discovery runner documented in
[evals/README.md](evals/README.md), then grade each retained trace.

Historical 0.3.0 verification: `make check` passed 671 tests, including 24 workflow-helper regressions
and seven packaging tests. The SDK coverage gate remains 98.16%; that percentage
covers `src/regrid`, not the bundled helper. Workflow tests exercise shared budgets,
uncertain reservations, evidence consistency, caller IDs, explicit retries,
checkpoint round trips, and the helper extracted from the standalone ZIP.
Run all research and composition fixtures with:

```sh
python3 plugins/regrid-research/evals/run.py validate --suite all
python3 plugins/regrid-research/evals/run.py packet --suite all
```

Fixture validation checks the inputs, not model behavior. The separate blinded
evaluation retains transcripts and semantic grading under `evals/results/`.
The final 0.3.0 run passed all 19 scenarios and 63 criteria; see the repository's
[final report](evals/results/final-report.json). It validates five handoffs, one
proposed checkpoint, and three proposed calls. An initial missing explanation
about authorization after budget exhaustion was retained, corrected, and retested.
These are offline simulated decisions, not live downstream app writes or Cowork
acceptance tests, and no baseline comparison was run.

Historical 0.2.0 verification (October 27, 2026): `make check` passed 646 tests with 98.16% combined
line/branch coverage; both extracted plugin variants passed strict Claude
validation. Direct MCP header authentication passed a usage-only request without
retrieving parcels. The [blinded offline evaluation report](evals/results/forward-report.json)
records 13/13 scenarios and 40/40 criteria passed, with the evaluator transcript
and content hashes retained. These evaluations use a synthetic tool double; the
20-address case checks the first request and continuation plan, not a full live
batch. No without-skill baseline was run. Evaluation files are repository-only
and are not shipped in the plugin ZIPs; see the repository copy of this README
for that report. The packaged live tool reference distinguishes executed calls
from the schema-checked address example.

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
