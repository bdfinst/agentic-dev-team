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
    # Guard: `transcripts == 1` is also true if subagent files are never read,
    # which is the regression this suite exists to catch.
    assert d["subagent_transcripts"] == 2
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
    # A REAL agent transcript beside it, so the assertion proves the journal is
    # filtered out rather than the whole subagents/ tree being skipped.
    _subagent(root, "real1", [
        _assistant([{"type": "text", "text": "real"}],
                   agent="dev-team:doc-review", sidechain=True),
    ], workflow="wf_x")
    d = _digest(root)
    assert d["subagent_transcripts"] == 1
    assert d["utilization"]["agents_invoked"] == {"doc-review": 1}


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


# --- findings from the #1994 review panel ----------------------------------


def _sync(root: Path, out_dir: Path, host="testhost"):
    proc = subprocess.run(
        [sys.executable, str(EXTRACT), "--sync-out", str(out_dir / "session-digest.jsonl"),
         "--watermark", str(out_dir / "wm.json"), "--projects-root", str(root),
         "--host", host],
        capture_output=True, text=True, timeout=120, check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    f = out_dir / "session-digest.jsonl"
    return [json.loads(x) for x in f.read_text().splitlines()] if f.exists() else []


def test_sync_emits_one_record_per_session_not_per_transcript(tree, tmp_path):
    """A session's dispatched agents are part of that session, not sessions of
    their own. Emitting per file labelled each `session_id = path.stem`, so an
    agent transcript became a fabricated session `agent-<id>` — and rollup()
    counts len(records) as sessions, inflating the denominator escalate()
    divides friction by and the --cost-log series the CI gate baselines on.
    """
    out = tmp_path / "digests" / "testhost"
    out.mkdir(parents=True)
    records = _sync(tree, out)
    assert len(records) == 1, [r["session_id"] for r in records]
    assert records[0]["session_id"] == SESSION_ID
    # The agents' tokens are folded into their session's record.
    assert sum(records[0]["tokens"].values()) == 3 * USAGE_SUM


def test_sync_carries_agent_dispatches_through_to_rollup(tree, tmp_path):
    """rollup() reads utilization.agent_dispatches, so sync_record must emit
    it — otherwise the cross-machine view is permanently empty and an agent
    dispatched from inside another agent reads as never observed."""
    out = tmp_path / "digests" / "testhost"
    out.mkdir(parents=True)
    records = _sync(tree, out)
    assert records[0]["utilization"]["agent_dispatches"] == {"correctness-review": 1}

    proc = subprocess.run(
        [sys.executable, str(EXTRACT), "--rollup", str(out.parent)],
        capture_output=True, text=True, timeout=120, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    rolled = json.loads(proc.stdout)
    assert rolled["sessions"] == 1, "one session, whatever its agent count"
    assert rolled["utilization"]["agent_dispatches"] == {"correctness-review": 1}


def test_the_trend_record_carries_the_same_era_as_its_digest(tmp_path):
    """slim_record() stamped v1 onto v2-basis numbers, so "split the trend
    stream on schema" — the documented mechanism — silently could not work."""
    root = tmp_path / "projects"
    _main_transcript(root, [_assistant([{"type": "text", "text": "hi"}])])
    log = tmp_path / "trend.jsonl"
    proc = subprocess.run(
        [sys.executable, str(EXTRACT), "--all-projects", "--projects-root", str(root),
         "--append", str(log)],
        capture_output=True, text=True, timeout=120, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    trend = json.loads(log.read_text().splitlines()[0])
    assert trend["schema"] == json.loads(proc.stdout)["schema"] == "session-digest/v2"


def test_a_windows_file_path_is_reduced_to_its_basename(tmp_path):
    """os.path.basename splits on '/' only, so a Windows-form path came back
    whole — an absolute path with a username, in a cross-machine stream."""
    root = tmp_path / "projects"
    _main_transcript(root, [
        _assistant([{"type": "tool_use", "id": "t1", "name": "Edit",
                     "input": {"file_path": r"C:\Users\alice\proj\secrets.env"}}]),
        _assistant([{"type": "tool_use", "id": "t2", "name": "Edit",
                     "input": {"file_path": r"C:\Users\alice\proj\secrets.env"}}]),
    ])
    proc = subprocess.run(
        [sys.executable, str(EXTRACT), "--all-projects", "--projects-root", str(root)],
        capture_output=True, text=True, timeout=120, check=False,
    )
    assert "alice" not in proc.stdout
    assert json.loads(proc.stdout)["rework"]["repeated_file_edits"] == {"secrets.env": 2}


def test_a_hostile_skill_name_cannot_become_a_digest_key(tmp_path):
    """`skills_invoked` and the correction-attribution maps reach the synced
    stream. They were ungated one line from a gated sibling."""
    root = tmp_path / "projects"
    _main_transcript(root, [
        _assistant([{"type": "tool_use", "id": "t1", "name": "Skill",
                     "input": {"skill": "/Users/alice/secret skill"}}]),
    ])
    proc = subprocess.run(
        [sys.executable, str(EXTRACT), "--all-projects", "--projects-root", str(root)],
        capture_output=True, text=True, timeout=120, check=False,
    )
    assert "/Users/alice" not in proc.stdout
    assert json.loads(proc.stdout)["utilization"]["skills_invoked"] == {"other": 1}


def test_a_malformed_model_value_does_not_abort_the_run(tmp_path):
    """`model` was the one unguarded field among careful neighbours; a dict
    made it an unhashable key and aborted the whole extraction."""
    root = tmp_path / "projects"
    rec = _assistant([{"type": "text", "text": "hi"}])
    rec["message"]["model"] = {"not": "a string"}
    _write(root / PROJECT_SLUG / f"{SESSION_ID}.jsonl", [rec])
    assert sum(_digest(root)["token"]["totals"].values()) == USAGE_SUM


def test_an_undecodable_transcript_is_skipped_not_fatal(tmp_path):
    """UnicodeDecodeError is a ValueError, not an OSError — a transcript
    truncated mid-character by a crashed session aborted the whole run, and in
    --sync-out that loses the watermark and re-emits every session on retry."""
    root = tmp_path / "projects"
    _main_transcript(root, [_assistant([{"type": "text", "text": "ok"}])])
    (root / PROJECT_SLUG / "broken.jsonl").write_bytes(b'{"type":"assistant"}\n\xff\xfe bad\n')
    assert sum(_digest(root)["token"]["totals"].values()) == USAGE_SUM
