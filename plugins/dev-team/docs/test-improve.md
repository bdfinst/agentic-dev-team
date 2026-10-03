# `/test-improve`

**File:** [`skills/test-improve/SKILL.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/skills/test-improve/SKILL.md)
**Role:** orchestrator.

`/test-improve` is the **consolidated** analyze-then-improve orchestrator for
legacy or in-flight test suites. It is one of the plugin's two multi-phase
pipelines with inter-phase human gates (the other is [`/ship`](workflows.md#ship)).
It defaults to lightweight ceremony. It prompts for heavier capabilities
(Gherkin extraction, mutation testing, refactor-for-testability) only on
demand. It always baselines coverage (and mutation, when enabled) before any
test change.

This page is the canonical phase reference. To see where `/test-improve` sits
among the plugin's other commands, read [workflows.md](workflows.md). To see how it
fits the wider agent architecture, read
[agent-architecture.md](agent-architecture.md#test-improvement-workflow-test-improve).

![/test-improve ten-phase (0-9) workflow with human gates between each phase](diagrams/test-improve-flow.svg)

## Phases

Each phase writes a progress file to
`.claude/memory/test-improve/<slug>/phase-<n>.md` so `/continue` (and `--from-phase`)
can resume.

**Execution order.** Phases keep their historical identity numbers (Phase 1
is always Analyze, Phase 2 is always Baseline, and so on). **Baseline (Phase 2)
and Derive Gherkin (Phase 3) execute before Analyze (Phase 1)**, so
`/test-health` can use documented-but-untested Gherkin scenarios as a
coverage signal. The order is `0 → 2 → 3 → 1 → 4 → 5 → 6 → 7 → 8 → 9`.
Phase 7 and Phase 8 are **not alternatives**. When Phase 6 returns `[y]`, both
run in sequence. Otherwise, Phase 8 follows Phase 6 directly. When the BDD
binding mode is `none`, Phase 3 is skipped and the sequence becomes
`0 → 2 → 1 → 4 → 5 → 6 → 7 → 8 → 9`. The list below follows this execution
order, not numeric order. The phase-start banner prints a separate
`Step <position>/<total> — Phase <N>: <name>` counter. `<position>` is a
running count of phases printed so far this run (never a fixed per-identity
slot). `<total>` is computed per run (base 9, -1 when BDD binding mode
is `none`, +1 once Phase 6 enters Phase 7) rather than a hardcoded 9 or 10.

- **Phase 0 — Approach contract.** Batched prompt (Enter accepts all
  defaults): mutation mode `[kill-loop]` (`off` / `kill-loop` /
  `baseline+kill-loop`), BDD rubric `[none]`, refactor `[no-refactor]`,
  quality targets, sink (`--parent <url>` vs local files), and the all-or-none
  code-lookup install (explicit `y`/`n`, not part of Enter-accepts-all). An
  Enter-through run now performs the mutant-kill loop by default. Go stack shows
  the alpha go-mutesting advisory before the mutation prompt. Answers are
  immutable for the run. Phase 0 surfaces a stated coverage target that is
  structurally unreachable under `no-refactor` as `[w] waive / [s] switch
  to refactor-allowed / [c] continue as-is`, computed by
  `scripts/coverage_gap_ranking.py`. With no coverage report on disk yet, Phase 0
  records the check as `deferred` and re-runs it at Phase 2 (#1787).
- **Phase 2 — Baseline (before any test edit).**
  Run `/coverage-baseline --workflow test-improve` unconditionally.
  Run `/mutation-testing --baseline --workflow test-improve` only in
  `baseline+kill-loop` mode (`off` and `kill-loop` take no baseline).
  Go is an advisory-only marker. The honest score counts hard kills and
  reports timeouts separately.
  Then `scripts/coverage_gap_ranking.py` writes
  `data/coverage-gap-ranking.json`: per-module buckets ranked by uncovered
  lines descending, each marked `seam: established|absent`.
  Phases 1, 4, and 5 read this file as their targeting
  input instead of mutation survivors (#1786). A deferred Phase-0 conflict
  check also resolves here.
- **Phase 3 — Derive Gherkin (conditional).** `none` skips entirely (Phase 1
  follows Phase 2 directly in that case). `xunit-with-annotations` writes
  `.feature` files without a runner. `bdd-runner` wires the native parser.
- **Phase 1 — Analyze.** Delegate to `/test-health` (sole worker). Make no
  separate calls to `/cd-test-architecture`, `/test-design`, or
  `/mutation-testing`. Whenever a coverage percentage is a stated goal, order
  the improvement plan's coverage-driven items by
  `coverage-gap-ranking.json` rank, never by mutation survivor count.
  Survivors order work only *within* a `seam: established` module (#1786).
  The mutation section respects the Phase-0 setting. A
  separate, direct classification pass persists a before-snapshot of test
  counts by MinimumCD type to `test-counts-before.json`. `--analyze-only`
  runs Phase 0 then this phase directly, bypasses the Baseline/Derive-Gherkin
  ordering above, and exits with no baseline captured.
- **Phase 4 — Plan fixes.** `/issues-from-assessment --workflow test-improve`
  partitions findings into `NO_REFACTOR` (Phase-5 Stories) /
  `REFACTOR_REQUIRED` (deferred to Phase 7) / `LOW_VALUE` (advisory-only). The
  command writes the NO_REFACTOR Story set in `coverage-gap-ranking.json` rank order
  when a coverage percentage is a stated goal (#1786).
- **Phase 5 — Improve without refactoring.** Per Story, run these steps in order:
  - `/build` (no-refactor).
  - `/coverage-delta --workflow test-improve --story <id>`.
  - `scripts/coverage_delta_steering.py`. Three consecutive near-zero-delta
    Stories exit 3 and prompt `[t] re-check Phase-1 targeting / [c] continue`
    mid-phase (#1790).
  - `mutation-kill` agent, dispatched once per module batch
    (`--file <every story file in the batch> --max-rounds 3
    --target-honest-score <Phase-0 mutation target>`, #2030). Residuals prompt
    `[c/r/w/q]`.
  - `scripts/mutation_yield_steering.py` at the batch boundary. Two consecutive
    batches that kill fewer than the minimum net survivors exit 3 and prompt the
    same `[t] re-check Phase-1 targeting / [c] continue` (#2033). This ports the
    #1790 mechanism to the more expensive lane, sharing its status vocabulary
    and exit-code contract.

  The end-of-phase review loop dispatches `/code-review --since <base-sha> --internal`
  once. It does not dispatch `/test-design` in parallel. `test-review` and
  `test-smell-review` (the two agents `/test-design` used to add) are
  already in `/code-review`'s own roster for a test/seam-scoped diff. That dual
  dispatch was a duplicate, so #1966/#1987 removed it. The loop confirms the
  change-size gate did not drop those two test lenses. It scores
  Farley on the in-scope test files, runs `/apply-fixes`, then runs a narrowed
  re-confirmation (not a full re-dispatch). The cap is 2 iterations, with `[r/w/q]`
  escalation. See `references/review-loop.md` steps 1-5. Evidence is in
  `phase-5-review.json`.
- **Phase 6 — Refactor decision prompt.** `[y] enter Phase 7 / [b] backlog
  and skip to Phase 8 / [q] quit`. The letter `y` is deliberately chosen over
  `r`, which is already claimed by mutation-kill's `[c/r/w/q]` (retry) and the
  review loop's `[r/w/q]` (revise).
- **Phase 7 — Refactor-for-testability (conditional).** Runs only when `[y]`.
  Changes are seam-only production-code changes, and existing tests are immutable.
  Each Story precondition-checks that the paired Phase-5 baseline is closed and
  green. The phase uses the same end-of-phase review loop. Evidence is in
  `phase-7-review.json`.
- **Phase 8 — Validate.** Run `/quality-targets-converge --workflow test-improve
  --refactor-mode <value>`. Threading Phase 0's `no-refactor`/
  `refactor-allowed` value keeps the coverage-gap dispatch table from
  proposing a `[Refactor-for-testability]` Story once Phase 6 chose no-refactor.
  The command writes a `refactor-backlog.md` entry
  instead. Mutation off means skipped (not waived). Go is advisory-only.
  When coverage is below 90% in no-refactor mode, a `[y/n]` re-run-in-refactor-allowed
  prompt lists backlogged items and records `coverage_reprompt_fired: true`
  in `phase-8.md`, so Phase 9's close-out prompt below does not re-ask. The
  identical classification pass from Phase 1 recounts test-by-type into
  `test-counts-after.json`. The workflow suggests `/handoff` here, and after Phase 1
  and the Phase 5/7 review loops, the context-heaviest boundaries.
- **Phase 9 — Executive-summary report.** Interpolates the shipped
  [`templates/executive-summary.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/skills/test-improve/templates/executive-summary.md)
  from the git-tracked `.dev-team-reports/test-improve/<slug>/data/`
  directory plus `.claude/memory/test-improve/<slug>/` process/audit state to
  `.dev-team-reports/test-improve/<slug>/report-<date>.md`. The report has 10
  numbered sections. Empty sections render "Not applicable" (never omitted). § 1
  includes a "Tests by type" table (Baseline/Achieved/Δ per MinimumCD type). § 7
  foregrounds a seam-needed/behavior-gained/estimated-risk table sourced
  from `refactor-backlog.md`. Phase 9 updates the parent tracker (or
  `.claude/plans/test-improve/FEATURE.md`) with a link to the report.
  The report is regeneratable from memory. After Phase 9, if
  `refactor-backlog.md` has entries and Phase 8's re-run prompt never fired
  this run, a close-out `[y/n]` prompt asks whether to re-run with
  refactor-allowed mode.

## Arguments

`/test-improve <repo-path> [--parent <url>] [--analyze-only] [--from-phase <n>] [--stack <id>]`

| Flag | Behavior |
| --- | --- |
| `<repo-path>` | Positional. Path to the repository to improve (required). |
| `--parent <url>` | Post progress and Stories to this tracker issue URL instead of local plan files. |
| `--analyze-only` | Run Phase 0–1 only; skip improvement phases. |
| `--from-phase <n>` | Resume from phase `n` (requires existing `.claude/memory/test-improve/<slug>/` files). |
| `--stack <id>` | Override auto-detected stack identifier (for example `go`, `python`, `java`). |

`/continue` resumes any phase from `.claude/memory/test-improve/<slug>/phase-<n>.md`.
`--from-phase <n>` does the same explicitly and never re-prompts Phase 0.
`--analyze-only` runs Phase 0 + Phase 1 and exits before baseline capture.
