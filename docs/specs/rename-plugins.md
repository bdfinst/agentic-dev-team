# Spec: Rename Plugins — `agentic-dev-team` → `dev-team`, `agentic-security-assessment` → `security-assessment`

## Intent Description

Drop the `agentic-` prefix from both published plugin names in the `bfinster` marketplace. The current names are verbose and the prefix carries no information — every plugin in this marketplace is "agentic" by definition. After this change, users install and reference the plugins as `dev-team@bfinster` and `security-assessment@bfinster`.

The rename touches plugin manifests, the marketplace catalog, release-please configuration, internal references inside docs/skills/agents/hooks/install scripts, and CI workflows. It does **not** rename the existing `security-review.md` review agent inside `dev-team` — that agent keeps its name; we use `security-assessment` for the renamed plugin to avoid namespace collision.

The work happens on a new branch (`refactor/rename-plugins`) so the rename ships as one reviewable PR. Existing release-please tags (`agentic-dev-team-v5.6.0`, `agentic-security-assessment-v2.2.2`) stay in git history; new releases publish under `dev-team-vX.Y.Z` and `security-assessment-vX.Y.Z`. Installed users migrate via an updated `/upgrade` command that detects the old plugin id, uninstalls it, and installs the new one (no compat shim directories left behind).

## User-Facing Behavior

```gherkin
Feature: Renamed plugins install and operate under new names

  Scenario: Fresh install of dev-team
    Given a user has the bfinster marketplace registered
    When they run "claude plugin install dev-team@bfinster"
    Then the plugin installs successfully
    And "claude plugin list" reports a plugin named "dev-team"
    And all dev-team slash commands (e.g. /code-review, /plan, /build) are available
    And no plugin named "agentic-dev-team" appears in the list

  Scenario: Fresh install of security-assessment
    Given a user has the bfinster marketplace registered
    And dev-team is installed
    When they run "claude plugin install security-assessment@bfinster"
    Then the plugin installs successfully
    And "claude plugin list" reports a plugin named "security-assessment"
    And the dependency check passes against dev-team (>= the declared minimum-version)

  Scenario: Existing user with old plugin id runs /upgrade
    Given a user has "agentic-dev-team@bfinster" installed at the pre-rename version
    When they run "/upgrade"
    Then the command detects the rename
    And reports: "Plugin renamed: agentic-dev-team → dev-team. Migrating."
    And uninstalls "agentic-dev-team@bfinster"
    And installs "dev-team@bfinster"
    And reports the new installed version
    And instructs the user to restart Claude Code

  Scenario: Existing user with old security plugin id runs /upgrade
    Given a user has "agentic-security-assessment@bfinster" installed
    When they run "/upgrade" (from dev-team)
    Then the command also detects the security plugin rename
    And migrates "agentic-security-assessment@bfinster" → "security-assessment@bfinster"
    And reports both migrations in one summary

  Scenario: /upgrade is idempotent post-migration
    Given a user has already migrated to "dev-team@bfinster"
    When they run "/upgrade" again
    Then no rename migration is attempted
    And the command behaves as a normal version-check upgrade

  Scenario: Marketplace catalog lists new names
    When a user runs "claude plugin marketplace bfinster"
    Then the listing shows plugins named "dev-team" and "security-assessment"
    And neither "agentic-dev-team" nor "agentic-security-assessment" appears as an available plugin

  Scenario: Release-please tags new releases under new component names
    Given the rename PR has merged to main
    And a subsequent conventional commit lands on main
    When release-please runs
    Then the release PR proposes tags "dev-team-vX.Y.Z" and/or "security-assessment-vX.Y.Z"
    And existing tags "agentic-dev-team-v*" and "agentic-security-assessment-v*" remain unchanged in git history

  Scenario: CI workflows pass against renamed paths
    Given the rename has moved plugin directories to plugins/dev-team and plugins/security-assessment
    When the plugin-tests CI workflow runs on the rename branch
    Then all jobs that reference plugin paths or names resolve correctly
    And the workflow succeeds

  Scenario: Internal cross-references are consistent
    Given the rename is complete
    When grepping the repository for "agentic-dev-team" or "agentic-security-assessment"
    Then matches appear ONLY in: CHANGELOG history entries, historical plan docs explicitly marked as historical, and the /upgrade migration logic
    And no live documentation, skill body, agent body, hook script, or install script references the old names

  Scenario: Old install command fails clearly
    Given the rename PR has shipped
    When a new user runs "claude plugin install agentic-dev-team@bfinster"
    Then the command fails with a plugin-not-found error from Claude Code
    And the README and marketplace listing direct them to the new name
```

## Architecture Specification

### Components touched

| Path | Change |
|---|---|
| `.claude-plugin/marketplace.json` | Rename both plugin entries; update `source` paths to new directories; bump descriptions if they reference old names. |
| `plugins/agentic-dev-team/` | Directory rename → `plugins/dev-team/`. |
| `plugins/agentic-security-assessment/` | Directory rename → `plugins/security-assessment/`. |
| `plugins/dev-team/.claude-plugin/plugin.json` | `name` field → `dev-team`. Version unchanged (release-please will bump on next conventional commit). |
| `plugins/security-assessment/.claude-plugin/plugin.json` | `name` field → `security-assessment`. Update `depends-on[].name` → `dev-team`. |
| `release-please-config.json` | Update both `packages` keys to new paths; update `package-name` and `component` for both. |
| `.release-please-manifest.json` | Update path keys to new directory paths. |
| `.github/workflows/plugin-tests.yml` | Update any path or plugin-name references. |
| `plugins/dev-team/commands/upgrade.md` | Add migration logic (detect old plugin id, uninstall + reinstall under new name). |
| `plugins/dev-team/commands/*`, `agents/*`, `skills/*`, `hooks/*`, `knowledge/*`, `docs/*`, `templates/*`, `CLAUDE.md`, `README.md` | Replace literal occurrences of `agentic-dev-team` with `dev-team` and `agentic-security-assessment` with `security-assessment` where they refer to the plugin name. |
| `plugins/security-assessment/install.sh`, `install-macos.sh`, `install-windows.ps1` | Update banner text and dependency-check name (`agentic-dev-team` → `dev-team`). |
| `plugins/security-assessment/CLAUDE.md`, `README.md`, `docs/`, `skills/`, `agents/`, `commands/`, `harness/`, `hooks/` | Replace literal name references. |
| Top-level `README.md`, `CLAUDE.md`, repo-level `docs/` | Replace literal name references. |

### Out of scope

- The repository name (`agentic-dev-team` on GitHub) — not renamed in this change.
- The existing `plugins/dev-team/agents/security-review.md` review agent — keeps its name.
- CHANGELOG.md history entries — left intact (they describe the past).
- Existing git tags — not retagged.
- Plans/ADRs explicitly marked as historical in `plans/` and `docs/adr/` — old name references stay as historical record.

### Interfaces / contracts

- **Marketplace plugin id** is the user-visible interface. `dev-team@bfinster` and `security-assessment@bfinster` become the canonical install ids.
- **`primitives-contract` version** in `security-assessment/.claude-plugin/plugin.json` is unchanged; only the `depends-on.name` shifts to `dev-team`.
- **Slash command names** (`/upgrade`, `/code-review`, etc.) are unchanged.
- **`/upgrade` migration logic** is the only place that knows both names — it MUST query `installed_plugins.json` for both `agentic-dev-team@*` and `agentic-security-assessment@*` patterns and offer migration when found.

### Constraints

- The PR is a single atomic rename. No partial states (e.g., new plugin.json name but old directory) should be committed.
- Search-and-replace must be case-preserving where mixed-case ("Agentic Dev Team") appears in human prose.
- Hook scripts referenced by relative paths (`bash hooks/foo.sh`) continue to work because directory contents are preserved; only the parent directory name changes.
- The marketplace catalog must validate against `marketplace.json` schema after the change.

### Migration path for installed users

`/upgrade` gains a Step 0 (runs before the existing Step 1): query the local plugin registry for any plugin whose id begins with `agentic-dev-team@` or `agentic-security-assessment@`. For each match, run `claude plugin uninstall <old-id>` followed by `claude plugin install <new-name>@<marketplace>`. Report each migration as one line. If no old-id matches are found, the step is a no-op and falls through to normal upgrade flow.

## Acceptance Criteria

| ID | Criterion | Measurement |
|---|---|---|
| AC-1 | Marketplace catalog validates | `marketplace.json` parses as JSON and both plugins have new names; no `agentic-` prefix remains in live `plugins[]` entries. |
| AC-2 | Both plugin manifests reflect new names | `jq -r .name` on each `plugin.json` returns `dev-team` and `security-assessment` respectively. |
| AC-3 | `security-assessment` declares dependency on `dev-team` | `jq -r '.["depends-on"][0].name'` returns `dev-team`. |
| AC-4 | release-please config points to new paths and component names | `release-please-config.json` `packages` keys are `plugins/dev-team` and `plugins/security-assessment`; `component` fields match new names. |
| AC-5 | Manifest paths updated | `.release-please-manifest.json` keys match new directory paths. |
| AC-6 | No live references to old names | `grep -r "agentic-dev-team\|agentic-security-assessment"` over the repo, excluding `CHANGELOG.md`, `plans/`, `docs/adr/`, `evals/security-review-adapter/` historical artifacts, and the `/upgrade` migration block, returns zero matches. |
| AC-7 | CI passes on the rename branch | `.github/workflows/plugin-tests.yml` and any other CI workflow exits green. |
| AC-8 | `/upgrade` migration logic exists and is tested | The upgrade command contains explicit handling for `agentic-dev-team@*` and `agentic-security-assessment@*` patterns, with a unit-level or eval-level test covering the migration. |
| AC-9 | `/upgrade` is idempotent | Running `/upgrade` against an already-migrated install reports no migration action and performs a normal version check. |
| AC-10 | Branch is `refactor/rename-plugins` and PR uses conventional commit prefix `refactor!:` (breaking) | Branch name matches; PR title begins with `refactor!:` so release-please flags both packages as a major bump. |
| AC-11 | No directory-name leakage | `ls plugins/` shows only `dev-team` and `security-assessment`; no compat-shim directories remain. |
| AC-12 | `/agent-audit` passes after rename | Skill/agent structural validation reports no regressions. |

## Consistency Gate

- [x] Intent is unambiguous — drops `agentic-` prefix from both plugin names; clarifies that the existing `security-review` agent is untouched and the new plugin name is `security-assessment` to avoid collision.
- [x] Every behavior has a corresponding BDD scenario — fresh install (both plugins), upgrade migration (both plugins), idempotency, marketplace listing, release-please tagging, CI, internal-reference consistency, old-install failure mode.
- [x] Architecture constrains without over-engineering — enumerates exactly which files change, lists out-of-scope items, and specifies the one new piece of logic (`/upgrade` Step 0) rather than a compat-shim system.
- [x] Terminology consistent — `dev-team`, `security-assessment`, "rename", "migration" used uniformly across all four artifacts.
- [x] No contradictions — release history preservation, hard rename, and `/upgrade`-driven migration all consistent across Intent, Architecture, and Acceptance Criteria.

**Verdict: PASS**
