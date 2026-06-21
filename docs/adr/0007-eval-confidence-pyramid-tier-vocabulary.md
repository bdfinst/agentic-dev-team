# 7. Eval confidence-pyramid tier vocabulary

Date: 2026-06-19

## Status

Accepted

## Context

The eval system grew up around one shape of test: dispatch a single review
agent (or advisory skill) at a fixture and grade its recorded output against an
expected JSON. That is a real and useful test, but it is only one rung of a
ladder, and we never named the ladder. As we added the integration tier
(#313) — which dispatches the *orchestrator*, builds code in a worktree, and
grades on whether the project's tests pass — the absence of a shared vocabulary
became a hazard:

- Fixtures of fundamentally different kinds (single-agent verdict vs.
  whole-pipeline build) were grading through the same monolithic code path, so
  adding a kind meant adding a branch (addressed structurally by the grader
  registry, #309).
- Discussions about "what the evals cover" had no precise terms. "Does the eval
  pass?" means something very different for a reviewer-detection fixture than
  for a build-it-and-run-the-tests fixture, and conflating them invites false
  confidence.
- The competitive analysis against claude-flow framed its corpus explicitly in
  confidence-pyramid terms (unit → integration → acceptance). We wanted the
  same precision without copying its implementation.

A claim needs an instrument (CLAUDE.md claims discipline). Different tiers
answer different questions and warrant different confidence; naming them keeps
us honest about which question a given green run actually answers.

## Decision

Adopt a three-tier confidence-pyramid vocabulary for the eval corpus, mapped to
concrete graders in the registry (#309):

1. **Unit** — verification of a single component's output in isolation. "Did the
   reviewer flag the right thing?" Graders: `verdict` (review-agent output) and
   `skill_gate` (advisory-skill gates/layers). Cheap, deterministic given a
   recorded actual; this is the bulk of the corpus and the default PR gate.

2. **Integration** — validation that the orchestrator's plan yields working
   code. "Does a plan from our orchestrator produce code that compiles and whose
   tests pass?" Grader: `integration` (#313), scoring recorded test-command exit
   codes from an ephemeral golden-repo worktree. Opt-in (`run-integration`),
   never in the default suite, and economical only with the replay cache (#311).

3. **Acceptance / choreography** — *deferred, named here for completeness.*
   Validation of multi-agent phase transitions and hand-offs (the orchestration
   choreography itself). It needs phase-transition instrumentation and a
   fake-worker harness that do not exist yet. Reserving the name now prevents
   the integration tier from being stretched to cover it by accident.

The vocabulary is the contract; the registry is the mechanism. A new tier or
genre is a registered grader, not a new branch in the grader.

## Consequences

**Easier:**

- Conversations and docs can say "unit tier" / "integration tier" and mean
  something precise. `evals/README.md` is organised around these terms.
- Adding a fixture genre is one grader module + one registry entry. The tier it
  belongs to is explicit in which grader it uses.
- The deferred acceptance tier has a reserved name, so scope creep into the
  integration tier is visible and resistable.

**Harder / trade-offs:**

- Three tiers is a deliberate ceiling for now. The acceptance tier is named but
  unbuilt; until it ships, "the evals pass" still leaves choreography unverified
  and prose must not over-claim coverage.
- Tier names must stay stable — they leak into fixture structure
  (`integration` block, `grader` field), CI labels (`run-integration`), and
  docs. Renaming later is a breaking change to the corpus contract.

## References

- Issue #314 (umbrella), #309 (grader registry), #311 (fingerprint cache),
  #313 (integration tier).
- `evals/README.md` — tier-by-tier description and commands.
