#!/usr/bin/env bash
# build-skills-index.sh — thin shell wrapper around build_skills_index.py.
#
# The actual builder is implemented in build_skills_index.py. This wrapper is the
# canonical entry point the rest of the codebase (tests, CI, manual invocations)
# references, mirroring build-knowledge-index.sh.
#
# Modes:
#   (no args)   regenerate plugins/dev-team/docs/skills.md in place
#   --check     verify the on-disk catalog matches a fresh build, exit non-zero
#               with a unified diff on stderr if it doesn't. Writes no file.
#
# Env vars (TEST-ONLY injection seams — DO NOT set in production callers):
#   SKILLS_INDEX_SKILLS_DIR   override the skills/ corpus root
#   SKILLS_INDEX_OUTPUT       override the output path
#
# Requirements:
#   python3 + PyYAML (already dev deps via requirements-dev.txt).

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/build_skills_index.py" "$@"
