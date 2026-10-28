---
name: setup
description: Checks whether the Regrid research plugin's MCP tools and authentication are available, or diagnoses setup and connection failures without revealing credentials.
---

# Check Regrid setup

1. Inspect the tools available in this session for the Regrid MCP connection.
   If missing, report that the connector is not available and use the appropriate
   host setup below. Do not inspect secret files or request a token in chat.
2. If tools exist, make a documentation or schema discovery call. Report this
   separately from authenticated access; public documentation needs no token.
3. If a non-billable account usage operation is exposed, call it to verify
   authentication. Report success or the sanitized failure, without account
   secrets, raw headers, or token-bearing URLs. If unavailable, say authentication
   remains unverified; do not use a parcel lookup just to test setup.
4. Report three statuses: tools available, documentation reachable, authenticated
   access verified. A configured header alone does not pass the third check.

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
