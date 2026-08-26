#!/usr/bin/env python3
"""ci_tree_cache.py — skip a gate whose tree has not changed since it last
passed (issue #2002).

Why this exists. `chk_hook_units` collects 9,469 tests and is the gate's
wall-clock long pole. Session-report data shows **1,029 runs of that exact
directory list in 30 days (27% of all pytest invocations)**, plus 35 cases of
an identical pytest command repeated >= 8x within a single session, worst case
**34x**. The waste is re-running an unchanged tree, and a content hash detects
exactly that: the 34x case collapses to one run.

Why the key covers the WHOLE tracked tree, not a per-check subset
-----------------------------------------------------------------
This is a gate-skipping mechanism, so a false skip is silent and CI-only —
the same danger #2003 analyses for the watched-path lever. A per-check hash
set would have to be a permanent SUPERSET of everything the suite reads, and
for `chk_hook_units` that is already `.claude/`, `docs/`, `evals/`, `.husky/`,
`.github/`, `README.md`, `package.json`, `package-lock.json`,
`.claude-plugin/`, `ruff.toml`, `plugins/`, `scripts/`, `tests/` — open-ended
and growing with every content-guard. A forgotten path there is a false skip.

Hashing the entire tracked tree costs ~64ms against a ~90s suite, so the
subset buys nothing and risks correctness. Everything is hashed; any change
anywhere invalidates every cached entry. The superset problem does not arise
because there is no subset.

Safety posture — every failure path answers "not fresh"
------------------------------------------------------
`is-fresh` exits non-zero (run the suite) on: an unknown check, a missing or
unreadable cache, a cache written by a different repo root, a git failure, or
any unexpected exception. A gate that cannot fail is worse than no gate; a
cache that skips on error is that gate. The only exit-0 path is a recorded key
that byte-equals a freshly computed one.

`record` is called ONLY after a green run, so a red run never poisons the
cache into skipping.

Stdlib-only, Python 3.10+ floor. Not shipped with the plugin — this is
repo-root developer tooling (see CLAUDE.md's scope note for `scripts/*`).

Usage:
    python3 scripts/ci_tree_cache.py key
    python3 scripts/ci_tree_cache.py is-fresh chk_hook_units && echo skip
    python3 scripts/ci_tree_cache.py record chk_hook_units
    python3 scripts/ci_tree_cache.py clear
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

#: Checks that may consult the cache. Deliberately an allowlist: a check not
#: named here can never be skipped by this mechanism, mirroring the safe
#: default the --changed-only levers use for unmapped checks.
CACHEABLE_CHECKS = frozenset({"chk_hook_units"})

#: Cache version. Bump to invalidate every stored entry when the key
#: computation itself changes — otherwise a stale key from an older algorithm
#: could compare equal by coincidence of format.
CACHE_VERSION = 1

_GIT_TIMEOUT_S = 60


def cache_path() -> Path:
    """Per-user cache file, alongside the pinned-shellcheck download."""
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "agentic-dev-team" / "tree-cache.json"


def _git(args: list[str], repo_root: Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=True,
        timeout=_GIT_TIMEOUT_S,
    )
    return result.stdout


def repo_root() -> Path:
    return Path(
        _git(["rev-parse", "--show-toplevel"], Path.cwd()).strip()
    ).resolve()


def _tracked_and_untracked(root: Path) -> list[str]:
    """Every file git considers part of the working tree.

    Tracked files plus untracked-but-not-ignored ones — the latter matter
    because a brand-new test file that nobody has `git add`ed yet still
    changes what the suite collects. Ignored files are excluded: build output
    and caches are not inputs.
    """
    tracked = _git(["ls-files", "-z"], root).split("\0")
    untracked = _git(
        ["ls-files", "-z", "--others", "--exclude-standard"], root
    ).split("\0")
    return sorted({f for f in (*tracked, *untracked) if f})


def compute_key(root: Path) -> str:
    """A content hash over the whole working tree.

    Path, size, and bytes all feed the digest, with an explicit length prefix
    so two files cannot be confused by concatenation (a rename that shifts
    content across a boundary must change the key).
    """
    digest = hashlib.sha256()
    digest.update(f"v{CACHE_VERSION}\0".encode())
    for rel in _tracked_and_untracked(root):
        path = root / rel
        try:
            payload = path.read_bytes()
        except (OSError, ValueError):
            # A path git lists but we cannot read (a broken symlink, a race
            # with a concurrent write). Fold the failure into the key rather
            # than ignoring it, so the tree is never treated as equal to one
            # where the file read cleanly.
            digest.update(b"UNREADABLE\0")
            digest.update(rel.encode())
            continue
        digest.update(rel.encode())
        digest.update(b"\0")
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def _load_cache() -> dict:
    try:
        payload = json.loads(cache_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _entry_key(root: Path, check: str) -> str:
    """Namespace entries by repo root so sibling worktrees never share a
    verdict — two worktrees of this repo have different trees at the same
    check name."""
    return f"{root}::{check}"


def is_fresh(root: Path, check: str) -> bool:
    if check not in CACHEABLE_CHECKS:
        return False
    cache = _load_cache()
    if cache.get("version") != CACHE_VERSION:
        return False
    recorded = cache.get("entries", {})
    if not isinstance(recorded, dict):
        return False
    stored = recorded.get(_entry_key(root, check))
    if not isinstance(stored, str) or not stored:
        return False
    return stored == compute_key(root)


def record(root: Path, check: str) -> None:
    if check not in CACHEABLE_CHECKS:
        return
    cache = _load_cache()
    entries = cache.get("entries")
    if not isinstance(entries, dict) or cache.get("version") != CACHE_VERSION:
        entries = {}
    entries[_entry_key(root, check)] = compute_key(root)
    path = cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write-then-rename so a crash mid-write cannot leave a truncated cache
    # that later parses as a valid-but-wrong entry.
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps({"version": CACHE_VERSION, "entries": entries}, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ci_tree_cache.py",
        description=(
            "Skip a gate whose working tree is byte-identical to the one it "
            "last passed on."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("key", help="print the current tree key")
    fresh = sub.add_parser(
        "is-fresh", help="exit 0 iff <check> already passed on this exact tree"
    )
    fresh.add_argument("check")
    rec = sub.add_parser("record", help="record <check> as passing on this tree")
    rec.add_argument("check")
    sub.add_parser("clear", help="delete the cache")
    args = parser.parse_args(argv)

    # Every unexpected failure resolves to "not fresh" / no-op, never a skip.
    try:
        root = repo_root()
        if args.command == "key":
            print(compute_key(root))
            return 0
        if args.command == "is-fresh":
            return 0 if is_fresh(root, args.check) else 1
        if args.command == "record":
            record(root, args.check)
            return 0
        if args.command == "clear":
            cache_path().unlink(missing_ok=True)
            return 0
    except (subprocess.SubprocessError, OSError, ValueError) as exc:
        print(f"ci_tree_cache: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
