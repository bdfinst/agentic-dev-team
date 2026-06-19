#!/usr/bin/env bash
# verify-joern-csharp.sh — verify joern can build a C# CPG.
#
# Used by install.sh (presence check) and install-macos.sh (post-install
# check) to confirm the .NET/C# reachability path in fp-reduction actually
# works. Builds a CPG from the committed C# fixture with
# `joern-parse --language csharp` and confirms the output CPG is non-empty.
#
# Minimum tested joern version: 2.0.0 — the first line that bundles the
# csharpsrc2cpg C# frontend (older builds reject `--language csharp`). The
# C# frontend parses via the external 'dotnetastgen' .NET global tool.
#
# Usage:
#   verify-joern-csharp.sh [<fixture-dir>]
#
# Exit codes:
#   0  — joern present and built a non-empty C# CPG (joern-cpg path is live)
#   1  — joern absent (fp-reduction runs in LLM-fallback mode for .NET)
#   2  — joern present but the C# CPG build failed or was empty (C# frontend
#        missing/broken; .NET targets degrade to LLM-fallback)

set -uo pipefail

JOERN_DOCS="https://docs.joern.io/installation/"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIXTURE_DIR="${1:-$SCRIPT_DIR/../knowledge/fixtures/joern-dotnet}"

if ! command -v joern-parse >/dev/null 2>&1; then
  echo "  [warn] joern not installed — fp-reduction will run in LLM-fallback mode for .NET/C# targets." >&2
  echo "         Install joern (>= 2.0.0) for deterministic call-graph reachability: $JOERN_DOCS" >&2
  exit 1
fi

if [ ! -d "$FIXTURE_DIR" ]; then
  echo "  [FAIL] C# fixture directory not found: $FIXTURE_DIR" >&2
  exit 2
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
TMP_CPG="$WORK/csharp-verify.cpg"

if ! joern-parse "$FIXTURE_DIR" --language csharp --output "$TMP_CPG" >/dev/null 2>&1; then
  echo "  [warn] 'joern-parse --language csharp' failed on the C# fixture — C# frontend missing/broken." >&2
  echo "         .NET targets will use LLM-fallback. See $JOERN_DOCS" >&2
  exit 2
fi

if [ ! -s "$TMP_CPG" ]; then
  echo "  [warn] joern produced an empty C# CPG — C# frontend not functional." >&2
  echo "         .NET targets will use LLM-fallback. See $JOERN_DOCS" >&2
  exit 2
fi

echo "  [ok]   joern built a non-empty C# CPG ($(wc -c <"$TMP_CPG" | tr -d ' ') bytes) — .NET reachability via joern-cpg is live."
exit 0
