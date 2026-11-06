"""String-literal scanning for the embedded-SQL extractors.

Every language scanner returns ``Literal`` objects in source order. A literal
holds the text between the quotes, never a comment, and the file line where
that text starts. ``concatenated`` is set when a ``+`` (or ``+=``) joins the
literal to another expression, and ``interpolated`` when the literal embeds a
value (an f-string field, a template ``${}``, a C# ``$""``).

``python_literals`` uses the stdlib ``tokenize`` module, so comments and
prefixes are exact. The scanners for JS/TS, C#, and Java live in
``sql_literals_c``.

Every scanner is total: unterminated quotes or broken syntax end the scan
early and never raise.

Stdlib-only. Python 3.10+.
"""

from __future__ import annotations

import io
import re
import tokenize
from collections.abc import Iterator
from dataclasses import dataclass
from itertools import accumulate

_TRIPLE = ('"""', "'''")
_FIELD_RE = re.compile(r"\{")


@dataclass
class Literal:
    text: str
    line: int
    interpolated: bool = False
    concatenated: bool = False


def has_python_field(body: str) -> bool:
    """True when an f-string body holds a replacement field (not ``{{``)."""
    return bool(_FIELD_RE.search(body.replace("{{", "").replace("}}", "")))


def _tokens(text: str) -> Iterator[tokenize.TokenInfo]:
    """Tokens of ``text``; broken syntax ends the stream instead of raising."""
    try:
        yield from tokenize.generate_tokens(io.StringIO(text).readline)
    except (tokenize.TokenError, SyntaxError, ValueError):
        return


def _split_string(token: str) -> tuple[str, str]:
    """Prefix and body of a ``STRING`` token."""
    prefix = re.match(r"[A-Za-z]*", token).group()
    rest = token[len(prefix) :]
    quote = 3 if rest[:3] in _TRIPLE else 1
    return prefix, rest[quote:-quote] if len(rest) >= 2 * quote else ""


def python_literals(text: str) -> list[Literal]:
    """Literals of a Python source text, with concatenation flags set."""
    starts = [0, *accumulate(len(ln) + 1 for ln in text.split("\n"))]

    def offset(pos: tuple[int, int]) -> int:
        return starts[pos[0] - 1] + pos[1]

    fstart = getattr(tokenize, "FSTRING_START", None)
    fend = getattr(tokenize, "FSTRING_END", None)
    toks = list(_tokens(text))
    items: list[Literal | str] = []  # Literal, an operator, "n:<name>", or ""
    i = 0
    while i < len(toks):
        tok = toks[i]
        i += 1
        if tok.type in (tokenize.NL, tokenize.COMMENT):
            continue
        if tok.type == tokenize.STRING:
            prefix, body = _split_string(tok.string)
            interpolated = "f" in prefix.lower() and has_python_field(body)
            items.append(Literal(body, tok.start[0], interpolated))
        elif fstart is not None and tok.type == fstart:
            depth, j = 1, i
            while j < len(toks) and depth:
                depth += (toks[j].type == fstart) - (toks[j].type == fend)
                j += 1
            closing = toks[j - 1]
            ok = depth == 0 and closing.type == fend
            body = text[offset(tok.end) : offset(closing.start)] if ok else ""
            interpolated = any(
                t.type != tokenize.FSTRING_MIDDLE for t in toks[i : j - 1]
            )
            items.append(Literal(body, tok.start[0], interpolated))
            i = j
        elif tok.type == tokenize.OP:
            items.append(tok.string)
        elif tok.type == tokenize.NAME:
            items.append("n:" + tok.string)
        else:
            items.append("")
    _flag_concatenation(items)
    return [it for it in items if isinstance(it, Literal)]


def _flag_concatenation(items: list[Literal | str]) -> None:
    for k, item in enumerate(items):
        if not isinstance(item, Literal):
            continue
        before = items[k - 1] if k else ""
        after = items[k + 1] if k + 1 < len(items) else ""
        after2 = items[k + 2] if k + 2 < len(items) else ""
        if (
            isinstance(before, Literal)
            or isinstance(after, Literal)
            or before in ("+", "+=")
            or after in ("+", "%")
            or (after == "." and after2 == "n:format")
        ):
            item.concatenated = True
