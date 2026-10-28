# Changelog

User-visible changes are grouped by release using the categories from [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Version numbering follows [Semantic Versioning](https://semver.org/); the current `0.x` API remains under development.

No releases have been tagged in this repository. The Python SDK/CLI metadata version is `0.1.0`; the independently versioned Regrid Research plugin is `0.5.0`. These metadata versions do not establish published releases. Keep pending changes under Unreleased until an actual release is prepared.

## Unreleased

### Added

- MIT license, public contribution/security/conduct guides, issue and PR templates, pinned GitHub Actions CI, and dependency-update configuration.

- Claude Regrid Research plugin with a bounded property-research skill, setup diagnostics, and a token-free MCP bridge configuration; includes import instructions and acceptance checks.

- `make doctor` checks local `.env` presence and token configuration without revealing credentials or making API calls. Both `make doctor` and `make live` explicitly load `.env` through uv.

- Synchronous SDK and CLI covering all 33 operations in the supplied US/Canada OpenAPI contract, including public schemas, usage, reports, and temporary typeahead tokens.
- TileJSON, raster/vector and retina tile downloads, and UTFGrid retrieval through advertised metadata, with metadata reuse and same-origin enforcement.
- Opt-in `TypedRegridClient` with complete documented response structures and addon properties, lossless serialization, and shared `.raw` dictionary access.
- Versioned catalog of 169 US parcel fields with SQL types, tiers, coverage-column names, and selected verified queryability, source, standardization, and preferred-field metadata.
- Generated `ParcelFields` and opt-in `ParcelProperties.typed_fields`, preserving existing dictionary access, identifiers, unknown fields, and omitted/null distinctions.
- Optional SDK/CLI query validation with an explicit escape hatch for unknown fields; existing queries keep their default behavior.
- Opt-in `make live` smoke test: one-record lookup, premium datasets disabled, validation of the same response, before/after usage checks, and redacted output. Defaults to `24 pennbrook dr haddonfield nj 08033`; `REGRID_LIVE_ADDRESS` optionally overrides it.
- Development commands for installation, lint, formatting, typing, coverage-gated mocked tests, and separate local HTTPS E2E tests.
- Contributor, architecture, API coverage, parcel interpretation, and UTFGrid documentation; placeholder-only `.env.sample`.

### Changed

- Regrid Research 0.5.0 adds opt-in `1.1` query handoffs and explicit upgrades while retaining `1.0` compatibility; caller-verified per-attempt reconciliation preserves uncertain history. Setup diagnostic calls share the workflow request budget without consuming property records. Evidence-only prose avoids loading schemas/examples, and saved tool catalogs load only for unavailable or mismatched live schemas. New regression scenarios cover these composition boundaries; offline evaluations remain separate from Claude/Cowork acceptance.

- Regrid Research 0.4.0 adds metadata-first discovery trials with without-skill baselines and trace/model recording, direct resource links, qualified MCP names, safer actionable validation diagnostics, and an explicit checkpoint save CLI. The helper requires Python 3.10+ with only the standard library; `workflow.py save INPUT DEST` validates before saving and refuses existing destinations unless an explicitly requested update uses `--replace`. The [0.4.0 acceptance report](plugins/regrid-research/evals/results/authoring-0.4.0-report.json) records Claude model evaluations blocked by expired CLI authentication and Cowork import/authenticated lookup unverified because Desktop inspection was unavailable. Passing local tests and structural validation does not establish those acceptance gates.

- Regrid Research 0.3.0 adds composable structured results with independent lookup/match statuses, shared request/record budgets, supplied-evidence provenance, flexible presentation, and explicitly requested checkpoint/resume helpers. Adds downstream handoff evaluations and includes the offline helper in all package variants.

- Regrid Research 0.2.0 separates Cowork HTTP and Claude Code local-bridge packages while sharing one canonical skill and its live MCP references. Adds explicit match states, unit/multiple-parcel handling, finite-list budgets, conditional ownership answers, response reuse, reproducible packaging checks, and offline behavioral evaluations.

- Clarify Cowork web-connector authentication: limited request-header beta, custom-header approval, standalone skill setup, and separation from Desktop Developer JSON and the local Claude Code bridge.

- Adopt Pydantic v2 for strict endpoint-specific requests and optional response validation, retaining raw SDK dictionaries and CLI JSON output.
- Replace weak test assertions with exact SDK/CLI wire contracts, binary-output checks, and meaningful validation regressions. Generated parcel models are checked for drift during tests.
- Expand `.gitignore` for Python build/test artifacts, local research output, editor files, and macOS metadata while retaining `.env.sample`.

### Fixed

- Restrict automatic parcel-search limits to parcel routes so public address-schema requests receive no search parameters.
- Reject non-finite upstream JSON numbers before serialization can silently convert them to null.

### Security

- Store account tokens as `SecretStr` and mask temporary-token models unless explicitly exported.
- Sanitize request and response-validation failures without retaining input-bearing Pydantic exceptions.
- Reject unsafe UTFGrid URLs and replace metadata credentials with the configured client token.
- Keep local environment files and private keys out of Git. The live runner suppresses HTTP logging and prints no credentials, property details, response bodies, or exception text.

## Release Maintenance

SDK/CLI and plugin versions are independent. At release time, move only the relevant pending entries into a component-specific version heading dated `YYYY-MM-DD`; retain other pending work under Unreleased.

- For an SDK/CLI release, synchronize `pyproject.toml` and `src/regrid/__init__.py`.
- For a plugin release, update `plugins/regrid-research/.claude-plugin/plugin.json` and the documented archive names. Run `.venv/bin/python scripts/build_claude_plugins.py` to rebuild the Cowork, Claude Code, and standalone skill ZIPs in ignored `dist/`; all three archive versions derive from the plugin manifest. Validate the rebuilt artifacts and record model/Cowork acceptance separately from structural checks.

Describe user-facing changes rather than copying commit logs. Add repository comparison links when a remote and release tags exist; do not invent release dates or links.
