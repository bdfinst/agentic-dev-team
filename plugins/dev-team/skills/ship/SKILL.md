---
name: ship
description: >-
  Run the full spec-to-merge pipeline as one command: spec, plan, TDD build,
  code review, and a PR with auto-merge — pausing at the existing human gates.
  Use when the user says "ship this", "take this feature end to end", or wants
  the spec->plan->build->PR flow without re-assembling it each time.
argument-hint: "<feature-description> [--skip-spec] [--no-auto-merge]"
user-invocable: true
allowed-tools: Read, Glob, Grep, Skill(specs *), Skill(plan *), Skill(build *), Skill(code-review *), Skill(pr *)
---

# Ship

Role: orchestrator. This command chains the existing pipeline skills end to end; it
does not implement, review, or merge anything itself — each phase is delegated to the
skill that owns it, and the existing human approval gates are preserved.

You have been invoked with the `/ship` command.

## Orchestrator constraints

1. **Delegate every phase.** Call the owning skill (`/specs`, `/plan`, `/build`,
   `/code-review`, `/pr`); do not re-implement their logic here.
2. **Honor the human gates.** Do not advance past a gate without explicit approval —
   this command sequences phases, it does not remove their review points.
3. **Confirm the approach first.** Before planning, screen the request against
   `${CLAUDE_PLUGIN_ROOT}/knowledge/decision-defaults.md` and confirm any ambiguous high-reversal-cost axis
   (replace-vs-merge, format fidelity, migrate-vs-edit-stub, scope) in one batch.
4. **Be concise.** Report each phase's outcome and the next gate, nothing more.

## Parse Arguments

Arguments: $ARGUMENTS

- Positional: the feature description (required).
- `--skip-spec`: Skip the spec phase (use when a spec already exists for this work).
- `--no-auto-merge`: Pass through to `/pr` so the PR is not set to auto-merge.

## Steps

### 1. Approach contract

Screen the request against `${CLAUDE_PLUGIN_ROOT}/knowledge/decision-defaults.md`. Surface any ambiguous
axis to the user in a single batch and get the answers before proceeding. Stop here if
a genuinely blocking ambiguity remains.

### 2. Spec (unless `--skip-spec`)

Invoke `/specs` for the feature. `/specs` runs the Ambiguity Resolution Protocol
before finalizing acceptance criteria — any finding classified `requires-stakeholder-input`
is surfaced to the human as a required answer, not an optional confirmation.

**These unresolved items ARE the human gate.** Do not auto-approve past them, even in
non-interactive mode. The only exception is `--skip-spec` (when a reviewed spec already
exists). A spec that passed its consistency gate with undocumented assumptions is not
an approved spec.

Present the completed spec (Intent, Architecture, Acceptance Criteria, and Ambiguity
Log) for human review. **Human gate** — wait for approval before planning.

### 3. Plan

Invoke `/plan` with the (approved) spec. The plan decomposes the feature into vertical
slices with Gherkin scenarios and states the chosen stance on any decision-defaults
axis. **Human gate** — wait for plan approval before building.

### 4. Build

Invoke `/build` to execute the approved plan with RED-GREEN-REFACTOR, inline review
checkpoints, and verification evidence. Do not proceed until the build reports a green
suite.

### 5. Review

Invoke `/code-review` over the changes and let its fix loop converge. Surface any
findings that need human judgment.

### 6. PR

Invoke `/pr` (passing `--no-auto-merge` only if it was given to `/ship`). `/pr` runs
the pre-PR quality gate, opens the PR, and — by default — enables auto-merge so it
lands once checks pass. **Human gate** — the PR is the final review artifact.

### 7. Report

Report the PR URL, the quality-gate result, and whether auto-merge is armed.

## Notes

- `/ship` is sequencing only: every gate, fix loop, and evidence requirement comes from
  the underlying skills. If any phase stops at a gate, `/ship` stops with it.
- For a plan-only pass, use `/plan`; for build-only, use `/build`. `/ship` is for the
  whole loop in one invocation.
