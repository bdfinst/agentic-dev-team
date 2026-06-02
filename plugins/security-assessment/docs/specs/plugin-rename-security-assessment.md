# Spec: Rename `agentic-security-review` → `agentic-security-assessment`

> **STATUS: landed 2026-04-24.** The rename has shipped. This spec is preserved for history. A mechanical sed pass during execution over-reached in directional references — some sentences now read `agentic-security-assessment → agentic-security-assessment` where they originally read `agentic-security-review → agentic-security-assessment`. Read `git show 9195f22` for the authoritative rename diff.
>
> **Source**: overlap analysis conducted 2026-04-24; Item 4 of the cleanup arising from the `security-review` agent vs. `agentic-security-review` plugin prefix collision.
> **Companion docs**: `docs/rule-id-audit.md`, `docs/rules-vs-prompts-policy.md`.
> **Cross-cutting**: touches 36 files across both plugins and repo-root config.

## Intent Description

The `agentic-security-assessment` plugin shares a prefix with the `security-review` agent that lives in the `agentic-dev-team` plugin. The collision consistently confuses readers: the plugin is "the security-review thing" in shorthand, the agent shares that shorthand, and documentation has to repeatedly disambiguate. The overlap analysis surfaced the terminology as a first-class concern.

Rename the plugin to `agentic-security-assessment` — this reflects what the plugin actually is (an orchestrated deep-assessment pipeline, not an inline review agent). Pure structural rename: no behavioral change, no primitives-contract bump, the agent name `security-review` stays stable (it's a contract-stable agent ID per `security-primitives-contract.md:36`).

Touches 36 files across the repository. Core change is a single `git mv` on the plugin directory; everything else is reference updates across manifests, config, docs, and install scripts.

## User-Facing Behavior

```gherkin
Feature: Plugin rename agentic-security-assessment → agentic-security-assessment

  Scenario: Marketplace install by new name succeeds
    When a user runs `claude plugin install agentic-security-assessment@bfinster`
    Then .claude-plugin/marketplace.json lists the plugin under the new name and source path
    And the install completes

  Scenario: Plugin directory moved with git history preserved
    Then plugins/agentic-security-assessment/ exists with all content
    And plugins/agentic-security-assessment/ does NOT exist
    And `git log --follow` on any moved file traces through the rename

  Scenario: Manifest reflects new name and MAJOR version
    Then plugins/agentic-security-assessment/.claude-plugin/plugin.json name == "agentic-security-assessment"
    And the version is bumped 0.3.0 → 1.0.0 (MAJOR, signals breaking consumers that depend on the old name)

  Scenario: Contract and agent unchanged
    Then plugins/agentic-dev-team/knowledge/security-primitives-contract.md version header is unchanged
    And the agent ID "security-review" continues to appear in the contract's registry
    And required-primitives-contract: "^1.0.0" is unchanged in the renamed plugin

  Scenario: All cross-references resolve (strict grep)
    When `grep -rln "agentic-security-assessment" --exclude-dir=.git --exclude=CHANGELOG.md` runs over the working tree
    Then it produces zero matches
    And every internal path reference resolves to the new location

  Scenario: In-flight work preserved
    Then plugins/agentic-security-assessment/docs/specs/recon-file-inventory.md exists (moved intact)
    And plugins/agentic-security-assessment/plans/recon-file-inventory.md exists (moved intact)
    And plugins/agentic-security-assessment/docs/specs/multi-language-sast.md exists (moved intact)
    And plugins/agentic-security-assessment/plans/multi-language-sast.md exists (moved intact)
    And this rename spec itself at plugins/agentic-security-assessment/docs/specs/plugin-rename-security-assessment.md exists (moved intact)
    And in-file references to the old plugin name have been updated

  Scenario: Release-please config points at new plugin path
    Then release-please-config.json references plugins/agentic-security-assessment/
    And .release-please-manifest.json references plugins/agentic-security-assessment/
    And conventional-commit scope updates to security-assessment (no preservation of old scope)

  Scenario: CHANGELOG captures the rename for users
    Then plugins/agentic-security-assessment/CHANGELOG.md has a top entry for 1.0.0
    And the entry documents the rename and the migration hint for users whose settings.local.json opt-out snippets reference the old path

  Scenario: Install scripts run cleanly at new path
    Then plugins/agentic-security-assessment/install.sh runs without path errors
    And install-macos.sh and install-windows.ps1 run without path errors

  Scenario: Clean cut — no stub at old path
    Then no file or directory remains at plugins/agentic-security-assessment/
    And the old marketplace entry is dropped entirely (not kept as deprecated)

  Scenario: Source prompt and repo-level plans updated in place
    Then .prompts/close-gaps-vs-opus-repo-scan.md references the new plugin name
    And plans/combined-plan-opus-4-7-security-review.md and plans/security-review-companion-plugin.md are renamed and their contents updated
```

## Architecture Specification

### Files that change (grouped by commit target)

**Plugin move** (one commit, `git mv`):

- `plugins/agentic-security-assessment/` → `plugins/agentic-security-assessment/` (whole directory; git preserves history for every file under it)

**Manifest updates** (one commit):

- `plugins/agentic-security-assessment/.claude-plugin/plugin.json` — `name` → `agentic-security-assessment`; `version` → `1.0.0`
- `.claude-plugin/marketplace.json` — plugin entry `name` and `source` path updated; old entry dropped (Q3 default)

**Release automation** (one commit):

- `release-please-config.json` — plugin path under the `packages` key renamed; conventional-commit scope updated to `security-assessment`
- `.release-please-manifest.json` — plugin path renamed; version bumped to match plugin.json

**Plugin-internal references** (one commit):

- `plugins/agentic-security-assessment/CLAUDE.md`
- `plugins/agentic-security-assessment/README.md`
- `plugins/agentic-security-assessment/CHANGELOG.md` — add 1.0.0 entry with migration note
- `plugins/agentic-security-assessment/install.sh`, `install-macos.sh`, `install-windows.ps1`
- `plugins/agentic-security-assessment/commands/{security-assessment,cross-repo-analysis,redteam-model,export-pdf}.md`
- `plugins/agentic-security-assessment/skills/compliance-mapping/SKILL.md`
- `plugins/agentic-security-assessment/knowledge/compliance-patterns.yaml`
- `plugins/agentic-security-assessment/hooks/static-scan-on-edit.sh`
- `plugins/agentic-security-assessment/docs/user-guide-security-assessment.md`
- `plugins/agentic-security-assessment/docs/comparative-testing.md`
- `plugins/agentic-security-assessment/docs/specs/{plugin-rename-security-assessment,recon-file-inventory,multi-language-sast}.md`
- `plugins/agentic-security-assessment/plans/{recon-file-inventory,multi-language-sast}.md`

**Cross-plugin references** (one commit):

- `plugins/agentic-dev-team/agents/security-review.md` — trigger-context section points at new plugin name
- `plugins/agentic-dev-team/knowledge/security-primitives-contract.md` — any path references (not contract content)
- `plugins/agentic-dev-team/knowledge/schemas/recon-envelope-v1.json` — descriptions/comments if any reference the old name

**Repo-level** (one commit):

- Root `README.md`
- `docs/rule-id-audit.md`, `docs/rules-vs-prompts-policy.md` (just created)
- `evals/comparative/README.md`, `evals/comparative/fixture-repo/ACCEPTED-RISKS.md`
- `scripts/run-assessment-local.sh`
- `.claude/settings.local.json` (committed project settings — update any path entries)

**Archival plans** (one commit, Q5 default — rename files AND update contents):

- `plans/combined-plan-opus-4-7-security-review.md` → `plans/combined-plan-opus-4-7-security-assessment.md`
- `plans/security-review-companion-plugin.md` → `plans/security-assessment-companion-plugin.md`
- In-file references updated

**Source prompt** (Q6 default — update inline):

- `.prompts/close-gaps-vs-opus-repo-scan.md` — update plugin-path references to the new name

### Files that do NOT change

- Agent ID `security-review` in `security-primitives-contract.md` registry
- Primitives contract version (`1.1.0` today, unchanged by this rename)
- `required-primitives-contract: ^1.0.0` in the renamed plugin's `plugin.json`
- `plugins/agentic-dev-team/CLAUDE.md`, any dev-team agent, any dev-team skill, any dev-team knowledge file other than the three listed above
- Primary contract schemas (`recon-envelope-v1.json`, `unified-finding-v1.json`, `disposition-register-v1.json`) except comment/description lines if any mention the old name

### Git + commit strategy

One PR, seven commits (one per group above). Each commit is individually reviewable and `git log --follow` traces every renamed file.

Commit scope per conventional-commits: **`refactor(security-assessment)`** on the rename commit; **`chore(release)`** on the release-please config change; **`docs(security-assessment)`** on doc updates; **`refactor!`** on the breaking manifest change (bang marker signals MAJOR bump).

### Version bump rationale

MAJOR bump (0.3.0 → 1.0.0) per Q1 default. The rename is breaking for any consumer that installs by name, references the plugin path, or has a checked-in `settings.local.json` opt-out. Pre-1.0 semver technically allows MINOR for breaking changes, but bumping to 1.0.0 at the rename communicates the break to external consumers cleanly.

### Blast radius and sequencing

The rename is cross-cutting but entirely mechanical. Every reference update is a find/replace of a literal string (`agentic-security-assessment` → `agentic-security-assessment`) plus a few stylized updates (e.g., conventional-commit scopes). The seven commits isolate categories so that any one can be reviewed or reverted in place.

Gap 6a (in flight) moves with the plugin but also needs updated in-file references — handled in the "in-flight work" commit. The already-persisted Gap 6a plan v2 must be updated to reflect new paths post-rename.

### Out of scope

- Changing the agent `security-review` name (it is contract-stable)
- Bumping the primitives contract version
- Modifying envelope schemas (other than comment-line name references if any)
- Deprecation stub at the old path (Q2 default — clean cut)
- Preserving old conventional-commit scope in release-please (Q4 default — switch clean)
- Deprecated marketplace entry (Q3 default — drop entirely)
- Renaming dev-team-internal files

### Risks

- **Users with checked-in `settings.local.json` opt-out snippets** referencing the old path will hit a mismatch on first post-rename session. Mitigated by CHANGELOG migration note; not fully automatable.
- **External forks or dependents** that install the plugin by name will break until they adopt the new name. MAJOR bump signals this; no runtime migration possible.
- **Release-please config drift** — if the config references the plugin by path or scope, the rename commit must update config atomically or release automation will emit for the wrong package. Mitigated by putting the config update in its own reviewable commit.

## Acceptance Criteria

- [ ] AC-1: `plugins/agentic-security-assessment/` no longer exists
- [ ] AC-2: `plugins/agentic-security-assessment/` exists with full content; `git log --follow` on a sample file traces through the rename
- [ ] AC-3: `plugins/agentic-security-assessment/.claude-plugin/plugin.json` name == `"agentic-security-assessment"`
- [ ] AC-4: `.claude-plugin/marketplace.json` entry shows new name and source; no entry for the old name remains
- [ ] AC-5: `grep -rln "agentic-security-assessment" --exclude-dir=.git --exclude=CHANGELOG.md` returns zero files
- [ ] AC-6: `required-primitives-contract: ^1.0.0` unchanged in plugin.json
- [ ] AC-7: `security-primitives-contract.md` version header unchanged
- [ ] AC-8: Release-please config + manifest reference `plugins/agentic-security-assessment/`; `release-please` dry-run (or config-parse check) emits no error
- [ ] AC-9: CHANGELOG 1.0.0 entry documents the rename and the opt-out migration hint
- [ ] AC-10: Gap 6a spec + plan + multi-language-sast spec + plan moved and their contents updated; paths in content match the new location
- [ ] AC-11: `install.sh`, `install-macos.sh`, `install-windows.ps1` dry-runs exit 0 at the new path
- [ ] AC-12: Version bumped to 1.0.0 per Q1
- [ ] AC-13: Archival plans renamed per Q5; in-file references updated
- [ ] AC-14: `.prompts/close-gaps-vs-opus-repo-scan.md` updated in place per Q6
- [ ] AC-15: New top-level docs (`docs/rule-id-audit.md`, `docs/rules-vs-prompts-policy.md`) reference the new plugin name

## Consistency Gate

- [x] Intent is unambiguous
- [x] Every behavior has a corresponding BDD scenario
- [x] Architecture constrains without over-engineering
- [x] Terminology consistent across artifacts
- [x] No contradictions between artifacts

**Gate: PASS (2026-04-24).** Proceeding to `/plan`.
