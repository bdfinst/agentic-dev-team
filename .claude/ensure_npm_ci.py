#!/usr/bin/env python3
"""SessionStart hook (registered in .claude/settings.json): self-heal a
checkout (most commonly a freshly created git worktree) that never ran
`npm ci`, so husky's git hooks aren't silently inert.

Why this matters: core.hooksPath=.husky/_ is set once in the shared
.git/config and is inherited by every worktree automatically — but
.husky/_ itself (the shim git actually invokes) is gitignored and
generated locally by npm ci's `prepare` script. A worktree missing it has
every git hook (pre-commit, pre-push) silently no-op with no error, which
is easy to miss (see CLAUDE.md "Worktrees — run npm ci first").

Fail-open and time-boxed — never blocks session start. Stdlib-only.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

_TIMEOUT_SECONDS = 180


def _emit(message: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": message,
                }
            }
        )
    )


def main() -> int:
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).parent.parent)

    # Only meaningful in this repo's own checkout(s).
    if not (root / "package.json").is_file():
        return 0

    # Already provisioned: nothing to do.
    if (root / "node_modules" / ".bin" / "husky").is_file():
        return 0

    npm = shutil.which("npm")
    if npm is None:
        return 0

    log_path = Path.home() / ".cache" / "npm-ci-sessionstart.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with log_path.open("w", encoding="utf-8") as log_file:
            result = subprocess.run(
                [npm, "ci"],
                cwd=root,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                timeout=_TIMEOUT_SECONDS,
                check=False,
            )
        ok = result.returncode == 0
    except subprocess.TimeoutExpired:
        ok = False

    if ok:
        _emit(
            "This checkout had no node_modules/husky — ran npm ci to provision "
            "it, so pre-commit/pre-push git hooks are no longer silently inert."
        )
    else:
        _emit(
            "This checkout is missing node_modules and an automatic npm ci "
            f"failed or timed out — pre-commit/pre-push hooks stay silently "
            f"inert until you run npm ci by hand. See {log_path}."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
