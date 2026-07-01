---
name: test-improve
description: >-
  Consolidated analyze-then-improve test orchestrator. Defaults to lightweight
  ceremony; opts into heavier capabilities (Gherkin extraction, mutation
  testing, refactor-for-testability) only when the operator asks. Always
  baselines coverage (and mutation, when enabled) before any test change, runs
  the end-of-phase review loop after Phases 4 and 5, and produces a stable
  10-section executive-summary report. Replaces /test-modernize and
  /test-upgrade. Use when the user says "improve our tests", "modernize the
  test suite", "upgrade our tests", or runs /test-improve.
argument-hint: "<repo-path> [--parent <url>] [--analyze-only] [--from-phase <n>] [--stack <id>]"
role: orchestrator
user-invocable: true
allowed-tools: Read, Grep, Glob, Bash(git diff *), Skill, Agent
---

# Test Improve

Role: orchestrator. This command sequences existing skills and agents through a
seven-phase analyze-then-improve workflow; it does **not** implement, audit, or
write tests itself. Each phase is **delegated** to the worker skill or agent
that owns it, and per-phase progress is persisted to
`memory/test-improve/<slug>/phase-<n>.md` so `/continue` (and `--from-phase`)
can resume.

You have been invoked with the `/test-improve` command.

## Orchestrator constraints

1. **Delegate every phase.** Call the owning skill or agent (`/test-health`,
   `/gherkin-derive`, `/issues-from-assessment`, `/build`, `/coverage-baseline`,
   `/coverage-delta`, `/mutation-testing`, `mutation-kill` agent,
   `/quality-targets-converge`, `/test-design`, `/code-review`, `/apply-fixes`).
   Never re-implement their logic here.
2. **Honor the human gates.** Do not advance past a gate without explicit
   approval.
3. **Confirm the approach first.** Phase 0 owns the approach contract; do not
   start work until it has completed and its answers are persisted.
4. **Baseline before changing anything.** Coverage (and mutation, when
   enabled) must land in `memory/test-improve/<slug>/` before any file under
   the stack's test directory is modified.
5. **Be concise.** Report each phase's outcome and the next gate, nothing
   more.

## Parse Arguments

- Positional: `<repo-path>` (default: cwd).
- `--parent <url>` — optional tracker parent issue URL; the host selects the
  CLI (ADO / GitHub / GitLab / Jira). Omit for **local-files mode** (the
  default), which writes to `./reports/test-improve/` and `./plans/test-improve/`.
- `--analyze-only` — run Phase 0 then Phase 1 and **exit after Phase 1** with a
  summary of the improvement plan. No baseline is captured; no code changes.
- `--from-phase <n>` — skips completed phases and resumes at phase `n` when
  `memory/test-improve/<slug>/phase-<n-1>.md` exists. `--from-phase` does
  **not** re-prompt Phase-0 inputs; to change them, delete
  `memory/test-improve/<slug>/phase-0.md` and re-run from Phase 0.
- `--stack <id>` — force a stack profile (e.g. `js`, `dotnet`, `java`, `go`)
  when manifest detection is ambiguous.

## Phase-start banner

At the start of every phase (0..7), print a two-line banner:

```
Phase N/7 — <phase name>
mutation: <on|off> · binding: <none|xunit-with-annotations|bdd-runner> · refactor: <no-refactor|refactor-allowed> · sink: <tracker|local>
```

The recap line reflects the still-active Phase-0 settings so an operator
resuming via `--from-phase` (or returning to a long-running session) sees the
current phase and active settings without scrollback archaeology.

## Steps

### Phase 0 — Approach contract

Resolve every ambiguous input in **one batch** before any work starts, then
persist the resolved inputs to `memory/test-improve/<slug>/phase-0.md`. The
file must exist **before Phase 1** runs.

**Detect language(s) and stack profile.** Inspect manifests for JS/TS
(`package.json`), Java (`pom.xml` / `build.gradle`), C# (`*.csproj`), and Go
(`go.mod`). If `--stack` was passed, honor it. Record the resolved stack in
`phase-0.md`.

**Go advisory (shown before the mutation prompt when Go is detected).**

> Mutation testing on Go uses **go-mutesting**, which is **alpha**-quality.
> Survivor count is **not a gate** on Go — treat it as advisory. For real
> confidence in Go tests, prefer `go test -fuzz` on the parts of the code
> that reward it. The orchestrator will still record baseline and delta
> numbers, but the Phase-6 mutation target is advisory-only for Go.

**Prompt battery (one batch, five knobs).** Each prompt displays its default in
`[brackets]`; pressing **Enter accepts every default in one keystroke**.

1. **Mutation on/off** — `[off]`. Default is **off** (lightweight ceremony).
   Turn on when the suite is already high-coverage and the team wants
   assertion-strength feedback.
2. **BDD rubric** — five yes/no questions from
   `knowledge/references/bdd-value-guide.md`. **Default `none`** if the
   operator declines to answer. Scoring: ≥3 yes → `bdd-runner` recommended;
   1–2 yes → `xunit-with-annotations` recommended; 0 yes → `none`.
3. **Refactor mode** — `[no-refactor]`. Default is **`no-refactor`**. Choose
   `refactor-allowed` to permit production-code changes in Phase 5 (seams
   only; existing tests may not be modified or removed).
4. **Quality targets** — defaults: coverage ≥ 90% line + branch; surviving
   mutants = 0 (only when mutation enabled); determinism = 100%; wall-clock =
   fastest achievable. Any target can be overridden here; overrides land in
   `phase-0.md` and flow into Phase 6.
5. **Sink** — `--parent <url>` selects a tracker (ADO / GitHub / GitLab /
   Jira via the host CLI); missing CLI or omitted flag falls back to
   **local-files** mode (writes under `./reports/test-improve/` and
   `./plans/test-improve/`).

**Persistence.** Write the resolved inputs to `memory/test-improve/<slug>/phase-0.md` before Phase 1 runs — Phase 1 must not start until `phase-0.md` exists.

**Immutability.** Phase-0 answers are **immutable** for the remainder of the
run. `--from-phase` does not re-prompt Phase-0 inputs. To change them, delete
`memory/test-improve/<slug>/phase-0.md` and re-run from Phase 0.

**`--analyze-only` semantics.** With `--analyze-only`, Phase 0 completes as
normal, Phase 1 (`/test-health`) runs, and the orchestrator **exits after
Phase 1** with a summary of the improvement plan. No baseline is captured; no
code changes.

**`--from-phase` semantics.** `--from-phase <n>` **skips** phases `0..n-1`
when their `memory/test-improve/<slug>/phase-<i>.md` files exist and resumes
at phase `n`. Phase-0 inputs are read from `phase-0.md` (never re-prompted).

**Phase-4b prompt letter.** The Phase-4b refactor-decision prompt uses
`[y/b/q]` (not `[r]`). The letter `r` is already claimed by mutation-kill's
`[c/r/w/q]` (retry) and the review-loop's `[r/w/q]` (revise); reusing `r` a
third time at the highest-consequence prompt in the flow would produce
operator confusion. `[y]` advances to Phase 5; `[b]` backlogs the
REFACTOR_REQUIRED items and skips to Phase 6; `[q]` quits before Phase 6.

### Phase 1 — Analyze via /test-health

Delegate the entire analysis pass to **`/test-health`** — it is the **sole
worker** for Phase 1. Invoke it exactly once with the resolved repo path from
Phase 0. `/test-health` internally orchestrates whatever sub-skills it needs
(CD-alignment audit, test-design assessment, mutation-testing roll-up); the
orchestrator must **not** invoke `/cd-test-architecture`, `/test-design`, or
`/mutation-testing` separately here. Any prior workflow that reached those
skills directly is superseded by the single `/test-health` call.

**Mutation section respects Phase 0.** When `phase-0.md` recorded
**mutation off**, the rolled-up report's mutation section is either **omitted**
or marked "not enabled for this run". `/test-health` is not invoked with a
mutation flag — the setting flows through from `phase-0.md` and the section is
handled at report time.

**Output.** Persist the rolled-up analysis plus the ordered improvement plan to
`memory/test-improve/<slug>/phase-1.md`.

**Human gate.** After `/test-health` returns, present **the ordered improvement
plan** to the operator and wait for explicit approval. **Phase 2 does not run**
until the operator approves. This is the human gate for Phase 1; do not advance
past it without approval.

### Phase 2 — Baseline (coverage + mutation)

Capture the objective starting point **before any file under the stack's test
directory is modified**. Baselines are the ground truth every downstream delta
compares against; running any test edit before baseline capture invalidates
the whole run.

**Coverage baseline.** Invoke `/coverage-baseline --workflow test-improve`
against the resolved repo path. Persist the result to
`memory/test-improve/<slug>/baseline-coverage.json`.

**Mutation baseline (mutation-on only).** When `phase-0.md` recorded
**mutation on**, invoke `/mutation-testing --baseline --workflow test-improve`.
Persist the result to `memory/test-improve/<slug>/baseline-mutation.json`. The
file records the **honest score**: hard kills / effective total, with the
**timeout count reported separately** (timeouts are not counted as kills).

**Mutation-off skip.** When `phase-0.md` recorded **mutation off**,
`/mutation-testing` is **not invoked** and no `baseline-mutation.json` is
written. The Phase-6 mutation target is later marked "not enabled", not waived
(see Phase 6).

**Go advisory marker.** When the resolved stack is Go and mutation is on, the
mutation baseline is **advisory only** — go-mutesting is alpha-quality (see the
Go advisory in Phase 0). `baseline-mutation.json` is written with the
`advisory-only: true` marker; survivor counts are not a gate.

**Ordering invariant.** Baselines land **before any test file is modified** — no file under the stack's test directory may change between Phase 0 and the creation of `baseline-coverage.json` (and `baseline-mutation.json` when applicable). Phase 2b, Phase 4, and any subsequent test edits depend on this ordering.

_(Phases 2b..7 are added in subsequent slices.)_
