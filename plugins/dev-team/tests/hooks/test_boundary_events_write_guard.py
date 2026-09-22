"""Unit tests for hooks/boundary_events_write_guard.py (#2171, plan Step
1.1 — Write/Edit path-match guard only; Bash write-shaped command detection
and settings.json registration are Step 1.2, not covered here).

In-process, stdin-monkeypatched, with `emit_boundary_event` stubbed (same
split `test_destructive_guard.py` uses) — real subprocess + real-ledger
end-to-end coverage lives in `tests/hooks/test_boundary_events_write_guard.py`.
"""

from __future__ import annotations

import json
import sys

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_PLUGIN_DIR = _REPO_ROOT / "plugins" / "dev-team"

for _p in (_PLUGIN_DIR / "hooks",):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import boundary_events_write_guard as guard


@pytest.fixture(autouse=True)
def _no_boundary_events(monkeypatch):
    """Unit-level tests call `main()`/`targets_ledger()` in-process — stub
    the emit so no real ledger write happens as a side effect of testing
    the guard itself. `tests/hooks/test_boundary_events_write_guard.py`
    exercises the real subprocess + real emit path (matches
    pre_tool_guard.py's own test split)."""
    monkeypatch.setattr(guard, "emit_boundary_event", lambda *a, **k: None)


# ---------------------------------------------------------------------------
# _extract_file_path
# ---------------------------------------------------------------------------


def test_extract_file_path_prefers_file_path():
    assert guard._extract_file_path({"file_path": "a.py", "path": "b.py"}) == "a.py"


def test_extract_file_path_falls_back_to_path():
    assert guard._extract_file_path({"path": "b.py"}) == "b.py"


def test_extract_file_path_empty_when_neither():
    assert guard._extract_file_path({}) == ""


def test_extract_file_path_empty_when_not_a_dict():
    assert guard._extract_file_path("a.py") == ""


# ---------------------------------------------------------------------------
# targets_ledger — path-form matrix (relative, absolute, "./"-prefixed)
# ---------------------------------------------------------------------------


def test_targets_ledger_relative_path(tmp_path):
    assert guard.targets_ledger(
        ".claude/metrics/boundary-events.jsonl", str(tmp_path)
    )


def test_targets_ledger_dot_slash_prefixed_path(tmp_path):
    assert guard.targets_ledger(
        "./.claude/metrics/boundary-events.jsonl", str(tmp_path)
    )


def test_targets_ledger_absolute_path(tmp_path):
    absolute = str(tmp_path / ".claude" / "metrics" / "boundary-events.jsonl")
    assert guard.targets_ledger(absolute, str(tmp_path))


def test_targets_ledger_false_for_unrelated_file_under_metrics(tmp_path):
    assert not guard.targets_ledger(
        ".claude/metrics/session-digest.jsonl", str(tmp_path)
    )


def test_targets_ledger_false_for_review_verdicts_store(tmp_path):
    """Slice 2's own store — matches the exact ledger name/path, not a
    `.claude/metrics/` prefix (plan Step 1.1 implementation note)."""
    assert not guard.targets_ledger(
        ".claude/metrics/review-verdicts.jsonl", str(tmp_path)
    )


def test_targets_ledger_false_for_empty_path(tmp_path):
    assert not guard.targets_ledger("", str(tmp_path))


# ---------------------------------------------------------------------------
# main() — in-process, stdin-monkeypatched (Write and Edit tool shapes)
# ---------------------------------------------------------------------------


def _stdin(monkeypatch, payload):
    import io

    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))


def test_main_blocks_write_to_ledger(monkeypatch, tmp_path, capsys):
    _stdin(
        monkeypatch,
        {
            "tool_name": "Write",
            "tool_input": {"file_path": ".claude/metrics/boundary-events.jsonl"},
            "cwd": str(tmp_path),
        },
    )
    assert guard.main() == 2
    out = capsys.readouterr().out
    assert "emit_boundary_event()" in out
    assert "BLOCKED" in out


def test_main_blocks_edit_to_ledger(monkeypatch, tmp_path, capsys):
    _stdin(
        monkeypatch,
        {
            "tool_name": "Edit",
            "tool_input": {"file_path": ".claude/metrics/boundary-events.jsonl"},
            "cwd": str(tmp_path),
        },
    )
    assert guard.main() == 2
    out = capsys.readouterr().out
    assert "emit_boundary_event()" in out


def test_main_allows_write_to_unrelated_file(monkeypatch, tmp_path, capsys):
    _stdin(
        monkeypatch,
        {
            "tool_name": "Write",
            "tool_input": {"file_path": ".claude/metrics/session-digest.jsonl"},
            "cwd": str(tmp_path),
        },
    )
    assert guard.main() == 0
    assert capsys.readouterr().out == ""


def test_main_allows_write_to_review_verdicts_store(monkeypatch, tmp_path, capsys):
    _stdin(
        monkeypatch,
        {
            "tool_name": "Write",
            "tool_input": {"file_path": ".claude/metrics/review-verdicts.jsonl"},
            "cwd": str(tmp_path),
        },
    )
    assert guard.main() == 0
    assert capsys.readouterr().out == ""


def test_main_fails_open_on_missing_tool_input(monkeypatch, tmp_path):
    _stdin(monkeypatch, {"tool_name": "Write", "cwd": str(tmp_path)})
    assert guard.main() == 0


def test_main_fails_open_on_non_json_stdin(monkeypatch):
    import io

    monkeypatch.setattr(sys, "stdin", io.StringIO("not-json"))
    assert guard.main() == 0


def test_main_fails_open_on_empty_stdin(monkeypatch):
    import io

    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert guard.main() == 0


def test_main_silent_pass_when_file_path_absent(monkeypatch, tmp_path):
    _stdin(monkeypatch, {"tool_name": "Write", "tool_input": {}, "cwd": str(tmp_path)})
    assert guard.main() == 0
