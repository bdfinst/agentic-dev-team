"""Shared repowise `.mcp.json` detection + relocation (#1747).

`repowise init`/`repowise update` unconditionally writes a `mcpServers.
repowise` entry into the project-root `.mcp.json`, baking in the invoking
machine's absolute filesystem path (a known, currently-open upstream bug:
repowise-dev/repowise#1117). When `.mcp.json` is git-tracked — a team may
legitimately commit it to distribute other MCP servers (`codegraph`, an
internal org server) that don't bake in a local path — that entry breaks
for every other clone/teammate.

`detect()` is the single shared predicate both consumers of this module
need: `project-init/SKILL.md`'s `.mcp.json` standing check (which calls
`relocate()` via this module's CLI) and `hooks/mcp_json_repowise_nudge.py`
(the SessionStart hook that prompts an already-initialized project to
re-run `/project-init`). Implemented once here so the two can never drift
out of sync on what counts as "needs fixing."

`relocate()` registers at `local` scope BEFORE stripping the tracked entry
— never the reverse — so a failed `claude mcp add` (CLI missing, timeout,
non-zero exit) leaves `.mcp.json` untouched rather than deleting the only
registration that existed. Every other `mcpServers` entry is preserved
byte-for-byte; only the `repowise` key is ever touched.

Stdlib-only. Python 3.10+. See ADR 0014 / ADR 0015.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

_MCP_JSON_NAME = ".mcp.json"
_SERVER_NAME = "repowise"


def _load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _dump_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def is_tracked(mcp_json_path: Path, cwd: Path) -> bool:
    """True iff `mcp_json_path` exists and `git ls-files --error-unmatch`
    (run with `cwd`) confirms it's tracked. False on any git failure (not a
    repo, git missing, timeout) — never raises."""
    if not mcp_json_path.is_file():
        return False
    try:
        completed = subprocess.run(
            ["git", "ls-files", "--error-unmatch", mcp_json_path.name],
            cwd=str(cwd),
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def detect(cwd: Path) -> dict | None:
    """The shared predicate: the `repowise` `mcpServers` entry iff
    `<cwd>/.mcp.json` exists, is git-tracked, AND carries a `repowise` key.
    None on anything else, including any internal failure — this must
    never raise, since both callers treat None as "nothing to do"."""
    try:
        mcp_json_path = Path(cwd) / _MCP_JSON_NAME
        if not is_tracked(mcp_json_path, Path(cwd)):
            return None
        servers = _load_json(mcp_json_path).get("mcpServers")
        if not isinstance(servers, dict):
            return None
        entry = servers.get(_SERVER_NAME)
        return entry if isinstance(entry, dict) else None
    except Exception:  # noqa: BLE001 - fail-open: a detection bug must never propagate
        return None


def strip_entry(mcp_json_path: Path) -> bool:
    """Remove only the `repowise` key from `mcp_json_path`'s `mcpServers`
    object, preserving every other entry untouched. Drops the `mcpServers`
    key entirely if removing `repowise` leaves it empty. Idempotent: a
    no-op (returns False, no write) when there's nothing to strip."""
    config = _load_json(mcp_json_path)
    servers = config.get("mcpServers")
    if not isinstance(servers, dict) or _SERVER_NAME not in servers:
        return False
    servers.pop(_SERVER_NAME)
    if servers:
        config["mcpServers"] = servers
    else:
        config.pop("mcpServers", None)
    _dump_json(mcp_json_path, config)
    return True


def _register_local_scope(repo_root: Path) -> bool:
    """`claude mcp add repowise --scope local -- repowise mcp <repo_root>
    --transport stdio`. True on exit 0; False on any failure (`claude` CLI
    missing, non-zero exit, timeout) — never raises. Deliberately re-derives
    `args` from the CURRENT repo root rather than reusing the stripped
    entry's own `args` — those carry the OLD, wrong machine's path, which is
    exactly the bug being fixed."""
    try:
        completed = subprocess.run(
            [
                "claude", "mcp", "add", _SERVER_NAME, "--scope", "local",
                "--", _SERVER_NAME, "mcp", str(repo_root), "--transport", "stdio",
            ],
            cwd=str(repo_root),
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def relocate(
    cwd: Path, *, register: Callable[[Path], bool] = _register_local_scope
) -> str:
    """Detect -> register at local scope -> strip from the tracked file, in
    that order (never strip-then-register — see module docstring). Returns
    one of:
        "not-tracked"       -- .mcp.json missing, or not git-tracked
        "no-repowise-entry" -- tracked, but no repowise key to relocate
        "relocated"         -- registered locally and stripped
        "relocate-failed"   -- repowise entry found, but `claude mcp add`
                                failed; .mcp.json is left untouched

    `register` is injectable (stdlib `Callable`, defaulting to the real
    `claude mcp add` call) so callers/tests can verify both branches
    without a real `claude` CLI or a live MCP registration. Never raises.
    """
    cwd = Path(cwd)
    entry = detect(cwd)
    if entry is None:
        return "no-repowise-entry" if is_tracked(cwd / _MCP_JSON_NAME, cwd) else "not-tracked"

    if not register(cwd):
        return "relocate-failed"

    strip_entry(cwd / _MCP_JSON_NAME)
    return "relocated"


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["relocate"])
    parser.add_argument("--cwd", default=".")
    args = parser.parse_args()

    if args.action == "relocate":
        print(relocate(Path(args.cwd).resolve()))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
