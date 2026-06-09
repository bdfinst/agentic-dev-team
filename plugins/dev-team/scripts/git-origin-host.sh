#!/usr/bin/env bash
# git-origin-host.sh — classify the `origin` remote so /plan only offers GitHub
# issue creation on an actual GitHub host.
#
# Prints exactly one of:
#   github  — github.com OR an enterprise GHE host (any dot-label equals "github")
#   other   — a non-GitHub host, including lookalikes like notgithub.example.com
#   none    — no origin remote, or an unparseable URL (fail-open: never blocks)
#
# Reads `git remote get-url origin` unless a URL is given as $1 (for testing).
# Usage: git-origin-host.sh [remote-url]

set -uo pipefail

url="${1:-}"
if [ -z "$url" ]; then
  url="$(git remote get-url origin 2>/dev/null || true)"
fi
[ -n "$url" ] || { echo none; exit 0; }

# Extract the host from https://, ssh://, or scp-like (git@host:path) forms.
host=""
case "$url" in
  *://*)   rest="${url#*://}"; rest="${rest#*@}"; host="${rest%%/*}"; host="${host%%:*}" ;;
  *@*:*)   rest="${url#*@}"; host="${rest%%:*}" ;;
  *)       host="${url%%:*}" ;;
esac
host="$(printf '%s' "$host" | tr '[:upper:]' '[:lower:]')"
[ -n "$host" ] || { echo none; exit 0; }

# Match a whole dot-label of "github" (covers github.com and enterprise GHE such
# as github.example.com). A substring like "notgithub" or "mygithub" does NOT
# match, because the pattern requires a dot immediately before "github".
case ".$host." in
  *.github.*) echo github; exit 0 ;;
esac
echo other
