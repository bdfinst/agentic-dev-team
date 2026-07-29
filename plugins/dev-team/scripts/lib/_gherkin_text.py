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

Stdlib-only. Python 3.8+ (ADR 0014/0015).
"""

from __future__ import annotations

import re

FEATURE_PREFIX = "Feature:"
SCENARIO_OUTLINE_PREFIX = "Scenario Outline:"
SCENARIO_PREFIX = "Scenario:"

# Full C0 + C1 control-character range — stripped before printing untrusted
# scanned-file content (or a path derived from it) to a terminal. A
# `.feature` file's content (titles, and the path it was found at) comes
# from whatever repository is being scanned, and could otherwise inject
# terminal escape sequences (CWE-150), forge fake report lines via an
# embedded CR/LF, or masquerade as trusted tool output fed back into an
# agent's report. Titles are always single lines (parsed via `splitlines()`
# then `.strip()`), so stripping CR/LF/tab from title text is a no-op; a
# filesystem path has no such guarantee, so the full range — not just the
# subset that happened to matter for line-oriented title text — is needed
# now that this function also sanitizes paths.
CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f]")

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
