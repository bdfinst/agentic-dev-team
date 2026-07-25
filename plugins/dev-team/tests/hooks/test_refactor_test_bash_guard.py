"""Unit tests for hooks/refactor_test_bash_guard.py (#906).

The preventive, Bash-aware sibling of refactor_test_freeze_guard.py: block,
pass-through, staleness, and fail-open paths, plus per-shape coverage of the
regex library and the boundary-events wiring.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "hooks"))
sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"))

import refactor_test_bash_guard as guard
from test_file_classify import STALE_AFTER_SECONDS

_WRITTEN_AT = "2026-07-04T10:00:00+00:00"
_WRITTEN_AT_EPOCH = 1783159200.0
_NOW = _WRITTEN_AT_EPOCH + 60


def _write_state(tmp_path: Path, phase: str = "refactor", **overrides) -> None:
    state = {
        "phase": phase,
        "step": "2.1",
        "written_at": _WRITTEN_AT,
        "test_files_staged": ["src/thing.test.js"],
    }
    state.update(overrides)
    path = tmp_path / "memory" / "build-phase.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state))


def _audit_events(tmp_path: Path):
    path = tmp_path / ".claude" / "metrics" / "refactor-freeze.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


# ---------------------------------------------------------------------------
# One true-positive block per recognized Bash shape.
# ---------------------------------------------------------------------------

_TRUE_POSITIVE_COMMANDS = [
    ("sed-i", "sed -i 's/x/y/' src/thing.test.js"),
    ("sed-i", "sed -i.bak 's/x/y/' src/thing.test.js"),
    ("perl-i", "perl -i -pe 's/x/y/' src/thing.test.js"),
    ("tee", "tee src/thing.test.js <<< 'x'"),
    ("tee", "tee -a src/thing.test.js <<< 'x'"),
    ("redirect", "echo 'x' > src/thing.test.js"),
    ("redirect", "echo 'x' >> src/thing.test.js"),
    ("mv-cp", "mv src/a.js src/thing.test.js"),
    ("mv-cp", "cp src/a.js src/thing.test.js"),
    (
        "python-open-write",
        "python3 -c \"open('src/thing.test.js', 'w').write('x')\"",
    ),
]


def test_each_recognized_shape_blocks_a_staged_test_file(tmp_path):
    for rule_id, command in _TRUE_POSITIVE_COMMANDS:
        _write_state(tmp_path)
        (tmp_path / ".claude" / "metrics" / "refactor-freeze.jsonl").unlink(missing_ok=True)
        code, lines, matched_rule = guard.evaluate(command, tmp_path, now=_NOW)
        assert code == 2, command
        assert lines[0].startswith("[BLOCK]"), command
        assert matched_rule == rule_id, command


def test_compound_command_dangerous_target_after_earlier_redirect_match(tmp_path):
    """#914 regression: a benign 'redirect' match earlier in a compound
    command must never mask a later, genuinely dangerous 'mv-cp' match on a
    frozen test file — all patterns are evaluated, not just the first hit."""
    _write_state(tmp_path)
    code, _lines, matched_rule = guard.evaluate(
        "echo done > /tmp/log.txt; mv src/scratch.js src/thing.test.js",
        tmp_path,
        now=_NOW,
    )
    assert code == 2
    assert matched_rule == "mv-cp"


def test_compound_command_double_ampersand_delimiter_still_blocks(tmp_path):
    """#914 regression, `&&` delimiter: the masking bug isn't specific to
    `;` — any compound-command delimiter must reach the later target."""
    _write_state(tmp_path)
    code, _lines, matched_rule = guard.evaluate(
        "echo done > /tmp/log.txt && mv src/scratch.js src/thing.test.js",
        tmp_path,
        now=_NOW,
    )
    assert code == 2
    assert matched_rule == "mv-cp"


def test_compound_command_dangerous_target_before_later_benign_redirect(tmp_path):
    """#914 regression, reverse order: the dangerous target appearing
    textually FIRST (with a benign redirect afterward) must still block —
    matching isn't just fixed for one direction of ordering."""
    _write_state(tmp_path)
    code, _lines, matched_rule = guard.evaluate(
        "mv src/scratch.js src/thing.test.js; echo done > /tmp/log.txt",
        tmp_path,
        now=_NOW,
    )
    assert code == 2
    assert matched_rule == "mv-cp"


def test_compound_command_same_rule_repeated_only_second_occurrence_dangerous(
    tmp_path,
):
    """#914 regression, same-rule masking: two segments both match the
    `mv-cp` pattern; the first targets a non-test file and the second a
    frozen test file. `re.search` (single match per pattern) would only see
    the first, benign occurrence and miss the second — every occurrence of
    every pattern must be evaluated, not just the first per rule_id."""
    _write_state(tmp_path)
    code, _lines, matched_rule = guard.evaluate(
        "mv src/a.js src/scratch.js; mv src/b.js src/thing.test.js",
        tmp_path,
        now=_NOW,
    )
    assert code == 2
    assert matched_rule == "mv-cp"


def test_block_names_the_file_and_recovery(tmp_path):
    _write_state(tmp_path)
    _, lines, _ = guard.evaluate(
        "sed -i 's/x/y/' src/thing.test.js", tmp_path, now=_NOW
    )
    body = " ".join(lines)
    assert "src/thing.test.js" in body
    assert "TEST" in body and "REFACTOR" in body


def test_block_is_recorded_in_the_audit_log(tmp_path):
    _write_state(tmp_path)
    guard.evaluate("sed -i 's/x/y/' src/thing.test.js", tmp_path, now=_NOW)
    events = _audit_events(tmp_path)
    assert [e["event"] for e in events] == ["block"]
    assert events[0]["file"] == "src/thing.test.js"
    assert events[0]["step"] == "2.1"


# ---------------------------------------------------------------------------
# Ambiguous / non-matching / out-of-scope commands never block.
# ---------------------------------------------------------------------------

_NO_BLOCK_COMMANDS = [
    "ls -la",
    "git commit -m 'wip'",
    "npm test",
    "cmd 2>&1",
    "echo hello world",
]


def test_unparseable_commands_never_block(tmp_path):
    _write_state(tmp_path)
    for command in _NO_BLOCK_COMMANDS:
        assert guard.evaluate(command, tmp_path, now=_NOW) == (0, [], None), command


def test_compound_command_with_only_benign_targets_is_a_no_op(tmp_path):
    """#914 regression, other direction: evaluating every pattern (instead
    of stopping at the first match) must not turn a compound command with
    only benign targets into a false-positive block."""
    _write_state(tmp_path)
    result = guard.evaluate(
        "echo done > /tmp/log.txt; mv src/scratch.js src/other-scratch.js",
        tmp_path,
        now=_NOW,
    )
    assert result == (0, [], None)


def test_matching_shape_on_a_non_test_target_is_a_no_op(tmp_path):
    _write_state(tmp_path)
    code, lines, matched_rule = guard.evaluate(
        "sed -i 's/x/y/' src/thing.ts", tmp_path, now=_NOW
    )
    assert (code, lines, matched_rule) == (0, [], None)


def test_matching_shape_outside_refactor_phase_is_a_no_op(tmp_path):
    for phase in ("implement", "test", "red", "green"):
        _write_state(tmp_path, phase=phase)
        result = guard.evaluate("sed -i 's/x/y/' src/thing.test.js", tmp_path, now=_NOW)
        assert result == (0, [], None), phase


def test_no_op_when_no_phase_is_recorded(tmp_path):
    assert guard.evaluate("sed -i 's/x/y/' src/thing.test.js", tmp_path, now=_NOW) == (
        0,
        [],
        None,
    )


def test_stale_refactor_state_does_not_linger(tmp_path):
    _write_state(tmp_path)
    result = guard.evaluate(
        "sed -i 's/x/y/' src/thing.test.js",
        tmp_path,
        now=_WRITTEN_AT_EPOCH + STALE_AFTER_SECONDS + 1,
    )
    assert result == (0, [], None)


def test_empty_command_passes_silently(tmp_path):
    _write_state(tmp_path)
    assert guard.evaluate("", tmp_path, now=_NOW) == (0, [], None)


# ---------------------------------------------------------------------------
# New-test-file creation is blocked preemptively (never reaches disk).
# ---------------------------------------------------------------------------


def test_new_test_file_creation_is_blocked_preemptively(tmp_path):
    _write_state(tmp_path)  # baseline staged file is src/thing.test.js only
    code, _lines, matched_rule = guard.evaluate(
        "tee src/rogue.spec.js <<< 'x'", tmp_path, now=_NOW
    )
    assert code == 2
    assert matched_rule == "tee"
    assert not (tmp_path / "src" / "rogue.spec.js").exists()


def test_new_non_test_file_creation_is_allowed(tmp_path):
    _write_state(tmp_path)
    result = guard.evaluate("tee src/scratch.js <<< 'x'", tmp_path, now=_NOW)
    assert result == (0, [], None)


# ---------------------------------------------------------------------------
# Fail-open paths.
# ---------------------------------------------------------------------------


def test_malformed_state_fails_open_with_an_audit_line(tmp_path):
    path = tmp_path / "memory" / "build-phase.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json")
    result = guard.evaluate("sed -i 's/x/y/' src/thing.test.js", tmp_path, now=_NOW)
    assert result == (0, [], None)
    events = _audit_events(tmp_path)
    assert [e["event"] for e in events] == ["fail-open"]


def test_main_fails_open_on_internal_error(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        guard, "read_stdin_json", lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    assert guard.main() == 0
    assert capsys.readouterr().out == ""
    events = _audit_events(tmp_path)
    assert [e["event"] for e in events] == ["fail-open"]


def test_missing_pattern_file_falls_back_to_defaults(tmp_path, monkeypatch):
    _write_state(tmp_path)
    monkeypatch.setattr(guard, "_PATTERNS_FILE", tmp_path / "does-not-exist.json")
    code, _lines, matched_rule = guard.evaluate(
        "sed -i 's/x/y/' src/thing.test.js", tmp_path, now=_NOW
    )
    assert code == 2
    assert matched_rule == "sed-i"


def test_malformed_pattern_file_falls_back_to_defaults(tmp_path, monkeypatch):
    _write_state(tmp_path)
    bogus = tmp_path / "bogus-patterns.json"
    bogus.write_text("{not json")
    monkeypatch.setattr(guard, "_PATTERNS_FILE", bogus)
    code, _lines, matched_rule = guard.evaluate(
        "sed -i 's/x/y/' src/thing.test.js", tmp_path, now=_NOW
    )
    assert code == 2
    assert matched_rule == "sed-i"


# ---------------------------------------------------------------------------
# main() end-to-end + boundary-events emission.
# ---------------------------------------------------------------------------


def test_main_blocks_via_stdin_payload_and_emits_boundary_event(
    tmp_path, monkeypatch, capsys
):
    import datetime

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    _write_state(tmp_path, written_at=now_iso)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        guard,
        "read_stdin_json",
        lambda: {
            "tool_input": {"command": "sed -i 's/x/y/' src/thing.test.js"},
            "session_id": "sess-1",
        },
    )
    assert guard.main() == 2
    assert "[BLOCK]" in capsys.readouterr().out

    events_path = tmp_path / "metrics" / "boundary-events.jsonl"
    assert events_path.is_file()
    events = [json.loads(line) for line in events_path.read_text().splitlines() if line]
    assert events[-1]["decision"] == "block"
    assert events[-1]["hook"] == "refactor_test_bash_guard"
    assert events[-1]["matched_rule"] == "sed-i"
    assert events[-1]["session_id"] == "sess-1"


def test_main_allows_non_matching_command(tmp_path, monkeypatch, capsys):
    _write_state(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        guard,
        "read_stdin_json",
        lambda: {"tool_input": {"command": "npm test"}},
    )
    assert guard.main() == 0
    assert capsys.readouterr().out == ""
