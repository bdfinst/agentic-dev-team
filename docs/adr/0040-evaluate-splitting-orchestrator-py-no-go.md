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
  evaluate splitting the file into a dispatch_primitives module and a
  phase_functions module before or during Slice 4, rather than letting the
  file grow past that point unexamined.
- Slice 4 (PR #1724, Implement phase) walked that commitment back again with
  weaker language and preserved the split proposal and deferral history in
  issue #1723, since `plans/*.md` files are transient and the decision's
  context was at real risk of being lost permanently.

By the time #1723 was evaluated, the file had reached **820 lines** — past
the watch line by roughly 2x, having deferred the split question three times
with no new information changing the calculus each time.

Issue #1723 proposed a lightweight go/no-go, with candidate module
boundaries already specified: a `dispatch_primitives` module
(`dispatch_persona`, `dispatch_personas`, `_parse_dispatch_envelope`,
`_failed_result`, `reconcile`, `WaveError`, timeout constants,
`JSON_CONTRACT_PERSONAS`) and a `phase_functions` module
(`_default_phase_research`, `_default_phase_plan`, `_default_phase_implement`,
`_run_phase`, `_resolve_default`, `_warn_on_failed_personas`,
`_print_wave_failure`, the persona-roster constants), with `run_pipeline`,
`classify`, the CLI entry point, and the phase-state helpers staying in
`orchestrator.py` as the composition root.

**What the evaluation found.** `tests/scripts/test_orchestrator.py` contains
**58 call sites** using `patch.object(orch, "dispatch_persona", ...)` or
`patch.object(orch, "dispatch_personas", ...)` to intercept the dispatch
calls made from inside the phase functions that the proposal moves to
`phase_functions.py` — verified with a multiline-aware search; a naive
single-line grep undercounts to 45, missing 13 sites where the
`patch.object(` opener and its `orch, "dispatch_persona(s)"` arguments are
split across lines (e.g. `test_orchestrator.py` lines 938-939, 1786-1789).
If those phase functions import `dispatch_persona`/`dispatch_personas` as
bare names from a new `dispatch_primitives.py` module, patching
`orch.dispatch_persona` — even with `orchestrator.py` re-exporting the name
for backward compatibility — no longer intercepts the call: Python binds the
imported name into `phase_functions.py`'s own module namespace at import
time, and patching a different module's attribute of the same name does not
affect that binding.

This is not a novel or unusual pattern; it's the standard "patch where a
name is *used*, not where it's *defined*" hazard, applied to two functions
against 58 existing call sites in a single file. The practical severity of a
missed site is narrower than it might first appear, though, and is stated
precisely rather than worst-cased: `dispatch_persona` returns a stub result
immediately when `skip_llm=True` (`orchestrator.py:546-547`), before any
subprocess call — 72 of the 58+ call sites in the test file pass
`skip_llm=True`. For the remaining `skip_llm=False` sites, the real
subprocess call is bounded by `PERSONA_DISPATCH_TIMEOUT_S` (60s), and
`FileNotFoundError`/`TimeoutExpired`/`OSError` are caught and converted to
`_failed_result(persona, error="llm_unavailable")` rather than propagating —
so a missed patch site cannot hang the suite indefinitely, and on a machine
without the `claude` binary it makes no external call at all. Most sites
also patch specifically to *capture* the call and assert on what was
captured; bypassing the patch there surfaces as a loud assertion failure on
an empty/wrong capture, not silence. The residual, real risk is narrower
than "silent hang": a `skip_llm=False` site whose assertions don't depend on
call capture could pass while quietly making a bounded (<=60s) real
dispatch call on a machine that has the `claude` CLI installed — real, but
neither silent nor unbounded, and precisely fixable by retargeting every
site to patch the new module directly (or routing calls through qualified
module access rather than a bare imported name), not a mechanical rename
with no behavioral surface.

## Decision

**No-go, for now.** The 820-line size and the file's history of deferred
splits are real signals of God-object growth, but they do not by themselves
outweigh the concrete, verified risk in the 58-site test-patch coupling: a
split done today either (a) requires touching and correctly re-verifying 58
patch targets against a mocking pitfall with a real, non-silent-but-still
easy-to-miss failure mode, or (b) is scoped down to avoid moving
`dispatch_persona`/`dispatch_personas` at all — which defeats the module
boundary the proposal itself specifies, since those two functions are
exactly what makes `dispatch_primitives.py` a coherent module.

`orchestrator.py` stays a single file. No module split lands as part of
this decision.

**Revisit trigger.** Reopen this evaluation if either candidate module
accumulates independent growth that would benefit from isolated testing —
e.g., new dispatch-primitive functions with their own test suite, or new
phase functions that don't touch `dispatch_persona`/`dispatch_personas`
directly. A future split attempt should retarget the 58 (or by-then-more)
`patch.object(orch, "dispatch_persona"/"dispatch_personas", ...)` sites as
an explicit, verified step of that change — counted with a multiline-aware
search, not a single-line grep, which is exactly the blind spot this
evaluation found — and should consider one of two mitigations:

1. Route calls through a qualified module reference
   (`dispatch_primitives.dispatch_persona(...)`) rather than a bare imported
   name, so test doubles can patch the primitives module directly instead of
   depending on re-export forwarding.
2. Extend `orchestrator.py`'s own existing dependency-injection pattern —
   `run_pipeline` already takes `classify_fn`/`phase_research_fn`/
   `phase_plan_fn`/`phase_implement_fn`, resolved at call time via
   `_resolve_default` (`orchestrator.py:637`, under the "Resolve
   inject-able dependencies" comment at line 685) — to the dispatch
   primitives, e.g. a `dispatch_fn=None` parameter on each phase function
   resolved the same way. This would make a split test-transparent by
   construction rather than by patch-target bookkeeping, and is consistent
   with a pattern this module already uses for the same class of problem.

## Consequences

**What gets better.** No mechanical refactor risk is taken on right now; the
existing 58 test-patch sites, and the passing test suite they protect,
are untouched. The deferred-three-times decision finally has a durable,
findable record instead of evaporating with another transient plan file.

**What gets worse.** `orchestrator.py` remains an 820-line file, past this
project's own 400-line watch line by a wide margin, and will keep growing as
future phases or dispatch behavior are added to it. Every future plan that
touches this file will re-trigger `plan-review-design`'s "God object growing
beyond 400 lines with mixed responsibilities" blocker
(`plugins/dev-team/agents/plan-review-design.md:83`) — that rubric governs
plans that add logic to the file, a distinct concern from this ADR's split
decision, so the two do not contradict each other, but a future plan should
cite this ADR (rather than re-litigating the split question from zero) up to
the point this ADR's own revisit trigger fires.

**What this does not change.** The candidate module boundaries proposed in
issue #1723 remain valid as a design if a future split is attempted — this
decision does not invalidate them, it defers acting on them until the
test-patch coupling risk above is specifically addressed.

## Notes

Issue #1723, part of epic #1648 / spec #1707. Evaluated as a go/no-go per
the issue's own framing ("a lightweight go/no-go, not a mandate to split").
