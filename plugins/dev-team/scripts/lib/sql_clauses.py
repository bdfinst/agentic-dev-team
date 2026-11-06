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


# Words that begin a statement. T-SQL needs no ``;``, so a segment can hold
# several statements back to back.
STATEMENT_WORDS = frozenset(
    {
        "SELECT",
        "INSERT",
        "UPDATE",
        "DELETE",
        "MERGE",
        "WITH",
        "EXEC",
        "EXECUTE",
        "DECLARE",
        "TRUNCATE",
        "CREATE",
        "DROP",
        "ALTER",
        "BEGIN",
        "COMMIT",
        "ROLLBACK",
        "IF",
        "WHILE",
        "PRINT",
        "RETURN",
    }
)
# A write keyword after one of these belongs to a clause, not to a statement:
# ON DELETE CASCADE, DO UPDATE SET, FOR UPDATE, AFTER INSERT, THEN DELETE.
NOT_A_STATEMENT_AFTER = frozenset(
    {
        "ON",
        "FOR",
        "DO",
        "THEN",
        "OR",
        "AFTER",
        "BEFORE",
        "OF",
        "KEY",
        "GRANT",
        "REVOKE",
        "DENY",
        "INSTEAD",
    }
)


def is_statement_start(
    tokens: Sequence[Token], items: list[int], position: int
) -> bool:
    """True when ``items[position]`` begins a new statement in the segment."""
    name = word(tokens[items[position]])
    if name not in STATEMENT_WORDS:
        return False
    following = tokens[items[position + 1]] if position + 1 < len(items) else None
    if name == "SELECT":
        return True
    if name in ("INSERT", "UPDATE", "DELETE", "MERGE"):
        if position > 0:
            previous = tokens[items[position - 1]]
            if is_punct(previous, ",") or word(previous) in NOT_A_STATEMENT_AFTER:
                return False
        return following is not None and not is_punct(following, "(")
    if name == "WITH":
        # WITH x AS (...) and WITH RECURSIVE start a CTE; WITH (NOLOCK),
        # WITH CHECK OPTION, and WITH NO DATA are clauses.
        if following is None or is_punct(following, "("):
            return False
        if word(following) == "RECURSIVE":
            return True
        after = tokens[items[position + 2]] if position + 2 < len(items) else None
        return after is not None and (word(after) == "AS" or is_punct(after, "("))
    if name == "IF":
        return following is not None and not is_punct(following, "(")
    return True


def render(tokens: Sequence[Token]) -> str:
    """Matched tokens as one line of SQL-like text."""
    text = " ".join(t.text for t in tokens)
    text = text.replace(" . ", ".")
    text = re.sub(r"\( ", "(", text)
    text = re.sub(r" ([,)])", r"\1", text)
    return text
