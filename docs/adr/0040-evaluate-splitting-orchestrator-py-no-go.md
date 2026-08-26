# 40. Evaluate splitting orchestrator.py: no-go

Date: 2026-08-26

## Status

Accepted

## Context

`plugins/dev-team/scripts/orchestrator.py` grew across three consecutive
slices of the "Wire orchestrator.py to Real Agent Dispatch" effort (epic
#1648, spec #1707):

- Slice 2 (PR #1718, Research phase) flagged the file was already past this
  project's rubric's 400-line god-object watch line (533 lines pre-Slice-3).
- Slice 3 (PR #1721, Plan phase) explicitly deferred a concrete commitment —
  evaluate splitting the file into a dispatch-primitives module and a
  phase-functions module before or during Slice 4, rather than letting the
  file grow past that point unexamined.
- Slice 4 (PR #1724, Implement phase) walked that commitment back again with
  weaker language and preserved the split proposal and deferral history in
  issue #1723, since `plans/*.md` files are transient and the decision's
  context was at real risk of being lost permanently.

By the time #1723 was evaluated, the file had reached **820 lines** — past
the watch line by roughly 2x, having deferred the split question three times
with no new information changing the calculus each time.

Issue #1723 proposed a lightweight go/no-go, with candidate module
boundaries already specified: a `dispatch-primitives` module
(`dispatch_persona`, `dispatch_personas`, `_parse_dispatch_envelope`,
`_failed_result`, `reconcile`, `WaveError`, timeout constants,
`JSON_CONTRACT_PERSONAS`) and a `phase-functions` module
(`_default_phase_research`, `_default_phase_plan`, `_default_phase_implement`,
`_run_phase`, `_resolve_default`, `_warn_on_failed_personas`,
`_print_wave_failure`, the persona-roster constants), with `run_pipeline`,
`classify`, the CLI entry point, and the phase-state helpers staying in
`orchestrator.py` as the composition root.

**What the evaluation found.** `tests/scripts/test_orchestrator.py` contains
**46 call sites** using `patch.object(orch, "dispatch_persona", ...)` or
`patch.object(orch, "dispatch_personas", ...)` to intercept the dispatch
calls made from inside the phase functions that the proposal moves to
`phase-functions.py`. If those phase functions import `dispatch_persona`/
`dispatch_personas` as bare names from a new `dispatch-primitives.py`
module, patching `orch.dispatch_persona` — even with `orchestrator.py`
re-exporting the name for backward compatibility — no longer intercepts the
call: Python binds the imported name into `phase-functions.py`'s own module
namespace at import time, and patching a different module's attribute of
the same name does not affect that binding. Every one of the 46 sites would
silently start exercising the *real* dispatch function instead of the test
double, which performs real subprocess/Claude CLI dispatch — a failure mode
that would not read as a test failure so much as a hang, an external call
during CI, or a flaky timeout, depending on environment.

This is not a novel or unusual pattern; it's the standard "patch where a
name is *used*, not where it's *defined*" hazard, applied to two functions
against 46 existing call sites in a single file. It is precisely fixable —
retarget every site to patch the new module directly, or route calls through
qualified module access rather than a bare imported name — but it is real,
precise work with a real, silent-failure-mode risk of getting a subset of
the 46 sites wrong, not a mechanical rename with no behavioral surface.

## Decision

**No-go, for now.** The 820-line size and the file's history of deferred
splits are real signals of God-object growth, but they do not by themselves
outweigh the concrete, verified risk in the 46-site test-patch coupling: a
split done today either (a) requires touching and correctly re-verifying 46
patch targets against a mocking pitfall with a silent, hard-to-notice
failure mode, or (b) is scoped down to avoid moving `dispatch_persona`/
`dispatch_personas` at all — which defeats the module boundary the proposal
itself specifies, since those two functions are exactly what makes
`dispatch-primitives.py` a coherent module.

`orchestrator.py` stays a single file. No module split lands as part of
this decision.

**Revisit trigger.** Reopen this evaluation if either candidate module
accumulates independent growth that would benefit from isolated testing —
e.g., new dispatch-primitive functions with their own test suite, or new
phase functions that don't touch `dispatch_persona`/`dispatch_personas`
directly. A future split attempt should retarget the 46 (or by-then-more)
`patch.object(orch, "dispatch_persona"/"dispatch_personas", ...)` sites as
an explicit, verified step of that change — not an afterthought — and should
consider whether the phase functions should call dispatch primitives via a
qualified module reference (`dispatch_primitives.dispatch_persona(...)`)
specifically so that test doubles can patch the primitives module directly
rather than depending on re-export forwarding.

## Consequences

**What gets better.** No mechanical refactor risk is taken on right now; the
existing 46 test-patch sites, and the passing test suite they protect,
are untouched. The deferred-three-times decision finally has a durable,
findable record instead of evaporating with another transient plan file.

**What gets worse.** `orchestrator.py` remains an 820-line file, past this
project's own 400-line watch line by a wide margin, and will keep growing as
future phases or dispatch behavior are added to it.

**What this does not change.** The candidate module boundaries proposed in
issue #1723 remain valid as a design if a future split is attempted — this
decision does not invalidate them, it defers acting on them until the
test-patch coupling risk above is specifically addressed.

## Notes

Issue #1723, part of epic #1648 / spec #1707. Evaluated as a go/no-go per
the issue's own framing ("a lightweight go/no-go, not a mandate to split").
