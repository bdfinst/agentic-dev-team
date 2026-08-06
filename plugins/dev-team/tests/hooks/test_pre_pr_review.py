"""Unit tests for hooks/pre_pr_review.py (#1886).

Ports the INTENT of `test_pre_commit_review.py`'s dispatch-corroboration
coverage (#1461/#1763) to the new PR-time trigger point: the hash binds to
`branch_diff_gate_hash()` (the whole branch diff vs. its base) instead of
`review_gate_hash()` (one commit's staged patch); the gate file is
`.claude/memory/.pr-review-passed`; the trigger command is `gh pr create`
instead of `git commit`; the bypass mechanism is the `PR_GATE_BYPASS_REASON`
env var instead of `--no-verify`/`-n` + `GATE_BYPASS_REASON`.

Deliberately NOT ported (see `pre_pr_review.py`'s own module docstring for
why): multi-target `-C` resolution, `-a`/pathspec-form-commit detection,
cosmetic-delta carry-forward — none apply to `gh pr create`'s command shape.
"""

from __future__ import annotations

import importlib.util as _importlib_util
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_HOOK = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "pre_pr_review.py"
_LEDGER_HOOK = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "agent_dispatch_ledger.py"
_REVIEW_GATE_HASH_CLI = (
    _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib" / "review_gate_hash.py"
)

_WINDOW_SECONDS = 1800

_TESTS_LIB = Path(__file__).resolve().parents[2] / "tests" / "lib"
if str(_TESTS_LIB) not in sys.path:
    sys.path.insert(0, str(_TESTS_LIB))

from hermetic import hermetic_git_env  # type: ignore[import-not-found]

_ppr_spec = _importlib_util.spec_from_file_location("pre_pr_review_direct", _HOOK)
assert _ppr_spec is not None and _ppr_spec.loader is not None
_ppr = _importlib_util.module_from_spec(_ppr_spec)
_ppr_spec.loader.exec_module(_ppr)


def _run(payload: dict, cwd: Path, extra_env: dict | None = None) -> subprocess.CompletedProcess[str]:
    proc_env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
    }
    if extra_env:
        proc_env.update(extra_env)
    return subprocess.run(
        ["python3", str(_HOOK)],
        input=json.dumps(payload),
        env=proc_env,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def _bare_repo_on_feature_branch(tmp_path: Path) -> Path:
    """A hermetic git repo: `main` with one commit, then a bare `feature`
    branch checked out from it with NO commits of its own yet — the caller
    adds whatever commit(s) the test needs."""
    env = hermetic_git_env(home=tmp_path)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, env=env, check=True)
    (tmp_path / "base.txt").write_text("base\n")
    subprocess.run(["git", "add", "base.txt"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "checkout", "-q", "-b", "feature"], cwd=tmp_path, env=env, check=True)
    return tmp_path


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A hermetic git repo: `main` with one commit, then a `feature` branch
    with one further commit — the minimal shape that gives
    `branch_diff_gate_hash("main", ...)` a non-empty diff."""
    _bare_repo_on_feature_branch(tmp_path)
    env = hermetic_git_env(home=tmp_path)
    (tmp_path / "a.ts").write_text("v1\n")
    subprocess.run(["git", "add", "a.ts"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "feature work"], cwd=tmp_path, env=env, check=True)
    return tmp_path


def _current_hash(repo: Path) -> str:
    lib_dir = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"
    if str(lib_dir) not in sys.path:
        sys.path.insert(0, str(lib_dir))
    import review_gate_hash as _rgh  # type: ignore[import-not-found]

    return _rgh.branch_diff_gate_hash("main", cwd=repo)


def _write_gate_file(repo: Path, content: str | None = None) -> str:
    h = content or _current_hash(repo)
    gate_path = repo / ".claude" / "memory" / ".pr-review-passed"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(h)
    return h


def _iso(dt) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_dispatch_events(repo: Path, agents: list[str], subject_hash: str, ts=None) -> None:
    when = ts or datetime.now(timezone.utc)
    log = repo / ".claude" / "metrics" / "boundary-events.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as fh:
        for agent in agents:
            fh.write(
                json.dumps(
                    {
                        "ts": _iso(when),
                        "hook": "agent_dispatch_ledger",
                        "tool": "Agent",
                        "decision": "record",
                        "matched_rule": agent,
                        "plugin_version": "0.0.0",
                        "subject_hash": subject_hash,
                    }
                )
                + "\n"
            )


def _write_dispatch_failure(repo: Path, agent: str, subject_hash: str, ts=None) -> None:
    when = ts or datetime.now(timezone.utc)
    log = repo / ".claude" / "metrics" / "boundary-events.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": _iso(when),
        "hook": "code-review",
        "tool": "Skill",
        "decision": "dispatch-failure",
        "matched_rule": agent,
        "plugin_version": "0.0.0",
        "subject_hash": subject_hash,
    }
    with log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def _write_doc_only_exemption(repo: Path, subject_hash: str, ts=None) -> None:
    when = ts or datetime.now(timezone.utc)
    log = repo / ".claude" / "metrics" / "boundary-events.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "ts": _iso(when),
                    "hook": "code-review",
                    "tool": "Skill",
                    "decision": "bypass",
                    "matched_rule": "doc-only-review-exempt",
                    "plugin_version": "0.0.0",
                    "subject_hash": subject_hash,
                }
            )
            + "\n"
        )


def _write_single_agent_exemption(repo: Path, subject_hash: str, ts=None) -> None:
    when = ts or datetime.now(timezone.utc)
    log = repo / ".claude" / "metrics" / "boundary-events.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "ts": _iso(when),
                    "hook": "code-review",
                    "tool": "Skill",
                    "decision": "bypass",
                    "matched_rule": "single-agent-review-exempt",
                    "plugin_version": "0.0.0",
                    "subject_hash": subject_hash,
                }
            )
            + "\n"
        )


# --- non-gate branches ------------------------------------------------------


def test_non_gh_pr_create_silent(repo: Path) -> None:
    result = _run({"tool_input": {"command": "git status"}, "cwd": str(repo)}, repo)
    assert result.returncode == 0
    assert result.stdout == ""


def test_malformed_stdin_silent(repo: Path) -> None:
    result = subprocess.run(
        ["python3", str(_HOOK)],
        input="not json{{{",
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0


# --- bypass ------------------------------------------------------------------


def test_bypass_without_reason_falls_through_to_normal_gate(repo: Path) -> None:
    # No gate file exists — the ordinary gate evaluation blocks, since the
    # unset env var means "no bypass attempted", not "bypass denied".
    result = _run({"tool_input": {"command": "gh pr create"}, "cwd": str(repo)}, repo)
    assert result.returncode == 2
    assert "BLOCKED" in result.stdout


def test_bypass_with_reason_allows_and_audits(repo: Path) -> None:
    result = _run(
        {"tool_input": {"command": "gh pr create"}, "cwd": str(repo)},
        repo,
        extra_env={"PR_GATE_BYPASS_REASON": "hotfix, review to follow"},
    )
    assert result.returncode == 0
    audit = repo / ".claude" / "metrics" / "gate-bypass-audit.jsonl"
    lines = [json.loads(ln) for ln in audit.read_text().splitlines() if ln]
    assert len(lines) == 1
    assert lines[0]["triggeredBy"] == "PR_GATE_BYPASS_REASON"
    assert lines[0]["reason"] == "hotfix, review to follow"


def test_bypass_with_empty_reason_falls_through_to_normal_gate(repo: Path) -> None:
    result = _run(
        {"tool_input": {"command": "gh pr create"}, "cwd": str(repo)},
        repo,
        extra_env={"PR_GATE_BYPASS_REASON": ""},
    )
    assert result.returncode == 2


# --- issue #1904 Bug 1: unresolvable base ref hard-blocks, never passes -----


def test_unresolvable_base_ref_hard_blocks_not_passes(tmp_path: Path) -> None:
    """Issue #1904 Bug 1: when `default_base_ref()` cannot resolve any
    candidate (not a git repo at all here — no `git init` ever ran), the
    gate must hard-block with the setup-failure message — NOT fall back to
    `"HEAD"`, hash `HEAD...HEAD` to `EMPTY_DIGEST`, and silently treat that
    as an ordinary (passable) empty diff."""
    result = _run({"tool_input": {"command": "gh pr create"}, "cwd": str(tmp_path)}, tmp_path)
    assert result.returncode == 2
    assert "Could not determine the review-gate's own state" in result.stdout
    assert not (tmp_path / ".claude" / "memory" / ".pr-review-passed").is_file()


# --- issue #1904 Bug 2a: bypass reachable even on gate-setup failure -------


def test_genuinely_empty_branch_diff_hard_blocks_as_setup_failure(tmp_path: Path) -> None:
    """Issue #1904 Bug 1: even when `default_base_ref()` DOES resolve (here,
    `feature` has no commits of its own yet, so `main`...`feature` diffs to
    nothing), `_prepare_gate()` must refuse to hand out the resulting
    `EMPTY_DIGEST` as an ordinary `current_hash` — it is a CONSTANT, not
    comparable evidence. Must fail with the setup-failure message, not the
    ordinary "gate file missing" message."""
    _bare_repo_on_feature_branch(tmp_path)
    result = _run({"tool_input": {"command": "gh pr create"}, "cwd": str(tmp_path)}, tmp_path)
    assert result.returncode == 2
    assert "Could not determine the review-gate's own state" in result.stdout


def test_empty_digest_gate_file_with_matching_empty_digest_dispatches_never_passes(
    tmp_path: Path,
) -> None:
    """The concrete security hazard Bug 1 exists to close: a `.pr-review-passed`
    file that happens to store `EMPTY_DIGEST` (whether hand-crafted, or a
    prior gate write made while the branch diff was empty) PLUS >= 2 genuine
    dispatch records whose `subject_hash` also happens to be `EMPTY_DIGEST`
    (recorded during ANY unrelated review made while nothing was staged,
    before the #1904 ledger fix) must NEVER corroborate a `gh pr create` on
    THIS branch, even though every individual comparison would otherwise
    "match". Before this fix, `_prepare_gate()` handed out `EMPTY_DIGEST` as
    an ordinary `current_hash`, `_hash_verdict()` matched it against the
    stored `EMPTY_DIGEST` gate file, and the ledger's `>= 2` distinct-dispatch
    check would have been satisfied by these unrelated dispatches — passing
    the gate on a constant, content-independent hash. This is the same
    `_bare_repo_on_feature_branch` empty-diff repo as the test above; the
    ledger + gate file here are the attacker/coincidence-controlled
    ingredients the old code would have accepted."""
    empty_digest = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    doc_repo = _bare_repo_on_feature_branch(tmp_path)
    _write_gate_file(doc_repo, content=empty_digest)
    _write_dispatch_events(doc_repo, ["security-review", "structure-review"], empty_digest)
    result = _run({"tool_input": {"command": "gh pr create"}, "cwd": str(doc_repo)}, doc_repo)
    assert result.returncode == 2
    assert "Could not determine the review-gate's own state" in result.stdout


def test_hash_verdict_defense_in_depth_rejects_empty_digest_directly() -> None:
    """Direct unit test of `_hash_verdict()`'s own empty-digest guard (issue
    #1904 Bug 1) — defense in depth alongside `_prepare_gate()`'s guard,
    covering a future caller that reaches this lens without going through
    `_prepare_gate()` first."""
    verdict = _ppr._hash_verdict(Path("/nonexistent/gate/file"), _ppr._EMPTY_DIGEST)
    assert verdict is not None
    assert verdict.passed is False
    assert verdict.matched_rule == "gate-setup-failure-empty-digest"


def test_bypass_reason_reaches_the_gate_even_on_setup_failure(tmp_path: Path) -> None:
    """Issue #1904 Bug 2a: `_GATE_SETUP_FAILURE_MESSAGE` itself documents
    `PR_GATE_BYPASS_REASON` as the way out — before this fix,
    `_prepare_gate()`'s failure returned BEFORE `_handle_bypass()` ever ran,
    so the documented bypass silently did nothing on this path. Same
    unresolvable-base-ref repo as the test above, but now with the bypass
    env var set — must allow the PR and audit the bypass with the `-1`
    sentinel file count (setup failed before any real file list existed)."""
    result = _run(
        {"tool_input": {"command": "gh pr create"}, "cwd": str(tmp_path)},
        tmp_path,
        extra_env={"PR_GATE_BYPASS_REASON": "gate infra broken, review manually"},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    audit = tmp_path / ".claude" / "metrics" / "gate-bypass-audit.jsonl"
    lines = [json.loads(ln) for ln in audit.read_text().splitlines() if ln]
    assert len(lines) == 1
    assert lines[0]["triggeredBy"] == "PR_GATE_BYPASS_REASON"
    assert lines[0]["stagedFileCount"] == -1


# --- hash verdict ------------------------------------------------------------


def test_missing_gate_file_blocks(repo: Path) -> None:
    result = _run({"tool_input": {"command": "gh pr create"}, "cwd": str(repo)}, repo)
    assert result.returncode == 2
    assert "BLOCKED" in result.stdout


def test_hash_mismatch_rejects_even_with_ample_dispatch_evidence(repo: Path) -> None:
    h = _current_hash(repo)
    _write_gate_file(repo, content="a-different-hash")
    _write_dispatch_events(repo, ["security-review", "structure-review"], h)
    result = _run({"tool_input": {"command": "gh pr create"}, "cwd": str(repo)}, repo)
    assert result.returncode == 2


def test_matching_gate_file_with_two_dispatches_passes_and_is_consumed(repo: Path) -> None:
    h = _write_gate_file(repo)
    _write_dispatch_events(repo, ["security-review", "structure-review"], h)
    result = _run({"tool_input": {"command": "gh pr create"}, "cwd": str(repo)}, repo)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not (repo / ".claude" / "memory" / ".pr-review-passed").is_file()


# --- dispatch corroboration --------------------------------------------------


def _touch_empty_ledger(repo: Path) -> None:
    """A ledger file that exists (successful read) but has zero qualifying
    entries — distinct from a MISSING ledger file, which is a read
    failure (see `test_missing_ledger_file_is_a_read_failure_not_no_dispatch_evidence`)."""
    log = repo / ".claude" / "metrics" / "boundary-events.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("")


def test_hash_match_with_no_dispatch_evidence_blocks_distinctly(repo: Path) -> None:
    _write_gate_file(repo)
    _touch_empty_ledger(repo)
    result = _run({"tool_input": {"command": "gh pr create"}, "cwd": str(repo)}, repo)
    assert result.returncode == 2
    assert "No genuine review-agent dispatch" in result.stdout


def test_hash_match_with_one_distinct_dispatch_is_insufficient(repo: Path) -> None:
    h = _write_gate_file(repo)
    _write_dispatch_events(repo, ["security-review"], h)
    result = _run({"tool_input": {"command": "gh pr create"}, "cwd": str(repo)}, repo)
    assert result.returncode == 2
    assert "Only 1 distinct" in result.stdout


def test_same_agent_dispatched_twice_counts_as_one_distinct(repo: Path) -> None:
    h = _write_gate_file(repo)
    _write_dispatch_events(repo, ["security-review", "security-review"], h)
    result = _run({"tool_input": {"command": "gh pr create"}, "cwd": str(repo)}, repo)
    assert result.returncode == 2
    assert "Only 1 distinct" in result.stdout


def test_stale_dispatch_evidence_blocks_distinctly(repo: Path) -> None:
    h = _write_gate_file(repo)
    stale = datetime.now(timezone.utc) - timedelta(seconds=_WINDOW_SECONDS + 120)
    _write_dispatch_events(repo, ["security-review", "structure-review"], h, ts=stale)
    result = _run({"tool_input": {"command": "gh pr create"}, "cwd": str(repo)}, repo)
    assert result.returncode == 2
    assert "outside the" in result.stdout


def test_dispatch_for_different_content_reports_different_content(repo: Path) -> None:
    _write_gate_file(repo)
    _write_dispatch_events(repo, ["security-review", "structure-review"], "unrelated-hash")
    result = _run({"tool_input": {"command": "gh pr create"}, "cwd": str(repo)}, repo)
    assert result.returncode == 2
    assert "different" in result.stdout.lower()


def test_missing_ledger_file_is_a_read_failure_not_no_dispatch_evidence(repo: Path) -> None:
    _write_gate_file(repo)
    result = _run({"tool_input": {"command": "gh pr create"}, "cwd": str(repo)}, repo)
    assert result.returncode == 2
    # No ledger file exists at all here — a real missing-ledger read failure.
    assert "Could not read the dispatch ledger" in result.stdout


# --- exemptions ---------------------------------------------------------------


def test_doc_only_exemption_satisfies_the_gate_without_dispatch_evidence(tmp_path: Path) -> None:
    doc_repo = _bare_repo_on_feature_branch(tmp_path)
    (doc_repo / "README.md").write_text("docs only\n")
    env = hermetic_git_env(home=doc_repo)
    subprocess.run(["git", "add", "README.md"], cwd=doc_repo, env=env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "docs"], cwd=doc_repo, env=env, check=True)
    h = _write_gate_file(doc_repo)
    _write_doc_only_exemption(doc_repo, h)
    result = _run({"tool_input": {"command": "gh pr create"}, "cwd": str(doc_repo)}, doc_repo)
    assert result.returncode == 0, result.stdout + result.stderr


def test_doc_only_exemption_is_rejected_when_branch_diff_is_not_documentation(
    repo: Path,
) -> None:
    h = _write_gate_file(repo)
    _write_doc_only_exemption(repo, h)
    result = _run({"tool_input": {"command": "gh pr create"}, "cwd": str(repo)}, repo)
    assert result.returncode == 2


def test_single_agent_exemption_with_one_real_dispatch_passes(repo: Path) -> None:
    h = _write_gate_file(repo)
    _write_dispatch_events(repo, ["security-review"], h)
    _write_single_agent_exemption(repo, h)
    result = _run({"tool_input": {"command": "gh pr create"}, "cwd": str(repo)}, repo)
    assert result.returncode == 0, result.stdout + result.stderr


def test_single_agent_exemption_without_any_dispatch_evidence_blocks(repo: Path) -> None:
    h = _write_gate_file(repo)
    _write_single_agent_exemption(repo, h)
    result = _run({"tool_input": {"command": "gh pr create"}, "cwd": str(repo)}, repo)
    assert result.returncode == 2


# --- registry-read-failure branch (previously uncovered, per #1904) --------


def test_registry_read_failure_produces_registry_read_failure_message(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pins the previously-uncovered `_REGISTRY_READ_FAILURE_MESSAGE`
    fail-closed branch: `_dispatch_failure_verdict()` must veto with this
    message — ahead of every other lens — whenever
    `evidence.dispatch_failure_agents is None` (a registry read failure),
    even with an otherwise-passing hash match and ample dispatch evidence."""
    lib_dir = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"
    if str(lib_dir) not in sys.path:
        sys.path.insert(0, str(lib_dir))
    import review_gate_corroboration as rgc  # type: ignore[import-not-found]

    h = _write_gate_file(repo)
    _write_dispatch_events(repo, ["security-review", "structure-review"], h)
    monkeypatch.setattr(rgc, "_registered_agents", lambda: None)

    gate_file = repo / ".claude" / "memory" / ".pr-review-passed"
    verdict = _ppr._evaluate_gate(gate_file, h, str(repo), [])
    assert verdict.passed is False
    assert verdict.matched_rule == "registry-read-failure"


# --- dispatch-failure veto (#1763) -------------------------------------------


def test_dispatch_failure_event_vetoes_gate_despite_two_distinct_dispatches(
    repo: Path,
) -> None:
    h = _write_gate_file(repo)
    _write_dispatch_events(repo, ["security-review", "structure-review"], h)
    _write_dispatch_failure(repo, "security-review", h)
    result = _run({"tool_input": {"command": "gh pr create"}, "cwd": str(repo)}, repo)
    assert result.returncode == 2
    assert "Dispatch failure recorded for security-review" in result.stdout


def test_superseding_record_event_clears_the_dispatch_failure_veto(repo: Path) -> None:
    h = _write_gate_file(repo)
    earlier = datetime.now(timezone.utc) - timedelta(seconds=5)
    _write_dispatch_failure(repo, "security-review", h, ts=earlier)
    _write_dispatch_events(repo, ["security-review", "structure-review"], h)
    result = _run({"tool_input": {"command": "gh pr create"}, "cwd": str(repo)}, repo)
    assert result.returncode == 0, result.stdout + result.stderr


# --- end-to-end: --since <base> --json -> gh pr create (#1904 Bug 2b) -------


def _run_ledger_dispatch(repo: Path, agent: str) -> None:
    """Invoke the REAL `agent_dispatch_ledger.py` hook via subprocess — the
    genuine ledger-stamping code path, not a hand-written fixture event.
    Mirrors a real Agent-tool dispatch of a registered review agent during a
    `--since <base>`-scoped `/code-review` run."""
    proc_env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    result = subprocess.run(
        ["python3", str(_LEDGER_HOOK)],
        input=json.dumps(
            {"tool_name": "Agent", "tool_input": {"subagent_type": agent}, "cwd": str(repo)}
        ),
        env=proc_env,
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _write_gate_file_via_branch_diff_cli(repo: Path) -> str:
    """Invoke the REAL `review_gate_hash.py --branch-diff` CLI — the genuine
    gate-hash-writing code path `skills/code-review/SKILL.md` step 9 uses —
    and write `.pr-review-passed` exactly as that step's bash block does."""
    completed = subprocess.run(
        ["python3", str(_REVIEW_GATE_HASH_CLI), "--branch-diff"],
        cwd=str(repo),
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        capture_output=True,
        text=True,
        check=True,
    )
    h = completed.stdout.strip()
    gate_path = repo / ".claude" / "memory" / ".pr-review-passed"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(h + "\n")
    return h


def test_since_scoped_review_then_gh_pr_create_passes_end_to_end(repo: Path) -> None:
    """Issue #1904 Bug 2b, closing the loop: simulates the REAL sequence
    `/pr` actually drives — `/code-review --since <base> --json` (a clean
    working tree, so real Agent dispatches during it) followed by
    `gh pr create` — using the genuine ledger-stamping
    (`agent_dispatch_ledger.py`) and gate-hash-writing
    (`review_gate_hash.py --branch-diff`) code paths, not hand-written
    fixture files that bypass that write logic. Before the Bug 1/2b fixes,
    this sequence could never pass: the ledger stamped `EMPTY_DIGEST` (a
    clean tree has no staged diff), which never matches the branch-diff hash
    step 9 writes."""
    # The `repo` fixture already leaves the working tree clean (its last
    # action is a commit) — exactly `/pr` step 1's precondition before
    # invoking `/code-review --since <base>`.
    _run_ledger_dispatch(repo, "security-review")
    _run_ledger_dispatch(repo, "structure-review")
    _write_gate_file_via_branch_diff_cli(repo)

    result = _run({"tool_input": {"command": "gh pr create"}, "cwd": str(repo)}, repo)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not (repo / ".claude" / "memory" / ".pr-review-passed").is_file()


# --- degraded-import fallback shape -----------------------------------------


def test_degraded_ledger_evidence_field_shape_matches_real_ledger_evidence() -> None:
    """The degraded-import stand-in's field names must track the real
    `LedgerEvidence` NamedTuple — a future field added to one without the
    other silently leaves the degraded path non-decisive with no signal."""
    lib_dir = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"
    if str(lib_dir) not in sys.path:
        sys.path.insert(0, str(lib_dir))
    import review_gate_corroboration as rgc  # type: ignore[import-not-found]

    real_fields = set(rgc.LedgerEvidence._fields)
    degraded_fields = {
        "agents_in_window",
        "any_dispatch_ever",
        "same_subject_dispatch_ever",
        "read_failure_reason",
        "dispatch_failure_agents",
    }
    assert degraded_fields == real_fields
