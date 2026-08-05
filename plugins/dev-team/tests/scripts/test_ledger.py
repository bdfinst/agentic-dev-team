"""Unit tests for skills/code-review/scripts/ledger.py.

Covers ledger init (all pending, cap recorded), section-artifact writing (schema
+ panel + status flip), idempotent re-init, and partial-state validity. Resume
detection (pending_slices) lives in Slice 4 and is tested there.
"""

from __future__ import annotations

import json
import sys

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(
    0,
    str(_REPO_ROOT / "plugins" / "dev-team" / "skills" / "code-review" / "scripts"),
)

import ledger


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


def test_raw_dir_resolves_under_consolidated_root(tmp_path):
    assert ledger.raw_dir(str(tmp_path)) == tmp_path / ".dev-team-reports" / "code-review" / "raw"
    assert ledger.section_path(str(tmp_path), "0001").parent == ledger.raw_dir(str(tmp_path))


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
    # No dispatch_failures passed -> written as an empty list.
    assert artifact["dispatchFailures"] == []
    # Ledger status for 0001 is now done; 0002 still pending.
    updated = ledger.read_ledger(str(tmp_path))
    statuses = {s["id"]: s["status"] for s in updated["slices"]}
    assert statuses == {"0001": "done", "0002": "pending"}


def test_write_section_persists_dispatch_failures(tmp_path):
    ledger.init_ledger(_slices(), cap=50, root=str(tmp_path))
    failures = [{"agentName": "structure-review", "attempts": 2}]
    path = ledger.write_section(
        _slices()[0],
        [],
        panel=["correctness-review"],
        root=str(tmp_path),
        dispatch_failures=failures,
    )
    artifact = json.loads(path.read_text())
    assert artifact["dispatchFailures"] == failures


def test_write_section_cli_persists_dispatch_failures(tmp_path):
    root = str(tmp_path)
    ledger.init_ledger(_slices(), cap=50, root=root)
    slice_arg = json.dumps(_slices()[0])
    failures_arg = json.dumps([{"agentName": "structure-review", "attempts": 2}])
    rc = ledger.main(
        [
            "write-section",
            "--root",
            root,
            "--slice",
            slice_arg,
            "--findings",
            "[]",
            "--panel",
            "correctness-review",
            "--dispatch-failures",
            failures_arg,
        ]
    )
    assert rc == 0
    artifact = json.loads(ledger.section_path(root, "0001").read_text())
    assert artifact["dispatchFailures"] == [{"agentName": "structure-review", "attempts": 2}]


def test_write_section_cli_without_dispatch_failures_writes_empty_list(tmp_path):
    root = str(tmp_path)
    ledger.init_ledger(_slices(), cap=50, root=root)
    slice_arg = json.dumps(_slices()[0])
    rc = ledger.main(
        [
            "write-section",
            "--root",
            root,
            "--slice",
            slice_arg,
            "--findings",
            "[]",
            "--panel",
            "correctness-review",
        ]
    )
    assert rc == 0
    artifact = json.loads(ledger.section_path(root, "0001").read_text())
    assert artifact["dispatchFailures"] == []


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


def test_mark_done_survives_concurrent_calls_for_different_slices(tmp_path):
    """Regression test for #1859: concurrent mark_done calls must not lose an update.

    Each thread flips a different slice's status. Without locked_state's
    serialization, a thread's read-modify-write can interleave with another's
    and silently clobber it (last writer wins). A threading.Barrier forces
    every thread to start its call at the same instant, maximizing the chance
    the old, unguarded code would have exhibited the race.
    """
    import threading

    n = 8
    slices = [{"id": f"{i:04d}", "files": [f"src/{i}.ts"], "is_declarative": False} for i in range(n)]
    ledger.init_ledger(slices, cap=50, root=str(tmp_path))

    barrier = threading.Barrier(n)

    def _mark(slice_id):
        barrier.wait()
        ledger.mark_done(str(tmp_path), slice_id)

    threads = [threading.Thread(target=_mark, args=(s["id"],)) for s in slices]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    result = ledger.read_ledger(str(tmp_path))
    statuses = {entry["id"]: entry["status"] for entry in result["slices"]}
    assert statuses == {s["id"]: ledger.STATUS_DONE for s in slices}


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


# --- Slice 2, Step 2.1: pending on non-empty dispatchFailures -----------------


def test_pending_treats_nonempty_dispatch_failures_as_pending(tmp_path):
    ledger.init_ledger(_slices(), cap=50, root=str(tmp_path))
    ledger.write_section(
        _slices()[0],
        [],
        panel=["correctness-review"],
        root=str(tmp_path),
        dispatch_failures=[{"agentName": "structure-review", "attempts": 2}],
    )
    ledger.write_section(_slices()[1], [], panel=["correctness-review"], root=str(tmp_path))
    # 0001 recorded a dispatch failure -> still pending despite its artifact
    # existing; 0002 has no failures -> done.
    assert _ids(ledger.pending_slices(_slices(), str(tmp_path))) == ["0001"]


def test_pending_treats_empty_dispatch_failures_as_done(tmp_path):
    ledger.init_ledger(_slices(), cap=50, root=str(tmp_path))
    ledger.write_section(
        _slices()[0],
        [{"severity": "warning", "file": "src/a.ts", "line": 1, "message": "x"}],
        panel=["correctness-review"],
        root=str(tmp_path),
        dispatch_failures=[],
    )
    ledger.write_section(_slices()[1], [], panel=["correctness-review"], root=str(tmp_path))
    # Findings present but no dispatch failures -> both slices done.
    assert ledger.pending_slices(_slices(), str(tmp_path)) == []


def test_pending_treats_malformed_artifact_as_pending_not_a_crash(tmp_path):
    ledger.init_ledger(_slices(), cap=50, root=str(tmp_path))
    ledger.write_section(_slices()[1], [], panel=["correctness-review"], root=str(tmp_path))
    ledger.section_path(str(tmp_path), "0001").write_text("not valid json{")
    # A corrupt artifact must not abort --resume for every slice -- only
    # the one slice with the bad artifact is re-reviewed, matching
    # consolidate.py's own tolerance for the same file set.
    assert _ids(ledger.pending_slices(_slices(), str(tmp_path))) == ["0001"]


def test_pending_treats_wrong_shape_artifact_as_pending_not_a_crash(tmp_path):
    ledger.init_ledger(_slices(), cap=50, root=str(tmp_path))
    ledger.write_section(_slices()[1], [], panel=["correctness-review"], root=str(tmp_path))
    ledger.section_path(str(tmp_path), "0001").write_text(json.dumps(["not", "a", "dict"]))
    assert _ids(ledger.pending_slices(_slices(), str(tmp_path))) == ["0001"]
