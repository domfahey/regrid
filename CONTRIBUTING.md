# Contributing

Bug reports, documentation improvements, and focused pull requests are welcome.
Read [AGENTS.md](AGENTS.md) for repository conventions and
[architecture.md](architecture.md) for design boundaries. Follow the
[code of conduct](CODE_OF_CONDUCT.md).

## Development

Install Python 3.10+ and uv, fork the repository, and create a branch:

```sh
# After forking on GitHub, substitute your GitHub username below.
git clone https://github.com/YOUR_USERNAME/regrid.git
cd regrid
git switch -c describe-your-change
make install
make format
make check
```

`make check` runs lint, formatting checks, type checking, and mocked tests with
at least 90% combined line/branch coverage. No credentials are needed.
Run `make e2e` for local HTTPS tests; OpenSSL and localhost sockets are required.
Do not run `make live` as an ordinary test: it requires your own account and may
consume paid records. Never attach tokens, `.env`, private records, or unredacted
HTTP logs to issues or pull requests. Use synthetic fixtures.

Add regression tests for behavior changes, preserve raw response/CLI compatibility,
and update relevant docs and `changelog.md`. Keep changes focused and describe
what changed, why, tests run, and any unverified gates in the PR.
Use Conventional Commit subjects such as `fix: preserve omitted fields`.

## Plugin changes

Canonical skills live under `plugins/regrid-research/skills/`. Build with
`.venv/bin/python scripts/build_claude_plugins.py`; generated archives stay in
ignored `dist/`. See the plugin's [evaluation guide](plugins/regrid-research/evals/README.md).
Structural checks, model evaluations, and Cowork acceptance are separate gates.

Report vulnerabilities privately using [SECURITY.md](SECURITY.md).
Contributions are provided under this project's MIT license. Regrid service access
and data remain subject to Regrid's terms; never contribute credentials or data
you lack permission to share.
