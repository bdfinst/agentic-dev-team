"""Unit tests for hooks/lib/turn_identity.py.

Covers the shared transcript_id/count_user_lines helpers extracted out of
codegraph_nudge.py (and later adopted by codegraph_turn_mark.py in a
follow-up slice) so the two sides of the turn-mark sentinel contract can't
drift apart.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
_HOOKS_LIB = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"

# Load by explicit file path (not a bare `import turn_identity`) so the
# module resolves deterministically regardless of sys.path order — see the
# precedent/rationale in test_cost_meter_lib.py (#1120).
_TURN_IDENTITY_PATH = _HOOKS_LIB / "turn_identity.py"
_spec = importlib.util.spec_from_file_location("turn_identity_lib", _TURN_IDENTITY_PATH)
assert _spec is not None and _spec.loader is not None
turn_identity = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(turn_identity)


def test_transcript_id():
    assert turn_identity.transcript_id("/x/y/abc123.jsonl") == "abc123"
    assert turn_identity.transcript_id("abc123.json") == "abc123"
    assert turn_identity.transcript_id("noext") == "noext"


def test_count_user_lines_tail_window(tmp_path: Path):
    transcript = tmp_path / "t.jsonl"

    # Content beyond the tail window should not be counted — write a
    # padding line larger than _TAIL_WINDOW_BYTES that itself contains a
    # user marker, followed by a small tail with exactly 2 more markers.
    padding = (
        '{"type":"user","message":"' + ("x" * turn_identity._TAIL_WINDOW_BYTES) + '"}\n'
    )
    tail = '{"type":"user"}\n{"type":"assistant"}\n{"type":"user"}\n'
    transcript.write_text(padding + tail)

    assert turn_identity.count_user_lines(transcript) == 2


def test_count_user_lines_missing_file_returns_zero(tmp_path: Path):
    assert turn_identity.count_user_lines(tmp_path / "nope.jsonl") == 0


def test_matches_current_turn_true_on_exact_match():
    sentinel = {"transcript_id": "abc123", "turn_counter": 3}
    assert turn_identity.matches_current_turn(sentinel, "abc123", 3) is True


def test_matches_current_turn_false_on_mismatched_transcript():
    sentinel = {"transcript_id": "other", "turn_counter": 3}
    assert turn_identity.matches_current_turn(sentinel, "abc123", 3) is False


def test_matches_current_turn_false_on_mismatched_counter():
    sentinel = {"transcript_id": "abc123", "turn_counter": 2}
    assert turn_identity.matches_current_turn(sentinel, "abc123", 3) is False


def test_matches_current_turn_corrupt_turn_counter_returns_false():
    """A non-numeric turn_counter must fail closed to False rather than
    raise — the regression guard for the read-side crash bug where
    `int(sentinel_tc)` could raise ValueError/TypeError uncaught."""
    sentinel = {"transcript_id": "abc123", "turn_counter": "not-a-number"}
    assert turn_identity.matches_current_turn(sentinel, "abc123", 3) is False

    sentinel_list = {"transcript_id": "abc123", "turn_counter": ["nope"]}
    assert turn_identity.matches_current_turn(sentinel_list, "abc123", 3) is False
