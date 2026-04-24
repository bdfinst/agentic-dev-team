You are working in the `agentic-security-review` plugin at
/Users/finsterb/_git-os/agentic-dev-team/plugins/agentic-security-review/

Your task: ship the four helper scripts that the security-assessment
orchestrator spec references but the plugin does not currently
bundle. Their absence causes every security-assessment run to skip
phase-timing instrumentation, the accepted-risks gate, severity-floor
application, and CI-file discovery — or to inline the behavior
ad-hoc per run, which destroys reproducibility.

## Evidence

Observed across four separate `/security-assessment` runs on
2026-04-24 (extranetapi, login-service, speedpay-sdk, ivr against the
NextGen fleet at /Users/finsterb/_git-aci/ng-security-scan). Every
run's closing notes called out the same gap. Representative quote:

  "pipeline helper scripts referenced in the orchestrator spec
  (`phase-timer.sh`, `apply-accepted-risks.sh`,
  `apply-severity-floors.sh`, `find-ci-files.sh`) are not present in
  this project or either plugin cache — phase-timing instrumentation
  and automated verification were skipped."

The spec references are in:

- `skills/security-assessment-pipeline/SKILL.md:27, :93, :108, :150-151`
- `commands/security-assessment.md:76, :101, :106, :123, :144`
- `agents/exec-report-generator.md` (consumes the phase-timings JSONL)

Existing sibling scripts that are present — use them as style/tone
references — live at:

- `scripts/check-severity-consistency.sh`
- `scripts/verify-report.sh`

## Scripts to ship

Each lives under `scripts/`. Each must be executable, pass `shellcheck`,
and print usage on `-h`.

### 1. `scripts/phase-timer.sh`

Contract (from `commands/security-assessment.md:76` and
`skills/security-assessment-pipeline/SKILL.md:150-151`):

```
scripts/phase-timer.sh start <phase-name> <slug> [<memory-dir>]
scripts/phase-timer.sh end   <phase-name> <slug> [<memory-dir>]
```

Appends one JSONL record per invocation to
`<memory-dir>/phase-timings-<slug>.jsonl`. Record shape:

```json
{"event": "start|end", "phase": "phase-1-tool-pass", "slug": "ivr",
 "epoch_ms": 1745528439123, "iso": "2026-04-24T17:30:39.123Z",
 "pid": 12345}
```

Acceptance:

- [ ] Both `start` and `end` modes work; argument validation with a
  helpful usage string.
- [ ] `memory-dir` defaults to `./memory` (matches the existing
  `scan_java.sh` convention).
- [ ] Uses `date +%s%3N`-equivalent; works on macOS (where GNU `date`
  is not default — use `python3 -c 'import time; ...'` fallback if
  needed to stay portable).
- [ ] Emits to stderr (not stdout) if the memory-dir is not writable;
  exits non-zero but never crashes the caller.
- [ ] `-h` / `--help` prints usage.

### 2. `scripts/apply-accepted-risks.sh`

Contract (from `commands/security-assessment.md:123` and
`skills/security-assessment-pipeline/SKILL.md:93`):

```
scripts/apply-accepted-risks.sh <target-dir> <slug> [<memory-dir>]
```

If `<target-dir>/ACCEPTED-RISKS.md` exists, parses it and suppresses
any finding in `<memory-dir>/findings-<slug>.jsonl` whose `rule_id` +
`source_ref` matches an accepted-risks entry. Writes the suppression
log to `<memory-dir>/accepted-risks-<slug>.jsonl` (one record per
suppressed finding including the justification).

Decide and document the ACCEPTED-RISKS.md parse format. Existing
references in the spec do not pin it down — the common shape is a
YAML frontmatter list of `{rule_id, source_ref_glob, reason, expires}`
entries, but any parseable format is fine. Document whatever you
choose in the script header and in `docs/accepted-risks-format.md`.

Acceptance:

- [ ] No-op (exit 0) when ACCEPTED-RISKS.md is absent.
- [ ] Deterministic parse of the documented format.
- [ ] Suppression is idempotent — re-running produces identical output.
- [ ] Expired entries in ACCEPTED-RISKS.md (past `expires` date) are
  logged as `expired` and do NOT suppress.
- [ ] Schema for the new `accepted-risks-*.jsonl` added to
  `docs/primitives-contract.md` (or the current contract file).

### 3. `scripts/apply-severity-floors.sh`

Contract (from `commands/security-assessment.md:144` and
`skills/security-assessment-pipeline/SKILL.md:108`):

```
scripts/apply-severity-floors.sh <slug> [<memory-dir>]
```

Applies domain-class severity floors to
`<memory-dir>/disposition-<slug>.json`. Floors are already described
by the fp-reduction skill (hardcoded-creds, weak-crypto, TLS-disabled,
unauth info-leak); this script makes the application a visible,
deterministic step rather than an inline behavior of the fp-reduction
agent.

Input: the existing disposition register.
Output: mutated disposition register (in place) + a
`severity-floors-log-<slug>.jsonl` file recording every floor
application with the raw and floored severity.

The 2026-04-24 extranetapi run already emitted
`severity-floors-log-extranetapi.jsonl` with 17 entries by inlining
the logic. This script must produce byte-identical output when fed
the same pre-floor disposition register.

Acceptance:

- [ ] Floor table externalized to `knowledge/severity-floors.yaml`
  (rather than hardcoded in the script) — one row per finding class,
  with `class`, `floor`, `rationale`.
- [ ] Script is idempotent (re-running does not lower or re-raise
  severities).
- [ ] Every floor application emits exactly one log record;
  un-floored findings emit no record.
- [ ] Exits non-zero if disposition register is missing.
- [ ] The floor table is cited by id in each log record so reviewers
  can audit which rule fired.

### 4. `scripts/find-ci-files.sh`

Contract (from `commands/security-assessment.md:101`):

```
scripts/find-ci-files.sh <target-dir>
```

Prints paths (one per line) to CI/CD definition files in the target:

- `**/Jenkinsfile`
- `**/*.groovy` under a `ci/` or `jenkins/` subtree
- `**/azure-pipelines*.yml` / `**/azure-pipelines*.yaml`
- `**/.github/workflows/*.yml` / `*.yaml`
- `**/.gitlab-ci.yml`
- `**/bitbucket-pipelines.yml`
- `**/Dockerfile` (already covered by hadolint tier, but include for
  completeness so callers can decide scope)

Exit 0 whether or not files were found. Callers then consult
tool-availability (actionlint, semgrep, etc.) and record coverage
gaps in `meta-<slug>.json` per the spec in
`commands/security-assessment.md:106`.

Acceptance:

- [ ] No false positives — ignore `node_modules/`, `vendor/`,
  `.git/`, and `bin/` / `obj/`.
- [ ] Stable sort order (alphabetical) so diffs are reviewable.
- [ ] `-h` / `--help` prints the list of glob patterns it matches
  so operators can extend the filter.

## Test coverage

Each script gets a smoke test under `tests/scripts/`. Follow the
existing test harness pattern (if any — check `tests/` layout). At
minimum:

- One happy-path invocation.
- One missing-argument failure mode.
- For `phase-timer.sh` specifically: a round-trip test that starts a
  phase, ends it, and asserts the JSONL file has exactly 2 records
  with matching `phase` and `slug`.

## Non-goals

- Do not rewrite the `security-assessment` skill or the orchestrator
  commands. The scripts just close gaps the spec already describes.
- Do not invent new phases or new envelope fields. Severity floors,
  accepted-risks format, and CI-file discovery all already exist in
  the orchestrator spec — this work is materializing them, not
  redesigning them.
- Do not add Python dependencies. These are shell scripts; reach for
  `jq` (already an assumed dependency elsewhere in the plugin) and
  built-in `date` / `find` / `grep` / `awk`. If you must use Python,
  keep it to the stdlib.

## Definition of done

- All four scripts in place, executable, shellcheck-clean.
- Smoke tests pass in CI.
- A fresh `/security-assessment` run against any repo in
  `/Users/finsterb/_git-aci/ng-security-scan/targets/` (try
  `spnextgen/ivr` — small, already scanned, good regression target)
  produces:
  - `memory/phase-timings-ivr.jsonl` with non-zero records,
  - `memory/severity-floors-log-ivr.jsonl` matching the 2026-04-24
    reference output byte-for-byte if the pre-floor disposition is
    unchanged,
  - No log line saying "helper script not present" or "skipped
    phase timing."
- Update `CHANGELOG.md` with a single line: "Shipped
  phase-timer.sh / apply-accepted-risks.sh /
  apply-severity-floors.sh / find-ci-files.sh that the
  security-assessment orchestrator spec had always referenced."
