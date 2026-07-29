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
from types import SimpleNamespace

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

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
    assert new_offset == len(b"complete\n")


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


def _usage_line_with_cache(model, inp, out, cache_create, cache_read, *, sidechain=False, attribution=None):
    rec = {
        "message": {
            "model": model,
            "usage": {
                "input_tokens": inp,
                "output_tokens": out,
                "cache_creation_input_tokens": cache_create,
                "cache_read_input_tokens": cache_read,
            },
        },
    }
    if sidechain:
        rec["isSidechain"] = True
    if attribution:
        rec["attributionAgent"] = attribution
    return json.dumps(rec) + "\n"


def test_cmd_record_persists_cache_tokens_per_bucket(hermetic_cost_meter):
    """#1513 — the durable log's per-bucket slim output must carry
    cache_creation_input_tokens (the spawn-floor F component), so F is readable
    from cost-metering.jsonl, not only from `report --json`."""
    tmp_path = hermetic_cost_meter
    transcript = tmp_path / "transcript.jsonl"
    log = tmp_path / "metrics" / "cost-metering.jsonl"
    transcript.write_text(
        _usage_line_with_cache("claude-x", 100, 50, 108000, 5000)
        + _usage_line_with_cache(
            "claude-x", 20, 900, 40000, 2000, sidechain=True, attribution="security-review"
        )
    )

    cost_meter.cmd_record(SimpleNamespace(transcript=str(transcript), log=str(log)), _PRICING)

    entry = json.loads(log.read_text().splitlines()[-1])
    # Every dimension's buckets carry both cache fields.
    for dim in ("by_agent_type", "by_thread", "by_model"):
        for bucket in entry[dim].values():
            assert "cache_creation_input_tokens" in bucket
            assert "cache_read_input_tokens" in bucket
    # The subagent's spawn floor is now legible from the log — both cache
    # fields, on all three dimensions, value-checked (not just present).
    assert entry["by_agent_type"]["security-review"]["cache_creation_input_tokens"] == 40000
    assert entry["by_agent_type"]["security-review"]["cache_read_input_tokens"] == 2000
    assert entry["by_agent_type"]["main"]["cache_creation_input_tokens"] == 108000
    assert entry["by_agent_type"]["main"]["cache_read_input_tokens"] == 5000
    assert entry["by_thread"]["subagent"]["cache_creation_input_tokens"] == 40000
    assert entry["by_thread"]["subagent"]["cache_read_input_tokens"] == 2000
    # by_model aggregates both records (same model claude-x): 108000+40000, 5000+2000.
    assert entry["by_model"]["claude-x"]["cache_creation_input_tokens"] == 148000
    assert entry["by_model"]["claude-x"]["cache_read_input_tokens"] == 7000


def test_log_round_trips_cache_keys_and_readers_consume_it(hermetic_cost_meter, capsys):
    """AC3 — a durable log whose buckets carry the new cache keys round-trips
    intact and is consumed by readers. Asserts observable output, not just a
    (tautological) return code: regression must hit the real >=2-session branch
    ('no cost regression'), and pace must print the cumulative spend."""
    tmp_path = hermetic_cost_meter
    transcript = tmp_path / "transcript.jsonl"
    log = tmp_path / "metrics" / "cost-metering.jsonl"
    transcript.write_text(_usage_line_with_cache("claude-x", 100, 50, 108000, 5000))
    cost_meter.cmd_record(SimpleNamespace(transcript=str(transcript), log=str(log)), _PRICING)
    # A second session so regression exercises the real comparison branch.
    transcript.write_text(_usage_line_with_cache("claude-x", 120, 60, 90000, 4000))
    cost_meter._state_file(transcript).unlink(missing_ok=True)
    cost_meter.cmd_record(SimpleNamespace(transcript=str(transcript), log=str(log)), _PRICING)

    lines = log.read_text().splitlines()
    assert len(lines) == 2  # both sessions persisted (disambiguates the branch below)
    # Round-trip: the new cache keys survive in the durable log's buckets.
    assert json.loads(lines[-1])["by_agent_type"]["main"]["cache_creation_input_tokens"] == 90000

    rc = cost_meter.cmd_regression(
        SimpleNamespace(log=str(log), tolerance=0.5, window=0), _PRICING
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "no cost regression" in out  # the real >=2-session branch, not "only N session(s)"

    cost_meter.cmd_pace(
        SimpleNamespace(log=str(log), budget=None, period_days=30, window_days=7), _PRICING
    )
    assert "cumulative spend" in capsys.readouterr().out


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
# by_agent_type (#1094) — incremental record path
# ---------------------------------------------------------------------------


def test_cmd_record_dispatch_join_survives_across_fires(hermetic_cost_meter):
    """The Task-dispatch join maps (tool_use id -> subagent_type,
    agentId -> subagent_type) must persist in state: dispatch may land in one
    fire and the sidechain turns it explains in a later one."""
    tmp_path = hermetic_cost_meter
    transcript = tmp_path / "transcript.jsonl"
    log = tmp_path / "metrics" / "cost-metering.jsonl"

    dispatch = json.dumps(
        {
            "type": "assistant",
            "message": {
                "model": "claude-x",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_9",
                        "name": "Task",
                        "input": {"subagent_type": "security-review", "prompt": "p"},
                    }
                ],
            },
        }
    )
    transcript.write_text(dispatch + "\n")

    args = SimpleNamespace(transcript=str(transcript), log=str(log))
    cost_meter.cmd_record(args, _PRICING)

    result = json.dumps(
        {
            "type": "user",
            "toolUseResult": {"agentId": "agent9"},
            "message": {
                "content": [{"type": "tool_result", "tool_use_id": "toolu_9"}]
            },
        }
    )
    sidechain = json.dumps(
        {
            "type": "assistant",
            "isSidechain": True,
            "agentId": "agent9",
            "message": {
                "model": "claude-x",
                "usage": {"input_tokens": 700, "output_tokens": 70},
            },
        }
    )
    with transcript.open("a") as fh:
        fh.write(result + "\n" + sidechain + "\n")
    cost_meter.cmd_record(args, _PRICING)

    last = json.loads(log.read_text().splitlines()[-1])
    assert last["by_agent_type"]["security-review"]["input_tokens"] == 700


def test_cmd_record_tails_sibling_subagent_files_with_per_file_offsets(
    hermetic_cost_meter,
):
    """Sibling per-subagent transcripts (#1094) are tailed incrementally too:
    cumulative totals across fires must match a from-scratch full reparse."""
    tmp_path = hermetic_cost_meter
    transcript = tmp_path / "transcript.jsonl"
    log = tmp_path / "metrics" / "cost-metering.jsonl"
    transcript.write_text(_usage_line("claude-x", 100, 50))

    subdir = tmp_path / "transcript" / "subagents"
    subdir.mkdir(parents=True)
    sub = subdir / "agent-abc.jsonl"

    def _sub_line(input_tokens: int) -> str:
        return json.dumps(
            {
                "type": "assistant",
                "isSidechain": True,
                "agentId": "abc",
                "attributionAgent": "test-review",
                "message": {
                    "model": "claude-x",
                    "usage": {"input_tokens": input_tokens, "output_tokens": 1},
                },
            }
        ) + "\n"

    sub.write_text(_sub_line(1000))

    args = SimpleNamespace(transcript=str(transcript), log=str(log))
    cost_meter.cmd_record(args, _PRICING)

    state = json.loads(cost_meter._state_file(transcript).read_text())
    assert state["subagent_offsets"]["agent-abc.jsonl"] == sub.stat().st_size

    with sub.open("a") as fh:
        fh.write(_sub_line(2000))
    cost_meter.cmd_record(args, _PRICING)

    last = json.loads(log.read_text().splitlines()[-1])
    expected = cost_meter.parse_transcript(transcript, _PRICING)
    assert last["total"]["input_tokens"] == expected["totals"]["input_tokens"]
    assert (
        last["by_agent_type"]["test-review"]["input_tokens"]
        == expected["by_agent_type"]["test-review"]["input_tokens"]
        == 3000
    )


def test_cmd_record_rebuilds_from_scratch_on_pre_1094_state_schema(
    hermetic_cost_meter,
):
    """A persisted state without by_agent_type (pre-#1094) must trigger a full
    rebuild — resuming it would ship an agent-type dimension that no longer
    sums to the session totals."""
    tmp_path = hermetic_cost_meter
    transcript = tmp_path / "transcript.jsonl"
    log = tmp_path / "metrics" / "cost-metering.jsonl"
    transcript.write_text(_usage_line("claude-x", 100, 50, sidechain=True))

    stale_state = {
        "offset": transcript.stat().st_size,
        "by_model": {},
        "by_thread": {},
        "totals": {},
        "unpriced_models": [],
    }
    state_file = cost_meter._state_file(transcript)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(stale_state))

    args = SimpleNamespace(transcript=str(transcript), log=str(log))
    cost_meter.cmd_record(args, _PRICING)

    last = json.loads(log.read_text().splitlines()[-1])
    assert last["total"]["input_tokens"] == 100
    assert last["by_agent_type"]["unattributed"]["input_tokens"] == 100


# ---------------------------------------------------------------------------
# _purge_stale — TTL purge for the new cost-meter state dir
# ---------------------------------------------------------------------------


def test_purge_stale_removes_old_state_but_keeps_fresh(hermetic_cost_meter):
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


# ---------------------------------------------------------------------------
# #1531 — cmd_regression decision-branch coverage. The spike/within-tolerance
# return-code and the --window baseline flip are already covered by
# tests/repo/test_cost_meter.py; these pin the three remaining branches:
# the <2-session short-circuit, the strict latest==limit boundary, and the
# mean>0 zero-baseline guard. Expected values hand-derived from the documented
# mean*(1+tolerance) rule and verified against the live function.
# ---------------------------------------------------------------------------
def _write_cost_log(path, costs):
    path.write_text("".join(json.dumps({"total": {"cost_usd": c}}) + "\n" for c in costs))


@pytest.mark.parametrize("costs,count", [([2.0], 1), ([], 0)])
def test_cmd_regression_short_circuits_under_two_sessions(hermetic_cost_meter, capsys, costs, count):
    log = hermetic_cost_meter / "c.jsonl"
    _write_cost_log(log, costs)
    rc = cost_meter.cmd_regression(SimpleNamespace(log=str(log), tolerance=0.5, window=0), _PRICING)
    out = capsys.readouterr().out
    assert rc == 0
    assert f"only {count} session(s) logged; need >=2" in out


def test_cmd_regression_latest_equal_to_limit_is_not_a_regression(hermetic_cost_meter, capsys):
    # prior [1.0, 1.0] -> mean 1.0, +50% -> limit 1.5; latest 1.5 == limit; strict > means no regression.
    log = hermetic_cost_meter / "c.jsonl"
    _write_cost_log(log, [1.0, 1.0, 1.5])
    rc = cost_meter.cmd_regression(SimpleNamespace(log=str(log), tolerance=0.5, window=0), _PRICING)
    out = capsys.readouterr().out
    assert rc == 0
    assert "no cost regression" in out


def test_cmd_regression_zero_baseline_never_flags(hermetic_cost_meter, capsys):
    # prior mean 0.0 -> the `mean > 0` guard suppresses a regression even though latest > limit(==0).
    log = hermetic_cost_meter / "c.jsonl"
    _write_cost_log(log, [0.0, 0.0, 5.0])
    rc = cost_meter.cmd_regression(SimpleNamespace(log=str(log), tolerance=0.5, window=0), _PRICING)
    out = capsys.readouterr().out
    assert rc == 0
    assert "no cost regression" in out


# ---------------------------------------------------------------------------
# #1535 — cmd_regression's remaining untested branches: an absent log file and
# the malformed-JSON-line skip.
# ---------------------------------------------------------------------------
def test_cmd_regression_missing_log_is_noop(hermetic_cost_meter, capsys):
    missing = hermetic_cost_meter / "does-not-exist.jsonl"
    rc = cost_meter.cmd_regression(SimpleNamespace(log=str(missing), tolerance=0.5, window=0), _PRICING)
    out = capsys.readouterr().out
    assert rc == 0
    assert "no metrics log yet" in out


def test_cmd_regression_skips_malformed_lines_and_counts_valid(hermetic_cost_meter, capsys):
    # A garbage line between valid entries must be skipped, and the 3 valid costs
    # ([1.0, 1.0] prior -> limit 1.5; latest 5.0) must still drive the verdict.
    log = hermetic_cost_meter / "c.jsonl"
    log.write_text(
        '{"total": {"cost_usd": 1.0}}\n'
        "NOT JSON {{\n"
        '{"total": {"cost_usd": 1.0}}\n'
        '{"total": {"cost_usd": 5.0}}\n'
    )
    rc = cost_meter.cmd_regression(SimpleNamespace(log=str(log), tolerance=0.5, window=0), _PRICING)
    out = capsys.readouterr().out
    assert rc == 1
    assert "COST REGRESSION" in out
    # "prior 2" proves all 3 valid entries were counted (2 priors + latest); if the
    # skip had also dropped a valid entry it would read "prior 1".
    assert "rolling-mean(prior 2)=$1.0000" in out
