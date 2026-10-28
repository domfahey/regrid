# Changelog

User-visible changes are grouped by release using the categories from [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Version numbering follows [Semantic Versioning](https://semver.org/); the current `0.x` API remains under development.

No releases have been tagged in this repository. `0.1.0` is the current package metadata version, not evidence of a published release. Keep pending changes under Unreleased until an actual release is prepared.

## Unreleased

### Added

- Opt-in `make live` smoke test with one-record lookup, local typed validation, before/after usage checks, and redacted status output.

- Versioned catalog of 169 US parcel fields and generated opt-in `ParcelProperties.typed_fields`, preserving existing dictionary access.
- Optional SDK/CLI query validation against documented field and operator metadata, with an explicit escape hatch for unknown fields.
- Field interpretation guidance and reproducible model generation checked by tests.

- UTFGrid retrieval through raster TileJSON discovery in raw/typed clients and CLI, with same-origin validation and metadata reuse.
- Complete typed matched-address, enhanced-ownership, building, zoning, typeahead, and county properties; validated direct schema-map field access.
- Exact SDK and CLI contract tests for all 33 supplied OpenAPI operations and their parameter profiles.

- Synchronous SDK and CLI for the supplied US/Canada Parcel API endpoints, public schemas, usage, reports, temporary tokens, TileJSON, and tile downloads.
- Opt-in `TypedRegridClient` with typed parcel, count, geometry, usage, metadata, schema, report, and token responses; `.raw` retains dictionary access on the shared transport.
- Strict Pydantic v2 request and client-configuration models with endpoint-specific option validation.
- Response serialization that preserves unknown fields, aliases, and omitted versus explicit null values.
- Make targets for installation, lint, formatting, typing, mocked tests, and separate local HTTPS E2E tests; mocked tests enforce 90% combined line and branch coverage.
- Contributor guidelines, architecture documentation, API reference, and placeholder-only environment configuration.

### Changed

- Request validation now uses Pydantic v2 while retaining dictionary responses and CLI JSON output by default.
- Runtime dependencies now include `pydantic>=2.12,<3` alongside HTTPX.

### Fixed

- Restrict default parcel-search limits to parcel routes so public address-schema requests carry no search parameters.

- Reject non-finite upstream JSON numbers before response serialization can silently change them to null.

### Security

- Store account credentials as `SecretStr`; mask temporary-token models unless explicitly exported.
- Sanitize request and typed-response validation failures without retaining underlying Pydantic exceptions containing input values.
- Keep local environment files and private keys out of Git; authenticated request URLs must be redacted from logs.

## Release Maintenance

At release time, move pending entries into a version heading dated `YYYY-MM-DD`, synchronize `pyproject.toml` and `src/regrid/__init__.py`, and start a fresh Unreleased section. Describe user-facing changes rather than copying commit logs. Add repository comparison links when a remote and release tags exist; do not invent release dates or links.
