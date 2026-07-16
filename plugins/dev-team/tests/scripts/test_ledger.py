"""Unit tests for skills/code-review/scripts/ledger.py.

Covers ledger init (all pending, cap recorded), section-artifact writing (schema
+ panel + status flip), idempotent re-init, and partial-state validity. Resume
detection (pending_slices) lives in Slice 4 and is tested there.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(
    0,
    str(_REPO_ROOT / "plugins" / "dev-team" / "skills" / "code-review" / "scripts"),
)

import ledger  # noqa: E402


def _slices():
    return [
        {"id": "0001", "files": ["src/a.ts", "src/b.ts"], "is_declarative": False},
        {"id": "0002", "files": ["src/models/x.ts"], "is_declarative": True},
    ]


def test_init_records_all_slices_pending_with_cap(tmp_path):
    result = ledger.init_ledger(_slices(), cap=50, root=str(tmp_path))
    assert result["cap"] == 50
    assert result["schema"] == ledger.LEDGER_SCHEMA
    assert [s["status"] for s in result["slices"]] == ["pending", "pending"]
    assert result["slices"][0]["files"] == ["src/a.ts", "src/b.ts"]
    assert result["slices"][1]["is_declarative"] is True
    # Persisted to the expected path under the target root.
    assert ledger.ledger_path(str(tmp_path)).exists()


def test_write_section_creates_artifact_and_flips_status(tmp_path):
    ledger.init_ledger(_slices(), cap=50, root=str(tmp_path))
    findings = [{"severity": "warning", "file": "src/a.ts", "line": 3, "message": "x"}]
    path = ledger.write_section(
        _slices()[0], findings, panel=["correctness-review", "structure-review"], root=str(tmp_path)
    )
    assert path == ledger.section_path(str(tmp_path), "0001")
    artifact = json.loads(path.read_text())
    assert artifact["schema"] == ledger.SECTION_SCHEMA
    assert artifact["id"] == "0001"
    assert artifact["files"] == ["src/a.ts", "src/b.ts"]
    assert artifact["panel"] == ["correctness-review", "structure-review"]
    assert artifact["findings"] == findings
    # Ledger status for 0001 is now done; 0002 still pending.
    updated = ledger.read_ledger(str(tmp_path))
    statuses = {s["id"]: s["status"] for s in updated["slices"]}
    assert statuses == {"0001": "done", "0002": "pending"}


def test_reinit_is_idempotent(tmp_path):
    a = ledger.init_ledger(_slices(), cap=50, root=str(tmp_path))
    b = ledger.init_ledger(_slices(), cap=50, root=str(tmp_path))
    assert a == b


def test_partial_state_is_valid_json(tmp_path):
    ledger.init_ledger(_slices(), cap=50, root=str(tmp_path))
    ledger.write_section(_slices()[0], [], panel=["correctness-review"], root=str(tmp_path))
    # Interrupted here (0002 never written) — ledger + written section stay valid.
    data = json.loads(ledger.ledger_path(str(tmp_path)).read_text())
    assert len(data["slices"]) == 2
    assert json.loads(ledger.section_path(str(tmp_path), "0001").read_text())["id"] == "0001"


def test_read_ledger_none_when_absent(tmp_path):
    assert ledger.read_ledger(str(tmp_path)) is None


def test_mark_done_noop_without_ledger(tmp_path):
    # Should not raise when there is no ledger yet.
    ledger.mark_done(str(tmp_path), "0001")
    assert ledger.read_ledger(str(tmp_path)) is None


# --- Slice 4: resume detection + cap guard ------------------------------------


def _ids(slices):
    return [s["id"] for s in slices]


def test_pending_returns_only_slices_without_artifacts(tmp_path):
    ledger.init_ledger(_slices(), cap=50, root=str(tmp_path))
    ledger.write_section(_slices()[0], [], panel=["correctness-review"], root=str(tmp_path))
    pending = ledger.pending_slices(_slices(), str(tmp_path))
    assert _ids(pending) == ["0002"]


def test_pending_returns_all_when_no_artifacts(tmp_path):
    ledger.init_ledger(_slices(), cap=50, root=str(tmp_path))
    assert _ids(ledger.pending_slices(_slices(), str(tmp_path))) == ["0001", "0002"]


def test_pending_returns_none_when_all_written(tmp_path):
    ledger.init_ledger(_slices(), cap=50, root=str(tmp_path))
    for s in _slices():
        ledger.write_section(s, [], panel=["correctness-review"], root=str(tmp_path))
    assert ledger.pending_slices(_slices(), str(tmp_path)) == []


def test_disk_wins_when_ledger_says_pending_but_artifact_exists(tmp_path):
    # Write the artifact directly, leaving the ledger status at "pending".
    ledger.init_ledger(_slices(), cap=50, root=str(tmp_path))
    path = ledger.section_path(str(tmp_path), "0001")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}")
    # Ledger still says pending, but the artifact exists -> treated done.
    assert _ids(ledger.pending_slices(_slices(), str(tmp_path))) == ["0002"]


def test_resume_cap_mismatch_raises(tmp_path):
    ledger.init_ledger(_slices(), cap=50, root=str(tmp_path))
    with pytest.raises(ValueError):
        ledger.check_resume_cap(str(tmp_path), requested_cap=25)


def test_resume_cap_match_or_absent_ok(tmp_path):
    ledger.init_ledger(_slices(), cap=50, root=str(tmp_path))
    ledger.check_resume_cap(str(tmp_path), requested_cap=50)  # matches -> no raise
    ledger.check_resume_cap(str(tmp_path), requested_cap=None)  # no explicit cap -> no raise
    ledger.check_resume_cap(str(tmp_path) + "-absent", requested_cap=25)  # no ledger -> no raise
