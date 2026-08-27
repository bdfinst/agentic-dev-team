"""#180 — raw-log tier: the deterministic gate (flag only the worst sessions) and
the privacy guard (a tier finding must stay metrics-only, no quoted payloads).
Model-free; the live per-log pass is opt-in (run-rawlog-tier.sh).

Ported from tests/repo/eval_rawlog_tests.bats (issue #672).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

RAWLOG = REPO_ROOT / "scripts" / "eval_rawlog.py"


@pytest.fixture
def case(tmp_path: Path) -> Path:
    digests = tmp_path / "digests" / "box"
    digests.mkdir(parents=True)
    (digests / "session-digest.jsonl").write_text(
        '{"schema":"session-sync/v1","host":"box","project":"p","session_id":"calm",'
        '"rework":{"failed_edits":0},'
        '"accuracy":{"tool_calls":2,"tool_error_rate":0,"user_correction_turns":0},'
        '"gate":{"commit_bypasses":0}}\n'
        '{"schema":"session-sync/v1","host":"box","project":"p","session_id":"messy",'
        '"rework":{"failed_edits":8,"retried_bash_commands":4},'
        '"accuracy":{"tool_calls":10,"tool_error_rate":0.3,"user_correction_turns":2},'
        '"gate":{"commit_bypasses":1}}\n'
        '{"schema":"session-sync/v1","host":"box","project":"p","session_id":"mid",'
        '"rework":{"failed_edits":2},'
        '"accuracy":{"tool_calls":5,"tool_error_rate":0.1,"user_correction_turns":0},'
        '"gate":{"commit_bypasses":0}}\n'
    )
    return tmp_path


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(RAWLOG), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_v3_digest_records_are_ranked_not_silently_dropped_2047(tmp_path: Path) -> None:
    """ADR 0036's failure mode, guarded directly: eval_rawlog.py must not
    exact-match an old schema string and silently rank zero sessions against
    a v3 digest (session_report.py's own output schema, #2046/#2047)."""
    digests = tmp_path / "digests" / "box"
    digests.mkdir(parents=True)
    (digests / "session-digest.jsonl").write_text(
        '{"schema":"session-sync/v3","host":"box","project":"p","session_id":"messy",'
        '"rework":{"failed_edits":8,"retried_bash_commands":4},'
        '"accuracy":{"tool_calls":10,"tool_error_rate":0.3,"user_correction_turns":2},'
        '"gate":{"commit_bypasses":1}}\n'
    )
    res = _run("--flag", str(tmp_path / "digests"), "--top", "5")
    assert res.returncode == 0, res.stdout + res.stderr
    data = json.loads(res.stdout)
    assert data["worst_sessions"], (
        "a v3-schema digest was ranked as an EMPTY result -- the exact "
        "ADR 0036 silent-empty-ranking failure mode"
    )
    assert data["worst_sessions"][0]["session_id"] == "messy"


def test_flag_the_worst_session_ranks_first_the_gate_bounds_to_top_n_180(
    case: Path,
) -> None:
    res = _run("--flag", str(case / "digests"), "--top", "2")
    assert res.returncode == 0, res.stdout + res.stderr
    data = json.loads(res.stdout)
    assert len(data["worst_sessions"]) == 2
    assert data["worst_sessions"][0]["session_id"] == "messy"
    # 'calm' (lowest friction) is gated out of the top-2 — never gets the raw pass
    ids = [s["session_id"] for s in data["worst_sessions"]]
    assert "calm" not in ids


def test_validate_a_metrics_only_finding_passes_the_privacy_guard_180(
    case: Path,
) -> None:
    finding_file = case / "f.json"
    finding_file.write_text(
        json.dumps(
            [
                {
                    "session_id": "messy",
                    "project": "p",
                    "friction_type": "hallucinated_citation",
                    "lens": "harness",
                    "target_artifact": "session-review",
                    "confidence": "high",
                    "count": 1,
                }
            ]
        )
    )
    res = _run("--validate", str(finding_file))
    assert res.returncode == 0, res.stdout + res.stderr
    data = json.loads(res.stdout)
    assert data["ok"] is True
    assert data["clean"] == 1


def test_validate_a_finding_carrying_a_quote_payload_field_is_rejected_180(
    case: Path,
) -> None:
    finding_file = case / "f.json"
    finding_file.write_text(
        json.dumps(
            [
                {
                    "session_id": "messy",
                    "quote": "the secret is hunter2",
                    "lens": "harness",
                }
            ]
        )
    )
    res = _run("--validate", str(finding_file))
    data = json.loads(res.stdout)
    assert data["ok"] is False
    assert "disallowed keys" in data["violations"][0]["violations"][0]


def test_validate_a_path_code_looking_value_is_rejected_180(case: Path) -> None:
    finding_file = case / "f.json"
    finding_file.write_text(
        json.dumps(
            [
                {
                    "session_id": "messy",
                    "target_artifact": "/Users/x/secret.ts",
                    "lens": "harness",
                }
            ]
        )
    )
    res = _run("--validate", str(finding_file))
    data = json.loads(res.stdout)
    assert data["ok"] is False
    assert "path/code payload" in " ".join(data["violations"][0]["violations"])


def test_validate_an_unknown_lens_is_rejected_180(case: Path) -> None:
    finding_file = case / "f.json"
    finding_file.write_text(json.dumps([{"session_id": "messy", "lens": "freeform"}]))
    res = _run("--validate", str(finding_file))
    data = json.loads(res.stdout)
    assert data["ok"] is False
