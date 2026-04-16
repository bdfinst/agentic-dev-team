# Plan: Superpowers Gap Closure

**Created**: 2026-04-16
**Branch**: superpowers
**Status**: implemented

## Goal

Implement all 10 slices from the superpowers gap closure spec: 7 core improvements (A-G) that close gaps identified in the competitive analysis against obra/superpowers, plus 3 platform support slices (H1-H3) for Windows hooks, Gemini CLI, and OpenAI Codex. All changes are documentation/configuration — markdown skill files, knowledge files, prompt templates, manifest files, and shell scripts. No application code is being written; "tests" are acceptance criteria checks (file exists, token budget met, cross-references valid).

## Acceptance Criteria

- [ ] All files listed in the spec's acceptance criteria exist and meet their requirements
- [ ] No regression: all 9 existing hooks produce the same exit codes and stdout on macOS/Linux as before changes (verified by running each hook). All existing slash commands in CLAUDE.md remain present with valid frontmatter (verified by grep for `---` blocks in `commands/*.md`).
- [ ] Token budgets respected (estimated via word count × 1.35): anti-rationalization < 600, receiving-code-review < 500, agent-skill-authoring < 1200, testing-anti-patterns < 400, each debugging reference < 400. Files within 10% of limit require a second check.
- [ ] Terminology consistent: `grep -r "rationalization prevention\|rationalization bulletproofing"` returns zero matches across all new/modified files (knowledge/anti-rationalization.md, quality-gate-pipeline/SKILL.md, test-driven-development/SKILL.md, prompts/implementer.md, CLAUDE.md)
- [ ] Cross-references resolve: all relative markdown links in new/modified files resolve from the file's own directory (verified at Step 18; broken links fixed before PR)
- [ ] `knowledge/agent-registry.md` updated with all new files
- [ ] `CLAUDE.md` quick reference updated with new skill count (31→32: +receiving-code-review) and skills-by-phase table
- [ ] `gemini-extension.json` contains name (string), version (string), description (string), contextFileName (string) — verified by `python3 -m json.tool gemini-extension.json`
- [ ] `.codex/config.toml` parses without error — verified by `python3 -c "import tomllib; tomllib.load(open('.codex/config.toml','rb'))"`
- [ ] GEMINI.md and AGENTS.md skill registries match CLAUDE.md skill count (maintenance gate for context file drift)
- [ ] Windows hooks shim: (1) `run-hook.cmd` passes stdin bytes to bash script (echo fixture test), (2) propagates exit codes 0, 1, 2 from bash script, (3) when no bash found, exits code 1 with message containing "bash" and "Git for Windows"

## User-Facing Behavior

See `docs/specs/superpowers-gap-closure.md` for the full Gherkin scenarios (53 scenarios across 10 slices). The scenarios are the behavioral contracts.

## Steps

Steps are ordered by dependency: independent slices first, then dependent chains, then shared-file updates last.

---

### Step 1: Create anti-rationalization knowledge file (Slice A — part 1)

**Complexity**: standard
**RED**: Verify `knowledge/anti-rationalization.md` does not exist
**GREEN**: Create the knowledge file with 5+ categories, catch-all rule, cross-references to TDD and debugging tables
**REFACTOR**: Verify under 600 tokens, terminology is canonical
**Files**: `plugins/agentic-dev-team/knowledge/anti-rationalization.md`
**Commit**: `feat: add anti-rationalization knowledge file with cross-cutting patterns`

### Step 2: Update Quality Gate Pipeline with anti-rationalization references (Slice A — part 2)

**Complexity**: standard
**RED**: Verify `quality-gate-pipeline/SKILL.md` Phase 1 and Phase 2 do not reference anti-rationalization knowledge
**GREEN**: Add reference to existing Phase 2 "Red Flag Language" block and Phase 1 "Hallucination Detection Signals"
**REFACTOR**: Verify no new sections created — references added to existing blocks only
**Files**: `plugins/agentic-dev-team/skills/quality-gate-pipeline/SKILL.md`
**Commit**: `feat: add anti-rationalization references to quality gate pipeline`

### Step 3: Create receiving-code-review skill (Slice B)

**Complexity**: standard
**RED**: Verify `skills/receiving-code-review/SKILL.md` does not exist
**GREEN**: Create skill with frontmatter, banned-phrases list, verification-before-implementation gate, YAGNI gate, rationalization table, human vs agent authority distinction, ambiguous finding guidance, concise tone guidance
**REFACTOR**: Verify under 500 tokens, no conflict with Quality Gate Pipeline Phase 3
**Files**: `plugins/agentic-dev-team/skills/receiving-code-review/SKILL.md`
**Commit**: `feat: add receiving-code-review skill for review reception discipline`

### Step 4: Enhance skill authoring with pressure testing and CSO (Slice C — part 1)

**Complexity**: standard
**RED**: Verify current "Apply TDD to skill-writing itself" section lacks pressure testing procedure; verify "Optimize skill descriptions for triggering" lacks a checklist
**GREEN**: Expand both sections in place: pressure testing procedure (4 steps + 3 example scenarios), CSO checklist with pass/fail criteria and 4 description examples (2 good, 2 bad)
**REFACTOR**: Verify total file stays under 1,200 tokens; no parallel sections created
**Files**: `plugins/agentic-dev-team/skills/agent-skill-authoring/SKILL.md`
**Commit**: `feat: add pressure testing and CSO checklist to skill authoring guide`

### Step 5: Update agent-eval for pressure scenario fixtures (Slice C — part 2)

**Complexity**: standard
**RED**: Verify `commands/agent-eval.md` does not mention pressure scenarios
**GREEN**: Add section documenting pressure scenario fixture format and `evals/pressure/` directory. Define fixture schema: skill name, adversarial condition, expected behavior, pass/fail criteria. Add malformed fixture error handling.
**REFACTOR**: Verify eval command description is updated consistently
**Files**: `plugins/agentic-dev-team/commands/agent-eval.md`
**Commit**: `feat: add pressure scenario fixture support to agent-eval`

### Step 6: Create debugging supporting files (Slice D)

**Complexity**: standard
**RED**: Verify `skills/systematic-debugging/` contains only SKILL.md
**GREEN**: Create three supporting files: `root-cause-tracing.md` (backward call-chain analysis), `condition-based-waiting.md` (polling pattern replacing arbitrary waits), `find-polluter.md` (language-agnostic bisection algorithm). Add "Supporting References" section to Phase 2 of main SKILL.md with when-to-load guidance.
**REFACTOR**: Verify each file under 400 tokens; existing 4-phase process unchanged; find-polluter is language-agnostic
**Files**: `plugins/agentic-dev-team/skills/systematic-debugging/root-cause-tracing.md`, `plugins/agentic-dev-team/skills/systematic-debugging/condition-based-waiting.md`, `plugins/agentic-dev-team/skills/systematic-debugging/find-polluter.md`, `plugins/agentic-dev-team/skills/systematic-debugging/SKILL.md`
**Commit**: `feat: add debugging supporting references (root-cause tracing, condition-based waiting, find-polluter)`

### Step 7: Create implementer prompt template (Slice E — part 1)

**Complexity**: complex
**RED**: Verify `prompts/implementer.md` does not exist
**GREEN**: Create full implementer behavioral content: pre-implementation Q&A, TDD enforcement (reference TDD skill), self-review, verification evidence, and markdown status block (DONE/DONE_WITH_CONCERNS/NEEDS_CONTEXT/BLOCKED)
**REFACTOR**: Verify consistent with build.md step 4 expectations and orchestrator references
**Files**: `plugins/agentic-dev-team/prompts/implementer.md`
**Commit**: `feat: create implementer prompt template with status protocol`

### Step 8: Create spec-reviewer and quality-reviewer prompt templates (Slice E — part 2)

**Complexity**: complex
**RED**: Verify `prompts/spec-reviewer.md` and `prompts/quality-reviewer.md` do not exist
**GREEN**: Create both templates with full behavioral content and markdown status blocks. Spec-reviewer: skeptical of implementer claims, reads actual code, binary spec compliance check. Quality-reviewer: uses code-reviewer agent patterns, checks quality after spec compliance passes.
**REFACTOR**: Verify both use the same status block format as implementer
**Files**: `plugins/agentic-dev-team/prompts/spec-reviewer.md`, `plugins/agentic-dev-team/prompts/quality-reviewer.md`
**Commit**: `feat: create spec-reviewer and quality-reviewer prompt templates`

### Step 9: Update plan review templates with status protocol (Slice E — part 3)

**Complexity**: standard
**RED**: Verify existing plan review templates lack `"status"` field in JSON output
**GREEN**: Add `"status"` field to all 4 plan review templates. Mapping: approve with 0 warnings → DONE, approve with 1+ warnings → DONE_WITH_CONCERNS, needs-revision → DONE_WITH_CONCERNS. Add status derivation rules alongside existing verdict rules.
**REFACTOR**: Verify existing verdict field and rules are unchanged — status is additive
**Files**: `plugins/agentic-dev-team/prompts/plan-review-acceptance.md`, `plugins/agentic-dev-team/prompts/plan-review-design.md`, `plugins/agentic-dev-team/prompts/plan-review-ux.md`, `plugins/agentic-dev-team/prompts/plan-review-strategic.md`
**Commit**: `feat: add status protocol to plan review templates`

### Step 10: Update orchestrator with subagent status protocol (Slice E — part 4)

**Complexity**: complex
**RED**: Verify orchestrator lacks "Subagent Status Protocol" section
**GREEN**: Add section defining 4 status codes, orchestrator response table (including unrecognized → BLOCKED), both output formats (markdown block + JSON field), NEEDS_CONTEXT cap at 2 re-dispatches. For DONE_WITH_CONCERNS handling, define three deterministic response branches: (1) concern is non-blocking warning → accept work, log concern; (2) concern is fixable with guidance → re-dispatch with concern text as context; (3) concern requires human judgment → escalate to user. Each branch must have a clear trigger condition.
**REFACTOR**: Verify no conflict with existing Phase 3 inline review section
**Files**: `plugins/agentic-dev-team/agents/orchestrator.md`
**Commit**: `feat: add subagent status protocol to orchestrator`

### Step 11: Update build command for status handling (Slice E — part 5)

**Complexity**: standard
**RED**: Verify build.md step 4 does not handle NEEDS_CONTEXT or BLOCKED
**GREEN**: Update step 4 to check subagent status after dispatch. DONE/DONE_WITH_CONCERNS → continue flow. NEEDS_CONTEXT → gather context, re-dispatch (max 2). BLOCKED → escalate to user.
**REFACTOR**: Verify consistent with orchestrator's status protocol
**Files**: `plugins/agentic-dev-team/commands/build.md`
**Commit**: `feat: add status code handling to build command`

### Step 12: Create testing anti-patterns reference and update TDD skill (Slice F)

**Complexity**: standard
**Ordering**: Step 7 (implementer.md creation) MUST be complete and committed before this step begins. Step 13 MUST NOT have run yet.
**RED**: Verify `skills/test-driven-development/testing-anti-patterns.md` does not exist; verify TDD catch-all line lacks cross-reference; verify `prompts/implementer.md` exists (from Step 7) but lacks testing-anti-patterns reference
**GREEN**: Create testing-anti-patterns.md with 5+ anti-patterns (mock behavior, test-only methods, mocking without understanding, incomplete mocks, integration afterthought). Add "Supporting References" section to TDD SKILL.md. Augment catch-all line with link to `knowledge/anti-rationalization.md`. Add testing-anti-patterns reference to `prompts/implementer.md`.
**REFACTOR**: Verify under 400 tokens; no existing TDD content modified or removed
**Files**: `plugins/agentic-dev-team/skills/test-driven-development/testing-anti-patterns.md`, `plugins/agentic-dev-team/skills/test-driven-development/SKILL.md`, `plugins/agentic-dev-team/prompts/implementer.md`
**Commit**: `feat: add testing anti-patterns reference and TDD cross-references`

### Step 13: Create worktree setup knowledge file and update implementer (Slice G)

**Complexity**: standard
**Ordering**: Step 7 (implementer.md creation) AND Step 12 (testing-anti-patterns implementer ref) MUST be complete before this step. Apply worktree setup on top of existing implementer content.
**RED**: Verify `knowledge/worktree-setup.md` does not exist; verify implementer lacks worktree setup section (but HAS testing-anti-patterns reference from Step 12)
**GREEN**: Create worktree-setup.md with detection table: Node.js (npm/yarn/pnpm/bun by lockfile — first match wins for conflicting lockfiles), Python, Go, Rust, .NET, Java (Maven/Gradle). Add "Worktree Setup" section to implementer.md that runs before RED phase. Update orchestrator Phase 3 to reference worktree setup.
**REFACTOR**: Verify detection uses file presence only; BLOCKED status for baseline/install failures; lockfile priority order is documented
**Files**: `plugins/agentic-dev-team/knowledge/worktree-setup.md`, `plugins/agentic-dev-team/prompts/implementer.md`, `plugins/agentic-dev-team/agents/orchestrator.md`
**Commit**: `feat: add worktree language-specific setup with dependency install and baseline verification`

### Step 14: Windows hooks — run-hook.cmd shim and TMPDIR fixes (Slice H1)

**Complexity**: standard
**RED**: Verify `hooks/run-hook.cmd` does not exist; verify tdd-guard.sh and version-check.sh use hardcoded `/tmp/`
**GREEN**: Create `run-hook.cmd` (~20 lines) that locates bash via (1) PATH, (2) Git for Windows default `C:\Program Files\Git\bin\bash.exe`, (3) WSL. Passes stdin, args, and exit codes. Create `install.ps1` checking bash, jq, git with install instructions. Fix TMPDIR in tdd-guard.sh and version-check.sh: `${TMPDIR:-${TEMP:-/tmp}}`. Update `settings.json` to document Windows hook invocation pattern.
**REFACTOR**: Verify all 9 hooks unchanged on macOS/Linux; shim error message is clear
**Files**: `plugins/agentic-dev-team/hooks/run-hook.cmd`, `plugins/agentic-dev-team/install.ps1`, `plugins/agentic-dev-team/hooks/tdd-guard.sh`, `plugins/agentic-dev-team/hooks/version-check.sh`, `plugins/agentic-dev-team/settings.json`
**Commit**: `feat: add Windows hooks support with bash shim and TMPDIR fixes`

### Step 15: Gemini CLI extension manifest and context file (Slice H2)

**Complexity**: standard
**RED**: Verify `gemini-extension.json` and `GEMINI.md` do not exist
**GREEN**: Create `gemini-extension.json` with name, version, description, contextFileName pointing to GEMINI.md. Create `GEMINI.md` adapted from CLAUDE.md — include plugin philosophy, team organization, skill registry, but strip all Claude Code-specific features (Agent tool, allowed-tools, hooks, isolation: "worktree", model routing). Add capability limitations section. Create `hooks/hooks-gemini.json` for compatible hooks. Create 5 TOML commands in `commands-gemini/`: code-review, plan, build, help, browse.
**REFACTOR**: Verify GEMINI.md has no Claude Code references; skills directory is reused not forked
**Files**: `plugins/agentic-dev-team/gemini-extension.json`, `plugins/agentic-dev-team/GEMINI.md`, `plugins/agentic-dev-team/hooks/hooks-gemini.json`, `plugins/agentic-dev-team/commands-gemini/code-review.toml`, `plugins/agentic-dev-team/commands-gemini/plan.toml`, `plugins/agentic-dev-team/commands-gemini/build.toml`, `plugins/agentic-dev-team/commands-gemini/help.toml`, `plugins/agentic-dev-team/commands-gemini/browse.toml`
**Commit**: `feat: add Gemini CLI extension support with manifest, context file, and TOML commands`

### Step 16: OpenAI Codex configuration and install guide (Slice H3)

**Complexity**: standard
**RED**: Verify `AGENTS.md`, `.codex/config.toml`, `.codex/hooks.json`, and `CODEX-INSTALL.md` do not exist
**GREEN**: Create `AGENTS.md` adapted from CLAUDE.md — include plugin philosophy, team org, skill registry, strip Claude Code features, add capability limitations, note subagent dispatch requires explicit request. Verify under 32 KiB. Create `.codex/config.toml` with hooks enabled. Create `.codex/hooks.json` for compatible hooks. Create `CODEX-INSTALL.md` with step-by-step: skill symlinks to `.agents/skills/`, AGENTS.md placement, config.toml setup.
**REFACTOR**: Verify AGENTS.md under 32 KiB; skills not forked; limitations clearly documented
**Files**: `plugins/agentic-dev-team/AGENTS.md`, `plugins/agentic-dev-team/.codex/config.toml`, `plugins/agentic-dev-team/.codex/hooks.json`, `plugins/agentic-dev-team/CODEX-INSTALL.md`
**Commit**: `feat: add OpenAI Codex CLI support with AGENTS.md, config, and install guide`

### Step 17: Update shared registries and CLAUDE.md (all slices)

**Complexity**: standard
**RED**: Verify `knowledge/agent-registry.md` is missing new entries; verify CLAUDE.md skill count is stale
**GREEN**: Update `knowledge/agent-registry.md` with: anti-rationalization.md (knowledge), receiving-code-review (skill), testing-anti-patterns.md (supporting file), 3 debugging supporting files, worktree-setup.md (knowledge), 3 new prompt templates. Update `CLAUDE.md`: skill count (31→32), skills-by-phase table (Review: add receiving-code-review), Multi-Agent Collaboration Protocol (reference status protocol), subagent prompt template count (4→7).
**REFACTOR**: Verify all registry entries have correct file paths and token estimates
**Files**: `plugins/agentic-dev-team/knowledge/agent-registry.md`, `plugins/agentic-dev-team/CLAUDE.md`
**Commit**: `docs: update agent registry and CLAUDE.md with all new components`

### Step 18: Cross-reference validation pass

**Complexity**: trivial
**RED**: Check all markdown links between files resolve to existing files
**GREEN**: Fix any broken links found during validation
**REFACTOR**: None needed
**Files**: All modified files (read-only validation, edits only if broken links found)
**Commit**: `fix: resolve broken cross-references` (only if fixes needed)

## Complexity Classification

| Rating | Criteria | Review depth |
|--------|----------|--------------|
| `trivial` | Single-file rename, config change, typo fix, documentation-only | Skip inline review; covered by final `/code-review` |
| `standard` | New function, test, module, or behavioral change within existing patterns | Spec-compliance + relevant quality agents |
| `complex` | Architectural change, security-sensitive, cross-cutting concern, new abstraction | Full agent suite including opus-tier agents |

## Important: Shared File Update Policy

Steps 3, 6, and 12 each have spec-level acceptance criteria that mention updating `CLAUDE.md` or `knowledge/agent-registry.md`. **All registry and CLAUDE.md updates are deferred to Step 17.** Do NOT modify these files in earlier steps — Step 17 handles all shared-file updates in one atomic commit to avoid merge conflicts.

## Pre-PR Quality Gate

- [ ] All acceptance criteria from spec met (per-slice)
- [ ] Token budgets verified for all constrained files
- [ ] Cross-references validated (all markdown links resolve)
- [ ] No existing hook behavior changed on macOS/Linux
- [ ] GEMINI.md and AGENTS.md skill registries match CLAUDE.md skill count
- [ ] `gemini-extension.json` passes `python3 -m json.tool`; `.codex/config.toml` passes TOML parser
- [ ] `/code-review` passes
- [ ] Documentation updated (agent-registry.md, CLAUDE.md)

## Risks & Open Questions

| Risk | Mitigation |
|------|-----------|
| Token budget overrun on constrained files | Check token count after each file creation using word count as proxy (~0.75 tokens/word) |
| Implementer.md becomes too large with worktree setup + testing references + status protocol | Keep each section focused; worktree setup references knowledge file rather than inlining the table |
| GEMINI.md and AGENTS.md may reference capabilities that don't translate | Explicit "Capability Limitations" section in each platform context file |
| Gemini CLI TOML command format may not match expectations | Use superpowers' TOML commands as reference; test with `gemini extensions link .` if available |
| Codex hooks.json format is not well-documented | Create minimal hooks.json; document that hooks are experimental on Codex |
| `run-hook.cmd` may have edge cases with Windows path handling | Keep shim minimal (~20 lines); rely on Git for Windows bash which handles path translation |
| Multiple slices modify orchestrator.md and implementer.md | Implement E (creates files) → F (adds references) → G (adds worktree) in strict order |

## Parallelization Strategy

Steps that can run concurrently (no file conflicts):

**Batch 1** (independent): Steps 1-2 (A), Step 3 (B), Steps 4-5 (C), Step 6 (D), Step 14 (H1)
**Batch 2** (after Batch 1): Steps 7-11 (E — sequential internally)
**Batch 3** (after Steps 1-2 and 7, and Step 12 must commit implementer.md changes first): Step 12 (F — depends on A + E's implementer.md)
**Batch 4** (after Step 12 commits implementer.md changes): Step 13 (G — depends on E + F's implementer.md)
**Batch 5** (independent): Step 15 (H2), Step 16 (H3)
**Final**: Step 17 (registries), Step 18 (validation)

## Plan Review Summary

Four plan review personas evaluated this plan. All blocker issues have been addressed in this revision.

### Acceptance Test Critic — needs-revision → resolved
**Blockers addressed**:
1. "No regression" criterion rewritten with binary-verifiable checks (hook exit codes, frontmatter parse)
2. "Structurally valid" criterion replaced with parser commands (`python3 -m json.tool`, TOML parser)
3. DONE_WITH_CONCERNS scenario: Step 10 now specifies three deterministic response branches with trigger conditions

**Warnings noted**: Token counting method specified (word × 1.35). Terminology check made explicit with grep command. Missing scenarios for registry updates, token budgets, malformed status blocks, conflicting lockfiles, settings.json, TOML validity, and CSO examples noted — these are validation checks within implementation steps, not separate BDD scenarios.

### Design & Architecture Critic — approve
**Key observations**: Dependency graph is acyclic and ordering is correct. Token budgets per file are disciplined documentation design. Platform context file drift (GEMINI.md, AGENTS.md vs CLAUDE.md) is the main structural concern — addressed with Pre-PR Quality Gate check.
**Actions taken**: Explicit ordering guards added to Steps 12 and 13. Commands-gemini/ convention documented in GEMINI.md (Step 15).

### Strategic Critic — approve
**Key suggestion**: Consider splitting H1-H3 into a follow-on PR since Gemini TOML and Codex hooks.json formats are unverified. Core slices A-G have high confidence.
**Decision**: Proceed as single plan but H1-H3 are implemented last (Steps 14-16) and can be dropped if format issues arise. The plan's risk register already flags both format risks.
**Actions taken**: Added CLAUDE.md deferral notes to prevent shared-file conflicts. Serialization of Steps 7-13 made explicit.

### UX Critic — approve (self-skipped)
No user-facing changes in this plan.
