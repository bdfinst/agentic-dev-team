"""stub_extractors.csharp — C# `[Given(`/`[When(`/`[Then(` attribute step
bindings, method body bounded by lexically-aware brace balance (including
C# verbatim `@"..."` string patterns, handled by the shared lexer). Thin
wrapper around `_common.parse_annotation_style`, the control flow it shares
byte-for-byte with Java's annotation-style bindings (`java.py`).
"""

from __future__ import annotations

import re

from ._common import ParseResult, parse_annotation_style

_LANGUAGE = "C#"
_ATTRIBUTE_RE = re.compile(r"\[(?:Given|When|Then)\s*\(")


def parse(text: str, markers: tuple) -> ParseResult:
    return parse_annotation_style(text, markers, _LANGUAGE, _ATTRIBUTE_RE)
