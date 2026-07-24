#!/usr/bin/env python3
"""Python port of hooks/js-fp-review.sh (#600 / #572 Phase 3).

PostToolUse advisory hook for Write/Edit on JS/TS files. Detects common
mutation patterns and warns without blocking. Full nuanced analysis is
handled by the js-fp-review agent — this is a fast pre-check that surfaces
the obvious cases inline.

Contract (docs/python-hook-contract.md):
    Input : PostToolUse JSON on stdin with tool_input.file_path
    Output: advisory feedback on stdout
    Exit  : 0 always (advisory)

Stdlib-only (json/pathlib/re/sys). Python 3.8+. See ADR 0014.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Suffixes that trigger the check.
_JS_TS_EXT = (".js", ".ts", ".jsx", ".tsx")

# The .sh's grep patterns, translated one-for-one so line numbers and
# match text are identical between the two implementations.
_ARRAY_MUTATION_RE = re.compile(
    r"\.(push|pop|shift|unshift|splice|reverse|sort|fill|copyWithin)\s*\("
)
# Pattern the .sh subsequently EXCLUDES: `[...].` before the mutation.
_ARRAY_MUTATION_EXCLUDE_RE = re.compile(r"\[\.\.\..*\]\.")

_GLOBAL_MUTATION_RE = re.compile(r"\b(window|global|globalThis)\.\w+\s*=[^=]")
_PROCESS_ENV_RE = re.compile(r"process\.env\.\w+\s*=[^=]")

_OBJECT_ASSIGN_RE = re.compile(r"Object\.assign\s*\(\s*[a-zA-Z_]\w*\s*,")
_OBJECT_ASSIGN_EXCLUDE_RE = re.compile(r"Object\.assign\s*\(\s*\{\}")

_PARAM_MUTATION_RE = re.compile(
    r"\b(param|params|options|opts|config|cfg|obj|data|input|args|req|res)"
    r"\.\w+\s*=[^=]"
)
_THIS_EXCLUDE_RE = re.compile(r"\bthis\.")

# Bash comment-skip: `grep -v '^\s*//'` — line whose first non-whitespace is `//`.
_COMMENT_LINE_RE = re.compile(r"^\s*//")


def _read_stdin() -> str:
    try:
        return sys.stdin.read()
    except (OSError, ValueError):
        return ""


def _load_input(raw: str) -> dict:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _extract_file_path(payload: dict) -> str:
    """`jq -r '.tool_input.file_path // .tool_input.path // .file_path // .path // empty'`."""
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict):
        for key in ("file_path", "path"):
            val = tool_input.get(key)
            if isinstance(val, str) and val:
                return val
    for key in ("file_path", "path"):
        val = payload.get(key)
        if isinstance(val, str) and val:
            return val
    return ""


def _matching_lines(
    text: str, include: re.Pattern, exclude_patterns: list[re.Pattern]
) -> list[str]:
    """Return `grep -n INCLUDE | grep -v EXCLUDE...`-formatted lines.

    Emulates `grep -n` exactly: 1-indexed line numbers separated by `:`,
    empty when nothing matches. The exclusions in the .sh pipeline run
    AFTER `grep -n` has prefixed the line with `N:`, which means the
    `^\\s*//` comment-line filter never matches (the prefix pushes the
    first character to a digit). Reproduce that behavior byte-for-byte:
    apply excludes (including the comment filter) to the prefixed string,
    not the raw line.
    """
    matches: list[str] = []
    for idx, line in enumerate(text.splitlines(), start=1):
        if not include.search(line):
            continue
        prefixed = f"{idx}:{line}"
        skip = False
        for pat in exclude_patterns:
            if pat.search(prefixed):
                skip = True
                break
        if skip:
            continue
        # The `^\s*//` comment filter is intentionally NOT applied here —
        # see the docstring. This matches the .sh's actual behavior.
        matches.append(prefixed)
    return matches


def _lines_from_matches(matches: list[str]) -> str:
    """Join with newlines; empty string when there are no matches."""
    if not matches:
        return ""
    return "\n".join(matches)


def _build_warnings(content: str) -> str:
    """Assemble the .sh's WARNINGS string byte-for-byte.

    Each detection contributes a heredoc-style block prefixed with a
    leading newline, matching the .sh's `WARNINGS="${WARNINGS}\\n..."`
    accumulator shape.
    """
    warnings = ""

    array_lines = _lines_from_matches(
        _matching_lines(
            content,
            _ARRAY_MUTATION_RE,
            [_ARRAY_MUTATION_EXCLUDE_RE],
        )
    )
    if array_lines:
        warnings += (
            "\nFP: Array mutation detected — consider immutable "
            "alternatives (spread, slice, toSorted, toReversed):\n"
            f"{array_lines}"
        )

    global_lines = _lines_from_matches(
        _matching_lines(
            content,
            _GLOBAL_MUTATION_RE,
            [],
        )
    )
    env_lines = _lines_from_matches(
        _matching_lines(
            content,
            _PROCESS_ENV_RE,
            [],
        )
    )
    if global_lines or env_lines:
        # The .sh concatenates the two captures back-to-back, exactly as
        # `${GLOBAL_MUTATIONS}${PROCESS_ENV}`.
        warnings += (
            "\nFP: Global state mutation detected — use module-level state "
            "or dependency injection:\n"
            f"{global_lines}{env_lines}"
        )

    assign_lines = _lines_from_matches(
        _matching_lines(
            content,
            _OBJECT_ASSIGN_RE,
            [_OBJECT_ASSIGN_EXCLUDE_RE],
        )
    )
    if assign_lines:
        warnings += (
            "\nFP: Object.assign mutates target in place — use spread or "
            "Object.assign({}, ...):\n"
            f"{assign_lines}"
        )

    param_lines = _lines_from_matches(
        _matching_lines(
            content,
            _PARAM_MUTATION_RE,
            [_THIS_EXCLUDE_RE],
        )
    )
    if param_lines:
        warnings += (
            "\nFP: Possible parameter mutation — create a new object with "
            "spread instead:\n"
            f"{param_lines}"
        )

    return warnings


def main() -> int:
    raw = _read_stdin()
    payload = _load_input(raw)
    file_path_str = _extract_file_path(payload)
    if not file_path_str:
        return 0
    if not file_path_str.endswith(_JS_TS_EXT):
        return 0
    file_path = Path(file_path_str)
    if not file_path.is_file():
        return 0
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0

    warnings = _build_warnings(content)
    if warnings:
        # The .sh's `echo "$WARNINGS"` collapses the leading `\n` in the
        # WARNINGS string to an empty first line then appends the block +
        # a trailing newline. Reproduce byte-for-byte.
        sys.stdout.write(warnings + "\n")

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
