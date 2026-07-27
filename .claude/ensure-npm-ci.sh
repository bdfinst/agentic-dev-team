#!/usr/bin/env bash
# SessionStart hook (registered in .claude/settings.json): self-heal a
# checkout (most commonly a freshly created git worktree) that never ran
# `npm ci`, so husky's git hooks aren't silently inert.
#
# Why this matters: core.hooksPath=.husky/_ is set once in the shared
# .git/config and is inherited by every worktree automatically — but
# .husky/_ itself (the shim git actually invokes) is gitignored and
# generated locally by npm ci's `prepare` script. A worktree missing it
# has every git hook (pre-commit, pre-push) silently no-op with no error,
# which is easy to miss (see CLAUDE.md "Worktrees — run npm ci first").
#
# Fail-open and time-boxed — never blocks session start.
set -uo pipefail

_root="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$_root" || exit 0

# Only meaningful in this repo's own checkout(s).
[ -f package.json ] || exit 0

# Already provisioned: nothing to do.
[ -x node_modules/.bin/husky ] && exit 0

command -v npm >/dev/null 2>&1 || exit 0

_tmo() {
  if command -v timeout >/dev/null 2>&1; then timeout 180 "$@"
  elif command -v gtimeout >/dev/null 2>&1; then gtimeout 180 "$@"
  else "$@"; fi
}

_log="${HOME}/.cache/npm-ci-sessionstart.log"
mkdir -p "$(dirname "$_log")"

if _tmo npm ci >"$_log" 2>&1; then
  echo '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"This checkout had no node_modules/husky — ran npm ci to provision it, so pre-commit/pre-push git hooks are no longer silently inert."}}'
else
  python3 -c "
import json, sys
message = f'This checkout is missing node_modules and an automatic npm ci failed or timed out — pre-commit/pre-push hooks stay silently inert until you run npm ci by hand. See {sys.argv[1]}.'
print(json.dumps({'hookSpecificOutput': {'hookEventName': 'SessionStart', 'additionalContext': message}}))
" "$_log"
fi
exit 0
