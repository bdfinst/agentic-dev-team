#!/usr/bin/env python3
"""PostToolUse hook: autofix lint on JS/TS files as they are edited.

The JS/TS sibling of `format_python.py`. Registered in `.claude/settings.json`
for `Edit|Write|MultiEdit`, it runs the same tool `lint-staged` runs on commit
(`eslint --fix` over `*.{js,jsx,mjs,cjs,ts,tsx}`), so a file fixed here is a
file the pre-commit hook no longer has to fix.

Three deliberate constraints, mirroring the Python hook:

- **Repo-local eslint, never a global one.** ESLint is a devDependency pinned
  in `package.json`; a globally-installed copy would resolve different rules.
  The hook uses `node_modules/.bin/eslint` and does nothing when it is absent
  (e.g. an unprovisioned worktree that has not run `npm ci` yet).
- **Fixture corpora are excluded explicitly, not left to ESLint.** `eslint.config.mjs`
  lints only the *clean* eval fixtures — those whose `expected/*.json` declares
  `pass` for every applicable agent — because the dirty ones are intentionally
  flawed review-agent inputs. That exclusion is expressed as flat-config
  `files`/`ignores`, and flat-config resolution is not a reliable guard for an
  *explicitly passed* path: dirty `.js` fixtures under `evals/fixtures/` are
  matched by a config today and merely happen to carry no fixable violations.
  Relying on that would mean one future auto-fixable rule violation silently
  rewrites an eval input. `DENY_SEGMENTS` below is the actual guard.
- **Fail-open, time-boxed.** A hook that breaks the edit loop is worse than no
  hook. Every failure path exits 0.

Stdlib only, matching the rest of `.claude/`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

TIMEOUT_SECONDS = 30

EXTENSIONS = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx")

# Path segments that must never be autofixed. Fixture corpora are deliberately
# non-conformant code the review agents and eval harness must see unmodified;
# the rest is dependency or generated output.
DENY_SEGMENTS = (
    "node_modules/",
    "/fixtures/",
    "/rule-fixtures/",
    "/build/",
    "/dist/",
    "/coverage/",
    ".claude/worktrees/",
    "graphify-out/",
)


def _edited_path(payload: dict) -> str:
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return ""
    return str(tool_input.get("file_path") or "")


def _is_denied(path: Path, repo_root: Path) -> bool:
    """True when the path sits in a corpus this hook must not rewrite.

    Compared against the POSIX form of the repo-relative path with a leading
    slash, so a segment pattern like ``/fixtures/`` matches a directory
    component at any depth, including the first.
    """
    try:
        rel = path.resolve().relative_to(repo_root)
    except ValueError:
        return True  # outside the repo — not ours to touch
    probe = "/" + rel.as_posix()
    return any(seg in probe for seg in DENY_SEGMENTS)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if not isinstance(payload, dict):
        return 0

    raw = _edited_path(payload)
    if not raw or not raw.endswith(EXTENSIONS):
        return 0

    target = Path(raw)
    if not target.is_file():
        return 0

    # Resolve the repo root from this hook's own location (.claude/ sits at the
    # root) rather than trusting the process cwd, so eslint always discovers
    # eslint.config.mjs and the repo-local binary.
    repo_root = Path(__file__).resolve().parent.parent

    if _is_denied(target, repo_root):
        return 0

    eslint = repo_root / "node_modules" / ".bin" / "eslint"
    if not eslint.is_file():
        return 0

    try:
        subprocess.run(
            [str(eslint), "--fix", "--no-warn-ignored", str(target)],
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
