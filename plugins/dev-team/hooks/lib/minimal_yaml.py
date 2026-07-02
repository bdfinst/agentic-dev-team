#!/usr/bin/env python3
"""minimal_yaml.py — stdlib-only parser for the small YAML subset this plugin
actually consumes (ADR 0014 / ADR 0015: no third-party imports in shipped
`plugins/dev-team/` code).

Three shipped scripts used to `import yaml` (PyYAML, a third-party package)
to read two shapes of content:

1. SKILL.md **frontmatter** blocks — flat `key: value` pairs, occasional
   folded block scalars (`key: >-` followed by indented prose), booleans,
   and simple block sequences (`- item`).
2. Small **config YAML** files (skill_categories.yaml, scorecard.yaml,
   security-review-rule-map.yaml) — nested block mappings/sequences, inline
   flow collections (`{ mvp: true }`, `[".py", ".js"]`, including ones that
   wrap across two physical lines), quoted and bare scalars, ints/floats/
   bools.

Neither shape needs anchors, tags, multi-document streams, complex keys, or
any of the sharper edges of full YAML. This module implements just the
subset above with a small recursive-descent, indentation-based parser —
no third-party dependency, so a plain `python3` install (exactly what the
ADRs promise is sufficient) can run every shipped script that reads YAML.

Public API:
    parse_yaml(text) -> dict | list | scalar | None
    extract_frontmatter_block(text) -> str   (raises FrontmatterError)
    YamlError                                 (raised on unsupported/invalid input)
    FrontmatterError                          (raised when --- markers are missing)
"""

from __future__ import annotations

import re
from typing import Any, List, Optional, Tuple

_BLOCK_SCALAR_INDICATORS = (">-", ">+", ">", "|-", "|+", "|")
_INT_RE = re.compile(r"^-?\d+$")
_FLOAT_RE = re.compile(r"^-?\d+\.\d+([eE][+-]?\d+)?$|^-?\d+[eE][+-]?\d+$")


class YamlError(ValueError):
    """Input is outside the supported minimal-YAML subset, or malformed."""


class FrontmatterError(ValueError):
    """A document is missing a well-formed `---`-delimited frontmatter block."""


def extract_frontmatter_block(text: str) -> str:
    """Return the raw text between the first pair of `---` markers.

    Raises FrontmatterError if the document doesn't start with `---` or the
    block is unterminated.
    """
    if not text.startswith("---"):
        raise FrontmatterError("no `---` frontmatter block")
    end = text.find("\n---", 3)
    if end == -1:
        raise FrontmatterError("unterminated frontmatter block")
    return text[3:end]


def parse_yaml(text: str) -> Any:
    """Parse a minimal YAML subset. See module docstring for the supported shape."""
    lines = text.splitlines()
    value, _ = _parse_node(lines, 0, 0)
    return value


# ---------------------------------------------------------------------------
# Comment stripping / quote-aware scanning helpers
# ---------------------------------------------------------------------------


def _strip_comment(line: str) -> str:
    """Remove a trailing `# ...` comment (quote-aware, requires the `#` be at
    start-of-line or preceded by whitespace, matching YAML's own rule)."""
    in_single = in_double = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            if i == 0 or line[i - 1] in (" ", "\t"):
                return line[:i]
    return line


def _bracket_delta(s: str) -> int:
    """Net change in flow-collection nesting depth contributed by `s`,
    ignoring bracket characters inside quotes."""
    depth = 0
    in_single = in_double = False
    for ch in s:
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif not in_single and not in_double:
            if ch in "[{":
                depth += 1
            elif ch in "]}":
                depth -= 1
    return depth


def _split_key_value(content: str) -> Optional[Tuple[str, str]]:
    """Split a `key: value` (or `key:`) line at the first unquoted colon that
    is followed by whitespace or end-of-string. Returns None if `content`
    isn't a mapping-key line at all."""
    in_single = in_double = False
    for i, ch in enumerate(content):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == ":" and not in_single and not in_double:
            if i + 1 == len(content) or content[i + 1] in (" ", "\t"):
                return content[:i].strip(), content[i + 1 :].strip()
    return None


def _parse_key(key: str) -> str:
    key = key.strip()
    if len(key) >= 2 and key[0] in "\"'" and key[-1] == key[0]:
        return _parse_quoted(key)
    return key


# ---------------------------------------------------------------------------
# Scalars (bare, quoted, flow collections)
# ---------------------------------------------------------------------------


def _parse_quoted(text: str) -> str:
    quote = text[0]
    if len(text) < 2 or text[-1] != quote:
        raise YamlError(f"unterminated quoted scalar: {text!r}")
    body = text[1:-1]
    if quote == '"':
        return (
            body.replace('\\"', '"')
            .replace("\\n", "\n")
            .replace("\\t", "\t")
            .replace("\\\\", "\\")
        )
    return body.replace("''", "'")


def _split_top_level(s: str, sep: str) -> List[str]:
    """Split `s` on `sep` only at flow-collection depth 0 and outside quotes."""
    parts: List[str] = []
    depth = 0
    in_single = in_double = False
    start = 0
    for i, ch in enumerate(s):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif not in_single and not in_double:
            if ch in "[{":
                depth += 1
            elif ch in "]}":
                depth -= 1
            elif ch == sep and depth == 0:
                parts.append(s[start:i])
                start = i + 1
    parts.append(s[start:])
    return parts


def _parse_flow(text: str) -> Any:
    if text.startswith("["):
        if not text.endswith("]"):
            raise YamlError(f"unterminated flow sequence: {text!r}")
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(p.strip()) for p in _split_top_level(inner, ",")]
    if text.startswith("{"):
        if not text.endswith("}"):
            raise YamlError(f"unterminated flow mapping: {text!r}")
        inner = text[1:-1].strip()
        if not inner:
            return {}
        result = {}
        for part in _split_top_level(inner, ","):
            kv = _split_key_value(part.strip())
            if kv is None:
                raise YamlError(f"malformed flow-mapping entry: {part!r}")
            k, v = kv
            result[_parse_key(k)] = _parse_scalar(v)
        return result
    raise YamlError(f"not a flow collection: {text!r}")


def _parse_scalar(text: str) -> Any:
    text = text.strip()
    if text == "":
        return None
    if text[0] in "\"'":
        return _parse_quoted(text)
    if text[0] in "[{":
        return _parse_flow(text)
    if text in ("true", "True", "TRUE"):
        return True
    if text in ("false", "False", "FALSE"):
        return False
    if text in ("null", "Null", "NULL", "~"):
        return None
    if _INT_RE.match(text):
        return int(text)
    if _FLOAT_RE.match(text):
        return float(text)
    if ": " in text or text.endswith(":"):
        # A plain (unquoted) scalar containing ": " is ambiguous with a nested
        # mapping key in real YAML and is rejected there too — almost always
        # an unescaped colon in prose (fix: quote it or use a `>-` block
        # scalar), not something to silently accept as a string.
        raise YamlError(
            f"unquoted scalar contains ': ' (quote it or use '>-'): {text!r}"
        )
    return text


# ---------------------------------------------------------------------------
# Line reader: comment-stripped, multi-line-flow-merged "structural" lines
# ---------------------------------------------------------------------------


def _next_line(lines: List[str], i: int) -> Optional[Tuple[int, str, int]]:
    """Return (indent, content, next_i) for the next non-blank structural
    line at or after index i, merging continuation lines of an unbalanced
    flow collection. Returns None at end of input."""
    n = len(lines)
    while i < n:
        stripped = _strip_comment(lines[i]).rstrip()
        if stripped.strip() == "":
            i += 1
            continue
        indent = len(stripped) - len(stripped.lstrip(" "))
        content = stripped.strip()
        depth = _bracket_delta(content)
        j = i + 1
        while depth > 0 and j < n:
            piece_raw = _strip_comment(lines[j]).rstrip()
            piece = piece_raw.strip()
            if piece == "":
                j += 1
                continue
            content += " " + piece
            depth += _bracket_delta(piece)
            j += 1
        return indent, content, j
    return None


# ---------------------------------------------------------------------------
# Block scalars (`>-`, `|`, ...)
# ---------------------------------------------------------------------------


def _read_block_scalar(
    lines: List[str], i: int, parent_indent: int, indicator: str
) -> Tuple[str, int]:
    style = indicator[0]
    n = len(lines)
    body: List[str] = []
    content_indent: Optional[int] = None
    while i < n:
        raw = lines[i]
        if raw.strip() == "":
            if content_indent is None:
                i += 1
                continue
            body.append("")
            i += 1
            continue
        cur_indent = len(raw) - len(raw.lstrip(" "))
        if cur_indent <= parent_indent:
            break
        if content_indent is None:
            content_indent = cur_indent
        elif cur_indent < content_indent:
            break
        body.append(raw[content_indent:].rstrip())
        i += 1
    while body and body[-1] == "":
        body.pop()
    if style == ">":
        text = " ".join(body)
    else:
        text = "\n".join(body)
    return text, i


# ---------------------------------------------------------------------------
# Recursive descent: mappings / sequences
# ---------------------------------------------------------------------------


def _consume_value(
    lines: List[str], i: int, indent: int, val_text: str
) -> Tuple[Any, int]:
    """Resolve the value portion of a `key: val_text` (or `- val_text`)
    entry, consuming further block-scalar or nested-block lines as needed."""
    if val_text == "":
        nxt = _next_line(lines, i)
        if nxt is not None and nxt[0] > indent:
            return _parse_node(lines, i, nxt[0])
        return None, i
    if val_text in _BLOCK_SCALAR_INDICATORS:
        return _read_block_scalar(lines, i, indent, val_text)
    return _parse_scalar(val_text), i


def _parse_node(lines: List[str], i: int, indent: int) -> Tuple[Any, int]:
    nxt = _next_line(lines, i)
    if nxt is None:
        return None, i
    li, content, _j = nxt
    if li != indent:
        return None, i
    if content == "-" or content.startswith("- "):
        return _parse_sequence(lines, i, indent)
    return _parse_mapping(lines, i, indent)


def _parse_mapping(lines: List[str], i: int, indent: int) -> Tuple[dict, int]:
    result: dict = {}
    while True:
        nxt = _next_line(lines, i)
        if nxt is None:
            break
        li, content, j = nxt
        if li < indent:
            break
        if li > indent:
            raise YamlError(f"unexpected indentation before: {content!r}")
        kv = _split_key_value(content)
        if kv is None:
            raise YamlError(f"expected 'key: value' mapping entry, got: {content!r}")
        key, val = kv
        i = j
        value, i = _consume_value(lines, i, indent, val)
        result[_parse_key(key)] = value
    return result, i


def _parse_sequence(lines: List[str], i: int, indent: int) -> Tuple[list, int]:
    result: list = []
    while True:
        nxt = _next_line(lines, i)
        if nxt is None:
            break
        li, content, j = nxt
        if li < indent:
            break
        if li > indent:
            raise YamlError(f"unexpected indentation in sequence before: {content!r}")
        if not (content == "-" or content.startswith("- ")):
            break
        i = j
        remainder = "" if content == "-" else content[2:]
        if remainder == "":
            nxt2 = _next_line(lines, i)
            if nxt2 is not None and nxt2[0] > indent:
                child, i = _parse_node(lines, i, nxt2[0])
                result.append(child)
            else:
                result.append(None)
            continue
        kv = _split_key_value(remainder)
        if kv is None:
            result.append(_parse_scalar(remainder))
            continue
        # "- key: value" — an inline mapping starts at the column right
        # after "- "; further keys of the same mapping are indented to
        # align there.
        after_dash = content[1:]
        leading_spaces = len(after_dash) - len(after_dash.lstrip(" "))
        content_col = indent + 1 + leading_spaces
        key, val = kv
        value, i = _consume_value(lines, i, content_col, val)
        item = {_parse_key(key): value}
        while True:
            nxt2 = _next_line(lines, i)
            if nxt2 is None:
                break
            li2, content2, j2 = nxt2
            if li2 != content_col:
                break
            kv2 = _split_key_value(content2)
            if kv2 is None:
                break
            key2, val2 = kv2
            i = j2
            value2, i = _consume_value(lines, i, content_col, val2)
            item[_parse_key(key2)] = value2
        result.append(item)
    return result, i
