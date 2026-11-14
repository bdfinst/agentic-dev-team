"""instrument_log + its call sites (#2201): rows appear, behavior is unchanged."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "hooks" / "lib"))
import instrument_log


def _rows(base: Path, stream: str):
    f = base / ".claude" / "metrics" / f"{stream}.jsonl"
    return [json.loads(line) for line in f.read_text().splitlines()]


def test_append_row_writes_one_compact_row(tmp_path):
    assert instrument_log.append_row("subagent-stops", {"classification": "clean"},
                                     cwd=tmp_path, session_id="s1")
    (row,) = _rows(tmp_path, "subagent-stops")
    assert row["classification"] == "clean" and row["session_id"] == "s1"
    assert {"ts", "plugin_version"} <= row.keys()


def test_unknown_stream_is_refused(tmp_path):
    assert instrument_log.append_row("boundary-events", {"x": 1}, cwd=tmp_path) is False
    assert not (tmp_path / ".claude").exists()


def test_unwritable_location_is_swallowed(tmp_path):
    blocker = tmp_path / "f"
    blocker.write_text("x")
    assert instrument_log.append_row("ledger-skips", {"a": 1}, cwd=blocker) is False


def test_skill_context_hook_logs_injection_and_keeps_stdout(tmp_path):
    payload = {"tool_name": "Agent", "cwd": str(tmp_path), "session_id": "s2",
               "tool_input": {"subagent_type": "dev-team:software-engineer", "prompt": "x"}}
    out = subprocess.run([sys.executable, str(ROOT / "hooks" / "subagent_skill_context.py")],
                         input=json.dumps(payload), capture_output=True, text=True, check=True)
    assert "updatedInput" in out.stdout
    (row,) = _rows(tmp_path, "skill-injection")
    assert row["agent_type"] == "dev-team:software-engineer"
    assert row["added_chars"] > 0 and row["skills"]


def test_verdict_scope_logs_skip_counts(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    out = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "verdict_scope.py"), "--root", str(tmp_path),
         "--lens-files", json.dumps({"correctness-review": ["a.py"]})],
        capture_output=True, text=True, check=True)
    assert json.loads(out.stdout)["toDispatch"] == {"correctness-review": ["a.py"]}
    (row,) = _rows(tmp_path, "ledger-skips")
    assert (row["candidate_pairs"], row["skipped_pairs"]) == (1, 0)
    assert row["source"] == "consult"


def test_checkpoint_abort_logs_outcome_and_keeps_stdout(tmp_path):
    src = tmp_path / "in.json"
    src.write_text(json.dumps({"aborted": True, "redispatched": False, "findings": []}))
    out = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "checkpoint_abort.py"), "--mode", "outcome",
         "--from", str(src)],
        capture_output=True, text=True, check=True, cwd=tmp_path)
    assert json.loads(out.stdout)["outcome"] == "blocked"
    (row,) = _rows(tmp_path, "checkpoint-aborts")
    assert row["mode"] == "outcome" and row["outcome"] == "blocked"
    assert row["source"] == "checkpoint"


def test_checkpoint_abort_logs_abort_mode_source(tmp_path):
    src = tmp_path / "in.json"
    src.write_text(json.dumps([]))
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "checkpoint_abort.py"), "--mode", "abort",
         "--cheap-results-from", str(src), "--lenses", "correctness-review"],
        capture_output=True, text=True, cwd=tmp_path, check=True)
    (row,) = _rows(tmp_path, "checkpoint-aborts")
    assert row["mode"] == "abort"
    assert row["source"] == "checkpoint"


def _session_env(**ids):
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_SESSION_ID")
    }
    return {**env, **ids}


def _run_verdict_scope(root: Path, env: dict):
    (root / "a.py").write_text("x = 1\n")
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "verdict_scope.py"),
            "--root",
            str(root),
            "--lens-files",
            json.dumps({"correctness-review": ["a.py"]}),
        ],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )


def _run_checkpoint_abort(root: Path, env: dict, mode: str):
    src = root / "in.json"
    if mode == "abort":
        src.write_text("[]")
        args = [
            "--mode",
            "abort",
            "--cheap-results-from",
            str(src),
            "--lenses",
            "correctness-review",
        ]
    else:
        src.write_text(
            json.dumps({"aborted": True, "redispatched": False, "findings": []})
        )
        args = ["--mode", "outcome", "--from", str(src)]
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "checkpoint_abort.py"), *args],
        capture_output=True,
        text=True,
        check=True,
        cwd=root,
        env=env,
    )


def test_consult_row_carries_the_session_id_from_the_environment(tmp_path):
    _run_verdict_scope(tmp_path, _session_env(CLAUDE_CODE_SESSION_ID="sess-consult"))
    (row,) = _rows(tmp_path, "ledger-skips")
    assert row["session_id"] == "sess-consult"


@pytest.mark.parametrize("mode", ["abort", "outcome"])
def test_checkpoint_row_carries_the_session_id_from_the_environment(tmp_path, mode):
    _run_checkpoint_abort(
        tmp_path, _session_env(CLAUDE_CODE_SESSION_ID="sess-ckpt"), mode
    )
    (row,) = _rows(tmp_path, "checkpoint-aborts")
    assert row["session_id"] == "sess-ckpt"


def test_hook_documented_session_variable_is_the_fallback(tmp_path):
    _run_verdict_scope(tmp_path, _session_env(CLAUDE_SESSION_ID="sess-hook-var"))
    (row,) = _rows(tmp_path, "ledger-skips")
    assert row["session_id"] == "sess-hook-var"


def test_row_without_any_session_variable_omits_the_field(tmp_path):
    _run_checkpoint_abort(tmp_path, _session_env(), "outcome")
    (row,) = _rows(tmp_path, "checkpoint-aborts")
    assert "session_id" not in row


def test_env_session_id_ignores_blank_values(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "  ")
    monkeypatch.setenv("CLAUDE_SESSION_ID", "sess-b")
    assert instrument_log.env_session_id() == "sess-b"
