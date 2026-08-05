"""hooks/lib/gh_pr_create_detect.py — detect a `gh pr create` invocation
(#1886).

`hooks/pre_pr_review.py`'s trigger-point detector: a single quote-aware
tokenizing pass over each shell-separator-delimited segment of the raw Bash
command, looking for `gh pr create` as the segment's real command words
(after skipping any leading `NAME=value` environment-variable prefixes and
resolving a path-qualified `gh` — e.g. `/usr/local/bin/gh` — by basename).

This is deliberately a MUCH lighter heuristic than
`hooks/lib/pre_commit_detect.py`'s `is_git_commit_command` — that module
went through five adversarial hardening rounds (`<shell> -c` unwrapping,
command substitution, I/O redirection before the command word, `-C`/global
option chaining, ...) specifically for `git commit`'s much larger and more
security-sensitive command-shape surface (a missed detection there let a
commit land with no review corroboration at all). `gh pr create` has a much
narrower realistic invocation shape in practice, and the trigger point this
module guards is a human/agent-driven "open a PR" action, not a background
`git commit` that fires many times per session — so the cost/benefit of
matching that same adversarial-hardening investment here is different.

KNOWN RESIDUAL GAP, disclosed rather than silently accepted (mirrors this
repo's own convention for `pre_commit_detect.py`'s own disclosed gaps): this
detector does NOT unwrap `<shell> -c '...'`, command substitution
(`$(...)`/backticks), `eval`/`xargs`, I/O redirection before the command
word, or a `gh` alias/wrapper script — any of those can still reach `gh pr
create` undetected. A future round of adversarial review (correctness-review
/ security-review) should extend this the same way #1801 extended
`pre_commit_detect.py`, if this trigger point proves to need it in practice.

Stdlib-only. See ADR 0014 / ADR 0015.
"""

from __future__ import annotations

import re
import shlex

# Bare shell separators — `;`, `&&`, `||`, `|`, and a bare newline — split one
# Bash payload into independently-evaluated segments. Quote-aware: a
# separator character INSIDE a quoted string is never a boundary.
_SEPARATOR_RE = re.compile(r"(;|&&|\|\||\||\n)")

_ENV_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def _split_on_separators(command: str) -> list[str]:
    """Quote-aware split on `;`/`&&`/`||`/`|`/`&`/newline — a separator
    INSIDE a single- or double-quoted string is never treated as a
    boundary.

    Two fixes (issue #1904 Bug 3 — this is the SOLE trigger point for the
    entire review gate now that `pre_commit_review.py` is a no-op, so a
    missed detection here is a complete, silent bypass):

    1. Bare `&` (background) is a real shell separator — `true &
       gh pr create --title x` used to stay one segment (with `true` as
       `tokens[0]`), missing the `gh pr create` entirely. `&&` is checked
       BEFORE bare `&` in the tuple below, so `&&` still matches as the
       two-character operator it is; only a genuinely bare `&` falls
       through to the new single-character case.
    2. The backslash-escape exemption on a closing quote now applies ONLY
       when the open quote is `"` (double quote). POSIX single quotes have
       NO escape mechanism at all — `echo 'a\'` closes the quote at that
       `'` in real bash regardless of the preceding backslash, so treating
       it as still-open (the old, quote-character-agnostic check) let a
       genuinely-closed single-quoted region swallow the rest of the
       command, including a `;`-separated `gh pr create` that followed.
    """
    segments: list[str] = []
    current: list[str] = []
    quote: str | None = None
    i = 0
    while i < len(command):
        ch = command[i]
        if quote is not None:
            current.append(ch)
            if ch == quote and (
                quote == "'" or i == 0 or command[i - 1] != "\\"
            ):
                quote = None
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            current.append(ch)
            i += 1
            continue
        matched = None
        for sep in ("&&", "||", ";", "|", "\n", "&"):
            if command.startswith(sep, i):
                matched = sep
                break
        if matched is not None:
            segments.append("".join(current))
            current = []
            i += len(matched)
            continue
        current.append(ch)
        i += 1
    segments.append("".join(current))
    return segments


def _real_command_tokens(segment: str) -> list[str] | None:
    """Tokenize one segment and skip leading `NAME=value` env-assignment
    prefixes, returning the remaining tokens (the command and its
    arguments), or `None` if the segment doesn't tokenize (unbalanced
    quoting)."""
    try:
        tokens = shlex.split(segment, posix=True)
    except ValueError:
        return None
    i = 0
    while i < len(tokens) and _ENV_ASSIGNMENT_RE.match(tokens[i]):
        i += 1
    return tokens[i:]


def is_gh_pr_create_command(command: str) -> bool:
    """True if any shell-separator-delimited segment of `command` invokes
    `gh pr create` (a path-qualified `gh`, e.g. `/usr/local/bin/gh`, is
    recognized by basename)."""
    for segment in _split_on_separators(command):
        tokens = _real_command_tokens(segment)
        if not tokens:
            continue
        gh_token = tokens[0].replace("\\", "/").rsplit("/", 1)[-1]
        if gh_token != "gh":
            continue
        if len(tokens) >= 3 and tokens[1] == "pr" and tokens[2] == "create":
            return True
    return False


__all__ = ("is_gh_pr_create_command",)
