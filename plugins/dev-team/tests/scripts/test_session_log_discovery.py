"""Unit tests for scripts/lib/session_log/discovery.py (#2042, epic #2040).

Transcript path classification and enumeration, unified from the two
independently-drifted copies in `scripts/session_extract.py` and
`plugins/dev-team/scripts/extract_session_report.py`. See the module
docstring for the reconciliation notes this test locks down.
"""

from __future__ import annotations

import sys
from pathlib import Path

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "scripts" / "lib"))

from session_log import discovery

ROOT = Path("/root/.claude/projects")


def test_is_transcript_path_main_thread_session():
    assert discovery.is_transcript_path(ROOT, ROOT / "proj" / "session-id.jsonl")


def test_is_transcript_path_rejects_project_root_file():
    # Only two path parts below root (`<project>/<file>.jsonl`) qualifies —
    # a file directly at the root itself does not.
    assert not discovery.is_transcript_path(ROOT, ROOT / "session-id.jsonl")


def test_is_transcript_path_agent_dispatch():
    assert discovery.is_transcript_path(
        ROOT, ROOT / "proj" / "sess" / "subagents" / "agent-abc123.jsonl"
    )


def test_is_transcript_path_rejects_workflow_journal():
    # subagents/workflows/<runId>/journal.jsonl is harness bookkeeping, not a
    # transcript — the name doesn't match `agent-<id>.jsonl` (#1991).
    assert not discovery.is_transcript_path(
        ROOT,
        ROOT / "proj" / "sess" / "subagents" / "workflows" / "run1" / "journal.jsonl",
    )


def test_is_transcript_path_workflow_agent_nested_deeper():
    assert discovery.is_transcript_path(
        ROOT,
        ROOT
        / "proj"
        / "sess"
        / "subagents"
        / "workflows"
        / "run1"
        / "agent-xyz.jsonl",
    )


def test_is_transcript_path_outside_root_returns_false():
    assert not discovery.is_transcript_path(ROOT, Path("/elsewhere/file.jsonl"))


def test_is_subagent_transcript_true_for_any_nesting_depth():
    assert discovery.is_subagent_transcript(
        ROOT, ROOT / "proj" / "sess" / "subagents" / "agent-abc.jsonl"
    )
    assert discovery.is_subagent_transcript(
        ROOT,
        ROOT
        / "proj"
        / "sess"
        / "subagents"
        / "workflows"
        / "run1"
        / "agent-abc.jsonl",
    )


def test_is_subagent_transcript_false_for_main_thread():
    assert not discovery.is_subagent_transcript(ROOT, ROOT / "proj" / "sess.jsonl")


def test_is_subagent_transcript_outside_root_falls_back_to_full_parts():
    # relative_parts() falls back to path.parts (not an empty tuple) when the
    # path isn't under root — a "subagents" segment anywhere in an
    # unrelated absolute path still answers True, matching the pre-#2042
    # session_extract.py behavior this module preserves verbatim.
    assert discovery.is_subagent_transcript(
        ROOT, Path("/other/tree/subagents/agent-x.jsonl")
    )


def test_relative_parts_below_root():
    assert discovery.relative_parts(
        ROOT, ROOT / "proj" / "sess" / "subagents" / "agent-x.jsonl"
    ) == ("proj", "sess", "subagents", "agent-x.jsonl")


def test_relative_parts_outside_root_returns_full_parts():
    p = Path("/elsewhere/file.jsonl")
    assert discovery.relative_parts(ROOT, p) == p.parts


def test_sorted_paths_orders_by_full_path_string():
    paths = [Path("/a/z.jsonl"), Path("/a/m/x.jsonl"), Path("/a/b.jsonl")]
    assert discovery.sorted_paths(paths) == sorted(paths, key=lambda p: str(p))


def test_all_transcripts_finds_main_and_subagent_at_any_depth(tmp_path):
    proj = tmp_path / "proj"
    (proj).mkdir()
    (proj / "session1.jsonl").write_text("{}\n")
    sub = proj / "session2" / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-aaa1.jsonl").write_text("{}\n")
    nested = sub / "workflows" / "run1"
    nested.mkdir(parents=True)
    (nested / "agent-bbb2.jsonl").write_text("{}\n")
    # non-transcript bookkeeping must be excluded
    (nested / "journal.jsonl").write_text("{}\n")

    found = discovery.all_transcripts(tmp_path)
    names = sorted(p.name for p in found)
    assert names == ["agent-aaa1.jsonl", "agent-bbb2.jsonl", "session1.jsonl"]
    # deterministic total order (full path string)
    assert found == discovery.sorted_paths(found)
