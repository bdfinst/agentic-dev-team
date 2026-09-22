"""Unit tests for hooks/boundary_events_write_guard.py (#2171).

Plan Step 1.1 covers the Write/Edit path-match guard. Plan Step 1.2 adds
Bash `tool_input.command` write-shape detection (`bash_command_writes_to_ledger`)
and its `main()` dispatch — covered below.

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


# ---------------------------------------------------------------------------
# bash_command_writes_to_ledger — write-shaped commands (Step 1.2)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        # Redirect, across all four path forms (Examples Outline).
        "echo '{}' >> .claude/metrics/boundary-events.jsonl",
        "echo '{}' >> /repo/.claude/metrics/boundary-events.jsonl",
        "echo '{}' >> ./.claude/metrics/boundary-events.jsonl",
        "cd .claude/metrics && echo '{}' >> boundary-events.jsonl",
        # Heredoc, caught via its trailing redirect operator, not `<<`.
        "cat <<'EOF' >> .claude/metrics/boundary-events.jsonl\n{}\nEOF",
        # tee
        "echo '{}' | tee -a .claude/metrics/boundary-events.jsonl",
        # sed -i
        "sed -i 's/a/b/' .claude/metrics/boundary-events.jsonl",
        # cp/mv/rm/truncate/dd
        "rm .claude/metrics/boundary-events.jsonl",
        "mv .claude/metrics/boundary-events.jsonl /tmp/moved.jsonl",
        "cp .claude/metrics/boundary-events.jsonl /tmp/copy.jsonl",
        "truncate -s 0 .claude/metrics/boundary-events.jsonl",
        "dd if=/dev/null of=.claude/metrics/boundary-events.jsonl",
        # python3 -c with a write/append-mode open()
        "python3 -c \"open('.claude/metrics/boundary-events.jsonl', 'w').write('{}')\"",
        "python3 -c \"open('.claude/metrics/boundary-events.jsonl', 'a').write('{}')\"",
    ],
)
def test_bash_command_writes_to_ledger_true_for_write_shaped_commands(command):
    assert guard.bash_command_writes_to_ledger(command) is True


@pytest.mark.parametrize(
    "command",
    [
        "tail -20 .claude/metrics/boundary-events.jsonl",
        "cat .claude/metrics/boundary-events.jsonl",
        "grep foo .claude/metrics/boundary-events.jsonl",
        "head .claude/metrics/boundary-events.jsonl",
        # read-mode (mode omitted, defaults to "r") open()
        "python3 -c \"print(open('.claude/metrics/boundary-events.jsonl').read())\"",
        # reads the ledger, writes elsewhere — tee's own target is not the ledger
        "cat .claude/metrics/boundary-events.jsonl | tee /tmp/copy.jsonl",
        # write-shaped, but targets an unrelated file
        "echo '{}' >> .claude/metrics/session-digest.jsonl",
        "",
    ],
)
def test_bash_command_writes_to_ledger_false_for_read_or_unrelated_commands(command):
    assert guard.bash_command_writes_to_ledger(command) is False


# ---------------------------------------------------------------------------
# main() — Bash tool shape (Step 1.2)
# ---------------------------------------------------------------------------


def test_main_blocks_bash_redirect_to_ledger(monkeypatch, tmp_path, capsys):
    _stdin(
        monkeypatch,
        {
            "tool_name": "Bash",
            "tool_input": {
                "command": "echo '{}' >> .claude/metrics/boundary-events.jsonl"
            },
            "cwd": str(tmp_path),
        },
    )
    assert guard.main() == 2
    out = capsys.readouterr().out
    assert "BLOCKED" in out
    assert "hooks/lib/boundary_events.py" in out
    # Bash-path message names the CLI, not the Python-only function
    # (plan-review-ux finding, Step 1.2).
    assert "emit_boundary_event()" not in out


def test_main_allows_bash_read_of_ledger(monkeypatch, tmp_path, capsys):
    _stdin(
        monkeypatch,
        {
            "tool_name": "Bash",
            "tool_input": {"command": "tail -20 .claude/metrics/boundary-events.jsonl"},
            "cwd": str(tmp_path),
        },
    )
    assert guard.main() == 0
    assert capsys.readouterr().out == ""


def test_main_allows_bash_command_with_no_command_field(monkeypatch, tmp_path):
    _stdin(monkeypatch, {"tool_name": "Bash", "tool_input": {}, "cwd": str(tmp_path)})
    assert guard.main() == 0
