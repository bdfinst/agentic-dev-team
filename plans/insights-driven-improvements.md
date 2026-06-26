# Plan — insights-driven improvements (from the 2026-06-13 usage report)

Source: `docs/specs/insights-reports/report-2026-06-13-050846.html` — a Claude Code
usage analysis over 21 days / 128 sessions. This plan turns its friction findings
into concrete plugin changes.

## North-Star framing

The report's largest friction is **pre-execution misalignment**, not bad code:
**Wrong Approach (8) + Misunderstood Request (5)** plus repeated premature action
("Claude started reading files/verifying before a task was given — twice"). Each is
an avoidable interrupt the user has to issue. The instrument is the report's own
friction counts; the goal is to remove the recurring causes at the source.

This composes with — and sharpens — the Ownership Engineering Clarification Window
(PR #266): OE says *batch your questions once, then commit*; this plan supplies the
**specific high-reversal-cost questions** that empirically cause reverts, and adds
the one precondition OE is silent on (don't investigate before a task exists).

## Scope of this branch (#1 + #2)

Self-standing; off `main` so it composes cleanly whether or not PR #266 has merged.

### 1. Approach contract — `knowledge/decision-defaults.md`

**Friction removed:** 13 alignment-failure events from Claude committing to an
approach that conflicts with intent (merge-vs-replace, PNG-vs-SVG, edit-stub-vs-migrate).
**Change:**

- New `plugins/dev-team/knowledge/decision-defaults.md` — a short reference of the
  recurring high-reversal-cost decision axes, each with *trigger → default stance →
  confirm-before-commit*. Seeded from the report: replace-vs-merge, format fidelity,
  migrate-vs-edit-stub, auto-merge-vs-direct, scope.
- Wire it into the discovery/classification step of `agents/orchestrator.md` and
  `agents/product-manager.md`: screen each request against the file and confirm any
  ambiguous axis in one upfront batch before work begins.
- `skills/plan/SKILL.md`: the plan states its chosen stance on any triggered axis, so
  it's visible at the human plan-gate (where the report shows corrections are cheapest).
**Acceptance:** a bats referential-integrity sensor asserts the file exists and is
referenced by orchestrator, PM, and `/plan`; the knowledge index includes it.

### 2. "No task, no action" precondition

**Friction removed:** premature investigation before an instruction is given (the
report's "fun ending").
**Change:**

- `skills/context-loading-protocol/SKILL.md`: a **Step 0** — confirm an actionable
  task exists before reading files, verifying code, or loading agents.
- `agents/orchestrator.md`: a matching one-line precondition in Decision Making.
- This is the single place the OE rule "investigate, don't escalate" yields:
  investigation is correct *once a task exists*, not before.
**Acceptance:** prose precondition present in both files; covered by the bats sensor.

## Cross-cutting mechanics (both items)

- Update registries: `CLAUDE.md` knowledge-file list (25 → 26) and
  `knowledge/agent-registry.md` table.
- Regenerate `knowledge/index.json` (the knowledge-index freshness gate).
- Add `tests/repo/decision_defaults_refs_test.bats` (bash-3.2-safe, deterministic).
- Run `/agent-audit`; keep within token budgets and claims discipline (no bare
  numeric targets, no metaphor-as-mechanism buzzwords in shipped prose).

### 3. `/upgrade` marketplace pre-flight (implemented)

**Friction removed:** two upgrade sessions stalled by trusting the update mechanism
instead of checking the catalog against the release.
**Change:** `skills/upgrade/SKILL.md` Step 3 now diffs the marketplace's pinned
version against the latest release before concluding the mechanism is broken or the
plugin is up to date; a stale catalog is named as the root cause. Renamed ids migrate
rather than edit a stub in place (cross-links `knowledge/decision-defaults.md`).

### 4. `/ship` pipeline skill + auto-merge default (implemented)

**Friction removed:** the spec→plan→TDD→PR flow re-assembled by hand every session.
**Change:**

- New `skills/ship/SKILL.md` — a thin orchestrator chaining `/specs → /plan → /build
  → /code-review → /pr` with the existing human gates and an upfront approach-contract
  screen. It only sequences; every gate/fix-loop/evidence rule comes from the
  underlying skills. Registered in `CLAUDE.md` and `docs/skills.md`; `/help`
  auto-discovers it via Glob.
- `skills/pr/SKILL.md` now enables auto-merge by default (new Step 5), with
  `--no-auto-merge` to opt out — the auto-merge-vs-direct default from decision-defaults.

## Follow-ups (not this branch)

- **Judge-graded OE fixtures** `oe-10-replace-vs-merge`, `oe-11-no-instruction-yet`
  — added to the OE eval suite once PR #266 merges (the suite lives there, not on main).

## Sequencing & risk

Low risk (prose + one knowledge file + one deterministic test). #1 and #2 ship
together as one focused PR. #3/#4 follow independently.
