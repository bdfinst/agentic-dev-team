# Decision Log

Persistent log of significant decisions made during task execution. Survives session resets via the `memory/` directory. The Orchestrator and team agents append entries here when making non-obvious routing, architectural, or implementation choices.

---

## When to Log

Log a decision when:
- Routing a task to a non-default agent for a non-obvious reason
- Choosing between two valid architectural or implementation approaches
- Overriding a default pattern, convention, or routing table entry
- Resolving a conflict between agent recommendations
- Selecting a model tier that differs from the routing table default
- Making a scope decision that affects future phases

Do **not** log routine decisions (standard routing, normal code patterns, expected behavior).

---

## Entry Format

```
**ID**: DEC-YYYY-MM-DD-NNN
**Date**: YYYY-MM-DD
**Agent**: <agent-name>
**Task**: <brief description of the task context>
**Decision**: <what was decided>
**Rationale**: <why this option>
**Alternatives rejected**: <other options considered and why not chosen>
```

---

<!-- Decisions are appended below this line -->

**ID**: DEC-2026-04-20-001
**Date**: 2026-04-20
**Agent**: orchestrator (combined-plan authoring)
**Task**: Coordinate execution of `plans/opus-4-7-alignment.md` (P1) and `plans/security-review-companion-plugin.md` (P2), which modify overlapping files (`CLAUDE.md`, `agents/security-review.md`, `commands/code-review.md`, `knowledge/agent-registry.md`, `settings.json`)
**Decision**: 7-stage interleaved sequence documented in `plans/combined-plan-opus-4-7-security-review.md`. P1 Phase A (Steps 0, 4, 1a) ships immediately as quick wins. P2 adopts rev 7 with three conventions-in-flight ACs (AC-CIF-1 thinking directives, AC-CIF-2 CLAUDE.md architecture rule, AC-CIF-3 pre-classified negatives). P2 then executes its full Phase A–D timeline with conventions bound. P1 Phase C/D/E runs last (Stage 7) against the post-P2 codebase as verification rather than a sweep.
**Rationale**: Both plans modify the same five files. Running them independently produces sweep-after-sweep rework or merge conflicts. The three conventions-in-flight ACs cost P2 ~15 min per affected commit and save Stage 7 from being a multi-day retrofit across every new agent and CLAUDE.md section. Stage 1 quick wins (build.md scaffolding removal, token measurement script) are zero-conflict and deliver value today without blocking P2.
**Alternatives rejected**:
  (a) Ship P1 in full before P2 — rejected: P1 Phase C/D/E would be immediately stale once P2 adds ~9 new opus agents and expands CLAUDE.md with registry entries and adapter policies.
  (b) Delay P1 entirely until P2 ships — rejected: forgoes ≤1-hour Stage 1 quick wins that are independent of P2 scope.
  (c) No coordination, resolve at merge time — rejected: every P1-P2 overlap becomes a manual merge, and conventions would have to be retrofitted across many new files after the fact.
