#!/usr/bin/env python3
"""pre_commit_knowledge_index — Claude Code PreToolUse:Bash hook (Python port).

Python port of hooks/pre-commit-knowledge-index.sh (#582 / #572 Cluster A+B).

Blocks `git commit` when the working-tree knowledge/index.json does not
match what a fresh build of the working tree would produce. The
PostToolUse hook (knowledge_index.py) keeps the working-tree index
current on every Edit, so this gate's only purpose is to catch the
`git add corpus.md` without `git add knowledge/index.json` case.

Sibling to hooks/pre_commit_review.py — both share the git-commit
detection helper (pre_commit_detect) and the corpus-path helper
(knowledge_index_paths). The two hooks have independent concerns
(review-pass vs index-freshness); the sibling pattern keeps each file
single-purpose.

Contract (docs/python-hook-contract.md):
    Input : PreToolUse:Bash JSON on stdin
    Exit 0: allow (non-commit, --no-verify bypass, no corpus staged, or fresh)
    Exit 2: block with the two-line remediation message

Env seams (TEST-ONLY):
    KNOWLEDGE_INDEX_BUILDER  override the builder path

Stdlib-only. Python 3.8+.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional


_HOOK_DIR = Path(__file__).resolve().parent
_LIB_DIR = _HOOK_DIR / "lib"

sys.path.insert(0, str(_LIB_DIR))
try:
    from knowledge_index_paths import is_corpus_path  # type: ignore[import-not-found]
    from pre_commit_detect import is_git_commit_invocation  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover
    # Fail-open on missing shared libs.
    def is_corpus_path(_: str) -> bool:  # type: ignore[misc]
        return False

    def is_git_commit_invocation(_: str) -> bool:  # type: ignore[misc]
        return False


_REMEDIATION = """knowledge/index.json is stale; the auto-rebuild ran but you must stage the result.

  1. bash plugins/dev-team/hooks/lib/build-knowledge-index.sh
  2. git add plugins/dev-team/knowledge/index.json

Diff (expected vs working tree):
"""


def _read_stdin_json() -> Optional[dict]:
    try:
        raw = sys.stdin.read()
    except OSError:
        return None
    if not raw.strip():
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _staged_files() -> List[str]:
    try:
        completed = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            capture_output=True,
            check=False,
            text=True,
        )
    except (FileNotFoundError, OSError):
        return []
    if completed.returncode != 0:
        return []
    return [line for line in completed.stdout.splitlines() if line]


def main() -> int:
    payload = _read_stdin_json()
    if payload is None:
        return 0

    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return 0
    command = str(tool_input.get("command") or "")

    if not is_git_commit_invocation(command):
        return 0

    staged = _staged_files()
    corpus_staged = [p for p in staged if is_corpus_path(p)]
    if not corpus_staged:
        return 0

    builder = os.environ.get(
        "KNOWLEDGE_INDEX_BUILDER",
        str(_LIB_DIR / "build-knowledge-index.sh"),
    )
    try:
        completed = subprocess.run(
            ["bash", builder, "--check"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=False,
        )
    except (FileNotFoundError, OSError):
        # Fail-open — we cannot enforce the gate without a builder.
        return 0

    if completed.returncode == 0:
        return 0

    stderr_text = (completed.stderr or b"").decode("utf-8", errors="replace")
    sys.stderr.write(_REMEDIATION)
    sys.stderr.write(stderr_text)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # Fail-open on any unexpected error — the gate must never crash a commit.
        sys.exit(0)
