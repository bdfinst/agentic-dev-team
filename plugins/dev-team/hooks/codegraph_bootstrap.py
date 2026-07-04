#!/usr/bin/env python3
"""codegraph_bootstrap — Claude Code SessionStart hook (Python port).

Python port of hooks/codegraph-bootstrap.sh (#592 / #572 Phase 3).

Rebuilds the per-machine CodeGraph index when a freshly cloned repo has
adopted CodeGraph but has no local index yet. This is how a team shares
CodeGraph — the SQLite db is derived from source and machine-local so it
is never committed; every clone rebuilds it automatically on the first
session. See docs/adr/0012-auto-bootstrap-codegraph-index-per-clone.md.

Contract (docs/python-hook-contract.md):
    Input : SessionStart JSON on stdin
    Output: Notice/nudge on stderr (never stdout)
    Exit  : always 0 (a buggy bootstrap must never block a session)

Env seams (test-only):
    CODEGRAPH_BIN            codegraph executable (default: codegraph)
    CODEGRAPH_DB_FILE        index path (default: $CWD/.codegraph/codegraph.db)
    CODEGRAPH_BOOTSTRAP_SYNC when "1", run the build in the foreground

Stdlib-only. Python 3.8+.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional


_HOOK_DIR = Path(__file__).resolve().parent
_LIB_DIR = _HOOK_DIR / "lib"

sys.path.insert(0, str(_LIB_DIR))
try:
    from stdin_json import read_stdin_json  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover

    def read_stdin_json() -> Optional[dict]:  # type: ignore[misc]
        return None


# Single-line messages — kept in sync with the .sh sibling and the bats.
_BUILD_MSG = (
    "[codegraph-bootstrap] This project uses CodeGraph but has no local "
    "index yet — building it in the background. Use Read/Grep/Glob until "
    "it finishes; CodeGraph keeps it fresh after that."
)
_INSTALL_MSG = (
    "[codegraph-bootstrap] This project uses CodeGraph but it is not "
    "installed on this machine. Install it for code intelligence: "
    "https://github.com/colbymchenry/codegraph#installation"
)


def main() -> int:
    # Empty stdin is a valid input — silent no-op like the .sh's
    # `echo "$input" | jq -e .` on empty input (jq exits non-zero).
    payload = read_stdin_json()
    # Fail-open on malformed / empty input.
    if payload is None:
        return 0

    cwd_str = str(payload.get("cwd") or "").strip()
    cwd = Path(cwd_str) if cwd_str and Path(cwd_str).is_dir() else Path.cwd()

    # Repo opt-in: the committed `.codegraph/` directory.
    if not (cwd / ".codegraph").is_dir():
        return 0

    bin_name = os.environ.get("CODEGRAPH_BIN", "codegraph")
    db_env = os.environ.get("CODEGRAPH_DB_FILE")
    db_path = Path(db_env) if db_env else (cwd / ".codegraph" / "codegraph.db")

    # Local index already built.
    if db_path.is_file():
        return 0

    # Fresh clone: build if the binary is available, else nudge.
    #
    # The .sh uses `command -v "$bin"`. On the .sh, a path-like $bin (e.g.
    # /nonexistent/codegraph) is considered "available" by `command -v`
    # only if the file exists and is executable. Match that behavior:
    #   - if bin looks like a path (contains /), check its file directly
    #   - else, search PATH via shutil.which
    if "/" in bin_name or "\\" in bin_name:
        resolved = (
            bin_name
            if Path(bin_name).is_file() and os.access(bin_name, os.X_OK)
            else None
        )
    else:
        resolved = shutil.which(bin_name)

    if resolved is None:
        print(_INSTALL_MSG, file=sys.stderr)
        return 0

    print(_BUILD_MSG, file=sys.stderr)

    sync = os.environ.get("CODEGRAPH_BOOTSTRAP_SYNC", "0") == "1"
    try:
        if sync:
            # Foreground path — tests, or anyone wanting a blocking build.
            subprocess.run(
                [resolved, "init"],
                cwd=str(cwd),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            # Detached so SessionStart is never delayed by indexing.
            # Popen with start_new_session gives us the equivalent of setsid
            # on POSIX; on Windows we get CREATE_NEW_PROCESS_GROUP via
            # DETACHED_PROCESS. We swallow all IO to match the .sh's `>/dev/null 2>&1`.
            popen_kwargs = {
                "cwd": str(cwd),
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
                "stdin": subprocess.DEVNULL,
            }
            if os.name == "posix":
                popen_kwargs["start_new_session"] = True
            else:
                # Windows: DETACHED_PROCESS = 0x00000008
                popen_kwargs["creationflags"] = 0x00000008  # type: ignore[assignment]
            subprocess.Popen([resolved, "init"], **popen_kwargs)  # noqa: S603
    except OSError:
        # Never block a session on subprocess failure.
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
