"""Unit tests for hooks/lib/cost_meter.py (#732).

Covers two independent #732 fixes:
  * `record` path perf fix — `cmd_record` is invoked once per Stop/
    SubagentStop hook fire over the life of a session. Before this fix it
    called `parse_transcript()`, which re-reads and re-parses the *entire*
    transcript file from byte 0 on every single fire — O(turns) work
    repeated O(turns) times over a long session. This suite proves the
    fix: `cmd_record` now persists a byte offset (plus the running
    per-model/per-thread aggregates) in a tmp-state file keyed by the
    transcript path, and only tails bytes appended since the last fire.
  * naming cleanup — the generically-named `_dig()` helper (renamed
    `_first_present_field`) and the compressed `inp`/`out`/`cw`/`cr` local
    variables inside `_cost()`.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import os
import re
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_HOOKS_LIB = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"

# Load hooks/lib/cost_meter.py by explicit file path under a unique module name
# rather than a bare `import cost_meter`. A sibling module of the same basename
# exists at hooks/cost_meter.py, so a bare import resolves ambiguously by
# sys.path order: in a full-suite run another test can leave the top-level
# `hooks/` dir ahead of `hooks/lib/` on sys.path, and the plain import silently
# binds the WRONG cost_meter. Loading by path (and a distinct sys.modules key)
# pins the lib version regardless of import mode or sys.path state. See #1120.
_COST_METER_PATH = _HOOKS_LIB / "cost_meter.py"
_spec = importlib.util.spec_from_file_location("cost_meter_lib", _COST_METER_PATH)
assert _spec is not None and _spec.loader is not None
cost_meter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cost_meter)


_PRICING = {
    "cache_write_multiplier": 1.25,
    "cache_read_multiplier": 0.1,
    "models": {
        "claude-x": {"input": 3.0, "output": 15.0},
    },
    "aliases": {},
}


def _usage_line(
    model: str, input_tokens: int, output_tokens: int, sidechain: bool = False
) -> str:
    rec = {
        "message": {
            "model": model,
            "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
        },
    }
    if sidechain:
        rec["isSidechain"] = True
    return json.dumps(rec) + "\n"


# ---------------------------------------------------------------------------
# _read_new_lines — the bounded tail-read primitive
# ---------------------------------------------------------------------------


def test_read_new_lines_returns_nothing_past_eof(tmp_path):
    p = tmp_path / "t.jsonl"
    p.write_text("line-one\nline-two\n")
    offset = p.stat().st_size
    new_offset, lines = cost_meter._read_new_lines(p, offset)
    assert lines == []
    assert new_offset == offset


def test_read_new_lines_only_returns_content_after_offset(tmp_path):
    """Proves the read is bounded to new bytes, not a full re-read from 0."""
    p = tmp_path / "t.jsonl"
    p.write_text("line-one\nline-two\n")
    offset = p.stat().st_size
    with p.open("a") as fh:
        fh.write("line-three\n")
    new_offset, lines = cost_meter._read_new_lines(p, offset)
    # If this had re-read from byte 0, line-one/line-two would show up too.
    assert lines == ["line-three"]
    assert new_offset == p.stat().st_size


def test_read_new_lines_keeps_partial_trailing_line_unconsumed(tmp_path):
    p = tmp_path / "t.jsonl"
    p.write_text("complete\n")
    with p.open("a") as fh:
        fh.write("partial-no-newline-yet")
    new_offset, lines = cost_meter._read_new_lines(p, 0)
    assert lines == ["complete"]
    assert new_offset == len("complete\n".encode("utf-8"))


# ---------------------------------------------------------------------------
# cmd_record — persists offset + aggregates, only tails new content
# ---------------------------------------------------------------------------


@pytest.fixture
def hermetic_cost_meter(tmp_path, monkeypatch):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    yield tmp_path


def test_cmd_record_persists_byte_offset_state(hermetic_cost_meter):
    tmp_path = hermetic_cost_meter
    transcript = tmp_path / "transcript.jsonl"
    log = tmp_path / "metrics" / "cost-metering.jsonl"
    transcript.write_text(_usage_line("claude-x", 100, 50))

    args = SimpleNamespace(transcript=str(transcript), log=str(log))
    cost_meter.cmd_record(args, _PRICING)

    state_file = cost_meter._state_file(transcript)
    assert state_file.is_file()
    state = json.loads(state_file.read_text())
    assert state["offset"] == transcript.stat().st_size


def test_cmd_record_second_fire_only_tails_new_content(
    hermetic_cost_meter, monkeypatch
):
    """The core bounded-read contract: on the 2nd fire, `_read_new_lines` must
    be called with the offset left off at, never 0 — i.e. it must not re-scan
    content already accounted for."""
    tmp_path = hermetic_cost_meter
    transcript = tmp_path / "transcript.jsonl"
    log = tmp_path / "metrics" / "cost-metering.jsonl"
    transcript.write_text(_usage_line("claude-x", 100, 50))

    args = SimpleNamespace(transcript=str(transcript), log=str(log))
    cost_meter.cmd_record(args, _PRICING)
    offset_after_first = transcript.stat().st_size

    with transcript.open("a") as fh:
        fh.write(_usage_line("claude-x", 200, 75))

    seen_offsets = []
    real_read_new_lines = cost_meter._read_new_lines

    def _spy(path, offset):
        seen_offsets.append(offset)
        return real_read_new_lines(path, offset)

    monkeypatch.setattr(cost_meter, "_read_new_lines", _spy)
    cost_meter.cmd_record(args, _PRICING)

    assert seen_offsets == [offset_after_first]


def test_cmd_record_across_two_fires_matches_full_reparse(hermetic_cost_meter):
    """Correctness: cumulative totals recorded incrementally must equal a
    from-scratch full parse of the final transcript."""
    tmp_path = hermetic_cost_meter
    transcript = tmp_path / "transcript.jsonl"
    log = tmp_path / "metrics" / "cost-metering.jsonl"
    transcript.write_text(_usage_line("claude-x", 100, 50))

    args = SimpleNamespace(transcript=str(transcript), log=str(log))
    cost_meter.cmd_record(args, _PRICING)

    with transcript.open("a") as fh:
        fh.write(_usage_line("claude-x", 200, 75, sidechain=True))
        fh.write(_usage_line("claude-x", 10, 5))

    cost_meter.cmd_record(args, _PRICING)

    logged_lines = log.read_text().splitlines()
    assert len(logged_lines) == 2
    last = json.loads(logged_lines[-1])

    expected = cost_meter.parse_transcript(transcript, _PRICING)
    assert last["total"]["input_tokens"] == expected["totals"]["input_tokens"]
    assert last["total"]["output_tokens"] == expected["totals"]["output_tokens"]
    assert last["total"]["cost_usd"] == expected["totals"]["cost_usd"]


def test_cmd_record_resets_when_transcript_shrinks(hermetic_cost_meter):
    """A truncated/rotated transcript (offset > new size) must reset from
    scratch rather than seek past EOF."""
    tmp_path = hermetic_cost_meter
    transcript = tmp_path / "transcript.jsonl"
    log = tmp_path / "metrics" / "cost-metering.jsonl"
    transcript.write_text(_usage_line("claude-x", 100, 50) * 5)

    args = SimpleNamespace(transcript=str(transcript), log=str(log))
    cost_meter.cmd_record(args, _PRICING)

    # Simulate rotation: transcript replaced by a smaller fresh file.
    transcript.write_text(_usage_line("claude-x", 10, 5))
    cost_meter.cmd_record(args, _PRICING)

    logged_lines = log.read_text().splitlines()
    last = json.loads(logged_lines[-1])
    assert last["total"]["input_tokens"] == 10
    assert last["total"]["output_tokens"] == 5


# ---------------------------------------------------------------------------
# _purge_stale — TTL purge for the new cost-meter state dir
# ---------------------------------------------------------------------------


def test_purge_stale_removes_old_state_but_keeps_fresh(hermetic_cost_meter):
    tmp_path = hermetic_cost_meter
    state_dir = cost_meter._state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)

    stale = state_dir / "session-aaaaaaaaaaaa.json"
    stale.write_text("{}")
    old_time = time.time() - cost_meter._STATE_TTL_SECONDS - 60
    os.utime(stale, (old_time, old_time))

    fresh = state_dir / "session-bbbbbbbbbbbb.json"
    fresh.write_text("{}")

    cost_meter._purge_stale(state_dir)

    assert not stale.exists()
    assert fresh.exists()


# ---------------------------------------------------------------------------
# _first_present_field / _cost — field-lookup and cost math naming cleanup
# ---------------------------------------------------------------------------


def test_first_present_field_prefers_top_level_record():
    rec = {"usage": {"input_tokens": 1}, "message": {"usage": {"input_tokens": 2}}}
    assert cost_meter._first_present_field(rec, "usage") == {"input_tokens": 1}


def test_first_present_field_falls_back_to_message():
    rec = {"message": {"model": "claude-x"}}
    assert cost_meter._first_present_field(rec, "model") == "claude-x"


def test_first_present_field_returns_none_when_absent():
    rec = {"message": {}}
    assert cost_meter._first_present_field(rec, "model") is None


def test_cost_computes_expected_dollars():
    usage = {
        "input_tokens": 1_000_000,
        "output_tokens": 1_000_000,
        "cache_creation_input_tokens": 1_000_000,
        "cache_read_input_tokens": 1_000_000,
    }
    rate = _PRICING["models"]["claude-x"]
    cost = cost_meter._cost(usage, rate, _PRICING)
    expected = 3.0 + 15.0 + (3.0 * 1.25) + (3.0 * 0.1)
    assert cost == expected


def test_dig_helper_renamed_descriptively():
    # Low-severity naming finding (#732): `_dig()` and its compressed
    # inp/out/cw/cr locals in `_cost()` should carry descriptive names.
    assert not hasattr(cost_meter, "_dig")
    assert hasattr(cost_meter, "_first_present_field")

    cost_source = inspect.getsource(cost_meter._cost)
    for cryptic in ("inp", "out", "cw", "cr"):
        assert re.search(rf"\b{cryptic}\b", cost_source) is None
    for descriptive in (
        "input_tokens",
        "output_tokens",
        "cache_write_tokens",
        "cache_read_tokens",
    ):
        assert descriptive in cost_source
