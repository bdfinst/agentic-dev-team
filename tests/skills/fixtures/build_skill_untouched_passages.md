<!-- Verbatim pin of three passages of plugins/dev-team/skills/build/SKILL.md
     as they were before Step 4.2 (#2273) added the speculative-dispatch paragraph.
     tests/skills/test_build_candidates_flag.py asserts each fenced passage is still
     a substring of the skill. Do not edit by hand. To refresh after a deliberate
     change to one of these passages, copy the new text of that passage, byte for
     byte, between its fences. -->

## trivial bullet

~~~~
   - **trivial**: Skip inline review. The final `/code-review` (step 6) covers all modified files.
~~~~

## standard bullet

~~~~
   - **standard**: **Defer** review to the slice boundary (sub-step 6) — do not review now. Track the step's changed files so the slice checkpoint reviews them in one batch. Per-step review on standard steps is N near-identical passes where one at slice end largely does the same work, and the final `/code-review` (step 6) remains the backstop. This is the batching win — fewer review dispatches per multi-step slice at bounded quality risk.
~~~~

## dispatch paragraph

~~~~
For each step within a slice, dispatch the `software-engineer` agent (by `subagent_type`) scoped to a single unit of work. Pass it its step **and the slice's Gherkin scenario(s)** — the scenarios are the behavioral contract the step's test must satisfy — plus an explicit constraint: **the design is settled; do not design.** The agent implements the step exactly as planned, one behavior at a time, per the per-behavior cycle below — it does not revisit or re-derive design decisions the plan already made. **Require its step report to state assumptions explicitly**: when the plan under-specifies a detail that doesn't rise to an escalation (exact error-message wording, an unspecified boundary condition, a choice between two equally plan-consistent shapes), the agent records the decision and its basis in the report rather than resolving it silently — `/pr`'s "Decisions & assumptions" section (`skills/pr/SKILL.md`) collects these from each step's report.
~~~~
