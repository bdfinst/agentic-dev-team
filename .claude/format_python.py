#!/usr/bin/env python3
"""PostToolUse hook: autofix lint on Python files as they are edited.

Registered in `.claude/settings.json` for `Edit|Write|MultiEdit`. Runs the same
tool the blocking pre-push gate runs (`chk_ruff` in `scripts/ci-local.sh`), so a
file fixed here is a file that gate no longer has to reject.

Three deliberate constraints:

- **`ruff check --fix`, never `ruff format`.** `ruff.toml` at the repo root
  configures `ruff check` only and declares no `[format]` section, and no gate
  runs `ruff format`. Formatting here would restyle the tree in a way nothing
  else enforces.
- **`--force-exclude` is mandatory, not cosmetic.** Ruff honors its exclude
  list for *discovered* paths but lints an *explicitly passed* path regardless
  — and a hook always passes one explicitly. Without this flag the hook would
  autofix `**/fixtures`, `**/rule-fixtures`, and the other corpora `ruff.toml`
  excludes, which are intentionally non-conformant code the review agents and
  eval harness must see unmodified.
- **Fail-open, time-boxed.** A hook that breaks the edit loop is worse than no
  hook. Every failure path exits 0.

Stdlib only, matching the rest of `.claude/`.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

TIMEOUT_SECONDS = 15


def _edited_path(payload: dict) -> str:
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return ""
    return str(tool_input.get("file_path") or "")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if not isinstance(payload, dict):
        return 0

    raw = _edited_path(payload)
    if not raw or not raw.endswith(".py"):
        return 0

    target = Path(raw)
    if not target.is_file():
        return 0

    ruff = shutil.which("ruff")
    if ruff is None:
        return 0

    # Resolve the repo root from this hook's own location (.claude/ sits at the
    # root) rather than trusting the process cwd, so ruff always discovers
    # ruff.toml and applies its excludes and per-file target versions.
    repo_root = Path(__file__).resolve().parent.parent

    try:
        subprocess.run(
            [ruff, "check", "--fix", "--force-exclude", str(target)],
            cwd=repo_root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
