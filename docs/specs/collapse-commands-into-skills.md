# Spec: Collapse Commands into Skills

## Intent Description

The dev-team plugin currently maintains two separate directories for similar concerns:
`commands/` (35 user-invocable slash commands as flat `.md` files) and `skills/`
(41 agent-loaded procedure modules as `SKILL.md` files in named subdirectories).

The Claude Code platform has unified these into a single skills system where both
user-invocable commands and agent-loaded procedures use the same `skills/<name>/SKILL.md`
format, differentiated only by frontmatter (`user-invocable: true`). This change migrates
all 35 command files from `commands/*.md` into the `skills/` directory structure, removes
the `commands/` directory, resolves the one naming conflict (`test-health`), and updates
all documentation and `CLAUDE.md` to reflect the unified structure. No user-facing behavior
changes — all slash commands continue to work identically after migration.

The `test-health` naming conflict is resolved by keeping the `skills/test-health/SKILL.md`
version (the full implementation) and discarding `commands/test-health.md` (a thin wrapper
that only delegated to the skill). The `code-review` command is a directory-style command
with supporting files (`examples/`, `output-format.md`) that move alongside the main file.

## User-Facing Behavior

```gherkin
Feature: Unified skills directory for dev-team plugin

  Scenario: Plugin source ships a single skills directory
    Given the dev-team plugin source repository after migration
    Then plugins/dev-team/skills/ exists
    And plugins/dev-team/commands/ does not exist
    And plugins/dev-team/skills/ contains 75 entries

  Scenario: All former slash commands remain invocable after migration
    Given the plugin is installed from the migrated source
    When the user types /code-review
    Then the skill executes from .claude/skills/code-review/SKILL.md
    And the behavior is identical to the pre-migration command

  Scenario: Slash command with argument-hint still surfaces hints
    Given the plugin is installed from the migrated source
    When the user types /agent-eval
    Then the argument-hint "[--agent <name>] [--fixture <name>] [--trials <n>] [--verbose]" is shown

  Scenario: Agent-loaded skills remain accessible after migration
    Given the plugin is installed from the migrated source
    When an agent invokes Skill(context-loading-protocol)
    Then the skill content loads from .claude/skills/context-loading-protocol/SKILL.md

  Scenario: test-health naming conflict resolves to skill version
    Given commands/test-health.md (thin wrapper) and skills/test-health/SKILL.md (full implementation) both exist
    When the migration is complete
    Then only skills/test-health/SKILL.md exists
    And it is user-invocable
    And the argument-hint from the command version is preserved in the skill frontmatter

  Scenario: code-review supporting files migrate with the command
    Given commands/code-review.md and commands/code-review/ (examples/, output-format.md)
    When the migration is complete
    Then skills/code-review/SKILL.md exists with the former command content
    And skills/code-review/examples/ exists
    And skills/code-review/output-format.md exists

  Scenario: CLAUDE.md reflects the new structure
    Given the plugin source after migration
    Then CLAUDE.md has zero references to commands/
    And the "Slash Commands Registry" section is renamed or updated to use skills terminology
    And all path references point to skills/

  Scenario: agent-audit skill checks the skills directory
    Given the migrated plugin source
    When /agent-audit is run
    Then it audits .claude/skills/*.md and .claude/skills/*/SKILL.md
    And it does not reference .claude/commands/

  Scenario: Installed users with existing .claude/commands/ files are unaffected
    Given a project that has existing .claude/commands/ files before migration
    When the plugin is updated to the migrated version
    Then the existing commands/ files continue to work
    And no manual migration is required from installed users
```

## Architecture Specification

### Directory changes

| Before | After | Action |
|--------|-------|--------|
| `commands/<name>.md` | `skills/<name>/SKILL.md` | Create directory, move file, rename |
| `commands/code-review/` (supporting files) | `skills/code-review/` | Move directory contents alongside SKILL.md |
| `commands/test-health.md` | _(deleted)_ | Thin wrapper superseded by existing skill |
| `skills/<name>/SKILL.md` (existing 41) | `skills/<name>/SKILL.md` | Unchanged |

Net result: ~75 skills directories (35 migrated + 41 existing − 1 duplicate resolved).

### Frontmatter changes

Migrated command files already carry compatible frontmatter (`name`, `description`,
`argument-hint`, `user-invocable`, `allowed-tools`). No frontmatter changes required
for migrated files. For `test-health`: copy `argument-hint` from the command version
into the skill version if not already present.

### File-by-file changes

- **`plugins/dev-team/commands/`** — remove directory after migration
- **`plugins/dev-team/CLAUDE.md`** — 35 `commands/` references → `skills/`; rename
  "Slash Commands Registry" table header; update structural description in Repository
  Structure section
- **`plugins/dev-team/docs/skills.md`** — update to reflect unified skills concept
- **`plugins/dev-team/docs/code-review-process.md`** — update any `commands/` path references
- **`plugins/dev-team/docs/test-evaluation.md`** — update any `commands/` path references
- **`plugins/dev-team/commands/agent-audit.md`** (now `skills/agent-audit/SKILL.md`) —
  update Step 3 to audit `skills/` instead of `commands/`
- **`plugins/dev-team/.claude-plugin/plugin.json`** — no change (doesn't reference either directory)

### Constraints

- No behavior changes — this is a structural migration only.
- Backwards compatibility is guaranteed by the Claude Code platform: existing
  `.claude/commands/` files in installed projects continue working without any action
  from installed users.
- Migration order: move files first, then remove `commands/`, then update documentation.

## Acceptance Criteria

- [ ] `plugins/dev-team/commands/` directory does not exist in the repo after migration
- [ ] `plugins/dev-team/skills/` contains all 35 migrated command files (as `SKILL.md`)
  plus the 41 pre-existing skills (minus the test-health duplicate) ≈ 75 entries total
- [ ] All former slash commands remain invocable with identical behavior
- [ ] All agent-loaded skills remain loadable after migration
- [ ] `test-health` skill is user-invocable and carries the `argument-hint` from the command version
- [ ] `code-review` supporting files (`examples/`, `output-format.md`) exist under `skills/code-review/`
- [ ] `CLAUDE.md` contains zero occurrences of `commands/` (grep returns empty)
- [ ] `docs/skills.md`, `docs/code-review-process.md`, `docs/test-evaluation.md` updated
- [ ] `skills/agent-audit/SKILL.md` Step 3 audits `skills/` not `commands/`
- [ ] Plugin installs cleanly from the migrated source (`claude plugin install`)
- [ ] `/agent-audit` passes with no FAILs after migration

## Consistency Gate

- [x] Intent is unambiguous — two developers would interpret it the same way
- [x] Every behavior in the intent has at least one BDD scenario
- [x] Architecture constrains without over-engineering (structural rename only)
- [x] Terminology consistent across all four artifacts ("skills", "migrate", "SKILL.md")
- [x] No contradictions between artifacts
