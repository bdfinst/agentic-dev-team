#!/usr/bin/env bash
# reachability.sh — joern wrapper for fp-reduction Stage 1.
#
# Usage:
#   reachability.sh <repo-path> [<cache-dir>]
#
# Builds or loads a Code Property Graph for the target repo and exports a CFG
# JSON that the fp-reduction agent queries. Detects the target's primary
# language and passes the matching `--language` to joern, so non-default
# frontends (notably C#/.NET) actually build a CPG instead of silently
# degrading to LLM-fallback when joern's autodetect picks the wrong frontend.
# Caches by commit SHA + language under <cache-dir>/<sha>.<language>.cpg so
# repeat invocations on the same commit are cheap and cross-language fixtures
# don't collide.
#
# Language detection (first match wins):
#   csharp       .cs / .csproj / .sln
#   javascript   .ts / .tsx / .js / package.json
#   python       .py / pyproject.toml / requirements.txt
#   javasrc      .java / pom.xml / build.gradle
#   gosrc        .go / go.mod
#   (autodetect) none of the above — joern picks the frontend; cache tag "auto"
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

# _has_files <repo> <find-predicates...> — true if at least one matching file
# exists. The find pipeline runs inside a command substitution so pipefail
# doesn't trip on head closing the pipe early; we test the captured value.
_has_files() {
  local repo="$1"
  shift
  local found
  found="$(find "$repo" -type f \( "$@" \) -print 2>/dev/null | head -n1)"
  [ -n "$found" ]
}

# detect_language <repo> — prints the joern --language value, or "" (autodetect).
detect_language() {
  local repo="$1"
  if _has_files "$repo" -name '*.cs' -o -name '*.csproj' -o -name '*.sln'; then
    echo csharp
  elif _has_files "$repo" -name '*.ts' -o -name '*.tsx' -o -name '*.js' -o -name 'package.json'; then
    echo javascript
  elif _has_files "$repo" -name '*.py' -o -name 'pyproject.toml' -o -name 'requirements.txt'; then
    echo python
  elif _has_files "$repo" -name '*.java' -o -name 'pom.xml' -o -name 'build.gradle'; then
    echo javasrc
  elif _has_files "$repo" -name '*.go' -o -name 'go.mod'; then
    echo gosrc
  else
    echo ""
  fi
}

LANGUAGE="$(detect_language "$REPO")"
LANG_TAG="${LANGUAGE:-auto}"

mkdir -p "$CACHE_DIR"

# Compute cache key from commit SHA (or "working-tree" if not git)
if git -C "$REPO" rev-parse --git-dir >/dev/null 2>&1; then
  SHA=$(git -C "$REPO" rev-parse HEAD 2>/dev/null || echo "working-tree")
else
  SHA="working-tree"
fi

CPG_PATH="$CACHE_DIR/${SHA}.${LANG_TAG}.cpg"
CFG_JSON="$CACHE_DIR/${SHA}.${LANG_TAG}.cfg.json"

if [ -f "$CFG_JSON" ] && [ "$SHA" != "working-tree" ]; then
  echo "$CFG_JSON"
  exit 0
fi

# Build CPG — pass --language when detected; otherwise let joern autodetect.
build_ok=1
if [ -n "$LANGUAGE" ]; then
  joern-parse "$REPO" --language "$LANGUAGE" --output "$CPG_PATH" >/dev/null 2>&1 || build_ok=0
else
  joern-parse "$REPO" --output "$CPG_PATH" >/dev/null 2>&1 || build_ok=0
fi
if [ "$build_ok" -eq 0 ]; then
  echo "joern-parse failed on $REPO (language=${LANG_TAG}); caller should use LLM fallback" >&2
  exit 2
fi

# Export CFG
if ! joern-export --repr cfg --format json "$CPG_PATH" > "$CFG_JSON" 2>/dev/null; then
  echo "joern-export failed (language=${LANG_TAG}); caller should use LLM fallback" >&2
  exit 2
fi

echo "$CFG_JSON"
exit 0
