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

import subprocess
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_LIB_DIR = _SCRIPT_DIR / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from artifact_paths import project_root
from banned_scripts_policy import (
    ALLOWED_RELATIVE_PATHS,
    BANNED_EXTENSIONS,
    SCOPED_PREFIX,
    looks_like_monorepo_checkout,
)
from stdin_json import read_stdin_json

_GIT_TIMEOUT_S = 10

# Cap on files walked inside a single untracked directory (#1879). A
# wholly-new directory collapses to one `?? some/new/dir/` porcelain line —
# it must be recursed into on disk to see individual files — but an
# unbounded walk could hang on a pathological huge directory. This mirrors
# _GIT_TIMEOUT_S's intent (never let this scan hang indefinitely) with a
# count bound instead of a wall-clock one, since `Path.rglob` has no native
# timeout.
_MAX_UNTRACKED_DIR_ENTRIES = 5000


def _porcelain_paths(root: Path) -> list[str]:
    """Every path `git status --porcelain` reports under
    `plugins/dev-team/`, tracked or untracked. Fails open (returns `[]`) on
    any git failure — no repo, git missing, timeout — matching every other
    advisory hook's contract: a scan that can't run must never block.

    An entry whose path no longer exists on disk is skipped — checked by
    actually stat-ing it, not by inferring "deleted" from a `D` in the
    status code, which is wrong for an unresolved-merge conflict code
    (`DU`/`UD`) where the path IS still present in the working tree. The
    "old -> new" rename/copy arrow is only stripped when the status code
    actually reports a rename or copy (`R`/`C`), not on every entry that
    happens to contain the literal substring "-> ".
    """
    try:
        result = subprocess.run(
            [
                "git",
                "-c",
                "core.quotePath=false",
                "status",
                "--porcelain",
                "--",
                SCOPED_PREFIX.rstrip("/"),
            ],
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
        if len(line) < 3:
            continue
        status = line[:2]
        entry = line[3:]
        if status[0] in ("R", "C") and "-> " in entry:
            entry = entry.split("-> ", 1)[1]
        entry = entry.strip().strip('"')
        if not entry:
            continue
        # Test the actual runtime property ("is this path still present on
        # disk") rather than inferring it from the status code: a plain `D`
        # skip is wrong for an unresolved-merge conflict code (`DU`/`UD`),
        # where the path IS present in the working tree despite carrying a
        # `D` character.
        if not (root / entry).exists():
            continue
        paths.append(entry)
    return paths


def _files_in_untracked_dir(root: Path, rel_dir: str) -> list[str]:
    """Recurse into a wholly-new untracked directory (a porcelain entry
    ending in `/`), returning banned-extension files found inside, relative
    to `root` in POSIX form. Bounded by `_MAX_UNTRACKED_DIR_ENTRIES` and
    fails open (returns whatever was found so far) on any OS error.

    Relativizes via the known `root`/`rel_dir` prefix, not `path.resolve()`
    — resolving would follow a symlink named e.g. `evil.sh` to its target,
    which can land outside `root` and raise `ValueError`, silently dropping
    the entry. That's weaker than the sibling non-directory branch in
    `_porcelain_paths`, which flags such a link (it never resolves at all);
    this walk must not be the one gap in an otherwise-consistent scan.
    """
    hits: list[str] = []
    try:
        for count, path in enumerate((root / rel_dir).rglob("*")):
            if count >= _MAX_UNTRACKED_DIR_ENTRIES:
                break
            if not (path.is_file() or path.is_symlink()):
                continue
            if not path.name.lower().endswith(BANNED_EXTENSIONS):
                continue
            try:
                rel = path.relative_to(root).as_posix()
            except ValueError:
                continue
            hits.append(rel)
    except OSError:
        return hits
    return hits


def find_banned_files(root: Path) -> list[str]:
    hits = set()
    for rel in _porcelain_paths(root):
        if rel.endswith("/"):
            # A brand-new untracked directory — expand it on disk (#1879)
            # rather than checking the directory path string itself.
            if not rel.startswith(SCOPED_PREFIX):
                continue
            for found in _files_in_untracked_dir(root, rel):
                if found in ALLOWED_RELATIVE_PATHS:
                    continue
                hits.add(found)
            continue
        if not rel.startswith(SCOPED_PREFIX) or rel in ALLOWED_RELATIVE_PATHS:
            continue
        if rel.lower().endswith(BANNED_EXTENSIONS):
            hits.add(rel)
    return sorted(hits)


def main() -> int:
    payload = read_stdin_json() or {}
    cwd = Path(payload.get("cwd") or ".")

    # (#1861) Cheap, non-git early exit for any checkout where this
    # monorepo's own plugins/dev-team/ tree doesn't exist — e.g. every
    # downstream install of the plugin. This hook runs on the PostToolUse
    # `*` matcher (every tool call, forever), so it must not shell out to
    # `git rev-parse`/`git status` at all when there is nothing under
    # plugins/dev-team/ to scan — checked via a plain filesystem walk
    # BEFORE project_root() (which itself shells out to git), not after.
    if not looks_like_monorepo_checkout(cwd):
        return 0

    root = project_root(cwd)
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
