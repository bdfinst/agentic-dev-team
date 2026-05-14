# Plan: Agent Create Skill

**Created**: 2026-05-13
**Branch**: feat/semantic-duplication-scan
**Status**: implemented

## Goal

Add an `agent-create` skill that produces new Claude Code sub-agent files following the official sub-agent schema, enforcing token-efficiency budgets (≤ 40 lines review body, ≤ 75 lines team body), guiding tool selection, conflict detection, and registry updates. Update `/agent-add` to delegate to this skill and extend it from review-only to all agent types.

The skill is user-invocable directly (Skill tool or natural language) and listed in the Skills Registry only — no new command file. `/agent-add` remains the user-facing slash command; this skill is its implementation.

**Relationship to `agent-skill-authoring`**: that skill is a *reference* (meta-patterns, anti-patterns, registration checklist). This skill is *procedural* — it automates the creation workflow. `agent-create` references `agent-skill-authoring` for conventions and anti-patterns; it does not replace it.

**Out of scope**: token-efficiency enforcement for skill files and command files. Distinct artifact types tracked separately.

## Acceptance Criteria

**"Body" definition**: all content after and excluding the closing `---` of the YAML frontmatter block, including blank lines. The limit is inclusive (40 lines is permitted; 41 is not).

- [ ] Generated agent file passes `/agent-audit` structural compliance checks
- [ ] Review agent body is ≤ 40 lines
- [ ] Team agent body is ≤ 75 lines
- [ ] No line in the body matches `^You are an? ` (case-insensitive, per-line)
- [ ] Body does not contain the frontmatter `description` value verbatim. **Normalization**: collapse all runs of whitespace (space, tab, newline) to a single ASCII space and trim both ends of each string before the substring check.
- [ ] Body contains none of: `your-agent-name`, `One-sentence description`, `# Agent Name`
- [ ] No bullet point spans more than two lines
- [ ] When tools not provided, skill emits exact two-line prompt before proceeding: line 1 `Which tools does this agent need?`; line 2 `  Read, Grep, Glob (read-only) | add Edit, Write (file changes) | add Bash (shell) | add Skill (skill invocation) | add Agent (spawn subagents)`
- [ ] When `hooks`, `mcpServers`, or `permissionMode` requested, skill emits exact warning: `hooks/mcpServers/permissionMode are silently ignored for plugin agents — move the file to .claude/agents/ if you need them to take effect`; field absent unless user confirms
- [ ] Existing agent path not overwritten without confirmation; on decline skill reports path + description and stops
- [ ] Name not matching `^[a-z][a-z0-9-]*$` rejected with rule stated and kebab-case correction suggested; no file written
- [ ] When body exceeds line budget, skill emits "Body is N lines — X lines over the Y-line budget for Z agents", followed by a list of removed/collapsed items each prefixed with `- ` (dash space), followed by the exact prompt `Approve this trim? (yes/no)` — all before any file is written. On "no": skill emits "Options: (a) reduce spec scope and regenerate, (b) accept N lines and proceed without trimming" and waits.
- [ ] When `/agent-audit` fails, skill emits the raw `/agent-audit` output verbatim, then emits "All your inputs are preserved.", then emits the exact menu `(a) auto-correct and re-validate  (b) cancel` and waits. On second failure after auto-correct: surfaces the same menu again rather than stopping silently.
- [ ] After success, `knowledge/agent-registry.md` contains a new row in the table whose heading contains "Review Agents" (review type) or "Team Agents" (team type). Row format: `| <name> | <file-path> | <tier-label> | <description> |`
- [ ] After success, `plugins/agentic-dev-team/CLAUDE.md` contains a new row in the table whose heading contains "Review Agents" (review type) or "Team Agents" (team type). If the target heading is absent from CLAUDE.md, the skill emits an error identifying the missing heading and stops without modifying the file.

## User-Facing Behavior

```gherkin
Feature: Agent Create Skill

  Background:
    Given the agentic-dev-team plugin is installed

  Scenario: Creates a valid agent file from name and description
    Given the user provides name "import-cycle-review" and description "Detects circular import dependencies"
    And tools: Read, Grep, Glob
    When the agent-create skill runs
    Then a file is written to plugins/agentic-dev-team/agents/import-cycle-review.md
    And the frontmatter name is "import-cycle-review"
    And the frontmatter description is "Detects circular import dependencies"
    And the model field is "haiku"
    And running /agent-audit against the file returns no errors

  Scenario: Review agent body stays within the line budget
    Given the agent type is "review"
    When the skill generates the agent body
    Then the body line count is 40 or fewer
    And the body contains an Output JSON block
    And the body contains a "## Skip" section
    And the body contains a "## Detect" section

  Scenario: Review agent body does not include team agent sections
    Given the agent type is "review"
    When the skill generates the agent body
    Then the body does not contain a "## Responsibilities" section

  Scenario: Review agent body at exactly 40 lines passes the budget without trim prompt
    Given a review agent spec that generates exactly 40 lines of body
    When the skill runs the budget check
    Then no message matching "Body is N lines" is emitted
    And no "Approve this trim?" prompt is shown
    And the write gate proceeds normally

  Scenario: Review agent body at 41 lines triggers visible trim before write gate
    Given a review agent spec that would generate 41 lines of body
    When the skill generates the body
    Then the skill emits the exact string: "Body is 41 lines — 1 line over the 40-line budget for review agents"
    And emits a list of removed/collapsed items each prefixed with "- "
    And emits the exact prompt: "Approve this trim? (yes/no)"
    And no file is written until the user answers "yes"

  Scenario: Team agent body at exactly 75 lines passes the budget without trim prompt
    Given a team agent spec that generates exactly 75 lines of body
    When the skill runs the budget check
    Then no message matching "Body is N lines" is emitted
    And no "Approve this trim?" prompt is shown
    And the write gate proceeds normally

  Scenario: Team agent body at 76 lines triggers visible trim before write gate
    Given a team agent spec that would generate 76 lines of body
    When the skill generates the body
    Then the skill emits the exact string: "Body is 76 lines — 1 line over the 75-line budget for team agents"
    And emits a list of removed/collapsed items each prefixed with "- "
    And emits the exact prompt: "Approve this trim? (yes/no)"
    And no file is written until the user answers "yes"

  Scenario: User declines trim — skill offers two follow-up options
    Given a review agent spec that would generate 44 lines of body
    And the skill has emitted the trim list and "Approve this trim? (yes/no)"
    And the user answers "no"
    When the skill processes the decline
    Then the skill emits: "Options: (a) reduce spec scope and regenerate, (b) accept 44 lines and proceed without trimming"
    And waits for the user's choice
    And no file is written until the user chooses

  Scenario: Team agent body stays within the line budget
    Given the agent type is "team"
    When the skill generates the agent body
    Then the body line count is 75 or fewer
    And the body contains a "## Responsibilities" section
    And the body does not contain an Output JSON block
    And the body does not contain a "## Skip" section
    And the body does not contain a "## Detect" section

  Scenario: Body contains no token-wasting patterns
    Given the skill has generated any agent body
    Then no line matches "^You are a" or "^You are an" (case-insensitive)
    And the body does not contain the frontmatter description value verbatim
    And the body contains none of: "your-agent-name", "One-sentence description", "# Agent Name"
    And no bullet point spans more than two lines

  Scenario: User is prompted for tools when none are provided
    Given the user has not specified tools
    When the skill processes the request
    Then the skill emits exactly:
      """
      Which tools does this agent need?
        Read, Grep, Glob (read-only) | add Edit, Write (file changes) | add Bash (shell) | add Skill (skill invocation) | add Agent (spawn subagents)
      """
    And does not proceed until the user responds

  Scenario: Plugin-unsupported fields are absent by default
    Given the user has not requested hooks, mcpServers, or permissionMode
    When the skill generates the frontmatter
    Then hooks, mcpServers, and permissionMode are each absent

  Scenario: Plugin-unsupported field emits exact warning
    Given the user requests the "hooks" field
    When the skill processes the request
    Then the skill emits: "hooks/mcpServers/permissionMode are silently ignored for plugin agents — move the file to .claude/agents/ if you need them to take effect"
    And hooks is absent if the user declines
    And hooks is present if the user confirms

  Scenario: Skill refuses to overwrite silently
    Given plugins/agentic-dev-team/agents/import-cycle-review.md exists with description "Old version"
    When the user invokes the skill with name "import-cycle-review"
    Then the skill reports: "plugins/agentic-dev-team/agents/import-cycle-review.md already exists (description: Old version)"
    And asks "Overwrite? (yes/no)"
    And no file is written until the user answers "yes"
    And if the user answers "no" the skill stops with no changes

  Scenario: Skill rejects a name with uppercase letters
    Given the user provides name "ImportCycleReview"
    When the skill processes the name
    Then it emits: "Name must match ^[a-z][a-z0-9-]*$ — use lowercase letters, digits, and hyphens only"
    And suggests: "Did you mean: import-cycle-review?"
    And no file is written

  Scenario: Skill rejects a name starting with a digit
    Given the user provides name "3d-renderer-review"
    When the skill processes the name
    Then it rejects the name with the rule and a suggested correction
    And no file is written

  Scenario: Duplicate scope is flagged before writing
    Given "dependency-review" has description "Detects circular dependencies between modules"
    And the user creates an agent with description "Detect circular import dependencies"
    When the skill scans for scope overlap
    Then it emits: "Possible overlap with dependency-review: both detect circular dependency patterns. Continue anyway? (yes/no)"
    And does not write until the user responds
    And if the user responds "yes" the skill proceeds to generation
    And if the user responds "no" the skill stops with no changes

  Scenario: Validation failure preserves inputs and offers recovery
    Given the generated file fails /agent-audit (e.g. missing description)
    When the validation gate runs
    Then the skill emits the raw /agent-audit output verbatim
    And emits: "All your inputs are preserved."
    And emits the exact menu: "(a) auto-correct and re-validate  (b) cancel"
    And does not write the file

  Scenario: Second auto-correct failure resurfaces the menu
    Given auto-correct was chosen after a validation failure
    And the auto-corrected file still fails /agent-audit
    When the second validation attempt fails
    Then the skill emits the new /agent-audit output
    And emits "All your inputs are preserved."
    And emits the exact menu "(a) auto-correct and re-validate  (b) cancel" again
    And does not write the file

  Scenario: Registry updated with correct row after review agent creation
    Given "import-cycle-review" (review type) is written successfully
    When the skill completes
    Then knowledge/agent-registry.md has a new row with name, file path, model tier, and description
    And no row was added for import-cycle-review to the Team Agents section

  Scenario: CLAUDE.md updated in correct table for each agent type
    Given a review agent "import-cycle-review" is written successfully
    Then CLAUDE.md has a new row in the Review Agents table for import-cycle-review
    And the Team Agents table is unchanged

    Given a team agent "schema-planner" is written successfully
    Then CLAUDE.md has a new row in the Team Agents table for schema-planner
    And the Review Agents table is unchanged
```

## Steps

### Step 0: Spike — verify /agent-audit accepts a single file path argument

**Complexity**: trivial
**RED**: No fixture — investigation gate.
**GREEN**: Run `/agent-audit plugins/agentic-dev-team/agents/domain-review.md` and observe output.
  - **Outcome A (pass)**: agent-audit accepts a single file path and returns structured output → document exact invocation; use in Step 7 GREEN as written.
  - **Outcome B (fail)**: agent-audit does not accept a file path or requires a directory → Step 7 must be revised: write generated content to `.claude/staging/<name>.md`, run `/agent-audit .claude/staging/`, check result, delete staging file. Update Step 7 GREEN before implementing it.
  - **Outcome C (command not available)**: agent-audit is unavailable in the target context → AC 1 must be reclassified to use `claude-setup-review` directly against the generated file; document this deviation and update Step 7 accordingly.

Spike result must be recorded in the Risks section before Step 1 begins. Implementation must not begin until Step 0 is resolved.
**REFACTOR**: None.
**Files**: update Risks section of this plan with finding; update Step 7 GREEN section
**Commit**: none — spike only, no code

---

### Step 1: Scaffold skill with input parsing, name validation, and type-based defaults

**Complexity**: standard
**RED**: Create eval fixtures:
  - `evals/fixtures/aca-valid-name/README.md` — name `code-quality-review`, type `review`, description given. Expected: passes validation, proceeds.
  - `evals/fixtures/aca-invalid-name/README.md` — name `CodeQuality`. Expected: emits exact error + suggestion `code-quality`; no file. Additional cases: `3d-review` (digit start → rejected), `my--review` (double hyphen → accepted per regex).
**GREEN**: Create `plugins/agentic-dev-team/skills/agent-create/SKILL.md`:
  - Frontmatter: `name: agent-create`, description, `role: worker`, `user-invocable: true`
  - Opening note: `agent-create` automates the procedure; reference `agent-skill-authoring` for conventions and anti-patterns
  - Parse: name, type (review|team), description, tools, model
  - **Name validation (hard gate)**: must match `^[a-z][a-z0-9-]*$`; emit exact error + kebab-case suggestion; exit immediately, no file written
  - **Type detection**: infer from keywords if absent ("review/audit/check/validate/detect/scan" → review; "engineer/architect/manager/writer/planner/designer" → team); ask if ambiguous
  - **Defaults**: review → `tools: Read, Grep, Glob`, `model: haiku`; team → `model: sonnet`
**REFACTOR**: Verify edge cases: empty string, all-digit, leading hyphen.
**Files**: `plugins/agentic-dev-team/skills/agent-create/SKILL.md`, eval fixtures
**Commit**: `feat: scaffold agent-create skill with input parsing and name validation`

---

### Step 2: Add tool-selection prompt

**Complexity**: standard
**RED**: Create `evals/fixtures/aca-no-tools/README.md` — no tools provided. Expected: exact two-line prompt emitted before any generation. Failure: any other prompt text or proceeding without prompting.
**GREEN**: Add to SKILL.md: if tools not provided, emit (pinned verbatim):
```
Which tools does this agent need?
  Read, Grep, Glob (read-only) | add Edit, Write (file changes) | add Bash (shell) | add Skill (skill invocation) | add Agent (spawn subagents)
```
Wait for response. If tools provided: warn on unrecognised names (not error).
**REFACTOR**: None.
**Files**: `plugins/agentic-dev-team/skills/agent-create/SKILL.md`, `evals/fixtures/aca-no-tools/README.md`
**Commit**: `feat: add tool-selection prompt to agent-create skill`

---

### Step 3: Add conflict detection, scope-overlap check, and frontmatter generation

**Complexity**: standard
**RED**: Create eval fixtures:
  - `evals/fixtures/aca-existing-file/README.md` — file exists. Expected: exact format "…already exists (description: …)" + "Overwrite? (yes/no)"; no write without "yes".
  - `evals/fixtures/aca-scope-overlap/README.md` — overlapping descriptions. Expected exact format: "Possible overlap with <agent-name>: <one-sentence description of shared concept>. Continue anyway? (yes/no)" where `<agent-name>` is the registry name of the overlapping agent.
**GREEN**: Add to SKILL.md:
  - **Conflict**: glob `agents/<name>.md`; if exists, read description, emit exact format, require "yes"; on "no" stop with no changes
  - **Scope overlap** (review): compare new description against existing `description` + first 20 lines of `## Detect`; report if ≥ 60% topical overlap; advisory only
  - **Scope overlap** (team): compare descriptions only
  - **Frontmatter generation**: emit only official fields; apply defaults; omit fields with no value
**REFACTOR**: None.
**Files**: `plugins/agentic-dev-team/skills/agent-create/SKILL.md`, eval fixtures
**Commit**: `feat: add conflict detection, scope-overlap, and frontmatter generation`

---

### Step 4: Add plugin-unsupported field handling

**Complexity**: standard
**RED**: Create `evals/fixtures/aca-plugin-unsupported-field/README.md` — user requests `hooks`. Expected: exact warning string; field absent on decline; field present on confirm.
**GREEN**: Add to SKILL.md: if `hooks`/`mcpServers`/`permissionMode` requested, emit pinned warning:
```
hooks/mcpServers/permissionMode are silently ignored for plugin agents — move the file to .claude/agents/ if you need them to take effect
```
Include field only on confirm; omit on decline.
**REFACTOR**: None.
**Files**: `plugins/agentic-dev-team/skills/agent-create/SKILL.md`, eval fixture
**Commit**: `feat: add plugin-unsupported field handling`

---

### Step 5: Add review agent body generation with token-efficiency rules

**Complexity**: complex
**RED**: Create eval fixtures:
  - `evals/fixtures/aca-review-body-valid/README.md` — description "Detects unused import statements". Expected: body ≤ 40 lines; Output JSON block, `## Skip`, `## Detect`, `## Ignore` present; no "You are a…" line; no placeholder text.
  - `evals/fixtures/aca-review-body-over-budget/README.md` — spec requiring 45 lines. Expected: trim message shown; items listed with `- ` prefix; exact prompt "Approve this trim? (yes/no)" before any write.
  - `evals/fixtures/aca-review-preamble-rejected/README.md` — describes a generation that opens "You are an expert reviewer". Expected: pattern must not appear in output.
**GREEN**: Add review body generation to SKILL.md:
  - Required order: `# Title`, Output JSON block (exact schema), Status/Severity/Confidence one-liners, `## Skip`, `## Detect`, `## Ignore`
  - Anti-patterns: no `^You are an?` opener; title ≠ description verbatim; detect rules ≤ 2 lines; knowledge ref = 1 line; Skip = 1–3 bullets; Ignore = 1 sentence
  - **Budget gate**: if > 40 lines, emit exact string "Body is N lines — X lines over the 40-line budget for review agents"; emit list of removed/collapsed items prefixed with `- `; emit exact prompt "Approve this trim? (yes/no)"; if "yes": trim and continue to write gate; if "no": emit "Options: (a) reduce spec scope and regenerate, (b) accept N lines and proceed without trimming" and wait; on (a): return to generation; on (b): proceed to write gate with untrimmed body
  - Trimmable content (in priority order): blank separator lines between sections, wordy multi-line bullets collapsed to one line; **protected** (never trim): Output JSON block, section headings (`## Skip`, `## Detect`, `## Ignore`), the single required bullet under each section
  - Present full draft before write
**REFACTOR**: Verify trim never removes Output JSON block, section headers, or required sections.
**Files**: `plugins/agentic-dev-team/skills/agent-create/SKILL.md`, eval fixtures
**Commit**: `feat: add review agent body generation with token-efficiency rules`

---

### Step 6: Add team agent body generation with token-efficiency rules

**Complexity**: standard
**RED**: Create `evals/fixtures/aca-team-body-valid/README.md` — description "Plans database schema migrations". Expected: body ≤ 75 lines; `## Responsibilities` present; no Output JSON block, no `## Skip`, `## Detect`, `## Ignore`; no "You are a…".
**GREEN**: Add team body generation to SKILL.md:
  - Required: `# Title`, `## Responsibilities`; optional: `## Output Discipline`, `## Skills`, `## Process`
  - Same anti-pattern rules; same trim-with-diff gate at 75 lines
  - Responsibilities: ≤ 2 lines each, action-oriented; Skills section: name + 1-line invocation context
**REFACTOR**: None.
**Files**: `plugins/agentic-dev-team/skills/agent-create/SKILL.md`, eval fixture
**Commit**: `feat: add team agent body generation with token-efficiency rules`

---

### Step 7: Add /agent-audit validation gate with recovery flow

**Complexity**: standard  
*(Update the GREEN section with the confirmed invocation from Step 0 before implementing)*
**RED**: Create `evals/fixtures/aca-validation-failure/README.md` — generated agent missing `description`. Expected: raw /agent-audit output emitted verbatim; then "All your inputs are preserved."; then exact menu "(a) auto-correct and re-validate  (b) cancel" offered; no file written.
**GREEN**: Add to SKILL.md:
  - Run `/agent-audit <name>` (or Step 0's confirmed fallback) against generated content
  - On errors: emit raw `/agent-audit` output verbatim; emit "All your inputs are preserved."; emit exact menu "(a) auto-correct and re-validate  (b) cancel"; on cancel no changes; on auto-correct: fix issues, re-run validation, then:
    - If second attempt passes: proceed to write gate
    - If second attempt fails: emit new `/agent-audit` output verbatim; emit "All your inputs are preserved."; emit the same menu again (no silent stop)
  - On pass: present full file to user; write on confirmation
**REFACTOR**: None.
**Files**: `plugins/agentic-dev-team/skills/agent-create/SKILL.md`, eval fixture
**Commit**: `feat: add /agent-audit validation gate with recovery flow`

---

### Step 8: Add registry and CLAUDE.md update procedures

**Complexity**: standard
**RED**: Create `evals/fixtures/aca-registry-update/README.md` — review agent and team agent each created. Expected per type: correct registry table updated, correct CLAUDE.md table updated, other table unchanged.
**GREEN**: Add to SKILL.md:
  - Model → tier: haiku → small, sonnet → mid, opus → frontier
  - Before appending: locate the target table in each file by searching for a heading that contains "Review Agents" or "Team Agents" (case-insensitive). If the heading is not found, emit an error: "Cannot update <file>: heading containing '<type> Agents' not found. Update manually." and stop without modifying the file.
  - Review agents: append row to `knowledge/agent-registry.md` Review Agents table; append row to `CLAUDE.md` Review Agents table. Row format: `| <name> | <file-path> | <tier-label> | <description> |`
  - Team agents: append row to `knowledge/agent-registry.md` Team Agents table; append row to `CLAUDE.md` Team Agents table. Same row format.
  - Append-only; never edit existing rows; confirm both updates in completion report
**REFACTOR**: None.
**Files**: `plugins/agentic-dev-team/skills/agent-create/SKILL.md`, eval fixture
**Commit**: `feat: add registry and CLAUDE.md update procedures`

---

### Step 9: Update agent-add command to delegate to agent-create skill

**Complexity**: standard
**RED**: Confirm `commands/agent-add.md` has hardcoded inline template scoped to review agents only. Invoking it with a team-agent description currently produces review-agent output — this is the failure.
**GREEN**: Rewrite `commands/agent-add.md`:
  - Delegate all implementation to `skills/agent-create/SKILL.md`
  - Update description to cover both agent types
  - Add `--type review|team` to argument-hint
  - Remove hardcoded inline template (now in the skill)
  - Preserve `--name`, `--tier`, `--context`, `--lang`, `--dry` as pass-throughs
**REFACTOR**: None.
**Files**: `plugins/agentic-dev-team/commands/agent-add.md`
**Commit**: `refactor(agent-add): delegate to agent-create skill, extend to team agents`

---

### Step 10: Register skill in Skills Registry

**Complexity**: trivial
**RED**: `/agent-audit` flags missing Skills Registry entry.
**GREEN**: Append to `knowledge/agent-registry.md` **Skills Registry** table (not Slash Commands):
  `| Agent Create | skills/agent-create/SKILL.md | ~TBD | Orchestrator, Software Engineer, all team agents |`
  Update `~TBD` after Steps 1–9 complete.
  Do NOT add to Slash Commands table — no command file exists; skill is invoked via agent-add or natural language.
**REFACTOR**: None.
**Files**: `plugins/agentic-dev-team/knowledge/agent-registry.md`
**Commit**: `docs: register agent-create skill in Skills Registry`

---

## Complexity Classification

| Rating | Criteria | Review depth |
|--------|----------|--------------|
| `trivial` | Single-file change, config, docs-only | Skip inline review |
| `standard` | New behavior within existing patterns | Spec-compliance + quality agents |
| `complex` | Cross-cutting concern, new abstraction | Full agent suite |

## Pre-PR Quality Gate

- [ ] Step 0 spike result documented; Step 7 GREEN updated with confirmed invocation
- [ ] All eval fixtures pass manual validation
- [ ] `/agent-audit` passes on all new and modified files
- [ ] `/code-review` passes on all files
- [ ] agent-create token count estimated and added to registry entry
- [ ] `/agent-add` tested end-to-end for review and team agent creation

## Risks & Open Questions

- **agent-audit interface** (resolved — Outcome A): `/agent-audit` accepts a single file path argument directly ("A specific file path: audit that file only"). Step 7 uses `/agent-audit plugins/agentic-dev-team/agents/<name>.md`. No staging path needed.
- **Scope-overlap reliability**: 60% overlap threshold is LLM judgment; false positives are advisory-only (user can continue), so this is a UX inconvenience, not a blocker.
- **Trim correctness**: Trim must never remove required structural sections. Trimmable = blank separators, wordy bullets. Protected = Output JSON block, section headers (`## Skip`, `## Detect`, `## Ignore`, `## Responsibilities`). If budget cannot be met without removing protected content, surface to user.
- **Type inference**: Keyword inference is a suggestion with correction opportunity; never applied silently.

## Plan Review Summary

Four reviewers ran; all returned `needs-revision` on the first draft. Key changes in this revision:

| Reviewer | Top Blocker | Resolution |
|----------|-------------|-----------|
| Acceptance Test Critic | agent-eval AC unverifiable; body undefined; exact strings missing | Use `/agent-audit` instead; define body; pin all exact strings; split registry AC |
| Design Critic | Overlap with agent-skill-authoring; command file contradiction | Relationship clarified (reference vs procedure); no command file, Skills Registry only |
| UX Critic | Trim invisible before write gate; validation failure loses inputs | Trim shows diff before gate; validation failure preserves inputs + offers recovery |
| Strategic Critic | Same agent-skill-authoring overlap; scope boundary unstated | Relationship stated; out-of-scope (skills/commands) explicitly named |

## Plan Review Summary

Four reviewers ran across four revision cycles. All four passed on the final revision.

| Reviewer | Verdict | Resolution across passes |
|----------|---------|--------------------------|
| Acceptance Test Critic | **approve** | 7 blockers (pass 1) → 4 blockers (pass 2) → 1 blocker + 3 step issues (pass 3) → approved (pass 4). Key resolutions: /agent-audit replaces agent-eval; body definition pinned; all exact strings defined; trim diff format; scope-overlap message pinned; team boundary scenarios added. |
| Design & Architecture Critic | **approve** (pass 2) | agent-skill-authoring relationship clarified (reference vs procedure); command file contradiction resolved (Skills Registry only). |
| UX Critic | **approve** (pass 2) | Trim visibility: diff shown before write gate; validation failure: inputs preserved + exact recovery menu. |
| Strategic Critic | **approve** (pass 1) | agent-skill-authoring overlap, scope boundary, and incremental delivery noted; addressed in plan goal section. |

**One remaining warning**: Step 6 has no over-budget team-body eval fixture. The shared trim logic is covered by Step 5's fixture and both AC + scenarios are present; this is a gap for independent team-path eval coverage, not a correctness issue.
