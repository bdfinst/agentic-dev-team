"""Unit tests for skills/harness-audit/scripts/lesson_validate.py (#866).

Covers the Acceptance Criteria from issue #866:
  - new lessons declare evidence or opt out explicitly
  - every matured lesson gets a verdict
  - thin data yields "insufficient data", never "neutral"
  - harmful verdicts produce actionable rollback proposals
  - verdicts never mutate history (append-only)
  - unmeasurable / legacy lessons are surfaced, never judged
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(
    0, str(_REPO_ROOT / "plugins" / "dev-team" / "skills" / "harness-audit" / "scripts")
)

import lesson_validate as lv  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _lesson_entry(
    timestamp: str,
    evidence,
    *,
    entry_type: str = "amend",
    file_modified: str = "CLAUDE.md",
    section_modified: str = "Agent Overrides > Software Engineer",
    previous_value: str = "",
    new_value: str = "- Prefer functional patterns",
) -> dict:
    entry = {
        "timestamp": timestamp,
        "type": entry_type,
        "trigger": "user",
        "description": "test lesson",
        "file_modified": file_modified,
        "section_modified": section_modified,
        "previous_value": previous_value,
        "new_value": new_value,
        "approved_by": "user",
    }
    if evidence is not lv.DEFAULT_METRIC or True:
        entry["evidence"] = evidence
    return entry


def _digest_record(recorded_at: str, rework_total: float) -> dict:
    return {
        "schema": "session-digest/v1",
        "recorded_at": recorded_at,
        "rework": {"failed_edits": rework_total},
        "accuracy": {"tool_calls": 5, "tool_error_rate": 0.0, "user_correction_turns": 0},
    }


def _digest_series(start_day: int, count: int, values: list[float]) -> list[dict]:
    """Build `count` digest records at 2026-01-<day>, one per day, using
    `values` cyclically for the rework total."""
    records = []
    for i in range(count):
        day = start_day + i
        records.append(
            _digest_record(f"2026-01-{day:02d}T00:00:00Z", values[i % len(values)])
        )
    return records


# ---------------------------------------------------------------------------
# Evidence field validation
# ---------------------------------------------------------------------------


def test_structured_evidence_is_valid():
    entry = _lesson_entry(
        "2026-06-01T00:00:00Z",
        {"metrics": ["rework"], "direction": "decrease", "window_sessions": 10},
    )
    assert lv.has_valid_evidence(entry)


def test_unmeasurable_literal_is_valid():
    entry = _lesson_entry("2026-06-01T00:00:00Z", "unmeasurable")
    assert lv.has_valid_evidence(entry)


def test_missing_evidence_field_is_invalid():
    entry = _lesson_entry("2026-06-01T00:00:00Z", "unmeasurable")
    del entry["evidence"]
    assert not lv.has_valid_evidence(entry)


def test_malformed_evidence_object_is_invalid():
    entry = _lesson_entry("2026-06-01T00:00:00Z", {"metrics": ["rework"]})  # no direction/window
    assert not lv.has_valid_evidence(entry)


def test_default_evidence_uses_rework_metric_and_window_10():
    evidence = lv.default_evidence()
    assert evidence["metrics"] == ["rework"]
    assert evidence["window_sessions"] == 10


# ---------------------------------------------------------------------------
# Classification: structured / unmeasurable / legacy
# ---------------------------------------------------------------------------


def test_classify_splits_structured_unmeasurable_and_legacy():
    structured_entry = _lesson_entry(
        "2026-06-01T00:00:00Z",
        {"metrics": ["rework"], "direction": "decrease", "window_sessions": 10},
    )
    unmeasurable_entry = _lesson_entry("2026-06-02T00:00:00Z", "unmeasurable")
    legacy_entry = _lesson_entry("2026-06-03T00:00:00Z", "unmeasurable")
    del legacy_entry["evidence"]

    structured, unmeasurable, legacy = lv.classify_changelog_entries(
        [structured_entry, unmeasurable_entry, legacy_entry]
    )
    assert structured == [structured_entry]
    assert unmeasurable == [unmeasurable_entry]
    assert legacy == [legacy_entry]


def test_classify_ignores_non_lesson_entry_types():
    rollback_entry = {"timestamp": "2026-06-01T00:00:00Z", "type": "rollback"}
    structured, unmeasurable, legacy = lv.classify_changelog_entries([rollback_entry])
    assert structured == unmeasurable == legacy == []


def test_unmeasurable_and_legacy_never_receive_a_verdict_via_report():
    unmeasurable_entry = _lesson_entry("2026-06-02T00:00:00Z", "unmeasurable")
    legacy_entry = _lesson_entry("2026-06-03T00:00:00Z", "unmeasurable")
    del legacy_entry["evidence"]

    report = lv.build_report([unmeasurable_entry, legacy_entry], [])
    assert report["verdicts"] == []
    assert report["unmeasurable_count"] == 1
    assert report["legacy_count"] == 1


# ---------------------------------------------------------------------------
# Thin data -> insufficient data, never neutral
# ---------------------------------------------------------------------------


def test_insufficient_data_when_fewer_than_window_records_before_and_after():
    entry = _lesson_entry(
        "2026-01-10T00:00:00Z",
        {"metrics": ["rework"], "direction": "decrease", "window_sessions": 10},
    )
    # Only 3 records before, 3 after — well under the window of 10.
    digest = _digest_series(1, 3, [5]) + _digest_series(11, 3, [1])
    result = lv.validate_lesson(entry, digest)
    assert result["verdict"] == lv.INSUFFICIENT_DATA


def test_insufficient_data_when_only_after_side_is_thin():
    entry = _lesson_entry(
        "2026-01-20T00:00:00Z",
        {"metrics": ["rework"], "direction": "decrease", "window_sessions": 10},
    )
    digest = _digest_series(1, 15, [5]) + _digest_series(21, 2, [1])
    result = lv.validate_lesson(entry, digest)
    assert result["verdict"] == lv.INSUFFICIENT_DATA


def test_report_never_emits_neutral_for_thin_data_only_insufficient():
    entry = _lesson_entry(
        "2026-01-10T00:00:00Z",
        {"metrics": ["rework"], "direction": "decrease", "window_sessions": 10},
    )
    digest = _digest_series(1, 2, [5]) + _digest_series(11, 2, [5])
    report = lv.build_report([entry], digest)
    verdict = report["verdicts"][0]["result"]["verdict"]
    assert verdict == lv.INSUFFICIENT_DATA
    assert verdict != "neutral"


# ---------------------------------------------------------------------------
# Matured lessons get a real verdict: validated / harmful / neutral
# ---------------------------------------------------------------------------


def test_validated_when_metric_moves_in_expected_decrease_direction():
    entry = _lesson_entry(
        "2026-01-11T12:00:00Z",
        {"metrics": ["rework"], "direction": "decrease", "window_sessions": 10},
    )
    # 10 sessions before adoption at rework=8, 10 after at rework=2 (decreased).
    digest = _digest_series(1, 10, [8]) + _digest_series(12, 10, [2])
    result = lv.validate_lesson(entry, digest)
    assert result["verdict"] == "validated"


def test_harmful_when_metric_moves_against_expected_decrease_direction():
    entry = _lesson_entry(
        "2026-01-11T12:00:00Z",
        {"metrics": ["rework"], "direction": "decrease", "window_sessions": 10},
    )
    # Expected rework to decrease, but it increased instead.
    digest = _digest_series(1, 10, [2]) + _digest_series(12, 10, [8])
    result = lv.validate_lesson(entry, digest)
    assert result["verdict"] == "harmful"


def test_neutral_when_adequate_data_shows_no_movement():
    entry = _lesson_entry(
        "2026-01-11T12:00:00Z",
        {"metrics": ["rework"], "direction": "decrease", "window_sessions": 10},
    )
    digest = _digest_series(1, 10, [4]) + _digest_series(12, 10, [4])
    result = lv.validate_lesson(entry, digest)
    assert result["verdict"] == "neutral"


def test_every_matured_structured_lesson_appears_in_report_verdicts():
    entries = [
        _lesson_entry(
            "2026-01-11T12:00:00Z",
            {"metrics": ["rework"], "direction": "decrease", "window_sessions": 10},
        ),
        _lesson_entry(
            "2026-01-15T12:00:00Z",
            {"metrics": ["rework"], "direction": "increase", "window_sessions": 10},
        ),
    ]
    digest = _digest_series(1, 20, [4])
    report = lv.build_report(entries, digest)
    references = {v["result"]["references_timestamp"] for v in report["verdicts"]}
    assert references == {"2026-01-11T12:00:00Z", "2026-01-15T12:00:00Z"}
    for v in report["verdicts"]:
        assert v["result"]["verdict"] in {"validated", "neutral", "harmful", lv.INSUFFICIENT_DATA}


# ---------------------------------------------------------------------------
# Harmful verdicts -> actionable rollback proposals
# ---------------------------------------------------------------------------


def test_harmful_verdict_produces_rollback_proposal_with_required_fields():
    entry = _lesson_entry(
        "2026-01-11T12:00:00Z",
        {"metrics": ["rework"], "direction": "decrease", "window_sessions": 10},
        file_modified="CLAUDE.md",
        section_modified="Agent Overrides > Software Engineer",
        previous_value="- Old preference",
    )
    digest = _digest_series(1, 10, [2]) + _digest_series(12, 10, [8])
    report = lv.build_report([entry], digest)

    assert len(report["rollback_proposals"]) == 1
    proposal = report["rollback_proposals"][0]
    assert proposal["references_timestamp"] == "2026-01-11T12:00:00Z"
    assert proposal["timestamp"] == "2026-01-11T12:00:00Z"
    assert proposal["file_modified"] == "CLAUDE.md"
    assert proposal["section_modified"] == "Agent Overrides > Software Engineer"
    assert proposal["previous_value"] == "- Old preference"
    assert proposal["requires_human_approval"] is True


def test_validated_and_neutral_verdicts_produce_no_rollback_proposal():
    validated_entry = _lesson_entry(
        "2026-01-11T12:00:00Z",
        {"metrics": ["rework"], "direction": "decrease", "window_sessions": 10},
    )
    neutral_entry = _lesson_entry(
        "2026-01-12T12:00:00Z",
        {"metrics": ["rework"], "direction": "increase", "window_sessions": 10},
    )
    digest = _digest_series(1, 10, [8]) + _digest_series(12, 10, [2])
    report = lv.build_report([validated_entry, neutral_entry], digest)
    assert report["rollback_proposals"] == []


# ---------------------------------------------------------------------------
# Append-only: verdicts never mutate history
# ---------------------------------------------------------------------------


def test_append_jsonl_preserves_every_existing_byte(tmp_path):
    changelog = tmp_path / "config-changelog.jsonl"
    original_lines = [
        json.dumps({"timestamp": "2026-01-01T00:00:00Z", "type": "amend"}),
        json.dumps({"timestamp": "2026-01-02T00:00:00Z", "type": "learn"}),
    ]
    changelog.write_text("\n".join(original_lines) + "\n", encoding="utf-8")
    before_bytes = changelog.read_bytes()

    lv.append_jsonl(changelog, [{"timestamp": "2026-01-03T00:00:00Z", "type": "validation"}])

    after_bytes = changelog.read_bytes()
    assert after_bytes[: len(before_bytes)] == before_bytes
    assert len(after_bytes) > len(before_bytes)


def test_main_apply_flag_only_appends_never_rewrites_existing_lines(tmp_path):
    changelog = tmp_path / "config-changelog.jsonl"
    digest = tmp_path / "session-digest.jsonl"

    entry = _lesson_entry(
        "2026-01-11T12:00:00Z",
        {"metrics": ["rework"], "direction": "decrease", "window_sessions": 10},
    )
    changelog.write_text(json.dumps(entry) + "\n", encoding="utf-8")
    digest_records = _digest_series(1, 10, [8]) + _digest_series(12, 10, [2])
    digest.write_text("\n".join(json.dumps(r) for r in digest_records) + "\n", encoding="utf-8")

    before_bytes = changelog.read_bytes()
    exit_code = lv.main(
        ["--changelog", str(changelog), "--digest", str(digest), "--apply"]
    )
    assert exit_code == 0

    after_bytes = changelog.read_bytes()
    assert after_bytes[: len(before_bytes)] == before_bytes
    assert b'"type": "validation"' in after_bytes or b'"type":"validation"' in after_bytes


def test_apply_writes_a_new_validation_entry_referencing_original_timestamp(tmp_path):
    changelog = tmp_path / "config-changelog.jsonl"
    digest = tmp_path / "session-digest.jsonl"

    entry = _lesson_entry(
        "2026-01-11T12:00:00Z",
        {"metrics": ["rework"], "direction": "decrease", "window_sessions": 10},
    )
    changelog.write_text(json.dumps(entry) + "\n", encoding="utf-8")
    digest_records = _digest_series(1, 10, [8]) + _digest_series(12, 10, [2])
    digest.write_text("\n".join(json.dumps(r) for r in digest_records) + "\n", encoding="utf-8")

    lv.main(["--changelog", str(changelog), "--digest", str(digest), "--apply"])

    lines = changelog.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    new_entry = json.loads(lines[1])
    assert new_entry["type"] == "validation"
    assert new_entry["references_timestamp"] == "2026-01-11T12:00:00Z"
    assert new_entry["verdict"] == "validated"


# ---------------------------------------------------------------------------
# Malformed / missing input tolerance
# ---------------------------------------------------------------------------


def test_read_jsonl_returns_empty_list_for_missing_file(tmp_path):
    assert lv.read_jsonl(tmp_path / "does-not-exist.jsonl") == []


def test_read_jsonl_skips_malformed_lines(tmp_path):
    path = tmp_path / "f.jsonl"
    path.write_text('{"a": 1}\nnot json\n{"b": 2}\n', encoding="utf-8")
    assert lv.read_jsonl(path) == [{"a": 1}, {"b": 2}]
