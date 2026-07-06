#!/usr/bin/env python3
"""refactor_test_bash_guard.py — PreToolUse hook (Bash), issue #906.

The preventive, Bash-aware half of the tests-frozen-during-refactor
invariant (#813). `refactor_test_freeze_guard.py` blocks Write/Edit at a
test file during a recorded REFACTOR phase, but Bash-driven edits (`sed -i`,
`tee`, shell redirection, `mv`/`cp` onto a target, `python -c` with an
`open(..., "w")`) bypass that guard entirely and were previously only
caught reactively, after the fact, by `refactor_test_revert_guard.py`
(PostToolUse) — which reverts/removes the damage once it has already
landed on disk.

This hook recognizes a conservative library of common file-modifying Bash
shapes (`hooks/refactor-bash-write-patterns.json`), extracts the apparent
write target, and — only when a recorded REFACTOR phase is active AND the
target resolves to a file in the step's `test_files_staged` (or would newly
create a file `test_file_classify.is_test_file()` classifies as a test) —
blocks with exit 2 before the command ever runs.

Ambiguous/unparseable commands (no pattern matches, or the matched target
cannot be confidently resolved) are NEVER blocked: the false-positive budget
favors letting the command through and relying on
`refactor_test_revert_guard.py` as the safety net (defense-in-depth, not a
replacement — see the issue's Non-goals). This is not a general-purpose
shell parser.

Fails OPEN on any internal error, with one audit line in
`metrics/refactor-freeze.jsonl` (hook="bash-freeze") — a broken guard must
never block work.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple

_SCRIPT_DIR = Path(__file__).resolve().parent
_LIB_DIR = _SCRIPT_DIR / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from stdin_json import read_stdin_json  # noqa: E402
from test_file_classify import is_test_file, read_build_phase  # noqa: E402
from boundary_events import emit_boundary_event as _emit_boundary_event  # noqa: E402
from refactor_test_freeze_guard import audit  # noqa: E402


def emit_boundary_event(*args, **kwargs) -> None:
    """Local safety net (#859): even a misbehaving helper must never affect
    this hook's exit code, stdout, or stderr."""
    try:
        _emit_boundary_event(*args, **kwargs)
    except Exception:  # noqa: BLE001 - fail-open by design
        pass


_PATTERNS_FILE = _SCRIPT_DIR / "refactor-bash-write-patterns.json"

RECOVERY = (
    "tests are frozen during REFACTOR; return to the TEST phase, make the "
    "change there, re-verify green, then re-enter REFACTOR"
)

# Inline fallback — kept in the same order as the shipped JSON so behavior
# is byte-identical when the config file is missing or malformed.
_DEFAULT_PATTERNS: List[Tuple[str, str]] = [
    (
        "sed-i",
        r"\bsed\s+-i(?:\.\S+)?\s+(?:-e\s+)?(?:'[^']*'|\"[^\"]*\")\s+(?P<target>[^\s;&|]+)",
    ),
    (
        "perl-i",
        r"\bperl\s+-i(?:\.\S+)?\s+(?:-[a-zA-Z]+\s+)*(?:'[^']*'|\"[^\"]*\")\s+(?P<target>[^\s;&|]+)",
    ),
    ("tee", r"\btee\s+(?:-a\s+)?(?P<target>[^\s;&|]+)"),
    ("redirect", r"(?<![\w&])>{1,2}(?!\S*&)\s*(?P<target>[^\s;&|>]+)"),
    (
        "mv-cp",
        r"\b(?:mv|cp)\s+(?:-\S+\s+)*(?P<src>[^\s;&|]+)\s+(?P<target>[^\s;&|]+)\s*(?:[;&|]|$)",
    ),
    (
        "python-open-write",
        r"open\(\s*['\"](?P<target>[^'\"]+)['\"]\s*,\s*['\"](?:w|a|wb|ab|w\+|a\+)['\"]",
    ),
]


def _load_patterns() -> List[Tuple[str, str]]:
    """Load (id, regex) pairs from the config file, falling back to inline
    defaults on any error — attempt-and-degrade, matches destructive_guard.py."""
    try:
        data = json.loads(_PATTERNS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return list(_DEFAULT_PATTERNS)
    if not isinstance(data, dict):
        return list(_DEFAULT_PATTERNS)
    raw = data.get("patterns")
    if not isinstance(raw, list):
        return list(_DEFAULT_PATTERNS)
    pairs: List[Tuple[str, str]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        rule_id = entry.get("id")
        regex = entry.get("regex")
        if isinstance(rule_id, str) and rule_id and isinstance(regex, str) and regex:
            pairs.append((rule_id, regex))
    return pairs if pairs else list(_DEFAULT_PATTERNS)


def _extract_target(
    command: str, patterns: List[Tuple[str, str]]
) -> Optional[Tuple[str, str]]:
    """Return (rule_id, raw_target) for the first pattern that matches, or
    None when the command is unparseable/ambiguous — never raises."""
    for rule_id, regex in patterns:
        try:
            match = re.search(regex, command)
        except re.error:
            continue
        if match is None:
            continue
        target = match.groupdict().get("target")
        if target:
            return rule_id, target
    return None


def _normalize_target(target: str) -> str:
    """Strip a matching pair of quotes and a leading './' — best-effort only."""
    stripped = target.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in ("'", '"'):
        stripped = stripped[1:-1]
    if stripped.startswith("./"):
        stripped = stripped[2:]
    return stripped


def _resolve_relative(target: str, project_dir: Path) -> str:
    """Best-effort project-relative posix path for `target`. Falls back to
    the normalized target string when it can't be resolved under
    `project_dir` (e.g. an absolute path outside the project)."""
    normalized = _normalize_target(target)
    candidate = Path(normalized)
    if candidate.is_absolute():
        try:
            return candidate.resolve().relative_to(project_dir.resolve()).as_posix()
        except (OSError, ValueError):
            return normalized
    return normalized


def _matches_staged_or_new_test(rel_target: str, staged: List[str]) -> bool:
    if rel_target in staged:
        return True
    return is_test_file(rel_target)


def evaluate(
    command: str, project_dir: Path, now: Optional[float] = None
) -> Tuple[int, List[str], Optional[str]]:
    """Return (exit_code, stdout_lines, matched_rule_id).

    `matched_rule_id` is the pattern id that triggered a block, or None
    (including for every non-blocking outcome).
    """
    if not command:
        return 0, [], None
    state, error = read_build_phase(project_dir, now=now)
    if error is not None:
        audit(project_dir, "bash-freeze", "fail-open", reason=error)
        return 0, [], None
    if state is None or state.get("phase") != "refactor":
        return 0, [], None

    match = _extract_target(command, _load_patterns())
    if match is None:
        return 0, [], None
    rule_id, raw_target = match

    staged = state.get("test_files_staged", [])
    rel_target = _resolve_relative(raw_target, project_dir)
    if not _matches_staged_or_new_test(rel_target, staged):
        return 0, [], None

    step = state.get("step") if isinstance(state.get("step"), str) else None
    audit(project_dir, "bash-freeze", "block", file=rel_target, step=step)
    step_label = " (step {})".format(step) if step else ""
    return (
        2,
        [
            "[BLOCK] Tests are frozen during REFACTOR{}.".format(step_label),
            "A refactor step must never change a test — refactoring is",
            "behavior-preserving by definition (tests-frozen invariant, Rec 4,",
            "docs/experiments/RECOMMENDATIONS.md).",
            "File: {}".format(rel_target),
            "Recovery: leave REFACTOR and return to the TEST phase, make the",
            "test change there, re-verify the full suite green (pasted",
            "evidence), then re-enter REFACTOR.",
        ],
        rule_id,
    )


def main() -> int:
    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    exit_code, lines = 0, []
    try:
        payload = read_stdin_json()
        tool_input = payload.get("tool_input") if isinstance(payload, dict) else None
        command = ""
        if isinstance(tool_input, dict):
            raw = tool_input.get("command")
            if isinstance(raw, str):
                command = raw
        exit_code, lines, rule_id = evaluate(command, project_dir)
        if exit_code == 2:
            session_id = payload.get("session_id") if isinstance(payload, dict) else None
            emit_boundary_event(
                project_dir,
                "refactor_test_bash_guard",
                "Bash",
                "block",
                rule_id or "bash-write",
                session_id,
            )
    except Exception as exc:  # fail open — a broken guard never blocks work
        audit(
            project_dir,
            "bash-freeze",
            "fail-open",
            reason="internal error: {}".format(exc),
        )
        return 0
    for line in lines:
        print(line)
    return exit_code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
