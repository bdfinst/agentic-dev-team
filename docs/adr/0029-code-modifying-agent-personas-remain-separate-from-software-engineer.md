# 29. Code-modifying agent personas remain separate from software-engineer

Date: 2026-07-24

## Status

Accepted

## Context

Issue #1387 audited every agent whose `tools:` frontmatter carries both
`Edit` and `Write` — i.e. every agent that can modify files: `implementer`,
`software-engineer`, `mutation-kill`, `qa-engineer`, `tech-writer`. The
`implementer`/`software-engineer` pair was resolved first (operator
decision, 2026-07-24): `implementer.md`'s own body opened with "You are a
**Software Engineer subagent**..." — it self-identified as a
software-engineer variant, not a distinct role, and both agents declared
identical `model: sonnet`, `effort: high`, `color: yellow`. `implementer.md`
was retired; `/build` and `agents/orchestrator.md` now dispatch
`software-engineer` directly, with the per-step context `implementer.md`'s
prompt used to encode (Code-First Small Batches cadence, "design is
settled — do not design") folded into `skills/build/SKILL.md`'s own dispatch
instructions.

The remaining three agents needed the same scrutiny rather than an assumed
pass: does each carry a distinct behavioral contract, or is it also a
software-engineer variant that happens to have a different `tools:` line?

## Decision

Keep `mutation-kill`, `qa-engineer`, and `tech-writer` as personas separate
from `software-engineer`. Each is retained for a reason specific to its
role, not by default:

- **`mutation-kill`** (`model: opus`, autonomous loop). Not a general
  implementation agent — a single-purpose, scripted survivor-reduction state
  machine: run a scoped mutation tool, generate targeted tests for survivors
  in priority order, verify they compile and pass, commit, and repeat until
  survivors stop decreasing, gating on hard kills only. Its `tools:` grant
  and its `opus` model reflect that narrow, higher-stakes loop, not
  full-stack development. `/mutation-testing` (advisory, classifies
  survivors) and `mutation-kill` (executes the fix) are two ends of the same
  workflow; folding the executor into `software-engineer` would erase the
  autonomous-loop contract (bounded termination condition, commit-per-fix
  discipline) that the rest of the harness dispatches against by name.
- **`qa-engineer`** (test-strategy coaching + browser automation). A
  distinct role, not a coding variant: it partners on acceptance criteria,
  coaches CD-aligned test architecture and test design, and owns browser-based
  exploratory/verification work via its scoped `Bash(npx playwright *)`
  grant — capabilities `software-engineer` does not carry and should not,
  since a coach that also authors the production code it is meant to
  independently assess would collapse the two-perspective review this repo
  relies on (`software-engineer` implements, `qa-engineer` coaches and
  verifies).
- **`tech-writer`** (docs-only, no `Bash`). The narrowest of the three: it
  cannot execute code at all. Its persona (reader-first communicator,
  terminology consistency, progressive disclosure) and its restricted
  `tools:` (`Read, Grep, Glob, Edit, Write, Skill`, no `Bash`) are both
  deliberate — it edits documentation, never code, and the missing `Bash`
  grant is itself a scope enforcement mechanism, not an oversight.

Each agent's own file documents its distinct contract in its `description:`
and body; this ADR is the audit record confirming the distinction was
checked, not assumed, per issue #1387's remaining open scope.

## Consequences

- **Easier**: the fleet's `Edit`+`Write` roster is now fully accounted for —
  every code-modifying agent either merged into `software-engineer`
  (`implementer`) or has a documented, checked reason to stay separate. A
  future audit of this class of overlap can start from this ADR instead of
  re-deriving the same three justifications.
- **Harder / risk**: none of the three decisions are enforced by a
  mechanical gate (unlike, say, ADR 0027's `color:` check) — if
  `mutation-kill`, `qa-engineer`, or `tech-writer` drift toward
  general-purpose implementation over time, nothing fails CI. Re-run this
  audit's question (does the `tools:` overlap still trace to a distinct
  behavioral contract?) if any of the three agents' scope changes
  materially.
