# Spec: Create Agent

## Intent Description

This feature adds a `agent-create` skill that produces new Claude Code sub-agent files following the official sub-agent schema (from `templates/agents/agent-template.md`) and enforcing token-efficiency rules. It handles both **review agents** (narrow scope, JSON output, read-only tools, runs on every code-review pass) and **team agents** (broader scope, prose output, action tools, loaded on demand).

Token efficiency is a first-class constraint. Review agents are loaded 8–10 simultaneously on every `/code-review` run; at ~12 tokens per line, a 40-line body costs ~480 tokens — exceeding this multiplied across ten agents adds thousands of tokens of overhead per review. Team agents are loaded one at a time and allow up to 75 lines. The skill enforces these budgets at generation time and prevents the patterns that inflate them: role-playing preambles, description restatement, prose where bullets suffice, and template sections copied over when inapplicable.

The skill is user-invocable directly. `/agent-add` is updated to delegate to it, extending its scope from review-only to all agent types. No new command file is created — the skill is the interface.

## User-Facing Behavior

```gherkin
Feature: Create Agent Skill

  Background:
    Given the agentic-dev-team plugin is installed

  Scenario: Creates a valid agent file from name and description
    Given the user provides an agent name and description
    When the agent-create skill runs
    Then a file is written to plugins/agentic-dev-team/agents/<name>.md
    And the frontmatter name matches ^[a-z][a-z0-9-]*$
    And the frontmatter description is non-empty
    And the model field is one of: haiku, sonnet, opus, inherit
    And running agent-eval with claude-setup-review against the file returns status "pass"

  Scenario: Review agent body stays within the line budget
    Given the agent type is "review"
    When the skill generates the agent body
    Then the body is 40 lines or fewer
    And the body contains an Output JSON block
    And the body contains a Skip section
    And the body contains a Detect section

  Scenario: Team agent body stays within the line budget
    Given the agent type is "team"
    When the skill generates the agent body
    Then the body is 75 lines or fewer
    And the body contains a Responsibilities section
    And the body does not contain an Output JSON block

  Scenario: Body contains no token-wasting patterns
    Given the skill has generated any agent body
    Then the body does not begin with "You are a" or "You are an"
    And the body does not restate the frontmatter description verbatim
    And the body contains none of the template placeholder strings: "your-agent-name", "One-sentence description", "# Agent Name"
    And no single detection rule or responsibility spans more than two lines

  Scenario: User is prompted for tools when none are provided
    Given the user has not specified a tools list
    When the skill processes the request
    Then the skill prompts: "Which tools does this agent need?"
    And the prompt includes examples: "Read, Grep, Glob (read-only) | add Edit, Write (file changes) | add Bash (shell) | add Skill (skill invocation) | add Agent (spawn subagents)"
    And the skill waits for the user's selection before proceeding

  Scenario: Plugin-unsupported fields are absent by default
    Given the user has not explicitly requested hooks, mcpServers, or permissionMode
    When the skill generates the frontmatter
    Then hooks is absent from the frontmatter
    And mcpServers is absent from the frontmatter
    And permissionMode is absent from the frontmatter

  Scenario: Plugin-unsupported fields warned when explicitly requested
    Given the user explicitly requests a hooks, mcpServers, or permissionMode field
    When the skill processes the request
    Then the skill emits: "hooks/mcpServers/permissionMode are silently ignored for plugin agents — move the file to .claude/agents/ if you need them to take effect"
    And the field is included if the user confirms
    And the field is omitted if the user declines

  Scenario: Skill refuses to overwrite an existing agent silently
    Given an agent file already exists at plugins/agentic-dev-team/agents/<name>.md
    When the user invokes the skill with the same name
    Then the skill reports the existing file path and its current description
    And asks for explicit confirmation before overwriting
    And does not write until the user confirms

  Scenario: Skill rejects an invalid name
    Given the user provides a name containing uppercase letters, spaces, or special characters
    When the skill processes the name
    Then the skill rejects it with an error describing the rule
    And suggests the corrected kebab-case form
    And does not write any file

  Scenario: Duplicate scope is flagged before writing
    Given an existing agent already covers the same detection domain
    When the skill identifies the overlap
    Then the skill reports the overlapping agent name and shared scope
    And asks whether to continue or cancel
    And does not write until the user decides

  Scenario: Agent registry is updated after successful creation
    Given a new agent has been written successfully
    When the skill completes
    Then knowledge/agent-registry.md contains a new row for the agent
    And the row includes the agent name, file path, model tier, and a description
    And plugins/agentic-dev-team/CLAUDE.md contains a new row for the agent in the appropriate table
```

## Architecture Specification

### New Component

| Component | Location |
|-----------|----------|
| Skill | `plugins/agentic-dev-team/skills/agent-create/SKILL.md` |

No new command file. The skill is `user-invocable: true` and is also delegated to by the updated `/agent-add` command.

### Modified Component

| Component | Change |
|-----------|--------|
| `commands/agent-add.md` | Replace hardcoded inline template with delegation to `skills/agent-create/SKILL.md`; extend scope to cover team agents in addition to review agents |

### Reads

- `templates/agents/agent-template.md` — field reference and permitted values
- `plugins/agentic-dev-team/agents/*.md` — scope-overlap check
- `plugins/agentic-dev-team/knowledge/agent-registry.md` — to append after creation
- `plugins/agentic-dev-team/CLAUDE.md` — to append after creation

### Writes

- `plugins/agentic-dev-team/agents/<name>.md` — the new agent
- `plugins/agentic-dev-team/knowledge/agent-registry.md` — new row (append only)
- `plugins/agentic-dev-team/CLAUDE.md` — new row in the appropriate agents table (append only)

### Process Flow

1. **Parse arguments** — name, type (review|team), description, tools, model
2. **Prompt for missing required fields** — if name absent: ask; if type absent: ask; if tools absent: display tool-selection prompt with examples; if description absent: ask
3. **Validate name** — must match `^[a-z][a-z0-9-]*$`; reject with correction suggestion if not
4. **Check conflict** — if `agents/<name>.md` exists: show its description and ask to confirm overwrite
5. **Check scope overlap** — scan existing agents for `description` and `## Detect` content; flag conceptual overlap and confirm with user
6. **Warn on plugin-unsupported fields** — if hooks/mcpServers/permissionMode requested: emit warning; confirm before including
7. **Apply defaults** — review: `tools: Read, Grep, Glob`, `model: haiku`; team: `model: sonnet`
8. **Generate frontmatter** — only official fields from template; validate all values
9. **Generate body** — type-specific structure; enforce token-efficiency rules; enforce line budget
10. **Validate** — run `agent-eval --agent claude-setup-review` against generated content; abort if status is not `pass`
11. **Present draft** — display full file; confirm before writing
12. **Write file**
13. **Update registry** — append row to `knowledge/agent-registry.md`
14. **Update CLAUDE.md** — append row to the appropriate agents table

### Body Structure by Type

| Section | Review agent | Team agent |
|---------|-------------|-----------|
| Output JSON block | Required | Absent |
| Status/Severity/Confidence lines | Required | Absent |
| Skip | Required | Optional |
| Detect | Required | Absent |
| Ignore | Required | Absent |
| Responsibilities | Absent | Required |
| Output discipline | Absent | Optional |
| Skills | Absent | Optional |

### Token-Efficiency Rules (normative)

| Rule | Applies to |
|------|-----------|
| Body ≤ 40 lines | Review agents |
| Body ≤ 75 lines | Team agents |
| No opener beginning "You are a" or "You are an" | All |
| No verbatim restatement of `description` field | All |
| Detection rules and responsibilities: ≤ 2 lines each | All |
| Knowledge file reference: one line only (`Read knowledge/X.md before starting`) | All |
| Omit template sections not applicable to this agent | All |
| No inline template comments in output | All |

## Acceptance Criteria

1. Generated agent file returns status `pass` from `agent-eval --agent claude-setup-review`
2. Review agent body is ≤ 40 lines
3. Team agent body is ≤ 75 lines
4. Body contains no opener matching `^You are an? `
5. Body does not contain the frontmatter `description` value verbatim
6. Body contains none of the strings: `your-agent-name`, `One-sentence description`, `# Agent Name`
7. No bullet point in the body spans more than two lines
8. When tools are not provided, the skill prompts with the standard tool-selection examples before proceeding
9. `hooks`, `mcpServers`, and `permissionMode` are absent from generated frontmatter unless the user explicitly confirmed after the plugin warning
10. A file matching an existing agent path is not overwritten without explicit user confirmation
11. A name not matching `^[a-z][a-z0-9-]*$` is rejected with a correction suggestion; no file is written
12. After successful creation, `knowledge/agent-registry.md` contains a new row with name, file path, model tier, and description
13. After successful creation, `plugins/agentic-dev-team/CLAUDE.md` contains a new row in the appropriate agents table

## Consistency Gate

- [x] Intent is unambiguous — line budgets justified with token arithmetic, agent types distinguished by structure, tool prompt UX specified
- [x] Every behavior in the intent has at least one BDD scenario
- [x] Architecture constrains without over-engineering — no new command file, skill is user-invocable directly
- [x] Terminology is consistent across all four artifacts
- [x] No contradictions between artifacts
