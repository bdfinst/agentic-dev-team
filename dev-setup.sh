#!/usr/bin/env bash
# dev-setup.sh — Set up this repo for in-repo plugin development.
#
# Creates symlinks from .claude/{agents,skills,commands,hooks} to the root-level
# source directories so Claude Code can load agents and skills while you develop.
#
# Run once after cloning:
#   ./dev-setup.sh
#
# To remove symlinks and restore clean state:
#   ./dev-setup.sh --clean

set -euo pipefail

PLUGIN_DIRS=(agents skills commands hooks)
CLAUDE_DIR=".claude"

clean() {
  for dir in "${PLUGIN_DIRS[@]}"; do
    target="$CLAUDE_DIR/$dir"
    if [ -L "$target" ]; then
      rm "$target"
      echo "removed $target"
    fi
  done
  echo "Dev symlinks removed."
}

if [ "${1:-}" = "--clean" ]; then
  clean
  exit 0
fi

for dir in "${PLUGIN_DIRS[@]}"; do
  target="$CLAUDE_DIR/$dir"
  if [ -L "$target" ]; then
    echo "already linked: $target"
  elif [ -e "$target" ]; then
    echo "ERROR: $target exists and is not a symlink. Remove it manually before running dev-setup." >&2
    exit 1
  else
    ln -s "../$dir" "$target"
    echo "linked: $target -> ../$dir"
  fi
done

echo ""
echo "Dev setup complete. Claude Code will load agents/skills from root-level directories."
echo "Run './dev-setup.sh --clean' to remove symlinks."
