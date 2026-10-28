# Repository Guidelines

## Project Structure & Module Organization

Python source lives in `src/regrid/`. `client.py` owns HTTPX transport, authentication, and raw responses; `endpoints.py` maps API operations. Strict request validation lives in `requests.py` and `config.py`. `models.py` defines Pydantic response models; `typed.py` exposes `TypedRegridClient`. `cli.py` and `__main__.py` provide command-line entry points.

Tests live in `tests/`, grouped by module. Consult `README.md` for usage, `architecture.md` for design boundaries, and `REFERENCE.md` for supplied API details. Build artifacts belong in ignored `dist/`.

## Build, Test, and Development Commands

- `make install`: install the editable package and development dependencies using uv.
- `make format`: format Python with Ruff; `make lint` checks lint rules.
- `make typecheck`: run mypy on `src/`.
- `make check`: run lint, formatting checks, type checking, and coverage-gated mocked tests.
- `make e2e`: run CLI subprocess and local HTTPS tests; requires OpenSSL and localhost socket access.
- `uv build`: produce wheel and source archives.
- `.venv/bin/regrid --help`: inspect CLI commands without calling Regrid.

## Coding Style & Naming Conventions

Target Python 3.10+. Use four-space indentation, 100-character lines, and type annotations. Use `snake_case` for functions/modules and `PascalCase` for classes. Let Ruff manage formatting and imports.

Preserve dictionary responses and CLI JSON compatibility. Keep strict, endpoint-specific request models separate from forward-compatible response models. Retain unknown response fields and distinguish omitted values from explicit nulls.

## Testing Guidelines

Use pytest with `test_*.py` files and `test_*` functions. Add regression tests for behavior changes, especially request serialization, validation, and credential redaction. Use `httpx.MockTransport`; ordinary tests must not contact Regrid.

`make test` requires at least 90% combined line and branch coverage. Mark HTTPS integration tests `e2e`; they run separately. Report blocked tests explicitly rather than treating them as passed.

## Commit & Pull Request Guidelines

Follow the existing Conventional Commit style: `feat:`, `fix:`, or `docs:` with a concise description. Preserve unrelated changes and commit only authorized work.

PRs should explain behavior changes, compatibility effects, and verification results; link relevant issues. Update usage documentation and `changelog.md` for user-visible changes. Screenshots are unnecessary unless they clarify output.

## Security & Configuration

Never commit secrets. Use `REGRID_TOKEN` and placeholder-only `.env.sample`; local `.env` files are ignored. `make live` and `make doctor` explicitly load `.env` through uv. For authenticated CLI/API work, use `uv run --env-file .env --no-sync regrid ...` or `uv run --env-file .env --no-sync python ...`. Never display or inspect the token; load it only into the child process. The SDK and CLI do not load `.env` themselves. Do not log token-bearing URLs. Preserve bounded requests, disabled redirects, and explicit pagination/retries.
