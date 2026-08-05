"""Unit tests for tests/lib/jsonl.py (#1889)."""

from __future__ import annotations

import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parent
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

import jsonl  # type: ignore[import-not-found]


def test_read_jsonl_parses_each_line(tmp_path: Path) -> None:
    path = tmp_path / "log.jsonl"
    path.write_text('{"a": 1}\n{"a": 2}\n', encoding="utf-8")
    assert jsonl.read_jsonl(path) == [{"a": 1}, {"a": 2}]


def test_read_jsonl_skips_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "log.jsonl"
    path.write_text('{"a": 1}\n\n{"a": 2}\n', encoding="utf-8")
    assert jsonl.read_jsonl(path) == [{"a": 1}, {"a": 2}]


def test_read_jsonl_empty_file_is_empty_list(tmp_path: Path) -> None:
    path = tmp_path / "log.jsonl"
    path.write_text("", encoding="utf-8")
    assert jsonl.read_jsonl(path) == []
