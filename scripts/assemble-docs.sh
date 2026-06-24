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

# Repo-level docs tree
cp -r "${REPO_ROOT}/docs" "${OUT}/docs"

# dev-team plugin docs
cp "${REPO_ROOT}/plugins/dev-team/README.md"    "${OUT}/plugins/dev-team/README.md"
cp "${REPO_ROOT}/plugins/dev-team/CHANGELOG.md" "${OUT}/plugins/dev-team/CHANGELOG.md"
cp -r "${REPO_ROOT}/plugins/dev-team/docs"      "${OUT}/plugins/dev-team/docs"
