"""Tests for scripts/session_extract.py - the deterministic, zero-token
session-log extractor (#127). Exercised against a committed fixture
transcript that plants one signal of each class.

Ported from tests/repo/session_extract_tests.bats (#673).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EXTRACT = REPO_ROOT / "scripts" / "session_extract.py"
FIX = REPO_ROOT / "tests" / "fixtures" / "session-review" / "sample-transcript.jsonl"
PLUGIN = REPO_ROOT / "plugins" / "dev-team"


def _run(*extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(EXTRACT),
            "--transcript",
            str(FIX),
            "--plugin-root",
            str(PLUGIN),
            *extra,
        ],
        capture_output=True,
        text=True,
    )


def _digest() -> dict:
    result = _run()
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def test_extract_token_signals() -> None:
    digest = _digest()
    assert digest["schema"] == "session-digest/v1"
    assert digest["sessions"] == 1
    assert digest["token"]["totals"]["input_tokens"] == 4100
    assert digest["token"]["cache_hit_ratio"] == 0.8
    assert digest["token"]["by_subagent"]["sidechain"] == 1
    assert digest["token"]["by_skill"]["code-review"]["input_tokens"] == 1500


def test_extract_rework_signals() -> None:
    digest = _digest()
    rework = digest["rework"]
    assert rework["failed_edits"] == 1
    assert rework["repeated_file_edits"]["a.ts"] == 2
    assert rework["retried_bash_commands"] == 1
    assert rework["repeated_verify_runs"] == 2
    assert rework["permission_denials"] == 1
    assert rework["compaction_events"] == 1


def test_extract_accuracy_signals() -> None:
    digest = _digest()
    accuracy = digest["accuracy"]
    assert accuracy["tool_errors_by_tool"]["Edit"] == 1
    assert accuracy["tool_errors_by_tool"]["Grep"] == 1
    assert accuracy["tool_error_rate"] == 0.4
    assert accuracy["user_correction_turns"] == 1


def test_extract_utilization() -> None:
    digest = _digest()
    utilization = digest["utilization"]
    assert utilization["skills_invoked"]["code-review"] == 2
    # the plugin ships many skills; nearly all are never-observed in this
    # fixture
    assert len(utilization["never_observed_skills"]) > 10
    # code-review WAS observed, so it must not be in never-observed
    assert "code-review" not in utilization["never_observed_skills"]


def test_extract_deterministic_identical_bytes_on_repeated_runs() -> None:
    a = _run().stdout
    b = _run().stdout
    assert a == b


def test_extract_privacy_no_raw_prompt_code_command_content_in_digest() -> None:
    output = _run().stdout
    # planted raw strings that must NEVER appear in a metrics-only digest
    assert "old_string not found" not in output
    assert "npm test" not in output
    assert "revert that change" not in output
    assert "/proj/src" not in output  # absolute paths reduced to basenames


def test_extract_append_writes_one_metrics_only_trend_record_per_run(
    tmp_path: Path,
) -> None:
    log = tmp_path / "session-digest.jsonl"
    _run("--append", str(log))
    _run("--append", str(log))
    lines = log.read_text().splitlines()
    # appended once per run -> two lines
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["schema"] == "session-digest/v1"
    # aggregate counts only: rework.repeated_file_edits is a COUNT, not a map
    assert first["rework"]["repeated_file_edits"] == 1
    assert first["accuracy"]["user_correction_turns"] == 1
    # privacy: the trend record carries no file names / commands / paths
    text = log.read_text()
    assert "a.ts" not in text
    assert "npm test" not in text


def test_extract_empty_input_yields_a_well_formed_empty_digest(tmp_path: Path) -> None:
    empty = tmp_path / "empty.jsonl"
    empty.write_text("")
    result = subprocess.run(
        [
            sys.executable,
            str(EXTRACT),
            "--transcript",
            str(empty),
            "--plugin-root",
            str(PLUGIN),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data.get("token", {}).get("totals", {}).get("input_tokens", 0) == 0
