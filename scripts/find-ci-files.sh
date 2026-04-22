#!/usr/bin/env bash
# find-ci-files.sh — enumerate CI/CD configuration files in a target directory.
#
# Walks the target for CI files across 6 CI systems. Prints one path per line
# on stdout. Used by /security-assessment to ensure the target walk includes
# CI configuration, since these files typically live outside src/ and are
# often skipped by an unqualified scan.
#
# Supported CI systems:
#   - GitHub Actions       .github/workflows/*.{yml,yaml}
#   - GitLab CI            .gitlab-ci.yml, .gitlab/**/*.{yml,yaml}
#   - CircleCI             .circleci/config.yml
#   - Azure Pipelines      azure-pipelines.yml, .azure-pipelines/**/*.{yml,yaml}
#   - Bitbucket Pipelines  bitbucket-pipelines.yml
#   - Jenkins              Jenkinsfile, jenkinsfile.d/**
#
# Usage:
#   find-ci-files.sh <target-dir>
#
# Output: one path per line, absolute or relative per invocation.
# Exit 0 always (including when nothing is found).

set -uo pipefail

TARGET="${1:?usage: find-ci-files.sh <target-dir>}"

if [[ ! -d "$TARGET" ]]; then
  echo "error: target not a directory: $TARGET" >&2
  exit 2
fi

# GitHub Actions
if [[ -d "$TARGET/.github/workflows" ]]; then
  find "$TARGET/.github/workflows" -type f \( -name "*.yml" -o -name "*.yaml" \) 2>/dev/null
fi

# GitLab CI
[[ -f "$TARGET/.gitlab-ci.yml" ]] && echo "$TARGET/.gitlab-ci.yml"
if [[ -d "$TARGET/.gitlab" ]]; then
  find "$TARGET/.gitlab" -type f \( -name "*.yml" -o -name "*.yaml" \) 2>/dev/null
fi

# CircleCI
[[ -f "$TARGET/.circleci/config.yml" ]] && echo "$TARGET/.circleci/config.yml"

# Azure Pipelines
[[ -f "$TARGET/azure-pipelines.yml" ]] && echo "$TARGET/azure-pipelines.yml"
[[ -f "$TARGET/azure-pipelines.yaml" ]] && echo "$TARGET/azure-pipelines.yaml"
if [[ -d "$TARGET/.azure-pipelines" ]]; then
  find "$TARGET/.azure-pipelines" -type f \( -name "*.yml" -o -name "*.yaml" \) 2>/dev/null
fi

# Bitbucket Pipelines
[[ -f "$TARGET/bitbucket-pipelines.yml" ]] && echo "$TARGET/bitbucket-pipelines.yml"

# Jenkins
[[ -f "$TARGET/Jenkinsfile" ]] && echo "$TARGET/Jenkinsfile"
if [[ -d "$TARGET/jenkinsfile.d" ]]; then
  find "$TARGET/jenkinsfile.d" -type f 2>/dev/null
fi

# Also walk up one level if target is a service subdir (e.g. services/auth-gateway/),
# CI lives at repo root not in the service subdir.
PARENT="$(dirname "$TARGET")"
GRANDPARENT="$(dirname "$PARENT")"
for climb in "$PARENT" "$GRANDPARENT"; do
  [[ "$climb" == "/" || "$climb" == "." || "$climb" == "$TARGET" ]] && continue
  if [[ -d "$climb/.github/workflows" && "$climb" != "$TARGET" ]]; then
    find "$climb/.github/workflows" -type f \( -name "*.yml" -o -name "*.yaml" \) 2>/dev/null
  fi
  [[ -f "$climb/.gitlab-ci.yml" ]] && echo "$climb/.gitlab-ci.yml"
  [[ -f "$climb/.circleci/config.yml" ]] && echo "$climb/.circleci/config.yml"
done

exit 0
