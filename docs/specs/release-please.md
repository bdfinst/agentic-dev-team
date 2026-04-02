# Specification: Automated Release Management with release-please

**Created**: 2026-04-02
**Status**: approved

## Intent Description

**What**: Add a GitHub Actions workflow that uses release-please to automate version bumping, CHANGELOG generation, and GitHub Release creation for the agentic-dev-team plugin repository.

**Why**: The repository currently has no release process — no git tags, no CHANGELOG, and no GitHub Releases. The husky pre-commit hook auto-increments a patch version on every commit, which produces meaningless version numbers. Adopting release-please will derive version bumps from conventional commit messages, produce a human-readable CHANGELOG, and create tagged GitHub Releases automatically when a release PR is merged.

**Scope**: Release-please integration only. No other CI workflows. No publishing beyond GitHub Releases. Husky is fully removed since it exists only for the auto-bump hook.

## User-Facing Behavior

```gherkin
Feature: Automated release management with release-please

  Scenario: Release PR is created from conventional commits
    Given the main branch has new commits since the last release
    And at least one commit uses a releasable prefix (feat, fix, refactor, perf)
    When a push to main triggers the release-please workflow
    Then release-please opens or updates a "release PR" on GitHub
    And the PR title contains the next version number
    And the PR body contains a generated CHANGELOG

  Scenario: GitHub Release is created when release PR is merged
    Given a release-please PR exists and is approved
    When the release PR is merged to main
    Then a GitHub Release is created with the new version tag
    And the release notes contain the CHANGELOG entries
    And plugin.json version is updated to match the release version
    And marketplace.json version is updated to match the release version

  Scenario: Version bump follows conventional commit semantics
    Given commits since the last release include a "feat:" commit
    Then the minor version is incremented
    Given commits since the last release include only "fix:" commits
    Then the patch version is incremented
    Given commits since the last release include a breaking change
    Then the major version is incremented

  Scenario: Non-releasable commits are excluded from CHANGELOG
    Given the main branch has only non-releasable commits (docs, chore, ci)
    When a push to main triggers the release-please workflow
    Then no release PR is created or updated
    And docs commits do not appear in the CHANGELOG

  Scenario: Husky and auto-bump hook are fully removed
    When release-please owns versioning
    Then the .husky directory no longer exists
    And husky is removed from devDependencies
    And package.json is removed from the repository
    And plugin.json version is only updated by release-please
```

## Architecture Specification

**Components affected**:
1. `.github/workflows/release-please.yml` — new GitHub Actions workflow
2. `release-please-config.json` — configuration (changelog sections, extra-files)
3. `.release-please-manifest.json` — tracks current version, seeded from current plugin.json
4. `.claude-plugin/plugin.json` — version managed by release-please
5. `.claude-plugin/marketplace.json` — version managed by release-please via `extra-files` with JSONPath (`.plugins[0].version`)
6. `.husky/` — entire directory removed
7. `package.json` — removed (only existed for husky devDependency)

**Interfaces**:
- release-please reads conventional commits from git history on `main`
- release-please writes version to `plugin.json` and `marketplace.json` via `extra-files`
- Trigger: `push` to `main` branch

**Constraints**:
- Version source of truth: `plugin.json`
- `docs:` commits excluded from CHANGELOG (configure `changelog-sections`)
- Initial version seeded from current `plugin.json` value
- Workflow permissions: `contents: write`, `pull-requests: write`

**Dependencies**:
- `google-github-actions/release-please-action` v4

## Acceptance Criteria

- [ ] A push to `main` with releasable commits creates/updates a release PR
- [ ] Merging the release PR creates a GitHub Release with a semver tag (e.g., `v1.3.1`)
- [ ] The release PR updates `plugin.json` and `marketplace.json` versions
- [ ] CHANGELOG excludes `docs:`, `chore:`, and `ci:` commits
- [ ] Non-releasable commits do not trigger a version bump or release PR
- [ ] `.husky/` directory is fully removed
- [ ] `package.json` is removed
- [ ] Initial release version is seeded from current `plugin.json` version
