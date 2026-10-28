---
name: setup
description: Checks whether the Regrid research plugin's MCP tools and authentication are available, or diagnoses setup and connection failures without revealing credentials.
---

# Check Regrid setup

1. Inherit the caller's constraints before doing anything: offline/no-network
   means no remote discovery, documentation fetch, authentication probe, or API
   call. Inspect only locally exposed tool metadata and supplied evidence, and
   report live checks as `not_attempted`. Never inspect secret files or request a
   token in chat.
2. Inspect the tools available in this session for the Regrid MCP connection.
   If missing, report that the connector is not available and use the appropriate
   host setup below. Do not inspect secret files or request a token in chat.
3. If network access is allowed and tools exist, inspect relevant schemas; make a
   documentation discovery call only when needed. Report this
   separately from authenticated access; public documentation needs no token.
4. An authenticated probe needs an explicit finite request bound. For a research
   handoff, inherit its same workflow ID, ledger, and remaining allowance; setup
   receives no fresh allowance. For a standalone setup request, default to at
   most one API request. If a non-billable account usage operation is exposed and
   one request remains, reserve and record that one diagnostic API attempt before
   calling it to verify authentication. Report success or the sanitized failure,
   without account secrets, raw headers, or token-bearing URLs. If unavailable,
   say authentication remains unverified.
   Never use a parcel lookup just to test setup, automatically retry an auth or
   permission failure, or retry an uncertain outcome. Stop when no request remains.
   If research delegated setup after an auth/permission failure, diagnose from
   the existing failure and configuration instructions; do not automatically
   issue another authenticated request. A later retry requires the caller's
   explicit instruction and the same remaining allowance.
5. Report three statuses: tools available, documentation reachable, authenticated
   access verified. A configured header alone does not pass the third check.

Tool listing, input-schema inspection, and documentation-only tools are distinct
from an API executor invocation. They consume no API request allowance, though a
remote call still requires network permission. Every API executor invocation
counts toward the shared request bound, including usage diagnostics, count-only
queries, failed calls, and uncertain outcomes, even when non-billable. Reserve
zero parcel records for a usage diagnostic, and preserve the attempt if it fails.
If a tool's API behavior or request bound is unknown, skip the probe and report
authentication unverified. Do not hide diagnostic requests outside the ledger.

Honor a caller's requested format. An optional structured setup result can carry
`tools_available`, `documentation_reachable`, and `authenticated_access_verified`
as `verified`, `failed`, `unknown`, or `not_attempted`, plus sanitized `blocker` and
`requests_used`. When invoked from research, return its unchanged workflow ID and
updated shared ledger separately; these small status fields do not replace the
research contract. `not_attempted` means no check was dispatched. A dispatched
probe with a timeout or ambiguous response has `unknown` verification status;
it is not `not_attempted`. A definite authentication rejection is `failed`.
Do not claim an unattempted check failed or succeeded.

For the observed tool names and a verified usage-only HAR request, consult the
[MCP reference](../property-research/references/mcp-tools.md). The live schema
takes precedence. Decode MCP text content and check the API result; an outer
HTTP 200 alone is not authentication success. Do not request per-token breakdowns
or print token fragments returned by account metadata.

For Cowork, the Cowork plugin declares a remote HTTP connector to
https://support.regrid.com/mcp; it launches no local bridge. Add/connect it in
Claude's Connectors settings. Merely installing the plugin does not authenticate.
Choose No sign-in and, where the Request headers beta is available, configure a
required `x-regrid-token` header with the actual token entered privately in the
settings UI. Values are literal, not environment-variable references. Custom
header names need Anthropic approval. If the section is absent or the name is
rejected, report that specific blocker; do not invent an OAuth flow or put the
key in a URL. An OAuth-enabled gateway is a separate, unimplemented alternative.
See the plugin README for the setup steps and official documentation link.

For Claude Code, the Code package's local `mcp-remote` bridge requires Node/npx
and `REGRID_TOKEN` in its host environment. The README's uv command loads `.env`
privately before launch. Cowork does not inherit that file or Desktop's Developer
JSON configuration. Use one package variant per host; use the standalone skill
when a Regrid connector is already configured. Cowork live authentication must be
verified in the user's session, not inferred from package validation.

Before first data use, remind the user of Regrid's documented requirement to
disable model training/data sharing in their AI account. Do not claim to have
verified account settings you cannot inspect.
