"""Tests for hooks/review_verdict_recorder.py (#2166, Step 2.3).

Fixture-transcript style, mirroring `test_subagent_completion_guard.py`'s own
convention: a subagent transcript is a list of JSONL rows written to a temp
file, `main()` is exercised end-to-end via `subprocess` (so the real
`read_stdin_json()` path is exercised, not a monkeypatched stand-in), and the
written `review-verdicts.jsonl` rows are read back and asserted on.

Covers every Gherkin scenario in the plan's Slice 2 feature block
(plans/2164-verdict-ledger-writer.md), one test per scenario.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

_HOOK_DIR = Path(__file__).resolve().parents[2] / "hooks"
_HOOK_PY = _HOOK_DIR / "review_verdict_recorder.py"
_LIB_DIR = _HOOK_DIR / "lib"
for _p in (_HOOK_DIR, _LIB_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import review_verdict_recorder as recorder
from review_verdicts import SCOPE_MARKER_PREFIX  # type: ignore[import-not-found]

_VERDICTS_REL = Path(".claude") / "metrics" / "review-verdicts.jsonl"

# A real registered review agent (agents/structure-review.md exists).
_REVIEW_AGENT = "structure-review"
# A real, registered TEAM agent that is not a review lens
# (agents/software-engineer.md exists, but doesn't match agents/*-review.md).
_NON_REVIEW_AGENT = "software-engineer"
# Not a real agent file at all (no agents/phantom-review.md).
_UNREGISTERED_AGENT = "phantom-review"


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _write_transcript(tmp_path: Path, rows: list[dict], name: str = "agent-test.jsonl") -> str:
    path = tmp_path / "subagents"
    path.mkdir(parents=True, exist_ok=True)
    file_path = path / name
    with file_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    return str(file_path)


def _dispatch_row(in_scope_files: list[str], agent_id: str = "agent-1") -> dict:
    """The subagent transcript's first (dispatch-prompt) turn: role `user`,
    plain-string content carrying the Step 2.1 scope marker."""
    marker = SCOPE_MARKER_PREFIX + ", ".join(in_scope_files)
    return {
        "type": "user",
        "agentId": agent_id,
        "message": {
            "role": "user",
            "content": f"Review the following files for issues.\n\n{marker}\n",
        },
    }


def _result_row(result: dict, attribution_agent: str, agent_id: str = "agent-1") -> dict:
    """The subagent transcript's final (result) turn: an assistant row
    carrying the native `attributionAgent` field and the agent's JSON
    result as text."""
    return {
        "type": "assistant",
        "isSidechain": True,
        "agentId": agent_id,
        "attributionAgent": attribution_agent,
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": json.dumps(result)}],
        },
    }


def _write_file(tmp_path: Path, rel_path: str, content: str = "hello\n") -> None:
    target = tmp_path / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _run_hook(raw_stdin: bytes) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_HOOK_PY)],
        input=raw_stdin,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        capture_output=True,
        timeout=10,
        check=False,
    )


def _run_main(tmp_path: Path, transcript_path: str | None, session_id: str | None = "sess-1") -> int:
    payload: dict = {"cwd": str(tmp_path)}
    if transcript_path is not None:
        payload["transcript_path"] = transcript_path
    if session_id is not None:
        payload["session_id"] = session_id
    result = _run_hook(json.dumps(payload).encode())
    assert result.stdout == b""
    assert result.stderr == b""
    return result.returncode


def _read_rows(tmp_path: Path) -> list[dict]:
    path = tmp_path / _VERDICTS_REL
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


# ---------------------------------------------------------------------------
# Scenario: clean review agent result records a pass row per in-scope file
# ---------------------------------------------------------------------------


def test_clean_result_records_a_pass_row_per_in_scope_file(tmp_path: Path) -> None:
    files = ["a.py", "b.py", "c.py"]
    for f in files:
        _write_file(tmp_path, f, content=f"content of {f}\n")

    transcript = _write_transcript(
        tmp_path,
        [
            _dispatch_row(files),
            _result_row(
                {"status": "pass", "issues": [], "summary": "clean"},
                f"dev-team:{_REVIEW_AGENT}",
            ),
        ],
    )

    assert _run_main(tmp_path, transcript) == 0
    rows = _read_rows(tmp_path)
    assert len(rows) == 3
    by_path = {r["file_path"]: r for r in rows}
    assert set(by_path) == set(files)
    for f in files:
        row = by_path[f]
        assert row["outcome"] == "pass"
        assert row["lens"] == _REVIEW_AGENT
        assert row["file_content_hash"] == _sha256(f"content of {f}\n")
        assert row["session_id"] == "sess-1"
        assert "plugin_version" in row


# ---------------------------------------------------------------------------
# Scenario: a result with findings records a mixed verdict per file
# ---------------------------------------------------------------------------


def test_findings_result_records_mixed_verdict_per_file(tmp_path: Path) -> None:
    files = ["a.py", "b.py", "c.py"]
    for f in files:
        _write_file(tmp_path, f)

    transcript = _write_transcript(
        tmp_path,
        [
            _dispatch_row(files),
            _result_row(
                {
                    "status": "warn",
                    "issues": [
                        {
                            "severity": "warning",
                            "confidence": "medium",
                            "file": "b.py",
                            "line": 3,
                            "message": "something",
                        }
                    ],
                    "summary": "1 issue",
                },
                f"dev-team:{_REVIEW_AGENT}",
            ),
        ],
    )

    assert _run_main(tmp_path, transcript) == 0
    rows = _read_rows(tmp_path)
    by_path = {r["file_path"]: r["outcome"] for r in rows}
    assert by_path == {"a.py": "pass", "b.py": "findings", "c.py": "pass"}


# ---------------------------------------------------------------------------
# Scenario: an unregistered subagent_type is ignored
# ---------------------------------------------------------------------------


def test_unregistered_subagent_type_writes_no_rows(tmp_path: Path) -> None:
    _write_file(tmp_path, "a.py")
    transcript = _write_transcript(
        tmp_path,
        [
            _dispatch_row(["a.py"]),
            _result_row(
                {"status": "pass", "issues": [], "summary": "clean"},
                _UNREGISTERED_AGENT,
            ),
        ],
    )
    assert _run_main(tmp_path, transcript) == 0
    assert _read_rows(tmp_path) == []


# ---------------------------------------------------------------------------
# Scenario: a registered but non-review subagent_type is ignored
# ---------------------------------------------------------------------------


def test_registered_non_review_subagent_type_writes_no_rows(tmp_path: Path) -> None:
    _write_file(tmp_path, "a.py")
    transcript = _write_transcript(
        tmp_path,
        [
            _dispatch_row(["a.py"]),
            _result_row(
                {"status": "pass", "issues": [], "summary": "clean"},
                f"dev-team:{_NON_REVIEW_AGENT}",
            ),
        ],
    )
    assert _run_main(tmp_path, transcript) == 0
    assert _read_rows(tmp_path) == []


# ---------------------------------------------------------------------------
# Scenario: a dispatch with an empty scope marker writes no rows
# ---------------------------------------------------------------------------


def test_empty_scope_marker_writes_no_rows(tmp_path: Path) -> None:
    transcript = _write_transcript(
        tmp_path,
        [
            _dispatch_row([]),
            _result_row(
                {"status": "pass", "issues": [], "summary": "clean"},
                f"dev-team:{_REVIEW_AGENT}",
            ),
        ],
    )
    assert _run_main(tmp_path, transcript) == 0
    assert _read_rows(tmp_path) == []


# ---------------------------------------------------------------------------
# Scenario: a dispatch with exactly one file in scope writes exactly one row
# ---------------------------------------------------------------------------


def test_single_file_scope_writes_exactly_one_row(tmp_path: Path) -> None:
    _write_file(tmp_path, "only.py")
    transcript = _write_transcript(
        tmp_path,
        [
            _dispatch_row(["only.py"]),
            _result_row(
                {"status": "pass", "issues": [], "summary": "clean"},
                f"dev-team:{_REVIEW_AGENT}",
            ),
        ],
    )
    assert _run_main(tmp_path, transcript) == 0
    rows = _read_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["file_path"] == "only.py"
    assert rows[0]["outcome"] == "pass"


# ---------------------------------------------------------------------------
# Scenario: an in-scope file that no longer exists is skipped, not fatal
# ---------------------------------------------------------------------------


def test_deleted_in_scope_file_is_skipped_others_still_written(tmp_path: Path) -> None:
    _write_file(tmp_path, "a.py")
    _write_file(tmp_path, "c.py")
    # "b.py" is declared in scope but never created on disk.
    transcript = _write_transcript(
        tmp_path,
        [
            _dispatch_row(["a.py", "b.py", "c.py"]),
            _result_row(
                {"status": "pass", "issues": [], "summary": "clean"},
                f"dev-team:{_REVIEW_AGENT}",
            ),
        ],
    )
    assert _run_main(tmp_path, transcript) == 0
    rows = _read_rows(tmp_path)
    assert {r["file_path"] for r in rows} == {"a.py", "c.py"}


# ---------------------------------------------------------------------------
# Scenario Outline: a malformed or unreadable transcript fails open
# ---------------------------------------------------------------------------


def test_missing_transcript_path_key_writes_no_rows(tmp_path: Path) -> None:
    assert _run_main(tmp_path, None) == 0
    assert _read_rows(tmp_path) == []


def test_unreadable_transcript_path_writes_no_rows(tmp_path: Path) -> None:
    # A directory can never be read as transcript text -- OSError on read.
    unreadable = tmp_path / "not-a-file"
    unreadable.mkdir()
    assert _run_main(tmp_path, str(unreadable)) == 0
    assert _read_rows(tmp_path) == []


def test_non_json_transcript_content_writes_no_rows(tmp_path: Path) -> None:
    bad = tmp_path / "garbage.jsonl"
    bad.write_text("this is not json\nneither is this\n", encoding="utf-8")
    assert _run_main(tmp_path, str(bad)) == 0
    assert _read_rows(tmp_path) == []


# ---------------------------------------------------------------------------
# Scenario: a well-formed transcript with a missing/reformatted scope marker
# fails open
# ---------------------------------------------------------------------------


def test_missing_scope_marker_writes_no_rows(tmp_path: Path) -> None:
    transcript = _write_transcript(
        tmp_path,
        [
            {
                "type": "user",
                "agentId": "agent-1",
                "message": {
                    "role": "user",
                    "content": "Review these files: a.py, b.py\n",
                },
            },
            _result_row(
                {"status": "pass", "issues": [], "summary": "clean"},
                f"dev-team:{_REVIEW_AGENT}",
            ),
        ],
    )
    assert _run_main(tmp_path, transcript) == 0
    assert _read_rows(tmp_path) == []


# ---------------------------------------------------------------------------
# Scenario: the recorder trusts the dispatch prompt's declared scope; it is
# not independently re-verified against the diff
# ---------------------------------------------------------------------------


def test_trusts_declared_scope_without_reverifying_against_diff(tmp_path: Path) -> None:
    """The marker declares "trusted.py" in scope; nothing in this test ever
    constructs or checks a diff/git state for that path -- the recorder
    writes a pass row purely from the marker + the final JSON result,
    exactly the trust boundary Decision 4a documents."""
    _write_file(tmp_path, "trusted.py")
    transcript = _write_transcript(
        tmp_path,
        [
            _dispatch_row(["trusted.py"]),
            _result_row(
                {"status": "pass", "issues": [], "summary": "clean"},
                f"dev-team:{_REVIEW_AGENT}",
            ),
        ],
    )
    assert _run_main(tmp_path, transcript) == 0
    rows = _read_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["file_path"] == "trusted.py"
    assert rows[0]["outcome"] == "pass"


# ---------------------------------------------------------------------------
# Malformed final JSON result also fails open (Step 2.3 IMPLEMENT text,
# not a separate Gherkin scenario but part of this step's own contract).
# ---------------------------------------------------------------------------


def test_malformed_final_json_result_writes_no_rows(tmp_path: Path) -> None:
    _write_file(tmp_path, "a.py")
    transcript = _write_transcript(
        tmp_path,
        [
            _dispatch_row(["a.py"]),
            {
                "type": "assistant",
                "isSidechain": True,
                "agentId": "agent-1",
                "attributionAgent": f"dev-team:{_REVIEW_AGENT}",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "not json output at all"}],
                },
            },
        ],
    )
    assert _run_main(tmp_path, transcript) == 0
    assert _read_rows(tmp_path) == []


# ---------------------------------------------------------------------------
# Unit-level coverage of the documented Task/Agent dispatch-join fallback
# (used only when attributionAgent is absent from every record -- the spike
# recorded in this hook's own module docstring found no real transcript that
# needed it, but the fallback is still implemented per the plan and exercised
# here directly rather than left dead).
# ---------------------------------------------------------------------------


def test_fallback_resolves_subagent_type_via_task_agent_join(tmp_path: Path) -> None:
    session_dir = tmp_path / "session-1"
    subagents_dir = session_dir / "subagents"
    subagents_dir.mkdir(parents=True)

    subagent_transcript = subagents_dir / "agent-abc123.jsonl"
    subagent_rows = [
        {
            "type": "user",
            "agentId": "abc123",
            "message": {"role": "user", "content": "Review a.py"},
        },
        {
            "type": "assistant",
            "isSidechain": True,
            "agentId": "abc123",
            # No attributionAgent field at all on any record.
            "message": {"role": "assistant", "content": "done"},
        },
    ]
    with subagent_transcript.open("w", encoding="utf-8") as fh:
        for row in subagent_rows:
            fh.write(json.dumps(row) + "\n")

    parent_transcript = tmp_path / "session-1.jsonl"
    parent_rows = [
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "Task",
                        "input": {"subagent_type": f"dev-team:{_REVIEW_AGENT}"},
                    }
                ],
            },
        },
        {
            "type": "user",
            "toolUseResult": {"agentId": "abc123"},
            "message": {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "toolu_1"}],
            },
        },
    ]
    with parent_transcript.open("w", encoding="utf-8") as fh:
        for row in parent_rows:
            fh.write(json.dumps(row) + "\n")

    records = recorder._read_transcript_records(subagent_transcript)
    resolved = recorder._resolve_subagent_type(subagent_transcript, records)
    assert resolved == _REVIEW_AGENT
