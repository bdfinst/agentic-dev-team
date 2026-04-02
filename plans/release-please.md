# Plan: Automated Release Management with release-please

**Created**: 2026-04-02
**Branch**: main
**Status**: approved
**Spec**: [docs/specs/release-please.md](../docs/specs/release-please.md)

## Goal

Add release-please to automate version bumping, CHANGELOG generation, and GitHub Release creation. Remove husky and package.json since they only existed for the now-replaced auto-bump hook. After this, merging a release PR to main produces a tagged GitHub Release with a CHANGELOG derived from conventional commits.

## Acceptance Criteria

- [ ] A push to `main` with releasable commits creates/updates a release PR
- [ ] Merging the release PR creates a GitHub Release with a semver tag (e.g., `v1.2.17`)
- [ ] The release PR updates `plugin.json` and `marketplace.json` versions
- [ ] CHANGELOG excludes `docs:`, `chore:`, and `ci:` commits
- [ ] Non-releasable commits do not trigger a version bump or release PR
- [ ] `.husky/` directory is fully removed
- [ ] `package.json` is removed
- [ ] Initial release version is seeded at `1.2.16` (current plugin.json version)

## Steps

### Step 1: Remove husky and package.json

**Complexity**: trivial
**RED**: N/A — removal only, no testable behavior
**GREEN**: Delete `.husky/` directory, `package.json`, and `node_modules/` (husky). Remove `node_modules/` from tracked files if present.
**REFACTOR**: None needed
**Files**: `.husky/` (delete), `package.json` (delete)
**Commit**: `chore: remove husky and package.json — versioning now owned by release-please`

### Step 2: Add release-please configuration

**Complexity**: standard
**RED**: Validate config files are well-formed JSON matching release-please schema (manual or CI validation)
**GREEN**: Create `release-please-config.json` with:
  - `release-type`: `simple`
  - `extra-files`: `[".claude-plugin/plugin.json", {"path": ".claude-plugin/marketplace.json", "jsonpath": "$.plugins[0].version"}]`
  - `changelog-sections`: exclude `docs`, `chore`, `ci`, `style`, `test` from CHANGELOG
  - `include-component-in-tag`: false
  - `include-v-in-tag`: true

Create `.release-please-manifest.json` seeded with: `{".": "1.2.16"}`
**REFACTOR**: None needed
**Files**: `release-please-config.json` (create), `.release-please-manifest.json` (create)
**Commit**: `ci: add release-please configuration seeded at v1.2.16`

### Step 3: Add GitHub Actions workflow

**Complexity**: standard
**RED**: Validate workflow YAML syntax (actionlint or manual review)
**GREEN**: Create `.github/workflows/release-please.yml`:
  - Trigger: `push` to `main`
  - Uses: `google-github-actions/release-please-action@v4`
  - Permissions: `contents: write`, `pull-requests: write`
  - Config file: `release-please-config.json`
  - Manifest file: `.release-please-manifest.json`
**REFACTOR**: None needed
**Files**: `.github/workflows/release-please.yml` (create)
**Commit**: `ci: add release-please GitHub Actions workflow`

## Pre-PR Quality Gate

- [ ] All config files are valid JSON
- [ ] Workflow YAML passes syntax check
- [ ] No references to husky remain in the codebase
- [ ] `/code-review --changed` passes
- [ ] Documentation updated (if applicable)

## Risks & Open Questions

- **Risk**: release-please `extra-files` with JSONPath for `marketplace.json` nested at `$.plugins[0].version` — if the JSONPath syntax doesn't match release-please's expectations, the version won't sync. **Mitigation**: Test by pushing a feat commit after merging and verify the release PR updates both files.
- **Risk**: Removing `package.json` may break something unexpected (e.g., tooling that reads it). **Mitigation**: Grep the codebase for `package.json` references before deleting.
- **Open question**: Should `refactor:` and `perf:` commits appear in the CHANGELOG? release-please includes them by default. Recommend keeping them since they represent meaningful changes.
