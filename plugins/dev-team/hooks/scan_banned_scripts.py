#!/usr/bin/env python3
"""scan_banned_scripts.py — PostToolUse backstop for
scan_bash_for_banned_scripts.py (#1755).

The PreToolUse scan only intercepts a *Bash command string*; a banned
`.sh`/`.bash`/`.bat`/`.cmd`/`.ps1` file written any other way (the `Write` or
`Edit` tool, or a `Bash` command whose target the PreToolUse heuristic
missed) still lands under plugins/dev-team/. This hook is the deterministic
backstop: it runs after EVERY tool call (`*` matcher) and inspects the
actual working tree via `git status --porcelain`, so it catches a banned
file regardless of which tool created it.

The tool call that wrote the file has already completed by the time this
hook runs — exit 2 cannot undo that. What it does instead is what
`docs/python-hook-contract.md`'s block contract is for: it puts the offense
directly in front of the agent (stdout AND stderr) so the very next thing it
does is remove or convert the file, rather than the violation surviving
silently to code review or CI.

Contract (docs/python-hook-contract.md):
    Input : PostToolUse JSON on stdin (matcher "*" — any tool_name)
    Output: exit 0 = clean; exit 2 = block (message on stdout AND stderr)

Stdlib-only. See ADR 0014/0015.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_LIB_DIR = _SCRIPT_DIR / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from artifact_paths import project_root

BANNED_EXTENSIONS = (".sh", ".bash", ".bat", ".cmd", ".ps1")
SCOPED_PREFIX = "plugins/dev-team/"

# Mirrors scan_bash_for_banned_scripts.py's carve-out — the two documented
# bootstrap-shim exceptions (repo CLAUDE.md § Script authoring).
ALLOWED_RELATIVE_PATHS = {
    "plugins/dev-team/install.sh",
    "plugins/dev-team/hooks/py.sh",
}

_GIT_TIMEOUT_S = 10


def _read_stdin() -> str:
    try:
        return sys.stdin.read()
    except Exception:  # noqa: BLE001 - never crash a hook on stdin read
        return ""


def _porcelain_paths(root: Path) -> list[str]:
    """Every path `git status --porcelain` reports under
    `plugins/dev-team/`, tracked or untracked. Fails open (returns `[]`) on
    any git failure — no repo, git missing, timeout — matching every other
    advisory hook's contract: a scan that can't run must never block."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--", SCOPED_PREFIX.rstrip("/")],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
            timeout=_GIT_TIMEOUT_S,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []

    paths = []
    for line in result.stdout.splitlines():
        entry = line[3:] if len(line) > 3 else ""
        # Rename lines carry "old -> new" — the new path is what's on disk.
        if "-> " in entry:
            entry = entry.split("-> ", 1)[1]
        entry = entry.strip().strip('"')
        if entry:
            paths.append(entry)
    return paths


def find_banned_files(root: Path) -> list[str]:
    hits = set()
    for rel in _porcelain_paths(root):
        if not rel.startswith(SCOPED_PREFIX) or rel in ALLOWED_RELATIVE_PATHS:
            continue
        if rel.lower().endswith(BANNED_EXTENSIONS):
            hits.add(rel)
    return sorted(hits)


def main() -> int:
    raw = _read_stdin()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    root = project_root(Path(payload.get("cwd") or "."))

    hits = find_banned_files(root)
    if not hits:
        return 0

    message = (
        "[BLOCK] Shell script(s) present under plugins/dev-team/ — every "
        "shipped script there must be Python 3.10+ stdlib-only (ADR "
        "0014/0015; repo CLAUDE.md § Script authoring): " + ", ".join(hits) + ". "
        "Remove or convert to .py, or confirm this is genuinely one of the "
        "two documented bootstrap-shim exceptions "
        "(plugins/dev-team/install.sh, plugins/dev-team/hooks/py.sh)."
    )
    sys.stdout.write(message + "\n")
    sys.stderr.write(message + "\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
