"""Dialect-neutral SQL tokenizer for the SQL anti-pattern detector.

This module is frozen after the first SQL-detector slice (#2283): every rule
family builds on it, so a change here moves all of them. Extend rules, not
the lexer.

``tokenize(text)`` returns every token, comments included, so a caller can
read suppression markers and still skip comments when it matches code. The
lexer never raises and never loops: any input, including unterminated
strings, comments, and quoted identifiers, yields a token list that covers
the text.

Token kinds:

- ``word``: bare identifier or keyword (``INSERT``, ``orders``, ``@var``)
- ``number``: numeric literal or ``$1``-style positional parameter
- ``string``: ``'...'`` with ``''`` escapes, or a Postgres dollar-quoted body
- ``quoted``: ``"..."``, backtick, or ``[...]`` identifier
- ``comment``: ``-- ...`` line comment or ``/* ... */`` block comment
- ``punct``: any other single character, such as ``(``, ``,``, ``;``, ``.``

Rules:

- Block comments nest, as in PostgreSQL and T-SQL. An unterminated comment
  runs to the end of the text.
- An unterminated string or quoted identifier runs to the end of the text
  and has ``terminated=False``.
- A ``[`` opens a bracket identifier only when a ``]`` follows on the same
  line. Otherwise it is punctuation, so ``a[1]`` and stray brackets cannot
  swallow the rest of the file.
- ``line`` and ``col`` are 1-based and mark the first character of the token.
  A newline is ``\\n``. ``\\r`` is ordinary whitespace.

Stdlib-only. Python 3.10+.
"""

from __future__ import annotations

from dataclasses import dataclass

WORD = "word"
NUMBER = "number"
STRING = "string"
QUOTED = "quoted"
COMMENT = "comment"
PUNCT = "punct"


@dataclass(frozen=True)
class Token:
    kind: str
    text: str
    line: int
    col: int
    terminated: bool = True


_WORD_START = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_#@")
_WORD_PART = _WORD_START | frozenset("0123456789$")
_DIGITS = frozenset("0123456789")
_TAG_START = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_")


def _is_word_start(ch: str) -> bool:
    return ch in _WORD_START or ord(ch) > 127


def _is_word_part(ch: str) -> bool:
    return ch in _WORD_PART or ord(ch) > 127


def _scan_quoted(text: str, start: int, close: str) -> tuple[int, bool]:
    """End index and terminated flag for a ``close``-delimited run.

    A doubled ``close`` character is an escape and stays inside the run.
    """
    i = start + 1
    n = len(text)
    while i < n:
        if text[i] == close:
            if i + 1 < n and text[i + 1] == close:
                i += 2
                continue
            return i + 1, True
        i += 1
    return n, False


def _scan_block_comment(text: str, start: int) -> tuple[int, bool]:
    depth = 1
    i = start + 2
    n = len(text)
    while i < n:
        two = text[i : i + 2]
        if two == "/*":
            depth += 1
            i += 2
        elif two == "*/":
            depth -= 1
            i += 2
            if depth == 0:
                return i, True
        else:
            i += 1
    return n, False


def _scan_dollar_quote(text: str, start: int) -> tuple[int, bool] | None:
    """End of a ``$tag$ ... $tag$`` body, or None when ``$`` is not one."""
    n = len(text)
    i = start + 1
    if i < n and text[i] in _TAG_START:
        i += 1
        while i < n and (text[i] in _TAG_START or text[i] in _DIGITS):
            i += 1
    if i >= n or text[i] != "$":
        return None
    delimiter = text[start : i + 1]
    end = text.find(delimiter, i + 1)
    if end == -1:
        return n, False
    return end + len(delimiter), True


def _scan_bracket(text: str, start: int) -> tuple[int, bool] | None:
    """End of a ``[name]`` identifier, or None when it is plain punctuation."""
    newline = text.find("\n", start)
    limit = len(text) if newline == -1 else newline
    i = start + 1
    while i < limit:
        if text[i] == "]":
            if i + 1 < limit and text[i + 1] == "]":
                i += 2
                continue
            return i + 1, True
        i += 1
    return None


def _scan_number(text: str, start: int) -> int:
    n = len(text)
    i = start
    while i < n and (text[i] in _DIGITS or text[i] == "."):
        i += 1
    if i < n and text[i] in "eE":
        j = i + 1
        if j < n and text[j] in "+-":
            j += 1
        if j < n and text[j] in _DIGITS:
            while j < n and text[j] in _DIGITS:
                j += 1
            i = j
    return i


def _classify(text: str, i: int) -> tuple[str, int, bool]:
    """Kind, end index, and terminated flag for the token starting at ``i``."""
    n = len(text)
    ch = text[i]
    nxt = text[i + 1] if i + 1 < n else ""
    if ch == "-" and nxt == "-":
        end = text.find("\n", i)
        return COMMENT, n if end == -1 else end, True
    if ch == "/" and nxt == "*":
        end, closed = _scan_block_comment(text, i)
        return COMMENT, end, closed
    if ch == "'":
        end, closed = _scan_quoted(text, i, "'")
        return STRING, end, closed
    if ch in '"`':
        end, closed = _scan_quoted(text, i, ch)
        return QUOTED, end, closed
    if ch == "[":
        bracket = _scan_bracket(text, i)
        if bracket is not None:
            return QUOTED, bracket[0], bracket[1]
    if ch == "$":
        if nxt in _DIGITS and nxt:
            j = i + 1
            while j < n and text[j] in _DIGITS:
                j += 1
            return NUMBER, j, True
        dollar = _scan_dollar_quote(text, i)
        if dollar is not None:
            return STRING, dollar[0], dollar[1]
    if ch in _DIGITS or (ch == "." and nxt in _DIGITS and nxt):
        return NUMBER, _scan_number(text, i), True
    if _is_word_start(ch):
        j = i + 1
        while j < n and _is_word_part(text[j]):
            j += 1
        return WORD, j, True
    return PUNCT, i + 1, True


def tokenize(text: str) -> list[Token]:
    """Split ``text`` into tokens. Whitespace is skipped, never emitted."""
    tokens: list[Token] = []
    n = len(text)
    i = 0
    line = 1
    line_start = 0
    while i < n:
        ch = text[i]
        if ch == "\n":
            line += 1
            line_start = i + 1
            i += 1
            continue
        if ch.isspace():
            i += 1
            continue
        kind, end, closed = _classify(text, i)
        tokens.append(Token(kind, text[i:end], line, i - line_start + 1, closed))
        newlines = text.count("\n", i, end)
        if newlines:
            line += newlines
            line_start = text.rfind("\n", i, end) + 1
        i = end
    return tokens
