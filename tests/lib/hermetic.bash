# tests/lib/hermetic.bash — shared bats helper for fixture isolation.
#
# Issue #546: git exports GIT_DIR / GIT_INDEX_FILE / GIT_WORK_TREE / GIT_PREFIX
# / GIT_REFLOG_ACTION into pre-push hooks, and nothing in the hook chain
# scrubs them. Fixture bats tests that call `git init` / `git commit` /
# `git push` then target the parent worktree's gitdir instead of their
# tempdirs, silently rewriting refs/heads/* on the pushing repo.
#
# Every fixture bats file that runs git operations must:
#   load '../lib/hermetic'      # (relative to the file's own directory)
#   setup()    { hermetic_setup; ... }
#   teardown() { hermetic_teardown; }
#
# Bash-3.2 safe (macOS default). POSIX-portable across macOS / Linux /
# Windows Git Bash.

# hermetic_setup — scrub inherited git env, create a per-worker tempdir,
# cd into it, and record HERMETIC_ROOT for hermetic_assert_pwd.
hermetic_setup() {
  # 1. Scrub git envs the parent process may have inherited (e.g. git
  #    exports these into a pre-push hook's environment).
  unset GIT_DIR GIT_INDEX_FILE GIT_WORK_TREE GIT_PREFIX GIT_REFLOG_ACTION

  # 2. Isolate git config to prevent global/system config bleed-through
  #    (~/.gitconfig, /etc/gitconfig).
  export GIT_CONFIG_GLOBAL=/dev/null
  export GIT_CONFIG_SYSTEM=/dev/null

  # 3. Per-worker tempdir — the "bats-<pid>-" prefix namespaces roots per
  #    parallel bats worker so concurrent workers never collide.
  HERMETIC_ROOT="$(mktemp -d -t "bats-$$-XXXXXX")" || return 1
  export HERMETIC_ROOT

  # 4. cd into it so ambient git commands can't walk up to a parent gitdir.
  cd "$HERMETIC_ROOT" || return 1
}

# hermetic_assert_pwd — fail if PWD has drifted outside HERMETIC_ROOT.
# Fixtures that legitimately cd into subdirectories are fine; anything
# outside the tempdir is a drift bug that would otherwise corrupt the
# parent worktree.
hermetic_assert_pwd() {
  if [ -z "${HERMETIC_ROOT:-}" ]; then
    printf 'hermetic_assert_pwd: HERMETIC_ROOT is unset — hermetic_setup was not called\n' >&2
    return 1
  fi
  case "$PWD/" in
    "$HERMETIC_ROOT"/*) return 0 ;;
    *)
      printf 'hermetic_assert_pwd: PWD drifted outside HERMETIC_ROOT\n' >&2
      printf '  PWD          = %s\n' "$PWD" >&2
      printf '  HERMETIC_ROOT = %s\n' "$HERMETIC_ROOT" >&2
      return 1
      ;;
  esac
}

# hermetic_teardown — called from the fixture's teardown() block.
# Asserts PWD did not drift, then removes $HERMETIC_ROOT so parallel bats
# workers don't accumulate scratch git repos in $TMPDIR (mktemp -d -t roots
# are NOT under $BATS_TEST_TMPDIR, so bats' own cleanup won't reap them).
# The rm is guarded on the path prefix looking like a real tempdir so a
# misconfigured $TMPDIR can't escalate the delete to an unexpected path.
hermetic_teardown() {
  local rc=0
  hermetic_assert_pwd || rc=$?
  if [ -n "${HERMETIC_ROOT:-}" ] && [ -d "$HERMETIC_ROOT" ]; then
    case "$HERMETIC_ROOT" in
      /tmp/*|/var/folders/*|/private/var/folders/*|/private/tmp/*)
        cd / && rm -rf "$HERMETIC_ROOT"
        ;;
    esac
  fi
  unset HERMETIC_ROOT
  return "$rc"
}
