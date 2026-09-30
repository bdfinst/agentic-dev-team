"""instrument_log + its call sites (#2201): rows appear, behavior is unchanged."""

import json
import subprocess
import sys
from pathlib import Path

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
