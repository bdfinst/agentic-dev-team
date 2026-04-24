#!/usr/bin/env bash
# setup.sh — materialise the two gitignored exclude-cases (.DS_Store,
# node_modules/pkg/index.js) that cannot ship inside the committed fixture
# tree because the repo root .gitignore filters them.
#
# Usage:
#   setup.sh <scratch-dir>
#
# The scratch dir is the test harness's staged copy of the fixture; this
# script adds the two files so the filesystem walk sees them and must
# exclude them per knowledge/recon-inventory-excludes.txt.

set -euo pipefail

if [[ $# -ne 1 ]]; then
  printf 'usage: %s <scratch-dir>\n' "$0" >&2
  exit 2
fi
SCRATCH="$1"

printf '(fake macOS metadata — excluded by filename)\n' >"$SCRATCH/.DS_Store"
mkdir -p "$SCRATCH/node_modules/pkg"
printf '// excluded by prefix\n' >"$SCRATCH/node_modules/pkg/index.js"
