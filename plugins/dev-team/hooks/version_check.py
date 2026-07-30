#!/usr/bin/env python3
"""Python port of hooks/version-check.sh (#609 / #572 Phase 3).

Claude Code PostToolUse hook — checks once per day whether the plugin repo
has upstream updates. If updates are available, prints a notice suggesting
`/upgrade`.

Contract (docs/python-hook-contract.md):
    Input : PostToolUse JSON on stdin (ignored)
    Output: Update notice on stdout, or nothing if up-to-date
    Cache : /tmp/adt-version-check-<date> — daily cache prevents repeated
            checks; replays cached message if any
    Exit  : Always 0 (advisory, never blocks)

Stdlib-only. Python 3.8+. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def _cache_dir() -> Path:
    """Mirror the .sh's hard-coded `/tmp` for the daily cache path.

    The bash script writes to `/tmp/adt-version-check-<date>` unconditionally
    — no `${TMPDIR:-/tmp}` fallback. Windows Git Bash treats `/tmp` as the
    MSYS-mounted temp directory, so the same literal is portable across the
    three platforms this port targets. Byte-parity with the .sh requires
    the same literal here.

    ``DEV_TEAM_VERSION_CHECK_CACHE_DIR``, when set, overrides this — a
    test-only escape hatch (#1574) so pytest can give each worker/run its
    own cache path instead of racing on the one real, shared `/tmp` file.
    Production callers never set it, so real behavior is unchanged.
    """
    override = os.environ.get("DEV_TEAM_VERSION_CHECK_CACHE_DIR")
    return Path(override) if override else Path("/tmp")


def _today_cache_file() -> Path:
    # Local wall-clock date for a daily cache filename, not a comparison —
    # mirrors the ported .sh's `date +%Y-%m-%d`, which also uses local time.
    today = datetime.now().strftime("%Y-%m-%d")  # noqa: DTZ005
    return _cache_dir() / f"adt-version-check-{today}"


def _plugin_dir() -> Path:
    """The plugin's repo root — one level up from hooks/."""
    return Path(__file__).resolve().parent.parent


def _git(args, cwd: Path, timeout: float = 5.0):
    """Run git with the given args and cwd, capturing output. Returns the
    CompletedProcess; caller inspects returncode. Any FileNotFoundError
    (git absent) or timeout returns None."""
    try:
        return subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


def _is_git_repo(plugin_dir: Path) -> bool:
    r = _git(["rev-parse", "--is-inside-work-tree"], plugin_dir, timeout=2.0)
    return r is not None and r.returncode == 0


def _default_branch(plugin_dir: Path) -> str:
    r = _git(["symbolic-ref", "refs/remotes/origin/HEAD"], plugin_dir, timeout=2.0)
    if r is None or r.returncode != 0:
        return "main"
    ref = r.stdout.strip()
    # Strip the `refs/remotes/origin/` prefix if present.
    prefix = "refs/remotes/origin/"
    if ref.startswith(prefix):
        return ref[len(prefix) :]
    return ref or "main"


def _fetch(plugin_dir: Path, timeout: float = 5.0) -> bool:
    """Fetch quietly with a short timeout. Returns True on success."""
    r = _git(["fetch", "origin", "--quiet"], plugin_dir, timeout=timeout)
    return r is not None and r.returncode == 0


def _commits_behind(plugin_dir: Path, branch: str) -> int:
    r = _git(
        ["rev-list", "--count", f"HEAD..origin/{branch}"],
        plugin_dir,
        timeout=2.0,
    )
    if r is None or r.returncode != 0:
        return 0
    try:
        return int(r.stdout.strip())
    except ValueError:
        return 0


def main() -> int:
    # Consume stdin (required by the hook protocol).
    try:
        sys.stdin.read()
    except (OSError, ValueError):
        pass

    cache_file = _today_cache_file()
    if cache_file.is_file():
        # Already checked today — replay cached message if any.
        try:
            cached = cache_file.read_text()
        except OSError:
            cached = ""
        # Bash: `CACHED=$(cat "$CACHE_FILE")` strips trailing newlines the
        # same way command substitution does. Then `[ -n "$CACHED" ] &&
        # echo "$CACHED"` prints only when non-empty and re-adds one LF.
        # Match both: rstrip newlines, print with a single trailing LF iff
        # anything remains.
        stripped = cached.rstrip("\n")
        if stripped:
            print(stripped)
        return 0

    plugin_dir = _plugin_dir()

    if not _is_git_repo(plugin_dir):
        # Not a git repo (vendored copy) — skip silently but cache.
        try:
            cache_file.touch()
        except OSError:
            pass
        return 0

    if not _fetch(plugin_dir):
        # Network too slow / fetch failed — skip silently, don't cache so it
        # retries later.
        return 0

    branch = _default_branch(plugin_dir)
    behind = _commits_behind(plugin_dir, branch)

    if behind > 0:
        msg = (
            f"📦 dev-team@bfinster: {behind} update(s) available. "
            "Run /upgrade to update."
        )
        try:
            cache_file.write_text(msg + "\n")
        except OSError:
            pass
        print(msg)
    else:
        # Up to date — cache empty result so subsequent same-day fires skip.
        try:
            cache_file.touch()
        except OSError:
            pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
