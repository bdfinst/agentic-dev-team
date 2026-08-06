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
