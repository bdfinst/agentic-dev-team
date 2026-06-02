# Plan: Rename Plugins — `agentic-dev-team` → `dev-team`, `agentic-security-assessment` → `security-assessment`

**Created**: 2026-06-02
**Branch**: refactor/rename-plugins
**Status**: approved
**Spec**: `docs/specs/rename-plugins.md`

## Goal

Drop the `agentic-` prefix from both published plugin names in the `bfinster` marketplace. After this change, users install and reference the plugins as `dev-team@bfinster` and `security-assessment@bfinster`. The rename is a single atomic PR; release history and tags are preserved; installed users migrate via `/upgrade` Step 0. The existing `security-review.md` review agent inside the dev-team plugin is **not** renamed.

## Acceptance Criteria

- [ ] `marketplace.json` lists plugins named `dev-team` and `security-assessment`; no `agentic-` prefix in live `plugins[]` entries (AC-1).
- [ ] Both `plugin.json` manifests return new names from `jq -r .name` (AC-2).
- [ ] `security-assessment` declares `depends-on[0].name == "dev-team"` (AC-3).
- [ ] `release-please-config.json` uses new paths, `package-name`, and `component` fields for both packages (AC-4).
- [ ] `.release-please-manifest.json` keys match new directory paths (AC-5).
- [ ] No live references to old names outside the explicit exclusion list (AC-6). **Exclusion list** (final): `CHANGELOG.md`, `plans/`, `docs/adr/`, `docs/specs/rename-plugins.md`, `docs/decisions/upgrade-step-0-sunset.md`, `evals/security-review-adapter/`, `evals/upgrade-migration/`, `plugins/dev-team/commands/upgrade.md`, `plugins/security-assessment/install.sh`, `scripts/assert-rename.sh`, `scripts/sweep-rename.sh`, `metrics/config-changelog.jsonl`, `memory/decisions.md`, and `README.md` (which carries the redirect notice). The grep also ignores `github.com/bdfinst/agentic-dev-team` URLs and the `Previously published as …` discoverability sentence in marketplace.json.
- [ ] CI passes on the rename branch (AC-7) — verified post-push on GitHub Actions; locally we run every script the workflow invokes.
- [ ] `/upgrade` contains migration logic for `agentic-dev-team@*` and `agentic-security-assessment@*` patterns with a test (AC-8).
- [ ] `/upgrade` migration uses install-first-then-uninstall ordering so a failed install never leaves the user without a plugin (AC-8a).
- [ ] `/upgrade` is idempotent post-migration (AC-9).
- [ ] PR title uses `refactor!:` prefix (AC-10).
- [ ] `plugins/` contains only `dev-team/` and `security-assessment/`; no shim directories (AC-11).
- [ ] `/agent-audit` passes after rename (AC-12).
- [ ] Top-level `README.md` carries a visible "Renamed plugins" notice with new install commands (AC-13).
- [ ] Every commit on the branch leaves `release-please-config.json` consistent with the on-disk `plugins/` layout (AC-14).

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
    Then the command detects the rename in Step 0 (before Step 1's version read or Step 2's auto-update check)
    And reports: "Plugin renamed: agentic-dev-team → dev-team. Migrating."
    And installs "dev-team@bfinster" FIRST
    And only after the install succeeds, uninstalls "agentic-dev-team@bfinster"
    And reports the migration summary
    And exits the /upgrade command early with an ACTION REQUIRED line instructing the user to restart Claude Code and re-run /upgrade for auto-update opt-in
    And does NOT run Step 1 (version read) or Step 2 (auto-update prompt) in the same invocation

  Scenario: Existing user with old security plugin id runs /upgrade
    Given a user has "agentic-security-assessment@bfinster" installed
    When they run "/upgrade" (from dev-team)
    Then the command also detects the security plugin rename
    And migrates "agentic-security-assessment@bfinster" → "security-assessment@bfinster" using install-first-then-uninstall
    And reports both migrations in one summary block with old → new pairs

  Scenario: /upgrade migration partial failure leaves the user in a recoverable state
    Given a user has "agentic-dev-team@bfinster" installed
    When they run "/upgrade"
    And the install of "dev-team@bfinster" fails (network error, marketplace unavailable, etc.)
    Then the old plugin "agentic-dev-team@bfinster" remains installed and functional
    And the command reports the failure with the exact manual install command to retry
    And the command exits non-zero

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
    Then matches appear ONLY in the AC-6 exclusion list
    And no live documentation, skill body, agent body, hook script, or install script references the old names

  Scenario: Old install command fails with a discoverable redirect
    Given the rename PR has shipped
    When a new user runs "claude plugin install agentic-dev-team@bfinster"
    Then the command fails with a plugin-not-found error from Claude Code
    And the top-level README has a visible "Renamed plugins" section with the new install commands
    And the marketplace plugin descriptions reference the prior names so search hits surface the migration
```

## Steps

> **Note on TDD shape.** This task is mechanical rename work driven by an explicit spec. "RED" here means a failing assertion script (or eval/test) that codifies an acceptance criterion before the rename satisfies it. Each step leaves the repo in a working, committable state — we use a shared assertion script (`scripts/assert-rename.sh`) that step 1 introduces and later steps extend.

### Step 1: Bootstrap rename-assertion harness

**Complexity**: standard
**RED**: Create `scripts/assert-rename.sh` with a battery of checks against the repo. Initial checks (all expected to FAIL before later steps land):

- `jq -r .name plugins/dev-team/.claude-plugin/plugin.json` returns `dev-team`
- `jq -r .name plugins/security-assessment/.claude-plugin/plugin.json` returns `security-assessment`
- `jq -r '.plugins[].name' .claude-plugin/marketplace.json` outputs exactly the two new names
- No directory `plugins/agentic-dev-team` or `plugins/agentic-security-assessment` exists
- **Cross-commit consistency check** (AC-14): every package key in `release-please-config.json` corresponds to an extant directory under `plugins/`, and vice versa — fails if the two get out of sync at any point.

Run the script; confirm it fails as expected.
**GREEN**: No code change — the script's failure IS the red bar.
**REFACTOR**: None needed.
**Files**: `scripts/assert-rename.sh`
**Commit**: `test: add rename assertion harness (failing baseline)`

### Step 2: Atomic rename — directories, manifests, marketplace, release-please

**Complexity**: complex
**Rationale**: Steps for directory move, manifest rewrite, marketplace catalog, and release-please config are bundled into ONE commit. Any subset leaves a state where either (a) the security plugin's `depends-on` points at a non-existent dev-team, or (b) release-please config references a path that no longer exists. AC-14 (cross-commit consistency) makes this non-negotiable.

**RED**: Append to `assert-rename.sh`:

- `! [ -d plugins/agentic-dev-team ]` and `[ -d plugins/dev-team ]`
- `! [ -d plugins/agentic-security-assessment ]` and `[ -d plugins/security-assessment ]`
- `jq -r .name plugins/dev-team/.claude-plugin/plugin.json` returns `dev-team`
- `jq -r .name plugins/security-assessment/.claude-plugin/plugin.json` returns `security-assessment`
- `jq -r '.["depends-on"][0].name' plugins/security-assessment/.claude-plugin/plugin.json` returns `dev-team`
- `jq -r '.plugins[].name' .claude-plugin/marketplace.json` returns exactly `dev-team\nsecurity-assessment`
- `jq -e '.packages | has("plugins/dev-team") and has("plugins/security-assessment") and (has("plugins/agentic-dev-team") | not) and (has("plugins/agentic-security-assessment") | not)' release-please-config.json` exits zero
- `.release-please-manifest.json` keys match new paths
- The cross-commit consistency check from Step 1 passes

**GREEN** (all in one commit):

- `git mv plugins/agentic-dev-team plugins/dev-team`
- `git mv plugins/agentic-security-assessment plugins/security-assessment`
- `plugins/dev-team/.claude-plugin/plugin.json`: `name` → `dev-team`
- `plugins/security-assessment/.claude-plugin/plugin.json`: `name` → `security-assessment`, `depends-on[0].name` → `dev-team`
- `.claude-plugin/marketplace.json`: both `plugins[].name` and `source` paths updated; clean the parenthetical historical note in the security plugin description (leave a brief "Previously published as agentic-security-assessment." sentence so search surfaces it)
- `release-please-config.json`: rename both `packages` keys, update `package-name` + `component`
- `.release-please-manifest.json`: rename both keys (preserve current versions verbatim)
- Run `scripts/assert-rename.sh`; the new checks pass.

**REFACTOR**: None needed — body-level reference fixes happen in steps 3–4.
**Files**: `plugins/dev-team/**` (moved), `plugins/security-assessment/**` (moved), `.claude-plugin/marketplace.json`, `release-please-config.json`, `.release-please-manifest.json`, `scripts/assert-rename.sh`
**Commit**: `refactor!: rename plugins to dev-team and security-assessment`

### Step 3: Sweep internal references in `plugins/dev-team/`

**Complexity**: standard
**RED**: Append to `assert-rename.sh`:

- `grep -rln "agentic-dev-team" plugins/dev-team/ --exclude=CHANGELOG.md --exclude=upgrade.md` returns empty.

(CHANGELOG keeps history; `upgrade.md` is the legitimate home for the old name in the migration block — handled in step 5.)

**GREEN**:

- Use a small helper `scripts/sweep-rename.sh <root> <old> <new>` to run consistent file-glob replacements across `.md`, `.sh`, `.json`, `.yml`, `.yaml`, and template files.
- Invoke `bash scripts/sweep-rename.sh plugins/dev-team agentic-dev-team dev-team` (excluding `CHANGELOG.md`, `commands/upgrade.md`).
- Manually preserve mixed-case human prose ("Agentic Dev Team" → "Dev Team") where present.
- Run `assert-rename.sh`; the new grep check passes.

**REFACTOR**: None needed.
**Files**: `plugins/dev-team/**` (CLAUDE.md, README.md, agents/, skills/, commands/, knowledge/, docs/, templates/, hooks/, install.sh), `scripts/sweep-rename.sh` (new)
**Commit**: `refactor: sweep internal references to dev-team`

### Step 4: Sweep internal references in `plugins/security-assessment/`

**Complexity**: standard
**RED**: Append to `assert-rename.sh`:

- `grep -rln "agentic-security-assessment" plugins/security-assessment/ | grep -vE 'CHANGELOG\.md$'` returns empty.
- `grep -rln "agentic-dev-team" plugins/security-assessment/ | grep -vE 'CHANGELOG\.md$'` returns empty.

**GREEN**:

- `bash scripts/sweep-rename.sh plugins/security-assessment agentic-security-assessment security-assessment`
- `bash scripts/sweep-rename.sh plugins/security-assessment agentic-dev-team dev-team`
- Manually verify `install.sh`, `install-macos.sh`, `install-windows.ps1` dependency-check messages now mention `dev-team`.
- Update the install-script behavior: if the dependency check finds `agentic-dev-team@*` rather than `dev-team@*`, print a clear migration notice and exit with instructions ("Run `/upgrade` from your existing dev-team install, or run `claude plugin install dev-team@bfinster`") rather than failing silently.

**REFACTOR**: None needed.
**Files**: `plugins/security-assessment/**` (excluding CHANGELOG.md)
**Commit**: `refactor: sweep internal references to security-assessment and dev-team`

### Step 5: Add `/upgrade` migration logic (Step 0) with install-first-then-uninstall

**Complexity**: complex
**RED**: Write fixtures and a runner under `evals/upgrade-migration/`:

- Fixture A: `installed_plugins.json` with `{"plugins": {"agentic-dev-team@bfinster": "5.6.0"}}`. Expect `--dry-run` output to:
  - announce `Plugin renamed: agentic-dev-team → dev-team. Migrating.`
  - schedule `claude plugin install --scope <scope> dev-team@bfinster` BEFORE `claude plugin uninstall --scope <scope> agentic-dev-team@bfinster`
  - end with `ACTION REQUIRED: restart Claude Code, then re-run /upgrade if you want to enable auto-update.`
  - exit zero AFTER the migration block — fixture asserts that no command from Step 1 (`claude plugin list` for version parsing) or Step 2 (auto-update status check) is scheduled in the same run
- Fixture B: `installed_plugins.json` with `{"plugins": {"agentic-security-assessment@bfinster": "2.2.2"}}`. Expect mirror behavior for the security plugin.
- Fixture C: post-migration state `{"plugins": {"dev-team@bfinster": "5.7.0"}}`. Expect output containing `No legacy plugin ids found` and zero scheduled commands.
- Fixture D: simulated install failure — runner injects a non-zero exit code for the install command. Expect the migration block to:
  - NOT schedule the uninstall
  - emit a recovery message containing the exact failed command
  - exit non-zero
- `evals/upgrade-migration/run.sh` wires fixtures through the migration block in dry-run mode and asserts on stdout/exit code.

Run the runner; it fails because the migration block doesn't exist yet.

**GREEN**:

- Edit `plugins/dev-team/commands/upgrade.md` to insert **Step 0: Detect and migrate legacy plugin ids** before the existing Step 1. The embedded Python block:
  - declares a small rename map: `LEGACY = {"agentic-dev-team": "dev-team", "agentic-security-assessment": "security-assessment"}`
  - queries `~/.claude/plugins/installed_plugins.json` for keys whose prefix matches any LEGACY entry
  - for each match, derives the install scope from `claude plugin list` (matching the convention added to Step 3 of the existing upgrade flow) and executes: `claude plugin install --scope <scope> <new>@<marketplace>` → check exit code → only if zero, `claude plugin uninstall --scope <scope> <old>@<marketplace>` → report success line
  - on install failure: prints `MIGRATION FAILED — old plugin still installed. Retry with: claude plugin install --scope <scope> <new>@<marketplace>` and exits non-zero
  - emits one summary block when migrations succeed, with old → new pairs, followed by `ACTION REQUIRED: restart Claude Code, then re-run /upgrade if you want to enable auto-update.` and **terminates `/upgrade` early** — does NOT continue to Steps 1–4 (which would re-prompt about auto-update against a freshly-installed plugin and re-run the version check immediately, both confusing UX directly after a migration).
  - accepts a `--dry-run` flag (read from `os.environ.get("UPGRADE_DRY_RUN")`) that prints scheduled commands without executing them
  - documents the sunset criterion inline: "Remove this Step 0 after both `dev-team` and `security-assessment` reach v2.0.0 or 2027-06-01, whichever comes first."
- The migration Step 0 MUST run before the existing Step 1 (Read current version) and Step 2 (Check auto-update status). Both of those reference `PLUGIN = "agentic-dev-team"` in their Python blocks; after Step 4's sweep, the literal becomes `PLUGIN = "dev-team"`, which would fail to resolve for any user still on the legacy plugin id. Step 0 migrates them first, then either exits (success path) or exits non-zero (failure path) before Steps 1–4 run.
- Run the eval runner; all four fixtures pass.

**REFACTOR**: Trim duplicate prose from the existing Step 1 intro now that the migration block is explicit.
**Files**: `plugins/dev-team/commands/upgrade.md`, `evals/upgrade-migration/run.sh`, `evals/upgrade-migration/fixtures/*.json`
**Commit**: `feat(upgrade): migrate legacy agentic-* plugin ids on upgrade`

### Step 6: Sweep repo-root references and add README redirect notice

**Complexity**: standard
**RED**: Append to `assert-rename.sh`:

- Final consolidated grep:

  ```
  grep -rln "agentic-dev-team\|agentic-security-assessment" . \
    --exclude-dir=.git --exclude-dir=node_modules \
    | grep -vE '(CHANGELOG\.md|plans/|docs/adr/|evals/security-review-adapter/|evals/upgrade-migration/|plugins/dev-team/commands/upgrade\.md|scripts/assert-rename\.sh|scripts/sweep-rename\.sh|docs/specs/rename-plugins\.md)'
  ```

  must return empty.

- Top-level `README.md` contains a section whose heading matches `## Renamed` (or similar) AND mentions both old → new pairs AND the new install commands.

**GREEN**:

- `bash scripts/sweep-rename.sh . agentic-dev-team dev-team` and `bash scripts/sweep-rename.sh . agentic-security-assessment security-assessment`, scoped to `README.md`, `CLAUDE.md`, repo-level `docs/` (excluding `docs/adr/`), and `.github/workflows/`.
- Add a "Renamed plugins" section near the top of the top-level `README.md`:
  - Lists both old → new pairs
  - Gives the new install commands
  - Tells installed users to run `/upgrade` from dev-team
- Leave historical mentions in `plans/`, `docs/adr/`, `CHANGELOG.md` intact.

**REFACTOR**: None needed.
**Files**: repo-root `README.md`, `CLAUDE.md`, `docs/**` (excluding `docs/adr/**`), `.github/workflows/**`
**Commit**: `docs: update repo-root references; add Renamed plugins README notice`

### Step 7: CI script verification

**Complexity**: standard
**RED**: Enumerate every script `.github/workflows/plugin-tests.yml` invokes. Append to `assert-rename.sh` a section that runs each script and asserts exit zero. Run; expect failures from any script that still hardcodes old paths or names.

**GREEN**: Fix referenced scripts (typically `plugins/security-assessment/tests/scripts/*.sh`) so they target the new paths. Re-run.

**REFACTOR**: None needed.
**Files**: depends on output; likely `plugins/security-assessment/tests/scripts/*.sh`, `.github/workflows/plugin-tests.yml`
**Commit**: `test: update plugin-test scripts for renamed paths`

### Step 8: Final acceptance pass + cross-commit consistency replay

**Complexity**: trivial
**RED**: Run the full acceptance suite:

- `bash scripts/assert-rename.sh`
- `bash evals/upgrade-migration/run.sh`
- `/agent-audit`
- Cross-commit consistency replay: `for sha in $(git rev-list main..HEAD); do git checkout $sha && bash scripts/assert-rename.sh --consistency-only; done && git checkout refactor/rename-plugins` — every commit on the branch must pass the consistency subset. Step 1 implements `--consistency-only` to gate this check.
- Open a GitHub issue (or add a dated entry in `docs/decisions/`) tracking the `/upgrade` Step 0 sunset (target: both plugins ≥ v2.0.0 or 2027-06-01).

Expect all green.
**GREEN**: Fix any residual issue.
**REFACTOR**: None needed.
**Files**: as needed.
**Commit**: `test: final rename acceptance pass`

## Complexity Classification

| Step | Rating | Rationale |
|------|--------|-----------|
| 1 | standard | New harness; drives the whole plan |
| 2 | complex | Atomic cross-cutting rename; release-please + marketplace + dependency graph all move together |
| 3 | standard | Sweep, contained to one plugin |
| 4 | standard | Sweep + install-script behavior change |
| 5 | complex | New behavior in `/upgrade`; install-first-then-uninstall ordering; failure semantics; idempotency |
| 6 | standard | Sweep + new README section |
| 7 | standard | CI script surface |
| 8 | trivial | Verification only |

## Pre-PR Quality Gate

- [ ] `bash scripts/assert-rename.sh` exits zero
- [ ] `bash evals/upgrade-migration/run.sh` exits zero (all four fixtures, including the install-failure path)
- [ ] `/agent-audit` passes
- [ ] Every script invoked by `.github/workflows/plugin-tests.yml` runs locally and exits zero
- [ ] `/code-review` passes
- [ ] PR title uses `refactor!:` prefix
- [ ] Commit history follows the plan's per-step commit messages
- [ ] Cross-commit consistency replay (Step 8) passes for every commit between `main` and branch HEAD
- [ ] `/upgrade` Step 0 sunset tracker filed (GitHub issue or `docs/decisions/` entry)
- [ ] Post-push: GitHub Actions plugin-tests workflow passes on the branch (AC-7 is final-verified here, not pre-PR)

## Plan Review Summary

Four plan-review personas were run in parallel; after one revision iteration, all four returned `approve` with zero blockers. The aggregated warnings and observations:

### Warnings (non-blocking, folded into the plan)

- **Acceptance Test Critic** — Live-mutation path of `/upgrade` migration only verified syntactically (eval is dry-run); partial-failure scenario added; AC-6 exclusion list reconciled with the assertion grep; "old install fails clearly" scenario split into deterministic + manual portions; Step 7 (CI script verification) clarified to enumerate scripts before declaring RED.
- **Design & Architecture Critic** — Steps 2+3 collapsed into a single atomic commit; AC-14 added with cross-commit consistency check; `scripts/sweep-rename.sh` extracted as shared helper; CI verification scope honestly limited to script-level locally.
- **UX Critic** — Install-first-then-uninstall ordering codified (AC-8a, scenario, Fixture D); README "Renamed plugins" notice added (AC-13); marketplace "Previously published as…" sentence retained; install scripts emit a migration notice rather than failing silently.
- **Strategic Critic** — Approved on first pass. Three warnings folded in: README discoverability notice (already addressed via AC-13/Step 6), sunset criterion inlined in `/upgrade` body plus tracker filed in Step 8, intentional major-version reset documented in the PR body.

### Observations (forward-carried)

- Atomic Step 2 makes release-please-config + on-disk plugin layout structurally impossible to desynchronize at any commit boundary.
- Cumulative `scripts/assert-rename.sh` doubles as a pre-PR gate and a cross-commit replay harness; lifecycle (kept as permanent invariant vs. removed post-merge) is left to the reviewer's discretion.
- `UPGRADE_DRY_RUN` env var keeps the migration block testable without mocking the Claude plugin CLI.
- Sunset criterion for the migration block lives inline in the command body where future maintainers will encounter it at removal time, plus a tracker filed in Step 8.

## Risks & Open Questions

- **CI cannot be fully verified locally.** We run every script the workflow invokes, but the workflow itself (matrix, env, secrets) only runs on GitHub Actions. Mitigation: explicit post-push verification loop captured in the quality gate; `act` is not assumed installed.
- **Live `/upgrade` migration path is only exercised in dry-run during testing.** The eval runner asserts on scheduled commands and exit codes but does not actually invoke `claude plugin install`. Mitigation: install-first-then-uninstall ordering means a real failure is recoverable, and the recovery message contains the exact retry command.
- **Sunset of the `/upgrade` Step 0 block.** Documented inline in the command body (target: both plugins ≥ v2.0.0 or 2027-06-01). Leave a tracking note in `docs/` or a follow-up issue.
- **Possible additional name references in eval fixtures we don't own.** `evals/security-review-adapter/` is explicitly excluded; the final grep is the canonical check for the rest.
- **Release-please tag continuity.** First post-rename release will produce `dev-team-v*` and `security-assessment-v*` tags while history retains `agentic-*-v*`. Mitigation: release-please handles this when the component changes; documented in PR body.
- **Marketplace consumers pinning by old name.** Any external scripts or docs pinning `agentic-dev-team@bfinster` will break with a plugin-not-found error. Mitigation: README redirect notice (Step 6) plus migration sentence in marketplace plugin descriptions (Step 2).
