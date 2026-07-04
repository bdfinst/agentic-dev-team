"""Unit tests for hooks/lib/stdin_json.py — shared stdin-JSON-read helper (#732).

Extracted from the identical `_read_stdin_json()` copy-pasted across 7 hooks
(pre_commit_review.py, pre_commit_knowledge_index.py, knowledge_index.py,
mutation_testing_smoke_gate.py, codegraph_nudge.py, codegraph_bootstrap.py,
bash_retry_guard.py). Behavior: read stdin, parse JSON, return the dict on
success — None on empty input, malformed JSON, a non-dict JSON value
(e.g. a list or scalar), or an OSError while reading.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

_HOOKS_LIB = Path(__file__).resolve().parents[2] / "hooks" / "lib"
if str(_HOOKS_LIB) not in sys.path:
    sys.path.insert(0, str(_HOOKS_LIB))

import stdin_json  # type: ignore[import-not-found]  # noqa: E402


def _set_stdin(monkeypatch, text: str) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(text))


def test_valid_json_object_returns_dict(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _set_stdin(monkeypatch, '{"tool_name": "Edit", "cwd": "/tmp"}')
    assert stdin_json.read_stdin_json() == {"tool_name": "Edit", "cwd": "/tmp"}


def test_empty_stdin_returns_none(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _set_stdin(monkeypatch, "")
    assert stdin_json.read_stdin_json() is None


def test_whitespace_only_stdin_returns_none(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _set_stdin(monkeypatch, "   \n\t")
    assert stdin_json.read_stdin_json() is None


def test_malformed_json_returns_none(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _set_stdin(monkeypatch, "{not valid json")
    assert stdin_json.read_stdin_json() is None


def test_non_dict_json_array_returns_none(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _set_stdin(monkeypatch, "[1, 2, 3]")
    assert stdin_json.read_stdin_json() is None


def test_non_dict_json_scalar_returns_none(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _set_stdin(monkeypatch, "42")
    assert stdin_json.read_stdin_json() is None


def test_stdin_read_oserror_returns_none(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    class _BoomStdin:
        def read(self) -> str:
            raise OSError("broken pipe")

    monkeypatch.setattr(sys, "stdin", _BoomStdin())
    assert stdin_json.read_stdin_json() is None
