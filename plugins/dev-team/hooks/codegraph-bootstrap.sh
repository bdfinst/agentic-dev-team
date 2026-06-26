#!/usr/bin/env bash
# codegraph-bootstrap.sh — Claude Code SessionStart hook
#
# Rebuilds the per-machine CodeGraph index when a freshly cloned repo has
# adopted CodeGraph but has no local index yet. This is how a team shares
# CodeGraph: the SQLite database is derived from source and machine-local
# (`.codegraph/.gitignore` excludes `*.db`), so it is never committed — instead
# every clone rebuilds it automatically on the first session. See
# docs/adr/0012-auto-bootstrap-codegraph-index-per-clone.md.
#
# Repo opt-in is the committed `.codegraph/` directory (the same sentinel
# codegraph-nudge.sh keys off). A repo that never adopted CodeGraph has no
# `.codegraph/`, so this hook is a no-op there — it never indexes a project the
# maintainer did not bless.
#
# Behaviour (CWD = the session's project dir):
#   * no `.codegraph/`                  -> exit 0 (repo hasn't adopted CodeGraph)
#   * `.codegraph/` + local db present  -> exit 0 (MCP watcher keeps it fresh)
#   * `.codegraph/` + db missing + bin  -> build the index in the BACKGROUND
#   * `.codegraph/` + db missing, no bin-> print a one-line install nudge
#
# The index build is detached so SessionStart never blocks on it (indexing a
# large repo can take many seconds). codegraph's own lock file makes a second
# concurrent `init` fail harmlessly, so no extra spawn guard is needed; this
# hook swallows that error (fail-open).
#
# Input:  SessionStart JSON on stdin (hook_event_name, cwd, model, ...).
# Output: Notice/nudge on stderr. Exit 0 always — a buggy bootstrap hook must
#         never block a session.
#
# Env seams (TEST-ONLY):
#   CODEGRAPH_BIN            codegraph executable (default: codegraph)
#   CODEGRAPH_DB_FILE        local index path (default: $CWD/.codegraph/codegraph.db)
#   CODEGRAPH_BOOTSTRAP_SYNC when "1", run the build in the foreground (tests)

set -uo pipefail

# Single-line, grep-friendly, screen-reader-friendly. The `[codegraph-bootstrap]`
# tag makes the source obvious in session output. Keep these constants in sync
# with tests/hooks/codegraph_bootstrap.bats.
BUILD_MSG='[codegraph-bootstrap] This project uses CodeGraph but has no local index yet — building it in the background. Use Read/Grep/Glob until it finishes; CodeGraph keeps it fresh after that.'
INSTALL_MSG='[codegraph-bootstrap] This project uses CodeGraph but it is not installed on this machine. Install it for code intelligence: https://github.com/colbymchenry/codegraph#installation'

main() {
  local input
  input=$(cat 2>/dev/null || true)

  # Fail-open on malformed input — never block a session.
  echo "$input" | jq -e . >/dev/null 2>&1 || return 0

  local cwd
  cwd=$(echo "$input" | jq -r '.cwd // empty' 2>/dev/null || true)
  [ -n "$cwd" ] && [ -d "$cwd" ] || cwd="$PWD"

  # Repo opt-in: the committed `.codegraph/` directory. Absent → not our concern.
  [ -d "$cwd/.codegraph" ] || return 0

  local bin db
  bin="${CODEGRAPH_BIN:-codegraph}"
  db="${CODEGRAPH_DB_FILE:-$cwd/.codegraph/codegraph.db}"

  # Local index already built — the MCP server's watcher + connect-time
  # catch-up keep it current from here. Nothing to do.
  [ -f "$db" ] && return 0

  # Fresh clone / new machine: the repo declares CodeGraph but this machine has
  # no index. Build it if the binary is here; otherwise nudge to install.
  if ! command -v "$bin" >/dev/null 2>&1; then
    printf '%s\n' "$INSTALL_MSG" >&2
    return 0
  fi

  printf '%s\n' "$BUILD_MSG" >&2

  if [ "${CODEGRAPH_BOOTSTRAP_SYNC:-0}" = "1" ]; then
    # Foreground path (tests, or anyone who wants a blocking build).
    ( cd "$cwd" && "$bin" init ) >/dev/null 2>&1 || true
  else
    # Detached so session start is never delayed by indexing. setsid when
    # available fully decouples the child; nohup is the portable fallback.
    if command -v setsid >/dev/null 2>&1; then
      setsid bash -c "cd \"\$1\" && \"\$2\" init >/dev/null 2>&1 || true" _ "$cwd" "$bin" >/dev/null 2>&1 &
    else
      nohup bash -c "cd \"\$1\" && \"\$2\" init >/dev/null 2>&1 || true" _ "$cwd" "$bin" >/dev/null 2>&1 &
    fi
  fi

  return 0
}

main
