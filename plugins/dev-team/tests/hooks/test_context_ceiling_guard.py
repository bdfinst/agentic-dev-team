"""Unit tests for the Python port of hooks/context-ceiling-guard.sh (#595).

Mirrors tests/hooks/context_ceiling_guard.bats one-for-one via subprocess
dispatch + covers the internal helpers as white-box units. Byte-parity with
the .sh is enforced separately by the parity harness.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


_HOOKS_DIR = Path(__file__).resolve().parents[2] / "hooks"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

import context_ceiling_guard as hook  # type: ignore[import-not-found]  # noqa: E402


_HOOK_PY = _HOOKS_DIR / "context_ceiling_guard.py"


def _write_transcript(path: Path, total: int) -> None:
    """Write a transcript whose latest usage line totals `total` prompt tokens."""
    line = {
        "message": {
            "model": "claude-opus-4-8",
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
    result = _run(_mkinput("Agent", {"subagent_type": "x"}, tr), _base_env(tmp_path))
    assert result.returncode == 0
    assert result.stdout == b""
    assert result.stderr == b""


def test_warns_exit_0_on_agent_load_over_the_ceiling(tmp_path: Path) -> None:
    tr = tmp_path / "t.jsonl"
    _write_transcript(tr, 100_000)  # 50%
    result = _run(
        _mkinput("Agent", {"subagent_type": "dev-team:doc-review"}, tr),
        _base_env(tmp_path),
    )
    assert result.returncode == 0
    assert b"50%" in result.stderr
    assert b"context-summarization" in result.stderr


def test_blocks_exit_2_over_the_ceiling_under_strict_mode(
    tmp_path: Path,
) -> None:
    tr = tmp_path / "t.jsonl"
    _write_transcript(tr, 100_000)
    env = _base_env(tmp_path)
    env["DEV_TEAM_CONTEXT_STRICT"] = "on"
    result = _run(_mkinput("Skill", {"skill": "plan"}, tr), env)
    assert result.returncode == 2
    assert b"blocked" in result.stderr


def test_never_gates_a_recovery_skill_even_strict(tmp_path: Path) -> None:
    tr = tmp_path / "t.jsonl"
    _write_transcript(tr, 180_000)  # 90%
    env = _base_env(tmp_path)
    env["DEV_TEAM_CONTEXT_STRICT"] = "on"
    result = _run(
        _mkinput("Skill", {"skill": "dev-team:context-summarization"}, tr),
        env,
    )
    assert result.returncode == 0
    assert result.stderr == b""


def test_ignores_tools_other_than_agent_or_skill(tmp_path: Path) -> None:
    tr = tmp_path / "t.jsonl"
    _write_transcript(tr, 180_000)
    result = _run(_mkinput("Read", {"file_path": "/x"}, tr), _base_env(tmp_path))
    assert result.returncode == 0
    assert result.stderr == b""


def test_disabled_via_dev_team_context_ceiling_off(tmp_path: Path) -> None:
    tr = tmp_path / "t.jsonl"
    _write_transcript(tr, 180_000)
    env = _base_env(tmp_path)
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
    env["DEV_TEAM_CONTEXT_CEILING_PCT"] = "25"
    result = _run(_mkinput("Agent", {"subagent_type": "x"}, tr), env)
    assert result.returncode == 0
    assert b"30%" in result.stderr


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

    result1 = _run(_mkinput("Agent", {"subagent_type": "x"}, tr), env)
    assert result1.returncode == 0
    assert b"50%" in result1.stderr

    # Same bucket → suppressed.
    result2 = _run(_mkinput("Agent", {"subagent_type": "x"}, tr), env)
    assert result2.returncode == 0
    assert result2.stderr == b""

    # Climb into a higher bucket → fresh warning.
    _write_transcript(tr, 140_000)  # 70% → bucket 14
    result3 = _run(_mkinput("Agent", {"subagent_type": "x"}, tr), env)
    assert result3.returncode == 0
    assert b"70%" in result3.stderr


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
    env["DEV_TEAM_CONTEXT_STRICT"] = "on"
    result = _run(_mkinput("Skill", {"skill": "any-plugin:continue"}, tr), env)
    assert result.returncode == 0


def test_malformed_ceiling_pct_falls_back_to_40(tmp_path: Path) -> None:
    tr = tmp_path / "t.jsonl"
    _write_transcript(tr, 100_000)  # 50%
    env = _base_env(tmp_path)
    env["DEV_TEAM_CONTEXT_CEILING_PCT"] = "not-a-number"
    result = _run(_mkinput("Agent", {"subagent_type": "x"}, tr), env)
    assert result.returncode == 0
    # 50% ≥ 40 (default) → warning fires
    assert b"50%" in result.stderr


def test_malformed_window_falls_back_to_200000(tmp_path: Path) -> None:
    tr = tmp_path / "t.jsonl"
    _write_transcript(tr, 100_000)  # 50% at default 200000
    env = _base_env(tmp_path)
    env["DEV_TEAM_CONTEXT_WINDOW"] = "bogus"
    result = _run(_mkinput("Agent", {"subagent_type": "x"}, tr), env)
    assert result.returncode == 0
    assert b"50%" in result.stderr


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
        ({"skill": "dev-team:context-summarization"}, "context-summarization"),
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
