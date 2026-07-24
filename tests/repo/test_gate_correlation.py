"""#111 — per-session review-gate instrumentation + bypass<->rework correlation.
Narrowed "process eval": does bypassing the pre-commit review gate correlate
with more rework? The digest now carries a per-session gate block, and
--correlate compares rework between bypass and non-bypass committing sessions.

Ported from tests/repo/gate_correlation_tests.bats (issue #672).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from _repo_root import REPO_ROOT

EXTRACT = REPO_ROOT / "scripts" / "session_extract.py"
PLUGIN = REPO_ROOT / "plugins" / "dev-team"


def _run_transcript(transcript: Path, *extra: str) -> dict:
    res = subprocess.run(
        [
            sys.executable,
            str(EXTRACT),
            "--transcript",
            str(transcript),
            "--plugin-root",
            str(PLUGIN),
            *extra,
        ],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    return json.loads(res.stdout)


def test_gate_commit_attempts_and_bypasses_counted_from_the_transcript_111(
    tmp_path: Path,
) -> None:
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(
        '{"type":"assistant","cwd":"/p","sessionId":"s","message":{"content":'
        '[{"type":"tool_use","name":"Bash","input":{"command":"git commit -m a"}}]}}\n'
        '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Bash",'
        '"input":{"command":"git commit -m b --no-verify"}}]}}\n'
        '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Bash",'
        '"input":{"command":"git commit -m c -n"}}]}}\n'
    )
    data = _run_transcript(transcript)
    assert data["gate"]["commit_attempts"] == 3
    assert data["gate"]["commit_bypasses"] == 2  # --no-verify and -n


def test_gate_a_plain_commit_is_not_counted_as_a_bypass_111(tmp_path: Path) -> None:
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(
        '{"type":"assistant","cwd":"/p","message":{"content":'
        '[{"type":"tool_use","name":"Bash","input":{"command":"git commit -m clean"}}]}}\n'
    )
    data = _run_transcript(transcript)
    assert data["gate"]["commit_attempts"] == 1
    assert data["gate"]["commit_bypasses"] == 0
    assert data["gate"]["bypass_rate"] == 0.0


def test_correlate_bypass_sessions_with_more_rework_are_surfaced_111(
    tmp_path: Path,
) -> None:
    digests = tmp_path / "digests" / "box"
    digests.mkdir(parents=True)
    (digests / "session-digest.jsonl").write_text(
        '{"schema":"session-sync/v1","host":"box","session_id":"b1",'
        '"rework":{"failed_edits":5,"retried_bash_commands":0},'
        '"gate":{"commit_attempts":1,"commit_bypasses":1}}\n'
        '{"schema":"session-sync/v1","host":"box","session_id":"b2",'
        '"rework":{"failed_edits":3,"retried_bash_commands":0},'
        '"gate":{"commit_attempts":1,"commit_bypasses":1}}\n'
        '{"schema":"session-sync/v1","host":"box","session_id":"g1",'
        '"rework":{"failed_edits":0,"retried_bash_commands":0},'
        '"gate":{"commit_attempts":1,"commit_bypasses":0}}\n'
        '{"schema":"session-sync/v1","host":"box","session_id":"g2",'
        '"rework":{"failed_edits":1,"retried_bash_commands":0},'
        '"gate":{"commit_attempts":1,"commit_bypasses":0}}\n'
    )
    res = subprocess.run(
        [
            sys.executable,
            str(EXTRACT),
            "--correlate",
            str(tmp_path / "digests"),
            "--plugin-root",
            str(PLUGIN),
        ],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    data = json.loads(res.stdout)
    assert data["bypass_sessions"] == 2
    assert data["clean_sessions"] == 2
    assert data["mean_rework_when_bypassed"] == 4.0
    assert data["mean_rework_when_gated"] == 0.5
    assert "MORE rework" in data["interpretation"]


def test_correlate_sessions_that_never_committed_are_excluded_111(
    tmp_path: Path,
) -> None:
    digests = tmp_path / "digests" / "box"
    digests.mkdir(parents=True)
    (digests / "session-digest.jsonl").write_text(
        '{"schema":"session-sync/v1","host":"box","session_id":"n1",'
        '"rework":{"failed_edits":9},"gate":{"commit_attempts":0,"commit_bypasses":0}}\n'
        '{"schema":"session-sync/v1","host":"box","session_id":"g1",'
        '"rework":{"failed_edits":1},"gate":{"commit_attempts":1,"commit_bypasses":0}}\n'
    )
    res = subprocess.run(
        [
            sys.executable,
            str(EXTRACT),
            "--correlate",
            str(tmp_path / "digests"),
            "--plugin-root",
            str(PLUGIN),
        ],
        capture_output=True,
        text=True,
    )
    data = json.loads(res.stdout)
    assert data["committing_sessions"] == 1  # n1 (no commit) excluded


def test_slim_trend_and_sync_records_carry_the_gate_block_111(tmp_path: Path) -> None:
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(
        '{"type":"assistant","cwd":"/work/p","sessionId":"s",'
        '"timestamp":"2026-06-07T10:00:00Z","message":{"content":'
        '[{"type":"tool_use","name":"Bash",'
        '"input":{"command":"git commit -m x --no-verify"}}]}}\n'
    )
    log = tmp_path / "trend.jsonl"
    res = subprocess.run(
        [
            sys.executable,
            str(EXTRACT),
            "--transcript",
            str(transcript),
            "--plugin-root",
            str(PLUGIN),
            "--append",
            str(log),
        ],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    record = json.loads(log.read_text().splitlines()[0])
    assert record["gate"]["commit_bypasses"] == 1
