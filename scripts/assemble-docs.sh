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

# marketplace-dev plugin docs
mkdir -p "${OUT}/plugins/marketplace-dev/knowledge"
cp "${REPO_ROOT}/plugins/marketplace-dev/README.md"        "${OUT}/plugins/marketplace-dev/README.md"
cp "${REPO_ROOT}/plugins/marketplace-dev/CHANGELOG.md"     "${OUT}/plugins/marketplace-dev/CHANGELOG.md"
cp -r "${REPO_ROOT}/plugins/marketplace-dev/docs"          "${OUT}/plugins/marketplace-dev/docs"
cp "${REPO_ROOT}/plugins/marketplace-dev/knowledge/agent-type-decision-rules.md" \
   "${OUT}/plugins/marketplace-dev/knowledge/agent-type-decision-rules.md"

# GitHub Pages custom domain — published to the gh-pages root so GitHub binds it.
# Must match the host in mkdocs.yml site_url.
printf 'devteam.bryanfinster.com\n' > "${OUT}/CNAME"
