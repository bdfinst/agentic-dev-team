# Combined Plan: Opus-4.7 Alignment × Security-Review Companion Plugin

**Created**: 2026-04-20
**Branch**: main
**Status**: approved (2026-04-20)
**Type**: coordination plan (does not replace source plans; sequences them)

## Purpose

Coordinate the execution of two independently-approved plans whose file scopes overlap in `CLAUDE.md`, `agents/security-review.md`, `commands/code-review.md`, `commands/review-agent.md`, `knowledge/agent-registry.md`, and `settings.json`. Without coordination the plans will either fight (merge conflicts; drifting token baselines; sweeps chasing tails) or produce costly rework.

This combined plan is the **execution schedule**. Step-level details remain in the two source plans — this document defines *when* each source plan's phases run and what conventions bind them together.

## Source plans

- **P1**: [`plans/opus-4-7-alignment.md`](./opus-4-7-alignment.md) — 9 steps, rev 2 (strategic + acceptance approved; design fixes applied)
- **P2**: [`plans/security-review-companion-plugin.md`](./security-review-companion-plugin.md) — 20 steps, rev 6 approved
- **Spike artifact**: [`docs/spikes/effort-parameter-support.md`](../docs/spikes/effort-parameter-support.md) — P1 Step 0 output (✓ complete)

## Guiding decision

Ship P1's quick wins today; gate P1's broader refactor work behind P2's landing; make P2 convention-compliant in flight so P1's Phase C/D/E becomes verification rather than sweep.

The mechanism is a small addendum to P2 (three "conventions-in-flight" acceptance criteria — section below) that ensures P2's new files adopt the conventions P1 is introducing. That addendum is the single point of coordination between the two plans.

## Stage sequencing

Each stage has a gate condition. Later stages do not begin until the prior stage's gate is green.

| Stage | Owner plan | Scope | Gate to enter next stage |
|---|---|---|---|
| **Stage 0** | P1 | P1 Step 0 (spike) — ✅ complete | `docs/spikes/effort-parameter-support.md` exists |
| **Stage 1** | P1 | P1 Step 4 (remove build scaffolding) + P1 Step 1a (measurement script only) | Both merged to main; CI green |
| **Stage 2** | P2-addendum | Adopt P2 rev 7 with three conventions-in-flight ACs (section below) | P2 rev 7 marked `approved` with the three ACs present |
| **Stage 3** | P2 | P2 Phase A (Steps 1–5): primitives, ACCEPTED-RISKS, SARIF baseline, primitives contract, contract-version-guard | P2 Phase A merged; `/agent-audit` green; all conventions-in-flight ACs verified against new files |
| **Stage 4** | P2 | P2 Phase B (Steps 6–14): companion plugin scaffold, PostToolUse hook, FP-reduction, business-logic-domain-review, narrative annotator, compliance mapping, service-comm, `/security-assessment`, exec report | P2 Phase B merged; tier-1 evals green |
| **Stage 5** | P2 | P2 Phase C (Steps 15–19): red-team harness, probes, analysis agents, `/export-pdf` | P2 Phase C merged; tier-2 evals green (nightly) |
| **Stage 6** | P2 | P2 Phase D (Step 20): registry + release-please + final audit | P2 fully merged; per-plugin release-please bumps verified |
| **Stage 7** | P1 | P1 Phase C/D/E (Steps 1b, 3, 2, 6, 7, 5, 8) on post-P2 codebase; now largely verification if conventions-in-flight held | P1 fully merged |

**Total elapsed time**: Stage 1 today; Stage 2 within a week; Stages 3–6 on P2's native timeline (multi-week); Stage 7 ≤ 1 day after P2 lands. Parallel work within stages is allowed where source plan permits.

## Gate details

### Stage 1 gate (Opus-4.7 quick wins)

- [ ] `commands/build.md` no longer contains the "Steps completed" summary template (`grep -c "Steps completed" plugins/agentic-dev-team/commands/build.md` returns 0)
- [ ] `commands/build.md` still contains TDD hard gates (`grep -c "paste failing output"` ≥ 1, `grep -c "paste passing output"` ≥ 1)
- [ ] `scripts/measure-tokens.sh` committed, documented, and exits 0 when run with no args (prints per-file measurements)
- [ ] `scripts/measure-tokens.sh --verify` may exit non-zero at this stage — the CLAUDE.md table update is deferred to Stage 7 so it measures against the post-P2 codebase
- [ ] `/agent-audit` green

**Why Step 1 is split across Stages 1 and 7**: measuring now gives us the script; updating CLAUDE.md's budget numbers now wastes effort because P2 changes them. Stage 7 re-runs the script and writes the final numbers.

### Stage 2 gate (conventions-in-flight addendum)

P2 rev 7 contains three new acceptance criteria (full text in next section). Gate is satisfied when the security-review plan file shows these three criteria marked, `Status: approved (revision 7)`, and a brief revision note explaining the addendum.

### Stage 3-6 gates

Owned by P2. See P2's own Pre-PR Quality Gate. The combined plan requires, additionally:

- Each merged P2 phase passes the conventions-in-flight check: any new opus-tier agent carries the thinking directive, new CLAUDE.md content respects the architecture rule, new negative rules are pre-classified. These are verified by the same scripts P1 Stage 7 introduces (`scripts/check-thinking-directives.sh`, `scripts/check-links.sh`, `scripts/check-negative-rules.sh`) — the scripts run in an advisory-only mode during Stages 3–6 (warnings, not failures) and become blocking in Stage 7.

### Stage 7 gate (Opus-4.7 completion)

All P1 Phase C/D/E acceptance criteria (AC-2 through AC-12 in `plans/opus-4-7-alignment.md`) satisfied against the post-P2 codebase. If conventions-in-flight held during Stages 3–6, this stage becomes lightweight:
- Step 7 (thinking directives): ideally zero changes — all opus agents already compliant
- Step 5 (negative-rule sweep): ideally zero unclassified negatives
- Step 3 (CLAUDE.md slim): targets revised against the new baseline from Step 1 re-run
- Step 2 (effort column): pure documentation addition, no file conflicts left
- Step 6 (subagent restraint): one-sentence insertion in CLAUDE.md
- Step 8 (task-complete hook): independent, no conflicts

## Conventions-in-flight addendum to P2 (rev 7)

Add these three acceptance criteria to `plans/security-review-companion-plugin.md` under a new subsection `### Conventions-in-flight (from combined-plan-opus-4-7-security-review.md)`:

### AC-CIF-1: Opus-tier agents carry thinking directive

> Any new file added under `plugins/agentic-dev-team/agents/` or `plugins/agentic-security-assessment/agents/` whose YAML frontmatter declares `model: opus` must contain the literal sentence `Think carefully and step-by-step; this problem is harder than it looks.` as an H2 subsection titled `## Thinking Guidance` placed immediately after the frontmatter close (`---`) and before any other heading. The body of the subsection is exactly that one sentence.
>
> Any new file with `model: haiku` must contain the literal sentence `Prioritize responding quickly rather than thinking deeply.` in the same placement.
>
> **Source**: Anthropic's official "Best Practices for Claude Opus 4.7 with Claude Code" post (`https://claude.com/blog/best-practices-for-using-claude-opus-4-7-with-claude-code`). Tracked by P1 Step 7.
>
> **Verification**: Apply during every new-agent commit in Stages 3–5. P1 Step 7 ships `scripts/check-thinking-directives.sh` in Stage 7 as the definitive gate; during P2 execution, reviewers manually verify new agents.
>
> **Impacted new opus agents** (per P2's plan): `codebase-recon`, `fp-reduction`, `business-logic-domain-review`, `cross-repo-synthesizer`, `exec-report-generator`, `redteam-recon-analyzer`, `redteam-evasion-analyzer`, `redteam-extraction-analyzer`, `redteam-report-generator`. (9 files.)

### AC-CIF-2: CLAUDE.md additions follow architecture rule

> New content added to `plugins/agentic-dev-team/CLAUDE.md` during P2 execution must be **needed every session**. Content that is reference data (schemas, registries, policy tables) goes in `plugins/agentic-dev-team/knowledge/`. Content that is a procedure (how to use a capability) goes in `plugins/agentic-dev-team/skills/`. CLAUDE.md receives at most a one-line pointer per relocated block.
>
> **Exception**: registry summary rows for new agents/skills/commands may appear in CLAUDE.md's existing `### Quick Reference` section (they are per-session references for the orchestrator).
>
> **Verification**: Review at P2 commit time. P1 Step 3 ships `scripts/check-links.sh` in Stage 7 to verify all pointers resolve.

### AC-CIF-3: New negative rules pre-classified

> Any new line added to `{plugins/agentic-dev-team/agents/orchestrator.md, plugins/agentic-dev-team/commands/build.md, plugins/agentic-dev-team/commands/plan.md, plugins/agentic-dev-team/commands/code-review.md, plugins/agentic-dev-team/CLAUDE.md}` during P2 execution that matches the pattern `^.*(Do not|DO NOT|Don't|DON'T|Never|NEVER)` must be preceded by one of:
>
> - `<!-- SAFETY-GATE: <1-line reason> -->` — for destructive actions, security, data loss protections (keep as negative)
> - Converted to a positive exemplar block containing the literal strings `Example 1:` and `Example 2:` — for process rules
>
> Rules that would be `NATIVE` (Opus 4.7 handles without the rule) per P1 Step 5's classification should not be added in the first place — if a rule feels "obvious," omit it.
>
> **Verification**: Review at P2 commit time. P1 Step 5 ships `scripts/check-negative-rules.sh` in Stage 7 to verify no unclassified negatives remain.

### Rationale for the addendum

Each AC is ≤ 15 minutes of additional work per affected commit. Collectively they prevent Stage 7 from becoming a multi-day sweep across files that just landed. The alternative is to let P2 land un-conventioned, then retrofit conventions in Stage 7 — which would touch every new agent file and every new CLAUDE.md section, creating a much larger and riskier Stage 7 PR.

## Shared file conflict matrix

Reference for anyone opening a PR that touches these files during any stage.

| File | P1 writes | P2 writes | Conflict mitigation |
|---|---|---|---|
| `CLAUDE.md` | Stage 7 (Step 3 slim, Step 2 effort, Step 6 subagent restraint) | Stages 3, 6 (registry rows, hook opt-out docs, contract reference) | P2 adds before P1 slims; P1 slim target revised against post-P2 baseline; AC-CIF-2 constrains P2 additions |
| `agents/security-review.md` | Stage 7 (Step 7 thinking directive) | Stage 3 (ACCEPTED-RISKS consultation) | Additive; AC-CIF-1 means P2 Stage 3 adds the directive up front — Stage 7 is a verification no-op for this file |
| `commands/code-review.md` | Stage 7 (Step 5 negative sweep) | Stages 3, 3a (ACCEPTED-RISKS, SARIF orchestration) | AC-CIF-3 pre-classifies P2's new negatives; Stage 7 sweep is lightweight |
| `commands/review-agent.md` | — | Stage 3 (ACCEPTED-RISKS consultation) | P1 does not touch this file |
| `commands/agent-audit.md` | — | Stage 3 (extended to validate contract references) | P1 does not touch this file |
| `knowledge/agent-registry.md` | Read-only (P1 Step 1 baseline) | Stage 6 (new components registered) | P1 Stage 1 captures pre-P2 baseline; Stage 7 re-baseline captures post-P2 |
| `settings.json` | Stage 7 (Step 8 Stop hook) | Stage 3 (PreToolUse contract-version-guard), Stage 4 (PostToolUse in companion plugin — not agentic-dev-team's settings.json) | Different event keys; additive; zero conflict |
| New opus agents (9 files) | Stage 7 (Step 7 directive) | Stages 3–5 (file creation) | AC-CIF-1 means directive lands with each file; Stage 7 verifies only |

## Resource implications

| Stage | Effort | Calendar | Blocking? |
|---|---|---|---|
| Stage 1 | ≤ 1 hour | Today | Not blocking anything |
| Stage 2 | ≤ 15 min | Within a week | Must precede Stage 3 |
| Stage 3 | P2 Phase A owner estimate | Multi-day | Blocks Stages 4, 7 |
| Stage 4 | P2 Phase B owner estimate | Multi-week | Blocks Stages 5, 7 |
| Stage 5 | P2 Phase C owner estimate | Multi-week | Blocks Stages 6, 7 |
| Stage 6 | P2 Phase D owner estimate | ≤ 1 day | Blocks Stage 7 |
| Stage 7 | ≤ 1 day (if conventions-in-flight held) | After Stage 6 | Final stage |

**Total critical path**: P2's own multi-week timeline + 1 hour (Stage 1) + 15 min (Stage 2) + ≤ 1 day (Stage 7).

Stage 1 and Stage 2 do not block P2 — they can be done before or alongside P2's Stage 3 without friction.

## Pre-merge quality gate for this combined plan

- [ ] Both source plans exist at the paths referenced in `## Source plans`
- [ ] P1 Step 0 spike complete (`docs/spikes/effort-parameter-support.md` exists)
- [ ] P2 rev 7 with the three conventions-in-flight ACs accepted (satisfies Stage 2 gate)
- [ ] This combined plan linked from both source plans' `## Plan Review Summary` sections (so anyone reading either plan finds the coordinator)
- [ ] An ADR or decision-log entry in `memory/decisions.md` records the Stage 1 / Stage 7 split for P1 Step 1

## Risks & open questions

- **Risk — Stage 2 adoption latency**: the conventions-in-flight addendum requires P2's author to accept a rev 7. If that takes longer than expected, Stage 3 starts without conventions bound, and Stage 7 grows. Mitigation: keep the addendum small (3 ACs, ~60 lines of spec). If rejected, fall back to Option 3 (delay P1 entirely until P2 ships and then sweep).
- **Risk — convention drift within P2's own phases**: P2 spans multi-week implementation; a new contributor might miss the conventions-in-flight ACs. Mitigation: advisory-mode scripts (the P1 check scripts run as warnings during Stages 3–5) give real-time feedback without blocking P2's pace.
- **Risk — token-baseline script divergence from harness tokenizer**: `scripts/measure-tokens.sh` uses `@anthropic-ai/tokenizer`; harness may count slightly differently. Mitigation: P1 Step 1's REFACTOR includes a single harness-cross-check; the Stage 7 re-run surfaces any systematic delta.
- **Risk — P2's new opus agents appearing after Stage 7**: If P2 adds opus agents in maintenance after Stage 7 closes, AC-CIF-1 becomes a standing convention with no enforcement. Mitigation: Stage 7 commits `scripts/check-thinking-directives.sh` as a permanent CI gate, so the convention continues to hold.
- **Open question — CLAUDE.md token ceiling after P2**: P2 materially grows CLAUDE.md. The current `~800` token architectural invariant may not be recoverable even after P1 Step 3's aggressive slim. If so, Stage 7 publishes a new invariant (e.g., `~1,300 tokens`) with a footnote explaining why, rather than targeting the old number. Resolve at Stage 7 start.
- **Open question — should Stage 1 include P1 Step 1 GREEN (CLAUDE.md footnote only, no numbers)?** Committing the footnote early records intent; numbers get filled in at Stage 7. Worth 5 minutes. Decide at Stage 1 kickoff.
- **Open question — Stage 2 could be a PR comment on the existing P2 rev 6 rather than a full rev 7 re-review.** If P2's author prefers, the addendum can be merged into P2 as a `docs:` commit without re-running the four plan-review personas. The substance is three additive ACs — they can't make the plan worse. Decide with P2's author.

## Decision log entry

```
ID: DEC-2026-04-20-001
Date: 2026-04-20
Agent: orchestrator (combined-plan authoring)
Task: Coordinate P1 (opus-4-7-alignment) and P2 (security-review-companion-plugin) execution
Decision: 7-stage interleaved sequence; P1 Phase A ships immediately, P1 Phase C/D/E deferred to Stage 7 post-P2; P2 adopts three conventions-in-flight ACs (rev 7) to reduce Stage 7 to verification.
Rationale: Both plans modify CLAUDE.md, agents/security-review.md, commands/code-review.md, and settings.json. Running them independently produces sweep-after-sweep rework. The addendum costs P2 ~15 min/file during execution and saves Stage 7 from being a multi-day retrofit.
Alternatives rejected:
  (a) Ship P1 in full before P2 — rejected: P1 Phase C/D/E would immediately be stale once P2 adds agents and CLAUDE.md content.
  (b) Delay P1 entirely until P2 ships — rejected: forgoes Stage 1 quick wins (build scaffolding, token measurement script) that are zero-conflict today.
  (c) No coordination, resolve conflicts at merge time — rejected: every P1-P2 overlap becomes a manual merge, and conventions would have to be retrofitted across many new files.
```

Append this entry to `memory/decisions.md` when the combined plan is approved.

## What to do next

1. **Review this combined plan.** Confirm the 7-stage sequencing, the three conventions-in-flight ACs, and the Stage 7 scope are what you want.
2. **If approved**: I can (a) update P1's status to reflect the Stage 1 / Stage 7 split, (b) draft the rev-7 addendum for P2 as a diff, and (c) append the decision-log entry.
3. **If you want changes**: specify which stage boundary or convention AC should shift.
