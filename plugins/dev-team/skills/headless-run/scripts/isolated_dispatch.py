#!/usr/bin/env python3
"""Run a Claude Code command/skill headlessly in an ISOLATED subprocess.

Follow-up to issue #842. A benchmark harness that shells out to
`claude -p "/code-review …"` once per case (e.g. the #821 harness) must not
inherit the parent Claude Code Remote session's identity or tool surface.
Nested inside a live Remote session, a plain `claude -p` reuses the parent
`session_id` and sees Remote-injected MCP tools (CronCreate, PushNotification,
…). This script maximizes isolation:

  * a fresh temp HOME + CLAUDE_CONFIG_DIR (no shared config/memory/telemetry);
  * a SCRUBBED env with inherited CLAUDE_* session/Remote identity vars removed;
  * a fresh `--session-id <uuid>` per invocation (the key fix for the reused
    session_id) with NO `--resume` by default (see `build_cmd(resume=...)`
    for the harness's opt-in, same-session #999/#1002 retry exception —
    this script's own CLI/`run()` entry point never sets it);
  * `--output-format json` so the caller reads the verified session_id/cost;
  * a hard subprocess timeout.

Honest caveat: Remote-injected MCP *tools* cannot be removed via env — that
inheritance is an upstream Claude Code / Remote-runtime behavior. This script
gets as close to a clean local run as env + flags allow; the fully-supported
path for a benchmark harness is still a plain local CLI checkout, not one
nested inside a Remote session.

This mirrors and improves on the isolation precedent in
`scripts/run_tdd_experiment.py` (make_cell_home / cell_env / dispatch): that
version does `env = dict(os.environ)` and does NOT scrub identity vars — this
one does.

Stdlib only, Python 3.8+ (ADR 0014 / 0015). uuid/tempfile/subprocess are fine
in a shipped script — the no-random/no-Date restriction applies only to
Workflow scripts, not shipped Python.

Auth (#957): the fresh HOME also wipes Claude Code's login state, so a
dispatch reports "Not logged in" unless `ANTHROPIC_API_KEY` is set.
`~/.claude.json` alone is NOT sufficient to fix this (confirmed
empirically) — something under `~/.claude/` itself gates the login check.
Pass `--preserve-auth` to copy both into the cell home first (most of
`~/.claude/`, minus a `_CLAUDE_DIR_EXCLUDE` allowlist-complement of bulky
conversation/session/telemetry state) — see `copy_auth_state()`'s
docstring for the full tradeoff. Off by default here; the
code-review-benchmark harness turns it on unconditionally.

Usage:
    isolated_dispatch.py <prompt> [--cwd DIR] [--model MODEL] [--timeout SECS]
        [--preserve-auth]

Exits non-zero on dispatch error or timeout.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Dict, List, Optional

# Inherited env vars that carry the parent session's / Remote runtime's identity.
# Removing them stops the nested dispatch from re-adopting the parent identity
# through the environment. (Remote-injected MCP tools are NOT env-carried and
# cannot be scrubbed here — see the module docstring's upstream caveat.)
SCRUB_VARS = (
    "CLAUDE_SESSION_ID",
    "CLAUDE_CODE_SESSION_ID",
    "CLAUDE_SESSION",
    "CLAUDE_CODE_SESSION",
    "CLAUDE_PARENT_SESSION_ID",
    "CLAUDE_CODE_PARENT_SESSION_ID",
    "CLAUDE_RESUME",
    "CLAUDE_CODE_RESUME",
    "CLAUDE_CODE_ENTRYPOINT",
    "CLAUDE_CODE_REMOTE",
    "CLAUDE_REMOTE",
    "CLAUDE_REMOTE_SESSION_ID",
    "CLAUDE_CODE_REMOTE_SESSION_ID",
    "CLAUDE_CODE_SSE_PORT",
)

# Keys we always set ourselves — never scrub these even if the heuristic below
# would otherwise match, because build_env re-assigns them to fresh values.
_PROTECTED = frozenset({"CLAUDE_CONFIG_DIR"})


def _should_scrub(name: str) -> bool:
    """A var leaks parent identity if it's explicitly listed OR it's a CLAUDE_*
    var whose name mentions SESSION/REMOTE (catches Remote-runtime variants we
    have not enumerated by name)."""
    if name in _PROTECTED:
        return False
    if name in SCRUB_VARS:
        return True
    return name.startswith("CLAUDE_") and ("SESSION" in name or "REMOTE" in name)


def new_session_id() -> str:
    """A fresh session id for this dispatch. Passed to `--session-id` so the
    nested run cannot reuse the parent session_id."""
    return str(uuid.uuid4())


def make_cell_home(root: Optional[Path] = None) -> Path:
    """Create an isolated throwaway HOME + config dir for one dispatch.

    Like run_tdd_experiment.make_cell_home, but a self-contained tempdir the
    caller cleans up. A fresh HOME means no shared config, memory/, or telemetry
    state bleeds in from the parent."""
    base = Path(
        tempfile.mkdtemp(prefix="headless-run-", dir=str(root) if root else None)
    )
    (base / ".claude").mkdir(parents=True, exist_ok=True)
    return base


# Top-level entries under `~/.claude/` deliberately NOT copied by
# `copy_auth_state()` — bulky conversation/session/telemetry state that
# empirically is not needed to satisfy Claude Code's login check (verified
# live: a dispatch with these excluded still authenticated successfully).
# Named explicitly, not inferred, so this list stays auditable as the real
# `~/.claude/` layout evolves.
_CLAUDE_DIR_EXCLUDE = frozenset(
    {
        "history.jsonl",  # full conversation history
        "file-history",  # per-edit undo history
        "session-env",  # per-session environment captures (can be thousands of entries)
        "paste-cache",  # clipboard paste cache
        "shell-snapshots",  # shell state snapshots
        "debug",  # debug logs
        "telemetry",  # usage telemetry
        "downloads",  # downloaded artifacts
    }
)


def _make_bulky_state_ignorer(source_root: str):
    """Build a `shutil.copytree`-compatible `ignore` callback for
    `copy_auth_state()`, bound to `source_root` via closure (not a shared
    mutable attribute — `copy_auth_state()` runs concurrently across the
    benchmark harness's `--workers` thread pool, so shared mutable state
    here would race).

    Only excludes `_CLAUDE_DIR_EXCLUDE` entries when `root == source_root`
    (the top level of the copy) — not by name against every nested
    directory the walk visits, since a plugin could legitimately have its
    own `cache/`-or-similar-named subdir that must NOT be excluded just
    because the name matches.
    """

    def _ignore(root: str, names: List[str]) -> List[str]:
        if root != source_root:
            return []
        return [n for n in names if n in _CLAUDE_DIR_EXCLUDE]

    return _ignore


def copy_auth_state(home: Path, source_home: Optional[Path] = None) -> bool:
    """Copy `~/.claude.json` + (most of) `~/.claude/` into the fresh cell
    home so the dispatch keeps its Claude Code OAuth login (#957).

    A fresh `HOME` wipes out both, and — confirmed empirically, twice —
    `~/.claude.json` alone (even including its `oauthAccount` key) is NOT
    sufficient to restore login; something else under `~/.claude/` itself
    gates Claude Code's login check ahead of its actual (Keychain-backed,
    `HOME`-independent) token lookup. Copying the whole `.claude/` tree
    does restore it. `_CLAUDE_DIR_EXCLUDE` skips the clearly bulky,
    clearly-not-auth-related pieces (conversation history, per-session
    captures, telemetry, debug logs) to keep the isolation tradeoff as
    small as it can be while still working — everything else (`settings
    .json`, `projects/`, `sessions/`, `plugins/`, `skills/`, etc.) is
    copied, since we don't have a confirmed narrower answer for which of
    those specifically satisfies the login check.

    Best-effort: returns `False` (never raises) if neither source exists.
    Broken/dangling symlinks under `.claude/` (e.g. stale plugin
    marketplace paths) are copied as links, not followed/failed on.

    Opt-in here via `--preserve-auth` (other callers keep today's
    stricter default); the code-review benchmark harness turns it on
    unconditionally (see `runner.py`).
    """
    source_home = source_home or Path.home()
    source_claude_json = source_home / ".claude.json"
    source_claude_dir = source_home / ".claude"
    if not source_claude_json.is_file() and not source_claude_dir.is_dir():
        return False

    if source_claude_json.is_file():
        shutil.copy(source_claude_json, Path(home) / ".claude.json")

    if source_claude_dir.is_dir():
        shutil.copytree(
            source_claude_dir,
            Path(home) / ".claude",
            symlinks=True,
            ignore_dangling_symlinks=True,
            ignore=_make_bulky_state_ignorer(str(source_claude_dir)),
            dirs_exist_ok=True,
        )
    return True


def build_env(home: Path, base: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Return a SCRUBBED environment rooted at a fresh HOME.

    Starts from `base` (defaults to os.environ), drops every parent
    session/Remote identity var, then sets a fresh HOME + CLAUDE_CONFIG_DIR,
    marks the run a sandbox (so headless --dangerously-skip-permissions is
    allowed off-root), and pins telemetry off."""
    src = dict(os.environ) if base is None else dict(base)
    env = {k: v for k, v in src.items() if not _should_scrub(k)}
    home = Path(home)
    env["HOME"] = str(home)
    env["CLAUDE_CONFIG_DIR"] = str(home / ".claude")
    env["IS_SANDBOX"] = "1"
    env["DEV_TEAM_TELEMETRY"] = "off"
    return env


def _is_root() -> bool:
    getuid = getattr(os, "getuid", None)
    return getuid is not None and getuid() == 0


def build_cmd(
    prompt: str,
    session_id: str,
    model: str,
    cwd: Optional[str] = None,  # accepted for symmetry; cwd is applied at run time
    skip_permissions: Optional[bool] = None,
    resume: bool = False,
) -> List[str]:
    """The `claude -p` argv for one isolated dispatch.

    Default (`resume=False`): always carries `--session-id <uuid>` (the
    reused-session fix) and `--output-format json`; NEVER `--resume`/
    `--fork-session` (those would re-adopt an existing session).
    `--dangerously-skip-permissions` is added only when not running as root
    (the CLI blocks it under root), matching run_tdd_experiment's
    `os.getuid() == 0` guard.

    `resume=True` (#999/#1002's harness-side retry-once backstop, see
    `evals/code-review-benchmark/runner.py::make_isolated_dispatch_fn`):
    targets an EXISTING session via `--resume <session_id>` instead of
    starting a fresh one — used for a cheap same-session follow-up dispatch
    when the primary dispatch's `/code-review --json` response narrated
    instead of emitting its required JSON payload, so the retry doesn't
    redo the (expensive) review, only asks the same session to re-state its
    already-computed result. Mutually exclusive with `--session-id` by
    construction (the CLI only accepts one or the other)."""
    if skip_permissions is None:
        skip_permissions = not _is_root()
    cmd = ["claude", "-p", prompt]
    if resume:
        cmd += ["--resume", session_id]
    else:
        cmd += ["--session-id", session_id]
    cmd += ["--output-format", "json", "--model", model]
    if skip_permissions:
        cmd.append("--dangerously-skip-permissions")
    return cmd


def _normalize_result(stdout: str) -> Dict:
    """Parse the `--output-format json` result into the fields a harness wants."""
    result = {
        "session_id": None,
        "cost_usd": None,
        "input_tokens": None,
        "output_tokens": None,
        "tokens_total": None,
        "num_turns": None,
        "duration_ms": None,
        "is_error": True,
        "parsed": False,
    }
    try:
        d = json.loads(stdout)
    except (json.JSONDecodeError, ValueError, TypeError):
        return result
    usage = d.get("usage", {}) or {}
    inp = (
        int(usage.get("input_tokens", 0) or 0)
        + int(usage.get("cache_creation_input_tokens", 0) or 0)
        + int(usage.get("cache_read_input_tokens", 0) or 0)
    )
    out = int(usage.get("output_tokens", 0) or 0)
    result.update(
        session_id=d.get("session_id"),
        cost_usd=d.get("total_cost_usd"),
        input_tokens=inp,
        output_tokens=out,
        tokens_total=inp + out,
        num_turns=d.get("num_turns"),
        duration_ms=d.get("duration_ms"),
        is_error=bool(d.get("is_error")),
        parsed=True,
    )
    return result


def run(
    prompt: str, cwd: str, model: str, timeout: int, preserve_auth: bool = False
) -> int:
    """Do one isolated dispatch end-to-end; print the normalized JSON result.

    Returns a process exit code: 0 on a clean parse with is_error false,
    non-zero on timeout, parse failure, or a dispatch that reported an error.
    `preserve_auth` copies the real `~/.claude.json` into the fresh cell home
    first — see `copy_auth_state()` (#957)."""
    home = make_cell_home()
    if preserve_auth:
        copy_auth_state(home)
    session_id = new_session_id()
    env = build_env(home)
    cmd = build_cmd(prompt, session_id, model, cwd=cwd)
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        print(
            json.dumps(
                {"is_error": True, "subtype": "timeout", "session_id": session_id}
            )
        )
        return 124
    finally:
        shutil.rmtree(str(home), ignore_errors=True)

    result = _normalize_result(proc.stdout or "")
    print(json.dumps(result))
    if not result["parsed"]:
        sys.stderr.write((proc.stderr or "").strip() + "\n")
        return 1
    return 1 if result["is_error"] else 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a Claude Code prompt headlessly in an isolated subprocess."
    )
    parser.add_argument("prompt", help="Prompt or slash command, e.g. '/code-review'.")
    parser.add_argument("--cwd", default=".", help="Working directory for the run.")
    parser.add_argument("--model", default="sonnet", help="Model for the dispatch.")
    parser.add_argument(
        "--timeout", type=int, default=900, help="Subprocess timeout, seconds."
    )
    parser.add_argument(
        "--preserve-auth",
        action="store_true",
        help=(
            "Copy ~/.claude.json into the fresh cell home so the dispatch "
            "keeps its Claude Code OAuth login (#957) instead of requiring "
            "ANTHROPIC_API_KEY. Also carries over mcpServers and other app "
            "state into the dispatch — off by default."
        ),
    )
    args = parser.parse_args(argv)
    return run(
        args.prompt,
        args.cwd,
        args.model,
        args.timeout,
        preserve_auth=args.preserve_auth,
    )


if __name__ == "__main__":
    raise SystemExit(main())
