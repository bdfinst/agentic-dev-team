#!/usr/bin/env bash
# setup.sh — materialise the submodule + symlink edge cases at test time.
#
# Usage:
#   setup.sh <scratch-dir>
#
# The test harness has already copied the fixture tree into <scratch-dir>
# (minus oracle files and this setup.sh). This script:
#   1. Creates a tiny bare stub repo under .stub/sub.git/ with one commit.
#   2. Converts <scratch-dir> into a git working tree and clones the stub as
#      a submodule at vendor/sub.
#   3. Creates src/alias.ts -> src/handlers/auth.ts (real relative symlink).
#   4. Creates src/orphan.ts -> does-not-exist.ts (broken symlink).

set -euo pipefail

if [[ $# -ne 1 ]]; then
  printf 'usage: %s <scratch-dir>\n' "$0" >&2
  exit 2
fi
SCRATCH="$1"

# Put the bare stub OUTSIDE the scratch dir so the scratch git repo does not
# accidentally add it as tracked content.
STUB_DIR="$(dirname "$SCRATCH")/.stub/sub.git"
mkdir -p "$STUB_DIR"
(
  WORK="$(mktemp -d)"
  cd "$WORK"
  git init -q
  printf 'initial\n' >README.md
  git -c user.email=stub@example.com -c user.name=Stub add README.md
  git -c user.email=stub@example.com -c user.name=Stub commit -q -m "init"
  git clone -q --bare . "$STUB_DIR"
  cd /
  rm -rf "$WORK"
) >/dev/null

# Turn the scratch dir into a git working tree with a submodule.
(
  cd "$SCRATCH"
  git init -q
  git -c user.email=test@example.com -c user.name=Test add .
  git -c user.email=test@example.com -c user.name=Test commit -q -m "fixture seed"
  # Add the local bare stub as a submodule. Use file:// so git allows it.
  git -c user.email=test@example.com -c user.name=Test -c protocol.file.allow=always \
    submodule add -q "file://$STUB_DIR" vendor/sub
  git -c user.email=test@example.com -c user.name=Test commit -q -m "add submodule"
) >/dev/null

# Symlinks: one valid relative link, one broken. Both added to git so that
# `git ls-files` returns them and the script's symlink-resolution post-pass
# can exercise the two branches (resolve -> substitute vs. broken -> drop +
# BROKEN_SYMLINK note to stderr).
ln -s handlers/auth.ts "$SCRATCH/src/alias.ts"
ln -s does-not-exist.ts "$SCRATCH/src/orphan.ts"
(
  cd "$SCRATCH"
  git -c user.email=test@example.com -c user.name=Test add src/alias.ts src/orphan.ts
  git -c user.email=test@example.com -c user.name=Test commit -q -m "add symlinks"
) >/dev/null
