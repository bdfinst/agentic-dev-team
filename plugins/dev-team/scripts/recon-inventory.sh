#!/usr/bin/env bash
# recon-inventory.sh — canonical file enumeration for the RECON envelope's
# file_inventory field (primitives contract 1.2.0+). Single source of truth
# for the enumeration pipeline; invoked both by the codebase-recon agent and
# by the evals/codebase-recon/tests/ test harness.
#
# Usage:
#   recon-inventory.sh <repo-root> [--slug <slug>]
#                                  [--force-filesystem-walk]
#                                  [--emit-main-inventory-json <path>]
#
# Output:
#   stdout: one repo-relative path per line, LC_ALL=C sorted, deduplicated,
#           LF-terminated, no blank lines.
#   stderr: human-readable progress + `# BROKEN_SYMLINK: <src> -> <dst>`
#           markers (one per broken link). Consumers capture these for the
#           envelope `notes` array.
#   --emit-main-inventory-json <path>: write a JSON fragment suitable for
#           splicing into the main RECON envelope:
#              { "source": "...", "count": N, "sibling_ref": "recon-<slug>.inventory.txt" }
#
# Exit codes:
#   0  success
#   2  usage error
#   3  repo root not a directory

set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage: recon-inventory.sh <repo-root> [--slug <slug>]
                                       [--force-filesystem-walk]
                                       [--emit-main-inventory-json <path>]
EOF
  exit 2
}

ROOT=""
SLUG=""
FORCE_FS_WALK=0
EMIT_MAIN=""

while (( "$#" )); do
  case "$1" in
    --slug) SLUG="${2-}"; shift 2 ;;
    --force-filesystem-walk) FORCE_FS_WALK=1; shift ;;
    --emit-main-inventory-json) EMIT_MAIN="${2-}"; shift 2 ;;
    -h|--help) usage ;;
    --*) printf 'unknown flag: %s\n' "$1" >&2; usage ;;
    *)
      if [[ -z "$ROOT" ]]; then
        ROOT="$1"; shift
      else
        printf 'unexpected positional arg: %s\n' "$1" >&2
        usage
      fi
      ;;
  esac
done

[[ -z "$ROOT" ]] && usage
if [[ ! -d "$ROOT" ]]; then
  printf 'repo-root is not a directory: %s\n' "$ROOT" >&2
  exit 3
fi

# Normalize root to an absolute real path so relative computations are stable.
ROOT_ABS="$(cd "$ROOT" && pwd -P)"

# Derive slug default from repo root basename, kebab-cased.
if [[ -z "$SLUG" ]]; then
  SLUG="$(basename "$ROOT_ABS" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9._-' '-' | sed 's/-\{2,\}/-/g; s/^-\+//; s/-\+$//')"
fi

EXCLUDES_FILE="$(cd "$(dirname "$0")/.." && pwd)/knowledge/recon-inventory-excludes.txt"

# Decide branch.
if [[ "$FORCE_FS_WALK" -eq 1 ]] || [[ ! -d "$ROOT_ABS/.git" && ! -f "$ROOT_ABS/.git" ]]; then
  SOURCE="filesystem-walk"
else
  SOURCE="git-ls-files"
fi

# Compute inventory into a scratch file so we can count then emit twice if
# --emit-main-inventory-json is set.
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
RAW="$TMP/raw.txt"
OUT="$TMP/out.txt"

_collect_git() {
  # Git branch: ls-files emits repo-relative paths including submodule
  # gitlinks (once, not recursed). NUL-delimited for safety.
  git -C "$ROOT_ABS" ls-files -z | tr '\0' '\n' >"$RAW"
}

_collect_fs() {
  # Filesystem walk with excludes. Strategy: `find -type f` (skip non-regular
  # files — devices, fifos, sockets), then prune prefixes and filenames.
  #
  # Read excludes file into two arrays.
  local prefixes=()
  local filenames=()
  local section=""
  while IFS= read -r line || [[ -n "$line" ]]; do
    # Section markers `# prefix:` or `# filename:` change which bucket we fill.
    if [[ "$line" =~ ^[[:space:]]*#[[:space:]]*prefix:[[:space:]]*$ ]]; then
      section="prefix"; continue
    elif [[ "$line" =~ ^[[:space:]]*#[[:space:]]*filename:[[:space:]]*$ ]]; then
      section="filename"; continue
    fi
    # Skip comments / blanks.
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    [[ -z "${line//[[:space:]]/}" ]] && continue
    # Strip whitespace and trailing slash.
    local entry="$line"
    entry="${entry#"${entry%%[![:space:]]*}"}"
    entry="${entry%"${entry##*[![:space:]]}"}"
    entry="${entry%/}"
    case "$section" in
      prefix)   prefixes+=("$entry") ;;
      filename) filenames+=("$entry") ;;
    esac
  done <"$EXCLUDES_FILE"

  # Build find arguments.
  local find_args=("$ROOT_ABS")
  # Prune prefixes: any directory whose relative path starts with one of the
  # prefixes (anywhere in the tree). We implement via `-path`/`-prune`.
  local pruned=()
  local p
  for p in "${prefixes[@]}"; do
    pruned+=(-o -path "$ROOT_ABS/$p" -o -path "$ROOT_ABS/*/$p")
  done
  # Pruned filenames at -name level.
  local name_excludes=()
  local n
  for n in "${filenames[@]}"; do
    name_excludes+=(-not -name "$n")
  done

  # Execute find: prune then print regular files.
  # -false is a sentinel so we can `-o` the prune list uniformly.
  if (( ${#prefixes[@]} )); then
    find "${find_args[@]}" \( -false "${pruned[@]}" \) -prune -o -type f "${name_excludes[@]}" -print \
      | while IFS= read -r abs; do
          printf '%s\n' "${abs#"$ROOT_ABS/"}"
        done >"$RAW"
  else
    find "${find_args[@]}" -type f "${name_excludes[@]}" -print \
      | while IFS= read -r abs; do
          printf '%s\n' "${abs#"$ROOT_ABS/"}"
        done >"$RAW"
  fi
}

if [[ "$SOURCE" == "git-ls-files" ]]; then
  _collect_git
else
  _collect_fs
fi

# Symlink resolution pass: for each path, if it's a symlink, substitute the
# resolved real-path (relative to repo root) or drop the entry and record a
# BROKEN_SYMLINK note to stderr if the target is missing or outside the repo.
_resolve_symlinks() {
  local in="$1"
  local out="$2"
  : >"$out"
  local line abs target real rel
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -z "$line" ]] && continue
    abs="$ROOT_ABS/$line"
    if [[ -L "$abs" ]]; then
      if [[ ! -e "$abs" ]]; then
        printf '# BROKEN_SYMLINK: %s -> (missing target)\n' "$line" >&2
        continue
      fi
      real="$(cd "$(dirname "$abs")" 2>/dev/null && { readlink -f -- "$(basename "$abs")" 2>/dev/null || python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$(basename "$abs")"; })" || real=""
      if [[ -z "$real" ]]; then
        printf '# BROKEN_SYMLINK: %s -> (unresolvable)\n' "$line" >&2
        continue
      fi
      # Must stay inside repo root.
      case "$real" in
        "$ROOT_ABS"|"$ROOT_ABS"/*)
          rel="${real#"$ROOT_ABS/"}"
          printf '%s\n' "$rel" >>"$out"
          ;;
        *)
          printf '# BROKEN_SYMLINK: %s -> %s (outside repo)\n' "$line" "$real" >&2
          ;;
      esac
    else
      printf '%s\n' "$line" >>"$out"
    fi
  done <"$in"
}

RESOLVED="$TMP/resolved.txt"
_resolve_symlinks "$RAW" "$RESOLVED"

# Sort + dedupe under LC_ALL=C for cross-locale determinism.
LC_ALL=C sort -u "$RESOLVED" >"$OUT"

# Emit stdout: the inventory (LF-terminated, no trailing blank line beyond the
# final line's LF — which `sort` already gives us).
cat "$OUT"

# Optionally emit the main-envelope JSON fragment.
if [[ -n "$EMIT_MAIN" ]]; then
  COUNT=$(wc -l <"$OUT" | tr -d ' ')
  printf '{ "source": "%s", "count": %s, "sibling_ref": "recon-%s.inventory.txt" }\n' \
    "$SOURCE" "$COUNT" "$SLUG" >"$EMIT_MAIN"
fi

exit 0
