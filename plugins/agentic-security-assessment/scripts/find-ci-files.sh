#!/usr/bin/env bash
# find-ci-files.sh — print paths to CI/CD definition files under a target.
#
# Used by /security-assessment Phase 1 to decide whether any CI-definition
# scanners (actionlint, semgrep CI packs, hadolint) should run and to record
# coverage gaps when no such scanner is available for a format that was found.
#
# Conventions: matches style of check-severity-consistency.sh + verify-report.sh,
# with the same two deliberate deviations documented in phase-timer.sh:
#   1. set -euo pipefail (stricter errexit).
#   2. Four-value exit-code contract (0/1/2/3).
#
# Usage:
#   find-ci-files.sh <target-dir>
#   find-ci-files.sh -h | --help
#
# Match patterns (one per line to stdout, alphabetically sorted):
#   Jenkinsfile          any file literally named Jenkinsfile
#   *.groovy             only under a ci/ or jenkins/ subtree
#   azure-pipelines*.yml / .yaml
#   .github/workflows/*.yml / .yaml
#   .gitlab-ci.yml
#   bitbucket-pipelines.yml
#   Dockerfile
#
# Excluded roots (never descended into):
#   node_modules/  vendor/  .git/  bin/  obj/
#
# Exit codes:
#   0   success (zero or more matches)
#   1   runtime error (e.g. find failed internally)
#   2   target directory not found
#   3   bad usage (missing argument)

set -euo pipefail

usage() {
  cat <<'USAGE'
usage: find-ci-files.sh <target-dir>

Prints paths (one per line, alphabetically sorted) to CI/CD definition files
found under <target-dir>.

Match patterns:
  Jenkinsfile
  *.groovy  (only under ci/ or jenkins/ subtrees)
  azure-pipelines*.yml / .yaml
  .github/workflows/*.yml / .yaml
  .gitlab-ci.yml
  bitbucket-pipelines.yml
  Dockerfile

Excluded roots (never descended into):
  node_modules  vendor  .git  bin  obj

Exit codes:
  0  success (zero or more matches)
  1  runtime error
  2  target directory not found
  3  bad usage (missing argument)
USAGE
}

if [[ $# -eq 0 ]]; then
  usage >&2
  exit 3
fi

case "${1:-}" in
  -h|--help)
    usage
    exit 0
    ;;
esac

TARGET="$1"

if [[ ! -d "$TARGET" ]]; then
  echo "find-ci-files.sh: target directory not found: $TARGET" >&2
  exit 2
fi

# Prune excluded roots anywhere in the tree, then match file patterns.
# Groovy is handled with a secondary filter: we list all .groovy files,
# then retain only those whose path contains "/ci/" or "/jenkins/".
find "$TARGET" \
  \( -path '*/node_modules' \
     -o -path '*/vendor' \
     -o -path '*/.git' \
     -o -path '*/bin' \
     -o -path '*/obj' \) -prune \
  -o \( -type f \
        \( -name 'Jenkinsfile' \
           -o -name 'Dockerfile' \
           -o -name '.gitlab-ci.yml' \
           -o -name 'bitbucket-pipelines.yml' \
           -o -name 'azure-pipelines*.yml' \
           -o -name 'azure-pipelines*.yaml' \
           -o \( -name '*.yml' -path '*/.github/workflows/*' \) \
           -o \( -name '*.yaml' -path '*/.github/workflows/*' \) \
           -o -name '*.groovy' \
        \) -print \) \
  | awk '
      # Filter groovy files: keep only those under /ci/ or /jenkins/.
      /\.groovy$/ { if ($0 ~ /\/(ci|jenkins)\//) print; next }
      { print }
    ' \
  | sort
