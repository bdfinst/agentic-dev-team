# Plan: Security-assessment helper scripts

**Created**: 2026-04-24
**Branch**: main
**Status**: approved (2026-04-24, by Bryan Finster)
**Spec**: [`docs/specs/security-assessment-helper-scripts.md`](../docs/specs/security-assessment-helper-scripts.md)
**Source prompt**: [`.prompts/security-review-ship-missing-helper-scripts.md`](../.prompts/security-review-ship-missing-helper-scripts.md)
**Target plugin**: `plugins/agentic-security-assessment/` (renamed from `agentic-security-review`)

## Goal

Ship the four helper scripts that the `security-assessment` orchestrator spec already references but the plugin does not currently bundle: `phase-timer.sh`, `apply-accepted-risks.sh`, `apply-severity-floors.sh`, `find-ci-files.sh`. Their absence means every run either skips phase-timing, accepted-risks gating, severity-floor application, and CI-file discovery — or inlines the behavior ad-hoc per run, which destroys reproducibility. This plan materializes behaviors the orchestrator spec already describes; it does not redesign the pipeline.

## Acceptance Criteria

(Copied from the spec; each maps to at least one TDD step below.)

- [ ] All four scripts exist under `plugins/agentic-security-assessment/scripts/`, are executable, and pass `shellcheck` with zero findings.
- [ ] Each script prints usage on `-h` / `--help`.
- [ ] `phase-timer.sh` round-trip test: start + end emits exactly 2 JSONL records with matching `phase` and `slug`.
- [ ] `phase-timer.sh` defaults memory-dir to `./memory`.
- [ ] `phase-timer.sh` millisecond timestamps work on macOS.
- [ ] `apply-accepted-risks.sh` is a no-op (exit 0) when `ACCEPTED-RISKS.md` is absent.
- [ ] `apply-accepted-risks.sh` parses the documented YAML-frontmatter fields (`rule_id`, `source_ref_glob`, `reason`, `expires`) without error on well-formed input.
- [ ] `apply-accepted-risks.sh` exits with code 3 and emits `apply-accepted-risks.sh: ACCEPTED-RISKS.md parse error at <location> — <detail>; no risks applied` to stderr when the frontmatter is malformed; `findings-<slug>.jsonl` is left unchanged.
- [ ] `apply-accepted-risks.sh` is idempotent — re-running on identical inputs produces byte-identical outputs.
- [ ] `apply-accepted-risks.sh` logs expired entries with `status: expired` and does not suppress.
- [ ] `apply-accepted-risks.sh` rewrites `findings-<slug>.jsonl` atomically (write to `<path>.tmp` then `mv`); interrupted runs leave the original file intact.
- [ ] `accepted-risks-<slug>.jsonl` schema added to `plugins/agentic-dev-team/knowledge/security-primitives-contract.md`.
- [ ] `docs/accepted-risks-format.md` documents the ACCEPTED-RISKS.md parse format (fields, UTC expiry semantics, bash-extglob-only glob syntax — see Step 4 canonical example below).
- [ ] `knowledge/severity-floors.json` exists with one entry per recognized floor class (`class`, `rationale`, optional `canonical_floor` for documentation). The actual floor value applied to each finding comes from the finding's `exploitability.rationale` (pattern `<class> floor=<n>`), matching the fp-reduction agent's existing convention. The knowledge file is the authoritative list of recognized classes — any class outside this list is treated as un-known and ignored. (JSON, not YAML, so `jq` parses it without a yq/python branch.)
- [ ] `apply-severity-floors.sh` is idempotent — repeated runs leave the disposition register and log file unchanged, even though first-run logs every matching finding including ones already at or above their floor. Idempotency marker: after application, the script sets `exploitability.floor_applied: true` in the disposition entry; subsequent runs skip marked entries.
- [ ] `apply-severity-floors.sh` logs one record per matching finding on first run (log-every-match, even when `original_score == final_score`); un-matched findings emit no record. This matches the 2026-04-24 reference semantics.
- [ ] `apply-severity-floors.sh` cites the `floor_class` in each log record (extracted from the rationale pattern). Log record schema: `{id, floor_class, floor, original_score, final_score}` — no `slug`, `rule_id`, or `iso` fields (per 2026-04-24 reference).
- [ ] `apply-severity-floors.sh` exits with code 2 and emits `apply-severity-floors.sh: disposition-<slug>.json not found at <resolved-path>` to stderr when the disposition register is missing (distinct from exit 1 = runtime error, exit 3 = malformed input).
- [ ] `apply-severity-floors.sh` byte-matches the 2026-04-24 `severity-floors-log-extranetapi.jsonl` reference WHEN the paired fixture `tests/scripts/fixtures/severity-floors/input-disposition-extranetapi.json` can be reconstructed to reproduce the reference; otherwise the assertion degrades to schema-identical + five-row spot-check (record chosen fallback in the PR description with the rows inspected).
- [ ] `find-ci-files.sh` excludes `node_modules/`, `vendor/`, `.git/`, `bin/`, `obj/`.
- [ ] `find-ci-files.sh` outputs are alphabetically sorted.
- [ ] `find-ci-files.sh` exits 0 whether or not matches are found.
- [ ] Smoke tests for each script pass in CI.
- [ ] Fresh `/security-assessment` run against `spnextgen/ivr` produces a non-empty `phase-timings-ivr.jsonl` with ≥ 2× phase count records, and a non-empty `severity-floors-log-ivr.jsonl` where every record contains `rule_id`, `raw_severity`, `floored_severity`, and `iso` fields (byte-identical-against-reference is reserved for the Step 3 unit fixture; E2E does not assert byte-identity since upstream disposition may have drifted).
- [ ] No E2E log line contains "helper script not present" or "skipped phase timing".
- [ ] `run-all.sh` itself has a self-test proving it exits non-zero and prints FAIL when a child test fails.
- [ ] Every script's `-h` output declares its exit-code contract (0 = success, 1 = runtime error, 2 = missing required input, 3 = malformed input) so callers can branch on exit codes.
- [ ] `find-ci-files.sh -h` prints both the match patterns AND the excluded roots (`node_modules/`, `vendor/`, `.git/`, `bin/`, `obj/`).
- [ ] `find-ci-files.sh` exits non-zero with an actionable stderr message when `<target-dir>` does not exist on the filesystem (distinct from the "no matches found" exit-0 case).
- [ ] `CHANGELOG.md` entry describing the four shipped scripts.

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

  Scenario: phase-timer produces millisecond-precision timestamps without GNU date
    Given the host provides no GNU date binary (BSD date only)
    And python3 is available on PATH
    When phase-timer.sh is invoked
    Then phase-timer.sh produces a millisecond-precision epoch_ms value
    And the iso field is ISO-8601 with millisecond precision ending in "Z"

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

  Scenario: apply-accepted-risks suppresses a finding matched by exact source_ref
    Given ACCEPTED-RISKS.md declares an entry with rule_id X and source_ref_glob equal to the exact source_ref of one finding in findings-<slug>.jsonl
    When apply-accepted-risks.sh is invoked
    Then that finding is removed from findings-<slug>.jsonl
    And memory/accepted-risks-<slug>.jsonl records one suppression entry with rule_id, source_ref, reason, and iso

  Scenario: apply-accepted-risks suppresses multiple findings matched by glob pattern
    Given ACCEPTED-RISKS.md declares an entry with rule_id X and source_ref_glob "src/**/*.cs"
    And findings-<slug>.jsonl contains two findings whose source_ref matches that glob
    When apply-accepted-risks.sh is invoked
    Then both findings are removed from findings-<slug>.jsonl
    And memory/accepted-risks-<slug>.jsonl records two suppression entries — one per finding

  Scenario: apply-accepted-risks exits non-zero on malformed YAML frontmatter
    Given ACCEPTED-RISKS.md exists with a YAML frontmatter block containing invalid syntax
    When apply-accepted-risks.sh is invoked
    Then apply-accepted-risks.sh exits with code 3
    And stderr contains "ACCEPTED-RISKS.md parse error"
    And findings-<slug>.jsonl is unchanged
    And no accepted-risks-<slug>.jsonl is written

  Scenario: apply-accepted-risks atomic rewrite survives interruption
    Given apply-accepted-risks.sh has started an in-place rewrite of findings-<slug>.jsonl
    When the process is interrupted before the mv completes
    Then the original findings-<slug>.jsonl is intact and readable
    And only a findings-<slug>.jsonl.tmp temp file remains as the partial artifact

  Scenario: apply-accepted-risks is idempotent
    Given an initial invocation has produced findings-<slug>.jsonl and accepted-risks-<slug>.jsonl
    When apply-accepted-risks.sh is invoked again on the same inputs
    Then the outputs are byte-identical to the first invocation

  Scenario: apply-accepted-risks logs expired entries without suppressing
    Given ACCEPTED-RISKS.md declares an entry with expires in the past
    When apply-accepted-risks.sh is invoked
    Then the entry is logged with status: expired
    And the finding it would have suppressed is retained

  Scenario: apply-severity-floors raises exploitability scores matching "<class> floor=<n>" rationales
    Given disposition-<slug>.json contains entries whose exploitability.rationale embeds "<class> floor=<n>" (e.g. "hardcoded-creds floor=9")
    And knowledge/severity-floors.json lists <class> among recognized classes
    When apply-severity-floors.sh is invoked
    Then each matching finding's exploitability.score becomes max(original_score, floor)
    And memory/severity-floors-log-<slug>.jsonl records one entry per matched finding with {id, floor_class, floor, original_score, final_score}
    And the disposition register is rewritten atomically in-place

  Scenario: apply-severity-floors skips entries whose rationale contains "suppressed to <n>"
    Given a disposition entry's rationale reads "info-leak-unauth floor=5 suppressed to 4: <context>"
    When apply-severity-floors.sh is invoked
    Then that entry is NOT logged
    And the entry's exploitability.score is unchanged

  Scenario: apply-severity-floors is idempotent across repeated runs
    Given apply-severity-floors.sh has been invoked once against a disposition register
    When apply-severity-floors.sh is invoked a second time against the resulting register
    Then no new log records are appended
    And no disposition entry's exploitability.score changes
    # Mechanism: first run sets exploitability.floor_applied=true on each matched entry;
    # subsequent runs skip marked entries.

  Scenario: apply-severity-floors matches the 2026-04-24 reference from the committed fixture
    Given the fixture file tests/scripts/fixtures/severity-floors/input-disposition-extranetapi.json is committed to the repo
    And the reference expected-log-extranetapi.jsonl is committed alongside it
    When apply-severity-floors.sh is invoked against the fixture
    Then the output severity-floors-log jsonl matches the reference byte-for-byte
    # Fallback: if reconstruction failed during Step 3 RED, the test asserts schema-identical + 5-row spot-check instead of byte-identity. See Step 3 for the fallback procedure.

  Scenario: apply-severity-floors logs matching findings even when already at or above floor
    Given a disposition entry has rationale "hardcoded-creds floor=9" and exploitability.score=9
    When apply-severity-floors.sh is invoked for the first time
    Then a log record IS emitted with original_score=9 and final_score=9
    And the disposition entry's exploitability.floor_applied is set to true
    # This preserves the 2026-04-24 reference log-every-match semantics.
    # Idempotency is handled by the floor_applied marker on subsequent runs.

  Scenario: apply-severity-floors fails with distinct exit code when disposition register is missing
    Given disposition-<slug>.json does not exist at the resolved path
    When apply-severity-floors.sh is invoked
    Then apply-severity-floors.sh exits with code 2
    And stderr contains "disposition-<slug>.json not found at <resolved-path>"

  Scenario: apply-severity-floors fails fast when neither yq nor python3 is available
    Given neither yq nor python3 is present on PATH
    When apply-severity-floors.sh is invoked
    Then apply-severity-floors.sh exits non-zero
    And stderr contains "requires jq (and yq or python3 for optional YAML)"
    # Note: with the floor table now in JSON, this only fires if the script is invoked with a future YAML-format floor table. jq alone is sufficient for the JSON path.

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

  Scenario: find-ci-files fails when target directory does not exist
    Given <target-dir> does not exist on the filesystem
    When find-ci-files.sh <target-dir> is invoked
    Then find-ci-files.sh writes "target directory not found: <target-dir>" to stderr
    And find-ci-files.sh exits non-zero

  Scenario: find-ci-files -h prints match patterns AND excluded roots
    When find-ci-files.sh -h is invoked
    Then stdout includes the list of match patterns
    And stdout includes the list of excluded roots (node_modules, vendor, .git, bin, obj)
    And exits 0

  Scenario: run-all.sh propagates test failure with named test case
    Given one test script in tests/scripts/ exits non-zero
    When bash tests/scripts/run-all.sh is invoked
    Then run-all.sh exits non-zero
    And the failing test name appears in stdout preceded by FAIL

  Scenario: All scripts pass shellcheck, print -h usage, declare exit-code contract
    When each helper script is invoked with -h
    Then the script prints its usage to stdout
    And the usage output declares the exit-code contract (0/1/2/3)
    And shellcheck reports zero findings against each script
```

## Scope & Sequencing Decision

The spec flagged that this bundle is technically four independent vertical slices. I'm delivering them in **one plan, five steps** — four script steps plus one integration step — for these reasons:

- Each step leaves the repo shippable. A reviewer can stop after Step N and merge; Steps N+1..5 don't break anything already delivered.
- The four scripts share zero code but share one destination directory, one test harness convention (to be established in Step 1), and one CHANGELOG entry.
- Splitting into four PRs would cost four review cycles for ~400 total lines of shell; the bundle is economical.

Step order follows the spec's recommended order: smallest and broadest-dependency first, largest and most design-sensitive last.

## Steps

### Step 1: Establish shell-test harness and ship `phase-timer.sh`

**Complexity**: standard
**Why first**: Every other step reuses the test harness established here; `phase-timer.sh` is the smallest script and its absence is the most commonly-cited gap (phase-timing instrumentation referenced from Phase 0 onwards).

**Prelude — harvest pattern conventions** (5 min):
- Read `plugins/agentic-security-assessment/scripts/check-severity-consistency.sh` and `scripts/verify-report.sh`. Extract the house conventions: shebang line, `set -euo pipefail` usage, usage-block header shape, argument-parsing idiom, error message prefix, exit-code style, `jq` invocation patterns. Document as a 10-line comment at the top of `scripts/phase-timer.sh` labeled `# Conventions: matches style of check-severity-consistency.sh + verify-report.sh`. Any deliberate deviation gets a one-line rationale in the PR description.

**RED**:
- Create `plugins/agentic-security-assessment/tests/scripts/run-all.sh` — a pure-bash test runner that executes every `*.test.sh` under `tests/scripts/`, prints `PASS: <name>` or `FAIL: <name>` per test, and exits non-zero if any fails. (No bats dependency; follow the plugin's shell-first posture.)
- Create `tests/scripts/run-all.self-test.sh` — a self-test that creates a temporary always-failing `*.test.sh` fixture, invokes `run-all.sh`, asserts exit non-zero and `FAIL: <fixture-name>` in stdout, then cleans up. Run this self-test alongside the real suite.
- Create `tests/scripts/phase-timer.test.sh` with test cases:
  - `-h` prints usage, declares exit-code contract (0/1/2/3), exits 0.
  - Missing arguments exits non-zero with usage to stderr.
  - `start` + `end` round-trip against a temp dir writes exactly 2 JSONL records to `<tmp>/phase-timings-<slug>.jsonl`; both records carry `event`, `phase`, `slug`, `epoch_ms`, `iso`, `pid`; both share the same `phase` and `slug`.
  - Default `memory-dir` resolves to `./memory` when omitted.
  - `iso` field is ISO-8601 with millisecond precision (regex assertion).
  - Non-writable memory-dir: error `"phase-timer.sh: cannot write to <dir>"` to stderr, non-zero exit, no crash.
  - Portability: override `PATH` to exclude GNU `date` (if present); assert millisecond-precision still produced via `python3` fallback.
- Run `bash tests/scripts/run-all.sh` → RED (phase-timer.sh doesn't exist).

**GREEN**:
- Create `plugins/agentic-security-assessment/scripts/phase-timer.sh`:
  - shebang `#!/usr/bin/env bash`; `set -euo pipefail`.
  - Header comment: purpose, usage, invocation shape, output shape.
  - `-h`/`--help` prints usage to stdout, exits 0.
  - Argument validation: require `start|end`, `<phase-name>`, `<slug>`; `<memory-dir>` optional, defaults to `./memory`.
  - Millisecond epoch: prefer `date +%s%3N` (GNU); on macOS (BSD `date`) fall back to `python3 -c 'import time; print(int(time.time()*1000))'`. ISO-8601 millisecond string: `python3 -c 'from datetime import datetime,timezone; print(datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00","Z"))'`.
  - Compose one JSONL record with `jq -c -n --arg ... '{event,phase,slug,epoch_ms,iso,pid}'` → appended to `<memory-dir>/phase-timings-<slug>.jsonl`.
  - Memory-dir not writable: emit "phase-timer.sh: cannot write to <dir>" to stderr, exit 1, do not propagate failure other than the non-zero exit.
- Run `bash tests/scripts/run-all.sh` → GREEN.

**REFACTOR**:
- Extract common argument-parsing/usage helpers to a small `scripts/_lib.sh` only if duplication appears in Steps 2–5. For this step alone, inline is fine.
- Run `shellcheck scripts/phase-timer.sh tests/scripts/run-all.sh tests/scripts/phase-timer.test.sh` → zero findings.

**Files**:
- `plugins/agentic-security-assessment/scripts/phase-timer.sh` (new)
- `plugins/agentic-security-assessment/tests/scripts/run-all.sh` (new)
- `plugins/agentic-security-assessment/tests/scripts/phase-timer.test.sh` (new)

**Commit**: `feat(security-assessment): ship phase-timer.sh with shell-test harness`

---

### Step 2: Ship `find-ci-files.sh`

**Complexity**: standard
**Why second**: Pure discovery, no mutation, simplest semantics after phase-timer. Exercises the test harness under a different shape (stdin/stdout only, no file writes).

**RED**:
- Create `tests/scripts/find-ci-files.test.sh` with test cases:
  - `-h` prints usage including the list of match patterns AND the excluded roots; declares exit-code contract; exits 0.
  - Missing `<target-dir>` argument → non-zero exit, usage to stderr.
  - Nonexistent `<target-dir>` path → non-zero exit; stderr contains `"target directory not found: <path>"`.
  - Fixture directory with one file per supported pattern (`Jenkinsfile`, `ci/build.groovy`, `azure-pipelines.yml`, `.github/workflows/ci.yml`, `.gitlab-ci.yml`, `bitbucket-pipelines.yml`, `Dockerfile`) → stdout lists each, sorted alphabetically.
  - Fixture with same files but nested under `node_modules/`, `vendor/`, `.git/`, `bin/`, `obj/` → stdout excludes those.
  - Empty target (no matches) → no output, exit 0.
- Run runner → RED.

**GREEN**:
- Create `plugins/agentic-security-assessment/scripts/find-ci-files.sh`:
  - Shebang + `set -euo pipefail` + `-h` usage block listing every match pattern and every excluded root (so operators can extend the filter by reading the script header).
  - Use `find <target-dir>` with `-not -path '*/node_modules/*' -not -path '*/vendor/*' -not -path '*/.git/*' -not -path '*/bin/*' -not -path '*/obj/*'` and `\( ... -o ... \)` for the match patterns.
  - Pipe through `sort` for stable alphabetical order.
  - Groovy match: only files under a `ci/` or `jenkins/` subtree.
  - Exit 0 regardless of match count.
- Create fixture tree under `tests/scripts/fixtures/find-ci-files/` with positive and negative examples.
- Run runner → GREEN.

**REFACTOR**:
- If the `find` expression gets large, consider array + printf to keep it readable; otherwise leave alone.
- `shellcheck` clean.

**Files**:
- `plugins/agentic-security-assessment/scripts/find-ci-files.sh` (new)
- `plugins/agentic-security-assessment/tests/scripts/find-ci-files.test.sh` (new)
- `plugins/agentic-security-assessment/tests/scripts/fixtures/find-ci-files/**` (new)

**Commit**: `feat(security-assessment): ship find-ci-files.sh for CI/CD definition discovery`

---

### Step 3: Ship `apply-severity-floors.sh` with externalized floor table

**Complexity**: complex
**Why third**: Largest design surface among the script-only steps — introduces `knowledge/severity-floors.json`, has a byte-identical regression target, and must be idempotent. Best to tackle while the test harness is warm and before the accepted-risks format lands.

**Design decision — JSON instead of YAML**: the floor table ships as `knowledge/severity-floors.json`, not `.yaml`. This eliminates the yq-vs-python fallback branch the spec flagged as out-of-scope. `jq` parses JSON natively.

**Schema correction (Option A, approved 2026-04-24)**: after inspecting the real 2026-04-24 reference log, the record shape and algorithm were corrected from the plan's initial interpretation:
- Record shape: `{id, floor_class, floor, original_score, final_score}` — numeric 0-10 scores, no `slug`/`iso`/`rule_id`. Matches the reference byte-for-byte.
- Algorithm: floor value comes from `<class> floor=<n>` pattern in each entry's `exploitability.rationale` (the fp-reduction agent's existing convention), NOT from a static policy lookup. Knowledge file enumerates recognized classes for audit but does not supply per-finding floor values.
- Log semantics: log every matched entry on first run (16 of 17 reference records have `original_score == final_score`); idempotency is achieved via an `exploitability.floor_applied` marker set on first application.
- Suppression phrase: `floor=<n> suppressed to <m>` in the rationale causes the entry to be ignored.

**RED**:
- Copy the 2026-04-24 reference `severity-floors-log-extranetapi.jsonl` from `/Users/finsterb/_git-aci/ng-security-scan/memory/severity-floors-log-extranetapi.jsonl` into `tests/scripts/fixtures/severity-floors/expected-log-extranetapi.jsonl`.
- **Reconstruct the pre-floor disposition register** from `/Users/finsterb/_git-aci/ng-security-scan/memory/disposition-extranetapi.json` by reverse-applying the floor values in the expected log. If reconstruction does not produce a fixture that reproduces the reference log byte-for-byte on a dry-run pass, STOP and invoke the documented fallback:
  - Commit `input-disposition-extranetapi.json` as the best-available reconstruction.
  - Replace the byte-identical assertion in this step's test with a **schema-identical + five-row spot-check**: assert every record carries `rule_id`, `raw_severity`, `floored_severity`, `iso`, and `finding_id`; spot-check five specific records against the reference (the five chosen records and rationale recorded in a code comment in the test file).
  - Note the chosen fallback in the PR description.
- Harvest the recognized floor classes appearing in the reference log → `knowledge/severity-floors.json`:
  ```json
  {
    "recognized_classes": [
      {"class": "hardcoded-creds",
       "canonical_floor": 9,
       "rationale": "Credential in source — atomic exposure, no practical mitigation."},
      {"class": "weak-crypto",
       "canonical_floor": 5,
       "rationale": "Broken/weak primitives or disabled integrity checks — varies with exploitability context."},
      {"class": "tls-disabled",
       "canonical_floor": 7,
       "rationale": "Unencrypted transport — varies with whether endpoint is internet-facing."},
      {"class": "info-leak-unauth",
       "canonical_floor": 5,
       "rationale": "Unauth info leak — context-dependent; some leaks are intentional trace/correlation IDs."},
      {"class": "unauth-admin-endpoint",
       "canonical_floor": 7,
       "rationale": "Unauthenticated admin/management surface."}
    ]
  }
  ```
  Note: `canonical_floor` is documentation only; the actual floor applied per-finding comes from `<class> floor=<n>` in the entry's rationale, not this file.
- Create `tests/scripts/apply-severity-floors.test.sh` with test cases:
  - `-h` prints usage with exit-code contract (0/1/2/3); missing-argument validation.
  - Missing `disposition-<slug>.json` → exit code **2**; stderr contains `"disposition-<slug>.json not found at <resolved-path>"`.
  - Given the fixture disposition + `severity-floors.json`, output `severity-floors-log-extranetapi.jsonl` is byte-identical to the expected reference — OR if fallback triggered, schema-identical + 5-row spot-check passes.
  - Idempotency: run twice, second run produces zero new log records and disposition is unchanged.
  - Already-at-or-above-floor: on first run, the finding IS logged (log-every-match per 2026-04-24 reference); on second run the `floor_applied` marker causes it to be skipped. (Was: "emits no log record" — superseded by Option A.)
  - Un-matched findings: a finding whose rationale has no `<class> floor=<n>` pattern, OR whose class is not in the recognized_classes allow-list, emits no log record.
  - Every log record carries all five fields `{id, floor_class, floor, original_score, final_score}` — nothing more, nothing less. (Was: "cites a `rule_id` matching the floor table" — superseded by Option A; records have `floor_class` instead.)
- Run runner → RED.

**GREEN**:
- Create `plugins/agentic-security-assessment/knowledge/severity-floors.json` with the harvested floor entries.
- Create `plugins/agentic-security-assessment/scripts/apply-severity-floors.sh`:
  - Header comment + shebang + `set -euo pipefail` + pattern-convention line (per Step 1 prelude).
  - `-h` usage prints purpose, invocation, and the exit-code contract (0 = success, 1 = runtime error, 2 = missing required input, 3 = malformed input).
  - Load `knowledge/severity-floors.json`'s `recognized_classes[].class` via `jq` as the allow-list.
  - Read `<memory-dir>/disposition-<slug>.json`; on missing file, emit the exact stderr template above and exit 2.
  - Document in the header: "This script must run after fp-reduction (Phase 2) and before narrative/compliance (Phase 3). Callers MUST serialize invocations; atomicity of the `<path>.tmp`+`mv` handles single-writer-but-crash; concurrent writers are a contract violation."
  - For each entry in `disposition.entries`:
    - Skip if `exploitability.floor_applied == true` (idempotency).
    - Let `rat = exploitability.rationale`. Skip if `rat` matches `/floor=\d+ suppressed to \d+/`.
    - Let `(class, floor) = rat.match(/([a-z][a-z-]*) floor=(\d+)/)`. Skip if no match or `class` not in the allow-list.
    - `original = exploitability.score`. `final = max(original, floor)`.
    - Mutate: `exploitability.score = final`; set `exploitability.floor_applied = true`.
    - Append one JSONL record: `{"id": ..., "floor_class": <class>, "floor": <floor>, "original_score": <original>, "final_score": <final>}`.
  - Atomic in-place rewrite of the disposition register: write to `<path>.tmp` then `mv`.
  - All JSON read/write/mutation via python3 stdlib (no yq dependency; json module is stdlib). `jq` used only for reading the recognized-classes list since that is a simple flat structure.
- Run runner → GREEN.

**REFACTOR**:
- If `jq` invocations get long, extract to well-named bash functions with descriptive names.
- `shellcheck` clean.

**Files**:
- `plugins/agentic-security-assessment/scripts/apply-severity-floors.sh` (new)
- `plugins/agentic-security-assessment/knowledge/severity-floors.json` (new; documents recognized floor classes. See Schema correction above — the actual floor value comes from the entry rationale, not this file.)
- `plugins/agentic-security-assessment/tests/scripts/apply-severity-floors.test.sh` (new)
- `plugins/agentic-security-assessment/tests/scripts/fixtures/severity-floors/**` (new)

**Commit**: `feat(security-assessment): ship apply-severity-floors.sh with externalized floor table`

---

### Step 4: Ship `apply-accepted-risks.sh` + format doc + primitives-contract schema

**Complexity**: complex
**Why last among scripts**: Introduces a new parse format (ACCEPTED-RISKS.md YAML-frontmatter), writes a new JSONL artifact whose schema must be registered in the primitives contract (which lives in the sibling plugin `agentic-dev-team`), and handles expiry semantics. Largest cross-cutting surface.

**Canonical ACCEPTED-RISKS.md format** (committed to the plan before RED so implementer and reviewer share one reference):

The machine-parseable block is a fenced ```` ```json ```` code block. The first such block in the file is the authoritative data. This avoids a pyyaml dependency (the plugin already depends on `jq`) while keeping ACCEPTED-RISKS.md human-readable. Free prose surrounding the block is ignored by the parser.

````markdown
# ACCEPTED-RISKS

Suppression entries for this repo. The `json` block below is parsed by
`apply-accepted-risks.sh`; free prose surrounding it is ignored.

Times are UTC. Globs use bash-extglob semantics only (no Python fnmatch
variance — the parser uses `[[ "$source_ref" == $glob ]]` with
`shopt -s extglob globstar`).

```json
{
  "accepted_risks": [
    {
      "rule_id": "semgrep.csharp.sqli.raw-sql-concat",
      "source_ref_glob": "src/Legacy/**/*.cs",
      "reason": "Legacy reporting module scheduled for deletion Q3 2026 (ACI-RPT-1234).",
      "expires": "2026-09-30"
    },
    {
      "rule_id": "hadolint.DL3003",
      "source_ref_glob": "docker/base/Dockerfile",
      "reason": "Base image built in a controlled CI step; cd is intentional.",
      "expires": "2027-01-01"
    }
  ]
}
```

Additional context, justification history, and approvals can live as free
prose anywhere outside the `json` block.
````

Field semantics:
- `rule_id` — exact string match against a finding's `rule_id`.
- `source_ref_glob` — bash-extglob pattern matched against a finding's `source_ref`. `**` recurses directories; `*` does not cross `/`. No Python fnmatch variance — parser uses `[[ "$source_ref" == $glob ]]` with `shopt -s extglob globstar`.
- `reason` — required human-readable string; copied into the suppression log for audit.
- `expires` — required `YYYY-MM-DD` UTC calendar date; entry is active up to and including that date, and expired starting the day after.

Parse contract:
- Valid JSON in the first ```` ```json ```` block and an `accepted_risks` array at the top level → proceed.
- Missing `json` block → no-op (exit 0) — treat as "no suppressions declared".
- Malformed JSON → exit 3 with `apply-accepted-risks.sh: ACCEPTED-RISKS.md parse error at <location> — <detail>; no risks applied` to stderr; findings file unchanged.
- Missing required field on any entry → exit 3.

**RED**:
- Create `docs/accepted-risks-format.md` describing the above (the plan already fully specifies it; the file makes it discoverable outside the plan).
- Create fixtures under `tests/scripts/fixtures/accepted-risks/`:
  - `target-none/` (no ACCEPTED-RISKS.md)
  - `target-match-exact/` (ACCEPTED-RISKS.md with exact `source_ref_glob` matching one finding)
  - `target-match-glob/` (ACCEPTED-RISKS.md with `src/**/*.cs` matching two findings)
  - `target-expired/` (ACCEPTED-RISKS.md entry with `expires: 2025-01-01`)
  - `target-mixed/` (findings-<slug>.jsonl with one matching + one non-matching finding)
  - `target-malformed/` (ACCEPTED-RISKS.md with broken YAML syntax)
- Create `tests/scripts/apply-accepted-risks.test.sh` with test cases:
  - `-h` prints usage with exit-code contract (0/1/2/3); missing-argument validation.
  - No ACCEPTED-RISKS.md → exit 0, findings file unchanged, no log written.
  - Exact match: finding removed from `findings-<slug>.jsonl`; `accepted-risks-<slug>.jsonl` records one suppression entry with `rule_id`, `source_ref`, `reason`, and `iso`.
  - Glob match: two matching findings each suppressed individually; one log record per suppression.
  - Expired entry: logged with `{"status": "expired", "rule_id": ..., "expires": ..., "iso": ...}`; finding is retained.
  - Malformed YAML → exit code **3**; stderr contains `"ACCEPTED-RISKS.md parse error"`; findings file unchanged.
  - Missing-required-field (e.g., entry without `reason`) → exit 3 with parse error; findings file unchanged.
  - Atomic rewrite: simulate interruption after `.tmp` is written but before `mv`; assert original `findings-<slug>.jsonl` is intact.
  - Idempotency: re-run produces byte-identical findings + log.
- Run runner → RED.

**GREEN**:
- Create `plugins/agentic-security-assessment/scripts/apply-accepted-risks.sh`:
  - Header + shebang + `set -euo pipefail` + pattern-convention line.
  - `-h` prints usage with the exit-code contract.
  - Parse ACCEPTED-RISKS.md's first fenced ```` ```json ```` code block via awk, then validate with `jq empty` + a Python stdlib validator (top-level `accepted_risks` array, per-entry required fields, `YYYY-MM-DD` expires format). On any error emit the parse-error template and exit 3. (Fenced-JSON replaces YAML frontmatter per the defaults approved in session — no new deps.)
  - Hand-rolled `glob_to_regex` in Python implements the documented semantics (`*` excludes `/`, `**` recurses, `?` matches a single non-`/` char) deterministically across Python versions; the format doc at `docs/accepted-risks-format.md` is the single source of truth for the grammar.
  - For each finding: iterate active (non-expired) entries; first matching entry suppresses.
  - Expired entries (today UTC > `expires`): emit `status: expired` log record; do not suppress any finding for that entry.
  - Atomic rewrite of findings file (`<path>.tmp` then `mv`); append-only log.
- Create `plugins/agentic-security-assessment/docs/accepted-risks-format.md` with the canonical example above + field semantics + error-exit-code table.
- Update `plugins/agentic-dev-team/knowledge/security-primitives-contract.md`: add schema sections for `accepted-risks-<slug>.jsonl` (two record shapes: suppression + expired) and `severity-floors-log-<slug>.jsonl`. Add a paragraph noting the primitives contract is the canonical cross-plugin schema registry and that producer plugins PR into it rather than forking it (addresses Design reviewer's observation).
- Run runner → GREEN.

**REFACTOR**:
- If Step 1's `scripts/_lib.sh` was deferred (per the "3+ scripts use the same helper verbatim" threshold documented in Step 5), revisit: at this point four scripts exist; if any usage-printer / arg-validator / ms-epoch helper is identical verbatim across 3+ of them, extract now. Otherwise keep inline.
- `shellcheck` clean.

**Files**:
- `plugins/agentic-security-assessment/scripts/apply-accepted-risks.sh` (new)
- `plugins/agentic-security-assessment/docs/accepted-risks-format.md` (new)
- `plugins/agentic-security-assessment/tests/scripts/apply-accepted-risks.test.sh` (new)
- `plugins/agentic-security-assessment/tests/scripts/fixtures/accepted-risks/**` (new)
- `plugins/agentic-dev-team/knowledge/security-primitives-contract.md` (edit: add schemas + registry paragraph)

**Commit**: `feat(security-assessment): ship apply-accepted-risks.sh with YAML-frontmatter format`

---

### Step 5: Integrate with CI + CHANGELOG + end-to-end smoke

**Complexity**: standard
**Why last**: Touches the plugin's CHANGELOG and CI wiring. End-to-end smoke against `spnextgen/ivr` is the integration-level acceptance.

**RED**:
- Add a CI job (wherever the plugin's CI is defined) that runs `bash plugins/agentic-security-assessment/tests/scripts/run-all.sh` and `shellcheck plugins/agentic-security-assessment/scripts/*.sh plugins/agentic-security-assessment/tests/scripts/*.sh`. Assertion: the CI workflow file has both steps.
- E2E smoke test (manual, captured in PR description, not CI): run `/security-assessment /Users/finsterb/_git-aci/ng-security-scan/targets/spnextgen/ivr` and assert:
  - `memory/phase-timings-ivr.jsonl` has ≥ 2× phase count records (start + end per phase).
  - `memory/severity-floors-log-ivr.jsonl` exists and is non-empty.
  - No log line contains "helper script not present" or "skipped phase timing."
- Until the CI wiring is in place → RED.

**GREEN**:
- Update the plugin's CI workflow (GitHub Actions if that's what the plugin uses) to run `run-all.sh` and `shellcheck`.
- Append one-line entry to `plugins/agentic-security-assessment/CHANGELOG.md` under the next version heading: `"Shipped phase-timer.sh / apply-accepted-risks.sh / apply-severity-floors.sh / find-ci-files.sh that the security-assessment orchestrator spec had always referenced."`
- Run E2E smoke against `spnextgen/ivr`; capture output in the PR description.

**REFACTOR**:
- Apply the `scripts/_lib.sh` rule: extract to `_lib.sh` only if the same helper (usage printer, arg validator, ms-epoch producer) appears **verbatim in 3 or more scripts**. Otherwise leave inline. Document the decision (extracted vs. kept inline) in the PR description.

**Files**:
- Plugin CI workflow (path determined at implementation time — if the plugin has no standalone CI, escalate to the human before adding one)
- `plugins/agentic-security-assessment/CHANGELOG.md` (edit)

**Commit**: `chore(security-assessment): wire helper-script tests into CI + changelog`

## Complexity Classification

| Step | Rating | Reasoning |
|------|--------|-----------|
| 1 | standard | Establishes new harness + ships one simple script; covered by inline review on test + script |
| 2 | standard | Discovery-only, pattern-matching logic, fixture-driven tests |
| 3 | complex | Byte-identical regression test against external reference; idempotency; externalized floor table spans two files |
| 4 | complex | New parse format + schema update to sibling plugin's primitives contract; expiry semantics are subtle |
| 5 | standard | CI wiring + CHANGELOG + smoke, no new logic |

## Pre-PR Quality Gate

- [ ] All shell tests pass: `bash plugins/agentic-security-assessment/tests/scripts/run-all.sh`
- [ ] `shellcheck` passes on every new `.sh` file (scripts + tests)
- [ ] `/code-review` passes on the PR
- [ ] E2E smoke against `spnextgen/ivr` produces the expected memory artifacts with no "helper script not present" messages
- [ ] Byte-identical assertion against `severity-floors-log-extranetapi.jsonl` passes
- [ ] Primitives contract update (`plugins/agentic-dev-team/knowledge/security-primitives-contract.md`) is reviewed by a maintainer of that plugin — cross-plugin coupling warrants an explicit ack
- [ ] Documentation updated: `docs/accepted-risks-format.md` exists and matches script behavior; primitives contract lists both new JSONL schemas
- [ ] `CHANGELOG.md` entry present

## Risks & Open Questions

- **Step 3 fixture reconstruction (acknowledged + fallback committed)** — the 2026-04-24 reference log exists but the pre-floor disposition register must be reverse-engineered. The fallback (schema-identical + 5-row spot-check) is now an explicit acceptance criterion and a codified Step 3 RED procedure, not a buried note. Risk: medium; mitigation is in-plan.
- **Cross-plugin edit to `plugins/agentic-dev-team/knowledge/security-primitives-contract.md` in Step 4** — primitives contract is the canonical shared schema registry; producer plugins PRing into it is the intended pattern. Pre-PR gate already requires a dev-team-plugin maintainer ack. Open question: do the two plugins release independently? If yes, the schema update may need to land and release in `agentic-dev-team` before `agentic-security-assessment` can reference it. Action at implementation time: verify release coupling before merging; split into a dependent-PR pair if independent.
- **Plugin CI existence** — Step 5 wires tests into CI. If the plugin has no standalone CI workflow, stop and escalate before inventing one. Risk: low.
- **Concurrent writers on `disposition-<slug>.json`** — `apply-severity-floors.sh` rewrites atomically but assumes serialized callers. Phase-ordering contract (must run after fp-reduction, before narrative) is documented in the script header. Risk: low; mitigation: contract-via-header is commensurate with the pipeline's single-writer expectation. If concurrent-writer support becomes necessary, add `flock` in a follow-up.
- **Bundled vs. split scope** — spec flagged four-slice bundling; plan bundles for harness reuse and single CHANGELOG. Each step commit is self-contained, so a split-at-merge fallback is always available. Risk: low.
- **Cross-script duplication threshold** — `scripts/_lib.sh` extraction rule is "3+ identical helpers"; implementer may disagree in practice. Resolution: decision + rationale recorded in the PR description; reviewers can override.

## Plan Review Summary

Four reviewer personas ran in parallel. Iteration 1: Design and Strategic approved; Acceptance and UX flagged blockers. Plan was revised; Acceptance and UX re-ran in iteration 2, both approved.

**Iteration 2 verdict: all four approve.**

| Reviewer | Iter-1 | Iter-2 | Key contribution |
|----------|--------|--------|------------------|
| Acceptance Test Critic | needs-revision (3 blockers, 2 warnings, 4 missing scenarios) | **approve** | Caught the untestable byte-identical criterion, the scenario Given that referenced an uncommitted artifact, and the missing malformed-input error path. |
| Design & Architecture Critic | **approve** (3 warnings, 5 observations) | not re-run | Flagged concurrent-writer contract on disposition register; flagged that YAML+python parsing violated the spec's no-new-deps stance — resolved by switching floor table to JSON. Flagged no pattern-adherence check against existing `check-severity-consistency.sh` / `verify-report.sh` — resolved by adding a Step 1 prelude. |
| UX Critic | needs-revision (3 blockers, 3 warnings) | **approve** | Caught that error-path UX (stderr templates, exit-code contracts, canonical ACCEPTED-RISKS.md example) was deferred to docs instead of fixed in the plan. Result: four-value exit-code contract (0/1/2/3) declared in every `-h` output. |
| Strategic Critic | **approve** (2 warnings, 2 observations) | not re-run | Confirmed problem fit, scope sizing, and step ordering are sound. Flagged cross-plugin coupling to `agentic-dev-team` schema registry — mitigation (Pre-PR ack) is in place. |

**Changes made in response to reviews:**

1. **Acceptance criteria** — rewrote 6 criteria: split malformed-YAML error path from idempotency, made byte-identical-vs-fallback explicit, added exit-code contracts, added atomic-rewrite for `apply-accepted-risks.sh`, added `find-ci-files.sh` non-existent-target error, added `-h` excluded-roots and exit-code declaration, switched floor table to JSON.
2. **Gherkin scenarios** — added 7 new scenarios (malformed YAML; atomic rewrite under interruption; exact-match vs glob-match; already-at-floor idempotency guardrail; missing-disposition exit code 2; nonexistent target-dir for find-ci-files; harness self-test for run-all.sh). Rewrote macOS portability scenario to test-independent preconditions.
3. **Step 1** — added pattern-convention prelude (adopt style of existing scripts) and harness self-test (`run-all.self-test.sh`).
4. **Step 3** — made the byte-identical → schema-spot-check fallback an in-step procedure with stop/commit/record instructions. Switched floor table from `.yaml` to `.json` (eliminates yq/python3 branch). Documented phase-ordering contract in script header.
5. **Step 4** — committed the canonical ACCEPTED-RISKS.md example, field semantics, UTC expiry, and bash-extglob-only glob syntax directly in the plan. Added required-field validation → exit 3. Added schema-registry paragraph to primitives contract update.
6. **Step 5** — made the `_lib.sh` extraction rule explicit ("3+ identical helpers").
7. **Risks** — promoted the Step 3 fallback from a risk note to in-step acceptance. Reframed remaining risks with concrete mitigations.

**Carried-forward warnings** (non-blocking, to track at implementation time):
- Cross-plugin primitives-contract edit may couple to `agentic-dev-team` release cycle — verify before merging.
- Plugin CI workflow existence must be confirmed at Step 5 start; escalate if absent.
- Concurrent-writer protection on `disposition-<slug>.json` is contract-based (header docs + serialized callers), not `flock`-based. Revisit if concurrent-caller support becomes required.
