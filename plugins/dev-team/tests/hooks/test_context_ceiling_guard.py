"""Unit tests for the Python port of hooks/context-ceiling-guard.sh (#595).

Originally mirrored tests/hooks/context_ceiling_guard.bats one-for-one via
subprocess dispatch; the .bats file was retired under the bash-removal epic
(ADR 0015) and this suite is now the sole source of truth.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# Boundary events (#859) are ALWAYS-ON and resolve their metrics/ dir from
# the hook payload's "cwd" (falling back to the process's actual OS cwd when
# absent) — isolate every subprocess run to a scratch dir so tests never
# write metrics/boundary-events.jsonl into the real repo checkout.
_BOUNDARY_EVENTS_SCRATCH_CWD = tempfile.mkdtemp(prefix="dev-team-context-ceiling-test-")


_HOOKS_DIR = Path(__file__).resolve().parents[2] / "hooks"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

import context_ceiling_guard as hook  # type: ignore[import-not-found]

_HOOK_PY = _HOOKS_DIR / "context_ceiling_guard.py"

_PLUGIN_DIR = _HOOKS_DIR.parent
_CONTEXT_SUMMARIZATION_SKILL = (
    _PLUGIN_DIR / "skills" / "handoff" / "SKILL.md"
)
_CONTEXT_LOADING_PROTOCOL_SKILL = (
    _PLUGIN_DIR / "skills" / "context-loading-protocol" / "SKILL.md"
)

# One utilization formula everywhere (#782): the exact same string must
# appear in the hook docstring and both SKILL.md files, so the three can
# never silently drift the way handoff/SKILL.md's old
# `(input + output) / window` once did against the hook's real measurement.
_UTILIZATION_FORMULA = (
    "utilization = (input + cache_read + cache_creation) / model_context_window"
)


def test_utilization_formula_is_identical_across_hook_and_both_skills() -> None:
    hook_text = _HOOK_PY.read_text(encoding="utf-8")
    summarization_text = _CONTEXT_SUMMARIZATION_SKILL.read_text(encoding="utf-8")
    loading_protocol_text = _CONTEXT_LOADING_PROTOCOL_SKILL.read_text(
        encoding="utf-8"
    )
    for label, text in (
        ("hooks/context_ceiling_guard.py", hook_text),
        ("skills/handoff/SKILL.md", summarization_text),
        ("skills/context-loading-protocol/SKILL.md", loading_protocol_text),
    ):
        assert _UTILIZATION_FORMULA in text, (
            f"{label} is missing the canonical utilization formula "
            f"({_UTILIZATION_FORMULA!r})"
        )


def _write_transcript(
    path: Path, total: int, model: str = "claude-haiku-4-5"
) -> None:
    """Write a transcript whose latest usage line totals `total` prompt tokens.

    `model` defaults to a Haiku id (200K window) rather than an unrecognized
    placeholder — fixture re-baseline rule (#779): tests that aren't
    specifically about window-family detection use a real, detectably-200K
    model id AND pin `DEV_TEAM_CONTEXT_WINDOW=200000` explicitly (belt and
    suspenders against a future default-window change); tests that ARE about
    window detection pass an explicit `model=` and never pin the window.
    """
    line = {
        "message": {
            "model": model,
            "usage": {
                "input_tokens": 2,
                "cache_read_input_tokens": total - 2,
                "cache_creation_input_tokens": 0,
            },
        }
    }
    path.write_text(json.dumps(line) + "\n")


def _mkinput(tool_name: str, tool_input: dict, transcript: Path) -> str:
    return json.dumps(
        {
            "tool_name": tool_name,
            "session_id": "s1",
            "transcript_path": str(transcript),
            "tool_input": tool_input,
            "cwd": _BOUNDARY_EVENTS_SCRATCH_CWD,
        }
    )


def _run(stdin: str, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_HOOK_PY)],
        input=stdin.encode("utf-8"),
        capture_output=True,
        env=env,
        check=False,
    )


# ---------------------------------------------------------------------------
# Behavior mirror of the .bats suite (13 cases)
# ---------------------------------------------------------------------------


def _base_env(tmp_path: Path) -> dict:
    """Env with the per-session marker isolated inside `tmp_path`."""
    return {
        "TMPDIR": str(tmp_path),
        "PATH": "/usr/bin:/bin",
    }


def test_silent_below_the_ceiling(tmp_path: Path) -> None:
    tr = tmp_path / "t.jsonl"
    _write_transcript(tr, 50_000)  # 50000/200000 = 25%
    env = _base_env(tmp_path)
    env["DEV_TEAM_CONTEXT_WINDOW"] = "200000"
    result = _run(_mkinput("Agent", {"subagent_type": "x"}, tr), env)
    assert result.returncode == 0
    assert result.stdout == b""
    assert result.stderr == b""


def test_warns_exit_0_on_agent_load_over_the_ceiling(tmp_path: Path) -> None:
    tr = tmp_path / "t.jsonl"
    _write_transcript(tr, 100_000)  # 50%
    env = _base_env(tmp_path)
    env["DEV_TEAM_CONTEXT_WINDOW"] = "200000"
    result = _run(
        _mkinput("Agent", {"subagent_type": "dev-team:doc-review"}, tr),
        env,
    )
    assert result.returncode == 0
    assert b"100000 of 200000 tokens" in result.stderr
    assert b"handoff" in result.stderr


def test_blocks_exit_2_over_the_ceiling_under_strict_mode(
    tmp_path: Path,
) -> None:
    tr = tmp_path / "t.jsonl"
    _write_transcript(tr, 100_000)
    env = _base_env(tmp_path)
    env["DEV_TEAM_CONTEXT_WINDOW"] = "200000"
    env["DEV_TEAM_CONTEXT_STRICT"] = "on"
    result = _run(_mkinput("Skill", {"skill": "plan"}, tr), env)
    assert result.returncode == 2
    assert b"blocked" in result.stderr


def test_never_gates_a_recovery_skill_even_strict(tmp_path: Path) -> None:
    tr = tmp_path / "t.jsonl"
    _write_transcript(tr, 180_000)  # 90%
    env = _base_env(tmp_path)
    env["DEV_TEAM_CONTEXT_WINDOW"] = "200000"
    env["DEV_TEAM_CONTEXT_STRICT"] = "on"
    result = _run(
        _mkinput("Skill", {"skill": "dev-team:handoff"}, tr),
        env,
    )
    assert result.returncode == 0
    assert result.stderr == b""


def test_ignores_tools_other_than_agent_or_skill(tmp_path: Path) -> None:
    tr = tmp_path / "t.jsonl"
    _write_transcript(tr, 180_000)
    env = _base_env(tmp_path)
    env["DEV_TEAM_CONTEXT_WINDOW"] = "200000"
    result = _run(_mkinput("Read", {"file_path": "/x"}, tr), env)
    assert result.returncode == 0
    assert result.stderr == b""


def test_disabled_via_dev_team_context_ceiling_off(tmp_path: Path) -> None:
    tr = tmp_path / "t.jsonl"
    _write_transcript(tr, 180_000)
    env = _base_env(tmp_path)
    env["DEV_TEAM_CONTEXT_WINDOW"] = "200000"
    env["DEV_TEAM_CONTEXT_CEILING"] = "off"
    result = _run(_mkinput("Agent", {"subagent_type": "x"}, tr), env)
    assert result.returncode == 0
    assert result.stderr == b""


def test_context_window_override_changes_the_verdict(tmp_path: Path) -> None:
    tr = tmp_path / "t.jsonl"
    _write_transcript(tr, 100_000)  # 100000/1000000 = 10% with a 1M window
    env = _base_env(tmp_path)
    env["DEV_TEAM_CONTEXT_WINDOW"] = "1000000"
    result = _run(_mkinput("Agent", {"subagent_type": "x"}, tr), env)
    assert result.returncode == 0
    assert result.stderr == b""


def test_context_ceiling_pct_lowers_the_trigger_point(tmp_path: Path) -> None:
    tr = tmp_path / "t.jsonl"
    _write_transcript(tr, 60_000)  # 30%
    env = _base_env(tmp_path)
    env["DEV_TEAM_CONTEXT_WINDOW"] = "200000"
    env["DEV_TEAM_CONTEXT_CEILING_PCT"] = "25"
    result = _run(_mkinput("Agent", {"subagent_type": "x"}, tr), env)
    assert result.returncode == 0
    assert b"60000 of 200000 tokens" in result.stderr
    assert b"ceiling of 50000 tokens" in result.stderr


def test_fail_open_when_the_transcript_is_missing(tmp_path: Path) -> None:
    result = _run(
        json.dumps(
            {
                "tool_name": "Agent",
                "transcript_path": str(tmp_path / "nope.jsonl"),
                "tool_input": {},
            }
        ),
        _base_env(tmp_path),
    )
    assert result.returncode == 0
    assert result.stderr == b""


def test_fail_open_on_malformed_json(tmp_path: Path) -> None:
    result = _run("not json", _base_env(tmp_path))
    assert result.returncode == 0
    assert result.stderr == b""


def test_warn_dedupes_within_5_pt_bucket_rewarns_on_higher(
    tmp_path: Path,
) -> None:
    tr = tmp_path / "t.jsonl"
    _write_transcript(tr, 100_000)  # 50% → bucket 10
    env = _base_env(tmp_path)
    env["DEV_TEAM_CONTEXT_WINDOW"] = "200000"

    result1 = _run(_mkinput("Agent", {"subagent_type": "x"}, tr), env)
    assert result1.returncode == 0
    assert b"100000 of 200000 tokens" in result1.stderr

    # Same bucket → suppressed.
    result2 = _run(_mkinput("Agent", {"subagent_type": "x"}, tr), env)
    assert result2.returncode == 0
    assert result2.stderr == b""

    # Climb into a higher bucket → fresh warning.
    _write_transcript(tr, 140_000)  # 70% → bucket 14
    result3 = _run(_mkinput("Agent", {"subagent_type": "x"}, tr), env)
    assert result3.returncode == 0
    assert b"140000 of 200000 tokens" in result3.stderr


# ---------------------------------------------------------------------------
# Additional coverage the bats suite doesn't hit
# ---------------------------------------------------------------------------


def test_empty_stdin_silent_pass(tmp_path: Path) -> None:
    result = _run("", _base_env(tmp_path))
    assert result.returncode == 0
    assert result.stderr == b""


def test_skill_recovery_stripped_plugin_prefix(tmp_path: Path) -> None:
    """`plugin:continue` should still be recognized as the recovery `continue`."""
    tr = tmp_path / "t.jsonl"
    _write_transcript(tr, 180_000)
    env = _base_env(tmp_path)
    env["DEV_TEAM_CONTEXT_WINDOW"] = "200000"
    env["DEV_TEAM_CONTEXT_STRICT"] = "on"
    result = _run(_mkinput("Skill", {"skill": "any-plugin:continue"}, tr), env)
    assert result.returncode == 0


def test_malformed_ceiling_pct_falls_back_to_40(tmp_path: Path) -> None:
    tr = tmp_path / "t.jsonl"
    _write_transcript(tr, 100_000)  # 50%
    env = _base_env(tmp_path)
    env["DEV_TEAM_CONTEXT_WINDOW"] = "200000"
    env["DEV_TEAM_CONTEXT_CEILING_PCT"] = "not-a-number"
    result = _run(_mkinput("Agent", {"subagent_type": "x"}, tr), env)
    assert result.returncode == 0
    # 100000/200000 = 50% ≥ 40% (default) → warning fires
    assert b"100000 of 200000 tokens" in result.stderr


def test_malformed_window_falls_back_to_200000(tmp_path: Path) -> None:
    tr = tmp_path / "t.jsonl"
    _write_transcript(tr, 100_000)  # 50% at default 200000
    env = _base_env(tmp_path)
    env["DEV_TEAM_CONTEXT_WINDOW"] = "bogus"
    result = _run(_mkinput("Agent", {"subagent_type": "x"}, tr), env)
    assert result.returncode == 0
    assert b"100000 of 200000 tokens" in result.stderr


# ---------------------------------------------------------------------------
# Helper coverage (white-box)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,default,expected",
    [
        ("42", 40, 42),
        ("0", 40, 40),  # zero → default
        ("-5", 40, 40),  # regex rejects '-'
        ("abc", 40, 40),
        ("", 40, 40),
        (None, 40, 40),
    ],
)
def test_positive_int_env(monkeypatch, value, default, expected):
    if value is None:
        monkeypatch.delenv("X_TEST_VAR", raising=False)
    else:
        monkeypatch.setenv("X_TEST_VAR", value)
    assert hook._positive_int_env("X_TEST_VAR", default) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("abc", "abc"),
        ("s-1_A", "s-1_A"),
        ("a b c", "abc"),
        ("../weird", "weird"),
        ("", "nosession"),
        ("!!!", "nosession"),
    ],
)
def test_sanitize_session(raw: str, expected: str) -> None:
    assert hook._sanitize_session(raw) == expected


@pytest.mark.parametrize(
    "tool_input,expected",
    [
        ({"skill": "plan"}, "plan"),
        ({"skill": "dev-team:handoff"}, "handoff"),
        ({"name": "plan"}, "plan"),
        ({"name": "foo:bar:baz"}, "baz"),
        ({}, ""),
    ],
)
def test_extract_skill_name(tool_input: dict, expected: str) -> None:
    assert hook._extract_skill_name(tool_input) == expected


def test_measure_occupancy_ignores_lines_without_usage(tmp_path: Path) -> None:
    tr = tmp_path / "t.jsonl"
    tr.write_text(
        json.dumps({"message": {"model": "x"}})
        + "\n"
        + json.dumps(
            {
                "message": {
                    "usage": {
                        "input_tokens": 100,
                        "cache_read_input_tokens": 50,
                        "cache_creation_input_tokens": 25,
                    }
                }
            }
        )
        + "\n"
    )
    assert hook._measure_occupancy(tr) == 175


def test_measure_occupancy_returns_none_on_no_usage(tmp_path: Path) -> None:
    tr = tmp_path / "t.jsonl"
    tr.write_text(json.dumps({"message": {"model": "x"}}) + "\n")
    assert hook._measure_occupancy(tr) is None


def test_measure_occupancy_uses_last_usage_line_only(tmp_path: Path) -> None:
    """The .sh does `| tail -n 1` — only the most recent usage counts."""
    tr = tmp_path / "t.jsonl"
    tr.write_text(
        json.dumps({"message": {"usage": {"input_tokens": 1_000_000}}})
        + "\n"
        + json.dumps(
            {
                "message": {
                    "usage": {
                        "input_tokens": 5,
                        "cache_read_input_tokens": 10,
                        "cache_creation_input_tokens": 0,
                    }
                }
            }
        )
        + "\n"
    )
    assert hook._measure_occupancy(tr) == 15


def test_measure_occupancy_missing_file(tmp_path: Path) -> None:
    assert hook._measure_occupancy(tmp_path / "nope.jsonl") is None


# ---------------------------------------------------------------------------
# Pinned message contract + absolute-ceiling bound framing (#780)
# ---------------------------------------------------------------------------


def test_resolve_bound_percentage_when_pct_threshold_is_smaller_or_equal():
    assert hook._resolve_bound(80_000, 150_000) == "percentage"
    assert hook._resolve_bound(150_000, 150_000) == "percentage"  # tie


def test_resolve_bound_absolute_when_abs_ceiling_is_smaller():
    assert hook._resolve_bound(400_000, 150_000) == "absolute"


def test_format_message_matches_the_pinned_contract():
    msg = hook._format_message(
        100_000, 200_000, 80_000, "percentage", "detected", "loading agent 'x'"
    )
    assert (
        "🪟 Context at 100000 of 200000 tokens — over the effective "
        "ceiling of 80000 tokens (percentage bound; window detected)" in msg
    )


def test_format_message_bound_framings_never_co_occur():
    pct_msg = hook._format_message(
        100_000, 200_000, 80_000, "percentage", "override", "x"
    )
    assert "percentage bound" in pct_msg
    assert "absolute bound" not in pct_msg

    abs_msg = hook._format_message(
        200_000, 1_000_000, 150_000, "absolute", "detected", "x"
    )
    assert "absolute bound" in abs_msg
    assert "percentage bound" not in abs_msg


@pytest.mark.parametrize("provenance", ["override", "detected", "default"])
def test_format_message_names_window_provenance(provenance: str) -> None:
    msg = hook._format_message(100_000, 200_000, 80_000, "percentage", provenance, "x")
    assert f"window {provenance}" in msg


# ---------------------------------------------------------------------------
# #785: context window auto-detection from transcript model
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "model,expected",
    [
        ("claude-haiku-4-5", 200_000),
        ("claude-3-5-haiku-20241022", 200_000),
        ("claude-opus-4-8", 1_000_000),
        ("claude-opus-4-7", 1_000_000),
        ("claude-opus-4-6", 1_000_000),
        ("claude-opus-5", 1_000_000),
        ("claude-sonnet-5", 1_000_000),
        ("claude-sonnet-4-6", 1_000_000),
        ("claude-fable-5", 1_000_000),
        ("claude-fable-1", 1_000_000),
        ("claude-mythos-1", 1_000_000),
        ("some-unrecognized-model", 200_000),
        # Window is a fixed per-model property, not a family-wide one: a
        # same-family model outside the pinned 1M versions must NOT be
        # assumed 1M (#779) — these fall to the 200K conservative default.
        ("claude-opus-4-5", 200_000),
        ("claude-3-opus-20240229", 200_000),
        ("claude-sonnet-4-5", 200_000),
        ("claude-3-5-sonnet-20241022", 200_000),
    ],
)
def test_window_for_model(model: str, expected: int) -> None:
    assert hook._window_for_model(model) == expected


@pytest.mark.parametrize(
    "model,expected_pct_denominator",
    [
        ("claude-haiku-4-5", 200_000),
        ("claude-3-5-haiku-20241022", 200_000),
        ("claude-opus-4-8", 1_000_000),
        ("claude-opus-4-7", 1_000_000),
        ("claude-opus-4-6", 1_000_000),
        ("claude-opus-5", 1_000_000),
        ("claude-sonnet-5", 1_000_000),
        ("claude-sonnet-4-6", 1_000_000),
        ("claude-fable-5", 1_000_000),
        ("claude-mythos-1", 1_000_000),
        # Same-family, non-pinned versions must NOT auto-detect as 1M.
        ("claude-opus-4-5", 200_000),
        ("claude-sonnet-4-5", 200_000),
    ],
)
def test_detects_window_per_model_family_end_to_end(
    tmp_path: Path, model: str, expected_pct_denominator: int
) -> None:
    """100_000 occupancy tokens against each family's detected window."""
    tr = tmp_path / "t.jsonl"
    _write_transcript(tr, 100_000, model=model)
    result = _run(_mkinput("Agent", {"subagent_type": "x"}, tr), _base_env(tmp_path))
    assert result.returncode == 0
    expected_pct = (100_000 * 100) // expected_pct_denominator
    if expected_pct >= 40:
        assert f"100000 of {expected_pct_denominator} tokens".encode() in result.stderr
    else:
        assert result.stderr == b""


def test_env_override_wins_over_detection(tmp_path: Path) -> None:
    """An Opus transcript would auto-detect to 1M (10%, below ceiling); the
    explicit override forces 200K (50%, over ceiling) and the override wins.
    """
    tr = tmp_path / "t.jsonl"
    _write_transcript(tr, 100_000, model="claude-opus-4-8")
    env = _base_env(tmp_path)
    env["DEV_TEAM_CONTEXT_WINDOW"] = "200000"
    result = _run(_mkinput("Agent", {"subagent_type": "x"}, tr), env)
    assert result.returncode == 0
    assert b"100000 of 200000 tokens" in result.stderr
    assert b"window override" in result.stderr


def test_unrecognized_model_falls_back_to_200000(tmp_path: Path) -> None:
    tr = tmp_path / "t.jsonl"
    _write_transcript(tr, 100_000, model="gpt-5-turbo")  # unrecognized family
    result = _run(_mkinput("Agent", {"subagent_type": "x"}, tr), _base_env(tmp_path))
    assert result.returncode == 0
    assert b"100000 of 200000 tokens" in result.stderr  # 100000/200000 default
    assert b"window default" in result.stderr


def test_detect_window_fail_open_on_missing_model_field(tmp_path: Path) -> None:
    tr = tmp_path / "t.jsonl"
    tr.write_text(
        json.dumps(
            {
                "message": {
                    "usage": {
                        "input_tokens": 2,
                        "cache_read_input_tokens": 99_998,
                        "cache_creation_input_tokens": 0,
                    }
                }
            }
        )
        + "\n"
    )
    assert hook._detect_window(tr) == (200_000, False)
    result = _run(
        _mkinput("Agent", {"subagent_type": "x"}, tr), _base_env(tmp_path)
    )
    assert result.returncode == 0
    assert b"100000 of 200000 tokens" in result.stderr
    assert b"window default" in result.stderr


def test_detect_window_fail_open_on_malformed_transcript(tmp_path: Path) -> None:
    tr = tmp_path / "t.jsonl"
    tr.write_text("not json at all\n")
    assert hook._detect_window(tr) == (200_000, False)


def test_detect_window_fail_open_on_missing_transcript(tmp_path: Path) -> None:
    assert hook._detect_window(tmp_path / "nope.jsonl") == (200_000, False)


def test_detect_window_fail_open_on_non_string_model(tmp_path: Path) -> None:
    tr = tmp_path / "t.jsonl"
    tr.write_text(json.dumps({"message": {"model": 12345}}) + "\n")
    assert hook._detect_window(tr) == (200_000, False)


def test_env_window_override_none_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("DEV_TEAM_CONTEXT_WINDOW", raising=False)
    assert hook._env_window_override() is None


def test_env_window_override_none_when_malformed(monkeypatch) -> None:
    monkeypatch.setenv("DEV_TEAM_CONTEXT_WINDOW", "bogus")
    assert hook._env_window_override() is None


def test_env_window_override_none_when_zero_or_negative(monkeypatch) -> None:
    monkeypatch.setenv("DEV_TEAM_CONTEXT_WINDOW", "0")
    assert hook._env_window_override() is None


def test_env_window_override_returns_explicit_value(monkeypatch) -> None:
    monkeypatch.setenv("DEV_TEAM_CONTEXT_WINDOW", "1000000")
    assert hook._env_window_override() == 1_000_000


# ---------------------------------------------------------------------------
# Absolute-token cap (#786)
# ---------------------------------------------------------------------------


def test_absolute_cap_fires_at_150k_on_a_1m_window(tmp_path: Path) -> None:
    """On a 1M window, 40% would be 400K — but the 150K absolute cap binds
    first, so occupancy at 150K (well under the 40% pct threshold) must
    still trigger the warning."""
    tr = tmp_path / "t.jsonl"
    _write_transcript(tr, 150_000)  # 15% of 1M — far below the 40% pct ceiling
    env = _base_env(tmp_path)
    env["DEV_TEAM_CONTEXT_WINDOW"] = "1000000"
    result = _run(_mkinput("Agent", {"subagent_type": "x"}, tr), env)
    assert result.returncode == 0
    assert b"150000 of 1000000 tokens" in result.stderr
    assert b"ceiling of 150000 tokens" in result.stderr
    assert b"absolute bound" in result.stderr
    assert b"percentage bound" not in result.stderr


def test_absolute_cap_does_not_fire_just_under_150k_on_a_1m_window(
    tmp_path: Path,
) -> None:
    tr = tmp_path / "t.jsonl"
    _write_transcript(tr, 149_999)
    env = _base_env(tmp_path)
    env["DEV_TEAM_CONTEXT_WINDOW"] = "1000000"
    result = _run(_mkinput("Agent", {"subagent_type": "x"}, tr), env)
    assert result.returncode == 0
    assert result.stderr == b""


def test_absolute_cap_is_a_noop_on_a_200k_window(tmp_path: Path) -> None:
    """40% of 200K = 80K, well under the 150K default cap — behavior must be
    identical to before the cap was introduced: unaffected right up to 80K,
    and firing at 80K exactly as it always did."""
    tr = tmp_path / "t.jsonl"
    _write_transcript(tr, 79_999)  # just under the 40% pct threshold
    env = _base_env(tmp_path)
    env["DEV_TEAM_CONTEXT_WINDOW"] = "200000"
    result = _run(_mkinput("Agent", {"subagent_type": "x"}, tr), env)
    assert result.returncode == 0
    assert result.stderr == b""

    tr2 = tmp_path / "t2.jsonl"
    _write_transcript(tr2, 80_000)  # exactly the 40% pct threshold
    env2 = _base_env(tmp_path)
    env2["DEV_TEAM_CONTEXT_WINDOW"] = "200000"
    result2 = _run(_mkinput("Agent", {"subagent_type": "y"}, tr2), env2)
    assert result2.returncode == 0
    assert b"80000 of 200000 tokens" in result2.stderr
    assert b"percentage bound" in result2.stderr


def test_dev_team_context_abs_ceiling_override_wins_over_default(
    tmp_path: Path,
) -> None:
    """A custom DEV_TEAM_CONTEXT_ABS_CEILING replaces the 150K default cap."""
    tr = tmp_path / "t.jsonl"
    _write_transcript(tr, 50_000)  # 5% of 1M — under both the pct ceiling
    # and the default 150K abs cap, but over a custom 40K abs cap.
    env = _base_env(tmp_path)
    env["DEV_TEAM_CONTEXT_WINDOW"] = "1000000"
    env["DEV_TEAM_CONTEXT_ABS_CEILING"] = "40000"
    result = _run(_mkinput("Agent", {"subagent_type": "x"}, tr), env)
    assert result.returncode == 0
    assert result.stderr != b""


def test_dev_team_context_abs_ceiling_override_can_raise_the_cap(
    tmp_path: Path,
) -> None:
    """Raising the abs cap above the pct threshold makes the pct ceiling
    binding again (min() picks the smaller of the two)."""
    tr = tmp_path / "t.jsonl"
    _write_transcript(tr, 200_000)  # 20% of 1M — under the pct ceiling (40%)
    env = _base_env(tmp_path)
    env["DEV_TEAM_CONTEXT_WINDOW"] = "1000000"
    env["DEV_TEAM_CONTEXT_ABS_CEILING"] = "1000000"  # cap raised out of the way
    result = _run(_mkinput("Agent", {"subagent_type": "x"}, tr), env)
    assert result.returncode == 0
    assert result.stderr == b""


def test_malformed_abs_ceiling_falls_back_to_150000(tmp_path: Path) -> None:
    tr = tmp_path / "t.jsonl"
    _write_transcript(tr, 150_000)  # over the 150K default cap on a 1M window
    env = _base_env(tmp_path)
    env["DEV_TEAM_CONTEXT_WINDOW"] = "1000000"
    env["DEV_TEAM_CONTEXT_ABS_CEILING"] = "not-a-number"
    result = _run(_mkinput("Agent", {"subagent_type": "x"}, tr), env)
    assert result.returncode == 0
    assert result.stderr != b""


def test_absolute_cap_fail_open_when_transcript_missing(tmp_path: Path) -> None:
    """Measurement failure still fails open even with a tiny abs cap that
    would otherwise fire immediately."""
    env = _base_env(tmp_path)
    env["DEV_TEAM_CONTEXT_WINDOW"] = "1000000"
    env["DEV_TEAM_CONTEXT_ABS_CEILING"] = "1"
    result = _run(
        json.dumps(
            {
                "tool_name": "Agent",
                "transcript_path": str(tmp_path / "nope.jsonl"),
                "tool_input": {},
            }
        ),
        env,
    )
    assert result.returncode == 0
    assert result.stderr == b""


# ---------------------------------------------------------------------------
# Graduated bands keyed to multiples of the effective ceiling (#781)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "occ,threshold_tokens,expected_band",
    [
        (150_000, 150_000, hook._BAND_NUDGE),  # exactly 1x
        (187_499, 150_000, hook._BAND_NUDGE),  # just under 1.25x
        (187_500, 150_000, hook._BAND_RUN_NOW),  # exactly 1.25x
        (224_999, 150_000, hook._BAND_RUN_NOW),  # just under 1.5x
        (225_000, 150_000, hook._BAND_FULL_SUMMARY),  # exactly 1.5x
        (500_000, 150_000, hook._BAND_FULL_SUMMARY),  # well past 1.5x
    ],
)
def test_band_for_threshold_multiple(
    occ: int, threshold_tokens: int, expected_band: int
) -> None:
    assert hook._band_for_threshold_multiple(occ, threshold_tokens) == expected_band


def test_format_message_nudge_band_leads_with_diagnostic_and_keeps_footer():
    msg = hook._format_message(150_000, 1_000_000, 150_000, "absolute", "detected", "x")
    assert msg.startswith("🪟 Context at")
    assert "[nudge]" in msg
    assert "Tune with DEV_TEAM_CONTEXT_WINDOW" in msg


def test_format_message_run_now_band_leads_with_diagnostic_and_keeps_footer():
    msg = hook._format_message(190_000, 1_000_000, 150_000, "absolute", "detected", "x")
    assert msg.startswith("🪟 Context at")
    assert "[run-now]" in msg
    assert "Run /handoff now" in msg
    assert "Tune with DEV_TEAM_CONTEXT_WINDOW" in msg


def test_format_message_full_summary_band_leads_with_directive_no_footer():
    """Top band (#781): leads with the directive (before the diagnostic
    line) and drops the knob footer entirely."""
    msg = hook._format_message(226_000, 1_000_000, 150_000, "absolute", "detected", "x")
    assert msg.startswith("[full-summary]")
    directive_idx = msg.index("Write a full summary to memory/")
    diagnostic_idx = msg.index("🪟 Context at")
    assert directive_idx < diagnostic_idx
    assert "Tune with DEV_TEAM_CONTEXT_WINDOW" not in msg


def test_dedupe_rekeyed_on_band_identity_worked_1m_case(tmp_path: Path) -> None:
    """Worked case from #781: on a 1M window with the 150K absolute cap
    binding, band escalations always break through the coarser
    5%-of-window pct_bucket — fires at 150000 (band 0), re-fires at 190000
    (band 1, even though pct_bucket is unchanged), and again at 226000
    (band 2)."""
    tr = tmp_path / "t.jsonl"
    env = _base_env(tmp_path)
    env["DEV_TEAM_CONTEXT_WINDOW"] = "1000000"

    _write_transcript(tr, 150_000)  # band 0 (nudge)
    result = _run(_mkinput("Agent", {"subagent_type": "x"}, tr), env)
    assert result.returncode == 0
    assert b"[nudge]" in result.stderr

    # Same band, pct_bucket unchanged (15% -> still bucket 3) -> suppressed.
    result = _run(_mkinput("Agent", {"subagent_type": "x"}, tr), env)
    assert result.returncode == 0
    assert result.stderr == b""

    _write_transcript(tr, 190_000)  # band 1 (run-now) — pct_bucket still 3
    result = _run(_mkinput("Agent", {"subagent_type": "x"}, tr), env)
    assert result.returncode == 0
    assert b"[run-now]" in result.stderr

    _write_transcript(tr, 226_000)  # band 2 (full-summary)
    result = _run(_mkinput("Agent", {"subagent_type": "x"}, tr), env)
    assert result.returncode == 0
    assert b"[full-summary]" in result.stderr


# ---------------------------------------------------------------------------
# #1354 mutant-kill pass: exact-value assertions on the band action strings,
# _build_label, the transcript-scan skip branches, and helper edges. Substring
# `in` checks passed even against XX-wrapped string mutants (the original text
# stays a substring), so these assert the FULL concatenated strings and that
# no XX marker leaks — plus direct-call coverage of the helpers.
# ---------------------------------------------------------------------------


_NUDGE_ACTION = (
    "Consider running /handoff (write a memory/ progress file, continue in a "
    "fresh context) and defer non-essential agents/skills."
)
_RUN_NOW_ACTION = (
    "Run /handoff now — write a memory/ progress file and continue in a "
    "fresh context."
)
_FULL_SUMMARY_ACTION = (
    "Write a full summary to memory/ and start a new conversation now — "
    "context is well past the effective ceiling."
)
_KNOB_FOOTER = (
    "Tune with DEV_TEAM_CONTEXT_WINDOW (overrides auto-detection) / "
    "DEV_TEAM_CONTEXT_CEILING_PCT / DEV_TEAM_CONTEXT_ABS_CEILING;\n"
    "DEV_TEAM_CONTEXT_STRICT=on hard-blocks; "
    "DEV_TEAM_CONTEXT_CEILING=off disables."
)


def test_format_message_nudge_action_and_footer_are_exact() -> None:
    msg = hook._format_message(
        150_000, 1_000_000, 150_000, "absolute", "detected", "x"
    )
    assert _NUDGE_ACTION in msg
    assert _KNOB_FOOTER in msg
    assert "XX" not in msg


def test_format_message_run_now_action_and_footer_are_exact() -> None:
    msg = hook._format_message(
        190_000, 1_000_000, 150_000, "absolute", "detected", "x"
    )
    assert _RUN_NOW_ACTION in msg
    assert _KNOB_FOOTER in msg
    assert "XX" not in msg


def test_format_message_full_summary_action_is_exact_no_footer() -> None:
    msg = hook._format_message(
        226_000, 1_000_000, 150_000, "absolute", "detected", "x"
    )
    assert _FULL_SUMMARY_ACTION in msg
    assert _KNOB_FOOTER not in msg
    assert "XX" not in msg


# --- _build_label: exact labels for Skill and Agent branches ---


def test_build_label_skill_uses_skill_key_verbatim() -> None:
    assert hook._build_label("Skill", {"skill": "plan"}) == "invoking skill 'plan'"


def test_build_label_skill_falls_back_to_name_key() -> None:
    assert hook._build_label("Skill", {"name": "foo"}) == "invoking skill 'foo'"


def test_build_label_skill_missing_both_is_question_mark() -> None:
    assert hook._build_label("Skill", {}) == "invoking skill '?'"


def test_build_label_skill_non_string_value_is_question_mark() -> None:
    assert hook._build_label("Skill", {"skill": 123}) == "invoking skill '?'"


def test_build_label_agent_uses_subagent_type_verbatim() -> None:
    assert (
        hook._build_label("Agent", {"subagent_type": "dev-team:doc-review"})
        == "loading agent 'dev-team:doc-review'"
    )


def test_build_label_agent_missing_is_question_mark() -> None:
    assert hook._build_label("Agent", {}) == "loading agent '?'"


def test_build_label_agent_non_string_value_is_question_mark() -> None:
    assert hook._build_label("Agent", {"subagent_type": 5}) == "loading agent '?'"


# --- _measure_occupancy: skip-branch and `or 0` / `> 0` boundary edges ---


def _usage_line(**usage: object) -> str:
    return json.dumps({"message": {"usage": usage}})


def test_measure_occupancy_skips_blank_line_before_usage(tmp_path: Path) -> None:
    tr = tmp_path / "t.jsonl"
    tr.write_text("\n" + _usage_line(input_tokens=7, cache_read_input_tokens=3) + "\n")
    assert hook._measure_occupancy(tr) == 10


def test_measure_occupancy_skips_non_json_line_before_usage(tmp_path: Path) -> None:
    tr = tmp_path / "t.jsonl"
    tr.write_text("not json\n" + _usage_line(input_tokens=8) + "\n")
    assert hook._measure_occupancy(tr) == 8


def test_measure_occupancy_skips_non_dict_row_before_usage(tmp_path: Path) -> None:
    tr = tmp_path / "t.jsonl"
    tr.write_text("[]\n" + _usage_line(input_tokens=9) + "\n")
    assert hook._measure_occupancy(tr) == 9


def test_measure_occupancy_skips_non_dict_message_before_usage(
    tmp_path: Path,
) -> None:
    tr = tmp_path / "t.jsonl"
    tr.write_text(
        json.dumps({"message": 123}) + "\n" + _usage_line(input_tokens=11) + "\n"
    )
    assert hook._measure_occupancy(tr) == 11


def test_measure_occupancy_skips_non_int_usage_before_valid(tmp_path: Path) -> None:
    tr = tmp_path / "t.jsonl"
    tr.write_text(
        _usage_line(input_tokens="oops")
        + "\n"
        + _usage_line(input_tokens=13)
        + "\n"
    )
    assert hook._measure_occupancy(tr) == 13


def test_measure_occupancy_absent_input_tokens_counts_as_zero(tmp_path: Path) -> None:
    tr = tmp_path / "t.jsonl"
    tr.write_text(_usage_line(cache_read_input_tokens=100) + "\n")
    assert hook._measure_occupancy(tr) == 100


def test_measure_occupancy_absent_cache_read_counts_as_zero(tmp_path: Path) -> None:
    tr = tmp_path / "t.jsonl"
    tr.write_text(_usage_line(input_tokens=100) + "\n")
    assert hook._measure_occupancy(tr) == 100


def test_measure_occupancy_all_zero_total_is_none(tmp_path: Path) -> None:
    tr = tmp_path / "t.jsonl"
    tr.write_text(
        _usage_line(
            input_tokens=0, cache_read_input_tokens=0, cache_creation_input_tokens=0
        )
        + "\n"
    )
    assert hook._measure_occupancy(tr) is None


def test_measure_occupancy_total_of_one_is_returned(tmp_path: Path) -> None:
    tr = tmp_path / "t.jsonl"
    tr.write_text(_usage_line(input_tokens=1) + "\n")
    assert hook._measure_occupancy(tr) == 1


# --- _detect_window: matched flag and skip branches ---


def test_detect_window_returns_true_for_haiku_model(tmp_path: Path) -> None:
    tr = tmp_path / "t.jsonl"
    _write_transcript(tr, 100_000, model="claude-haiku-4-5")
    assert hook._detect_window(tr) == (200_000, True)


def test_detect_window_returns_true_for_large_window_model(tmp_path: Path) -> None:
    tr = tmp_path / "t.jsonl"
    _write_transcript(tr, 100_000, model="claude-opus-4-8")
    assert hook._detect_window(tr) == (1_000_000, True)


def _model_line(model: str) -> str:
    return json.dumps({"message": {"model": model}})


def test_detect_window_skips_blank_line_before_model(tmp_path: Path) -> None:
    tr = tmp_path / "t.jsonl"
    tr.write_text("\n" + _model_line("claude-opus-4-8") + "\n")
    assert hook._detect_window(tr) == (1_000_000, True)


def test_detect_window_skips_non_json_line_before_model(tmp_path: Path) -> None:
    tr = tmp_path / "t.jsonl"
    tr.write_text("not json\n" + _model_line("claude-opus-4-8") + "\n")
    assert hook._detect_window(tr) == (1_000_000, True)


def test_detect_window_skips_non_dict_row_before_model(tmp_path: Path) -> None:
    tr = tmp_path / "t.jsonl"
    tr.write_text("[]\n" + _model_line("claude-opus-4-8") + "\n")
    assert hook._detect_window(tr) == (1_000_000, True)


def test_detect_window_skips_non_dict_message_before_model(tmp_path: Path) -> None:
    tr = tmp_path / "t.jsonl"
    tr.write_text(
        json.dumps({"message": 5}) + "\n" + _model_line("claude-opus-4-8") + "\n"
    )
    assert hook._detect_window(tr) == (1_000_000, True)


def test_resolve_window_provenance_is_detected_string(tmp_path: Path) -> None:
    tr = tmp_path / "t.jsonl"
    _write_transcript(tr, 100_000, model="claude-haiku-4-5")
    assert hook._resolve_window(tr) == (200_000, "detected")


# --- small helper boundaries ---


def test_positive_int_env_value_one_is_kept(monkeypatch) -> None:
    monkeypatch.setenv("X_TEST_ONE", "1")
    assert hook._positive_int_env("X_TEST_ONE", 40) == 1


def test_env_window_override_value_one_is_kept(monkeypatch) -> None:
    monkeypatch.setenv("DEV_TEAM_CONTEXT_WINDOW", "1")
    assert hook._env_window_override() == 1


def test_extract_skill_name_non_string_is_empty() -> None:
    assert hook._extract_skill_name({"skill": 123}) == ""


def test_marker_path_uses_tmpdir_and_session_filename(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    marker = hook._marker_path("s1")
    assert marker.parent == tmp_path
    assert marker.name == "dev-team-ctx-ceiling-s1.last"


def test_read_last_bucket_missing_file_is_zero(tmp_path: Path) -> None:
    assert hook._read_last_bucket(tmp_path / "nope.last") == 0


def test_read_last_bucket_non_numeric_is_zero(tmp_path: Path) -> None:
    marker = tmp_path / "m.last"
    marker.write_text("abc")
    assert hook._read_last_bucket(marker) == 0


def test_read_last_bucket_numeric_is_parsed(tmp_path: Path) -> None:
    marker = tmp_path / "m.last"
    marker.write_text("5")
    assert hook._read_last_bucket(marker) == 5


def test_band_threshold_zero_is_nudge() -> None:
    # threshold_tokens <= 0 short-circuits to NUDGE before the 1.5x/1.25x math.
    assert hook._band_for_threshold_multiple(100, 0) == hook._BAND_NUDGE


def test_band_threshold_one_reaches_full_summary() -> None:
    # threshold 1: 1*3//2 == 1, occ 100 >= 1 -> full-summary (not nudge).
    assert (
        hook._band_for_threshold_multiple(100, 1) == hook._BAND_FULL_SUMMARY
    )


# --- gated-tool and recovery-skill membership (frozenset string mutants) ---


def test_task_tool_is_gated_like_agent(tmp_path: Path) -> None:
    tr = tmp_path / "t.jsonl"
    _write_transcript(tr, 100_000)
    env = _base_env(tmp_path)
    env["DEV_TEAM_CONTEXT_WINDOW"] = "200000"
    result = _run(_mkinput("Task", {"subagent_type": "x"}, tr), env)
    assert result.returncode == 0
    assert b"100000 of 200000 tokens" in result.stderr


@pytest.mark.parametrize(
    "skill", ["context-loading-protocol", "review-summary", "session-review"]
)
def test_recovery_skills_are_never_gated_even_strict(
    tmp_path: Path, skill: str
) -> None:
    tr = tmp_path / "t.jsonl"
    _write_transcript(tr, 180_000)
    env = _base_env(tmp_path)
    env["DEV_TEAM_CONTEXT_WINDOW"] = "200000"
    env["DEV_TEAM_CONTEXT_STRICT"] = "on"
    result = _run(_mkinput("Skill", {"skill": skill}, tr), env)
    assert result.returncode == 0
    assert result.stderr == b""


# --- _resolve_verdict / main fail-open paths ---


def test_non_dict_tool_input_is_coerced_not_crashed(tmp_path: Path) -> None:
    """A non-dict tool_input must be coerced to {} — the mutant that sets it
    to None would crash in _build_label. Over-ceiling Agent must still warn."""
    tr = tmp_path / "t.jsonl"
    _write_transcript(tr, 100_000)
    env = _base_env(tmp_path)
    env["DEV_TEAM_CONTEXT_WINDOW"] = "200000"
    stdin = json.dumps(
        {
            "tool_name": "Agent",
            "session_id": "s1",
            "transcript_path": str(tr),
            "tool_input": ["not", "a", "dict"],
            "cwd": _BOUNDARY_EVENTS_SCRATCH_CWD,
        }
    )
    result = _run(stdin, env)
    assert result.returncode == 0
    assert b"100000 of 200000 tokens" in result.stderr


def test_missing_transcript_path_key_fails_open_exit_zero(tmp_path: Path) -> None:
    env = _base_env(tmp_path)
    env["DEV_TEAM_CONTEXT_WINDOW"] = "200000"
    stdin = json.dumps({"tool_name": "Agent", "tool_input": {"subagent_type": "x"}})
    result = _run(stdin, env)
    assert result.returncode == 0
    assert result.stderr == b""


def test_transcript_present_but_no_usage_fails_open_exit_zero(tmp_path: Path) -> None:
    tr = tmp_path / "t.jsonl"
    tr.write_text(_model_line("claude-haiku-4-5") + "\n")  # model, but no usage
    env = _base_env(tmp_path)
    env["DEV_TEAM_CONTEXT_WINDOW"] = "200000"
    result = _run(_mkinput("Agent", {"subagent_type": "x"}, tr), env)
    assert result.returncode == 0
    assert result.stderr == b""


def test_warn_stderr_has_no_leaked_mutation_marker(tmp_path: Path) -> None:
    """Guards the `message + "\\n"` write and any format-string mutant that
    would inject an `XX` marker into the emitted stderr."""
    tr = tmp_path / "t.jsonl"
    _write_transcript(tr, 100_000)
    env = _base_env(tmp_path)
    env["DEV_TEAM_CONTEXT_WINDOW"] = "200000"
    result = _run(_mkinput("Agent", {"subagent_type": "x"}, tr), env)
    assert result.returncode == 0
    assert b"XX" not in result.stderr
    assert result.stderr.endswith(b"\n")
