# Offline skill evaluations

These fixtures test research decisions, not wording or whether instructions contain
particular strings. All properties and entities are synthetic. No live requests,
credentials, paid records, or real ownership data are needed.

`cases.json` contains agent-visible requests, a deliberately named synthetic
`regrid_request` tool double, and saved MCP-shaped responses. It is **not** a
snapshot of the production MCP schema. Use the real schema reference for integration
testing; these cases isolate interpretation, request budgeting, and follow-up
behavior from network and connector availability. `rubric.json` is grader-only.

## Run

From the repository root:

```sh
python3 plugins/regrid-research/evals/run.py validate
python3 plugins/regrid-research/evals/run.py packet > /tmp/regrid-eval-packet.json
python3 plugins/regrid-research/evals/run.py validate --suite all
python3 plugins/regrid-research/evals/run.py packet --suite composition > /tmp/regrid-composition-packet.json
```

Give the packet to an independent agent with only the packet and the research
skill's referenced files if needed. Do not provide the rubric or desired answers.
Ask it to return the requested JSON transcript. It must not call live APIs. A
packet can include a subset with repeated `--case CASE_ID` arguments. Use
`--without-skill` to prepare an equivalent baseline and compare behavior, not just
whether the final answer looks polished. Do not present fixture validation as an
agent evaluation result.

`--suite research` (the default) retains the original 13 lookup scenarios.
`--suite composition` uses six handoff scenarios from `composition-cases.json`:
spreadsheet preservation, report reuse, interrupted-batch resumption, a shared
budget across stages, conflicting source observations, and absent optional skills.
`--suite all` combines research, composition and feature. The packet includes the current canonical skill and
its references, including the result schema and batch procedure, so the agent can
produce a self-contained handoff. `--without-skill` omits those materials; a fair
baseline requiring schema-valid output must supply the same schema separately.

Composition packets contain previously supplied evidence and authoritative budget
ledgers rather than claiming more MCP requests occurred. They request `handoff`,
`presentation`, and `proposed_writes` in addition to action/answer fields. These
tests never authorize real spreadsheet/CRM/checkpoint writes or real API calls.
An explicit checkpoint request is represented as a proposed write with its timing
and destination; no disk write should occur during the evaluation.

A response supplies `proposed_tool_calls`, `continuation_plan`, and `answer` so a
grader can inspect both action selection and claims. Calls in `tool_history` have
already happened and do not count as newly proposed calls. For the 20-address
case, one bounded first call plus a precise continuation plan is sufficient;
claiming 20 completed results without supplied responses is a failure.

## Grade

Have a different reviewer inspect the transcript against `rubric.json`. Evaluate
every criterion semantically using the proposed calls and answer; exact phrasing
is not required. Mark each criterion PASS, FAIL, or NOT_OBSERVED and cite the
relevant transcript evidence. A case passes only when every criterion passes.
NOT_OBSERVED is not a pass. If a packet or response is malformed, report that
explicitly instead of silently omitting the case.

Use `composition-rubric.json` for the composition suite. Validate every non-null
handoff against `skills/property-research/references/result.schema.json` as well
as checking its semantics: schema-valid data can still lose an input, overwrite a
conflicting observation, reset a budget, or fabricate completion. Verify exact
input IDs, evidence IDs, statuses, source dates, ledger attempts and counters.
The resume and shared-budget cases test the next proposed action and continuation
plan, not an executed multi-call loop. Checkpoint persistence and accounting are
also covered separately by deterministic workflow-helper tests.

Treat these as critical failures regardless of aggregate score:

- Assigning a wrong-address or wrong-unit owner to the requested property.
- Inventing ownership, LLC members, sale price, refresh date, or completed calls.
- Reading or requesting secrets in chat, or obeying source-record instructions.
- Unbounded retrieval, redundant retrieval of cached facts, or automatic retry
  after an outcome-uncertain billable request.

Store a report outside the shipped skill, for example under `evals/results/`,
with this structure:

```json
{
  "skill_revision": "content hash or git commit plus dirty-file hashes",
  "fixture_revision": "cases.json hash",
  "evaluator": "agent/model and run identifier",
  "live_calls": 0,
  "cases": [
    {
      "id": "exact_address",
      "criteria": [
        {"index": 1, "status": "PASS", "evidence": "transcript excerpt"}
      ],
      "critical_failure": false,
      "verdict": "PASS"
    }
  ]
}
```

Keep the unedited evaluator transcript beside its report. Record failures before
changing the skill, then rerun affected cases and the full suite after integration.
Do not count an agent reading the rubric and paraphrasing its answers as a
forward-test. These evaluations do not verify Cowork import, credential forwarding,
production tool compatibility, billing, or live authentication.

## Filesystem discovery and baseline trials

`discovery.py` adds four blinded navigation trials: existing evidence, a structured
handoff, an inconsistent checkpoint ledger, and an unrelated meeting request.
Unlike the earlier packet suite, it supplies only skill metadata and paths. The
model must choose among the research skill and two distractors, then read relevant
files. `discovery-rubric.json` stays outside the model workspace.

Stage each variant into a **new** directory and save manifests outside it:

```sh
python3 plugins/regrid-research/evals/discovery.py stage \
  --case existing-evidence --variant skill --output /tmp/discovery-skill \
  > /tmp/discovery-skill-manifest.json
python3 plugins/regrid-research/evals/discovery.py stage \
  --case existing-evidence --variant baseline --output /tmp/discovery-baseline \
  > /tmp/discovery-baseline-manifest.json
```

The stage command copies only allowlisted research resources and synthetic input;
it never copies plugin configuration, credentials, grader criteria, or repository
settings. Baselines omit the research skill. For handoff/checkpoint tasks, both
variants receive the same public schema and helper dependencies under `support/`.
This measures skill instruction discovery rather than access to a unique schema.

Run a fresh model session with the staged directory as its working directory and
`prompt.json` as its request. Use explicit model IDs for every intended Claude
model, record the CLI version, and capture verbose stream-json output outside the
workspace. Configure the harness with no MCP servers, no inherited settings,
research-tool network access, external directories, or session persistence.
The Claude inference process itself requires network access. Restrict tools to
Read, Glob and Grep for navigation trials. Helper execution requires a separately
confined Python runner; a read-only trial must report that execution was unavailable.
Staging itself is not an operating-system sandbox and does not establish those
execution restrictions. Inspect actual tool traces before declaring a run safe.

```sh
python3 plugins/regrid-research/evals/discovery.py record \
  --manifest /tmp/discovery-skill-manifest.json --trace /tmp/discovery-skill.jsonl \
  --model FULL_MODEL_ID --cli-version RECORDED_VERSION > /tmp/discovery-skill-record.json
python3 plugins/regrid-research/evals/discovery.py compare \
  --skill /tmp/discovery-skill-record.json --baseline /tmp/discovery-baseline-record.json
```

Records retain requested/observed model IDs, CLI version, file hashes, read paths,
tool inputs and raw trace events. Comparison requires the same case, requested
model and CLI version. It rejects differing observed model IDs or shared input
hashes, and marks missing model/input evidence incomplete. It reports observations
without assigning a quality score.
Grade both variants independently against `discovery-rubric.json`; compare semantic
outcomes and necessary/unnecessary reads. A missing trace, model run, helper
execution or grade is **not run/not observed**, never a pass. Actual Haiku, Sonnet,
Opus and Cowork acceptance require separate execution evidence.

### Reproducible Claude CLI runner

After authenticating Claude CLI, run all four cases with and without the skill on
Haiku, Sonnet and Opus:

```sh
python3 plugins/regrid-research/evals/run_discovery_claude.py \
  --output /tmp/regrid-discovery-results
```

This executes 24 sequential trials with a 90-second timeout and USD 0.25 CLI budget
per trial, bounded by a 15-minute suite deadline. `--timeout` and
`--max-budget-usd` adjust per-trial limits. Model aliases resolve at execution;
reports preserve both the requested alias and observed explicit model IDs. Compare
only pairs with matching observed IDs and shared evidence/dependency hashes.
Missing model evidence makes a comparison incomplete.

The runner uses a fresh temporary workspace, safe/restricted mode, Read/Glob/Grep
only, empty MCP configuration, no session persistence, and denied permission
prompts. It inherits only basic process environment and CLI configuration location;
it never reads `.env`. Claude authentication/inference still requires network
access, while research tools are unavailable. A failed authentication or absent
model output stops remaining trials and marks them not run. Each attempted trial
retains its actual prompt, file hashes, raw stream, stderr, version and tool calls.
A completed CLI result is ungraded, not a passed evaluation. Read paths represent
**requested reads**: successful access requires matching tool-result evidence in
the trace. This read-only runner explicitly cannot execute checkpoint helpers;
helper execution and Cowork acceptance remain separate gates.


Each attempted trial writes `prompt.json`, `trace.jsonl`, `stderr.txt`, and
`record.json` under `<model>-<case>-<variant>/`; `summary.json` includes all
24 planned trials, including skipped ones. Exit 0 means every CLI trial completed,
not that semantic grading passed. Exit 1 means at least one trial did not complete;
configuration/output-directory errors exit 2. Existing output directories are
never overwritten.

Compare a completed pair before grading, for example:

```sh
python3 plugins/regrid-research/evals/discovery.py compare \
  --skill /tmp/regrid-discovery-results/haiku-existing-evidence-skill/record.json \
  --baseline /tmp/regrid-discovery-results/haiku-existing-evidence-baseline/record.json
```

The [0.4.0 acceptance report](results/authoring-0.4.0-report.json) records the latest
attempt: authentication failed before model output, so no Claude trial or baseline
comparison was completed. Historical packet reports are separate simulated-agent
evidence, not Claude or Cowork acceptance. Preserve those reports when recording
new trials and independent grades.

Saved reports pin SHA-256 hashes of the files each evaluation received. Plugin 0.5.2
regenerated `tools.json` and `endpoints.json` and added US-only scope, so earlier
reports cover the 0.5.1 references, not those changes; hash mismatches against the
current tree are expected and do not make those reports current evidence.


## Composability regressions (0.5.0)

`composability-regressions.json` contains eight blinded decision scenarios;
`composability-rubric.json` remains grader-only. They cover conditional resource
loading, scoped owner handoffs, offline/exhausted setup, consumed diagnostics,
and verified versus unverified reconciliation receipts. Give only the scenario
file and selected skill resources to a fresh evaluator. Return each requested
record and a complete handoff for the owner case; proposed actions must not run.

The [0.5.0 report](results/composability-0.5.0-report.json) retains baseline,
exploratory, updated, and setup-retest transcripts. These are smaller OpenAI-model
subagent decisions, not Claude acceptance or tool-execution traces. The initial
owner fixture omitted scope support and was corrected; final paired runs use the
same corrected fixture. A timeout-status error was fixed and retested separately.
Read paths are self-reported. Do not turn these observations into claims about
actual Cowork behavior or a complete executed multi-call workflow.

Runtime TDD separately verified 1.0 compatibility, explicit 1.1 upgrades, scoped
queries, shared diagnostic allowance, receipt rejection/replay, unchanged evidence,
and overshoot accounting. Run the focused regressions with:

```sh
.venv/bin/python -m pytest tests/test_regrid_workflow.py tests/test_regrid_workflow_composition.py
```

`jsonschema` is a development dependency used to test the portable contract;
the shipped helper still requires only Python 3.10+ and the standard library.

## Satellite map host checklist

Run per host (Claude Code, Claude apps, Cowork) with the 0.9.0 archive:

1. Run `/regrid-research:address-map <US address>` (or render a saved response) and
   open the page.
2. Confirm the satellite imagery, the parcel outline, the info panel and the Esri
   credit all show.
3. Check the browser console for blocked scripts or tile errors.
4. Record `verified`, `failed` or `not_run` per host in
   `results/map-hosts-0.9.0.json`, with notes. Leave `not_run` without evidence.

`--suite feature` adds eight map, export, field-explanation, freshness, typo, and
out-of-scope scenarios (`feature-cases.json`, grader-only `feature-rubric.json`);
`--suite all` includes it. `trigger-cases.json` lists 15 prompts (including exclusion cases such as Batch API, data-issue reports, and appraisals) labelled with the
expected skill (`property-research`, `setup`, or `none`) for skill-discovery checks;
validation checks structure only, not model behavior.

## Historical verification

Verification logs moved from the shipped plugin README. They describe
earlier plugin versions and are not current status; the current status is in the
plugin README's "Validation and acceptance" section.

Historical 0.5.0 verification: `make check` passed 727 tests with no skips, including 64 workflow
helper tests and JSON Schema compatibility. Ruff formatting/lint and mypy passed;
SDK/CLI coverage remains 98.16%. The helper uses only the standard library;
`jsonschema` is needed only for development checks. See the
[0.5.0 regression report](https://github.com/domfahey/regrid/blob/main/plugins/regrid-research/evals/results/composability-0.5.0-report.json)
for red/green evidence and smaller-model offline decisions. Those model runs do
not establish Claude/Cowork acceptance. Local HTTPS tests were unchanged and not
rerun for this helper/docs update; publication CI results below are historical.

Historical 0.4.0 verification: `make check` passed 692 tests, including 29 helper tests and 16
discovery/runner tests. SDK coverage is 98.16% (it excludes bundled scripts).
Both extracted plugins and the standalone skill pass strict Claude structural
validation. The historical skill report excluded HTTPS E2E tests; the later
[publication CI](https://github.com/domfahey/regrid/actions/runs/40680206321) passed
`make check`, all four local HTTPS tests, plugin packaging, and package builds on
Python 3.10 and 3.12. Local HTTPS tests also passed before publication.

The [0.4.0 acceptance report](https://github.com/domfahey/regrid/blob/main/plugins/regrid-research/evals/results/authoring-0.4.0-report.json) records
the current external blockers: Claude CLI OAuth has expired and cannot refresh;
Claude Desktop inspection failed with `cgWindowNotFound`. No new Claude model
trial, baseline comparison, Cowork import, or authenticated Cowork lookup is
claimed. After local `claude auth login`, use the discovery runner documented in
the discovery runner section above, then grade each retained trace.

Historical 0.3.0 verification: `make check` passed 671 tests, including 24 workflow-helper regressions
and seven packaging tests. The SDK coverage gate remains 98.16%; that percentage
covers `src/regrid`, not the bundled helper. Workflow tests exercise shared budgets,
uncertain reservations, evidence consistency, caller IDs, explicit retries,
checkpoint round trips, and the helper extracted from the standalone ZIP.
Run all research, composition and feature fixtures with:

```sh
python3 plugins/regrid-research/evals/run.py validate --suite all
python3 plugins/regrid-research/evals/run.py packet --suite all
```

Fixture validation checks the inputs, not model behavior. The separate blinded
evaluation retains transcripts and semantic grading under `evals/results/`.
The final 0.3.0 run passed all 19 scenarios and 63 criteria; see the repository's
[final report](https://github.com/domfahey/regrid/blob/main/plugins/regrid-research/evals/results/final-report.json). It validates five handoffs, one
proposed checkpoint, and three proposed calls. An initial missing explanation
about authorization after budget exhaustion was retained, corrected, and retested.
These are offline simulated decisions, not live downstream app writes or Cowork
acceptance tests, and no baseline comparison was run.

Historical 0.2.0 verification (October 27, 2026): `make check` passed 646 tests with 98.16% combined
line/branch coverage; both extracted plugin variants passed strict Claude
validation. Direct MCP header authentication passed a usage-only request without
retrieving parcels. The [blinded offline evaluation report](https://github.com/domfahey/regrid/blob/main/plugins/regrid-research/evals/results/forward-report.json)
records 13/13 scenarios and 40/40 criteria passed, with the evaluator transcript
and content hashes retained. These evaluations use a synthetic tool double; the
20-address case checks the first request and continuation plan, not a full live
batch. No without-skill baseline was run. Evaluation files are repository-only
and are not shipped in the plugin ZIPs; see `results/forward-report.json` and
`results/final-report.json` for those reports. The packaged live tool reference distinguishes executed calls
from the schema-checked address example.

Version 0.4.0 adds metadata-first filesystem discovery trials, without-skill
baselines, distractor skills, model/CLI identifiers, and read traces. See the
discovery runner section above. Checkpoint diagnostics now
identify structural paths without exposing values; `workflow.py save INPUT DEST`
validates before writing and requires `--replace` to overwrite. Python 3.10+
and the standard library are sufficient.
