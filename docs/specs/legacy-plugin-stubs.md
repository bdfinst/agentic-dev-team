# Spec: Legacy Plugin Deprecation Stubs

## Intent Description

When the marketplace plugin ids were renamed in PR #43 (`agentic-dev-team` → `dev-team`, `agentic-security-assessment` → `security-assessment`), the new plugins shipped a Step 0 migration in `/upgrade` that walks installed users to the new ids. The migration ships in the **destination** plugin — useful only to someone already on the new plugin.

Users still installed on the **source** plugins (`agentic-dev-team@5.6.0` and earlier) run an `/upgrade` whose first action is `claude plugin update agentic-dev-team@bfinster`. That call now fails because the marketplace catalog no longer lists either old name. Those users are stranded with no auto-migration path.

This spec republishes both old plugin ids back into the marketplace catalog as **deprecation stubs** — minimal plugins whose entire purpose is to provide a working `/upgrade` that installs the new plugin and then removes the stub.

The stubs are intentionally narrow:

- One command (`/upgrade`), one README, one CHANGELOG, one `plugin.json`, no agents, no skills, no hooks, no knowledge, no templates.
- Version bumped from `5.6.0` → `6.0.1` (and `2.2.2` → `3.0.1`) so `claude plugin update` sees a newer version than what installed users have and fetches the stub.
- Marked DEPRECATED in description so anyone browsing the catalog sees the deprecation immediately.

The stubs are scheduled for removal from the marketplace catalog no earlier than 2027-06-01 — twelve months after rename — to give all installed users a chance to migrate.

## User-Facing Behavior

```gherkin
Feature: Legacy plugin id deprecation stubs

  Scenario: Pre-rename installed user runs /upgrade
    Given a user has "agentic-dev-team@bfinster" v5.6.0 (pre-rename) installed
    And the marketplace catalog now lists "agentic-dev-team@bfinster" v6.0.1 (stub)
    When they run "/upgrade" from a Claude Code session with the legacy plugin loaded
    Then the existing /upgrade calls "claude plugin update agentic-dev-team@bfinster"
    And the update succeeds (catalog resolves to the stub)
    And the user's installed plugin is replaced with v6.0.1 (stub)
    And the user is prompted to restart Claude Code

  Scenario: User runs /upgrade from inside the stub
    Given a user has just been upgraded to the v6.0.1 stub
    And they have restarted Claude Code
    When they run "/upgrade"
    Then /upgrade detects the install scope from "claude plugin list"
    And runs "claude plugin install --scope <scope> dev-team@bfinster"
    And only after the install succeeds, runs "claude plugin uninstall --scope <scope> agentic-dev-team@bfinster"
    And reports the migration in a single summary block
    And ends with an ACTION REQUIRED line prompting restart

  Scenario: Install of dev-team fails during stub /upgrade
    Given a user is on the v6.0.1 stub
    When they run "/upgrade"
    And the install of "dev-team@bfinster" fails (network / marketplace error)
    Then the stub is NOT uninstalled
    And the failure is reported with the exact retry command
    And /upgrade exits non-zero
    And the user retains a working stub (with its /upgrade) to retry

  Scenario: Fresh user accidentally installs the deprecated stub
    Given a new user runs "claude plugin install agentic-dev-team@bfinster"
    When the install completes
    Then they have the v6.0.1 stub installed
    And the stub README clearly states this is a deprecation stub
    And running "/upgrade" migrates them to the real plugin

  Scenario: Stub structure is minimal
    Given the deprecation stubs ship in plugins/agentic-dev-team/ and plugins/agentic-security-assessment/
    When inspecting the stub directories
    Then each contains only plugin.json, /upgrade, README.md, CHANGELOG.md
    And contains no agents/, no skills/, no knowledge/, no templates/, no hooks/, no harness/, no prompts/

  Scenario: Marketplace catalog lists stubs alongside real plugins
    When fetching .claude-plugin/marketplace.json
    Then plugins[].name includes all four: dev-team, security-assessment, agentic-dev-team, agentic-security-assessment
    And the two agentic-* descriptions contain "DEPRECATED"
    And neither legacy stub appears as a depended-on plugin

  Scenario: Release-please ignores the stubs
    Given release-please-config.json is configured
    When release-please runs
    Then it tracks only "plugins/dev-team" and "plugins/security-assessment"
    And does not propose releases for the legacy stub directories
    And the stub versions are manually bumped if ever changed
```

## Architecture Specification

### Files added (under `plugins/agentic-dev-team/`)

| Path | Purpose |
|---|---|
| `.claude-plugin/plugin.json` | Manifest: name `agentic-dev-team`, version `6.0.1`, description marked DEPRECATED |
| `commands/upgrade.md` | The migration command: scope detection → install new → uninstall self → restart prompt |
| `README.md` | Explains the stub, the migration, and the sunset date |
| `CHANGELOG.md` | Records the 6.0.1 deprecation release; points at `plugins/dev-team/CHANGELOG.md` for the real history |

Mirror under `plugins/agentic-security-assessment/` with name `agentic-security-assessment`, version `3.0.1`.

### Files modified

| Path | Change |
|---|---|
| `.claude-plugin/marketplace.json` | Append two stub entries to `plugins[]` with DEPRECATED descriptions; preserve the existing real-plugin entries |
| `scripts/assert-rename.sh` | New invariants: stub directories are shape-correct (only `/upgrade`, README, CHANGELOG, plugin.json — no agents/skills/etc.); marketplace catalog includes both real + stub; stub descriptions contain "DEPRECATED"; release-please consistency check excludes stub paths |

### Files explicitly NOT modified

- `release-please-config.json`: stubs are manually versioned, short-lived, and tracked outside the release-please workflow. Adding them would create perpetual release PRs for code that should be deleted, not iterated.
- `.release-please-manifest.json`: same reason.
- `plugins/dev-team/**` and `plugins/security-assessment/**`: the real plugins are unchanged. The existing migration in `plugins/dev-team/commands/upgrade.md` Step 0 remains in place (it's the second leg of the migration for users who already have both old and new installed, or who arrived via the stub).

### Behavior contract for `/upgrade` in each stub

1. Detect install scope via `claude plugin list`. Default to `user` if undetected.
2. `claude plugin install --scope <scope> <new-name>@bfinster`.
3. **Hard gate**: if the install fails, STOP. The stub is not uninstalled — the user has a working fallback. Surface the exact retry command.
4. `claude plugin uninstall --scope <scope> <self>@bfinster`. On failure, warn but continue.
5. Print a migration summary and an `ACTION REQUIRED: restart` line.

### Sunset

A future commit (no earlier than 2027-06-01) deletes:

- `plugins/agentic-dev-team/`
- `plugins/agentic-security-assessment/`
- The two stub entries in `.claude-plugin/marketplace.json`
- The stub-related assertions in `scripts/assert-rename.sh`

The companion sunset tracker `docs/decisions/upgrade-step-0-sunset.md` (introduced in PR #43) covers the broader cleanup timeline, including the `/upgrade` Step 0 block in the real plugin.

## Acceptance Criteria

| ID | Criterion | Measurement |
|---|---|---|
| LSAC-1 | Both stub directories exist with the four required files | `[ -f plugins/agentic-dev-team/{.claude-plugin/plugin.json,commands/upgrade.md,README.md,CHANGELOG.md} ]` and same for `agentic-security-assessment` |
| LSAC-2 | Stub `plugin.json` declares the old name and a version newer than the last real release (`6.0.1` > `5.6.0`; `3.0.1` > `2.2.2`) | `jq -r .name && jq -r .version` |
| LSAC-3 | Stub descriptions in `plugin.json` AND in `marketplace.json` contain `DEPRECATED` | grep |
| LSAC-4 | Stub directories contain NO agents/, skills/, knowledge/, templates/, prompts/, harness/, hooks/ subdirectories | `find` |
| LSAC-5 | `.claude-plugin/marketplace.json` `plugins[]` lists all four ids in any order | `jq` |
| LSAC-6 | `release-please-config.json` does NOT include the stub directories | `jq -e '.packages | has("plugins/agentic-dev-team") | not'` |
| LSAC-7 | Each stub's `/upgrade` command body documents install-first-then-uninstall ordering, the hard gate on install failure, scope detection, and the restart message | grep for keywords |
| LSAC-8 | `scripts/assert-rename.sh` passes all assertions including the new stub-shape invariants | exits zero |
| LSAC-9 | The existing `evals/upgrade-migration/run.sh` still passes (PR #43 evals not regressed) | exits zero |

## Consistency Gate

- [x] Intent is unambiguous — stubs solve a specific stranded-user problem; they are not the real plugins and explicitly state so.
- [x] Every behavior has a corresponding BDD scenario — fresh install-of-stub, upgrade-from-stub, install-failure path, structure invariants, marketplace listing, release-please scope.
- [x] Architecture constrains without over-engineering — four files per stub, two marketplace entries, no release-please involvement, explicit sunset.
- [x] Terminology consistent — "stub", "deprecation", "migration", "real plugin" used uniformly.
- [x] No contradictions — stub `/upgrade` and real `/upgrade` Step 0 are not duplicates; they're sequential legs of the same migration when both exist.

**Verdict: PASS**
