# Security policy

## Supported versions

Security fixes target the latest code on `main`. Older snapshots and plugin
archives are not independently maintained. No published release support window
is promised while the project is pre-1.0.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting:
https://github.com/domfahey/regrid/security/advisories/new

Include affected code/version, impact, and a minimal synthetic reproduction.
Do not open a public issue with exploit details, account tokens, `.env` contents,
private property records, or authenticated URLs. No response-time SLA is promised.

If a credential is exposed, revoke or rotate it with its provider immediately;
removing it from a file or commit alone does not invalidate it.

## Credential handling

Store credentials in an ignored local `.env`, environment, or secret manager.
The SDK/CLI do not automatically load `.env`; Makefile live/doctor commands load
it explicitly. Ordinary tests and CI require no Regrid token. Never use production
credentials in test fixtures, reports, plugin bundles, or Git history.
