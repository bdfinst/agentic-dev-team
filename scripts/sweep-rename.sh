#!/usr/bin/env bash
# scripts/sweep-rename.sh — bulk-replace one literal with another across a
# directory tree, scoped to file types that carry plugin references.
#
# Usage: scripts/sweep-rename.sh <root> <old> <new>
#
# - Only touches *.md, *.sh, *.json, *.yml, *.yaml, *.py, *.ps1, *.ts, *.js,
#   *.tsx, *.jsx, *.txt, *.tmpl files plus any file under templates/.
# - Skips .git/, node_modules/, .codegraph/, dist/, build/, and the script
#   itself to avoid self-rewrites and binary corruption.
# - Skips CHANGELOG.md by default (call out an exception via env if needed:
#   SWEEP_INCLUDE_CHANGELOG=1).
# - Idempotent: re-running after a successful sweep produces no changes.
# - macOS/BSD sed compatible via the no-extension -i workaround.

set -euo pipefail

if [ "$#" -lt 3 ]; then
  echo "usage: $0 <root> <old> <new>" >&2
  exit 2
fi

ROOT="$1"
OLD="$2"
NEW="$3"

if [ ! -d "$ROOT" ]; then
  echo "sweep-rename: '$ROOT' is not a directory" >&2
  exit 2
fi

# Escape sed metacharacters in OLD and NEW.
escape_sed() {
  printf '%s' "$1" | sed -e 's/[]\/$*.^[]/\\&/g'
}
ESC_OLD=$(escape_sed "$OLD")
ESC_NEW=$(escape_sed "$NEW")

# Build the file list. -prune is needed before -o -print to skip dirs.
mapfile -t files < <(
  find "$ROOT" \
    \( -path '*/.git' -o -path '*/node_modules' -o -path '*/.codegraph' \
       -o -path '*/dist' -o -path '*/build' \) -prune -o \
    -type f \
    \( -name '*.md' -o -name '*.sh' -o -name '*.json' \
       -o -name '*.yml' -o -name '*.yaml' -o -name '*.py' \
       -o -name '*.ps1' -o -name '*.ts' -o -name '*.js' \
       -o -name '*.tsx' -o -name '*.jsx' -o -name '*.txt' \
       -o -name '*.tmpl' -o -name '*.bats' -o -name '*.jsonl' \) \
    -print
)

changed=0
for f in "${files[@]}"; do
  case "$f" in
    */CHANGELOG.md)
      [ "${SWEEP_INCLUDE_CHANGELOG:-0}" = "1" ] || continue
      ;;
    */scripts/sweep-rename.sh|*/scripts/assert-rename.sh)
      continue
      ;;
    # Intentional homes for legacy plugin names — never sweep these.
    */evals/upgrade-migration/*|\
    */docs/decisions/upgrade-step-0-sunset.md|\
    */docs/specs/rename-plugins.md|\
    */plans/rename-plugins.md|\
    */plugins/dev-team/commands/upgrade.md|\
    */plugins/security-assessment/install.sh|\
    */.claude-plugin/marketplace.json|\
    */docs/adr/*|\
    */evals/security-review-adapter/*|\
    */metrics/config-changelog.jsonl|\
    */memory/decisions.md)
      continue
      ;;
  esac
  if grep -q -- "$OLD" "$f" 2>/dev/null; then
    # Portable sed -i: BSD requires '' after -i, GNU rejects it. Use a temp
    # and `cat` the result back so file mode (executable bit) is preserved.
    tmp=$(mktemp)
    sed "s/${ESC_OLD}/${ESC_NEW}/g" "$f" > "$tmp"
    if ! cmp -s "$f" "$tmp"; then
      cat "$tmp" > "$f"
      rm "$tmp"
      changed=$((changed + 1))
      printf '  rewrote %s\n' "$f"
    else
      rm "$tmp"
    fi
  fi
done

printf '%d file(s) changed (root=%s, old=%s, new=%s)\n' "$changed" "$ROOT" "$OLD" "$NEW"
