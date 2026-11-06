"""Clause helpers shared by the SQL rule families.

The tokenizer is flat, so a rule that must tell the outer ``WHERE`` from the
``WHERE`` of a subquery needs the paren structure. ``segments`` gives it: each
segment holds the token indexes of one statement at one paren depth, with
every nested ``( ... )`` group left out. A subquery or a function call is its
own segment, so a keyword in a segment belongs to that statement and no
other.

This is not a rule file: ``discover_rules`` imports only ``sql_rules_*.py``.

Stdlib-only. Python 3.10+.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from sql_tokenize import PUNCT, WORD, Token

SET_OPERATORS = frozenset({"UNION", "INTERSECT", "EXCEPT", "MINUS"})


def word(token: Token) -> str:
    """Upper-cased text of a bare word, else an empty string."""
    return token.text.upper() if token.kind == WORD else ""


def is_punct(token: Token, text: str) -> bool:
    return token.kind == PUNCT and token.text == text


def matching_parens(tokens: Sequence[Token]) -> dict[int, int]:
    """Map the index of each ``(`` to the index of its ``)``."""
    pairs: dict[int, int] = {}
    stack: list[int] = []
    for i, token in enumerate(tokens):
        if is_punct(token, "("):
            stack.append(i)
        elif is_punct(token, ")") and stack:
            pairs[stack.pop()] = i
    return pairs


def segments(tokens: Sequence[Token]) -> list[list[int]]:
    """Token indexes per statement per depth. ``;`` ends a segment.

    A nested group contributes its ``(`` and ``)`` to the parent segment and
    its own contents to a segment of its own.
    """
    out: list[list[int]] = []
    stack: list[list[int]] = [[]]

    def flush(items: list[int]) -> None:
        piece: list[int] = []
        for index in items:
            if is_punct(tokens[index], ";"):
                if piece:
                    out.append(piece)
                piece = []
            else:
                piece.append(index)
        if piece:
            out.append(piece)

    for i, token in enumerate(tokens):
        if is_punct(token, "("):
            stack[-1].append(i)
            stack.append([])
        elif is_punct(token, ")") and len(stack) > 1:
            flush(stack.pop())
            stack[-1].append(i)
        else:
            stack[-1].append(i)
    while stack:
        flush(stack.pop())
    return out


def set_operator_blocks(tokens: Sequence[Token], items: list[int]) -> list[list[int]]:
    """Split a segment at ``UNION``, ``INTERSECT``, ``EXCEPT``, and ``MINUS``."""
    blocks: list[list[int]] = [[]]
    for index in items:
        if word(tokens[index]) in SET_OPERATORS:
            blocks.append([])
        else:
            blocks[-1].append(index)
    return [block for block in blocks if block]


def render(tokens: Sequence[Token]) -> str:
    """Matched tokens as one line of SQL-like text."""
    text = " ".join(t.text for t in tokens)
    text = text.replace(" . ", ".")
    text = re.sub(r"\( ", "(", text)
    text = re.sub(r" ([,)])", r"\1", text)
    return text
