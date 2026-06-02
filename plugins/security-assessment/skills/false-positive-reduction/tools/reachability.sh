#!/usr/bin/env bash
# reachability.sh — joern wrapper for fp-reduction Stage 1.
#
# Usage:
#   reachability.sh <repo-path> [<cache-dir>]
#
# Builds or loads a Code Property Graph for the target repo and exports a CFG
# JSON that the fp-reduction agent queries. Caches by commit SHA under
# <cache-dir>/<sha>.cpg so repeat invocations on the same commit are cheap.
#
# Exit codes:
#   0  — CPG built/loaded; path to CFG JSON printed on stdout
#   1  — joern absent (caller should fall back to LLM mode)
#   2  — build failed (caller should fall back; still tag as llm-fallback)

set -uo pipefail

REPO="${1:?usage: reachability.sh <repo-path> [<cache-dir>]}"
CACHE_DIR="${2:-$REPO/memory/joern-cache}"

if ! command -v joern-parse >/dev/null 2>&1; then
  echo "joern-parse not on PATH; caller should use LLM fallback" >&2
  exit 1
fi

mkdir -p "$CACHE_DIR"

# Compute cache key from commit SHA (or "working-tree" if not git)
if git -C "$REPO" rev-parse --git-dir >/dev/null 2>&1; then
  SHA=$(git -C "$REPO" rev-parse HEAD 2>/dev/null || echo "working-tree")
else
  SHA="working-tree"
fi

CPG_PATH="$CACHE_DIR/${SHA}.cpg"
CFG_JSON="$CACHE_DIR/${SHA}.cfg.json"

if [ -f "$CFG_JSON" ] && [ "$SHA" != "working-tree" ]; then
  echo "$CFG_JSON"
  exit 0
fi

# Build CPG
if ! joern-parse "$REPO" --output "$CPG_PATH" >/dev/null 2>&1; then
  echo "joern-parse failed on $REPO; caller should use LLM fallback" >&2
  exit 2
fi

# Export CFG
if ! joern-export --repr cfg --format json "$CPG_PATH" > "$CFG_JSON" 2>/dev/null; then
  echo "joern-export failed; caller should use LLM fallback" >&2
  exit 2
fi

echo "$CFG_JSON"
exit 0
