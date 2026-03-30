# Documentation Review Findings

**Reviewer**: Technical Writer agent
**Date**: 2026-03-30
**Scope**: All files in `docs/`, plus `CLAUDE.md` cross-references
**Status**: All findings fixed

---

## Summary

The documentation is well-structured and comprehensive. The primary issues are **stale counts and missing entries** where docs haven't kept pace with new agents, commands, and eval fixtures. There are also a few **incorrect path references** and **terminology inconsistencies**.

| Severity | Count |
|----------|-------|
| Error (factually wrong or misleading) | 5 |
| Warning (stale, incomplete, or inconsistent) | 7 |
| Suggestion (clarity or style) | 3 |

---

## Errors

### E1. `docs/agent_info.md` — Team agents table missing 2 agents

**Lines 9-20.** The Team Agents table lists 10 agents, but `CLAUDE.md` lists 12. Missing:

- **Knowledge Capture** (`agents/learn.md`)
- **ADR Author** (`agents/adr.md`)

Both files exist and both appear in the `docs/team-structure.md` Mermaid diagram (as `KC` and `ADR` nodes). The table is the only place they're omitted.

**Fix**: Add two rows to the Team Agents table.

---

### E2. `docs/eval-system.md` — Layer 2 agent count is stale

**Line 47.** States "Nine specialized agents" but:
- The table on lines 49-59 indeed lists 9 agents.
- However, the review agent roster now includes 19 agents (10 more were added since this doc was written: `a11y-review`, `concurrency-review`, `performance-review`, `arch-review`, `doc-review`, `svelte-review`, `spec-compliance-review`, `progress-guardian`, `refactoring-review`, `data-flow-tracer`).

The doc should clarify whether it describes *all* model-based review agents or only those with eval fixtures. Currently it reads as an exhaustive list.

**Fix**: Either update the table to list all 19 review agents, or add a qualifier like "Nine agents currently have eval fixture coverage" with a note that additional agents exist.

---

### E3. `docs/eval-system.md` — Fixture count and breakdown are stale

**Lines 170-183.** States "46 code samples" but the actual count is **54+ files** across `evals/fixtures/`. Specific discrepancies:

| Agent | Doc says | Actual |
|-------|----------|--------|
| test-review | 5 files | 6 files |
| svelte-review | not listed | 8 files (`sv-*.svelte.ts`) |
| Total | 46 | 54+ |

**Fix**: Update the fixture tree listing and total count. Add the `sv-*.svelte.ts` line for svelte-review fixtures.

---

### E4. `CLAUDE.md` — Model routing table missing 3 agents

The Model Routing summary table in `CLAUDE.md` under "## Model Routing" omits three sonnet-tier review agents that **are** listed in `docs/architecture.md` line 29:

- `refactoring-review`
- `progress-guardian`
- `data-flow-tracer`

**Fix**: Add these three to the `sonnet` row in the CLAUDE.md routing table.

---

### E5. `docs/skills.md` — Slash commands catalog missing 5 commands

The Slash Commands Catalog is missing commands that exist in `commands/` and are listed in `CLAUDE.md`:

| Command | File | Category |
|---------|------|----------|
| `/review` | `review.md` | Review (alias for `/code-review`) |
| `/triage` | `triage.md` | Workflow |
| `/issues-from-plan` | `issues-from-plan.md` | Workflow |
| `/competitive-analysis` | `competitive-analysis.md` | Workflow |
| `/harness-audit` | `harness-audit.md` | Eval |

**Fix**: Add these to the appropriate tables in `docs/skills.md`.

---

## Warnings

### W1. `docs/skills.md` — Leading slashes on directory names

**Line 6.** Uses `/skills/` and `/commands/` with leading slashes, implying absolute paths. The actual directories are `skills/` and `commands/` at the project root.

**Fix**: Remove leading slashes: `skills/` and `commands/`.

---

### W2. `docs/skills.md` — Skill template path uses `.claude/` prefix

**Line 140.** Says "Create `.claude/skills/{skill-name}.md`" — this is the path in a consuming project, not in this repo. The instruction is ambiguous in context.

**Fix**: Clarify: "In a consuming project, create `.claude/skills/{skill-name}.md`. In this repo, create `skills/{skill-name}.md`."

---

### W3. `docs/agent_info.md` — "Add a Team Agent" references wrong file

**Line 94.** Says "Add the agent to the Team Organization diagram in `CLAUDE.md`". The team organization diagram is actually in `docs/team-structure.md`, not in `CLAUDE.md`. `CLAUDE.md` has a registry table but no Mermaid diagram.

**Fix**: Change to "Add the agent to the Team Organization diagram in `docs/team-structure.md` and the Team Agents table in `CLAUDE.md`."

---

### W4. `docs/agent_info.md` — Manual review agent steps reference `.claude/` paths

**Lines 108-113.** The manual process for adding a review agent references `.claude/agents/` and `.claude/evals/`. In this repo, the paths are `agents/` and `evals/` (no `.claude/` prefix).

**Fix**: Remove `.claude/` prefix from paths, or add a note that these paths apply to consuming projects.

---

### W5. `docs/skills.md` — Missing "Beads Task Tracking" from Orchestration Skills table

**Line 23.** The Orchestration Skills table includes Beads, so this is actually present. No action needed. *(Self-correction after re-read.)*

However, the table is missing **three development discipline skills** that were added later:

| Skill | File | Purpose |
|-------|------|---------|
| CI Debugging | `ci-debugging.md` | CI pipeline failure investigation |
| Test Design Reviewer | `test-design-reviewer.md` | Test quality patterns and anti-patterns |
| Browser Testing | `browser-testing.md` | Playwright-based browser QA |

And missing **three research/design skills**:

| Skill | File | Purpose |
|-------|------|---------|
| Competitive Analysis | `competitive-analysis.md` | Gap analysis against external tools |
| Design Interrogation | `design-interrogation.md` | Stress-test design decisions |
| Design It Twice | `design-it-twice.md` | Parallel alternative interface design |

**Fix**: Add these 6 skills to the appropriate tables.

---

### W6. `docs/architecture.md` — Summarization table references API `usage` field

**Line 71.** States "Utilization is measured via the `usage` field in API responses." Claude Code does not expose a direct `usage` field to agents. The context loading protocol uses proxy signals (tool call count, message count, file read volume) rather than raw API usage metrics.

**Fix**: Replace with "Utilization is estimated via proxy signals (tool call volume, message count, accumulated file reads) as described in the Context Loading Protocol."

---

### W7. Terminology inconsistency: "skill" vs "command"

Across the docs, the term "skill" is sometimes used to describe slash commands (e.g., `docs/eval-system.md` line 99: "The `/apply-fixes` skill"). Slash commands and skills are distinct concepts per the definitions in `docs/skills.md` lines 3-6.

Affected locations:
- `docs/eval-system.md` line 99: "/apply-fixes skill" should be "/apply-fixes command"
- `docs/eval-system.md` line 209: "/agent-eval skill" should be "/agent-eval command"

**Fix**: Use "command" when referring to slash commands in `commands/`, reserve "skill" for knowledge modules in `skills/`.

---

## Suggestions

### S1. `docs/agent-readiness-scorecard.md` — Self-contained and clear

This document is well-written. The progressive disclosure structure (tiers -> weights -> detailed criteria -> calculation) works well. The "Why it matters" and "Dashboard automation" sections under each category are particularly effective. No changes needed.

---

### S2. `docs/cadad-roadmap.md` — Add completion status column

The todo list items use `- [ ]` checkboxes but there's no indication of which (if any) have been started. Consider adding a `Status` column (Not started / In progress / Done) to the summary table at the bottom, or converting the checkboxes to a project board.

---

### S3. `docs/architecture.md` — Add a "reading order" note

This is the most comprehensive doc and serves as the system's architecture reference. A one-line note at the top suggesting reading order would help newcomers: "Start with the System Overview flowchart, then read Context Management to understand how agents are loaded."

---

## Cross-Document Consistency Check

| Claim | CLAUDE.md | docs/architecture.md | docs/agent_info.md | docs/skills.md | docs/eval-system.md |
|-------|-----------|---------------------|-------------------|---------------|-------------------|
| Team agent count | 12 | — | **10** (missing 2) | — | — |
| Review agent count | 19 | — | 19 | — | **9** (stale) |
| Skill count | 27 | — | — | **21** (missing 6) | — |
| Slash command count | 27 | — | — | **22** (missing 5) | — |
| Eval fixture count | — | — | — | — | **46** (actual: 54+) |
| Model routing (sonnet) | **missing 3** | correct (includes 3) | — | — | — |
