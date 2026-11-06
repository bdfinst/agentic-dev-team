"""String-literal scanners for the C-family languages: JS/TS, C#, and Java.

One lexer class serves all three. A language is a ``Lang`` value that turns on
the literal forms it has:

- JS/TS: ``'..'`` and ``".."`` (one line), template literals with ``${}``
  (multi-line), regex literals (skipped, so a quote inside one is not a string)
- C#: ``".."``, verbatim ``@".."``, interpolated ``$".."`` (always counted as
  interpolated), raw strings (a run of three or more quotes), and
  ``'c'`` char literals
- Java: ``".."``, text blocks (three quotes), and ``'c'`` char literals

Comments (``//`` and ``/* */``) are skipped. A one-line string that reaches a
newline unterminated is dropped and scanning resumes on the next line, so one
stray quote (an apostrophe in JSX text) cannot swallow the rest of the file.

Stdlib-only. Python 3.10+.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass

from sql_literals import Literal


@dataclass(frozen=True)
class Lang:
    templates: bool = False  # JS: `..${}..`
    regex: bool = False  # JS: /../ literals
    csharp: bool = False  # @"..", $"..", raw """..."""
    text_blocks: bool = False  # Java: """..."""
    char_literals: bool = False  # 'c' (JS uses ' for strings instead)


JS = Lang(templates=True, regex=True)
CSHARP = Lang(csharp=True, char_literals=True)
JAVA = Lang(text_blocks=True, char_literals=True)

_REGEX_AFTER = set("(,=:[!&|?{};")


class _Lexer:
    def __init__(self, text: str, lang: Lang) -> None:
        self.text = text
        self.lang = lang
        self.n = len(text)
        self.i = 0
        self.out: list[Literal] = []
        self.prev = ""  # the last two significant characters
        self.pending: Literal | None = None  # literal waiting for a following "+"
        self.newlines = [k for k, ch in enumerate(text) if ch == "\n"]

    def line(self, pos: int) -> int:
        return bisect_left(self.newlines, pos) + 1

    def sig(self, ch: str) -> None:
        if self.pending is not None:
            if ch == "+":
                self.pending.concatenated = True
            self.pending = None
        self.prev = (self.prev + ch)[-2:]

    def emit(self, start: int, end: int, interpolated: bool = False) -> None:
        concatenated = self.prev in ("+", "+=") or self.prev.endswith("+")
        lit = Literal(
            self.text[start:end], self.line(start), interpolated, concatenated
        )
        self.out.append(lit)
        self.sig('"')
        self.pending = lit

    # -- primitives ---------------------------------------------------------

    def comment_end(self, i: int) -> int | None:
        """Index after the comment that starts at ``i``, or None."""
        t = self.text
        if t.startswith("//", i):
            end = t.find("\n", i)
            return self.n if end < 0 else end
        if t.startswith("/*", i):
            end = t.find("*/", i + 2)
            return self.n if end < 0 else end + 2
        return None

    def line_string(self, i: int, quote: str) -> int | None:
        """End index of the closing quote of a one-line string body at ``i``."""
        t = self.text
        while i < self.n:
            ch = t[i]
            if ch == "\\":
                i += 2
            elif ch == quote:
                return i
            elif ch == "\n":
                return None
            else:
                i += 1
        return None

    def block_string(self, i: int, quote: str) -> int | None:
        """Index of the next unescaped run of three quotes at or after ``i``."""
        t, closer = self.text, quote * 3
        while i < self.n:
            if t[i] == "\\":
                i += 2
            elif t.startswith(closer, i):
                return i
            else:
                i += 1
        return None

    # -- JS -----------------------------------------------------------------

    def skip_expression(self, i: int) -> int:
        """Index after the ``}`` that closes a template ``${`` opened before ``i``."""
        t, depth = self.text, 1
        while i < self.n:
            ch = t[i]
            if ch in "'\"":
                end = self.line_string(i + 1, ch)
                i = i + 1 if end is None else end + 1
            elif ch == "`":
                i = self.template_end(i + 1)[0]
            elif self.comment_end(i) is not None:
                i = self.comment_end(i)
            else:
                depth += (ch == "{") - (ch == "}")
                i += 1
                if depth == 0:
                    return i
        return self.n

    def template_end(self, i: int) -> tuple[int, int | None, bool]:
        """(index after the closing backtick, body end or None, interpolated)."""
        t, interpolated = self.text, False
        while i < self.n:
            ch = t[i]
            if ch == "\\":
                i += 2
            elif ch == "`":
                return i + 1, i, interpolated
            elif ch == "$" and t.startswith("${", i):
                interpolated = True
                i = self.skip_expression(i + 2)
            else:
                i += 1
        return self.n, None, interpolated

    def regex_literal(self) -> bool:
        """Skip a regex literal at ``i`` when the context allows one."""
        if self.prev and self.prev[-1] not in _REGEX_AFTER:
            return False
        t, i, in_class = self.text, self.i + 1, False
        while i < self.n and t[i] != "\n":
            ch = t[i]
            if ch == "\\":
                i += 1
            elif ch == "[":
                in_class = True
            elif ch == "]":
                in_class = False
            elif ch == "/" and not in_class:
                self.sig("/")
                self.i = i + 1
                return True
            i += 1
        return False

    # -- C# -----------------------------------------------------------------

    def csharp_string(self) -> bool:
        """Scan a C# string starting at ``i`` (prefix ``$`` and ``@`` allowed)."""
        t, j = self.text, self.i
        dollars = verbatim = 0
        while j < self.n and t[j] in "$@" and dollars + verbatim < 3:
            dollars += t[j] == "$"
            verbatim += t[j] == "@"
            j += 1
        if j >= self.n or t[j] != '"':
            return False
        quotes = 1
        while t.startswith('"' * (quotes + 1), j):
            quotes += 1
        body = j + (quotes if quotes >= 3 and not verbatim else 1)
        if verbatim:
            end = self.verbatim_end(body)
        elif quotes >= 3:
            end = t.find('"' * quotes, body)
            end = None if end < 0 else end
        elif quotes == 2:
            self.emit(j + 2, j + 2, bool(dollars))
            self.i = j + 2
            return True
        else:
            end = self.line_string(body, '"')
        if end is None:
            self.i = self.skip_line(body)
            return True
        self.emit(body, end, bool(dollars))
        self.i = end + (quotes if quotes >= 3 and not verbatim else 1)
        return True

    def verbatim_end(self, i: int) -> int | None:
        t = self.text
        while i < self.n:
            if t.startswith('""', i):
                i += 2
            elif t[i] == '"':
                return i
            else:
                i += 1
        return None

    def skip_line(self, i: int) -> int:
        end = self.text.find("\n", i)
        return self.n if end < 0 else end

    # -- driver -------------------------------------------------------------

    def string_at_cursor(self) -> bool:
        """Scan the quoted form at ``i``. False when none starts here."""
        i, ch, lang = self.i, self.text[self.i], self.lang
        if lang.csharp and ch in '$@"':
            return self.csharp_string()
        if lang.templates and ch == "`":
            after, end, interpolated = self.template_end(i + 1)
            if end is not None:
                self.emit(i + 1, end, interpolated)
            self.i = after
            return True
        if ch == '"' and lang.text_blocks and self.text.startswith('"""', i):
            end = self.block_string(i + 3, '"')
            if end is None:
                self.i = self.n
            else:
                self.emit(i + 3, end)
                self.i = end + 3
            return True
        if ch == '"' or (ch == "'" and not lang.char_literals):
            end = self.line_string(i + 1, ch)
            if end is None:
                self.i = self.skip_line(i + 1)
            else:
                self.emit(i + 1, end)
                self.i = end + 1
            return True
        if ch == "'":  # a char literal never holds SQL; consume it so '"' is safe
            end = self.line_string(i + 1, "'")
            self.i = self.skip_line(i + 1) if end is None else end + 1
            self.sig("'")
            return True
        return False

    def regex_or_string(self) -> bool:
        if self.text[self.i] == "/":
            return self.lang.regex and self.regex_literal()
        return self.string_at_cursor()

    def run(self) -> list[Literal]:
        t = self.text
        while self.i < self.n:
            ch = t[self.i]
            if ch.isspace():
                self.i += 1
            elif ch == "/" and self.comment_end(self.i) is not None:
                self.i = self.comment_end(self.i)
            elif self.regex_or_string():
                pass
            else:
                self.sig(ch)
                self.i += 1
        return self.out


def scan(text: str, lang: Lang) -> list[Literal]:
    """Literals of ``text`` for one language. Never raises."""
    return _Lexer(text, lang).run()


def js_literals(text: str) -> list[Literal]:
    return scan(text, JS)


def csharp_literals(text: str) -> list[Literal]:
    return scan(text, CSHARP)


def java_literals(text: str) -> list[Literal]:
    return scan(text, JAVA)
