---
name: test-improve
description: >-
  Consolidated analyze-then-improve test orchestrator. Defaults to lightweight
  ceremony; opts into heavier capabilities (Gherkin extraction, mutation
  testing, refactor-for-testability) only when the operator asks. Always
  baselines coverage (and mutation, when enabled) before any test change, runs
  the end-of-phase review loop after Phases 5 and 7, and produces a stable
  10-section executive-summary report. Use when the user says "improve our
  tests", "modernize the test suite", "upgrade our tests", or runs
  /test-improve.
argument-hint: "<repo-path> [--parent <url>] [--analyze-only] [--from-phase [<n>]] [--stack <id>]"
role: orchestrator
user-invocable: true
allowed-tools: Read, Grep, Glob, Bash(git diff *), Bash(python3 *), Skill, Agent
---

# Test Improve

Role: orchestrator. This command sequences existing skills and agents through a
ten-phase (0-9) analyze-then-improve workflow; it does **not** implement, audit, or
write tests itself. Each phase is **delegated** to the worker skill or agent
that owns it, and per-phase progress is persisted to
`.claude/memory/test-improve/<slug>/phase-<n>.md` so `/continue` (and `--from-phase`)
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
   enabled) must land directly in `.dev-team-reports/test-improve/<slug>/data/`
   before any file under the stack's test directory is modified.
5. **Be concise.** Report each phase's outcome and the next gate, nothing
   more.

## Parse Arguments

- Positional: `<repo-path>` (default: cwd).
- `--parent <url>` — optional tracker parent issue URL; the host selects the
  CLI (ADO / GitHub / GitLab / Jira). Omit for **local-files mode** (the
  default), which writes to `.dev-team-reports/test-improve/` and `.claude/plans/test-improve/`.
- `--analyze-only` — run Phase 0 then Phase 1 directly and **exit after Phase 1** with a
  summary of the improvement plan (bypassing the default Baseline/Derive-Gherkin
  ordering — see Phase 0's `--analyze-only` semantics). No baseline is
  captured; no code changes.
- `--from-phase [<n>]` — skips completed phases and resumes at phase `n` when
  `.claude/memory/test-improve/<slug>/phase-<n-1>.md` exists. **The number is
  optional.** Passed with **no argument**, `/test-improve` **auto-detects** the
  resume point from `.claude/memory/test-improve/<slug>/` (see the `--from-phase`
  semantics below): it resumes at the phase after the highest completed
  progress file and prints which phase it resolved to and why. An explicit
  `<n>` **overrides** auto-detection. Either form does **not** re-prompt
  Phase-0 inputs; to change them, delete
  `.claude/memory/test-improve/<slug>/phase-0.md` and re-run from Phase 0.
- `--stack <id>` — force a stack profile (e.g. `js`, `dotnet`, `java`, `go`)
  when manifest detection is ambiguous.

## Phase-start banner

At the start of every phase, print a two-line banner:

```
Step <position>/<total> — Phase <N>: <phase name>
mutation: <off|kill-loop|baseline+kill-loop> · binding: <none|xunit-with-annotations|bdd-runner> · refactor: <no-refactor|refactor-allowed> · sink: <tracker|local>
```

`<N>` is the phase's stable identity number — unchanged by execution order
(Phase 1 is always Analyze, Phase 2 is always Baseline, etc.). `<position>`
is a **running count of phases printed so far this run, including this
one** — increment it by exactly 1 at each phase-start banner, never
computed from a fixed per-identity table. A bare `Phase N/9` counter would
print non-monotonically under this reordered execution sequence (`2/9` then
`3/9` then `1/9`), reading as a hung or looping run to an operator watching
stdout; a plain running count fixes this without renumbering any phase,
file, or `--from-phase` flag value, and — unlike a fixed per-identity
table — it stays correct regardless of which phases actually execute.

**`<total>` is not always 9 or 10 — compute it, never hardcode it.** Two
independent things vary the count: whether Phase 3 runs (known from Phase
0's BDD binding mode: skipped when `none`, so **-1**) and whether Phase 7
runs (Phase 6's decision — Phase 7 and Phase 8 are **not alternatives**;
when Phase 6 returns `[y]`, both Phase 7 *and* Phase 8 execute in sequence,
so entering Phase 7 is **+1**, not a shared slot). Concretely:

- Base count is **9** (Phases 0, 2, 3, 1, 4, 5, 6, 8, 9 — Phase 7 excluded
  by default).
- **-1** when the Phase-0 BDD binding mode is `none` (Phase 3 never runs) —
  known from Phase 0 onward, so this adjustment is baked into every
  banner's `<total>` from the very first one.
- **+1** the moment Phase 6 resolves to `[y]` (entering Phase 7) — this is
  **not** knowable before Phase 6 fires (an operator in `refactor-allowed`
  mode can still pick `[b]`/`[q]` and skip Phase 7 despite the mode
  permitting it), so `<total>` for Phases 0 through 6's banners uses the
  **without-Phase-7** count; if Phase 6 then returns `[y]`, print one line
  before Phase 7's banner — `Phase 7 entered — total phase count for this
  run is now <new total> (was <old total>).` — and use the new total for
  Phase 7, 8, and 9's banners. When `refactor-mode: no-refactor` (Phase 6
  offers no `[y]` at all) or Phase 6 returns `[b]`/`[q]`, no adjustment ever
  fires and `<total>` stays fixed for the whole run.

This keeps `<position>` strictly monotonic in every run shape, and
`<total>` honest at each point it's printed — correcting exactly once, with
a visible reason, only in the one case (entering Phase 7) that's genuinely
unknowable in advance.

The recap line reflects the still-active Phase-0 settings so an operator
resuming via `--from-phase` (or returning to a long-running session) sees the
current phase and active settings without scrollback archaeology.

## Steps

**Execution order.** Phases below are numbered by stable identity, not by
execution order — Phase 2 (Baseline) and Phase 3 (Derive Gherkin) execute
before Phase 1 (Analyze) so `/test-health` can use documented-but-untested
Gherkin scenarios as a coverage signal. **Document order below matches
execution order**: `0 → 2 → 3 → 1 → 4 → 5 → 6 → 7 → 8 → 9`, where Phase 7
runs only when Phase 6 returns `[y]` (see "Phase-start banner" above for how
this affects the banner's `<total>`) — Phase 7 and Phase 8 always run in
that sequence together, never as alternatives to each other. When the
Phase-0 BDD binding mode is `none`, Phase 3 is skipped and the executed
sequence becomes `0 → 2 → 1 → 4 → 5 → 6 → (7) → 8 → 9`.

## Phase Reference Files

| Phase | Name | Reference file |
| --- | --- | --- |
| 0 | Approach contract | `references/phase-0-approach-contract.md` |
| 1 | Analyze via /test-health | `references/phase-1-analyze.md` |
| 2 | Baseline | `references/phase-2-baseline.md` |
| 3 | Derive Gherkin | `references/phase-3-derive-gherkin.md` |
| 4 | Plan fixes | `references/phase-4-plan-fixes.md` |
| 5 | Improve without refactoring | `references/phase-5-improve.md` |
| 6 | Refactor decision | `references/phase-6-refactor-decision.md` |
| 7 | Refactor-for-testability | `references/phase-7-refactor.md` |
| 8 | Validate | `references/phase-8-validate.md` |
| 9 | Executive-summary report | `references/phase-9-report.md` |

Before executing a phase, read only that phase's reference file — never a
phase-specific reference file for a phase already completed in this run or a
prior resumed session. Shared implementation-detail reference files (e.g.
`references/review-loop.md`) are not phase-specific and may be read whenever
the phase you are executing points at them, regardless of whether another
phase also uses them.

This instruction is prose, not a hook-enforced gate — no mechanism in this
repo verifies at runtime that only the active phase's reference file was
read; compliance depends on the executing agent following the rule as
written.

### Phase 0 — Approach contract

<!-- include: references/phase-0-approach-contract.md -->
See `references/phase-0-approach-contract.md` for the full prompt battery and conflict-check mechanics.

### Phase 2 — Baseline (coverage + mutation)

<!-- include: references/phase-2-baseline.md -->
See `references/phase-2-baseline.md` for the full coverage-and-mutation baseline procedure, the coverage-gap ranking, and the ordering invariant.

### Phase 3 — Derive Gherkin (conditional)

<!-- include: references/phase-3-derive-gherkin.md -->
See `references/phase-3-derive-gherkin.md` for the full binding-mode
branches, persistence, human gate, and the bdd-runner pending-stub
interaction with Phase 5 — conditional on the Phase-0 BDD rubric answer.

### Phase 1 — Analyze via /test-health

<!-- include: references/phase-1-analyze.md -->
See `references/phase-1-analyze.md` for the full `/test-health` delegation,
the coverage-gap-ranking ordering rule and its `--analyze-only` no-ranking
case, the test-count-by-type snapshot and existing-snapshot guard, the human
gate, and the `/handoff` suggestion.

### Phase 4 — Plan fixes (partition findings by gap class)

<!-- include: references/phase-4-plan-fixes.md -->
See `references/phase-4-plan-fixes.md` for the full gap-class partitioning,
the coverage-gap-ranking Story order, the persistence path, and the human
gate blocking Phase 5.

### Phase 5 — Improve without refactoring (build + mutation-kill + review loop)

<!-- include: references/phase-5-improve.md -->
See `references/phase-5-improve.md` for the full per-Story build,
coverage-delta, and mutation-kill loop, the pending-stub gate, and the
end-of-phase review loop (which shares `references/review-loop.md` with
Phase 7).

### Phase 6 — Refactor decision (mode-gated)

<!-- include: references/phase-6-refactor-decision.md -->
See `references/phase-6-refactor-decision.md` for the full REFACTOR_REQUIRED
presentation, the `refactor-mode` branch, and the `[y/b/q]` decision prompt.

### Phase 7 — Refactor-for-testability (conditional)

<!-- include: references/phase-7-refactor.md -->
See `references/phase-7-refactor.md` for the full hard mode gate, the seam-only and
existing-tests-immutable constraints, the Phase-5 precondition check, and
the end-of-phase review loop (which shares `references/review-loop.md` with
Phase 5).

### Phase 8 — Validate (converge quality targets)

<!-- include: references/phase-8-validate.md -->
See `references/phase-8-validate.md` for the full mutation-target-per-mode
rules, the branch-scoped mutation validation, the coverage-<90%-in-no-refactor
re-run prompt, the evidence and test-count recount, and the `/handoff`
suggestion.

### Phase 9 — Executive-summary report

Produce a stable executive-summary report from the shipped template. Every
section is present in every run; empty sections **do not disappear** — they
render `_Not applicable — <reason>._` so the shape of the report never changes
between runs.

**Template source.** Copy
`plugins/dev-team/skills/test-improve/templates/executive-summary.md` to the
output path.

**Output path.** `.dev-team-reports/test-improve/<slug>/report-<date>.md` —
the file is always relative to the invocation directory, whether the run used
a tracker sink or local-files mode. Its git-tracked `data/` sibling is
`.dev-team-reports/test-improve/<slug>/data/`.

**Interpolation.** Every placeholder is **interpolated** from two sources:
the git-tracked `.dev-team-reports/test-improve/<slug>/data/` directory
(`test-counts-before.json`, `test-counts-after.json` if Phase 8 ran,
`baseline-coverage.json`, `baseline-mutation.json` in `baseline+kill-loop`
mode, and `coverage-history.json` — each already current there, written
directly at the point of capture by Phase 2 and Phase 5 respectively), and the
process/audit state still under `.claude/memory/test-improve/<slug>/`
(`phase-0.md`, `phase-1.md`, `phase-4.md`, `phase-5-review.json`,
`phase-7-review.json` if Phase 7 ran, `waivers.json`, `phase-8.md`), plus
`.dev-team-reports/test-improve/<slug>/refactor-backlog.md` if Phase 6 chose
`[b]` or Phase 8 wrote a no-refactor-mode entry to it. `mutation-history.json`
is outside this interpolation set — and always has been; it is consumed by
`/coverage-delta` and `/quality-targets-converge`, not by the
executive-summary report, so its absence from this list is not the bug this
plan fixes. `coverage-gap-ranking.json` (issue #1786) is outside it for the
same reason: it is a targeting input read by Phases 1, 4, and 5, not a number
the report interpolates. No placeholder is left literal.

**Empty-section rule.** Sections with no data render `_Not applicable —
<reason>._` (e.g. § 6 when Phase 7 was declined reads "*Phase 7 not run —
operator chose to backlog REFACTOR_REQUIRED items at Phase 6.*"). Sections
are never omitted or hidden — this keeps the report shape stable across runs.

**Mutation row shape (per Phase-0 mutation mode).**

- `off`: `_Not applicable — mutation disabled at Phase 0._`
- `kill-loop`, non-Go: final surviving-mutant count from the Phase-5 kill loop;
  the baseline and Δ cells read `_Not applicable — no baseline run (kill-loop
  mode)._` since no Phase-2 baseline was taken.
- `baseline+kill-loop`, non-Go: honest baseline-to-achieved score (hard kills /
  effective total; timeouts reported separately) with the Δ column populated.
- Go stack (`kill-loop` or `baseline+kill-loop`): honest numbers with the
  "advisory only — go-mutesting is alpha" footnote.

**Parent-issue-or-FEATURE.md link update.** When the run used a **parent
tracker** (Phase 0 selected `--parent <url>`), the parent issue is updated
with a link to `.dev-team-reports/test-improve/<slug>/report-<date>.md`. When
the run was **local-files-only**, `.claude/plans/test-improve/FEATURE.md` is
updated with the same link.

**Regeneratable-from-tracked-data contract.** The report is a **pure
function** of the git-tracked `.dev-team-reports/test-improve/<slug>/data/`
directory (the numbers, already current by construction — each file was
written directly there at the point of capture) plus the process/audit
narrative still under `.claude/memory/test-improve/<slug>/`. Deleting the
report file and re-invoking Phase 9 reproduces the report byte-for-byte —
there is no copy step to re-run, and always exactly one place to read the
numbers from; Phase 9 always reads `data/` directly, unconditionally.

### After Phase 9 — Re-run-with-refactor close-out prompt

**No prompt** when: `.dev-team-reports/test-improve/<slug>/refactor-backlog.md` does not exist (no `REFACTOR_REQUIRED` items were ever backlogged), the file exists but has zero entries (treated the same as absent), `phase-8.md` records `coverage_reprompt_fired: true` (Phase 8's own coverage-driven `[y/n]` already fired this run — no repeating the same question twice), or `phase-0.md` recorded `refactor-mode: refactor-allowed` (a Phase-6 `[b]` backlog entry under `refactor-allowed` mode is the operator's deliberate deferral, not a no-refactor constraint to lift — re-asking "re-run with refactor-allowed mode now?" would be nonsensical when that's the mode already in use).

**Otherwise** (backlog file has ≥1 entry, Phase 8 never fired its prompt,
and `phase-0.md` recorded `refactor-mode: no-refactor`), prompt **`[y/n]`**
— distinct from Phase 8's coverage-driven, mid-run prompt, this one is
backlog-driven and fires at close-out: *"N REFACTOR_REQUIRED items remain
backlogged. Re-run with refactor-allowed mode now? `[y/n]`"* (N = entry
count). `[n]` leaves the backlog as-is. `[y]` — Phase-0 answers are
immutable per-run, so tell the operator to re-run `/test-improve
<repo-path>` fresh, choosing `refactor-allowed`; this is a new invocation,
not `--from-phase`.
