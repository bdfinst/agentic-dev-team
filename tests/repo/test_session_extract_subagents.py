"""`scripts/session_extract.py` counts dispatched agents (#1994).

It carried the same defect the shipped extractor had (#1990/#1991): discovery
globbed only `<project>/<sessionId>.jsonl`, so every dispatched agent's own
transcript under `<project>/<sessionId>/subagents/` was invisible. This one
feeds `/session-review` and the `session-digest.jsonl` trend stream the repo
uses to judge its own harness, so every token, rework and accuracy number it
ever recorded excluded subagent work — on the machine that motivated #1990,
about a third of the tokens and nearly half the cost.

These pin the ported behavior AND the traps #1991's review found the hard way,
so the port cannot regress to a shape the shipped extractor has already left
behind.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

EXTRACT = REPO_ROOT / "scripts" / "session_extract.py"

PROJECT_SLUG = "-tmp-fixture-project"
PROJECT_CWD = "/tmp/fixture/project"
SESSION_ID = "11111111-2222-3333-4444-555555555555"
USAGE = {
    "input_tokens": 10,
    "output_tokens": 20,
    "cache_creation_input_tokens": 30,
    "cache_read_input_tokens": 40,
}
USAGE_SUM = sum(USAGE.values())


def _assistant(blocks, *, agent=None, sidechain=False, usage=True):
    rec = {
        "type": "assistant",
        "sessionId": SESSION_ID,
        "cwd": PROJECT_CWD,
        "timestamp": "2026-08-20T12:00:00Z",
        "isSidechain": sidechain,
        "message": {"role": "assistant", "model": "claude-sonnet-5", "content": blocks},
    }
    if usage:
        rec["message"]["usage"] = dict(USAGE)
    if agent is not None:
        rec["attributionAgent"] = agent
    return rec


def _bash(command, tool_id):
    return {"type": "tool_use", "id": tool_id, "name": "Bash", "input": {"command": command}}


def _write(path: Path, records) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


def _main_transcript(root: Path, records) -> None:
    _write(root / PROJECT_SLUG / f"{SESSION_ID}.jsonl", records)


def _subagent(root: Path, agent_id: str, records, *, workflow=None) -> None:
    base = root / PROJECT_SLUG / SESSION_ID / "subagents"
    if workflow:
        base = base / "workflows" / workflow
    _write(base / f"agent-{agent_id}.jsonl", records)


def _digest(root: Path) -> dict:
    proc = subprocess.run(
        [sys.executable, str(EXTRACT), "--all-projects", "--projects-root", str(root)],
        capture_output=True, text=True, timeout=120, check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(proc.stdout)


@pytest.fixture
def tree(tmp_path):
    """A main session plus two review agents — a `/code-review` panel's shape."""
    root = tmp_path / "projects"
    _main_transcript(root, [
        _assistant([
            {"type": "tool_use", "id": "t1", "name": "Agent",
             "input": {"subagent_type": "dev-team:correctness-review"}},
        ]),
    ])
    for agent_id, agent in (("aaa1", "dev-team:correctness-review"),
                            ("bbb2", "dev-team:angular-reactivity-review")):
        _subagent(root, agent_id, [
            _assistant([{"type": "text", "text": "reviewing"}],
                       agent=agent, sidechain=True),
        ])
    return root


def test_subagent_usage_counts_toward_the_digest(tree):
    d = _digest(tree)
    assert sum(d["token"]["totals"].values()) == 3 * USAGE_SUM
    assert d["transcripts"] == 1
    assert d["subagent_transcripts"] == 2


def test_transcripts_counts_sessions_not_files(tree):
    """`digest["transcripts"] = len(paths)` in the CLI used to overwrite the
    count with every discovered file, so each agent run read as a session."""
    d = _digest(tree)
    assert d["transcripts"] == 1, "main-thread sessions only"
    assert d["sessions"] == 1


def test_by_agent_type_is_keyed_by_agent_name(tree):
    assert _digest(tree)["token"]["by_agent_type"] == {
        "main": 1, "correctness-review": 1, "angular-reactivity-review": 1,
    }


def test_an_agent_seen_only_in_its_own_transcript_is_not_never_observed(tree):
    util = _digest(tree)["utilization"]
    assert util["agents_invoked"]["angular-reactivity-review"] == 1
    assert "angular-reactivity-review" not in util["never_observed_agents"]


def test_runs_and_dispatches_are_reported_separately(tree):
    util = _digest(tree)["utilization"]
    assert util["agent_dispatches"] == {"correctness-review": 1}
    assert util["agents_invoked"] == {
        "correctness-review": 1, "angular-reactivity-review": 1,
    }


def test_workflow_agents_nest_deeper_and_do_not_invent_an_agent(tmp_path):
    """Real Workflow transcripts carry `attributionAgent: "workflow-subagent"`
    — a harness role. Counting it invents an agent while the one that actually
    ran stays in never_observed_agents."""
    root = tmp_path / "projects"
    _main_transcript(root, [_assistant([{"type": "text", "text": "hi"}])])
    _subagent(root, "ccc3", [
        _assistant([{"type": "text", "text": "wf"}],
                   agent="workflow-subagent", sidechain=True),
    ], workflow="wf_deadbeef")
    d = _digest(root)
    assert d["subagent_transcripts"] == 1
    assert sum(d["token"]["totals"].values()) == 2 * USAGE_SUM
    assert d["utilization"]["agents_invoked"] == {"unattributed": 1}
    assert "workflow-subagent" not in d["token"]["by_agent_type"]


def test_a_workflow_journal_is_not_a_transcript(tmp_path):
    """`subagents/workflows/<runId>/journal.jsonl` is harness bookkeeping."""
    root = tmp_path / "projects"
    _main_transcript(root, [_assistant([{"type": "text", "text": "hi"}])])
    _write(
        root / PROJECT_SLUG / SESSION_ID / "subagents" / "workflows" / "wf_x" / "journal.jsonl",
        [{"type": "started", "key": "v2:abc", "agentId": "a1"}],
    )
    d = _digest(root)
    assert d["subagent_transcripts"] == 0
    assert d["utilization"]["agents_invoked"] == {}


def test_a_session_transcript_keeps_any_filename(tmp_path):
    """Depth decides what a main transcript is, not filename shape.

    The harness uses `<sessionId>.jsonl`, but nothing guarantees it, and a
    name-shape filter silently drops sessions that differ — a worse failure
    than the one it prevents.
    """
    root = tmp_path / "projects"
    _write(root / PROJECT_SLUG / "not-a-uuid.jsonl", [_assistant([{"type": "text", "text": "x"}])])
    d = _digest(root)
    assert d["transcripts"] == 1
    assert sum(d["token"]["totals"].values()) == USAGE_SUM


def test_sibling_agents_running_one_command_are_not_retries(tmp_path):
    """Subagents share their parent's sessionId, so a session-keyed bash tally
    scored a panel's siblings running one command each as retries."""
    root = tmp_path / "projects"
    _main_transcript(root, [_assistant([{"type": "text", "text": "go"}])])
    for i, agent_id in enumerate(("aaa1", "bbb2", "ccc3")):
        _subagent(root, agent_id, [
            _assistant([_bash("git diff --cached", f"t{i}")],
                       agent="dev-team:correctness-review", sidechain=True),
        ])
    d = _digest(root)
    assert d["subagent_transcripts"] == 3, "guard: the files were actually read"
    assert d["rework"]["retried_bash_commands"] == 0


def test_a_real_retry_within_one_thread_is_still_counted(tmp_path):
    root = tmp_path / "projects"
    _main_transcript(root, [
        _assistant([_bash("npm test", "t1")]),
        _assistant([_bash("npm test", "t2")]),
    ])
    assert _digest(root)["rework"]["retried_bash_commands"] == 1


def test_an_inlined_sidechain_record_does_not_retitle_the_main_thread(tmp_path):
    """An older harness inlined sidechain turns into the parent transcript,
    where `isSidechain` is their only attribution. That signal is kept per
    record — but one attributed record must not relabel the whole session."""
    root = tmp_path / "projects"
    _main_transcript(root, [
        _assistant([{"type": "text", "text": "main"}]),
        _assistant([{"type": "text", "text": "inlined"}], sidechain=True),
    ])
    d = _digest(root)
    assert d["token"]["by_agent_type"] == {"main": 1, "sidechain": 1}
    assert d["transcripts"] == 1


def test_a_hostile_attribution_name_cannot_become_a_digest_key(tmp_path):
    root = tmp_path / "projects"
    _main_transcript(root, [_assistant([{"type": "text", "text": "hi"}])])
    _subagent(root, "aaa1", [
        _assistant([{"type": "text", "text": "x"}],
                   agent="/Users/alice/secret leaked", sidechain=True),
    ])
    proc = subprocess.run(
        [sys.executable, str(EXTRACT), "--all-projects", "--projects-root", str(root)],
        capture_output=True, text=True, timeout=120, check=False,
    )
    assert "/Users/alice" not in proc.stdout
    assert json.loads(proc.stdout)["utilization"]["agents_invoked"] == {"other": 1}


def test_the_schema_marks_the_post_1994_era(tree):
    """Token, tool-call and rework totals all jump once subagents are counted,
    and the two bash-rework metrics change basis. A trend stream holding both
    eras has to be able to tell them apart."""
    assert _digest(tree)["schema"] == "session-digest/v2"


def test_the_digest_emits_no_absolute_paths(tree, tmp_path):
    proc = subprocess.run(
        [sys.executable, str(EXTRACT), "--all-projects", "--projects-root", str(tree)],
        capture_output=True, text=True, timeout=120, check=False,
    )
    assert PROJECT_CWD not in proc.stdout
    assert str(tree) not in proc.stdout
