#!/usr/bin/env bash
# Assemble scattered markdown sources into _mkdocs_src/ for MkDocs to build.
# Preserves the same relative paths so mkdocs.yml nav entries need no changes.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${REPO_ROOT}/_mkdocs_src"

rm -rf "${OUT}"
mkdir -p "${OUT}" "${OUT}/plugins/dev-team"

# Root-level docs
cp "${REPO_ROOT}/README.md"         "${OUT}/README.md"
cp "${REPO_ROOT}/GETTING-STARTED.md" "${OUT}/GETTING-STARTED.md"
cp "${REPO_ROOT}/CONTRIBUTING.md"   "${OUT}/CONTRIBUTING.md"
cp "${REPO_ROOT}/CHANGELOG.md"      "${OUT}/CHANGELOG.md"

# Repo-level docs tree (includes stylesheets/)
cp -r "${REPO_ROOT}/docs" "${OUT}/docs"

# dev-team plugin docs
cp "${REPO_ROOT}/plugins/dev-team/README.md"    "${OUT}/plugins/dev-team/README.md"
cp "${REPO_ROOT}/plugins/dev-team/CHANGELOG.md" "${OUT}/plugins/dev-team/CHANGELOG.md"
cp -r "${REPO_ROOT}/plugins/dev-team/docs"      "${OUT}/plugins/dev-team/docs"

# security-assessment plugin docs
mkdir -p "${OUT}/plugins/security-assessment"
cp "${REPO_ROOT}/plugins/security-assessment/README.md"    "${OUT}/plugins/security-assessment/README.md"
cp "${REPO_ROOT}/plugins/security-assessment/CHANGELOG.md" "${OUT}/plugins/security-assessment/CHANGELOG.md"
cp -r "${REPO_ROOT}/plugins/security-assessment/docs"      "${OUT}/plugins/security-assessment/docs"

# marketplace-dev plugin docs (CLAUDE.md is an agent instruction file and is
# intentionally NOT published to the docs site)
mkdir -p "${OUT}/plugins/marketplace-dev/docs"
mkdir -p "${OUT}/plugins/marketplace-dev/knowledge"
cp "${REPO_ROOT}/plugins/marketplace-dev/README.md"        "${OUT}/plugins/marketplace-dev/README.md"
cp -r "${REPO_ROOT}/plugins/marketplace-dev/docs"  "${OUT}/plugins/marketplace-dev/"
cp "${REPO_ROOT}/plugins/marketplace-dev/CHANGELOG.md"     "${OUT}/plugins/marketplace-dev/CHANGELOG.md"
cp "${REPO_ROOT}/plugins/marketplace-dev/knowledge/agent-type-decision-rules.md" \
   "${OUT}/plugins/marketplace-dev/knowledge/agent-type-decision-rules.md"

# GitHub Pages custom domain — published to the gh-pages root so GitHub binds it.
# Must match the host in mkdocs.yml site_url.
printf 'devteam.bryanfinster.com\n' > "${OUT}/CNAME"

# awesome-pages section metadata for the synthetic (piecemeal-assembled) dirs.
# Dirs copied wholesale via `cp -r` carry their own committed `.pages`; the
# tree roots below are built up file-by-file here, so their `.pages` are
# written inline (same pattern as the CNAME above). Titles/order for the
# `cp -r`'d dirs (adr, experiments, plugin docs) live in committed `.pages`.
cat > "${OUT}/.pages" <<'PAGES'
nav:
  - Home: README.md
  - Getting Started: GETTING-STARTED.md
  - Contributing: CONTRIBUTING.md
  - docs
  - plugins
  - Changelog: CHANGELOG.md
PAGES

printf 'title: Plugins\n'                    > "${OUT}/plugins/.pages"
printf 'title: dev-team Plugin\n'            > "${OUT}/plugins/dev-team/.pages"
printf 'title: security-assessment Plugin\n' > "${OUT}/plugins/security-assessment/.pages"
printf 'title: marketplace-dev Plugin\n'     > "${OUT}/plugins/marketplace-dev/.pages"
