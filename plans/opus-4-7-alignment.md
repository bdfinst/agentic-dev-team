# Plan: Align Agentic-Dev-Team Plugin with Opus 4.7 Guidance

**Created**: 2026-04-20
**Revised**: 2026-04-20 (rev 2 — addresses all 8 blockers from Strategic, Acceptance, and Design critics; incorporates Anthropic's official best-practices post)
**Branch**: main
**Status**: approved — split execution (2026-04-20)
**Execution coordinator**: [`plans/combined-plan-opus-4-7-security-review.md`](./combined-plan-opus-4-7-security-review.md)

## Split execution notice

This plan is approved but executed across two windows per the combined plan:

- **Stage 1 (today)**: Step 0 (done), Step 4, Step 1a (measurement script only — defer CLAUDE.md baseline numbers)
- **Stage 7 (after `plans/security-review-companion-plugin.md` lands)**: Step 1b (baseline numbers), Step 3, Step 2, Step 6, Step 7, Step 5, Step 8

The conventions-in-flight ACs (AC-CIF-1, AC-CIF-2, AC-CIF-3) in the security-review plan rev 7 ensure Stage 7 is verification, not sweep. See the combined plan for gate criteria between stages.

## Goal

Apply the adjustments from Anthropic's official "Best Practices for Claude Opus 4.7 with Claude Code" post (primary source) and the ProductCompass migration guide (supporting) to the agentic-dev-team plugin. Outcome: a plugin that takes advantage of Opus 4.7's literal-instruction character, selective subagent delegation, adaptive thinking, and session-level effort configuration — while preserving its TDD hard gates and plan-review discipline.

## Primary sources

- **Anthropic official**: `https://claude.com/blog/best-practices-for-using-claude-opus-4-7-with-claude-code`
- **ProductCompass supporting**: `https://www.productcompass.pm/p/claude-opus-4-7-guide`
- **Spike doc (Step 0 output)**: `docs/spikes/effort-parameter-support.md`

## Acceptance Criteria

All criteria below are grep/script-verifiable. Line numbers intentionally avoided — targets are section headings.

- [ ] **AC-1 (Spike)**: `docs/spikes/effort-parameter-support.md` exists and records a definitive yes/no on native `effort:` support with evidence. (Met by Step 0.)
- [ ] **AC-2 (Effort column — documentation)**: The section titled "Model Routing Table" in `agents/orchestrator.md` contains a column header "Effort". Every data row has an Effort value from the set `{high, xhigh, max}`. Default assignments: `haiku` rows → `high`; `sonnet` rows → `high`; `opus` rows and `architect` → `xhigh`. A footnote immediately below the table contains the string "advisory" AND either "prompt-level" OR "prose" (so readers know effort is conveyed as prose per the Step 0 spike). `scripts/check-routing-table.sh` exits 0.
- [ ] **AC-3 (Mid-task effort toggle)**: `agents/orchestrator.md` contains a subsection titled `### Mid-task Effort Toggling` of 4–10 lines. The subsection contains the words `escalate` AND `revert` AND `max`. `grep -A 10 "Mid-task Effort Toggling" agents/orchestrator.md | grep -E "(escalate.*revert|revert.*escalate)" | grep -c "max"` returns a count ≥ 1.
- [ ] **AC-4 (Token budgets re-baselined)**: The section "Baseline Budget" in `CLAUDE.md` contains measured values with ≤ 10% deviation from the output of `scripts/measure-tokens.sh HEAD`. A footnote of the form `*Measured YYYY-MM-DD with <package>@<version>.*` appears immediately below the table, naming the exact tokenizer package + version used. `scripts/measure-tokens.sh --verify` exits 0.
- [ ] **AC-5 (CLAUDE.md token budget met)**: `scripts/measure-tokens.sh CLAUDE.md` reports ≤ 1,100 tokens (the stated architectural invariant of ~800 + 35% tokenizer upper bound). The following section headings remain in CLAUDE.md: `## Architecture`, `## Output Guardrails`, `## Core Principles`, `## Three-Phase Workflow` (or `### Three-Phase Workflow`), `## Model Routing` (summary table only), `## Context Management`. Sections relocated have a one-line pointer in CLAUDE.md pointing to the new home. `scripts/check-links.sh CLAUDE.md` exits 0.
- [ ] **AC-6 (Build scaffolding removed, gates preserved)**: `grep -c "Steps completed" commands/build.md` returns 0. `grep -c "Paste the failing output" commands/build.md` returns ≥ 1. `grep -c "Paste the passing output" commands/build.md` returns ≥ 1. `grep -c "verification evidence" commands/build.md` returns ≥ 1. (Exact phrasing matches current build.md; Stage 1 verification confirmed all four counts.)
- [ ] **AC-7 (Negative-rule sweep with 3-bucket classification)**: `scripts/check-negative-rules.sh` exits 0 when run against the fixed file list `{agents/orchestrator.md, commands/build.md, commands/plan.md, commands/code-review.md, CLAUDE.md}`. Every classified line falls into exactly one of: `SAFETY-GATE` (retained negative, carries an inline comment beginning `<!-- SAFETY-GATE:`), `NATIVE` (deleted, 4.7 handles natively), `PROCESS` (converted to a block containing the literal strings `Example 1:` and `Example 2:`). Pre-GREEN baseline count of unresolved negatives is recorded in the check output; post-GREEN count is 0.
- [ ] **AC-8 (Subagent restraint rule)**: `CLAUDE.md` contains the exact sentence `Do not spawn a subagent for work you can complete directly in a single response.` within the `### Multi-Agent Coordination` subsection of `## Multi-Agent Collaboration Protocol` (verified by `grep -F`). The sentence appears above the existing numbered coordination list so it reads as a prerequisite, not an afterthought. (Verified anchor: the section exists in CLAUDE.md at H3; no such section exists in orchestrator.md — prior draft targeted a fabricated anchor.)
- [ ] **AC-9 (Thinking-intensity directives)**: Every agent file in `agents/` whose frontmatter declares `model: opus` OR `name: architect` contains the exact sentence `Think carefully and step-by-step; this problem is harder than it looks.` in its instructions. Every agent file whose frontmatter declares `model: haiku` contains the exact sentence `Prioritize responding quickly rather than thinking deeply.` Verified by `scripts/check-thinking-directives.sh`, exit 0.
- [ ] **AC-10 (Task-complete notify hook)**: `plugins/agentic-dev-team/hooks/task-complete-notify.sh` exists, is executable (`test -x`), and plays a short system sound on macOS (via `afplay /System/Library/Sounds/Glass.aiff` or equivalent) with a no-op fallback on non-macOS. It is registered in `plugins/agentic-dev-team/settings.json` under a `Stop` hook entry. `bash plugins/agentic-dev-team/hooks/task-complete-notify.sh` exits 0 on both macOS and Linux.
- [ ] **AC-11 (`/agent-audit` passes)**: `/agent-audit` run against the git diff of this branch exits 0 with no structural violations reported in any file touched by this plan.
- [ ] **AC-12 (No `/agent-eval` regression)**: Pre-branch `/agent-eval` baseline is captured in `evals/baseline-<commit-sha>.json` before Step 1 GREEN. Post-branch `/agent-eval` output shows every fixture at or above the baseline accuracy. No fixture drops below its pre-branch score.

## User-Facing Behavior

No spec artifacts — internal plugin tuning. User-observable side-effects:

- Effort tier visible as documentation in the routing table when developers read the orchestrator spec.
- CLAUDE.md fits on fewer screens when browsing the repo.
- `/build` output no longer carries a canned summary template; model produces concise completion reports natively.
- Long-running `/build` and `/code-review` tasks play a system sound on completion (opt-out by disabling the hook in settings).

## Out of Scope

This plan will NOT touch:

- Review-agent detection logic or eval fixtures
- Existing safety hooks (`pre-tool-guard.sh`, `destructive-guard.sh`, `eval-compliance-check`)
- Model-tier assignments (haiku/sonnet/opus — those remain as-is)
- The three-phase workflow structure (Research → Plan → Implement)
- Any agent's technical responsibilities, personality, or success metrics
- The `/triage`, `/pr`, `/setup`, `/continue`, `/browse` command specs (not in the sweep file list)
- Beads-workflow companion plugin or security-review companion plugin (separate roadmap items)

## Phase Sequencing

The 9 steps are **not** fully independent. CLAUDE.md is modified by Steps 1, 2, 3, 5, 6. To avoid merge conflicts and anchor drift, steps MUST run in this order:

| Order | Step | Phase | Can parallelize? |
|---|---|---|---|
| 1 | Step 0 (Spike) | A — today | — (already done) |
| 2 | Step 4 (Build scaffolding) | A — today | Parallel with Step 1 |
| 3 | Step 1 (Token baseline) | A — today | Parallel with Step 4 |
| 4 | Step 3 (Slim CLAUDE.md) | C — sequenced | No — blocks Steps 2, 6 |
| 5 | Step 2 (Effort column) | C — sequenced | No — operates on slimmed CLAUDE.md |
| 6 | Step 6 (Subagent restraint) | C — sequenced | No — touches orchestrator.md |
| 7 | Step 7 (Thinking directives) | D — broad | No — touches every agent file |
| 8 | Step 5 (Negative-rule sweep) | D — broad | No — touches all 5 files |
| 9 | Step 8 (Task-complete hook) | E — additive | Parallel with Step 7 |

Each step leaves the tree committable. Commit after each step.

## Steps

### Step 0: Spike — verify `effort:` parameter support

**Status**: ✅ complete (run during plan revision).
**Complexity**: `trivial`
**RED**: `docs/spikes/effort-parameter-support.md` does not exist.
**GREEN**: `docs/spikes/effort-parameter-support.md` exists and contains a definitive answer with evidence. Conclusion (already determined): `effort:` is NOT a native Agent-tool parameter; it must be conveyed as prose. All downstream steps assume the advisory-only branch.
**REFACTOR**: None.
**Files**: `docs/spikes/effort-parameter-support.md` (created).
**Commit**: `docs: spike effort parameter support for Opus 4.7 planning`

### Step 4: Remove non-gate progress scaffolding from build.md

**Complexity**: `trivial`
**RED**: `grep -c "Steps completed" plugins/agentic-dev-team/commands/build.md` returns 1 (or more). Assert failing state.
**GREEN**: Replace the step-7 "Report a summary:" block in `build.md` with: `Update the plan status to 'implemented'. Briefly confirm completion and direct the user to /pr.` Do not prescribe shape — 4.7 emits concise completion reports natively.

After editing, verify:
- `grep -c "Steps completed" commands/build.md` returns 0 (scaffolding gone)
- `grep -c "paste failing output" commands/build.md` returns ≥ 1 (TDD gate intact)
- `grep -c "paste passing output" commands/build.md` returns ≥ 1 (TDD gate intact)

**Guardrail**: Do NOT edit `build.md` lines containing `RED`, `GREEN`, `paste failing output`, `paste passing output`, `hard gate`, or `verification evidence`. These are substantive TDD gates, not scaffolding.

**REFACTOR**: None.
**Files**: `plugins/agentic-dev-team/commands/build.md`
**Commit**: `refactor(build): remove canned summary template; trust native progress output`

### Step 1: Re-baseline token budgets

**Complexity**: `standard`
**RED**: Write `scripts/measure-tokens.sh` that:
- Uses `@anthropic-ai/tokenizer@latest` (record exact version in footnote)
- Measures tokens for every file named in CLAUDE.md's `### Baseline Budget` section
- Compares claimed vs. measured; exits non-zero if any file deviates > 10%
- Supports `--verify` (read table from CLAUDE.md) and unadorned mode (print measurements)

First run against main MUST exit non-zero (current table was measured on pre-4.7 tokenizer).

**GREEN**: Update the "Baseline Budget" section in CLAUDE.md with measured values. Add footnote: `*Measured 2026-04-20 with @anthropic-ai/tokenizer@<exact-version>. Re-baseline when the tokenizer changes.*` Recompute "Full load" total and the "< 10,000 tokens" simple-task target. If the target is no longer reachable, update it with a footnote explaining why (do not hide the drift).

Anchor in CLAUDE.md must be the section heading `### Baseline Budget`, not a line number. Step 3 may relocate — if it moves, the anchor still resolves.

**REFACTOR**: Cross-check ONE file's count against the Claude Code runtime's own accounting (spawn a short test sub-agent, note the reported context usage). Document any systematic delta between local measurement and harness measurement in the footnote.

**Files**: `plugins/agentic-dev-team/CLAUDE.md`, `scripts/measure-tokens.sh` (top-level scripts, dev-only tooling)
**Commit**: `chore: re-baseline token budget table for Opus 4.7 tokenizer`

### Step 3: Slim CLAUDE.md per its own architectural invariant

**Complexity**: `standard`
**RED**: `scripts/measure-tokens.sh CLAUDE.md` reports > 1,100 tokens (architectural invariant ~800 + 35% tokenizer upper bound from Step 1). This is failing state.

**GREEN**: Apply CLAUDE.md's own architecture rule (lines 9-14): content in CLAUDE.md must be *needed every session*. Content needed only when a specific phase or skill activates moves to `knowledge/` (reference data) or `skills/` (procedures).

Relocations:
- **Multi-LLM Routing table** (Claude vs. Gemini) → `knowledge/multi-llm-routing.md`. Reference data. One-line pointer in CLAUDE.md.
- **Performance Metrics Targets** (10-15% efficiency, 95% accuracy, etc.) → `knowledge/performance-targets.md`. Reference values, not procedures. One-line pointer in CLAUDE.md. **Do NOT** put this in `skills/performance-metrics/SKILL.md` — that file is the logging procedure; targets belong in knowledge per the existing `knowledge/agent-registry.md` precedent.
- **Feedback & Learning** prose → reduce to a 2-line pointer to the skill.
- **Human Oversight** prose → reduce to a 2-line pointer to the skill.
- **Detailed Model Routing rationale** → keep the compact table in CLAUDE.md; rationale column already exists in `agents/orchestrator.md`.

Retained (every-session content) — heading levels match current CLAUDE.md exactly (do NOT promote or demote during relocation):
- `## Architecture`
- `## Output Guardrails`
- `## Core Principles`
- `## Request Processing Flow` containing `### Three-Phase Workflow` (keep the parent H2 and the H3 child)
- `## Multi-Agent Collaboration Protocol` containing `### Sub-Agents as Context Isolation` and `### Multi-Agent Coordination`
- `## Model Routing` (summary table only; detailed rationale stays in `agents/orchestrator.md`)
- `## Context Management`

**REFACTOR**: Run `scripts/check-links.sh CLAUDE.md` (create the script if it doesn't exist — it greps `@`-refs and `[](...)` markdown links from CLAUDE.md and asserts each target path exists). Verify all pointers resolve. Exit non-zero if any link is broken.

**Files**: `plugins/agentic-dev-team/CLAUDE.md`, `plugins/agentic-dev-team/knowledge/multi-llm-routing.md` (new), `plugins/agentic-dev-team/knowledge/performance-targets.md` (new), `scripts/check-links.sh` (new)
**Commit**: `refactor(claude-md): relocate reference data to knowledge/ per architectural invariant`

### Step 2: Add Effort column to Model Routing Table (advisory-only)

**Complexity**: `standard`
**RED**: Write `scripts/check-routing-table.sh` that:
- Parses the Model Routing Table in `agents/orchestrator.md` (locate by section heading, not line number)
- Fails if any row lacks an Effort value from `{high, xhigh, max}`
- Fails if the table is not followed by a footnote containing the word `advisory` AND (`prompt-level` OR `prose`)
- Mirrors the check for the summary in `CLAUDE.md`

First run against main MUST exit non-zero.

**GREEN**: Per Step 0's finding, effort is advisory (encoded as prose), not a dispatch field.
- Add `Effort` column to the Model Routing Table in `agents/orchestrator.md`.
  - Default: `haiku` rows → `high`; `sonnet` rows → `high`; `opus` rows and `architect` → `xhigh`.
  - `max` appears only where explicitly annotated for deep-reasoning work.
- Add a footnote immediately below the table: `*Effort is advisory — it records the intended tier. Runtime effort is controlled at the Claude Code session level (per `docs/spikes/effort-parameter-support.md`). Agents convey effort intent via prompt-level thinking directives (see Step 7 / thinking-intensity guidance in each agent file).*`
- Mirror in `CLAUDE.md`'s summary table.
- Add a subsection `### Mid-task Effort Toggling` to `agents/orchestrator.md` (4–6 lines): default is the table value; escalate to `max` when a subproblem requires cross-file reasoning or novel design; revert to default after. Contains the literal words `escalate`, `revert`, and `max`.

**REFACTOR**: Do NOT edit `prompts/implementer.md` or `prompts/quality-reviewer.md` with `effort:` fields — the spike rejected that path. Instead, cross-link from those templates to the orchestrator's Effort section so dispatchers read the intended tier when crafting their prompt.

**Files**: `plugins/agentic-dev-team/agents/orchestrator.md`, `plugins/agentic-dev-team/CLAUDE.md`, `scripts/check-routing-table.sh` (new)
**Commit**: `feat(routing): add advisory effort tier column to model routing table`

### Step 6: Add subagent-restraint rule (Anthropic-official guidance)

**Complexity**: `trivial`
**Anchor verification**: Confirmed via grep — the `### Multi-Agent Coordination` subsection exists in `CLAUDE.md` (under `## Multi-Agent Collaboration Protocol`). It does NOT exist in `agents/orchestrator.md` (which has `## Collaboration Protocols` with different subsections). Target: CLAUDE.md.

**RED**: `grep -F "Do not spawn a subagent for work you can complete directly in a single response." CLAUDE.md` returns no match.

**GREEN**: In `plugins/agentic-dev-team/CLAUDE.md`, at the top of the `### Multi-Agent Coordination` subsection (directly under the H3 heading, before the numbered list "1. Orchestrator identifies..."), insert the exact sentence:

> Do not spawn a subagent for work you can complete directly in a single response. Spawn multiple subagents in the same turn when fanning out across items or reading multiple files.

Source: Anthropic's official best-practices post — quoted verbatim so the literal-instruction character of 4.7 works in our favor.

**REFACTOR**: Read the numbered coordination list that follows. If any bullet prescribes sub-agent use for trivial work, soften to "for non-trivial tasks..." language so it doesn't contradict the new restraint rule.

**Files**: `plugins/agentic-dev-team/CLAUDE.md`
**Commit**: `feat(orchestrator): add subagent restraint rule per Opus 4.7 guidance`

### Step 7: Add thinking-intensity directives to agent frontmatter

**Complexity**: `standard`
**Bucket verification**: Confirmed via `grep ^model: plugins/agentic-dev-team/agents/*.md`. Actual counts:

**OPUS bucket** (6 files) — receive `Think carefully and step-by-step; this problem is harder than it looks.`:
- `agents/arch-review.md`
- `agents/architect.md`
- `agents/domain-review.md`
- `agents/security-review.md`
- `agents/software-engineer.md`
- `agents/security-engineer.md`

**HAIKU bucket** (5 files) — receive `Prioritize responding quickly rather than thinking deeply.`:
- `agents/naming-review.md`
- `agents/complexity-review.md`
- `agents/claude-setup-review.md`
- `agents/token-efficiency-review.md`
- `agents/performance-review.md`

Sonnet-tier agents (all others): no directive added — they are the default baseline.

**RED**: Write `scripts/check-thinking-directives.sh` that:
- Parses each `agents/*.md` YAML frontmatter (content between the first pair of `---` delimiters). Uses a proper frontmatter parser, not a loose line-level grep.
- For files with frontmatter `model: opus` OR `name: architect`: asserts body contains the literal opus directive sentence exactly once (`grep -c` returns 1, not ≥ 1 — avoids duplicate-insertion bugs).
- For files with frontmatter `model: haiku`: asserts body contains the literal haiku directive sentence exactly once.
- For files matching neither: asserts body contains NEITHER directive (prevents cross-contamination).
- Exits non-zero if any agent is missing its required directive OR has the wrong directive OR has a duplicate.

First run against main MUST exit non-zero.

**GREEN**: Apply the bucketed directives. Prescribed placement (uniform across all 12 files for structural consistency): insert as a new H2 subsection `## Thinking Guidance` placed immediately after the YAML frontmatter close (`---`) and before the existing first heading. Body is exactly the one sentence — no prose around it.

This avoids: (a) colliding with existing first content (bullet lists, H1/H2 headings), (b) ambiguity about "opening line" placement, (c) breaking markdown parsing.

**REFACTOR**: Run the script; also grep each file to confirm no conflict between the new directive and any pre-existing speed/thinking prompts in the body. If a conflict is found, remove the older prompt (the Step 7 directive is the canonical source).

**Files**: 12 agent files (7 opus + 5 haiku per bucket verification above), `scripts/check-thinking-directives.sh` (new). Note: the script is authoritative — if a new opus/haiku agent is added between plan approval and GREEN, add it to the commit.
**Commit**: `feat(agents): add thinking-intensity directives per Opus 4.7 guidance`

### Step 5: Sweep negative rules with 3-bucket classification

**Complexity**: `standard`
**RED**: Write `scripts/check-negative-rules.sh` that:
- Scans the fixed file list: `agents/orchestrator.md`, `commands/build.md`, `commands/plan.md`, `commands/code-review.md`, `CLAUDE.md`
- Identifies every line matching `^.*(Do not|DO NOT|DON'T|Don't|Never|NEVER)` that is not already inside a code fence
- For each match, prints: filepath:line:match:classification
- Classification is SAFETY-GATE if the preceding comment `<!-- SAFETY-GATE:` is present; NATIVE if the line is marked `<!-- NATIVE:` with explanation; PROCESS if converted to a block containing `Example 1:` and `Example 2:`; UNRESOLVED otherwise
- Exits non-zero if any UNRESOLVED remains

First run MUST exit non-zero with a baseline count. Record that count in the commit message.

**GREEN**: For each unresolved negative rule, classify as:
- **SAFETY-GATE** (destructive action, data loss, security): keep negative, add `<!-- SAFETY-GATE: <1-line reason> -->` on the preceding line
- **NATIVE** (4.7 handles without the rule): delete the line, add `<!-- NATIVE: <1-line reason> -->` as a comment where the line was (so diff reviewers can see the deletion was intentional)
- **PROCESS** (non-obvious convention): convert to a block:
  ```
  Example 1: <concrete valid case>
  Example 2: <concrete valid case>
  ```

Post-GREEN count of UNRESOLVED is 0. Post-GREEN count of PROCESS blocks matches the pre-GREEN count of rules tagged PROCESS.

**REFACTOR**: Re-run the script. Audit SAFETY-GATE classifications — any that look questionable on second read should be downgraded to PROCESS (safer default if unclear).

**Files**: `plugins/agentic-dev-team/agents/orchestrator.md`, `plugins/agentic-dev-team/commands/build.md`, `plugins/agentic-dev-team/commands/plan.md`, `plugins/agentic-dev-team/commands/code-review.md`, `plugins/agentic-dev-team/CLAUDE.md`, `scripts/check-negative-rules.sh` (new)
**Commit**: `refactor(prompts): classify and convert non-gate negative rules (3-bucket sweep)`

### Step 8: Add task-complete notification hook

**Complexity**: `trivial`
**RED**: `test -x plugins/agentic-dev-team/hooks/task-complete-notify.sh` exits non-zero (file missing).

**GREEN**: Create `plugins/agentic-dev-team/hooks/task-complete-notify.sh`:
```bash
#!/usr/bin/env bash
# Stop hook — plays a system sound when a long-running task finishes.
# Opt-out: remove the Stop entry from plugins/agentic-dev-team/settings.json.
if [[ "$(uname)" == "Darwin" ]] && command -v afplay &> /dev/null; then
  afplay /System/Library/Sounds/Glass.aiff 2>/dev/null &
fi
exit 0
```

Register in `plugins/agentic-dev-team/settings.json` under the `Stop` event. No-op on Linux/Windows (silent success).

**REFACTOR**: None.
**Files**: `plugins/agentic-dev-team/hooks/task-complete-notify.sh` (new), `plugins/agentic-dev-team/settings.json`
**Commit**: `feat(hooks): add task-complete notification Stop hook`

## Complexity Classification

| Step | Rating | Rationale |
|------|--------|-----------|
| 0 | trivial | Spike doc, evidence already gathered |
| 4 | trivial | Single-file deletion + grep-verifiable guards |
| 1 | standard | New tooling + measured doc update |
| 3 | standard | Cross-file relocation, governed by explicit architecture rule |
| 2 | standard | Documentation addition per spike result; cross-file (orchestrator + CLAUDE.md) |
| 6 | trivial | One-sentence insertion verbatim from source |
| 7 | standard | Touches 9 agent files; grep-verifiable |
| 5 | standard | Judgment-per-line with 3-bucket machine check |
| 8 | trivial | New hook script + settings entry |

No step is classified `complex`. The effort column (formerly complex) drops to standard because the spike removed the dispatch-contract question.

## Pre-PR Quality Gate

- [ ] All 12 acceptance criteria met (AC-1 through AC-12 above)
- [ ] `/agent-audit` exits 0
- [ ] `/agent-eval` shows no fixture below baseline
- [ ] `scripts/measure-tokens.sh --verify` exits 0
- [ ] `scripts/check-routing-table.sh` exits 0
- [ ] `scripts/check-thinking-directives.sh` exits 0
- [ ] `scripts/check-negative-rules.sh` exits 0
- [ ] `scripts/check-links.sh CLAUDE.md` exits 0
- [ ] All 5 sweep files + 9 agent files + CLAUDE.md lint clean
- [ ] `/code-review` passes
- [ ] Each commit uses conventional-commit prefix matching the step's change type (release-please compatible)

## Risks & Open Questions

- **Risk — tokenizer drift between local script and harness**: `scripts/measure-tokens.sh` uses `@anthropic-ai/tokenizer`. The harness may count slightly differently. Mitigation: Step 1 REFACTOR requires one cross-check against harness-reported context usage; document the delta in the footnote.
- **Risk — SAFETY-GATE misclassification in Step 5**: Converting a genuine safety rule to a positive exemplar weakens it. Mitigation: REFACTOR phase audits all SAFETY-GATE tags on second read; when unclear, downgrade to PROCESS (keeps both forms — original remains, examples added). Plan also fixes the file list so the sweep terminates.
- **Risk — Step 7 may add noise to agent files**: Nine agents gain a new opening sentence. If the sentence conflicts with their existing persona, output quality may drop. Mitigation: REFACTOR phase sanity-checks for conflicts.
- **Risk — Opportunity cost** (flagged by Strategic Critic): The plugin has `plans/security-review-companion-plugin.md` and beads-workflow companion plugin work pending. Mitigation: Phase A (Steps 0, 4, 1) is ≤ 1 hour of work and ships standalone — does not block the companion plugin roadmap. Phases C, D, E can be sequenced against the roadmap as capacity allows.
- **Open question — Step 7 applicability to all opus agents**: The thinking-intensity directives are general. Some opus agents may benefit from task-specific thinking prompts instead. Acceptable for v1; revisit after first `/agent-eval` pass.
- **Open question — `settings.json` Stop-hook format**: If the plugin's settings schema does not yet support `Stop` events, Step 8 may need to fall back to `PostToolUse` on specific tools. Resolve during Step 8 GREEN.

## Plan Review Summary

This plan is revision 2. Revision 1 received verdicts: UX approve; Acceptance needs-revision (4 blockers); Design needs-revision (2 blockers); Strategic needs-revision (2 blockers).

Revision 2 changes (addressing all 8 blockers):

| Blocker | Fix in rev 2 |
|---|---|
| Strategic B1 — problem framing speculative | Citing Anthropic's official best-practices post as primary source; ProductCompass as supporting. 4 of 5 recommendations now officially confirmed. |
| Strategic B2 / Design B1 — `effort:` unresolved | Step 0 spike committed (`docs/spikes/effort-parameter-support.md`). `effort:` is NOT a native Agent-tool parameter. Step 2 takes advisory-only branch; prompt-template edits dropped. |
| Design B2 — Steps 1/2/3 overlap on CLAUDE.md | Explicit sequencing table added (§ Phase Sequencing). Line-number anchors replaced with section-heading anchors throughout. |
| Acceptance B1 — effort-toggle "documents" weasel | AC-3 now grep-verifiable (section heading + required literal words). |
| Acceptance B2 — hardcoded line 178-184 | AC-4 anchors to `### Baseline Budget` heading with ≤ 10% threshold. |
| Acceptance B3 — "actually loaded per-session" ambiguous | AC-5 enumerates retained section headings; success tied to token budget ≤ 1,100, not a line count. |
| Acceptance B4 — "top 5 most-invoked files" undefined | AC-7 lists the 5 files explicitly; Step 5 uses the same fixed list. |

Warnings from revision 1 also addressed: tokenizer identity in footnote (Step 1 REFACTOR); positive grep guards in Step 4 acceptance; `/agent-audit` command form specified (AC-11); `/agent-eval` baseline capture defined (AC-12); performance-metrics Targets routed to `knowledge/` not `skills/` (Step 3); scripts placed in top-level `scripts/` (dev-only); 3-bucket classification added to Step 5.

New additions from Anthropic's official post (absent in revision 1): Step 6 (subagent restraint), Step 7 (thinking-intensity directives), Step 8 (task-complete notify hook).

**Awaiting re-review** by Strategic, Acceptance, and Design critics. UX Critic already approved — does not need re-review.
