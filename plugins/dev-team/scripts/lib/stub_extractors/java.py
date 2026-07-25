"""stub_extractors.java — Java `@Given(`/`@When(`/`@Then(` annotation step
bindings, method body bounded by lexically-aware brace balance. Thin
wrapper around `_common.parse_annotation_style`, the control flow it shares
byte-for-byte with C#'s attribute-style bindings (`csharp.py`).
"""

from __future__ import annotations

import re

from ._common import ParseResult, parse_annotation_style

_LANGUAGE = "Java"
_ANNOTATION_RE = re.compile(r"@(?:Given|When|Then)\s*\(")


def parse(text: str, markers: tuple) -> ParseResult:
    return parse_annotation_style(text, markers, _LANGUAGE, _ANNOTATION_RE)
