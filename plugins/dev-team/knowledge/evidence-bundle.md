# Evidence Bundle

A structured "what was checked, and what wasn't" statement carried by `/build`'s
final output and `/pr`'s PR body. Verification here is a stack of scoped
verifiers — unit suite, type check, lint, review agents, coverage delta,
runtime verification (sub-step 4.9), Farley score — not one boolean. A green checkmark alone
over-claims: it says checks passed but not what each one actually verified,
what it structurally cannot verify for this diff, which regions remain
untested, or what risk was consciously accepted. The bundle closes that gap.

**Reporting only — no new checks.** The bundle is assembled entirely from data
the pipeline already produces: quality-gate outputs, `.claude/metrics/review-value.jsonl`,
`metrics/verify-log.jsonl`, coverage baseline/delta files, and gate-bypass audit
lines already written to the build/PR output. Assembling it never re-runs a
check, never invokes a tool "just to build the bundle."

Reference form: `${CLAUDE_PLUGIN_ROOT}/knowledge/evidence-bundle.md`.

## The four fixed sections

Always present, in this order, with these exact headers. **Degradation rule**:
when a section has no data, it states why (e.g. "not measured — no coverage
tool detected") — it is never dropped. All four headers always appear even on
a run with nothing to report in one of them.

| Section | Content | Data source (already produced) |
|---|---|---|
| Checks run | One row per verifier: exact command executed + result summary | `/pr` Step 2 gate commands/output; `/build` Step 5 suite output, Step 6 review status, Step 7 Farley score |
| Scope notes | What the executed suite does NOT verify for this diff | Review agents dispatched vs. skipped; gate steps reported "not applicable"; `metrics/verify-log.jsonl` `skipped` reasons; absent tools (coverage, mutation) |
| Untested regions | Coverage-derived statement of what the diff leaves unexercised | `baseline-coverage.json` + `coverage-history.json` line/branch % and delta; diff-scoped uncovered files from a coverage report artifact when one exists; "not measured" when none exists |
| Residual risks | Consciously accepted risk, derived-first | Deferred/escalated findings (`.claude/metrics/review-value.jsonl`), gate-bypass audit lines, structural-review waivers, negative coverage-delta warnings; author-judged prose may be appended but never substitutes for the derived rows |

## Skeleton

```markdown
## Evidence Bundle

**Checks run**
- `<exact command>` — <result summary>
- `<exact command>` — <result summary>
(N checks total; showing top N — see full log at <pointer> if truncated)

**Scope notes**
- <what this suite does not cover for this diff, one line each>

**Untested regions**
- <line/branch % + delta, or diff-scoped uncovered files, or "not measured — <reason>">

**Residual risks**
- <deferred/escalated finding, waiver, or bypass line — or "None identified" only when every derived source is empty>
```

## Degradation examples

- No coverage tool detected:
  `Untested regions: not measured — no coverage tool detected in this repo.`
  paired with a matching Scope note: `Scope notes: coverage delta unavailable — no coverage baseline exists for this repo.`
- No deferred/escalated findings, no waivers, no bypass lines, no negative
  coverage delta: `Residual risks: None identified — no deferred findings, waivers, or bypass lines this run.`
- Non-interactive bypass recorded during the run: fold the audit line in verbatim,
  e.g. `Residual risks: Acceptance-criteria gate auto-passed with 1 flagged criterion (non-interactive) — no human gate.`

## Line budget

Target **under ~40 lines** in a PR body. When a section's data would exceed
that, collapse to counts plus a pointer to the full log rather than growing
unbounded — e.g. `12 checks run, 12 passed (full command log in build output above)`
instead of listing all 12 rows.

## Assembly is per-command, not handed off

`/build` assembles its bundle from its own run's Step 5/6/7 outputs at Step 8.
`/pr` assembles its bundle from its own Step 2 quality-gate results plus
on-disk pipeline data (metrics files, coverage files) at its own runtime —
never from a handoff file written by `/build`. Running `/pr` standalone (no
preceding `/build` in the session) still produces a complete bundle; sections
degrade per the rule above wherever the on-disk data doesn't cover a source
that only `/build`'s in-session steps would have (e.g. Farley score).

## Boundaries

- Does not persist to `.claude/metrics/` or `.claude/memory/` — every underlying datum already
  persists in its own source file; a persisted bundle would duplicate that
  audit trail.
- `/code-review`'s own report keeps its existing contract
  (`knowledge/review-template.md`); it is one **input** to the bundle's Checks
  run section, not a carrier of the bundle itself.
- Never displaces the PR body's closing keywords (`Closes #N` / `Part of #`)
  or its other sections (`## Summary`, `## Quality Gate`, `## Decisions &
  Assumptions`, `## Test Plan`) — it is added alongside them.
