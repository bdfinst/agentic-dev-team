#!/usr/bin/env bats
# Enforces that every fixture bats file that does git operations sources
# tests/lib/hermetic.bash and wires hermetic_setup + hermetic_teardown into
# its setup()/teardown() blocks. Issue #546 — without this, fixtures inherit
# git env vars git exports into pre-push hooks and corrupt the parent
# worktree's refs.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

# Files that legitimately do NOT need hermetic_setup. Add one line per
# entry with a short rationale — no silent skips.
_is_whitelisted() {
  case "$1" in
    # The hermetic helper's OWN tests source the helper directly and
    # source-then-invoke it per-test rather than via bats setup/teardown.
    */tests/lib/hermetic_tests.bats) return 0 ;;
    # Tests that assert the adoption contract itself — they read files,
    # they do not run git operations.
    */tests/repo/hermetic_adoption_tests.bats) return 0 ;;
  esac
  return 1
}

# _needs_hermetic <file> — returns 0 iff the file directly invokes any git
# command that mutates state at shell-command position. Only lines that
# START with (optionally-indented) `git <mutating-verb>` count — this
# excludes JSON test payloads like `"command":"git commit -m x"` where the
# fixture is describing a git op the SUT will interpret, not running it.
#
# Mutating verbs: init, commit, push, update-ref, checkout, branch, tag,
# add, clone, fetch, pull, merge, rebase, reset, apply, cherry-pick,
# revert, worktree, stash. Read-only ops (log, rev-parse, for-each-ref,
# config --get) do not risk ref corruption and are ignored.
_needs_hermetic() {
  grep -q -E '^[[:space:]]*git[[:space:]]+(init|commit|push|update-ref|checkout|branch|tag|add|clone|fetch|pull|merge|rebase|reset|apply|cherry-pick|revert|worktree|stash)([[:space:]]|$)' "$1"
}

# _is_hermetic <file> — returns 0 iff the file both loads the hermetic
# helper AND wires hermetic_setup in its setup() and hermetic_teardown in
# its teardown().
_is_hermetic() {
  grep -q "load '../lib/hermetic'" "$1" \
    && grep -q "hermetic_setup" "$1" \
    && grep -q "hermetic_teardown" "$1"
}

@test "every fixture bats file that runs git ops loads tests/lib/hermetic" {
  # Enumerate every .bats file under tests/, skip whitelisted paths.
  offenders=""
  while IFS= read -r -d '' f; do
    _is_whitelisted "$f" && continue
    _needs_hermetic "$f" || continue
    _is_hermetic "$f" || offenders="$offenders $f"
  done < <(find "$REPO_ROOT/tests" -name "*.bats" -print0)

  if [ -n "$offenders" ]; then
    printf 'The following bats files do fixture git operations but do not\n' >&2
    printf 'source tests/lib/hermetic.bash + wire hermetic_setup/hermetic_teardown.\n' >&2
    printf 'See issue #546 for why this matters.\n\n' >&2
    for f in $offenders; do
      printf '  %s\n' "$f" >&2
    done
    return 1
  fi
}
