# 20. Fold the ACI mutation pipeline into the plugin as scripted mechanics

Date: 2026-07-16

## Status

Accepted

## Context

The ACI `nextgen-test-upgrade-process` repo (Azure DevOps) carried a standalone
Stryker mutation pipeline — `stryker-setup.py` → `stryker-pipeline.py` →
`mutation-agent.py`, plus `_common.py` and `stryker-retry-timeouts.py`. Its
survivor→generate→verify→commit loop duplicated the plugin's `dev-team:mutation-kill`
agent and `/mutation-testing` skill. The scripts lived outside the plugin only because
`mutation-agent.py` was hardcoded to one ACI project (`Aci.Speedpay.Internet.WebAPI`);
on inspection that coupling was incidental — every hardcoded fact was already available
from `stryker-config.json` or the existing test suite (#1136).

Two questions had to be answered together:

1. **Where should the sharded/CI pipeline live** — folded into the plugin, or kept as a
   thin ACI wrapper over a now-generic `mutation-kill`?
2. **How much of the loop should be a script vs. an agent prompt** — given
   [ADR 0013](0013-llm-driven-orchestration-over-deterministic-workflow-scripts.md)
   retained LLM-driven orchestration for `/build` and `/code-review` rather than
   replacing skill instructions with deterministic Workflow scripts.

## Decision

**Fold the pipeline into the plugin** as generic, stdlib-only Python under
`plugins/dev-team/skills/mutation-testing/scripts/`. The plugin becomes the single
source of truth; the ACI repo keeps only a `stryker-config.json` and a thin invocation
(tracked for follow-through in #1139). The migration also fixes, rather than ports, the
ACI copy's timeout-inflated score: scoring now uses the honest formula
`Killed / (Killed + Survived + NoCoverage)` with Timeout excluded from the numerator.

**The governing principle is: anything with a deterministic outcome becomes a Python
script; the `mutation-kill` agent prompt retains only the genuinely-LLM steps** —
generating targeted tests, and the infrastructure/structural exclusion judgment.
Generation is agent-driven by default, with an opt-in `--headless` mode that shells to
`claude --print` for unattended CI; the shard pipeline forces `--headless` because a
script-spawned round has no agent turn available.

### Why this does not contradict ADR 0013

ADR 0013 protects one specific thing: the **fan-out dispatch decision** in `/build` and
`/code-review` — *whether and how to spawn sub-agents* — because that decision needs
runtime adaptation the model supplies (serialize two nominally-independent slices that
share a module, collapse a concurrent wave after an unexpected conflict, re-plan a step
instead of fixing it). A deterministic script cannot make those judgments.

This migration scripts a different category: the **mechanics** of a mutation round —
parsing a report, computing a score, detecting duplicate test methods, inserting before
a class-close brace, invoking build/test, committing, reverting on failure — plus the
**control flow** that sequences them (run → score → check-survivors → generate → insert
→ verify → commit → loop-or-stop). This control flow, unlike `/build`'s wave schedule,
carries **no adaptation value worth preserving**: its branches are fully determined by
observable facts (survivor count, build result, test result, no-improvement), not by
judgment about intent. Every decision point is a comparison a script makes correctly and
repeatably; there is no equivalent of "these two slices look independent but I should
serialize them." The one step that *does* require judgment — writing tests that kill a
given survivor, and deciding a file is structurally unkillable — stays with the agent.

So ADR 0013 and this decision draw the same line from opposite sides: keep the
adaptive, judgment-bearing work in the LLM; make the mechanical, deterministically-branching
work a tested script. Scripting a loop whose control flow has no adaptation value is not
the move ADR 0013 declined.

## Consequences

**Easier:** One maintained pipeline instead of two. The honest-score doctrine is enforced
in code, not prose. The mechanics get real pytest coverage (previously only prose in the
agent). Any .NET repo can run the pipeline with only a `stryker-config.json`.

**Harder / watch:** The `mutation-kill` agent is a live, shipped component used by every
plugin consumer; repointing it at new scripts concentrates behavior-change risk (mitigated
by the full green gate and human merge — no auto-merge). The `insert-before-class-close`
heuristic is stylistically coupled to block-namespace, 4-space-indent C#; it must
detect-or-refuse (never silently mis-insert) and broader C# styles remain a documented
limitation.

**Deferred:** The ACI repo keeps its forked scripts until the downstream thinning (#1139)
lands — until then duplication is resolved on the plugin side only.
