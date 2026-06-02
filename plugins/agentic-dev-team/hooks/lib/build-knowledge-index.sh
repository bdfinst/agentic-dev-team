#!/usr/bin/env bash
# build-knowledge-index.sh — thin shell wrapper around build_knowledge_index.py.
#
# The actual builder is implemented in build_knowledge_index.py (one
# Python process per build; ~0.17s for the real corpus). This wrapper
# exists so the file path the rest of the codebase already references
# keeps working as the canonical entry point for hooks, tests, and
# manual invocations.
#
# Modes:
#   (no args)   rebuild knowledge/index.json in place
#   --check     verify the on-disk index matches a fresh build, exit
#               non-zero with a unified diff on stderr if it doesn't.
#               Writes no file.
#
# Env vars (TEST-ONLY injection seams — DO NOT set in production callers,
# DO NOT document as user-facing config):
#   KNOWLEDGE_INDEX_CORPUS_ROOTS  override the corpus root
#   KNOWLEDGE_INDEX_OUTPUT        override the output index path
#
# Requirements:
#   python3 (already a hard dep via /init-dev-team).

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/build_knowledge_index.py" "$@"
