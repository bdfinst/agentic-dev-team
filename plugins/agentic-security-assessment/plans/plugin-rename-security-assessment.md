# Plan: Rename plugin `agentic-security-assessment` → `agentic-security-assessment`

**Created**: 2026-04-24
**Branch**: main
**Status**: paused — accepted strategic blocker on 2026-04-24; sequence behind Item 5 (agent `rule_id` / adapter gap) and any near-merge in-flight work. Resume this plan when: (a) Item 5 has shipped, and (b) in-flight branches touching `plugins/agentic-security-assessment/` have merged or been explicitly cleared for rebase.
**Spec**: `plugins/agentic-security-assessment/docs/specs/plugin-rename-security-assessment.md`
**Cross-plugin**: touches `agentic-dev-team/` (name-reference updates only, no behavioral change)

## Goal

Execute the structural rename of the companion plugin from `agentic-security-assessment` to `agentic-security-assessment` to eliminate the prefix collision with the `security-review` agent that lives in `agentic-dev-team`. Pure mechanical change: `git mv` of one directory plus find/replace of one literal string across 36 files, with a MAJOR version bump (0.3.0 → 1.0.0) on the plugin manifest to signal the breaking name change to external consumers. No behavioral change, no contract bump, agent name unchanged.

## Acceptance Criteria

Directly from the spec (AC-1 … AC-15). Every step below closes one or more ACs.

- [ ] AC-1: `plugins/agentic-security-assessment/` no longer exists
- [ ] AC-2: `plugins/agentic-security-assessment/` exists with full content; `git log --follow` traces through the rename
- [ ] AC-3: `plugins/agentic-security-assessment/.claude-plugin/plugin.json` name == `"agentic-security-assessment"`
- [ ] AC-4: `.claude-plugin/marketplace.json` entry shows new name and source; no entry for the old name remains
- [ ] AC-5: `grep -rln "agentic-security-assessment" --exclude-dir=.git --exclude=CHANGELOG.md` returns zero files
- [ ] AC-6: `required-primitives-contract: ^1.0.0` unchanged in `plugin.json`
- [ ] AC-7: `security-primitives-contract.md` version header unchanged
- [ ] AC-8: `release-please-config.json` + `.release-please-manifest.json` reference `plugins/agentic-security-assessment/`; `release-please` dry-run succeeds
- [ ] AC-9: CHANGELOG 1.0.0 entry documents the rename and opt-out migration hint
- [ ] AC-10: Gap 6a spec + plan + multi-language-sast spec + plan moved with the directory and their contents updated
- [ ] AC-11: `install.sh`, `install-macos.sh`, `install-windows.ps1` dry-runs exit 0 at the new path
- [ ] AC-12: Version bumped to `1.0.0`
- [ ] AC-13: Archival plans renamed (`plans/combined-plan-opus-4-7-security-review.md` → `...-assessment.md`; `plans/security-review-companion-plugin.md` → `security-assessment-companion-plugin.md`); in-file references updated
- [ ] AC-14: `.prompts/close-gaps-vs-opus-repo-scan.md` updated in place
- [ ] AC-15: New top-level docs (`docs/rule-id-audit.md`, `docs/rules-vs-prompts-policy.md`) reference the new plugin name

## User-Facing Behavior

(Verbatim from spec.)

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
    And the version is bumped 0.3.0 → 1.0.0

  Scenario: Contract and agent unchanged
    Then plugins/agentic-dev-team/knowledge/security-primitives-contract.md version header is unchanged
    And the agent ID "security-review" continues to appear in the contract's registry
    And required-primitives-contract: "^1.0.0" is unchanged in the renamed plugin

  Scenario: All cross-references resolve (strict grep)
    When `grep -rln "agentic-security-assessment" --exclude-dir=.git --exclude=CHANGELOG.md` runs over the working tree
    Then it produces zero matches

  Scenario: In-flight work preserved
    Then plugins/agentic-security-assessment/docs/specs/recon-file-inventory.md exists (moved intact)
    And plugins/agentic-security-assessment/plans/recon-file-inventory.md exists (moved intact)
    And plugins/agentic-security-assessment/docs/specs/multi-language-sast.md exists (moved intact)
    And plugins/agentic-security-assessment/plans/multi-language-sast.md exists (moved intact)
    And this rename spec/plan itself at plugins/agentic-security-assessment/{docs/specs,plans}/plugin-rename-security-assessment.md exists (moved intact)
    And in-file references to the old plugin name have been updated

  Scenario: Release-please config points at new plugin path
    Then release-please-config.json references plugins/agentic-security-assessment/
    And .release-please-manifest.json references plugins/agentic-security-assessment/
    And conventional-commit scope updates to security-assessment

  Scenario: CHANGELOG captures the rename for users
    Then plugins/agentic-security-assessment/CHANGELOG.md has a top entry for 1.0.0
    And the entry documents the rename and the migration hint for users whose settings.local.json opt-out snippets reference the old path

  Scenario: Install scripts run cleanly at new path
    Then plugins/agentic-security-assessment/install.sh runs without path errors
    And install-macos.sh and install-windows.ps1 run without path errors

  Scenario: Clean cut — no stub at old path
    Then no file or directory remains at plugins/agentic-security-assessment/
    And the old marketplace entry is dropped entirely

  Scenario: Source prompt and repo-level plans updated in place
    Then .prompts/close-gaps-vs-opus-repo-scan.md references the new plugin name
    And plans/combined-plan-opus-4-7-security-review.md and plans/security-review-companion-plugin.md are renamed and their contents updated
```

## Test harness note

The test scripts for this rename live under `evals/plugin-rename/tests/` at repo root (not inside the plugin) so they survive the directory move unaffected. Each step's RED test is a short shell script; each GREEN moves the corresponding change into place; each test is one-shot — they exist to gate this PR, and can be removed post-merge or retained as regression guards against accidental re-introduction of the old name.

Every RED is validated against the pre-change state before GREEN is applied, so no step rubber-stamps.

## Steps

### Step 1: Atomic structural move — directory + manifests + release config

**Complexity**: complex

The spec listed this as three separate commits. The plan consolidates them because splitting leaves the repo in an installable-but-broken intermediate state (plugin moved but marketplace entry still pointing at old path). Atomic move keeps the invariant "any commit is a working checkout."

**RED**:

- Create `evals/plugin-rename/tests/structural-move.sh`:
  - Assert `[ ! -d plugins/agentic-security-assessment ]`
  - Assert `[ -d plugins/agentic-security-assessment ]`
  - Assert `jq -r .name plugins/agentic-security-assessment/.claude-plugin/plugin.json` == `"agentic-security-assessment"`
  - Assert `jq -r .version plugins/agentic-security-assessment/.claude-plugin/plugin.json` == `"1.0.0"`
  - Assert `jq -r '.plugins[] | select(.name=="agentic-security-assessment") | .source' .claude-plugin/marketplace.json` == `"./plugins/agentic-security-assessment"`
  - Assert `jq -e '.plugins[] | select(.name=="agentic-security-assessment")' .claude-plugin/marketplace.json` — must return exit 1 (no old entry)
  - Assert `grep -q 'plugins/agentic-security-assessment' release-please-config.json`
  - Assert `grep -q 'plugins/agentic-security-assessment' .release-please-manifest.json`
  - Assert `! grep -q 'plugins/agentic-security-assessment' release-please-config.json`
  - Assert `! grep -q 'plugins/agentic-security-assessment' .release-please-manifest.json`
- Create `evals/plugin-rename/tests/release-please-precommit.sh` — **pre-commit gate for release-please behavior** (addresses R1 + acceptance blocker):
  - Read `release-please-config.json`; assert `refactor` appears in the `changelog-sections` OR `extra-types` array for the plugin's package entry, so that `refactor!:` commits trigger a release. If absent, the script prints a specific error: "release-please config does not treat `refactor` as a releasable type; add it or change Step 1 commit to `feat!:`".
  - Stage the Step 1 edits in a working copy (do not commit yet). Run `npx release-please release-pr --dry-run --config-file release-please-config.json --manifest-file .release-please-manifest.json --token=dummy` (or the equivalent local validator) against the staged state.
  - Assert the dry-run output identifies the renamed package path as an **update** to the existing package lineage, not as a new package creation. Heuristic: grep dry-run output for "new package" or "initial release" — if matched against the renamed path, fail.
  - Assert `npx release-please --help` at least loads (checks the tool is available; else skip with a clear notice and document as manual confirmation).
- Run both tests pre-change. Every assertion fails. **Do not proceed until the failures are observed.**

**GREEN**:

- **Pre-commit gate (blocks the commit until passing):**
  1. Apply the Step 1 edits to the working tree (as described below) WITHOUT committing.
  2. Run `evals/plugin-rename/tests/release-please-precommit.sh`. If it fails, DO NOT COMMIT — revert the staged edits, fix the config (add `refactor` as a releasable type, or switch the commit convention to `feat!:`), and re-run. Only proceed to commit after the gate passes.
- Edits applied:
  - `git mv plugins/agentic-security-assessment plugins/agentic-security-assessment`
  - Edit `plugins/agentic-security-assessment/.claude-plugin/plugin.json`: `name` → `"agentic-security-assessment"`; `version` → `"1.0.0"`
  - Edit `.claude-plugin/marketplace.json`: rename the plugin entry's `name` + `source`; delete any stale entry for the old name
  - Edit `release-please-config.json`: every occurrence of `plugins/agentic-security-assessment` → `plugins/agentic-security-assessment`; conventional-commit scope `security-review` → `security-assessment`; if `refactor` is not already a releasable type, add it under `changelog-sections` / `extra-types` so the Step 1 commit emits a release
  - Edit `.release-please-manifest.json`: rename the path key; preserve the version value that belongs to this plugin
- Run `evals/plugin-rename/tests/structural-move.sh`. All assertions pass.
- Commit.
- Run `evals/plugin-rename/tests/release-please-precommit.sh` one more time against the committed state for confirmation.

**REFACTOR**: None.
**Files**: whole plugin directory (moved); `.claude-plugin/marketplace.json`; `release-please-config.json`; `.release-please-manifest.json`; `evals/plugin-rename/tests/structural-move.sh` (new); `evals/plugin-rename/tests/release-please-precommit.sh` (new)
**Commit**: `refactor(security-assessment)!: rename plugin + bump to 1.0.0 + update release config`
**Commit body note**: Include a one-line reviewer note: "Scope `security-assessment` is introduced atomically with this commit. Release-please parses the new scope correctly per pre-commit dry-run."

### Step 2: Plugin-internal reference updates

**Complexity**: standard

The plugin's own files still contain the string `agentic-security-assessment` in prose, install snippets, cross-references, and the moved in-flight spec/plan files.

**RED**:

- Create `evals/plugin-rename/tests/internal-refs-clean.sh`:
  - Run `grep -rln 'agentic-security-assessment' plugins/agentic-security-assessment/ --exclude=CHANGELOG.md`
  - Assert output is empty (exit 1 from the grep)
- Run pre-change. Grep returns a list of ~15 files (CLAUDE.md, README.md, install scripts, commands, skills, docs, specs, plans, etc.). Test fails.

**GREEN**:

- `git grep -l 'agentic-security-assessment' -- plugins/agentic-security-assessment/ | grep -v CHANGELOG.md | xargs sed -i '' 's|agentic-security-assessment|agentic-security-assessment|g'` (on macOS; Linux drops the empty-string argument to `-i`)
- Visual check of the diff for any context where the literal string must remain (CHANGELOG migration notes are excluded above; any other legitimate historical reference should be explicitly preserved with a comment)
- Add CHANGELOG entry to `plugins/agentic-security-assessment/CHANGELOG.md` with the following **required structure** (addresses UX warning on migration discoverability):

  ```markdown
  ## 1.0.0 — RENAMED from `agentic-security-assessment` (2026-04-24)

  ### BREAKING CHANGE — plugin rename

  The plugin has been renamed from `agentic-security-assessment` to `agentic-security-assessment` to eliminate the prefix collision with the `security-review` agent in `agentic-dev-team`. The agent name is contract-stable and did not move.

  ### Migration

  Existing users must update the following references:

  1. `claude plugin install`: `agentic-security-assessment@bfinster` → `agentic-security-assessment@bfinster`
  2. `.claude/settings.local.json` opt-out snippets referencing `plugins/agentic-security-assessment/` → `plugins/agentic-security-assessment/`
  3. Any automation or docs citing the plugin path or name

  Link to spec: `plugins/agentic-security-assessment/docs/specs/plugin-rename-security-assessment.md`.
  ```

- Extend `install.sh` with a post-install check (addresses UX warning on stale opt-out snippets): grep the user's `$HOME/.claude/settings.local.json` and `./.claude/settings.local.json` for `agentic-security-assessment`. If found, print a one-line warning: `WARN: your settings.local.json references the old plugin name. Update to 'agentic-security-assessment'. See CHANGELOG 1.0.0.` Non-blocking; advisory only.
- Run the test. Passes.

**REFACTOR**: None — the blanket sed is safe because the string is distinctive and the CHANGELOG exclusion covers the one legitimate-historical case.
**Files**: ~15 files under `plugins/agentic-security-assessment/` including the in-flight Gap 6a spec, the Gap 6a plan, multi-language-sast spec + plan, all 4 commands, hooks, install scripts, CLAUDE.md, README.md, compliance-patterns.yaml, skill, user-guide, comparative-testing; plus `CHANGELOG.md` entry
**Commit**: `docs(security-assessment): update internal references to new plugin name + CHANGELOG 1.0.0 entry`

### Step 3: Cross-plugin reference updates in `agentic-dev-team`

**Complexity**: standard

Three dev-team files reference the old plugin name: the `security-review` agent's trigger-context section (just added), the primitives contract's cross-references, and the recon envelope schema description.

**RED**:

- Create `evals/plugin-rename/tests/cross-plugin-refs-clean.sh`:
  - Run `grep -rln 'agentic-security-assessment' plugins/agentic-dev-team/`
  - Assert output is empty
- Run pre-change. Grep returns 3 files. Test fails.

**GREEN**:

- `git grep -l 'agentic-security-assessment' -- plugins/agentic-dev-team/ | xargs sed -i '' 's|agentic-security-assessment|agentic-security-assessment|g'`
- Verify `security-primitives-contract.md` agent registry still has `security-review` as an agent ID (unchanged) while path references updated to the new plugin name
- Verify the contract version header is unchanged (AC-7)
- Run the test. Passes.

**REFACTOR**: None.
**Files**: `plugins/agentic-dev-team/agents/security-review.md`, `plugins/agentic-dev-team/knowledge/security-primitives-contract.md`, `plugins/agentic-dev-team/knowledge/schemas/recon-envelope-v1.json`
**Commit**: `docs(agentic-dev-team): update cross-references to renamed companion plugin`

### Step 4: Repo-level reference updates

**Complexity**: standard

Repo-root files and tooling outside either plugin carry the old name: root README, evals fixture repo docs, shell scripts, new top-level docs (rule-id-audit, rules-vs-prompts-policy), settings.local.json.

**RED**:

- Create `evals/plugin-rename/tests/repo-level-refs-clean.sh`:
  - Run `grep -rln 'agentic-security-assessment' --exclude-dir=.git --exclude-dir=plugins --exclude-dir=.prompts --exclude-dir=plans --exclude=CHANGELOG.md .`
  - Assert output is empty
- Pre-change: returns ~8 files. Test fails.

**GREEN**:

- `git grep -l 'agentic-security-assessment' -- ':!plugins/' ':!.prompts/' ':!plans/' ':!**/CHANGELOG.md' | xargs sed -i '' 's|agentic-security-assessment|agentic-security-assessment|g'`
- Verify: root README, `docs/rule-id-audit.md`, `docs/rules-vs-prompts-policy.md`, `evals/comparative/README.md`, `evals/comparative/fixture-repo/ACCEPTED-RISKS.md`, `scripts/run-assessment-local.sh`, `.claude/settings.local.json`
- Run the test. Passes.

**REFACTOR**: None.
**Files**: root-level docs + evals + scripts + settings (~7-8 files)
**Commit**: `docs: update repo-level references to renamed plugin`

### Step 5: Archival plans rename + source prompt update

**Complexity**: trivial

The two historical plans at repo-level `plans/` carry the old name in both filename and content; the source prompt at `.prompts/close-gaps-vs-opus-repo-scan.md` references the old plugin path.

**RED**:

- Create `evals/plugin-rename/tests/archival-and-prompt-clean.sh`:
  - Assert `[ -f plans/combined-plan-opus-4-7-security-assessment.md ]` and `[ ! -f plans/combined-plan-opus-4-7-security-review.md ]`
  - Assert `[ -f plans/security-assessment-companion-plugin.md ]` and `[ ! -f plans/security-review-companion-plugin.md ]`
  - Run `grep -l 'agentic-security-assessment' .prompts/close-gaps-vs-opus-repo-scan.md plans/combined-plan-opus-4-7-security-assessment.md plans/security-assessment-companion-plugin.md`
  - Assert empty
- Pre-change: three assertions fail. Test fails.

**GREEN**:

- `git mv plans/combined-plan-opus-4-7-security-review.md plans/combined-plan-opus-4-7-security-assessment.md`
- `git mv plans/security-review-companion-plugin.md plans/security-assessment-companion-plugin.md`
- `sed -i '' 's|agentic-security-assessment|agentic-security-assessment|g' .prompts/close-gaps-vs-opus-repo-scan.md plans/combined-plan-opus-4-7-security-assessment.md plans/security-assessment-companion-plugin.md`
- Run the test. Passes.

**REFACTOR**: None.
**Files**: the two archival plan files (moved + edited); `.prompts/close-gaps-vs-opus-repo-scan.md` (edited)
**Commit**: `docs(plans): rename archival plans + source prompt to new plugin name`

### Step 6: Final global cleanliness check + in-flight plan path fix-ups

**Complexity**: trivial

Catch-all: the repo's entire working tree (excluding git history, CHANGELOG, and archived material that uses the old name intentionally) must be free of the literal `agentic-security-assessment`. Also: the Gap 6a plan's in-file path references, which moved to the new plugin path in Step 2 but may reference old paths in prose — verify.

**RED**:

- Create `evals/plugin-rename/tests/final-global-grep.sh`:
  - Run `grep -rln 'agentic-security-assessment' --exclude-dir=.git --exclude=CHANGELOG.md .`
  - Assert the output is empty
- Create `evals/plugin-rename/tests/gap-6a-plan-paths.sh`:
  - For each path pattern that appeared in the Gap 6a plan, assert it resolves (file exists at `plugins/agentic-security-assessment/...`) or is a known dev-team path
  - Specifically verify: `plugins/agentic-security-assessment/docs/specs/recon-file-inventory.md`, `plugins/agentic-security-assessment/plans/recon-file-inventory.md`, and that the plan's internal references to the spec path match
- Pre-change: if Steps 2-5 were done correctly, grep is already clean; but the plan-path check may still fail if any in-file reference was missed (e.g., the Gap 6a plan references `plugins/agentic-security-assessment/plans/recon-file-inventory.md` in prose — the sed in Step 2 would have caught it, but verify).
- Run both tests. If they pass after Steps 1-5, GREEN here is a no-op assertion. If either fails, fix the specific residual.

**GREEN**:

- If `final-global-grep` finds anything, fix the specific files. Likely candidates: stylized references (`agentic_security_review` with underscore — would NOT match the hyphen-form grep, so not a concern; but worth a second grep for that variant as a sanity check).
- If `gap-6a-plan-paths` finds stale paths, fix them with targeted edits.
- Run the tests. Pass.

**REFACTOR**: None.
**Files**: any residual (expected: 0-2)
**Commit**: `docs: residual cleanup after plugin rename` (or skipped if no residual)

### Step 7: Spec-AC sweep + release-please dry-run

**Complexity**: trivial

Run every AC from the spec and release-please's own dry-run / config-parse as the final gate.

**RED**:

- Create `evals/plugin-rename/tests/all-acs.sh`:
  - AC-1: `[ ! -d plugins/agentic-security-assessment ]`
  - AC-2: `[ -d plugins/agentic-security-assessment ]`; `git log --follow plugins/agentic-security-assessment/.claude-plugin/plugin.json | head -5` returns non-empty
  - AC-3: `jq -r .name plugins/agentic-security-assessment/.claude-plugin/plugin.json` == `"agentic-security-assessment"`
  - AC-4: marketplace jq checks (from Step 1, repeated)
  - AC-5: final grep (from Step 6, repeated)
  - AC-6: `grep -q '"required-primitives-contract": "\^1.0.0"' plugins/agentic-security-assessment/.claude-plugin/plugin.json`
  - AC-7: contract version header unchanged — `grep -c '^version: 1.1.0' plugins/agentic-dev-team/knowledge/security-primitives-contract.md` equals 1
  - AC-8: release-please config/manifest checks (from Step 1); plus `npx release-please release-pr --dry-run --token=dry` exits 0 (or equivalent local validation)
  - AC-9: `grep -q '## 1\.0\.0' plugins/agentic-security-assessment/CHANGELOG.md`; `grep -qi 'renamed from' plugins/agentic-security-assessment/CHANGELOG.md`; `grep -qi 'settings.local.json' plugins/agentic-security-assessment/CHANGELOG.md`
  - AC-10: four in-flight files exist at `plugins/agentic-security-assessment/{docs/specs,plans}/{recon-file-inventory,multi-language-sast}.md`; `grep -L 'agentic-security-assessment' <each>` returns all files
  - AC-11: `bash plugins/agentic-security-assessment/install.sh --dry-run` exits 0; macOS + Windows equivalents noted (Windows can't be run in CI on macOS — accept manual confirmation + `pwsh -File ... -DryRun` if pwsh is installed)
  - AC-12: plugin.json version == 1.0.0 (from Step 1)
  - AC-13: both archival plans renamed; clean grep (from Step 5)
  - AC-14: `.prompts/close-gaps-vs-opus-repo-scan.md` grep clean
  - AC-15: `docs/rule-id-audit.md` and `docs/rules-vs-prompts-policy.md` grep clean + positive reference to new name
- Pre-GREEN: if Steps 1-6 are complete, all 15 ACs pass. If not, the failing AC names the missing step.

**GREEN**:

- Fix any missed AC.
- Run `evals/plugin-rename/tests/all-acs.sh`. All pass.

**REFACTOR**: Consider moving `evals/plugin-rename/tests/*.sh` to a single consolidated `evals/plugin-rename/all-tests.sh` driver if the individual scripts are noisy.

**Files**: `evals/plugin-rename/tests/all-acs.sh` (new)
**Commit**: `test(security-assessment): AC sweep confirms rename complete`

## Complexity Classification

| Step | Rating | Rationale |
| ---- | -------- | --------- |
| 1 | complex | Atomic structural move across plugin dir + three config files; largest blast radius in one commit |
| 2 | standard | Blanket sed across ~15 files; straightforward but high-volume |
| 3 | standard | Three files in the sister plugin; needs care not to touch contract version or agent ID |
| 4 | standard | Repo-level refs; ~7-8 files |
| 5 | trivial | Two `git mv` + one sed |
| 6 | trivial | Residual cleanup, expected no-op if prior steps were clean |
| 7 | trivial | AC sweep; no new behavior |

## Pre-PR Quality Gate

- [ ] All `evals/plugin-rename/tests/*.sh` pass
- [ ] All 15 ACs from spec pass via `all-acs.sh`
- [ ] `release-please` dry-run (or `release-please-config.json` schema validation) emits no error
- [ ] `git log --follow plugins/agentic-security-assessment/.claude-plugin/plugin.json` traces through the rename
- [ ] Manual: install via `claude plugin install agentic-security-assessment@bfinster` on a clean workspace (or equivalent local-path install) and run `/security-assessment` smoke test
- [ ] Manual: install scripts (`install.sh`, `install-macos.sh`, `install-windows.ps1`) run without error at the new path
- [ ] CHANGELOG entry visible
- [ ] `/code-review` passes on the diff

## Risks & Open Questions

| # | Type | Item | Mitigation / Owner |
|---|---|---|---|
| R1 | Risk (high) | release-please history tracking is keyed by path in `.release-please-manifest.json`. Renaming the path atomically in Step 1 should preserve history, but the exact behavior depends on release-please's interpretation of "new package with same version." Validate before merge. | Step 1 GREEN includes a dry-run invocation to confirm. If dry-run treats this as a new package, pause and consult release-please docs; options include keeping both paths transiently or accepting a history reset. |
| R2 | Risk | `sed -i ''` syntax is macOS BSD; Linux expects `sed -i`. CI may run on Linux. | Use a portable helper: `sed -i.bak 's|...|...|g' FILE && rm FILE.bak` works on both. Document in Step 2 GREEN. |
| R3 | Risk | Case-sensitivity on macOS filesystems: `git mv` with only case-different names is tricky. This rename is a full name change (review → assessment), so not affected, but worth noting. | No action. |
| R4 | Open | Users with committed `.claude/settings.local.json` opt-out snippets referencing the old PostToolUse matcher path will have stale config. Not automatable. | CHANGELOG migration note addresses this (AC-9). |
| R5 | Open | External forks / users who install by name will break until they adopt the new name. MAJOR bump signals this; no further migration possible. | CHANGELOG 1.0.0 entry; implicit by MAJOR bump. |
| R6 | Open | AC-11 Windows install-script dry-run (`install-windows.ps1 -DryRun`) cannot be executed on macOS CI. | Accept manual attestation in the PR description on a Windows host, or skip AC-11.ps1 in automated check and note in PR. |
| R7 | Open | Step 1 commit is large (whole directory rename + 3 config files). Reviewers may prefer finer granularity. | Spec's original 3-commit split is available if preferred; note that splitting leaves an intermediate broken state. Operator may override. |
| R8 | Open | The Gap 6a plan (pending approval, v2) references paths that will change mid-stream. This rename plan is a logical precondition for Gap 6a's implementation. | After this plan completes, update the Gap 6a plan's paths in a short follow-up edit (per the user's earlier instruction). Listed explicitly. |
| R9 | Open | This plan's own spec and plan files live inside the plugin being moved. They'll be relocated by Step 1 to the new path. The plan's "Spec" reference at the top is stale after Step 1. | Accept as minor; the plan is a one-shot artifact. Alternatively, move these two files to `docs/specs/` and `plans/` at repo root before Step 1 — adds complexity for no real benefit. |

## Plan Review Summary

Four personas ran in parallel against v1.

### Verdicts

| Reviewer | Verdict | Notes |
|---|---|---|
| Acceptance Test Critic | needs-revision (1 blocker) | release-please dry-run was deferred to Step 7 (post-commit) despite R1 flagging it high-risk |
| Design & Architecture Critic | approve with warnings | same dry-run concern (warning-level), scope-intro in same commit |
| UX Critic | needs-revision (0 blockers) | all three items warning-level: install-by-old-name dead-ends, stale opt-out snippets, CHANGELOG entry structure |
| Strategic Critic | needs-revision (1 blocker) | sequencing: Item 5 (agent rule_id / adapter gap) is a functional dedup-blocker and should ship first |

### Blockers resolved in v2

| Reviewer | Blocker | Resolution |
|---|---|---|
| Acceptance | release-please dry-run deferred to Step 7 | Added `release-please-precommit.sh` as Step 1 RED pre-commit gate; commit is blocked until dry-run confirms the rename is parsed as an existing-package update (not new package) and `refactor!` is a releasable type |

### Blocker requiring user decision (cannot be fixed in-plan)

| Reviewer | Blocker | Decision required |
|---|---|---|
| Strategic | Item 5 (agent rule_id / adapter gap) should sequence before this rename | User already decided to proceed with rename; this blocker is a second opportunity to reconsider. Rationale: Item 5 is functional (unblocks dedup); rename is cosmetic. In-flight work (Gap 6a, multi-language-sast) will need rebasing either way. |

### UX warnings addressed in v2

- CHANGELOG entry structure: v2 specifies explicit format with `BREAKING CHANGE` + `Migration` subsections, anchoring the migration note at the top of the entry.
- Install-time warning: `install.sh` will grep users' `settings.local.json` for old-name references and print a one-line advisory. Non-blocking.

### Warnings surfaced (not addressed — user discretion)

- **Strategic**: MAJOR bump (0.3.0 → 1.0.0) may be premature if plugin lacks external adoption; pre-1.0 semver permits MINOR bump for breaking changes. User call on signaling vs preserving pre-1.0 optionality.
- **Strategic**: Step 1 could be split into two commits (structural move + manifest in one; release config in another) — each a working checkout. Current plan keeps consolidated for simplicity.
- **UX**: Install-by-old-name post-rename dead-ends with generic "not found" error. Keeping a short-lived deprecated marketplace entry would redirect users — v2 stays with clean cut per spec Q3 default.
- **Acceptance**: Error-path scenarios for `git mv` collision, sed missing a file due to binary-detection, and release-please rename-preservation are not explicitly scripted; Step 1 and Step 6 failure modes cover them implicitly.
- **Design**: Sibling spec/plan files relocate with the plugin (R9). Plan accepts this as minor.

### Observations

- Atomic move + git-history preservation is the correct design contract (Design critic).
- Test harness location at repo root is the right dependency direction (Design critic).
- Cross-plugin boundary in Step 3 is clean: name-string references only, no contract version change (Design critic).
- MAJOR bump correctly signals break to semver-aware consumers (UX critic).
