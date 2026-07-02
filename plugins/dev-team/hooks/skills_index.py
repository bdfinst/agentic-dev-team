#!/usr/bin/env python3
"""skills_index.py — Claude Code PostToolUse hook (Python port of skills-index.sh).

When an Edit or Write touches `plugins/dev-team/skills/<name>/SKILL.md`,
regenerate `plugins/dev-team/docs/skills.md` by shelling out to the
skills-index builder. The catalog is derived from each SKILL.md's `name` /
`description` frontmatter so editing a skill keeps the catalog current with
no manual step — a CI freshness gate (`--check`) is the strict net behind it.

Sibling of `knowledge_index.py` (rebuilds `knowledge/index.json`); kept
separate so each index has its own trigger, builder, and test seam.

Posture: fail-open. Any internal error (missing builder, malformed stdin,
builder non-zero exit) → exit 0 with a single `[skills-index]`-tagged stderr
line. The hook MUST never block an Edit.

Feedback: `[skills-index] rebuilt` on success, `[skills-index] rebuild
failed: <reason>` on failure. Silent when the touched file is not a SKILL.md.

Input : JSON on stdin (PostToolUse contract: `tool_name`,
        `tool_input.file_path`).
Output: stderr feedback when a SKILL.md is touched; otherwise silent. Exit 0.

Env (TEST-ONLY injection seams):
  SKILLS_INDEX_BUILDER — override the builder path. Production callers MUST
                         NOT set this; it is resolved from the hook's own
                         location.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


_SKILL_PATH_RE = re.compile(r"/?plugins/dev-team/skills/[^/]+/SKILL\.md$")


def _default_builder() -> Path:
    hook_dir = Path(__file__).resolve().parent
    return hook_dir / "lib" / "build-skills-index.sh"


def _resolve_builder() -> Path:
    override = os.environ.get("SKILLS_INDEX_BUILDER")
    return Path(override) if override else _default_builder()


def _touches_skill_definition(file_path: str) -> bool:
    return bool(file_path) and bool(_SKILL_PATH_RE.search(file_path))


def _extract_fields(raw: str):
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return None, None
    if not isinstance(payload, dict):
        return None, None
    tool_name = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path") or ""
    return (
        tool_name if isinstance(tool_name, str) else "",
        file_path if isinstance(file_path, str) else "",
    )


def main() -> int:
    raw = sys.stdin.read()
    tool_name, file_path = _extract_fields(raw)
    if tool_name is None:
        return 0  # malformed stdin — silent per fail-open

    if tool_name not in {"Edit", "Write"}:
        return 0

    if not _touches_skill_definition(file_path):
        return 0

    builder = _resolve_builder()

    with tempfile.NamedTemporaryFile("w+", delete=False) as stderr_capture:
        stderr_path = stderr_capture.name
    try:
        try:
            with open(stderr_path, "w") as stderr_sink:
                completed = subprocess.run(
                    ["bash", str(builder)],
                    stdout=subprocess.DEVNULL,
                    stderr=stderr_sink,
                    check=False,
                )
        except (FileNotFoundError, OSError) as exc:
            print(f"[skills-index] rebuild failed: {exc}", file=sys.stderr)
            return 0

        if completed.returncode == 0:
            print("[skills-index] rebuilt", file=sys.stderr)
        else:
            try:
                with open(stderr_path) as fh:
                    first_line = fh.readline().rstrip("\n") or "unknown"
            except OSError:
                first_line = "unknown"
            print(f"[skills-index] rebuild failed: {first_line}", file=sys.stderr)
    finally:
        try:
            os.unlink(stderr_path)
        except OSError:
            pass

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
