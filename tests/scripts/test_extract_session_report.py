"""Contract tests for `session_report.py --profile downstream`.

The downstream profile's predecessor shipped with no tests at
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
from datetime import datetime, timezone
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

SCRIPT = REPO_ROOT / "plugins" / "dev-team" / "scripts" / "session_report.py"

PROJECT_SLUG = "-tmp-fixture-project"
PROJECT_CWD = "/tmp/fixture/project"
PROJECT_LABEL = "project"
SESSION_ID = "11111111-2222-3333-4444-555555555555"
# Derived from the real clock, not a literal: `--since` is resolved against
# `datetime.now()` inside the script, so a hardcoded date silently becomes a
# time bomb that starts failing once wall-clock time passes the window.
NOW_ISO = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
ANCIENT_ISO = "2000-01-01T00:00:00Z"
_FUTURE_DATE = "2999-12-31"

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
        "timestamp": NOW_ISO,
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
        [sys.executable, str(SCRIPT), "--profile", "downstream", "--all-projects", "--projects-root", str(root),
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


def test_by_agent_type_is_keyed_by_agent_name(tree, tmp_path):
    report = _run(tree, tmp_path / "r.json")
    by_agent_type = report["combined"]["token"]["by_agent_type"]
    assert set(by_agent_type) == {
        "main",
        "correctness-review",
        "angular-reactivity-review",
    }
    # Each bucket is a real token breakdown (#2010), not the message count this
    # key used to carry under `token` — where an int read as a token figure and
    # was off by orders of magnitude from `token.totals`.
    assert by_agent_type["correctness-review"]["messages"] == 1
    assert by_agent_type["correctness-review"]["context_tokens"] > 0


def test_regression_1990_signature_cannot_return(tree, tmp_path):
    """The report that exposed #1990 carried `by_agent_type == {"main": N}` with
    no sidechain entry at all, while thousands of subagent transcripts sat
    unread on disk. That exact shape must be impossible whenever subagent
    transcripts exist in the tree."""
    report = _run(tree, tmp_path / "r.json")
    by_agent_type = report["combined"]["token"]["by_agent_type"]
    assert report["combined"]["subagent_transcripts"] > 0
    assert set(by_agent_type) != {"main"}


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
        # "workflow-subagent" is what real Workflow transcripts carry — a
        # harness role, not an agent name (verified: 217/217 on this machine).
        _assistant([{"type": "text", "text": "workflow work"}],
                   agent="workflow-subagent", agent_id="ccc3", sidechain=True),
    ], workflow="wf_deadbeef")
    combined = _run(root, tmp_path / "r.json")["combined"]
    assert combined["subagent_transcripts"] == 1
    assert sum(combined["token"]["totals"].values()) == 2 * USAGE_SUM
    # Its tokens count, but it must not invent an agent named after the harness.
    assert combined["utilization"]["agents_invoked"] == {"unattributed": 1}
    assert "workflow-subagent" not in combined["token"]["by_agent_type"]


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
    # Guard: without this, a regression to "subagent files are never read"
    # also yields 0 retries and this test would pass for the wrong reason.
    assert combined["subagent_transcripts"] == 3
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
    assert combined["subagent_transcripts"] == 2  # guard: files were actually read
    assert combined["rework"]["repeated_verify_runs"] == 0


def test_session_count_is_unaffected_by_subagent_transcripts(tree, tmp_path):
    """Subagent records carry the parent's sessionId, so adding them must not
    inflate the session count."""
    combined = _run(tree, tmp_path / "r.json")["combined"]
    assert combined["subagent_transcripts"] == 2  # guard: files were actually read
    assert combined["sessions"] == 1


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
    # Guard: the subagent marker cannot leak from a file that was never read.
    assert json.loads(raw)["combined"]["subagent_transcripts"] == 1
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
    assert _run(tree, tmp_path / "r.json")["schema"] == "downstream-session-report/v3"


# --- flags -----------------------------------------------------------------


def test_since_excludes_older_activity(tmp_path):
    root = tmp_path / "projects"
    old = _assistant([{"type": "text", "text": "ancient"}])
    old["timestamp"] = ANCIENT_ISO
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
    combined = _run(root, tmp_path / "r.json", "--until", _FUTURE_DATE)["combined"]
    assert sum(combined["token"]["totals"].values()) == USAGE_SUM
    combined = _run(root, tmp_path / "r2.json", "--until", "2000-01-02")["combined"]
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
        [sys.executable, str(SCRIPT), "--profile", "downstream", "--project", PROJECT_CWD,
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
        [sys.executable, str(SCRIPT), "--profile", "downstream", "--all-projects", "--projects-root", str(root),
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
    ancient["timestamp"] = ANCIENT_ISO
    _subagent_transcript(root, "aaa1", [ancient])
    combined = _run(root, tmp_path / "r.json", "--since", "30")["combined"]
    assert combined["utilization"]["agents_invoked"] == {}
    assert "unattributed" not in combined["token"]["by_agent_type"]
    # The out-of-window file must not be counted as an in-window transcript
    # either — the two figures share one `filters` block and must share a basis.
    assert combined["subagent_transcripts"] == 0


# --- guards added after the review panel found these (see PR #1990 discussion)


def test_workflow_journal_is_not_a_transcript(tmp_path):
    """`subagents/workflows/<runId>/journal.jsonl` is harness bookkeeping, not
    a transcript. Recursing without a filename filter swept it in as an agent
    run and — because it carries no `cwd` — sent project labelling down the
    fallback that emitted a raw path slug."""
    root = tmp_path / "projects"
    _main_transcript(root, [_assistant([{"type": "text", "text": "hi"}])])
    journal = root / PROJECT_SLUG / SESSION_ID / "subagents" / "workflows" / "wf_x" / "journal.jsonl"
    _write(journal, [{"type": "started", "key": "v2:abc", "agentId": "a1"}])
    report = _run(root, tmp_path / "r.json")
    combined = report["combined"]
    assert combined["subagent_transcripts"] == 0
    assert combined["utilization"]["agents_invoked"] == {}
    assert list(report["projects"]) == [PROJECT_LABEL]


def test_a_project_with_no_resolvable_cwd_never_leaks_its_slug(tmp_path):
    """The project-slug directory name is an absolute path with separators
    rewritten. It must never reach the report, which promises basenames."""
    root = tmp_path / "projects"
    rec = _assistant([{"type": "text", "text": "no cwd here"}])
    del rec["cwd"]
    _write(root / PROJECT_SLUG / f"{SESSION_ID}.jsonl", [rec])
    out = tmp_path / "r.json"
    report = _run(root, out)
    raw = out.read_text(encoding="utf-8")
    assert PROJECT_SLUG not in raw
    assert "-tmp-" not in raw
    assert all(k.startswith("unknown-project-") for k in report["projects"])


def test_a_subagent_without_cwd_stays_in_its_parent_project(tmp_path):
    """Labelling each file independently split a cwd-less subagent transcript
    into a project of its own; the group's own directory resolves it."""
    root = tmp_path / "projects"
    _main_transcript(root, [_assistant([{"type": "text", "text": "hi"}])])
    rec = _assistant([{"type": "text", "text": "sub"}],
                     agent="dev-team:doc-review", agent_id="aaa1", sidechain=True)
    del rec["cwd"]
    _subagent_transcript(root, "aaa1", [rec])
    report = _run(root, tmp_path / "r.json")
    assert list(report["projects"]) == [PROJECT_LABEL]
    assert report["projects"][PROJECT_LABEL]["subagent_transcripts"] == 1


def test_a_hostile_attribution_name_cannot_become_a_report_key(tmp_path):
    """`attributionAgent` is chosen by the transcript's author — for a cloned
    repo, that is the repo's own `.claude/agents/*.md`. It must not pass
    through into a report the user is told to send to someone else."""
    root = tmp_path / "projects"
    _main_transcript(root, [_assistant([{"type": "text", "text": "hi"}])])
    _subagent_transcript(root, "aaa1", [
        _assistant([{"type": "text", "text": "x"}],
                   agent="/Users/alice/secret leaked here", agent_id="aaa1", sidechain=True),
    ])
    out = tmp_path / "r.json"
    combined = _run(root, out)["combined"]
    raw = out.read_text(encoding="utf-8")
    assert "/Users/alice" not in raw and "secret leaked here" not in raw
    assert combined["utilization"]["agents_invoked"] == {"other": 1}


def test_a_windows_file_path_is_reduced_to_its_basename(tmp_path):
    """os.path.basename splits on '/' only, so a Windows-form path came back
    whole — an absolute path with a username in it."""
    root = tmp_path / "projects"
    _main_transcript(root, [
        _assistant([{"type": "tool_use", "id": "t1", "name": "Edit",
                     "input": {"file_path": r"C:\Users\alice\proj\secrets.env"}}]),
        _assistant([{"type": "tool_use", "id": "t2", "name": "Edit",
                     "input": {"file_path": r"C:\Users\alice\proj\secrets.env"}}]),
    ])
    out = tmp_path / "r.json"
    combined = _run(root, out)["combined"]
    raw = out.read_text(encoding="utf-8")
    assert "alice" not in raw
    assert combined["rework"]["repeated_file_edits"] == {"secrets.env": 2}


def test_a_windows_style_cwd_still_resolves_to_its_project_basename(tmp_path):
    """`_project_label` used `os.path.basename(os.path.normpath(cwd))`, which
    splits on '/' only on this (POSIX) host — a Windows-authored transcript's
    backslash-separated `cwd` came back whole. `classify.safe_name`'s
    allowlist has no backslash in it, so the raw path never leaked, but the
    project label collapsed to "other" instead of resolving to the real
    project name (issue #2045: fixed by routing through the shared,
    Windows-path-aware `redact(..., from_path=True)` like every other
    path-derived field already does)."""
    root = tmp_path / "projects"
    rec = _assistant([{"type": "text", "text": "hi"}])
    rec["cwd"] = r"C:\Users\SENTINEL_WIN_USER\workspace\myproject"
    _write(root / PROJECT_SLUG / f"{SESSION_ID}.jsonl", [rec])
    out = tmp_path / "r.json"
    report = _run(root, out)
    raw = out.read_text(encoding="utf-8")
    assert "SENTINEL_WIN_USER" not in raw
    assert list(report["projects"]) == ["myproject"]


def test_a_projects_root_containing_a_subagents_segment_is_not_misread(tmp_path):
    """`"subagents" in path.parts` asked the absolute path, so a root under a
    directory of that name classified every transcript in the tree as a run."""
    root = tmp_path / "subagents" / "projects"
    _main_transcript(root, [_assistant([{"type": "text", "text": "hi"}])])
    combined = _run(root, tmp_path / "r.json")["combined"]
    assert combined["transcripts"] == 1
    assert combined["subagent_transcripts"] == 0
    assert set(combined["token"]["by_agent_type"]) == {"main"}
    assert combined["token"]["by_agent_type"]["main"]["messages"] == 1


def test_a_malformed_model_value_does_not_abort_the_run(tmp_path):
    """`model` was the one unguarded field: a non-str made it an unhashable
    dict key, aborting the whole extraction."""
    root = tmp_path / "projects"
    rec = _assistant([{"type": "text", "text": "hi"}])
    rec["message"]["model"] = {"not": "a string"}
    _write(root / PROJECT_SLUG / f"{SESSION_ID}.jsonl", [rec])
    combined = _run(root, tmp_path / "r.json")["combined"]
    assert sum(combined["token"]["totals"].values()) == USAGE_SUM


def test_main_thread_records_are_never_relabelled_by_attribution(tmp_path):
    """An older harness inlined sidechain records into the parent transcript.
    One attributed record there must not retitle the whole main thread."""
    root = tmp_path / "projects"
    _write(root / PROJECT_SLUG / f"{SESSION_ID}.jsonl", [
        _assistant([{"type": "text", "text": "main work"}]),
        _assistant([{"type": "text", "text": "inlined"}], agent="dev-team:doc-review"),
    ])
    combined = _run(root, tmp_path / "r.json")["combined"]
    assert set(combined["token"]["by_agent_type"]) == {"main"}
    assert combined["token"]["by_agent_type"]["main"]["messages"] == 2


def test_agent_runs_fall_back_to_dispatches_only_when_the_layout_is_absent(tmp_path):
    """The fallback asks 'did an older harness write this tree?'. Keying it on
    the window-scoped count made an all-out-of-window tree report zero runs."""
    root = tmp_path / "projects"
    _main_transcript(root, [
        _assistant([{"type": "tool_use", "id": "t1", "name": "Agent",
                     "input": {"subagent_type": "dev-team:security-review"}}]),
    ])
    ancient = _assistant([{"type": "text", "text": "old"}],
                         agent="dev-team:doc-review", agent_id="aaa1", sidechain=True)
    ancient["timestamp"] = ANCIENT_ISO
    _subagent_transcript(root, "aaa1", [ancient])
    combined = _run(root, tmp_path / "r.json", "--since", "30")["combined"]
    # The layout IS present, so runs — not dispatches — are the basis, and no
    # run fell in the window.
    assert combined["subagent_transcripts"] == 0
    assert combined["utilization"]["agents_invoked"] == {}
    assert combined["utilization"]["agent_dispatches"] == {"security-review": 1}


# --- #2010: per-dispatch context volume ------------------------------------


def test_per_agent_context_sums_to_the_report_totals(tree, tmp_path):
    """The load-bearing correctness property. Per-agent context is derived from
    the same usage records as `token.totals`, so the two must reconcile exactly.
    A mismatch means a dispatch was double-counted or dropped — and a per-lens
    cost decision made on either shape would be wrong in a way no other
    assertion here would catch."""
    combined = _run(tree, tmp_path / "r.json")["combined"]
    totals = combined["token"]["totals"]
    expected = (
        totals["input_tokens"]
        + totals["cache_read_input_tokens"]
        + totals["cache_creation_input_tokens"]
    )
    actual = sum(b["context_tokens"] for b in combined["token"]["by_agent_type"].values())
    assert actual == expected


def test_context_excludes_output_tokens(tree, tmp_path):
    """Context is what a dispatch CARRIED IN. Folding generation into it would
    make an agent that writes long findings look expensive to dispatch, which
    is the opposite of what this figure is for."""
    combined = _run(tree, tmp_path / "r.json")["combined"]
    for label, bucket in combined["token"]["by_agent_type"].items():
        carried = (
            bucket["input_tokens"]
            + bucket["cache_read_input_tokens"]
            + bucket["cache_creation_input_tokens"]
        )
        assert bucket["context_tokens"] == carried, label
        assert "output_tokens" in bucket, "output stays tracked, just separately"


def test_context_per_dispatch_is_none_rather_than_zero_without_dispatches(
    tree, tmp_path
):
    """`main` is not dispatched, so its per-dispatch figure is undefined. Zero
    would sort it as the cheapest row in any ranking built on this field —
    exactly backwards, since main carries the most context of anything."""
    combined = _run(tree, tmp_path / "r.json")["combined"]
    main = combined["token"]["by_agent_type"]["main"]
    assert main["dispatches"] == 0
    assert main["context_per_dispatch"] is None
    assert main["context_tokens"] > 0


def test_dispatches_are_counted_from_subagent_transcripts_not_messages(
    tree, tmp_path
):
    """One subagent transcript is one dispatch. Inferring dispatch count from
    message volume would divide by a number that grows with how chatty a lens
    is, making a verbose agent look cheap per dispatch."""
    combined = _run(tree, tmp_path / "r.json")["combined"]
    by_agent = combined["token"]["by_agent_type"]
    dispatched = sum(b["dispatches"] for b in by_agent.values())
    assert dispatched == combined["subagent_transcripts"]


def test_a_pre_2010_digest_does_not_corrupt_merged_totals():
    """Older digests carry an int (a message count) under this key. Summing it
    as tokens would silently inflate a cross-project total by a meaningless
    number, so the label is kept at zero instead of guessed at.

    Imported directly rather than driven through the CLI: the merge path only
    runs across multiple project digests, and the mixed-vintage case cannot be
    staged from transcripts alone."""
    import importlib.util

    path = REPO_ROOT / "plugins/dev-team/scripts/session_report.py"
    spec = importlib.util.spec_from_file_location("_esr_probe", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    dest = {}
    module._merge_agent_buckets(dest, {"doc-review": 7})
    assert dest["doc-review"]["input_tokens"] == 0
    assert dest["doc-review"]["messages"] == 0

    # A current-vintage bucket still merges normally alongside it.
    module._merge_agent_buckets(dest, {"doc-review": {"input_tokens": 5, "messages": 1}})
    assert dest["doc-review"]["input_tokens"] == 5
    assert dest["doc-review"]["messages"] == 1
