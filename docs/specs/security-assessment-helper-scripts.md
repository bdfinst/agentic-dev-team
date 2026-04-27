# Spec: Ship missing security-assessment helper scripts

Source prompt: [`.prompts/security-review-ship-missing-helper-scripts.md`](../../.prompts/security-review-ship-missing-helper-scripts.md)
Target plugin: `plugins/agentic-security-assessment/` (prompt predates the rename from `agentic-security-review`)

## Intent Description

The security-assessment orchestrator spec references four helper scripts — `phase-timer.sh`, `apply-accepted-risks.sh`, `apply-severity-floors.sh`, `find-ci-files.sh` — that the plugin does not ship. Every run either skips the behavior those scripts would provide (phase-timing instrumentation, accepted-risks gating, deterministic severity floors, CI-file discovery) or inlines the behavior ad-hoc inside a sub-agent. Inlining destroys reproducibility; skipping silently weakens the contract the spec promised.

This change ships all four scripts, externalizes the severity-floor table to a knowledge file so it is auditable, adds smoke tests, and registers the new `accepted-risks-*.jsonl` shape in the primitives contract. The scripts materialize behaviors the orchestrator spec already describes — this is implementation of an existing design, not new design.

## User-Facing Behavior

```gherkin
Feature: Security-assessment helper scripts

  Scenario: phase-timer records start and end events for a phase
    Given a security-assessment run is in progress
    When phase-timer.sh start phase-1-tool-pass <slug> is invoked
    And phase-timer.sh end phase-1-tool-pass <slug> is invoked
    Then memory/phase-timings-<slug>.jsonl contains exactly 2 records
    And both records share the same phase and slug
    And each record carries event, phase, slug, epoch_ms, iso, and pid fields

  Scenario: phase-timer defaults memory-dir to ./memory
    Given no <memory-dir> argument is provided
    When phase-timer.sh is invoked
    Then phase-timer.sh writes to ./memory/phase-timings-<slug>.jsonl

  Scenario: phase-timer is portable across macOS
    Given the script is run on macOS where GNU date is not default
    When phase-timer.sh is invoked
    Then phase-timer.sh produces a millisecond-precision epoch value
    And the iso field is ISO-8601 with millisecond precision

  Scenario: phase-timer fails gracefully when memory-dir is not writable
    Given the specified memory-dir does not exist or is not writable
    When phase-timer.sh is invoked
    Then phase-timer.sh writes an error message to stderr
    And phase-timer.sh exits non-zero
    And phase-timer.sh does not crash the caller

  Scenario: apply-accepted-risks is a no-op when ACCEPTED-RISKS.md is absent
    Given <target-dir>/ACCEPTED-RISKS.md does not exist
    When apply-accepted-risks.sh is invoked
    Then apply-accepted-risks.sh exits 0
    And findings-<slug>.jsonl is unchanged
    And no accepted-risks-<slug>.jsonl is written

  Scenario: apply-accepted-risks suppresses matching findings and logs them
    Given ACCEPTED-RISKS.md declares an entry for a specific rule_id + source_ref_glob
    And findings-<slug>.jsonl contains a matching finding
    When apply-accepted-risks.sh is invoked
    Then the matching finding is suppressed from the findings set
    And memory/accepted-risks-<slug>.jsonl records the suppression with the justification

  Scenario: apply-accepted-risks is idempotent
    Given an initial invocation has produced findings-<slug>.jsonl and accepted-risks-<slug>.jsonl
    When apply-accepted-risks.sh is invoked again on the same inputs
    Then the outputs are byte-identical to the first invocation

  Scenario: apply-accepted-risks logs expired entries without suppressing
    Given ACCEPTED-RISKS.md declares an entry with expires in the past
    When apply-accepted-risks.sh is invoked
    Then the entry is logged with status: expired
    And the finding it would have suppressed is retained

  Scenario: apply-severity-floors raises severities to class-specific floors
    Given disposition-<slug>.json contains findings tagged with hardcoded-creds / weak-crypto / TLS-disabled / unauth-info-leak
    And knowledge/severity-floors.yaml declares floors for those classes
    When apply-severity-floors.sh is invoked
    Then each matching finding's severity is raised to the declared floor
    And memory/severity-floors-log-<slug>.jsonl records one entry per floored finding
    And each log entry cites the floor rule id, raw severity, and floored severity

  Scenario: apply-severity-floors is idempotent
    Given a disposition register has already been floored
    When apply-severity-floors.sh is invoked again
    Then no floor record is added and no severity is changed

  Scenario: apply-severity-floors matches the byte-exact 2026-04-24 reference
    Given the pre-floor disposition register from the 2026-04-24 extranetapi run
    When apply-severity-floors.sh is invoked
    Then the output severity-floors-log-extranetapi.jsonl matches the reference byte-for-byte

  Scenario: apply-severity-floors fails when the disposition register is missing
    Given disposition-<slug>.json does not exist
    When apply-severity-floors.sh is invoked
    Then apply-severity-floors.sh exits non-zero
    And a diagnostic message is emitted

  Scenario: find-ci-files discovers pipelines in a target
    Given a target directory containing CI definition files
    When find-ci-files.sh <target-dir> is invoked
    Then the script prints paths to each matched file on stdout
    And paths are sorted alphabetically
    And paths under node_modules, vendor, .git, bin, and obj are excluded

  Scenario: find-ci-files emits -h usage
    When find-ci-files.sh -h is invoked
    Then the script prints the list of glob patterns it matches
    And the script exits 0

  Scenario: find-ci-files returns exit 0 even with no matches
    Given a target directory with no CI definition files
    When find-ci-files.sh <target-dir> is invoked
    Then find-ci-files.sh prints nothing
    And exits 0

  Scenario: All scripts pass shellcheck and print -h usage
    When each helper script is invoked with -h
    Then the script prints its usage to stdout
    And shellcheck reports zero findings against each script
```

## Architecture Specification

**Components added**

- `scripts/phase-timer.sh` — JSONL event emitter for phase start/end.
- `scripts/apply-accepted-risks.sh` — parses `ACCEPTED-RISKS.md`, suppresses matching findings, logs suppressions + expired entries.
- `scripts/apply-severity-floors.sh` — applies floor table from `knowledge/severity-floors.yaml` to the disposition register; logs each application.
- `scripts/find-ci-files.sh` — prints sorted paths to CI definition files under a target.
- `knowledge/severity-floors.yaml` — externalized floor table, one row per class with `class`, `floor`, `rationale`.
- `tests/scripts/` — smoke tests for each script: one happy path and one missing-argument failure; `phase-timer.sh` additionally gets a round-trip test.
- `docs/accepted-risks-format.md` — documents the ACCEPTED-RISKS.md parse format chosen.

**Components modified**

- `docs/primitives-contract.md` (or current contract file) — add schema for `accepted-risks-<slug>.jsonl` and `severity-floors-log-<slug>.jsonl`.
- `skills/security-assessment-pipeline/SKILL.md` — the existing references (lines 27, 93, 108, 150-151) already point to these scripts; verify the paths match after adding.
- `commands/security-assessment.md` — the existing references (lines 76, 101, 106, 123, 144) already invoke these scripts; verify nothing else changes.
- `CHANGELOG.md` — one-line entry.

**Components NOT modified**

- The orchestrator command itself — the scripts close gaps the spec already describes.
- The fp-reduction agent — severity floors move from "inline in fp-reduction" to "dedicated script"; fp-reduction must continue to work when the script has already run but must not double-apply floors.

**Key interfaces**

- `phase-timer.sh`:
  - Invocation: `phase-timer.sh start|end <phase-name> <slug> [<memory-dir>]`
  - Output: appends one JSONL record to `<memory-dir>/phase-timings-<slug>.jsonl`
  - Record shape: `{"event": "start"|"end", "phase": <str>, "slug": <str>, "epoch_ms": <int>, "iso": <str>, "pid": <int>}`
- `apply-accepted-risks.sh`:
  - Invocation: `apply-accepted-risks.sh <target-dir> <slug> [<memory-dir>]`
  - Inputs: `<target-dir>/ACCEPTED-RISKS.md` (optional), `<memory-dir>/findings-<slug>.jsonl`
  - Outputs: mutates `findings-<slug>.jsonl` (suppression); writes `accepted-risks-<slug>.jsonl`
  - Parse format: YAML frontmatter list of `{rule_id, source_ref_glob, reason, expires}` entries (documented in `docs/accepted-risks-format.md`)
- `apply-severity-floors.sh`:
  - Invocation: `apply-severity-floors.sh <slug> [<memory-dir>]`
  - Input: `<memory-dir>/disposition-<slug>.json`
  - Outputs: in-place mutation of disposition register; writes `severity-floors-log-<slug>.jsonl`
  - Floor source: `knowledge/severity-floors.yaml`
- `find-ci-files.sh`:
  - Invocation: `find-ci-files.sh <target-dir>`
  - Output: stdout, sorted paths, one per line
  - Match patterns: `Jenkinsfile`, `*.groovy` under `ci/` or `jenkins/`, `azure-pipelines*.y?ml`, `.github/workflows/*.y?ml`, `.gitlab-ci.yml`, `bitbucket-pipelines.yml`, `Dockerfile`
  - Exclude roots: `node_modules/`, `vendor/`, `.git/`, `bin/`, `obj/`

**Constraints**

- No Python dependencies. Reach for `jq` (assumed dependency elsewhere in the plugin) and built-in `date`/`find`/`grep`/`awk`. If Python is unavoidable for `date +%s%3N` portability, stdlib only.
- Every script: executable, `shellcheck`-clean, prints usage on `-h`/`--help`.
- Every script: argument validation with a helpful usage string; exits non-zero on misuse but never crashes the caller.
- `phase-timer.sh` portability: `date +%s%3N` on Linux, stdlib Python or equivalent fallback on macOS.
- `apply-accepted-risks.sh` and `apply-severity-floors.sh` are deterministic and idempotent — re-running on identical inputs must produce byte-identical outputs.
- Severity-floor table lives in `knowledge/severity-floors.yaml`, not inline in the script, so reviewers can audit which rule fired.

**Scope note** — this spec describes four independent vertical slices bundled into one PR at the human's direction. Each script is independently deliverable: `phase-timer.sh` has no dependencies on the others; `find-ci-files.sh` is pure discovery; `apply-accepted-risks.sh` and `apply-severity-floors.sh` operate on different files. The bundle is justified by their shared origin (one paragraph in the orchestrator spec references all four) and by a single CHANGELOG entry, but the bundle is a convenience, not a constraint.

## Acceptance Criteria

- [ ] All four scripts exist under `scripts/`, are executable, and pass `shellcheck` with zero findings.
- [ ] Each script prints usage on `-h` / `--help`.
- [ ] `phase-timer.sh` round-trip test: start + end emits exactly 2 JSONL records with matching `phase` and `slug` fields.
- [ ] `phase-timer.sh` defaults memory-dir to `./memory`.
- [ ] `phase-timer.sh` millisecond timestamps work on macOS (tested explicitly).
- [ ] `apply-accepted-risks.sh` is a no-op (exit 0) when `ACCEPTED-RISKS.md` is absent.
- [ ] `apply-accepted-risks.sh` deterministically parses the documented YAML-frontmatter format.
- [ ] `apply-accepted-risks.sh` is idempotent — re-running produces identical output.
- [ ] `apply-accepted-risks.sh` logs expired entries as `expired` and does NOT suppress findings tied to expired entries.
- [ ] `accepted-risks-<slug>.jsonl` schema is added to `docs/primitives-contract.md`.
- [ ] `docs/accepted-risks-format.md` documents the ACCEPTED-RISKS.md parse format.
- [ ] `knowledge/severity-floors.yaml` exists with one row per finding class (`class`, `floor`, `rationale`).
- [ ] `apply-severity-floors.sh` is idempotent.
- [ ] `apply-severity-floors.sh` emits exactly one log record per floor application; un-floored findings emit no record.
- [ ] `apply-severity-floors.sh` cites the floor rule id in each log record.
- [ ] `apply-severity-floors.sh` exits non-zero when `disposition-<slug>.json` is missing.
- [ ] `apply-severity-floors.sh` byte-matches the 2026-04-24 `severity-floors-log-extranetapi.jsonl` when fed the same pre-floor disposition register.
- [ ] `find-ci-files.sh` excludes `node_modules/`, `vendor/`, `.git/`, `bin/`, `obj/`.
- [ ] `find-ci-files.sh` outputs are alphabetically sorted.
- [ ] `find-ci-files.sh` exits 0 whether or not matches are found.
- [ ] Smoke tests for each script pass in CI.
- [ ] Fresh `/security-assessment` run against `spnextgen/ivr` produces:
  - non-empty `memory/phase-timings-ivr.jsonl`
  - `memory/severity-floors-log-ivr.jsonl` byte-identical to the 2026-04-24 reference (assuming unchanged pre-floor disposition)
  - no log line stating "helper script not present" or "skipped phase timing"
- [ ] `CHANGELOG.md` entry: "Shipped phase-timer.sh / apply-accepted-risks.sh / apply-severity-floors.sh / find-ci-files.sh that the security-assessment orchestrator spec had always referenced."

## Consistency Gate

- [x] Intent is unambiguous — four specific scripts, contracts defined in the prompt
- [x] Every behavior in the intent has at least one corresponding BDD scenario
- [x] Architecture specification constrains implementation to what the intent requires
- [x] Concepts named consistently across artifacts (`phase-timings-<slug>.jsonl`, `accepted-risks-<slug>.jsonl`, `severity-floors-log-<slug>.jsonl`, `disposition-<slug>.json`, `findings-<slug>.jsonl`)
- [x] No artifact contradicts another

**Scope violation — flagged**: this spec bundles four independent vertical slices. The specs skill says "Each specification covers one vertical slice only; split if scope is too broad", and these four scripts have no hard dependencies on each other. Recommended split order if plan-time reveals too much surface area:

1. `phase-timer.sh` (smallest, used by every phase — ship first to unblock timing data)
2. `find-ci-files.sh` (pure discovery, no mutation)
3. `apply-severity-floors.sh` + `knowledge/severity-floors.yaml` (determinism-sensitive; has a byte-identical reference test)
4. `apply-accepted-risks.sh` + `docs/accepted-risks-format.md` (largest design surface because parse format is new)

The human has pre-decided to bundle; this note exists so the plan phase can reconsider if any slice balloons.

**Verdict: PASS (with scope flag)** — spec is ready for planning; suggest splitting into four PRs or four sequential commits if any script's plan reveals unexpected complexity.
