# 13. LLM-driven orchestration over deterministic workflow scripts

Date: 2026-06-29

## Status

Accepted

## Context

The `/ship` skill chains `/specs`, `/plan`, `/build`, `/code-review`, and `/pr` into a
single end-to-end pipeline. Within that pipeline, two phases require fan-out:

- `/build` dispatches independent plan slices to isolated git worktrees concurrently.
- `/code-review` fans out to parallel review agents, each scoped to a file-type domain.

Both dispatch decisions are currently made by the LLM at runtime: it reads the skill
instructions, interprets the plan's wave schedule, and decides whether to call the
`Agent` tool. Nothing in the harness mechanically forces a sub-agent call to happen.

An alternative is a deterministic Workflow script — a JavaScript harness supported by
Claude Code that uses explicit `parallel()`, `pipeline()`, and `phase()` primitives to
fan out `agent()` calls. The orchestration structure would be guaranteed regardless of
what the LLM decides.

The trade-off was raised as a reliability concern: if the LLM drives orchestration, it
can decide not to spawn a sub-agent, making the isolation and parallelism promises
unreliable.

## Decision

Retain LLM-driven orchestration for `/build` and `/code-review`. Do not replace skill
instructions with Workflow scripts.

The primary reason is that the adaptation value of LLM orchestration exceeds the
reliability cost in this context.

`/build` in particular relies on the model reading plan content and making judgment
calls that are not derivable from structure alone: two structurally independent slices
that both touch a shared module may need to be serialized; a wave that looks concurrent
on paper may need to collapse to sequential after an unexpected merge conflict; a review
finding may require re-planning a step rather than fixing it. A deterministic script
executes the wave schedule as computed and has no mechanism for these mid-stream
judgments.

`/code-review` is a closer call — the fan-out is pure and no adaptation is needed —
but the arguments below apply there too.

The specific costs of moving to Workflow scripts outweigh the reliability gain:

1. **Human gates become awkward.** The pipeline has required human approval gates
   between phases (spec review, plan approval, pre-PR confirmation). The Workflow tool
   runs headlessly. Preserving those gates requires splitting the Workflow at each gate
   boundary and having the user re-invoke between splits, which removes the single-
   command property that `/ship` exists to provide.

2. **Orchestration logic becomes code.** Skills are markdown files that can be updated,
   tested, and reviewed as configuration. A Workflow script is JavaScript that requires
   code changes, CI, and releases for every orchestration adjustment. The maintenance
   burden grows with every new agent, gate, or routing rule.

3. **Context serialization is awkward.** Skills pass rich, dynamic context to sub-
   agents: institutional context from `REVIEW-CONTEXT.md`, static analysis findings
   from the pre-pass, results from prior iterations. In a Workflow script, all of this
   must be serialized into prompt strings upfront — dynamic or large context is
   structurally difficult.

4. **Leaf agents are still LLMs.** A Workflow script makes the fan-out deterministic
   but not the work. Whether a slice is correctly implemented or a review agent catches
   a real defect remains a model judgment. The reliability boundary moves down one
   level without eliminating the underlying non-determinism.

5. **Error handling must be exhaustive.** LLM orchestrators improvise on unexpected
   failures. Workflow scripts must enumerate every non-happy-path case explicitly or
   silently degrade to `null` results.

## Consequences

**Harder:** The guarantee that parallel sub-agents will always be spawned cannot be
mechanically enforced. Observability of whether the model followed the dispatch
instructions requires reading transcripts, not checking harness state.

**Mitigated by:** The `allowed-tools` frontmatter limits which tools a skill may use.
The pre-computed wave schedule (`build-wave.sh`, `build-jobs.sh`) produces a structured
artifact the model reads directly, reducing the surface for misinterpretation. The
worktree isolation guarantee (`isolation: "worktree"`) is enforced by the harness once
the Agent tool is called — only the decision to call it is LLM-driven.

**Future option:** If defection rate proves material (measurable via transcript
analysis), a PostToolUse hook can assert that concurrent waves resulted in Agent tool
calls and log a warning when they did not — adding observability without replacing the
architecture.

**Easier:** Adding new agents, changing routing rules, and adjusting human gates
requires editing markdown skill files rather than releasing JavaScript. The pipeline
can adapt to mid-run judgment calls that structural computation cannot anticipate.
