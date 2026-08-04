#!/usr/bin/env python3
"""scan_bash_for_banned_scripts.py — real-time PreToolUse denial of new
shell-script writes under plugins/dev-team/ (#1755).

This repo's own CLAUDE.md states the rule ("every shipped
plugins/dev-team/ script is Python 3.10+ stdlib-only", ADR 0014/0015) and CI
has a `check-python-only` gate, but neither stops a `.sh`/`.bash`/`.bat`/
`.cmd`/`.ps1` file from being written *during* a session — the violation was
only caught later, in code review or CI. This hook closes that gap at the
point of the `Bash` tool call itself, before the write happens.

Heuristic, not exhaustive: it regex/token-scans the command string for
redirect (`>`, `>>`), `cp`, `mv`, and `tee` write targets. A sufficiently
obfuscated command (base64-decoded write, a wrapper script, `eval`) can
evade it — this hook's own scan says so, deliberately, rather than implying
a guarantee it can't back. `scan_banned_scripts.py` (PostToolUse, `*`
matcher) is the required backstop: it inspects the real working tree after
every tool call, catching anything this scan misses regardless of which
tool wrote it.

Contract (docs/python-hook-contract.md):
    Input : PreToolUse JSON on stdin with tool_input.command (Bash matcher)
    Output: exit 0 = allow; exit 2 = block (message on stdout AND stderr)

Stdlib-only. See ADR 0014/0015.
"""

from __future__ import annotations

import json
import re
import shlex
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_LIB_DIR = _SCRIPT_DIR / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from artifact_paths import project_root

# The extensions this repo's CLAUDE.md forbids under plugins/dev-team/.
BANNED_EXTENSIONS = (".sh", ".bash", ".bat", ".cmd", ".ps1")

SCOPED_PREFIX = "plugins/dev-team/"

# The two documented bootstrap-shim exceptions (repo CLAUDE.md § Script
# authoring — Python only): install.sh can't itself be Python because it
# must run before an interpreter is guaranteed on PATH, and hooks/py.sh is
# the trampoline that resolves one. Every other invocation under
# plugins/dev-team/ routes through py.sh, never a bare interpreter.
ALLOWED_RELATIVE_PATHS = {
    "plugins/dev-team/install.sh",
    "plugins/dev-team/hooks/py.sh",
}

_REDIRECT_RE = re.compile(r">>?\s*([^\s;|&<>]+)")


def _read_stdin() -> str:
    try:
        return sys.stdin.read()
    except Exception:  # noqa: BLE001 - never crash a hook on stdin read
        return ""


def _has_banned_extension(path_str: str) -> bool:
    return path_str.lower().endswith(BANNED_EXTENSIONS)


def _redirect_targets(command: str) -> list[str]:
    return [
        match.group(1)
        for match in _REDIRECT_RE.finditer(command)
        if _has_banned_extension(match.group(1))
    ]


def _copy_move_tee_targets(command: str) -> list[str]:
    """Best-effort tokenization to catch `cp`/`mv`/`tee` destinations.

    Splits on shell command separators first so each simple command
    tokenizes on its own — a single `shlex.split()` over a compound command
    (`a && b`) would otherwise misattribute tokens across commands.
    Malformed quoting is skipped, never crashed on: a scan error must fail
    open, not block a legitimate command it couldn't parse.
    """
    targets: list[str] = []
    for segment in re.split(r"&&|\|\||[;|]", command):
        segment = segment.strip()
        if not segment:
            continue
        try:
            tokens = shlex.split(segment)
        except ValueError:
            continue
        if not tokens:
            continue
        prog = Path(tokens[0]).name
        args = [t for t in tokens[1:] if not t.startswith("-")]
        if prog == "tee":
            # tee writes to every named file, not just the last.
            targets.extend(a for a in args if _has_banned_extension(a))
        elif prog in ("cp", "mv"):
            # Simple-invocation heuristic: the destination is the last
            # positional argument. Multi-source `cp a b DEST` still resolves
            # correctly since DEST is last regardless of source count.
            candidates = [a for a in args if _has_banned_extension(a)]
            if candidates:
                targets.append(candidates[-1])
    return targets


def _scoped_relative_path(target: str, cwd: Path, root: Path) -> str | None:
    """Resolve `target` (as written in the command) against `cwd`, then
    return its path relative to `root` in POSIX form — or ``None`` when it
    resolves outside `root` entirely."""
    candidate = Path(target)
    resolved = candidate if candidate.is_absolute() else (cwd / candidate)
    try:
        rel = resolved.resolve().relative_to(root.resolve())
    except ValueError:
        return None
    return rel.as_posix()


def find_banned_write(command: str, cwd: Path, root: Path) -> str | None:
    """Return the first plugins/dev-team/-scoped banned-extension write
    target in `command` (relative to `root`), or ``None``. Skips the two
    documented bootstrap-shim carve-outs."""
    for target in [*_redirect_targets(command), *_copy_move_tee_targets(command)]:
        rel = _scoped_relative_path(target, cwd, root)
        if rel is None or not rel.startswith(SCOPED_PREFIX):
            continue
        if rel in ALLOWED_RELATIVE_PATHS:
            continue
        return rel
    return None


def main() -> int:
    raw = _read_stdin()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    tool_input = payload.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str) or not command.strip():
        return 0

    cwd = Path(payload.get("cwd") or ".")
    root = project_root(cwd)

    hit = find_banned_write(command, cwd, root)
    if hit is None:
        return 0

    message = (
        f"[BLOCK] {hit} is a shell-script write under plugins/dev-team/. "
        "Every shipped script there must be Python 3.10+ stdlib-only "
        "(ADR 0014/0015; repo CLAUDE.md § Script authoring). Write a "
        ".py module instead, or confirm this is genuinely one of the two "
        "documented bootstrap-shim exceptions (plugins/dev-team/install.sh, "
        "plugins/dev-team/hooks/py.sh)."
    )
    sys.stdout.write(message + "\n")
    sys.stderr.write(message + "\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
