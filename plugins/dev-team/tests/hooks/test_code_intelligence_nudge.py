"""Unit tests for hooks/code_intelligence_nudge.py (#593, #1368).

Mirror of tests/hooks/codegraph_nudge.bats (parallel and turn-mark hook
tests). The mark hook stays out-of-scope for this slice — only the nudge
hook is being ported/generalized here.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[4]
_HOOK = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "code_intelligence_nudge.py"
_CAREFUL_STATE = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "careful-state.json"

# Load the hook module by explicit file path so unit tests can exercise its
# internal helpers (e.g. _detect_present_tools) directly, without spawning a
# subprocess per assertion — see test_cost_meter_lib.py (#1120) for the same
# precedent/rationale.
_spec = importlib.util.spec_from_file_location("code_intelligence_nudge_lib", _HOOK)
assert _spec is not None and _spec.loader is not None
code_intelligence_nudge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(code_intelligence_nudge)

# Derived from the same composer main() calls, so this constant tracks
# wording changes to CUES/_compose_message automatically — these tests are
# about main()'s wiring (detection -> sentinel -> composition -> print/exit),
# not about the exact prose, which is covered by test_single_tool_message_per_tool.
EXPECTED_WARN_MSG = code_intelligence_nudge._compose_message(["codegraph"])


@pytest.fixture(autouse=True)
def clean_careful_state():
    """Wipe careful-state.json before AND after every test. A leaked file
    silently flips the hook into block mode and corrupts every warn-path
    assertion."""
    _CAREFUL_STATE.unlink(missing_ok=True)
    yield
    _CAREFUL_STATE.unlink(missing_ok=True)


def _run(payload: dict, extra_env: dict = None) -> subprocess.CompletedProcess[str]:
    proc_env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        "PYTHONDONTWRITEBYTECODE": "1",
        **(extra_env or {}),
    }
    return subprocess.run(
        ["python3", str(_HOOK)],
        input=json.dumps(payload),
        env=proc_env,
        capture_output=True,
        text=True,
        check=False,
    )


def _write_transcript(path: Path, user_count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f'{{"type":"user","message":"u{i}"}}' for i in range(user_count)]
    path.write_text("\n".join(lines) + ("\n" if lines else ""))


# --- Step 1: silent when .codegraph is absent -----------------------------


def test_silent_when_codegraph_absent(tmp_path: Path) -> None:
    r = _run(
        {
            "tool_name": "Read",
            "cwd": str(tmp_path),
            "tool_input": {"file_path": str(tmp_path / "foo.txt")},
        }
    )
    assert r.returncode == 0
    assert r.stdout == ""
    assert r.stderr == ""


# --- Step 2: Read is always single-file → silent --------------------------


def test_silent_on_read_when_codegraph_present(tmp_path: Path) -> None:
    (tmp_path / ".codegraph").mkdir()
    (tmp_path / "foo.txt").write_text("hi")
    r = _run(
        {
            "tool_name": "Read",
            "cwd": str(tmp_path),
            "tool_input": {"file_path": str(tmp_path / "foo.txt")},
        }
    )
    assert r.returncode == 0
    assert r.stdout == ""
    assert r.stderr == ""


# --- Step 3: Grep/Glob heuristic -----------------------------------------


def test_codegraph_only_regression(tmp_path: Path) -> None:
    """Only .codegraph/ present -> the pre-Step-1.3 single-tool CodeGraph
    nudge still fires, naming codegraph_explore with its differentiator
    clause, and mentions neither Repowise nor Graphify."""
    (tmp_path / ".codegraph").mkdir()
    (tmp_path / "src").mkdir()
    r = _run(
        {
            "tool_name": "Grep",
            "cwd": str(tmp_path),
            "tool_input": {"pattern": "foo", "path": str(tmp_path / "src")},
        }
    )
    assert r.returncode == 0
    assert r.stderr.strip() == EXPECTED_WARN_MSG
    assert "codegraph_explore" in r.stderr
    assert "Repowise" not in r.stderr
    assert "Graphify" not in r.stderr


def test_silent_on_grep_with_file_path(tmp_path: Path) -> None:
    (tmp_path / ".codegraph").mkdir()
    (tmp_path / "foo.txt").write_text("hi")
    r = _run(
        {
            "tool_name": "Grep",
            "cwd": str(tmp_path),
            "tool_input": {"pattern": "foo", "path": str(tmp_path / "foo.txt")},
        }
    )
    assert r.returncode == 0
    assert r.stderr == ""


def test_warns_on_glob_with_wildcard_pattern(tmp_path: Path) -> None:
    (tmp_path / ".codegraph").mkdir()
    r = _run(
        {
            "tool_name": "Glob",
            "cwd": str(tmp_path),
            "tool_input": {"pattern": "**/*.ts"},
        }
    )
    assert r.returncode == 0
    assert r.stderr.strip() == EXPECTED_WARN_MSG


def test_silent_on_glob_with_literal_pattern(tmp_path: Path) -> None:
    (tmp_path / ".codegraph").mkdir()
    r = _run(
        {
            "tool_name": "Glob",
            "cwd": str(tmp_path),
            "tool_input": {"pattern": "package.json"},
        }
    )
    assert r.returncode == 0
    assert r.stderr == ""


# --- Step 4: sentinel-based turn detection -------------------------------


def test_silent_after_codegraph_used_this_turn(tmp_path: Path) -> None:
    (tmp_path / ".codegraph").mkdir()
    (tmp_path / ".claude").mkdir()
    (tmp_path / "src").mkdir()
    tx = tmp_path / "transcripts" / "abc123.jsonl"
    _write_transcript(tx, 3)
    (tmp_path / ".claude" / "code-intelligence-turn-state.json").write_text(
        json.dumps(
            {"transcript_id": "abc123", "turn_counter": 3, "tools_used": ["codegraph"]}
        )
    )
    r = _run(
        {
            "tool_name": "Grep",
            "cwd": str(tmp_path),
            "transcript_path": str(tx),
            "tool_input": {"pattern": "foo", "path": str(tmp_path / "src")},
        }
    )
    assert r.returncode == 0
    assert r.stderr == ""


def test_warns_when_sentinel_is_for_prior_turn(tmp_path: Path) -> None:
    (tmp_path / ".codegraph").mkdir()
    (tmp_path / ".claude").mkdir()
    (tmp_path / "src").mkdir()
    tx = tmp_path / "transcripts" / "abc123.jsonl"
    _write_transcript(tx, 4)
    (tmp_path / ".claude" / "code-intelligence-turn-state.json").write_text(
        json.dumps(
            {"transcript_id": "abc123", "turn_counter": 3, "tools_used": ["codegraph"]}
        )
    )
    r = _run(
        {
            "tool_name": "Grep",
            "cwd": str(tmp_path),
            "transcript_path": str(tx),
            "tool_input": {"pattern": "foo", "path": str(tmp_path / "src")},
        }
    )
    assert r.returncode == 0
    assert r.stderr.strip() == EXPECTED_WARN_MSG


def test_warns_when_sentinel_is_for_different_transcript(tmp_path: Path) -> None:
    (tmp_path / ".codegraph").mkdir()
    (tmp_path / ".claude").mkdir()
    (tmp_path / "src").mkdir()
    tx = tmp_path / "transcripts" / "abc123.jsonl"
    _write_transcript(tx, 2)
    (tmp_path / ".claude" / "code-intelligence-turn-state.json").write_text(
        json.dumps(
            {"transcript_id": "other", "turn_counter": 2, "tools_used": ["codegraph"]}
        )
    )
    r = _run(
        {
            "tool_name": "Grep",
            "cwd": str(tmp_path),
            "transcript_path": str(tx),
            "tool_input": {"pattern": "foo", "path": str(tmp_path / "src")},
        }
    )
    assert r.returncode == 0
    assert r.stderr.strip() == EXPECTED_WARN_MSG


def test_warns_when_sentinel_missing(tmp_path: Path) -> None:
    (tmp_path / ".codegraph").mkdir()
    (tmp_path / ".claude").mkdir()
    (tmp_path / "src").mkdir()
    tx = tmp_path / "transcripts" / "abc123.jsonl"
    _write_transcript(tx, 1)
    r = _run(
        {
            "tool_name": "Grep",
            "cwd": str(tmp_path),
            "transcript_path": str(tx),
            "tool_input": {"pattern": "foo", "path": str(tmp_path / "src")},
        }
    )
    assert r.returncode == 0
    assert r.stderr.strip() == EXPECTED_WARN_MSG


# --- Step 5: careful-mode escalation --------------------------------------


def test_careful_mode_blocks(tmp_path: Path) -> None:
    (tmp_path / ".codegraph").mkdir()
    (tmp_path / "src").mkdir()
    _CAREFUL_STATE.write_text(json.dumps({"active": True}))
    try:
        r = _run(
            {
                "tool_name": "Grep",
                "cwd": str(tmp_path),
                "tool_input": {"pattern": "foo", "path": str(tmp_path / "src")},
            }
        )
        assert r.returncode == 2
        assert r.stderr.strip() == f"{EXPECTED_WARN_MSG} [blocked by /careful]"
    finally:
        _CAREFUL_STATE.unlink(missing_ok=True)


def test_warns_when_careful_inactive(tmp_path: Path) -> None:
    (tmp_path / ".codegraph").mkdir()
    (tmp_path / "src").mkdir()
    _CAREFUL_STATE.write_text(json.dumps({"active": False}))
    try:
        r = _run(
            {
                "tool_name": "Grep",
                "cwd": str(tmp_path),
                "tool_input": {"pattern": "foo", "path": str(tmp_path / "src")},
            }
        )
        assert r.returncode == 0
        assert r.stderr.strip() == EXPECTED_WARN_MSG
    finally:
        _CAREFUL_STATE.unlink(missing_ok=True)


# --- Step 6: fail-open guards ---------------------------------------------


def test_fails_open_on_malformed_json() -> None:
    r = subprocess.run(
        ["python3", str(_HOOK)],
        input="not json",
        env={
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0
    assert r.stdout == ""
    assert r.stderr == ""


def test_fails_open_on_empty_stdin() -> None:
    r = subprocess.run(
        ["python3", str(_HOOK)],
        input="",
        env={
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0


def test_fails_open_on_missing_transcript(tmp_path: Path) -> None:
    """Nonexistent transcript_path falls through — sentinel logic returns
    'not used', so the warn fires. Same as bats' fails_open_on_missing_transcript."""
    (tmp_path / ".codegraph").mkdir()
    (tmp_path / "src").mkdir()
    r = _run(
        {
            "tool_name": "Grep",
            "cwd": str(tmp_path),
            "transcript_path": "/nonexistent/transcript.jsonl",
            "tool_input": {"pattern": "foo", "path": str(tmp_path / "src")},
        }
    )
    assert r.returncode == 0
    assert r.stderr.strip() == EXPECTED_WARN_MSG


def test_pass_silently_on_unrelated_tool(tmp_path: Path) -> None:
    (tmp_path / ".codegraph").mkdir()
    r = _run(
        {"tool_name": "Bash", "cwd": str(tmp_path), "tool_input": {"command": "ls"}}
    )
    assert r.returncode == 0
    assert r.stderr == ""


# --- _detect_present_tools -------------------------------------------------


def test_detects_each_tool_independently(tmp_path: Path) -> None:
    codegraph_only = tmp_path / "codegraph_only"
    codegraph_only.mkdir()
    (codegraph_only / ".codegraph").mkdir()
    assert code_intelligence_nudge._detect_present_tools(codegraph_only) == [
        "codegraph"
    ]

    repowise_only = tmp_path / "repowise_only"
    repowise_only.mkdir()
    (repowise_only / ".repowise").mkdir()
    assert code_intelligence_nudge._detect_present_tools(repowise_only) == [
        "repowise"
    ]

    graphify_only = tmp_path / "graphify_only"
    graphify_only.mkdir()
    (graphify_only / "graphify-out").mkdir()
    (graphify_only / "graphify-out" / "graph.json").write_text("{}")
    assert code_intelligence_nudge._detect_present_tools(graphify_only) == [
        "graphify"
    ]


def test_detects_none_present(tmp_path: Path) -> None:
    assert code_intelligence_nudge._detect_present_tools(tmp_path) == []


def test_graphify_path_wrong_type_fails_open(tmp_path: Path) -> None:
    """graphify-out/graph.json as a directory (not a regular file) → not present."""
    (tmp_path / "graphify-out" / "graph.json").mkdir(parents=True)
    assert "graphify" not in code_intelligence_nudge._detect_present_tools(tmp_path)


def test_repowise_path_wrong_type_fails_open(tmp_path: Path) -> None:
    """.repowise as a regular file (not a directory) → not present."""
    (tmp_path / ".repowise").write_text("not a directory")
    assert "repowise" not in code_intelligence_nudge._detect_present_tools(tmp_path)


def test_graphify_dir_without_graph_json_does_not_nudge(tmp_path: Path) -> None:
    """graphify-out/ present but graph.json missing → graphify not detected."""
    (tmp_path / "graphify-out").mkdir()
    assert "graphify" not in code_intelligence_nudge._detect_present_tools(tmp_path)


# --- _compose_message -------------------------------------------------------


def test_single_tool_message_per_tool() -> None:
    for tool, differentiator in (
        ("graphify", "non-code content"),
        ("repowise", "not raw call-graph structure"),
        ("codegraph", "not risk, rationale, or non-code content"),
    ):
        msg = code_intelligence_nudge._compose_message([tool])
        assert msg is not None
        assert "[code-intelligence-nudge]" in msg
        assert code_intelligence_nudge._LABELS[tool] in msg
        assert differentiator in msg
        # No cross-contamination from the other two tools' cues.
        for other in ("graphify", "repowise", "codegraph"):
            if other != tool:
                assert code_intelligence_nudge.CUES[other] not in msg


def test_combined_message_two_tools_precedence_order() -> None:
    msg = code_intelligence_nudge._compose_message(["codegraph", "repowise"])
    assert msg is not None
    assert "Multiple code-intelligence indexes found" in msg
    repowise_idx = msg.index(code_intelligence_nudge.CUES["repowise"])
    codegraph_idx = msg.index(code_intelligence_nudge.CUES["codegraph"])
    assert repowise_idx < codegraph_idx


def test_combined_message_three_tools_precedence_order() -> None:
    msg = code_intelligence_nudge._compose_message(
        ["codegraph", "graphify", "repowise"]
    )
    assert msg is not None
    graphify_idx = msg.index(code_intelligence_nudge.CUES["graphify"])
    repowise_idx = msg.index(code_intelligence_nudge.CUES["repowise"])
    codegraph_idx = msg.index(code_intelligence_nudge.CUES["codegraph"])
    assert graphify_idx < repowise_idx < codegraph_idx


def test_closing_line_identical_across_variants() -> None:
    single = code_intelligence_nudge._compose_message(["codegraph"])
    combined = code_intelligence_nudge._compose_message(["codegraph", "repowise"])
    assert single is not None and combined is not None
    assert single.endswith(code_intelligence_nudge._CLOSING_LINE)
    assert combined.endswith(code_intelligence_nudge._CLOSING_LINE)


def test_compose_message_returns_none_for_empty_list() -> None:
    assert code_intelligence_nudge._compose_message([]) is None


# --- main() wiring: multi-tool detection + composition (Step 1.3) ----------


def _graphify_index(root: Path) -> None:
    (root / "graphify-out").mkdir(parents=True, exist_ok=True)
    (root / "graphify-out" / "graph.json").write_text("{}")


def test_repowise_only(tmp_path: Path) -> None:
    (tmp_path / ".repowise").mkdir()
    r = _run(
        {
            "tool_name": "Glob",
            "cwd": str(tmp_path),
            "tool_input": {"pattern": "**/*.ts"},
        }
    )
    expected = code_intelligence_nudge._compose_message(["repowise"])
    assert r.returncode == 0
    assert r.stderr.strip() == expected
    assert "get_context" in r.stderr
    assert code_intelligence_nudge.CUES["codegraph"] not in r.stderr
    assert code_intelligence_nudge.CUES["graphify"] not in r.stderr


def test_graphify_only(tmp_path: Path) -> None:
    _graphify_index(tmp_path)
    r = _run(
        {
            "tool_name": "Grep",
            "cwd": str(tmp_path),
            "tool_input": {"pattern": "foo"},
        }
    )
    expected = code_intelligence_nudge._compose_message(["graphify"])
    assert r.returncode == 0
    assert r.stderr.strip() == expected
    assert "graphify query" in r.stderr
    assert code_intelligence_nudge.CUES["codegraph"] not in r.stderr
    assert code_intelligence_nudge.CUES["repowise"] not in r.stderr


def test_two_present_combined(tmp_path: Path) -> None:
    (tmp_path / ".codegraph").mkdir()
    (tmp_path / ".repowise").mkdir()
    r = _run(
        {
            "tool_name": "Grep",
            "cwd": str(tmp_path),
            "tool_input": {"pattern": "foo"},
        }
    )
    expected = code_intelligence_nudge._compose_message(["repowise", "codegraph"])
    assert r.returncode == 0
    assert r.stderr.strip() == expected
    repowise_idx = r.stderr.index(code_intelligence_nudge.CUES["repowise"])
    codegraph_idx = r.stderr.index(code_intelligence_nudge.CUES["codegraph"])
    assert repowise_idx < codegraph_idx


def test_three_present_combined(tmp_path: Path) -> None:
    (tmp_path / ".codegraph").mkdir()
    (tmp_path / ".repowise").mkdir()
    _graphify_index(tmp_path)
    r = _run(
        {
            "tool_name": "Grep",
            "cwd": str(tmp_path),
            "tool_input": {"pattern": "foo"},
        }
    )
    expected = code_intelligence_nudge._compose_message(
        ["codegraph", "repowise", "graphify"]
    )
    assert r.returncode == 0
    assert r.stderr.strip() == expected
    graphify_idx = r.stderr.index(code_intelligence_nudge.CUES["graphify"])
    repowise_idx = r.stderr.index(code_intelligence_nudge.CUES["repowise"])
    codegraph_idx = r.stderr.index(code_intelligence_nudge.CUES["codegraph"])
    assert graphify_idx < repowise_idx < codegraph_idx


def test_none_present_silent(tmp_path: Path) -> None:
    r = _run(
        {
            "tool_name": "Grep",
            "cwd": str(tmp_path),
            "tool_input": {"pattern": "foo"},
        }
    )
    assert r.returncode == 0
    assert r.stdout == ""
    assert r.stderr == ""


def test_read_never_nudges(tmp_path: Path) -> None:
    (tmp_path / ".codegraph").mkdir()
    _graphify_index(tmp_path)
    (tmp_path / "foo.txt").write_text("hi")
    r = _run(
        {
            "tool_name": "Read",
            "cwd": str(tmp_path),
            "tool_input": {"file_path": str(tmp_path / "foo.txt")},
        }
    )
    assert r.returncode == 0
    assert r.stdout == ""
    assert r.stderr == ""


def test_single_file_grep_never_nudges(tmp_path: Path) -> None:
    (tmp_path / ".codegraph").mkdir()
    _graphify_index(tmp_path)
    (tmp_path / "foo.txt").write_text("hi")
    r = _run(
        {
            "tool_name": "Grep",
            "cwd": str(tmp_path),
            "tool_input": {"pattern": "foo", "path": str(tmp_path / "foo.txt")},
        }
    )
    assert r.returncode == 0
    assert r.stdout == ""
    assert r.stderr == ""


def test_literal_glob_never_nudges(tmp_path: Path) -> None:
    (tmp_path / ".codegraph").mkdir()
    _graphify_index(tmp_path)
    r = _run(
        {
            "tool_name": "Glob",
            "cwd": str(tmp_path),
            "tool_input": {"pattern": "package.json"},
        }
    )
    assert r.returncode == 0
    assert r.stdout == ""
    assert r.stderr == ""


def test_suppressed_when_used_this_turn(tmp_path: Path) -> None:
    """Both codegraph and graphify present; codegraph already used this
    turn -> composed message omits the CodeGraph line, keeps Graphify."""
    (tmp_path / ".codegraph").mkdir()
    _graphify_index(tmp_path)
    (tmp_path / ".claude").mkdir()
    tx = tmp_path / "transcripts" / "abc123.jsonl"
    _write_transcript(tx, 3)
    (tmp_path / ".claude" / "code-intelligence-turn-state.json").write_text(
        json.dumps(
            {"transcript_id": "abc123", "turn_counter": 3, "tools_used": ["codegraph"]}
        )
    )
    r = _run(
        {
            "tool_name": "Grep",
            "cwd": str(tmp_path),
            "transcript_path": str(tx),
            "tool_input": {"pattern": "foo"},
        }
    )
    expected = code_intelligence_nudge._compose_message(["graphify"])
    assert r.returncode == 0
    assert r.stderr.strip() == expected
    assert code_intelligence_nudge.CUES["codegraph"] not in r.stderr
    assert code_intelligence_nudge.CUES["graphify"] in r.stderr


# --- Step 2.3: list-based sentinel (multi-family suppression) -------------


def _write_sentinel(tmp_path: Path, tid: str, tc: int, tools_used) -> None:
    (tmp_path / ".claude").mkdir(exist_ok=True)
    (tmp_path / ".claude" / "code-intelligence-turn-state.json").write_text(
        json.dumps({"transcript_id": tid, "turn_counter": tc, "tools_used": tools_used})
    )


def test_suppresses_only_families_used_this_turn(tmp_path: Path) -> None:
    """Both codegraph and repowise present; only "codegraph" in tools_used
    -> composed message omits CodeGraph, keeps Repowise."""
    (tmp_path / ".codegraph").mkdir()
    (tmp_path / ".repowise").mkdir()
    tx = tmp_path / "transcripts" / "abc123.jsonl"
    _write_transcript(tx, 3)
    _write_sentinel(tmp_path, "abc123", 3, ["codegraph"])
    r = _run(
        {
            "tool_name": "Grep",
            "cwd": str(tmp_path),
            "transcript_path": str(tx),
            "tool_input": {"pattern": "foo"},
        }
    )
    expected = code_intelligence_nudge._compose_message(["repowise"])
    assert r.returncode == 0
    assert r.stderr.strip() == expected
    assert code_intelligence_nudge.CUES["codegraph"] not in r.stderr
    assert code_intelligence_nudge.CUES["repowise"] in r.stderr


def test_three_present_two_used_shows_remaining_only(tmp_path: Path) -> None:
    """All three present; codegraph and repowise already used this turn
    -> composed message names only Graphify."""
    (tmp_path / ".codegraph").mkdir()
    (tmp_path / ".repowise").mkdir()
    _graphify_index(tmp_path)
    tx = tmp_path / "transcripts" / "abc123.jsonl"
    _write_transcript(tx, 3)
    _write_sentinel(tmp_path, "abc123", 3, ["codegraph", "repowise"])
    r = _run(
        {
            "tool_name": "Grep",
            "cwd": str(tmp_path),
            "transcript_path": str(tx),
            "tool_input": {"pattern": "foo"},
        }
    )
    expected = code_intelligence_nudge._compose_message(["graphify"])
    assert r.returncode == 0
    assert r.stderr.strip() == expected
    assert code_intelligence_nudge.CUES["codegraph"] not in r.stderr
    assert code_intelligence_nudge.CUES["repowise"] not in r.stderr
    assert code_intelligence_nudge.CUES["graphify"] in r.stderr


def test_full_suppression_when_all_used(tmp_path: Path) -> None:
    """Both present tools already used this turn -> full suppression."""
    (tmp_path / ".codegraph").mkdir()
    (tmp_path / ".repowise").mkdir()
    tx = tmp_path / "transcripts" / "abc123.jsonl"
    _write_transcript(tx, 3)
    _write_sentinel(tmp_path, "abc123", 3, ["codegraph", "repowise"])
    r = _run(
        {
            "tool_name": "Grep",
            "cwd": str(tmp_path),
            "transcript_path": str(tx),
            "tool_input": {"pattern": "foo"},
        }
    )
    assert r.returncode == 0
    assert r.stdout == ""
    assert r.stderr == ""


def test_corrupt_sentinel_read_fails_open(tmp_path: Path) -> None:
    """Sentinel matches the current transcript/turn but tools_used is not a
    list -> treated as no tool used this turn; the hook still warns, not
    crashes."""
    (tmp_path / ".codegraph").mkdir()
    (tmp_path / ".repowise").mkdir()
    tx = tmp_path / "transcripts" / "abc123.jsonl"
    _write_transcript(tx, 3)
    _write_sentinel(tmp_path, "abc123", 3, "not-a-list")
    r = _run(
        {
            "tool_name": "Grep",
            "cwd": str(tmp_path),
            "transcript_path": str(tx),
            "tool_input": {"pattern": "foo"},
        }
    )
    expected = code_intelligence_nudge._compose_message(["repowise", "codegraph"])
    assert r.returncode == 0
    assert r.stderr.strip() == expected


def test_legacy_sentinel_read_fails_open(tmp_path: Path) -> None:
    """Sentinel matches the current transcript/turn but has no tools_used
    field at all (pre-Slice-2 schema) -> treated as no tool used this turn;
    the hook still warns, not crashes."""
    (tmp_path / ".codegraph").mkdir()
    (tmp_path / ".repowise").mkdir()
    tx = tmp_path / "transcripts" / "abc123.jsonl"
    _write_transcript(tx, 3)
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "code-intelligence-turn-state.json").write_text(
        json.dumps({"transcript_id": "abc123", "turn_counter": 3})
    )
    r = _run(
        {
            "tool_name": "Grep",
            "cwd": str(tmp_path),
            "transcript_path": str(tx),
            "tool_input": {"pattern": "foo"},
        }
    )
    expected = code_intelligence_nudge._compose_message(["repowise", "codegraph"])
    assert r.returncode == 0
    assert r.stderr.strip() == expected
