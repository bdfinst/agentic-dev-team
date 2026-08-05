Delegate the entire analysis pass to **`/test-health`** — it is the **sole
worker** for Phase 1. Invoke it exactly once with the resolved repo path from
Phase 0. `/test-health` internally orchestrates whatever sub-skills it needs
(CD-alignment audit, test-design assessment, mutation-testing roll-up); the
orchestrator must **not** invoke `/cd-test-architecture`, `/test-design`, or
`/mutation-testing` separately here. Any prior workflow that reached those
skills directly is superseded by the single `/test-health` call.

**Mutation section respects the Phase-0 mutation mode.** When `phase-0.md`
recorded mutation mode **`off`**, the rolled-up report's mutation section is
either **omitted** or marked "not enabled for this run". When it recorded
**`kill-loop`** or **`baseline+kill-loop`**, the mutation section is **present**.
`/test-health` is not invoked with a mutation flag — the mode flows through from
`phase-0.md` and the section is handled at report time.

**Order the plan by the coverage-gap ranking whenever a coverage percentage
is a stated goal (issue #1786).** Read
`.dev-team-reports/test-improve/<slug>/data/coverage-gap-ranking.json` —
written by Phase 2 (see `phase-2-baseline.md`) — and order the
coverage-driven items of `/test-health`'s ordered
improvement plan by that ranking's `modules` array (`rank` 1 first), not by
mutation survivor count and not by an ordering re-derived here. `/test-health`'s
own ordering stands only for items the ranking does not speak to (flakiness,
determinism, suite shape), and for a run where **no coverage percentage is a
stated goal** (Phase-0 knob 4 overrode the coverage targets away) the ranking
is **informational** rather than the ordering authority.

**Under `--analyze-only` there is no ranking to read.** That mode runs Phase 0
then Phase 1 directly and captures no baseline, so Phase 2 never wrote
`coverage-gap-ranking.json`. Do not fabricate one and do not silently fall back
to survivor ordering: present `/test-health`'s own ordering and state plainly
that the coverage-gap ranking was not computed for this run (a full run would
order the coverage-driven items by it). The same holds for a `--from-phase 1`
resume whose `data/` directory has no ranking file — say so rather than
proceeding as if the ordering were coverage-derived.

**Mutation survivors order work *within* an already-seamed module, never
across modules.** A module whose ranking entry reads `seam: established`
already has baseline coverage, so survivor counts are the right next signal
*there* — that is the ordering the `mutation-kill` agent applies inside Phase
5. A module whose entry reads `seam: absent` needs coverage before it needs
assertion quality, and is ordered by uncovered lines alone. Under
`refactor-mode: no-refactor` a top-ranked `seam: absent` module whose tests
need a production seam is still shown in the presented plan — labeled
**skipped-in-no-refactor** per the human gate below — so the operator sees the
coverage left on the table instead of a plan that quietly reorders around it.

**Output.** Persist the rolled-up analysis plus the ordered improvement plan to
`.claude/memory/test-improve/<slug>/phase-1.md`.

**Test-count-by-type snapshot.** Independent of the `/test-health` call
above (and of whether `/test-health`'s own trivial-suite short-circuit
fired for this run), perform a direct classification pass over the test
files under the `<repo-path>` Phase 0 resolved: apply
`knowledge/cd-test-architecture.md`'s
six-type criteria (Static analysis / Unit / Component / Contract /
Integration / End-to-end) directly to each test suite/file found. **One
test file counts as exactly one suite**, regardless of how many describe
blocks or test classes it contains. Tie-break rule for a file that doesn't
cleanly fit one type: classify by its dominant/highest-dependency type
(e.g. a suite exercising a real DB connection classifies as integration
even if most of its assertions read like unit-level checks); if dominance
is still tied, classify by the higher-fidelity type using this fixed
precedence: `end_to_end` > `integration` > `contract` > `component` >
`unit` (this precedence applies to test files only — `static_analysis` is
never a legitimate outcome of classifying a test file; see its own
counting rule below). Persist
`.dev-team-reports/test-improve/<slug>/data/test-counts-before.json` — written
**directly** to the git-tracked `data/` sibling (this file has no other
consumer, so no separate `.claude/memory/` copy is needed) — with the six
canonical snake_case keys, in this fixed order: `static_analysis`, `unit`,
`component`, `contract`, `integration`, `end_to_end` — each key present
even at zero, counting **test suites/files, not individual test cases or
assertions**. `static_analysis` counts configured linter/scanner tool
invocations (one per tool — e.g. ESLint, Semgrep, mypy) rather than
test-directory files, since static analysis runs over non-running code and
is rarely organized as a describe-block suite; when the repo has no
configured static-analysis tooling at all, the key is `0`, not omitted.

**Existing-snapshot guard.** Before persisting, check whether
`test-counts-before.json` already exists under
`.dev-team-reports/test-improve/<slug>/data/` for the resolved slug. This
guard is Phase 1's application of the shared existing-tracked-artifact
re-capture guard — the canonical definition and rationale live once in
`knowledge/decision-defaults.md`'s "Re-capture: keep vs. overwrite an existing
tracked artifact" axis; this step cites that axis for the *why* and spells out
the operational branches below so an executing agent doesn't need to open a
second file mid-task. **No existing file** → write the fresh snapshot
directly; no prompt is needed. **An existing file that is malformed or
corrupt** (fails to parse as JSON — e.g. left over from a prior interrupted
write) → treat it as absent, never as a snapshot to keep; emit a warning
naming why a fresh capture is happening, then write the fresh snapshot
directly (no prompt — there is nothing valid to keep). **An existing, readable
file**, interactive session → prompt: *"An existing
test-counts-before.json was found for `<slug>` — overwrite it (starts a fresh
before/after comparison) or keep it (reuse for this run)? `[keep/overwrite,
default: keep]`"* Answering `overwrite` replaces the existing file with a
fresh snapshot. Answering `keep` (or declining) leaves the existing file
untouched and Phase 1 reuses it for this run. An **unrecognized answer**
(anything other than `keep` or `overwrite`) re-prompts with the identical
text — it never silently falls back to the default. When the run is
**non-interactive** (no usable TTY / `DEV_TEAM_AUTO_APPROVE=1`), the prompt is
never shown; Phase 1 defaults to **keep existing** and logs the
auto-decision, mirroring `decision-defaults.md`'s non-interactive rule — never
a non-default stance (overwrite) with nobody present to confirm it. The
malformed-file branch above is the one exception to that keep-by-default
posture — an unreadable file is treated as absent in every mode, since there
is nothing valid to keep.

This pass does **not** invoke `/test-health` or `/cd-test-architecture`'s
full skill.

**Human gate.** After `/test-health` returns, present **the ordered improvement
plan** to the operator and wait for explicit approval. **Phase 4 does not run**
until the operator approves. This is the human gate for Phase 1; do not advance
past it without approval. When `phase-0.md` recorded
`refactor-mode: no-refactor`, any plan item that would require a production-code
refactor is labeled **skipped-in-no-refactor** (out of scope for this run) so
the operator sees the coverage/behavior left on the table — such items are never
presented as ordinary next steps that this run will execute.

**`/handoff` suggestion** (context-heavy analysis). Once the gate above resolves, print: `Phase 1 complete. Consider running /handoff to compress context before continuing. To resume: /test-improve <repo-path> --from-phase 4 (or --from-phase with no number to auto-detect the resume point)`
