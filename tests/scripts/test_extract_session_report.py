"""Contract tests for the shipped downstream session-report extractor.

`plugins/dev-team/scripts/extract_session_report.py` shipped with no tests at
all, which is how issue #1990 survived four PRs: its transcript discovery
globbed only `<project>/<sessionId>.jsonl` and never opened the subagent
transcripts at `<project>/<sessionId>/subagents/agent-<id>.jsonl`, so every
dispatched agent's tokens, tool calls and run counts were absent from the
report — silently, since the report still looked complete.

Everything here builds synthetic transcript trees under `tmp_path` and invokes
the shipped script as a subprocess against `--projects-root`, exercising the
real entry point. No real session data, no network, no home-directory reads.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

SCRIPT = REPO_ROOT / "plugins" / "dev-team" / "scripts" / "extract_session_report.py"

PROJECT_SLUG = "-tmp-fixture-project"
PROJECT_CWD = "/tmp/fixture/project"
PROJECT_LABEL = "project"
SESSION_ID = "11111111-2222-3333-4444-555555555555"

USAGE = {
    "input_tokens": 10,
    "output_tokens": 20,
    "cache_creation_input_tokens": 30,
    "cache_read_input_tokens": 40,
}
USAGE_SUM = sum(USAGE.values())


def _assistant(text_blocks, *, agent=None, agent_id=None, sidechain=False, usage=USAGE):
    rec = {
        "type": "assistant",
        "sessionId": SESSION_ID,
        "cwd": PROJECT_CWD,
        "timestamp": "2026-08-20T12:00:00Z",
        "isSidechain": sidechain,
        "message": {"role": "assistant", "model": "claude-sonnet-5", "content": text_blocks},
    }
    if usage is not None:
        rec["message"]["usage"] = dict(usage)
    if agent is not None:
        rec["attributionAgent"] = agent
    if agent_id is not None:
        rec["agentId"] = agent_id
    return rec


def _bash(command, tool_id):
    return {"type": "tool_use", "id": tool_id, "name": "Bash", "input": {"command": command}}


def _write(path: Path, records) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


def _main_transcript(root: Path, records) -> Path:
    path = root / PROJECT_SLUG / f"{SESSION_ID}.jsonl"
    _write(path, records)
    return path


def _subagent_transcript(root: Path, agent_id: str, records, *, workflow=None) -> Path:
    base = root / PROJECT_SLUG / SESSION_ID / "subagents"
    if workflow:
        base = base / "workflows" / workflow
    path = base / f"agent-{agent_id}.jsonl"
    _write(path, records)
    return path


def _run(root: Path, out: Path, *extra) -> dict:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--all-projects", "--projects-root", str(root),
         "--out", str(out), *extra],
        capture_output=True, text=True, timeout=120, check=False,
    )
    assert proc.returncode == 0, f"extractor failed: {proc.stdout}\n{proc.stderr}"
    return json.loads(out.read_text(encoding="utf-8"))


@pytest.fixture
def tree(tmp_path):
    """A project with one main transcript and two review agents dispatched
    under the same session — the shape a `/code-review` panel produces."""
    root = tmp_path / "projects"
    _main_transcript(root, [
        _assistant([
            {"type": "text", "text": "dispatching"},
            {"type": "tool_use", "id": "t1", "name": "Agent",
             "input": {"subagent_type": "dev-team:correctness-review"}},
        ]),
    ])
    for agent_id, agent in (("aaa1", "dev-team:correctness-review"),
                            ("bbb2", "dev-team:angular-reactivity-review")):
        _subagent_transcript(root, agent_id, [
            _assistant([{"type": "text", "text": "reviewing"}],
                       agent=agent, agent_id=agent_id, sidechain=True),
        ])
    return root


# --- the defect itself ------------------------------------------------------


def test_subagent_usage_counts_toward_token_totals(tree, tmp_path):
    report = _run(tree, tmp_path / "r.json")
    combined = report["combined"]
    assert sum(combined["token"]["totals"].values()) == 3 * USAGE_SUM
    assert combined["transcripts"] == 1
    assert combined["subagent_transcripts"] == 2


def test_by_subagent_is_keyed_by_agent_name(tree, tmp_path):
    report = _run(tree, tmp_path / "r.json")
    by_subagent = report["combined"]["token"]["by_subagent"]
    assert by_subagent == {
        "main": 1,
        "correctness-review": 1,
        "angular-reactivity-review": 1,
    }


def test_regression_1990_signature_cannot_return(tree, tmp_path):
    """The report that exposed #1990 carried `by_subagent == {"main": N}` with
    no sidechain entry at all, while thousands of subagent transcripts sat
    unread on disk. That exact shape must be impossible whenever subagent
    transcripts exist in the tree."""
    report = _run(tree, tmp_path / "r.json")
    by_subagent = report["combined"]["token"]["by_subagent"]
    assert report["combined"]["subagent_transcripts"] > 0
    assert set(by_subagent) != {"main"}


def test_agent_seen_only_in_a_subagent_transcript_is_not_never_observed(tree, tmp_path):
    """`angular-reactivity-review` is dispatched by nobody in the main
    transcript here, exactly as in the real data that wrongly listed it (and
    six others) under `never_observed_agents` while it had run 25 times."""
    util = _run(tree, tmp_path / "r.json")["combined"]["utilization"]
    assert util["agents_invoked"]["angular-reactivity-review"] == 1
    assert "angular-reactivity-review" not in util["never_observed_agents"]


def test_workflow_subagents_nest_deeper_and_are_still_counted(tmp_path):
    """A Workflow's agents live one level further down, under
    `subagents/workflows/<runId>/`. A glob enumerating only the plain subagent
    depth misses them."""
    root = tmp_path / "projects"
    _main_transcript(root, [_assistant([{"type": "text", "text": "hi"}])])
    _subagent_transcript(root, "ccc3", [
        _assistant([{"type": "text", "text": "workflow work"}],
                   agent="dev-team:test-review", agent_id="ccc3", sidechain=True),
    ], workflow="wf_deadbeef")
    combined = _run(root, tmp_path / "r.json")["combined"]
    assert combined["subagent_transcripts"] == 1
    assert combined["utilization"]["agents_invoked"]["test-review"] == 1
    assert sum(combined["token"]["totals"].values()) == 2 * USAGE_SUM


def test_dispatches_are_reported_separately_from_runs(tree, tmp_path):
    """A dispatch is not a run. The main transcript dispatches
    correctness-review once; angular-reactivity-review ran without any visible
    dispatch. Both signals are reported, and neither is inferred from the
    other."""
    util = _run(tree, tmp_path / "r.json")["combined"]["utilization"]
    assert util["agent_dispatches"] == {"correctness-review": 1}
    assert util["agents_invoked"] == {
        "correctness-review": 1,
        "angular-reactivity-review": 1,
    }


def test_dispatch_counts_are_the_fallback_when_no_subagent_transcripts_exist(tmp_path):
    """An older harness wrote no subagent transcripts. Reporting zero runs for
    a tree like that would be a worse lie than reporting dispatches."""
    root = tmp_path / "projects"
    _main_transcript(root, [
        _assistant([
            {"type": "tool_use", "id": "t1", "name": "Agent",
             "input": {"subagent_type": "dev-team:security-review"}},
        ]),
    ])
    combined = _run(root, tmp_path / "r.json")["combined"]
    assert combined["subagent_transcripts"] == 0
    assert combined["utilization"]["agents_invoked"] == {"security-review": 1}


# --- signals that break if subagents are merged into the parent session -----


def test_sibling_agents_running_one_command_are_not_retries(tmp_path):
    """Subagents share their parent's sessionId. Bash history keyed on session
    would score a panel where each of three agents runs `git diff --cached`
    once as two retries."""
    root = tmp_path / "projects"
    _main_transcript(root, [_assistant([{"type": "text", "text": "go"}])])
    for i, agent_id in enumerate(("aaa1", "bbb2", "ccc3")):
        _subagent_transcript(root, agent_id, [
            _assistant([_bash("git diff --cached", f"t{i}")],
                       agent="dev-team:correctness-review", agent_id=agent_id, sidechain=True),
        ])
    combined = _run(root, tmp_path / "r.json")["combined"]
    assert combined["rework"]["retried_bash_commands"] == 0


def test_a_real_retry_within_one_thread_is_still_counted(tmp_path):
    root = tmp_path / "projects"
    _main_transcript(root, [
        _assistant([_bash("npm test", "t1")]),
        _assistant([_bash("npm test", "t2")]),
    ])
    combined = _run(root, tmp_path / "r.json")["combined"]
    assert combined["rework"]["retried_bash_commands"] == 1


def test_sibling_agents_verifying_do_not_register_repeated_verify_runs(tmp_path):
    root = tmp_path / "projects"
    _main_transcript(root, [_assistant([{"type": "text", "text": "go"}])])
    for i, agent_id in enumerate(("aaa1", "bbb2")):
        _subagent_transcript(root, agent_id, [
            _assistant([_bash("pytest tests/", f"t{i}")],
                       agent="dev-team:test-review", agent_id=agent_id, sidechain=True),
        ])
    combined = _run(root, tmp_path / "r.json")["combined"]
    assert combined["rework"]["repeated_verify_runs"] == 0


def test_session_count_is_unaffected_by_subagent_transcripts(tree, tmp_path):
    """Subagent records carry the parent's sessionId, so adding them must not
    inflate the session count."""
    assert _run(tree, tmp_path / "r.json")["combined"]["sessions"] == 1


def test_subagent_transcripts_group_under_their_own_project(tree, tmp_path):
    report = _run(tree, tmp_path / "r.json")
    assert list(report["projects"]) == [PROJECT_LABEL]
    assert report["projects"][PROJECT_LABEL]["subagent_transcripts"] == 2


# --- guarantees the module docstring makes ---------------------------------


def test_output_is_deterministic_except_generated_at(tree, tmp_path):
    first = _run(tree, tmp_path / "a.json")
    second = _run(tree, tmp_path / "b.json")
    first.pop("generated_at")
    second.pop("generated_at")
    assert first == second


def test_report_leaks_no_prompt_text_or_command_strings(tmp_path):
    root = tmp_path / "projects"
    _main_transcript(root, [
        _assistant([
            {"type": "text", "text": "SECRET_PROMPT_MARKER"},
            _bash("git commit -m 'SECRET_COMMIT_MARKER'", "t1"),
        ]),
    ])
    _subagent_transcript(root, "aaa1", [
        _assistant([{"type": "text", "text": "SECRET_SUBAGENT_MARKER"}],
                   agent="dev-team:doc-review", agent_id="aaa1", sidechain=True),
    ])
    out = tmp_path / "r.json"
    _run(root, out)
    raw = out.read_text(encoding="utf-8")
    for marker in ("SECRET_PROMPT_MARKER", "SECRET_COMMIT_MARKER", "SECRET_SUBAGENT_MARKER"):
        assert marker not in raw
    # ...while the metric the command feeds still lands.
    assert json.loads(raw)["combined"]["gate"]["commit_attempts"] == 1


def test_report_emits_no_absolute_paths(tree, tmp_path):
    out = tmp_path / "r.json"
    _run(tree, out)
    raw = out.read_text(encoding="utf-8")
    assert PROJECT_CWD not in raw
    assert str(tree) not in raw


def test_schema_version_marks_the_post_1990_era(tree, tmp_path):
    """Token, tool-call and rework totals all jump once subagents are counted.
    A consumer has to be able to tell the two eras apart rather than reading
    the jump as a behavior change."""
    assert _run(tree, tmp_path / "r.json")["schema"] == "downstream-session-report/v2"


# --- flags -----------------------------------------------------------------


def test_since_excludes_older_activity(tmp_path):
    root = tmp_path / "projects"
    old = _assistant([{"type": "text", "text": "ancient"}])
    old["timestamp"] = "2000-01-01T00:00:00Z"
    _main_transcript(root, [old])
    _subagent_transcript(root, "aaa1", [
        _assistant([{"type": "text", "text": "recent"}],
                   agent="dev-team:doc-review", agent_id="aaa1", sidechain=True),
    ])
    combined = _run(root, tmp_path / "r.json", "--since", "30")["combined"]
    assert sum(combined["token"]["totals"].values()) == USAGE_SUM
    assert combined["utilization"]["agents_invoked"] == {"doc-review": 1}


def test_until_excludes_newer_activity(tmp_path):
    root = tmp_path / "projects"
    _main_transcript(root, [_assistant([{"type": "text", "text": "in window"}])])
    combined = _run(root, tmp_path / "r.json", "--until", "2026-08-21")["combined"]
    assert sum(combined["token"]["totals"].values()) == USAGE_SUM
    combined = _run(root, tmp_path / "r2.json", "--until", "2026-08-19")["combined"]
    assert sum(combined["token"]["totals"].values()) == 0


def test_all_projects_covers_every_project_in_the_root(tmp_path):
    root = tmp_path / "projects"
    _main_transcript(root, [_assistant([{"type": "text", "text": "one"}])])
    other = root / "-tmp-other-repo" / f"{SESSION_ID}.jsonl"
    rec = _assistant([{"type": "text", "text": "two"}])
    rec["cwd"] = "/tmp/other/repo"
    _write(other, [rec])
    report = _run(root, tmp_path / "r.json")
    assert sorted(report["projects"]) == ["project", "repo"]


def test_single_project_mode_scopes_to_one_project(tmp_path):
    root = tmp_path / "projects"
    _main_transcript(root, [_assistant([{"type": "text", "text": "one"}])])
    _subagent_transcript(root, "aaa1", [
        _assistant([{"type": "text", "text": "sub"}],
                   agent="dev-team:doc-review", agent_id="aaa1", sidechain=True),
    ])
    other = root / "-tmp-other-repo" / f"{SESSION_ID}.jsonl"
    rec = _assistant([{"type": "text", "text": "two"}])
    rec["cwd"] = "/tmp/other/repo"
    _write(other, [rec])
    out = tmp_path / "r.json"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--project", PROJECT_CWD,
         "--projects-root", str(root), "--out", str(out)],
        capture_output=True, text=True, timeout=120, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert list(report["projects"]) == [PROJECT_LABEL]
    assert report["combined"]["subagent_transcripts"] == 1


def test_empty_root_exits_nonzero(tmp_path):
    root = tmp_path / "projects"
    root.mkdir()
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--all-projects", "--projects-root", str(root),
         "--out", str(tmp_path / "r.json")],
        capture_output=True, text=True, timeout=120, check=False,
    )
    assert proc.returncode == 1


def test_malformed_lines_are_skipped_not_fatal(tmp_path):
    root = tmp_path / "projects"
    path = root / PROJECT_SLUG / f"{SESSION_ID}.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(
        "not json at all\n"
        + json.dumps(_assistant([{"type": "text", "text": "ok"}])) + "\n"
        + "{truncated\n",
        encoding="utf-8",
    )
    combined = _run(root, tmp_path / "r.json")["combined"]
    assert sum(combined["token"]["totals"].values()) == USAGE_SUM


def test_out_of_window_agent_run_is_not_counted(tmp_path):
    """A subagent transcript whose every record predates `--since` did not run
    in the reported window. Counting the file rather than its in-window records
    would report a phantom run under the unattributed fallback."""
    root = tmp_path / "projects"
    _main_transcript(root, [_assistant([{"type": "text", "text": "recent"}])])
    ancient = _assistant([{"type": "text", "text": "old review"}],
                         agent="dev-team:doc-review", agent_id="aaa1", sidechain=True)
    ancient["timestamp"] = "2000-01-01T00:00:00Z"
    _subagent_transcript(root, "aaa1", [ancient])
    combined = _run(root, tmp_path / "r.json", "--since", "30")["combined"]
    assert combined["utilization"]["agents_invoked"] == {}
    assert "unattributed-agent" not in combined["token"]["by_subagent"]
