"""_gherkin_text.py — line-level Gherkin text primitives shared across the
`.feature`-file *parsers* (`gherkin_feature_merge.py`, `gherkin_failure_path_gate.py`,
`gherkin_cross_feature_duplicate_titles_gate.py`), plus a general
untrusted-text/path terminal-safety helper also used by `gherkin_stub_gate.py`
(a step-definition scanner — it never parses `.feature` files, and imports only
`safe_for_terminal`, none of the Gherkin block-parsing primitives below).

Hoisted out after `_stripped()` and the `Feature:`/`Scenario:`/`Scenario
Outline:` prefix constants were found duplicated byte-for-byte between the two
`.feature`-file parsers (issue #1420 code-review follow-up) — the same "third
occurrence" threshold `_vendored_tree.py` was extracted at. `is_tag_line`/
`safe_for_terminal` and `trim_trailing_tag_run` joined later (issue #1526) at
that same third-occurrence point — the latter closes the trailing `@tag`/
blank-line look-back loop that was independently duplicated in all three
`.feature`-file parsers (`gherkin_feature_merge.py`'s `_block_end`, and the two
gate scripts' own block-scanning loops).

Stdlib-only. (ADR 0014/0015).
"""

from __future__ import annotations

import re

FEATURE_PREFIX = "Feature:"
SCENARIO_OUTLINE_PREFIX = "Scenario Outline:"
SCENARIO_PREFIX = "Scenario:"

# Full C0 + C1 control-character range, plus Unicode line/paragraph
# separators and bidirectional-control characters — stripped before printing
# untrusted scanned-file content (or a path derived from it) to a terminal.
# A `.feature` file's content (titles, and the path it was found at) comes
# from whatever repository is being scanned, and could otherwise:
#   - inject terminal escape sequences (CWE-150) via the C0/C1 range;
#   - forge a fake extra report line via an embedded CR/LF (C0), or via
#     U+2028/U+2029, which several terminals still render as a hard line
#     break even though they're outside the ASCII control range;
#   - visually spoof a printed path/title (Trojan-Source-style) via a
#     bidirectional-override character (U+202A-U+202E) or isolate
#     (U+2066-U+2069), reordering how the surrounding text renders.
# Titles are always single lines (parsed via `splitlines()` then `.strip()`),
# so stripping any of these from title text is a no-op; a filesystem path
# has no such guarantee, so the full range is needed now that this function
# also sanitizes paths. `repr()`-based print sites (e.g.
# `gherkin_feature_merge.py`'s check-stale branch) don't need this guard —
# Python's `repr()` already escapes every character struck here.
CONTROL_CHARS = re.compile("[\x00-\x1f\x7f-\x9f\u2028\u2029\u202a-\u202e\u2066-\u2069]")

TERMINAL_DISPLAY_LIMIT = 200


def stripped(line: str) -> str:
    """Strip only the line ending, preserving all other whitespace — so a
    caller reconstructing text from `splitlines(keepends=True)` output stays
    byte-exact for everything except the ending itself."""
    return line.rstrip("\r\n")


def safe_for_terminal(text: str, limit: int = TERMINAL_DISPLAY_LIMIT) -> str:
    """Strip control characters and bound length before printing untrusted
    scanned-file text (or a path derived from it) to a terminal — the
    `--json` path is unaffected, `json.dumps` already escapes control
    characters. Apply this to every piece of untrusted text reaching a
    terminal print, including file paths: a filename is drawn from the same
    untrusted repository as titles and can legally contain control bytes on
    POSIX filesystems."""
    return CONTROL_CHARS.sub("", text)[:limit]


def is_tag_line(line: str) -> bool:
    """True when `line` is a Gherkin `@tag` line (every token starts with
    `@`) — used to walk a Feature block's trailing tag/blank-line run back
    onto the *next* block it actually belongs to, not this one."""
    text = stripped(line).strip()
    if not text:
        return False
    return all(tok.startswith("@") for tok in text.split())


def trim_trailing_tag_run(lines: list, header_index: int, end_index: int) -> int:
    """Back `end_index` up past a trailing `@tag`/blank-line run so it lands
    on the true end of the Feature block starting at `header_index` —
    Gherkin tags attach to the declaration that *follows* them, so a
    `@tag` (or blank line) immediately preceding the next Feature: header
    belongs to that next block, not this one. Without this, a tag on the
    following Feature block would leak into this block's body."""
    while end_index > header_index + 1:
        prev = lines[end_index - 1]
        if stripped(prev).strip() == "" or is_tag_line(prev):
            end_index -= 1
        else:
            break
    return end_index
