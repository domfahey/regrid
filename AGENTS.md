# Repository Guidelines

## Project Structure & Module Organization

Python source lives in `src/regrid/`. `client.py` owns HTTPX transport, authentication, and raw responses; `endpoints.py` maps API operations. Strict request validation lives in `requests.py` and `config.py`. `models.py` defines Pydantic response models; `typed.py` exposes `TypedRegridClient`. `cli.py` and `__main__.py` provide command-line entry points. `offline/` holds the standard-library-only helpers (`map.py`, `fields.py`, `freshness.py`). They never import `regrid` and are the source of the skill's bundled scripts.

Tests live in `tests/`, grouped by module. Consult `README.md` for usage, `architecture.md` for design boundaries, and `REFERENCE.md` for supplied API details. Build artifacts belong in ignored `dist/`. Canonical Claude skills, contracts, helper scripts, and evaluation fixtures live in `plugins/regrid-research/`; `scripts/build_claude_plugins.py` builds the three plugin/skill archive variants.

## Scope

US parcel data only. Prioritize US endpoints; keep existing Canadian routes working
but do not extend them. Do not add Regrid Global (international) or Batch
Processing API support unless the user explicitly asks.

## Build, Test, and Development Commands

- `make install`: install the editable package and development dependencies using uv.
- `make format`: format Python with Ruff; `make lint` checks lint rules.
- `make typecheck`: run mypy on `src/`.
- `make check`: run lint, formatting checks, type checking, and coverage-gated mocked tests.
- `make e2e`: run CLI subprocess and local HTTPS tests; requires OpenSSL and localhost socket access.
- `uv build`: produce wheel and source archives.
- `.venv/bin/regrid --help`: inspect CLI commands without calling Regrid.
- `.venv/bin/python scripts/sync_skill_helpers.py [--check]`: copy `src/regrid/offline/*.py` into the skill's `scripts/`. Edit only the `src/regrid/offline/` source, never the skill copy; a test fails on drift.
- `.venv/bin/python scripts/generate_skill_fields.py [--check]`: regenerate the skill's `references/fields.json` after editing `src/regrid/data/parcel_fields.json`.

## Coding Style & Naming Conventions

Target Python 3.10+. Use four-space indentation, 100-character lines, and type annotations. Use `snake_case` for functions/modules and `PascalCase` for classes. Let Ruff manage formatting and imports.

Preserve dictionary responses and CLI JSON compatibility. CLI commands that call the API print `regrid: requests made: N` on stderr, counted with `RegridClient.request_count`. It is the last stderr line, except in `address-map` and `freshness`, which print it before their note and error lines; offline commands (`map`, `export`, `fields`) never construct a client. Check output paths before sending any request, and never overwrite a response file with its own output. Keep strict, endpoint-specific request models separate from forward-compatible response models. Retain unknown response fields and distinguish omitted values from explicit nulls.

## Testing Guidelines

Use pytest with `test_*.py` files and `test_*` functions. Add regression tests for behavior changes, especially request serialization, validation, and credential redaction. Use `httpx.MockTransport`; ordinary tests must not contact Regrid.

`make test` requires at least 95% combined line and branch coverage for `src/regrid`. `src/regrid/offline/` counts toward coverage. The skill-only `workflow.py` is tested but excluded. Windows CI runs the offline helper tests and the offline and freshness CLI tests (not `test_cli.py`, paging or address-map), so mark POSIX-only assertions with `skipif(os.name == "nt")`. Mark HTTPS integration tests `e2e`; they run separately. Report blocked tests explicitly rather than treating them as passed.

## Plugin Changes

Keep skill instructions concise and load references conditionally. Preserve legacy
handoff compatibility and shared request accounting; changes to the schema and
helper must agree. The SDK and plugin have independent versions.

- Build archives: `.venv/bin/python scripts/build_claude_plugins.py`.
- Focused checks: `.venv/bin/python -m pytest tests/test_claude_plugins.py tests/test_regrid_workflow.py tests/test_regrid_workflow_composition.py tests/test_regrid_map.py tests/test_skill_helper_sync.py tests/test_cli_docs.py tests/test_offline_fields.py tests/test_offline_freshness.py tests/test_cli_offline.py tests/test_cli_freshness.py`.
- Plugin commands live in `plugins/regrid-research/commands/`. They ship in the Claude Code and Cowork archives, not the standalone skill. `references/cli.md`'s command map is checked against the real CLI parser.
- Validate packet fixtures: `.venv/bin/python plugins/regrid-research/evals/run.py validate --suite all`.
- Validate plugin structure, when Claude CLI is installed: `claude plugin validate ./plugins/regrid-research --strict`.

Run `make check` after helper/schema changes; `make install` includes the development
JSON Schema validator. The shipped helper remains standard-library-only. Follow
[evals/README.md](plugins/regrid-research/evals/README.md) for discovery and
composability scenarios; the packet fixture command above does not execute those
model evaluations. Report fixture validation, structural checks, offline model
decisions, and actual Claude/Cowork acceptance separately. Record map host checks
in `evals/results/map-hosts-<version>.json` as `verified`, `failed` or `not_run`. Never label a skipped
or blocked gate passed. Do not invoke credentialed or model-billed evaluations
without task authorization. Keep generated ZIPs and credentials out of commits.

## Commit & Pull Request Guidelines

Follow the existing Conventional Commit style: `feat:`, `fix:`, or `docs:` with a concise description. Preserve unrelated changes and commit only authorized work.

PRs should explain behavior changes, compatibility effects, and verification results; link relevant issues. Update usage documentation and `changelog.md` for user-visible changes. Screenshots are unnecessary unless they clarify output.

## Security & Configuration

Never commit secrets. Use `REGRID_TOKEN` and placeholder-only `.env.sample`; local `.env` files are ignored. `make live` and `make doctor` explicitly load `.env` through uv. For authenticated CLI/API work, use `uv run --env-file .env --no-sync regrid ...` or `uv run --env-file .env --no-sync python ...`. Never display or inspect the token; load it only into the child process. The SDK and CLI do not load `.env` themselves. Do not log token-bearing URLs. Preserve bounded requests, disabled redirects, and explicit pagination/retries.
