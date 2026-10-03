"""Unit tests for hooks/checkpoint_dispatch_instrument.py.

PreToolUse (Agent|Task) hook: a review-lens dispatch that carries the scope
marker always writes one `ledger-skips.jsonl` row, so the stream no longer
depends on the model running `verdict_scope.py` by hand. Always exits 0.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from _repo_root import REPO_ROOT as _REPO_ROOT

_PLUGIN_DIR = _REPO_ROOT / "plugins" / "dev-team"
_HOOK = _PLUGIN_DIR / "hooks" / "checkpoint_dispatch_instrument.py"
_LIB = _PLUGIN_DIR / "hooks" / "lib"

_LENS = "correctness-review"
_MARKER = "Files in scope for this review: "


def _run(payload: dict) -> subprocess.CompletedProcess:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8"}
    return subprocess.run(
        [sys.executable, str(_HOOK)],
        input=json.dumps(payload).encode(),
        env=env,
        capture_output=True,
        timeout=10,
        check=False,
    )


def _dispatch(
    tmp_path: Path, prompt: str, subagent_type: str = f"dev-team:{_LENS}"
) -> dict:
    return {
        "tool_name": "Agent",
        "tool_input": {"subagent_type": subagent_type, "prompt": prompt},
        "cwd": str(tmp_path),
        "session_id": "sess-1",
    }


def _rows(tmp_path: Path) -> list[dict]:
    log = tmp_path / ".claude" / "metrics" / "ledger-skips.jsonl"
    if not log.is_file():
        return []
    return [json.loads(ln) for ln in log.read_text().splitlines() if ln.strip()]


if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from review_verdicts import (  # type: ignore[import-not-found]
    emit_review_verdict,
    hash_file,
)


def _seed_verdict(
    tmp_path: Path, rel: str, outcome: str = "pass", lens: str = _LENS
) -> None:
    emit_review_verdict(str(tmp_path), lens, rel, hash_file(tmp_path / rel), outcome)


def test_marked_lens_dispatch_writes_one_ledger_row(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x\n")
    (tmp_path / "b.py").write_text("y\n")
    result = _run(_dispatch(tmp_path, "Review the slice. " + _MARKER + "a.py, b.py"))
    assert result.returncode == 0
    rows = _rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["candidate_pairs"] == 2
    assert rows[0]["skipped_pairs"] == 0
    assert rows[0]["source"] == "dispatch-hook"
    assert rows[0]["session_id"] == "sess-1"


def test_row_counts_files_the_ledger_already_cleared(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x\n")
    (tmp_path / "b.py").write_text("y\n")
    _seed_verdict(tmp_path, "a.py")
    _run(_dispatch(tmp_path, _MARKER + "a.py, b.py"))
    rows = _rows(tmp_path)
    assert rows[0]["candidate_pairs"] == 2
    assert rows[0]["skipped_pairs"] == 1
    assert rows[0]["fully_skipped_lenses"] == []


def test_all_files_cleared_reports_the_lens_fully_skipped(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x\n")
    _seed_verdict(tmp_path, "a.py")
    _run(_dispatch(tmp_path, _MARKER + "a.py"))
    row = _rows(tmp_path)[0]
    assert row["skipped_pairs"] == row["candidate_pairs"] == 1
    assert row["fully_skipped_lenses"] == [_LENS]


def test_stale_content_is_not_counted_as_cleared(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x\n")
    _seed_verdict(tmp_path, "a.py")
    (tmp_path / "a.py").write_text("changed\n")
    _run(_dispatch(tmp_path, _MARKER + "a.py"))
    assert _rows(tmp_path)[0]["skipped_pairs"] == 0


def test_findings_verdict_and_other_lens_are_not_counted_as_cleared(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.py").write_text("x\n")
    (tmp_path / "b.py").write_text("y\n")
    _seed_verdict(tmp_path, "a.py", outcome="findings")
    _seed_verdict(tmp_path, "b.py", lens="structure-review")
    _run(_dispatch(tmp_path, _MARKER + "a.py, b.py"))
    assert _rows(tmp_path)[0]["skipped_pairs"] == 0


def test_hook_is_silent_and_handles_unprefixed_lens(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x\n")
    result = _run(_dispatch(tmp_path, _MARKER + "a.py", subagent_type=_LENS))
    assert result.stdout == b""
    assert result.stderr == b""
    assert len(_rows(tmp_path)) == 1


def test_unregistered_review_name_writes_nothing(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x\n")
    _run(_dispatch(tmp_path, _MARKER + "a.py", subagent_type="dev-team:phantom-review"))
    assert _rows(tmp_path) == []


def test_dispatch_without_marker_writes_nothing(tmp_path: Path) -> None:
    result = _run(_dispatch(tmp_path, "Review a.py and b.py"))
    assert result.returncode == 0
    assert _rows(tmp_path) == []


def test_non_review_agent_dispatch_writes_nothing(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x\n")
    result = _run(
        _dispatch(
            tmp_path, _MARKER + "a.py", subagent_type="dev-team:software-engineer"
        )
    )
    assert result.returncode == 0
    assert _rows(tmp_path) == []


def test_malformed_payloads_exit_zero_silently_and_write_nothing(
    tmp_path: Path,
) -> None:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    bad = [b"not json", b"[]", b"{}", b'{"tool_input": "x"}']
    for raw in bad:
        result = subprocess.run(
            [sys.executable, str(_HOOK)],
            input=raw,
            env=env,
            capture_output=True,
            timeout=10,
            check=False,
        )
        assert (result.returncode, result.stdout, result.stderr) == (0, b"", b"")
    non_string = _dispatch(tmp_path, "x")
    non_string["tool_input"]["prompt"] = 5
    assert _run(non_string).returncode == 0
    assert _rows(tmp_path) == []
