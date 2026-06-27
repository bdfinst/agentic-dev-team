# Spec: Plugin CLAUDE.md Size Reduction

<!-- spec-version: dev-team/specs@1 -->

## Intent Description

`plugins/dev-team/CLAUDE.md` is 30,232 characters — six times the 5,000-char threshold enforced by `scripts/token_efficiency_review.py`. The file is a comprehensive orchestration guide with 16 sections. At this size it adds significant token overhead to every conversation context where the plugin is loaded, and it fails the structural gate in `/agent-audit`.

The goal is to reduce CLAUDE.md to under 5,000 characters by extracting prose-heavy sections into dedicated skills or knowledge files, and replacing them in CLAUDE.md with concise references. CLAUDE.md becomes a lean routing index: it names where to find each concept, not what each concept says. No information is discarded — it moves into more specific, independently-loadable artifacts.

## Architecture Specification

**Target:** `plugins/dev-team/CLAUDE.md` ≤ 5,000 characters after the change.

**Current sections (16):**
`System Overview`, `North Star`, `Architecture`, `Output Guardrails`, `Core Principles`, `Team Organization`, `Agent & Skill Registry`, `Skills Registry`, `Request Processing Flow`, `Multi-Agent Collaboration Protocol`, `Model Routing`, `Context Management`, `Feedback & Learning`, `Human Oversight`, `Quality & Accuracy`, `Performance Metrics`

**Extraction strategy:**

Large prose sections (those whose content is already captured or naturally belongs in a skill/knowledge file) move out. CLAUDE.md retains only:

- One-line or short-paragraph summaries per concept
- A reference to the authoritative file (e.g., `see skills/context-loading-protocol/SKILL.md`)
- Hard invariants that must be visible at load time (not extractable)

**Constraints:**

- Every piece of information currently in CLAUDE.md must remain accessible — either kept in CLAUDE.md (as a summary or hard invariant) or moved to an existing or new skill/knowledge file.
- New files go under `plugins/dev-team/knowledge/` (for reference material) or `plugins/dev-team/skills/<name>/SKILL.md` (for actionable procedures). Follow existing naming conventions (kebab-case).
- Cross-references in CLAUDE.md use relative skill/knowledge names, not absolute paths, so the plugin remains portable.
- The sections `Core Principles` and `Output Guardrails` are likely short enough to stay in CLAUDE.md as-is; the implementation phase determines the exact cut.
- `Agent & Skill Registry` and `Skills Registry` sections reference `knowledge/agent-registry.md` — CLAUDE.md can collapse these to a single pointer line.
- Sections describing protocols already captured in skills (`Context Management` → `context-loading-protocol`, `Feedback & Learning` → `feedback-learning`, `Human Oversight` → `human-oversight-protocol`) can be replaced with one-line references.
- If a section has no existing home, create a new knowledge file for it.
- The plugin's `settings.json` and `install.sh` are not affected.
- `scripts/token_efficiency_review.py` is the validation oracle: `python3 scripts/token_efficiency_review.py --skip-llm --files plugins/dev-team/CLAUDE.md` must exit with no char-limit error.

## Acceptance Criteria

- [ ] `plugins/dev-team/CLAUDE.md` is ≤ 5,000 characters (measured by `len(text)`)
- [ ] `python3 scripts/token_efficiency_review.py --skip-llm --files plugins/dev-team/CLAUDE.md` exits 0 or 2 (warning only — llm-skipped); no char-limit error finding in output
- [ ] Every section from the original CLAUDE.md is either retained in condensed form or has a named, readable destination file that contains the full content
- [ ] No skill or knowledge file referenced from CLAUDE.md is missing on disk (`python3 scripts/claude_setup_review.py --plugin-root plugins/dev-team --skip-llm` exits 0 or 2 with no path-reference error)
- [ ] `/agent-audit` re-run shows PASS for CLAUDE.md token efficiency
- [ ] The plugin's functional behavior is unchanged — agents still load and route correctly; no agent or skill references a section that no longer exists in CLAUDE.md without a replacement pointer

## Ambiguity Log

| Decision | Classification | Resolved By | Rationale / Answer |
|---|---|---|---|
| Target character count: strict 5,000 vs pragmatic higher threshold | `requires-stakeholder-input` | Human | Option 1 chosen: strict under 5,000 chars, matching the `token_efficiency_review.py` threshold. |
| Which specific sections stay vs move | `inferable` | Inference | Implementation determines the exact split by measuring section sizes and checking for existing skill/knowledge homes. The constraint is the 5,000-char ceiling and the completeness criterion — not a pre-specified list of sections to move. |
| Whether to create new knowledge files or reuse existing ones | `inferable` | Inference | Reuse existing files where content already lives there (e.g., context-loading-protocol, human-oversight-protocol). Create new knowledge files only when no existing home exists. Follows established plugin conventions. |
| Whether moved content changes the plugin's functional behavior | `inferable` | Inference | Moving reference content (descriptions, protocols) into knowledge files changes only where it lives, not what it says. Agents load CLAUDE.md at context load time; if a section was informational prose, moving it to a knowledge file makes no behavioral difference unless an agent was instructed to follow it inline. |

## Consistency Gate

- [x] Intent is unambiguous — two developers would interpret it the same way
- [x] Every behavior/goal maps to at least one acceptance criterion
- [x] Architecture constrains without over-engineering — no new abstractions beyond knowledge files
- [x] Terminology consistent across artifacts
- [x] No contradictions between artifacts
- [x] Every gap/ambiguity finding is logged — target size resolved by human; all others inferable with rationale
