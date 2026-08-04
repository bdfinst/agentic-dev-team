"""Unit tests for hooks/pre_commit_review.py (#583).

Behavior parity with hooks/pre-commit-review.sh — the review gate that
blocks `git commit` unless a `.review-passed` file with a matching
staged-content hash exists in cwd. Content hashing is delegated to the
ported review_gate_hash module (#576).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_HOOK = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "pre_commit_review.py"

# Matches pre_commit_review.py's own WINDOW_SECONDS / _MIN_DISTINCT_DISPATCHES
# (#1461) — independent literals here, not an import, so a test regression
# actually pins the hook's real behavior rather than trivially agreeing with
# whatever the hook module currently says.
_WINDOW_SECONDS = 1800

_TESTS_LIB = Path(__file__).resolve().parents[2] / "tests" / "lib"
if str(_TESTS_LIB) not in sys.path:
    sys.path.insert(0, str(_TESTS_LIB))

# Direct module import (not subprocess) for unit-level testing of pure
# helpers like `_is_doc_only_changeset` — safe because `main()` only runs
# under `if __name__ == "__main__":`, so importing has no side effects.
import importlib.util as _importlib_util

from hermetic import hermetic_git_env  # type: ignore[import-not-found]

_pcr_spec = _importlib_util.spec_from_file_location("pre_commit_review_direct", _HOOK)
assert _pcr_spec is not None and _pcr_spec.loader is not None
_pcr = _importlib_util.module_from_spec(_pcr_spec)
_pcr_spec.loader.exec_module(_pcr)


def _run(
    payload: dict, cwd: Path, extra_env: dict | None = None
) -> subprocess.CompletedProcess[str]:
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


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A minimal hermetic git repo with one staged file."""
    env = hermetic_git_env(home=tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t"], cwd=tmp_path, env=env, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "t"], cwd=tmp_path, env=env, check=True
    )
    (tmp_path / "a.ts").write_text("v1\n")
    subprocess.run(["git", "add", "a.ts"], cwd=tmp_path, env=env, check=True)
    return tmp_path


def _current_hash(repo: Path) -> str:
    """Compute the review-gate hash via the Python lib (authoritative)."""
    import sys as _sys

    lib_dir = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"
    if str(lib_dir) not in _sys.path:
        _sys.path.insert(0, str(lib_dir))
    import review_gate_hash as _rgh  # type: ignore[import-not-found]

    return _rgh.review_gate_hash(cwd=repo)


def _iso(dt) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_dispatch_events(repo: Path, agents: list[str], subject_hash: str, ts=None) -> None:
    """Seed .claude/metrics/boundary-events.jsonl with one 'record' event
    per agent name (#1461) — the dispatch-ledger evidence
    `_evaluate_gate` reads. Defaults each event's ts to "now" (UTC) unless
    an explicit `ts` datetime is given. `subject_hash` (#1461 security
    review) must match the gate's current `review_gate_hash()` value for
    the event to count — the subject-binding fix that closes the
    review-A-commit-B bypass a corroboration mechanism without it would
    have."""
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


def _write_dispatch_failure(
    repo: Path,
    agent: str,
    subject_hash: str,
    ts=None,
    subject_hash_normalized: str | None = None,
) -> None:
    """Seed .claude/metrics/boundary-events.jsonl with one 'dispatch-failure'
    event (#1763) — the negative evidence `_dispatch_failure_verdict` (main
    pipeline) and `_cosmetic_carry_forward_verdict` (normalized-hash path)
    both read via `review_gate_corroboration.py`'s `dispatch_failure_agents`.
    Mirrors the exact (hook, tool, decision) tuple `boundary_events.py`'s
    `--event dispatch-failure` CLI writes (`_CLI_AGENT_EVENTS`)."""
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
    if subject_hash_normalized:
        entry["subject_hash_normalized"] = subject_hash_normalized
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


# --- non-gate branches ----------------------------------------------------


def test_non_commit_silent(repo: Path) -> None:
    r = _run({"tool_name": "Bash", "tool_input": {"command": "ls -la"}}, cwd=repo)
    assert r.returncode == 0
    assert r.stdout == ""
    assert r.stderr == ""


def test_no_verify_bypass_without_reason_blocks(repo: Path) -> None:
    """#709: the --no-verify escape hatch now requires a logged reason."""
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit --no-verify -m x"}},
        cwd=repo,
    )
    assert r.returncode == 2
    assert "GATE_BYPASS_REASON" in r.stdout
    assert "GATE_BYPASS_REASON" in r.stderr
    # #1367: stderr mirrors stdout byte-for-byte, not just a similar message.
    assert r.stdout == r.stderr
    assert not (repo / "metrics" / "gate-bypass-audit.jsonl").exists()


def test_no_verify_bypass_with_reason_allows_and_audits(repo: Path) -> None:
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit --no-verify -m x"}},
        cwd=repo,
        extra_env={"GATE_BYPASS_REASON": "hotfix, review to follow"},
    )
    assert r.returncode == 0
    audit = repo / ".claude" / "metrics" / "gate-bypass-audit.jsonl"
    assert audit.exists()
    lines = audit.read_text().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["triggeredBy"] == "--no-verify"
    assert entry["reason"] == "hotfix, review to follow"
    assert entry["stagedFileCount"] == 1
    assert "timestamp" in entry
    assert "branch" in entry
    assert "pluginVersion" in entry


def test_no_verify_bypass_empty_reason_blocks(repo: Path) -> None:
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit --no-verify -m x"}},
        cwd=repo,
        extra_env={"GATE_BYPASS_REASON": "   "},
    )
    assert r.returncode == 2
    assert "GATE_BYPASS_REASON" in r.stdout
    assert "GATE_BYPASS_REASON" in r.stderr


def test_bare_n_bypass_without_reason_blocks(repo: Path) -> None:
    """#709 AC4: bare -n is treated identically to --no-verify."""
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -n -m x"}},
        cwd=repo,
    )
    assert r.returncode == 2
    assert "GATE_BYPASS_REASON" in r.stderr
    assert "GATE_BYPASS_REASON" in r.stdout


def test_bypass_audit_uses_project_root_not_process_cwd(repo: Path) -> None:
    """Reproduces the bug: _record_bypass_audit built its path from a bare
    `Path("metrics")`, which resolves against the process's real OS cwd —
    not the project root the sibling emit_boundary_event(cwd, ...) call in
    the same `if` block correctly uses. Invoking the hook from a
    subdirectory of the project (process cwd = subdirectory) exposes the
    divergence: pre-fix, the audit line lands under
    <subdir>/metrics/gate-bypass-audit.jsonl; post-fix, it must land under
    <project-root>/.claude/metrics/gate-bypass-audit.jsonl."""
    sub = repo / "sub"
    sub.mkdir()
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit --no-verify -m x"}},
        cwd=sub,
        extra_env={"GATE_BYPASS_REASON": "hotfix from a subdirectory"},
    )
    assert r.returncode == 0
    audit = repo / ".claude" / "metrics" / "gate-bypass-audit.jsonl"
    assert audit.exists()
    entry = json.loads(audit.read_text().splitlines()[0])
    assert entry["reason"] == "hotfix from a subdirectory"
    # The bug's symptom: the line must NOT land under the subdirectory.
    assert not (sub / "metrics" / "gate-bypass-audit.jsonl").exists()
    assert not (sub / ".claude").exists()


def test_bare_n_bypass_with_reason_allows_and_audits(repo: Path) -> None:
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -n -m x"}},
        cwd=repo,
        extra_env={"GATE_BYPASS_REASON": "emergency rollback"},
    )
    assert r.returncode == 0
    audit = repo / ".claude" / "metrics" / "gate-bypass-audit.jsonl"
    entry = json.loads(audit.read_text().splitlines()[0])
    assert entry["triggeredBy"] == "-n"
    assert entry["reason"] == "emergency rollback"


def test_commit_with_nothing_staged_silent(tmp_path: Path) -> None:
    """No staged files → nothing to gate."""
    env = hermetic_git_env(home=tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t"], cwd=tmp_path, env=env, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "t"], cwd=tmp_path, env=env, check=True
    )
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}},
        cwd=tmp_path,
    )
    assert r.returncode == 0


def test_malformed_stdin_silent() -> None:
    r = subprocess.run(
        ["python3", str(_HOOK)],
        input="not json",
        env={
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0


# --- gate branches --------------------------------------------------------


def test_missing_gate_file_blocks(repo: Path) -> None:
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}, cwd=repo
    )
    assert r.returncode == 2
    assert "BLOCKED" in r.stdout
    assert "/code-review" in r.stdout
    assert "--no-verify" in r.stdout
    # #1367: mirrored to stderr so wrappers that only surface stderr on a
    # nonzero hook exit (rather than the hook's own stdout) still show why.
    assert "BLOCKED" in r.stderr


def test_matching_gate_file_passes_and_is_consumed(repo: Path) -> None:
    """#1461: a hash match alone is no longer sufficient — this now also
    requires >= 2 distinct genuine review-agent dispatches recorded in the
    recency window before the gate file's own write."""
    h = _current_hash(repo)
    gate_path = repo / ".claude" / "memory" / ".review-passed"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(h)
    _write_dispatch_events(repo, ["security-review", "structure-review"], h)
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}, cwd=repo
    )
    assert r.returncode == 0
    # Gate file consumed on success.
    assert not (repo / ".claude" / "memory" / ".review-passed").exists()


# ---------------------------------------------------------------------------
# #1461: dispatch-ledger corroboration scenarios (plan Slice 1, Step 1.3)
# ---------------------------------------------------------------------------


def test_hash_match_with_no_dispatch_evidence_blocks_distinctly(repo: Path) -> None:
    h = _current_hash(repo)
    gate_path = repo / ".claude" / "memory" / ".review-passed"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(h)
    # Ledger exists and is readable, but genuinely has zero qualifying
    # entries — distinct from a MISSING ledger, which this codebase treats
    # as a read failure (see review_gate_corroboration.py's module
    # docstring: many always-on guard hooks write this stream, so its
    # total absence at commit time is itself an infra signal).
    log = repo / ".claude" / "metrics" / "boundary-events.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("")
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}, cwd=repo
    )
    assert r.returncode == 2
    assert "No genuine review-agent dispatch found" in r.stdout
    # Distinguishable from the hash-mismatch message.
    assert "Code review required before committing" not in r.stdout


def test_missing_ledger_file_is_a_read_failure_not_no_dispatch_evidence(
    repo: Path,
) -> None:
    """The ledger file never having been created at all is bucketed as a
    read failure (many always-on guard hooks write it — its total absence
    is itself an infra signal), distinct from an existing-but-empty file."""
    h = _current_hash(repo)
    gate_path = repo / ".claude" / "memory" / ".review-passed"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(h)
    # No boundary-events.jsonl written at all.
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}, cwd=repo
    )
    assert r.returncode == 2
    assert "Could not read the dispatch ledger" in r.stdout


def test_evaluate_gate_unexpected_exception_in_ledger_evaluation_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#1461 fifth-round test-review finding: the outer `except Exception`
    in `_evaluate_gate` — the final fail-closed safety net for the whole
    corroboration mechanism — was never exercised; every existing
    fail-closed scenario in this suite routes through a returned
    `read_failure_reason`, never an actual raised exception escaping
    `_evaluate_ledger`/`_has_doc_only_exemption`/`_has_single_agent_exemption`/
    `_mtime_to_iso`. Calls `_evaluate_gate` directly (not via subprocess),
    monkeypatching `_evaluate_ledger` to raise, since that's the precise
    unit under test."""
    gate_file = tmp_path / ".review-passed"
    gate_file.write_text("some-hash")

    def _boom(*_args, **_kwargs):
        raise RuntimeError("simulated unexpected failure")

    monkeypatch.setattr(_pcr, "_evaluate_ledger", _boom)
    verdict = _pcr._evaluate_gate(gate_file, "some-hash", str(tmp_path), [])
    assert verdict.passed is False
    assert verdict.matched_rule == "dispatch-ledger-read-failure"


def test_hash_match_with_one_distinct_dispatch_blocks_as_insufficient(repo: Path) -> None:
    h = _current_hash(repo)
    gate_path = repo / ".claude" / "memory" / ".review-passed"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(h)
    _write_dispatch_events(repo, ["security-review"], h)
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}, cwd=repo
    )
    assert r.returncode == 2
    assert "Only 1 distinct review agent(s) dispatched" in r.stdout


def test_hash_match_with_same_agent_dispatched_twice_counts_as_one_distinct(
    repo: Path,
) -> None:
    h = _current_hash(repo)
    gate_path = repo / ".claude" / "memory" / ".review-passed"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(h)
    _write_dispatch_events(repo, ["security-review", "security-review"], h)
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}, cwd=repo
    )
    assert r.returncode == 2
    assert "Only 1 distinct review agent(s) dispatched" in r.stdout


def test_hash_match_with_stale_dispatch_evidence_blocks_distinctly(repo: Path) -> None:
    h = _current_hash(repo)
    gate_path = repo / ".claude" / "memory" / ".review-passed"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(h)
    stale_ts = datetime.now(timezone.utc) - timedelta(seconds=_WINDOW_SECONDS + 600)
    _write_dispatch_events(repo, ["security-review", "structure-review"], h, ts=stale_ts)
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}, cwd=repo
    )
    assert r.returncode == 2
    assert "outside the" in r.stdout and "window" in r.stdout
    assert "No genuine review-agent dispatch found" not in r.stdout


def test_hash_match_with_only_one_dispatch_inside_window_is_insufficient(
    repo: Path,
) -> None:
    h = _current_hash(repo)
    gate_path = repo / ".claude" / "memory" / ".review-passed"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    stale_ts = datetime.now(timezone.utc) - timedelta(seconds=_WINDOW_SECONDS + 600)
    _write_dispatch_events(repo, ["security-review"], h, ts=stale_ts)
    # Written BEFORE the gate file so its (second-truncated) "now" timestamp
    # can never land after `before_ts` (the gate's own mtime, also
    # second-truncated) — writing it after was a real race under parallel
    # test runs: a second-boundary crossing between the two statements
    # pushed this "fresh" dispatch's timestamp past `before_ts`, excluding
    # it from the window and dropping the in-window count from 1 to 0.
    _write_dispatch_events(repo, ["structure-review"], h)
    gate_path.write_text(h)
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}, cwd=repo
    )
    assert r.returncode == 2
    assert "Only 1 distinct review agent(s) dispatched" in r.stdout


def test_hash_mismatch_rejects_even_with_ample_dispatch_evidence(repo: Path) -> None:
    h = _current_hash(repo)
    gate_path = repo / ".claude" / "memory" / ".review-passed"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(h)
    _write_dispatch_events(repo, ["security-review", "structure-review", "arch-review"], h)
    # Edit the staged file's content after the gate write — hash now mismatches.
    (repo / "a.ts").write_text("v2-unreviewed\n")
    env = hermetic_git_env(home=repo)
    subprocess.run(["git", "add", "a.ts"], cwd=repo, env=env, check=True)
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}, cwd=repo
    )
    assert r.returncode == 2
    assert "Code review required before committing" in r.stdout


def test_rewritten_gate_file_anchors_on_its_own_new_mtime_not_original_dispatch(
    repo: Path,
) -> None:
    """A rewrite of .review-passed (new mtime, no fresh dispatch) is
    evaluated against its OWN new anchor — a hash rewrite alone is never
    itself dispatch evidence. Simulates "later rewritten" by advancing the
    gate file's mtime past the recency window relative to the (unchanged)
    original dispatch events, rather than depending on real wall-clock
    passage in a fast test."""
    h = _current_hash(repo)
    dispatch_ts = datetime.now(timezone.utc)
    _write_dispatch_events(repo, ["security-review", "structure-review"], h, ts=dispatch_ts)
    gate_path = repo / ".claude" / "memory" / ".review-passed"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(h)

    rewritten_mtime = (dispatch_ts + timedelta(seconds=_WINDOW_SECONDS + 600)).timestamp()
    os.utime(gate_path, (rewritten_mtime, rewritten_mtime))

    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}, cwd=repo
    )
    assert r.returncode == 2
    assert "outside the" in r.stdout and "window" in r.stdout


def test_ledger_read_failure_is_distinguishable_from_empty_ledger(repo: Path) -> None:
    h = _current_hash(repo)
    gate_path = repo / ".claude" / "memory" / ".review-passed"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(h)
    # Undecodable bytes make the whole ledger file unreadable, not merely
    # empty of qualifying entries.
    log = repo / ".claude" / "metrics" / "boundary-events.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_bytes(b"\xff\xfe\x00not valid utf-8\x80\x81")
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}, cwd=repo
    )
    assert r.returncode == 2
    assert "Could not read the dispatch ledger" in r.stdout
    assert "infra problem" in r.stdout
    assert "No genuine review-agent dispatch found" not in r.stdout


def _doc_only_repo(tmp_path: Path) -> Path:
    """A hermetic git repo with one staged DOCUMENTATION file (README.md),
    unlike the shared `repo` fixture which stages a.ts — needed to exercise
    the doc-only exemption's re-validated predicate (#1461 security
    re-review) honestly, rather than against staged code."""
    env = hermetic_git_env(home=tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t"], cwd=tmp_path, env=env, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "t"], cwd=tmp_path, env=env, check=True
    )
    (tmp_path / "README.md").write_text("docs\n")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, env=env, check=True)
    return tmp_path


def test_doc_only_exemption_satisfies_the_gate_without_dispatch_evidence(
    tmp_path: Path,
) -> None:
    repo = _doc_only_repo(tmp_path)
    h = _current_hash(repo)
    gate_path = repo / ".claude" / "memory" / ".review-passed"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(h)
    _write_doc_only_exemption(repo, h)
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}, cwd=repo
    )
    assert r.returncode == 0
    assert not (repo / ".claude" / "memory" / ".review-passed").exists()


def test_doc_only_exemption_is_rejected_when_staged_content_is_not_documentation(
    repo: Path,
) -> None:
    """#1461 security re-review: the doc-only exemption event is a
    self-asserted claim from the same party the gate constrains — an
    unconditional "the event exists, therefore trust it" check is the
    classic trust-the-client pattern. `repo`'s staged file is a.ts (code),
    not documentation, so a claimed doc-only exemption must NOT be honored:
    the gate falls through to requiring real dispatch evidence, exactly as
    if no exemption had been claimed at all."""
    h = _current_hash(repo)
    gate_path = repo / ".claude" / "memory" / ".review-passed"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(h)
    _write_doc_only_exemption(repo, h)
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}, cwd=repo
    )
    assert r.returncode == 2
    assert "No genuine review-agent dispatch found" in r.stdout


def _functional_config_repo(tmp_path: Path) -> Path:
    """A hermetic git repo with one staged FUNCTIONAL Claude-config markdown
    file (agents/security-review.md) — looks like documentation by
    extension, but must never classify as doc-only (#1461: this is the
    exact bypass class the exclusion exists to prevent)."""
    env = hermetic_git_env(home=tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t"], cwd=tmp_path, env=env, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "t"], cwd=tmp_path, env=env, check=True
    )
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "security-review.md").write_text("# altered agent body\n")
    subprocess.run(
        ["git", "add", "agents/security-review.md"], cwd=tmp_path, env=env, check=True
    )
    return tmp_path


def test_doc_only_exemption_is_rejected_for_functional_config_markdown(
    tmp_path: Path,
) -> None:
    """#1461 security re-review (test-review finding): a `.md` file under
    `agents/` is functional Claude-config, not documentation — the exact
    bypass class the doc-only exemption's `_FUNCTIONAL_CONFIG_SEGMENTS`
    guard exists to close. A claimed doc-only exemption over a staged
    change to `agents/security-review.md` must NOT be honored; the gate
    must fall through to requiring real dispatch evidence."""
    repo = _functional_config_repo(tmp_path)
    h = _current_hash(repo)
    gate_path = repo / ".claude" / "memory" / ".review-passed"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(h)
    _write_doc_only_exemption(repo, h)
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}, cwd=repo
    )
    assert r.returncode == 2
    assert "No genuine review-agent dispatch found" in r.stdout


def test_doc_only_exemption_is_rejected_for_mixed_doc_and_code_changeset(
    tmp_path: Path,
) -> None:
    """#1461 security re-review (test-review finding): a changeset must be
    ENTIRELY documentation to qualify for the doc-only exemption — one doc
    file staged alongside one code file must not slip through."""
    repo = _doc_only_repo(tmp_path)
    (repo / "a.ts").write_text("v1\n")
    env = hermetic_git_env(home=repo)
    subprocess.run(["git", "add", "a.ts"], cwd=repo, env=env, check=True)
    h = _current_hash(repo)
    gate_path = repo / ".claude" / "memory" / ".review-passed"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(h)
    _write_doc_only_exemption(repo, h)
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}, cwd=repo
    )
    assert r.returncode == 2
    assert "No genuine review-agent dispatch found" in r.stdout


def test_single_agent_exemption_without_any_dispatch_evidence_blocks(
    repo: Path,
) -> None:
    """#1461 security re-review: the single-agent exemption event alone,
    with ZERO real dispatch evidence behind it, previously passed the gate
    for an arbitrary changeset — the classic trust-the-client pattern. The
    sanctioned `--agent <name>` path always dispatches at least 1 genuine
    review agent, so requiring `n >= 1` alongside the exemption event
    closes this without regressing the documented workflow (see the next
    test)."""
    h = _current_hash(repo)
    gate_path = repo / ".claude" / "memory" / ".review-passed"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(h)
    _write_single_agent_exemption(repo, h)
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}, cwd=repo
    )
    assert r.returncode == 2
    assert "No genuine review-agent dispatch found" in r.stdout


def test_single_agent_exemption_with_one_real_dispatch_passes(repo: Path) -> None:
    """The sanctioned `--agent <name>` flow: exactly 1 genuine dispatch plus
    its exemption event — must still pass despite never reaching the
    `>= 2` distinct-dispatch floor."""
    h = _current_hash(repo)
    gate_path = repo / ".claude" / "memory" / ".review-passed"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(h)
    _write_dispatch_events(repo, ["security-review"], h)
    _write_single_agent_exemption(repo, h)
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}, cwd=repo
    )
    assert r.returncode == 0
    assert not (repo / ".claude" / "memory" / ".review-passed").exists()


def test_two_line_gate_file_with_correct_first_line_hash_passes_via_hash_verdict(
    repo: Path,
) -> None:
    """#1646: `_hash_verdict()` used to `.strip()` the WHOLE gate file and
    compare that against the single-line `current_hash` — for a 2-line gate
    file (#1627's optional normalized-hash second line) `stored` became
    `"line1\\nline2"`, which can never equal a single-line hash, so this
    lens always rejected regardless of whether the first line's hash was
    correct. Reproduces with a 2-line gate file whose first line IS the
    correct hash and asserts the gate passes directly through
    `_hash_verdict()` — not by falling through to the cosmetic-delta
    carry-forward lens, which only ever fires after a raw-hash MISMATCH."""
    h = _current_hash(repo)
    gate_path = repo / ".claude" / "memory" / ".review-passed"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    # Dispatch evidence must be written BEFORE the gate file — the
    # corroboration window is anchored on the gate file's own mtime and only
    # accepts evidence timestamped at or before it (see the invariant note
    # in _evaluate_gate). Writing the gate first leaves the dispatch write
    # free to land in a later wall-clock second under load, pushing it
    # outside the window (issue #1668's exact flake mechanism).
    _write_dispatch_events(repo, ["security-review", "correctness-review"], h)
    gate_path.write_text(f"{h}\nsome-normalized-hash-that-does-not-matter\n")
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}, cwd=repo
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert not gate_path.exists()
    audit_log = repo / ".claude" / "metrics" / "boundary-events.jsonl"
    assert audit_log.is_file()
    entries = [
        json.loads(ln) for ln in audit_log.read_text().splitlines() if ln.strip()
    ]
    assert not any(
        e.get("matched_rule") == "cosmetic-delta-carry-forward" for e in entries
    )


def test_single_agent_exemption_reachable_with_two_line_gate_file(repo: Path) -> None:
    """#1646: the single-agent exemption path (`_single_agent_exemption_verdict`)
    is only reached once `_hash_verdict()` returns `None` (hash OK). Before
    the fix, a 2-line gate file made `_hash_verdict()` always reject, so this
    sanctioned `--agent <name>` exemption was structurally unreachable
    whenever the gate file carried #1627's optional second line."""
    h = _current_hash(repo)
    gate_path = repo / ".claude" / "memory" / ".review-passed"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    # Dispatch/exemption evidence must be written BEFORE the gate file — see
    # the identical ordering note in the sibling test above (issue #1668).
    _write_dispatch_events(repo, ["security-review"], h)
    _write_single_agent_exemption(repo, h)
    gate_path.write_text(f"{h}\nsome-normalized-hash-that-does-not-matter\n")
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}, cwd=repo
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert not gate_path.exists()


def test_gate_path_setup_failure_fails_closed_not_open(repo: Path) -> None:
    """#1461 security re-review: `gate_file.parent.mkdir(...)` previously
    ran OUTSIDE `_evaluate_gate`'s own fail-closed try/except, in `main()`
    itself — so a setup failure there (e.g. `.claude/memory` existing as a
    regular file, or a read-only tree) escaped straight to this module's
    top-level fail-open `except Exception: sys.exit(0)`, deterministically
    turning a should-block commit into a silent allow. Reproduces by
    pre-creating `.claude/memory` as a FILE, not a directory, so `mkdir`
    raises."""
    claude_dir = repo / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    (claude_dir / "memory").write_text("not a directory")
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}, cwd=repo
    )
    assert r.returncode == 2, r.stdout + r.stderr
    # Distinct message/rule from a dispatch-LEDGER read failure (#1461
    # second security re-review, A09 finding): this is a gate-path SETUP
    # failure, a different bucket so the audit trail doesn't mislabel it.
    assert "Could not determine the review-gate's own state" in r.stdout
    # The fail-closed path's own audit trail: verify the block was actually
    # recorded, not just the exit code/message (test-review finding).
    audit_log = repo / ".claude" / "metrics" / "boundary-events.jsonl"
    assert audit_log.is_file()
    entries = [json.loads(ln) for ln in audit_log.read_text().splitlines() if ln.strip()]
    assert any(
        e.get("decision") == "block" and e.get("matched_rule") == "gate-setup-failure"
        for e in entries
    )


def test_staged_names_uses_payload_cwd_not_process_cwd(tmp_path: Path) -> None:
    """#1461 security re-review: `_staged_names()`/`_current_branch()` ran
    `git` without `cwd=`, using the hook PROCESS's real OS cwd — which can
    silently disagree with the payload's project root (`review_gate_hash`
    and `_resolve_file` were already fixed to use the payload cwd; these
    two lagged behind). Reproduces by running the hook process from an
    unrelated, non-repo directory while the payload's `cwd` points at the
    real repo with a staged, ungated commit in flight: before the fix,
    `_staged_names()` would see "nothing staged" (wrong cwd, not a git
    repo) and `main()` would silently return 0 — skipping the ENTIRE review
    gate, corroboration included, with no audit trail at all."""
    real_repo = tmp_path / "real-repo"
    real_repo.mkdir()
    env = hermetic_git_env(home=real_repo)
    subprocess.run(["git", "init", "-q"], cwd=real_repo, env=env, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t"], cwd=real_repo, env=env, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "t"], cwd=real_repo, env=env, check=True
    )
    (real_repo / "a.ts").write_text("v1\n")
    subprocess.run(["git", "add", "a.ts"], cwd=real_repo, env=env, check=True)

    unrelated_dir = tmp_path / "unrelated"
    unrelated_dir.mkdir()  # NOT a git repo — the hook process's real OS cwd

    r = _run(
        {
            "tool_name": "Bash",
            "tool_input": {"command": "git commit -m x"},
            "cwd": str(real_repo),
        },
        cwd=unrelated_dir,
    )
    assert r.returncode == 2, r.stdout + r.stderr
    assert "BLOCKED" in r.stdout
    assert "/code-review" in r.stdout
    assert "--no-verify" in r.stdout


def test_stale_gate_file_blocks(repo: Path) -> None:
    """Reviewed content changed → hash mismatch → block. Gate file NOT removed."""
    h = _current_hash(repo)
    gate_path = repo / ".claude" / "memory" / ".review-passed"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(h)
    # Edit the staged file's content.
    (repo / "a.ts").write_text("v2-unreviewed\n")
    env = hermetic_git_env(home=repo)
    subprocess.run(["git", "add", "a.ts"], cwd=repo, env=env, check=True)
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}, cwd=repo
    )
    assert r.returncode == 2
    assert "BLOCKED" in r.stdout
    assert "BLOCKED" in r.stderr
    # Gate file preserved because it did NOT match.
    assert (repo / ".claude" / "memory" / ".review-passed").exists()


def test_extra_staged_file_after_review_blocks(repo: Path) -> None:
    h = _current_hash(repo)
    gate_path = repo / ".claude" / "memory" / ".review-passed"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(h)
    (repo / "b.ts").write_text("new\n")
    env = hermetic_git_env(home=repo)
    subprocess.run(["git", "add", "b.ts"], cwd=repo, env=env, check=True)
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}, cwd=repo
    )
    assert r.returncode == 2
    assert "BLOCKED" in r.stdout
    assert "BLOCKED" in r.stderr


# ---------------------------------------------------------------------------
# Degraded-import `_resolve_file` fallback (finding #5)
# ---------------------------------------------------------------------------


def test_import_error_fallback_resolves_under_dot_claude() -> None:
    """When `from artifact_paths import resolve_file` fails, the module's
    own fallback `_resolve_file` must still land under
    `<repo-root>/.claude/<category>/<filename>` — not the bare
    `Path(category) / filename` bug Step 4.4 eliminated for the normal
    import path."""
    import importlib.util

    poisoned = dict(sys.modules)
    poisoned["artifact_paths"] = None  # type: ignore[assignment]
    real_modules = sys.modules
    sys.modules = poisoned  # type: ignore[assignment]
    try:
        spec = importlib.util.spec_from_file_location(
            "pre_commit_review_import_error_probe", _HOOK
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.modules = real_modules

    result = module._resolve_file("metrics", "gate-bypass-audit.jsonl")
    expected = _REPO_ROOT / ".claude" / "metrics" / "gate-bypass-audit.jsonl"
    assert result == expected


# ---------------------------------------------------------------------------
# _is_doc_only_changeset() — verifier-side doc-only re-derivation (#1461
# second security re-review: the first draft copied change_shape.py's loose
# heuristic verbatim, which is safe for lens-narrowing but exploitable as
# the sole gate for a zero-dispatch-evidence pass)
# ---------------------------------------------------------------------------


def test_is_doc_only_changeset_true_for_real_markdown() -> None:
    assert _pcr._is_doc_only_changeset(["README.md", "docs/guide.md"]) is True


def test_is_doc_only_changeset_false_for_code_file() -> None:
    assert _pcr._is_doc_only_changeset(["a.ts"]) is False


def test_is_doc_only_changeset_rejects_root_prefix_match_at_depth(tmp_path: Path) -> None:
    """A basename merely STARTING WITH a root-doc prefix must not count
    unless it's actually at the repo root — `src/license_manager.py` is
    code, not a LICENSE file, regardless of its basename.

    #1477 judgment call: under the CURRENT exact-match implementation, this
    test and `test_is_doc_only_changeset_rejects_root_prefix_match_with_
    code_extension` below both resolve to `_is_doc_only_changeset` returning
    `False` — but via genuinely different sub-branches of the same `if
    len(parts) == 1 and stem in _DOC_ROOT_NAMES` condition (this one
    short-circuits on `len(parts) == 1` being False for a non-root path;
    the other reaches `stem in _DOC_ROOT_NAMES` being False for a root-level
    path whose full basename, extension included, never equals a bare
    word). Each test also documents a DIFFERENT historical security-review
    finding (the depth axis vs. the extension axis, fixed in separate
    #1461 rounds) — kept as two separate regression artifacts rather than
    consolidated, per the "cheap insurance, distinct documented findings"
    guidance: a future mutant flipping `and` to `or`, or removing either
    half of that condition, is caught by one test but not the other."""
    assert _pcr._is_doc_only_changeset(["src/license_manager.py"]) is False
    assert _pcr._is_doc_only_changeset(["lib/notice_handler.js"]) is False
    assert _pcr._is_doc_only_changeset(["hooks/changelog_writer.py"]) is False


def test_is_doc_only_changeset_rejects_docs_dir_file_without_doc_extension() -> None:
    """A `docs/` directory membership alone is not sufficient — a doc-site
    build script or Sphinx `conf.py` is executable code."""
    assert _pcr._is_doc_only_changeset(["docs/conf.py"]) is False
    assert _pcr._is_doc_only_changeset(["docs/scripts/publish.sh"]) is False


def test_is_doc_only_changeset_accepts_root_doc_stem_without_extension() -> None:
    """A genuine extensionless root doc (LICENSE, NOTICE) still counts —
    only when it's actually at the repo root."""
    assert _pcr._is_doc_only_changeset(["LICENSE"]) is True
    assert _pcr._is_doc_only_changeset(["NOTICE"]) is True


def test_is_doc_only_changeset_rejects_root_prefix_match_with_code_extension() -> None:
    """#1461 THIRD security re-review: a root-level file whose basename
    starts with a doc prefix but carries a code extension (`license_manager
    .py`, `readme_deploy.sh`, `changelog.py`) must still be rejected — the
    prior fix closed the depth axis but left this extension axis open,
    since the root-prefix branch runs unconditionally after the doc-
    extension check merely fails, with no check on what the actual
    extension is.

    #1477: see `test_is_doc_only_changeset_rejects_root_prefix_match_at_
    depth`'s docstring above for the judgment call on why this test is kept
    separate rather than consolidated with it, despite both currently
    returning `False` for the same top-level reason."""
    assert _pcr._is_doc_only_changeset(["license_manager.py"]) is False
    assert _pcr._is_doc_only_changeset(["readme_deploy.sh"]) is False
    assert _pcr._is_doc_only_changeset(["changelog.py"]) is False
    assert _pcr._is_doc_only_changeset(["notice.yml"]) is False
    assert _pcr._is_doc_only_changeset(["authors.js"]) is False


def test_is_doc_only_changeset_rejects_extensionless_prefix_match() -> None:
    """#1461 FOURTH security re-review: an extensionless root-level file
    whose name merely STARTS WITH a root-doc name (`licensetool`,
    `readmegen`, `noticehook`) must still be rejected — root-doc matching
    is exact-name-only, never a prefix, so an arbitrary extensionless
    executable can't borrow a doc name's prefix to earn the exemption."""
    assert _pcr._is_doc_only_changeset(["licensetool"]) is False
    assert _pcr._is_doc_only_changeset(["readmegen"]) is False
    assert _pcr._is_doc_only_changeset(["noticehook"]) is False


def test_is_doc_only_changeset_rejects_non_doc_files_with_doc_extension() -> None:
    """#1461 FOURTH security re-review: `.txt` is a real doc extension
    (README.txt), but `requirements.txt`/`CMakeLists.txt` are supply-chain
    and build surface, not documentation, despite carrying that extension —
    denylisted by exact name."""
    assert _pcr._is_doc_only_changeset(["requirements.txt"]) is False
    assert _pcr._is_doc_only_changeset(["requirements-dev.txt"]) is False
    assert _pcr._is_doc_only_changeset(["CMakeLists.txt"]) is False


def test_is_doc_only_changeset_rejects_manifest_files_under_a_subdirectory() -> None:
    """#1461 FIFTH security re-review: the common multi-file pip layout
    (`requirements/base.txt`, `constraints/pins.txt`) escapes the exact-
    basename denylist above while still matching `_DOC_EXTENSIONS` — a
    directory-segment check closes it."""
    assert _pcr._is_doc_only_changeset(["requirements/base.txt"]) is False
    assert _pcr._is_doc_only_changeset(["constraints/pins.txt"]) is False
    # A genuine doc file under an unrelated directory is unaffected.
    assert _pcr._is_doc_only_changeset(["docs/requirements-overview.md"]) is True


def test_is_doc_only_changeset_rejects_templates_agents_path() -> None:
    """`templates/agents/` is functional Claude-config (SKILL.md's literal
    rule), never documentation, regardless of extension."""
    assert _pcr._is_doc_only_changeset(["templates/agents/python.md"]) is False


def test_is_doc_only_changeset_accepts_templates_readme_not_under_agents() -> None:
    """A `templates/README.md` outside `templates/agents/` is real
    documentation — only the `agents/` subtree is excluded, matching
    SKILL.md's stated rule (not the broader whole-`templates/`-tree
    exclusion `change_shape.py` uses for its own, lower-stakes purpose)."""
    assert _pcr._is_doc_only_changeset(["templates/README.md"]) is True


def test_is_doc_only_changeset_rejects_mixed_whitespace_only_entries() -> None:
    """Entries that are all blank/unusable must not vacuously pass."""
    assert _pcr._is_doc_only_changeset(["", "   "]) is False


def test_is_doc_only_changeset_rejects_functional_config_regardless_of_case() -> None:
    """#1461 third security re-review: path segments are lower-cased before
    comparison, so a case-insensitive checkout can't escape the
    functional-config exclusion via case alone (`Agents/foo.md`,
    `.Claude/x.md`)."""
    assert _pcr._is_doc_only_changeset(["Agents/foo.md"]) is False
    assert _pcr._is_doc_only_changeset([".Claude/x.md"]) is False


def test_is_doc_only_changeset_rejects_functional_config_names_by_stem() -> None:
    """#1461 fifth-round test-review finding: `_FUNCTIONAL_CONFIG_NAMES`
    (`claude.md`, `agents.md`) is a stem-only check — central to the
    doc-only exemption's threat model (a root-level `CLAUDE.md`/`AGENTS.md`
    drives agent/skill behavior, it is never "just documentation") — but
    had zero test coverage across all prior rounds. A root-level file, or
    one nested outside any `_FUNCTIONAL_CONFIG_SEGMENTS` directory, must
    still be rejected purely by its basename."""
    assert _pcr._is_doc_only_changeset(["CLAUDE.md"]) is False
    assert _pcr._is_doc_only_changeset(["notes/AGENTS.md"]) is False


def test_functional_config_segments_all_rejected() -> None:
    """Every `_FUNCTIONAL_CONFIG_SEGMENTS` entry, not just `agents`/`.claude`
    (already covered above) — `skills`, `prompts`, `knowledge` were
    untested (#1461 fifth-round test-review finding)."""
    assert _pcr._is_doc_only_changeset(["skills/foo.md"]) is False
    assert _pcr._is_doc_only_changeset(["prompts/foo.md"]) is False
    assert _pcr._is_doc_only_changeset(["knowledge/foo.md"]) is False


def test_doc_only_exemption_is_rejected_for_a_doc_named_code_file(
    tmp_path: Path,
) -> None:
    """#1461 second security re-review: end-to-end reproduction of the
    bypass the unit tests above target — staging a code file whose
    basename starts with a root-doc prefix, at a non-root depth, must not
    slip through the doc-only exemption."""
    env = hermetic_git_env(home=tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t"], cwd=tmp_path, env=env, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "t"], cwd=tmp_path, env=env, check=True
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "license_manager.py").write_text("def check(): pass\n")
    subprocess.run(
        ["git", "add", "src/license_manager.py"], cwd=tmp_path, env=env, check=True
    )
    h = _current_hash(tmp_path)
    gate_path = tmp_path / ".claude" / "memory" / ".review-passed"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(h)
    _write_doc_only_exemption(tmp_path, h)
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}},
        cwd=tmp_path,
    )
    assert r.returncode == 2
    assert "No genuine review-agent dispatch found" in r.stdout


# ---------------------------------------------------------------------------
# Staged-detection failure fails CLOSED, not silently through as "nothing
# staged" (#1461 second security re-review, correctness finding)
# ---------------------------------------------------------------------------


def test_corrupt_git_index_fails_closed_not_silently_allowed(repo: Path) -> None:
    """A `git diff --cached --name-only` failure (corrupt index) must block
    with a distinct setup-failure message, never be folded into "nothing
    staged" and silently allowed."""
    index_path = repo / ".git" / "index"
    index_path.write_bytes(b"not a valid git index file at all")
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}, cwd=repo
    )
    assert r.returncode == 2, r.stdout + r.stderr
    assert "Could not determine the review-gate's own state" in r.stdout


def test_gate_still_sees_staged_files_under_diff_relative_config(repo: Path) -> None:
    """#1461 third security re-review: a repo-local `diff.relative=true`
    config silently scopes/relativizes `git diff` output to the invocation
    cwd — without `-c diff.relative=false`, invoking the hook from a
    subdirectory would truncate `_staged_names()`'s view of what's staged,
    letting a real staged change outside that subdirectory go ungated."""
    env = hermetic_git_env(home=repo)
    subprocess.run(
        ["git", "config", "diff.relative", "true"], cwd=repo, env=env, check=True
    )
    sub = repo / "sub"
    sub.mkdir()
    # a.ts (already staged by the `repo` fixture) lives outside `sub/` —
    # under diff.relative, a `git diff --cached` run from `sub` would
    # normally see nothing.
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}, cwd=sub
    )
    assert r.returncode == 2, r.stdout + r.stderr
    assert "BLOCKED" in r.stdout
    assert "/code-review" in r.stdout


# ---------------------------------------------------------------------------
# "Different content" vs "stale" message distinction (#1461 second security
# re-review, correctness finding)
# ---------------------------------------------------------------------------


def test_dispatch_for_different_subject_hash_in_window_reports_different_content(
    repo: Path,
) -> None:
    h = _current_hash(repo)
    gate_path = repo / ".claude" / "memory" / ".review-passed"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(h)
    # Genuine, recent dispatches — but for a DIFFERENT changeset's hash.
    _write_dispatch_events(repo, ["security-review", "structure-review"], "a-different-hash")
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}, cwd=repo
    )
    assert r.returncode == 2
    assert "for different staged content" in r.stdout
    assert "outside the" not in r.stdout


# ---------------------------------------------------------------------------
# #1763: mechanical dispatch-failure gate veto, with supersession (plan
# Slice 3, Step 3.2)
# ---------------------------------------------------------------------------


def test_dispatch_failure_event_vetoes_gate_despite_two_distinct_dispatches(
    repo: Path,
) -> None:
    """The veto applies regardless of how many other agents genuinely
    dispatched and returned for this same subject_hash — it takes priority
    over the terminal distinct-dispatch-count lens."""
    h = _current_hash(repo)
    gate_path = repo / ".claude" / "memory" / ".review-passed"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(h)
    _write_dispatch_events(repo, ["security-review", "structure-review"], h)
    _write_dispatch_failure(repo, "correctness-review", h)
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}, cwd=repo
    )
    assert r.returncode == 2
    assert "Dispatch failure recorded for correctness-review" in r.stdout
    assert "not a code-review finding" in r.stdout


def test_superseding_record_event_clears_the_dispatch_failure_veto(repo: Path) -> None:
    """A LATER genuine "record" event for the same agent and hash supersedes
    and clears an earlier dispatch-failure — the recovered-on-a-normal-
    resume path."""
    h = _current_hash(repo)
    gate_path = repo / ".claude" / "memory" / ".review-passed"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(h)
    failure_ts = datetime.now(timezone.utc) - timedelta(seconds=60)
    _write_dispatch_failure(repo, "correctness-review", h, ts=failure_ts)
    # The superseding dispatch, plus one more distinct agent, clears the
    # >= 2 distinct-dispatch floor too.
    _write_dispatch_events(repo, ["correctness-review", "structure-review"], h)
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}, cwd=repo
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert not (repo / ".claude" / "memory" / ".review-passed").exists()


def test_dispatch_failure_event_for_a_different_hash_does_not_block(repo: Path) -> None:
    """A dispatch-failure event bound to unrelated staged content must never
    veto a gate whose own subject_hash has no failure of its own."""
    h = _current_hash(repo)
    gate_path = repo / ".claude" / "memory" / ".review-passed"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(h)
    _write_dispatch_failure(repo, "correctness-review", "a-different-hash")
    _write_dispatch_events(repo, ["security-review", "structure-review"], h)
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}, cwd=repo
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert not (repo / ".claude" / "memory" / ".review-passed").exists()


def test_dispatch_failure_veto_is_not_cleared_by_time_alone(repo: Path) -> None:
    """The veto is scoped only by subject_hash equality, never by
    `WINDOW_SECONDS` — a dispatch-failure event far outside the recency
    window, for unchanged content with no later superseding "record" event,
    must still block."""
    h = _current_hash(repo)
    gate_path = repo / ".claude" / "memory" / ".review-passed"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(h)
    stale_ts = datetime.now(timezone.utc) - timedelta(seconds=_WINDOW_SECONDS + 600)
    _write_dispatch_failure(repo, "correctness-review", h, ts=stale_ts)
    _write_dispatch_events(repo, ["security-review", "structure-review"], h)
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}, cwd=repo
    )
    assert r.returncode == 2
    assert "Dispatch failure recorded for correctness-review" in r.stdout


def test_dispatch_failure_message_names_infra_reason_remediation_and_bypass() -> None:
    """The rendered message covers all four required properties: agent
    name; dispatch/infra-not-finding framing; rerun-clears-it remediation;
    the standard --no-verify bypass line."""
    message = _pcr._dispatch_failure_message(frozenset({"correctness-review"}))
    assert "correctness-review" in message
    assert "dispatch/infra failure" in message
    assert "not a code-review finding" in message
    assert "clean rerun" in message and "clears this block" in message
    assert "To bypass: use git commit --no-verify" in message


def test_dispatch_failure_message_is_byte_identical_for_the_same_agents() -> None:
    """Calling `_dispatch_failure_message` with the same agents set from
    either lens must produce byte-identical output — there is only one
    rendering, not two independently-worded copies."""
    agents = frozenset({"correctness-review", "structure-review"})
    assert _pcr._dispatch_failure_message(agents) == _pcr._dispatch_failure_message(agents)


def _js_repo_with_history(tmp_path: Path) -> Path:
    """A hermetic git repo with one real commit on HEAD, then a further
    staged code edit — the shape `normalized_gate_hash()` needs to produce a
    real (non-`None`) normalized hash, matching
    `test_review_gate_normalized_hash.py`'s own `reviewed_repo` fixture."""
    env = hermetic_git_env(home=tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, env=env, check=True)
    (tmp_path / "a.js").write_text("function f() {\n  return 1\n}\n")
    subprocess.run(["git", "add", "a.js"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=tmp_path, env=env, check=True)
    (tmp_path / "a.js").write_text("function f() {\n  return 2\n}\n")
    subprocess.run(["git", "add", "a.js"], cwd=tmp_path, env=env, check=True)
    return tmp_path


def test_cosmetic_carry_forward_lens_also_honors_the_dispatch_failure_veto(
    tmp_path: Path,
) -> None:
    """The cosmetic-delta carry-forward lens must consult the same veto,
    scoped to the NORMALIZED hash it would otherwise honor, and must not
    return a passing verdict when it applies — surfacing the identical
    `_dispatch_failure_message`, not a generic fallback."""
    lib_dir = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"
    if str(lib_dir) not in sys.path:
        sys.path.insert(0, str(lib_dir))
    import review_gate_normalized_hash as _ngh  # type: ignore[import-not-found]

    repo = _js_repo_with_history(tmp_path)
    raw = _current_hash(repo)
    normalized = _ngh.normalized_gate_hash(repo)
    assert normalized is not None

    # Two genuine, distinct dispatches for the normalized hash — enough to
    # otherwise clear the carry-forward lens's own >= 2 floor.
    _write_dispatch_events(repo, ["correctness-review", "structure-review"], raw)
    # Stamp subject_hash_normalized on those same events too, matching what
    # a real dispatch would carry.
    log = repo / ".claude" / "metrics" / "boundary-events.jsonl"
    lines = [json.loads(ln) for ln in log.read_text().splitlines() if ln.strip()]
    for entry in lines:
        entry["subject_hash_normalized"] = normalized
    log.write_text("\n".join(json.dumps(e) for e in lines) + "\n")
    _write_dispatch_failure(repo, "security-review", raw, subject_hash_normalized=normalized)

    gate_path = repo / ".claude" / "memory" / ".review-passed"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(f"{raw}\n{normalized}\n")

    # Re-stage a whitespace-only delta so the RAW hash mismatches (routing
    # through the carry-forward lens) while the NORMALIZED hash is unchanged.
    (repo / "a.js").write_text("function f() {\n      return 2\n}\n")
    subprocess.run(["git", "add", "a.js"], cwd=repo, env=hermetic_git_env(home=repo), check=True)

    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}, cwd=repo
    )
    assert r.returncode == 2, r.stdout + r.stderr
    assert "Dispatch failure recorded for security-review" in r.stdout
    assert "not a code-review finding" in r.stdout
    # The exact same rendering the main-pipeline lens would produce.
    assert r.stdout == _pcr._dispatch_failure_message(frozenset({"security-review"}))


def test_doc_only_exemption_does_not_launder_a_dispatch_failure(tmp_path: Path) -> None:
    """The veto's priority over the exemption lenses is enforced by
    STATEMENT ORDER in `_evaluate_gate`, not by comment alone (#1763
    security review) — this test would fail if a refactor moved
    `_dispatch_failure_verdict` below `_doc_only_exemption_verdict`."""
    repo = _doc_only_repo(tmp_path)
    h = _current_hash(repo)
    gate_path = repo / ".claude" / "memory" / ".review-passed"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(h)
    _write_doc_only_exemption(repo, h)
    _write_dispatch_failure(repo, "correctness-review", h)
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}, cwd=repo
    )
    assert r.returncode == 2
    assert "Dispatch failure recorded for correctness-review" in r.stdout


def test_single_agent_exemption_does_not_launder_a_dispatch_failure(repo: Path) -> None:
    """Same priority-ordering proof as the doc-only case above, for the
    OTHER exemption lens (#1763 security review)."""
    h = _current_hash(repo)
    gate_path = repo / ".claude" / "memory" / ".review-passed"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(h)
    _write_dispatch_events(repo, ["security-review"], h)
    _write_single_agent_exemption(repo, h)
    _write_dispatch_failure(repo, "correctness-review", h)
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}, cwd=repo
    )
    assert r.returncode == 2
    assert "Dispatch failure recorded for correctness-review" in r.stdout


def test_cosmetic_carry_forward_lens_vetoes_on_raw_hash_only_dispatch_failure(
    tmp_path: Path,
) -> None:
    """#1763 correctness review: a dispatch-failure event that never got a
    `subject_hash_normalized` stamped (e.g. the emission command's NORM
    computation failed and fell through `|| true`) must still veto the
    cosmetic carry-forward lens via the RAW hash — checking only the
    normalized-hash dispatch_failure_agents would be blind to it and could
    pass a commit with an unsuperseded dispatch failure on record."""
    lib_dir = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"
    if str(lib_dir) not in sys.path:
        sys.path.insert(0, str(lib_dir))
    import review_gate_normalized_hash as _ngh  # type: ignore[import-not-found]

    repo = _js_repo_with_history(tmp_path)
    raw = _current_hash(repo)
    normalized = _ngh.normalized_gate_hash(repo)
    assert normalized is not None

    _write_dispatch_events(repo, ["correctness-review", "structure-review"], raw)
    log = repo / ".claude" / "metrics" / "boundary-events.jsonl"
    lines = [json.loads(ln) for ln in log.read_text().splitlines() if ln.strip()]
    for entry in lines:
        entry["subject_hash_normalized"] = normalized
    log.write_text("\n".join(json.dumps(e) for e in lines) + "\n")
    # No subject_hash_normalized on this one — raw hash only.
    _write_dispatch_failure(repo, "security-review", raw)

    gate_path = repo / ".claude" / "memory" / ".review-passed"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(f"{raw}\n{normalized}\n")

    (repo / "a.js").write_text("function f() {\n      return 2\n}\n")
    subprocess.run(["git", "add", "a.js"], cwd=repo, env=hermetic_git_env(home=repo), check=True)

    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}, cwd=repo
    )
    assert r.returncode == 2, r.stdout + r.stderr
    assert "Dispatch failure recorded for security-review" in r.stdout


def test_cosmetic_carry_forward_lens_vetoes_on_current_hash_only_dispatch_failure(
    tmp_path: Path,
) -> None:
    """#1836 test-review finding: the dispatch-failure veto's raw-hash union
    checks BOTH `stored_raw` (the content actually reviewed) AND
    `current_hash` (today's exact re-staged content) independently — a
    failure recorded against ONLY `current_hash`, with nothing against
    `stored_raw` or the normalized hash, must still veto. Every prior test
    for this lens wrote the failure against `stored_raw`; this is the first
    to pin the OTHER half of that union — without it, dropping
    `current_hash` from the raw_hashes tuple would silently let a commit
    with a genuine, unsuperseded dispatch failure against today's content
    pass the gate."""
    lib_dir = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"
    if str(lib_dir) not in sys.path:
        sys.path.insert(0, str(lib_dir))
    import review_gate_normalized_hash as _ngh  # type: ignore[import-not-found]

    repo = _js_repo_with_history(tmp_path)
    raw = _current_hash(repo)
    normalized = _ngh.normalized_gate_hash(repo)
    assert normalized is not None

    _write_dispatch_events(repo, ["correctness-review", "structure-review"], raw)
    log = repo / ".claude" / "metrics" / "boundary-events.jsonl"
    lines = [json.loads(ln) for ln in log.read_text().splitlines() if ln.strip()]
    for entry in lines:
        entry["subject_hash_normalized"] = normalized
    log.write_text("\n".join(json.dumps(e) for e in lines) + "\n")

    gate_path = repo / ".claude" / "memory" / ".review-passed"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(f"{raw}\n{normalized}\n")

    (repo / "a.js").write_text("function f() {\n      return 2\n}\n")
    subprocess.run(["git", "add", "a.js"], cwd=repo, env=hermetic_git_env(home=repo), check=True)

    # Recorded against today's exact post-re-stage hash — NOT `raw`
    # (stored_raw) and not the normalized hash.
    current_hash = _current_hash(repo)
    _write_dispatch_failure(repo, "security-review", current_hash)

    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}, cwd=repo
    )
    assert r.returncode == 2, r.stdout + r.stderr
    assert "Dispatch failure recorded for security-review" in r.stdout


def test_cosmetic_carry_forward_lens_treats_blank_stored_raw_as_not_decisive(
    tmp_path: Path,
) -> None:
    """#1836 closing-pass security/correctness review: a malformed
    `.review-passed` (blank first line, valid second line) must fall
    through to the generic `_BLOCK_MESSAGE` rejection, NOT reach
    `_evaluate_carry_forward` with a falsy `stored_raw` — that function now
    treats any falsy raw-hash binding as unprovable, which would render
    through the SAME sentinel a genuine registry read failure uses,
    misattributing a malformed gate file as "could not read the registered
    review-agent set"."""
    lib_dir = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"
    if str(lib_dir) not in sys.path:
        sys.path.insert(0, str(lib_dir))
    import review_gate_normalized_hash as _ngh  # type: ignore[import-not-found]

    repo = _js_repo_with_history(tmp_path)
    raw = _current_hash(repo)
    normalized = _ngh.normalized_gate_hash(repo)
    assert normalized is not None

    _write_dispatch_events(repo, ["correctness-review", "structure-review"], raw)
    log = repo / ".claude" / "metrics" / "boundary-events.jsonl"
    lines = [json.loads(ln) for ln in log.read_text().splitlines() if ln.strip()]
    for entry in lines:
        entry["subject_hash_normalized"] = normalized
    log.write_text("\n".join(json.dumps(e) for e in lines) + "\n")

    gate_path = repo / ".claude" / "memory" / ".review-passed"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(f"\n{normalized}\n")  # blank first line, valid second

    (repo / "a.js").write_text("function f() {\n      return 2\n}\n")
    subprocess.run(["git", "add", "a.js"], cwd=repo, env=hermetic_git_env(home=repo), check=True)

    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}, cwd=repo
    )
    assert r.returncode == 2, r.stdout + r.stderr
    assert r.stdout == _pcr._BLOCK_MESSAGE
    assert "registered review-agent set" not in r.stdout


def test_cosmetic_carry_forward_lens_vetoes_before_the_count_check(tmp_path: Path) -> None:
    """#1763 security review: the veto must be checked BEFORE the `>= 2`
    distinct-dispatch count on the cosmetic path too — same priority order
    as the main pipeline — so a dispatch failure with fewer than 2
    corroborating dispatches still surfaces the specific
    dispatch-failure-veto message/rule, not the generic block message."""
    lib_dir = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"
    if str(lib_dir) not in sys.path:
        sys.path.insert(0, str(lib_dir))
    import review_gate_normalized_hash as _ngh  # type: ignore[import-not-found]

    repo = _js_repo_with_history(tmp_path)
    raw = _current_hash(repo)
    normalized = _ngh.normalized_gate_hash(repo)
    assert normalized is not None

    # Only ONE normalized dispatch — below the >= 2 floor — plus the
    # dispatch-failure event, both bound to the normalized hash.
    _write_dispatch_events(repo, ["correctness-review"], raw)
    log = repo / ".claude" / "metrics" / "boundary-events.jsonl"
    lines = [json.loads(ln) for ln in log.read_text().splitlines() if ln.strip()]
    for entry in lines:
        entry["subject_hash_normalized"] = normalized
    log.write_text("\n".join(json.dumps(e) for e in lines) + "\n")
    _write_dispatch_failure(repo, "security-review", raw, subject_hash_normalized=normalized)

    gate_path = repo / ".claude" / "memory" / ".review-passed"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(f"{raw}\n{normalized}\n")

    (repo / "a.js").write_text("function f() {\n      return 2\n}\n")
    subprocess.run(["git", "add", "a.js"], cwd=repo, env=hermetic_git_env(home=repo), check=True)

    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}, cwd=repo
    )
    assert r.returncode == 2, r.stdout + r.stderr
    assert "Dispatch failure recorded for security-review" in r.stdout
    assert r.stdout == _pcr._dispatch_failure_message(frozenset({"security-review"}))


def test_registry_read_failure_sentinel_is_never_rendered_as_an_agent_name() -> None:
    """#1763 correctness review: `_UNPROVABLE_DISPATCH_FAILURE` (a registry
    read failure, distinct from a ledger read failure) must render the
    dedicated registry-read-failure message, never be treated as if it
    were a real agent name by `_dispatch_failure_message`."""
    lib_dir = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"
    if str(lib_dir) not in sys.path:
        sys.path.insert(0, str(lib_dir))
    import review_gate_corroboration as _rgc  # type: ignore[import-not-found]

    evidence = _rgc.LedgerEvidence(
        agents_in_window=frozenset(),
        any_dispatch_ever=False,
        same_subject_dispatch_ever=False,
        read_failure_reason=None,
        dispatch_failure_agents=_rgc._UNPROVABLE_DISPATCH_FAILURE,
    )
    verdict = _pcr._dispatch_failure_verdict(evidence)
    assert verdict is not None
    assert verdict.passed is False
    assert verdict.matched_rule == "registry-read-failure"
    assert verdict.message == _pcr._REGISTRY_READ_FAILURE_MESSAGE
    assert "<ledger-read-failure" not in verdict.message
    assert "<degraded-import" not in verdict.message


def test_dispatch_failure_message_empty_set_degrades_to_labeled_placeholder() -> None:
    """Defensive fallback (#1763 correctness review): calling
    `_dispatch_failure_message` with an empty set — unreachable from either
    real call site today, since both guard on truthiness first — must still
    degrade to a labeled placeholder, never a nameless/malformed message."""
    message = _pcr._dispatch_failure_message(frozenset())
    assert "an unnamed review agent" in message
    assert "for  —" not in message


# ---------------------------------------------------------------------------
# #1477 test-completeness gap 1: full `_DOC_EXTENSIONS`/`_DOC_ROOT_NAMES`
# branch coverage on the ACCEPT path (prior tests only exercised `.md` and
# rejection-path `.txt`; the other four extensions and two of the seven
# root-doc words had zero accept-path coverage).
# ---------------------------------------------------------------------------


def test_is_doc_only_changeset_accepts_every_doc_extension() -> None:
    """Every entry in `_DOC_EXTENSIONS` on the accept path, not just `.md`."""
    assert _pcr._is_doc_only_changeset(["guide.md"]) is True
    assert _pcr._is_doc_only_changeset(["guide.mdx"]) is True
    assert _pcr._is_doc_only_changeset(["guide.markdown"]) is True
    assert _pcr._is_doc_only_changeset(["guide.rst"]) is True
    assert _pcr._is_doc_only_changeset(["guide.adoc"]) is True
    assert _pcr._is_doc_only_changeset(["guide.txt"]) is True


def test_is_doc_only_changeset_accepts_every_doc_root_name() -> None:
    """Every entry in `_DOC_ROOT_NAMES` on the accept path — prior coverage
    only exercised LICENSE/NOTICE; `contributing` and `code_of_conduct`
    (matched case-insensitively, per the module's lower-casing) had zero
    coverage."""
    assert _pcr._is_doc_only_changeset(["README"]) is True
    assert _pcr._is_doc_only_changeset(["CHANGELOG"]) is True
    assert _pcr._is_doc_only_changeset(["CONTRIBUTING"]) is True
    assert _pcr._is_doc_only_changeset(["LICENSE"]) is True
    assert _pcr._is_doc_only_changeset(["NOTICE"]) is True
    assert _pcr._is_doc_only_changeset(["AUTHORS"]) is True
    assert _pcr._is_doc_only_changeset(["CODE_OF_CONDUCT"]) is True


# ---------------------------------------------------------------------------
# #1477 test-completeness gap 2: a filename that hits two simultaneously-
# triggering reject predicates at once.
# ---------------------------------------------------------------------------


def test_is_doc_only_changeset_rejects_combined_non_doc_dir_and_functional_config() -> None:
    """`requirements/agents.md` hits BOTH the non-doc-dir branch
    (`requirements` in `_NON_DOC_DIR_SEGMENTS`) AND the functional-config-
    segment branch (`agents` in `_FUNCTIONAL_CONFIG_SEGMENTS`) at once —
    confirms the combination still correctly rejects, not merely that each
    predicate rejects it alone (each is independently tested elsewhere:
    `test_is_doc_only_changeset_rejects_manifest_files_under_a_subdirectory`
    for the former, `test_functional_config_segments_all_rejected` for the
    latter)."""
    assert _pcr._is_doc_only_changeset(["requirements/agents.md"]) is False


# ---------------------------------------------------------------------------
# #1477 test-completeness gap 3: `_current_branch()`/`_plugin_version()`
# exception-fallback branches, previously untested.
# ---------------------------------------------------------------------------


def test_current_branch_returns_empty_string_on_subprocess_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(*_args, **_kwargs):
        raise FileNotFoundError("git executable not found")

    monkeypatch.setattr(_pcr.subprocess, "run", _boom)
    assert _pcr._current_branch() == ""


def test_current_branch_returns_empty_string_on_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess([], returncode=128, stdout="", stderr="fatal")

    monkeypatch.setattr(_pcr.subprocess, "run", _fake_run)
    assert _pcr._current_branch() == ""


def test_plugin_version_returns_unknown_on_malformed_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`_plugin_version()` resolves `_HOOK_DIR / ".." / ".claude-plugin" /
    "plugin.json"` — pointing `_HOOK_DIR` at a directory whose sibling
    manifest is malformed JSON exercises the `except (OSError, ValueError)`
    fallback (`json.JSONDecodeError` is a `ValueError` subclass)."""
    fake_hook_dir = tmp_path / "hooks"
    fake_hook_dir.mkdir()
    plugin_dir = tmp_path / ".claude-plugin"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.json").write_text("{not valid json")

    monkeypatch.setattr(_pcr, "_HOOK_DIR", fake_hook_dir)
    assert _pcr._plugin_version() == "unknown"


def test_plugin_version_returns_unknown_when_manifest_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing manifest raises `OSError` (`FileNotFoundError`) from
    `.read_text()` — the sibling half of the same except clause."""
    fake_hook_dir = tmp_path / "hooks"
    fake_hook_dir.mkdir()
    # No .claude-plugin/plugin.json written at all.

    monkeypatch.setattr(_pcr, "_HOOK_DIR", fake_hook_dir)
    assert _pcr._plugin_version() == "unknown"


# ---------------------------------------------------------------------------
# #1477 structural finding 5: `_DegradedLedgerEvidence` (the ImportError-
# fallback stand-in for `review_gate_corroboration.LedgerEvidence`) hand-
# duplicates its field shape with no test asserting parity — a future field
# addition to the real NamedTuple could silently leave the degraded path
# stale without this. #1836 extends the same guard to
# `CosmeticCarryForwardEvidence`, the second real shape this same stand-in
# now serves (via `_evaluate_carry_forward`) — without this, a future field
# added there but not to `_DegradedLedgerEvidence` would raise
# `AttributeError` inside `_cosmetic_carry_forward_verdict`'s blanket
# `except Exception: return None`, silently making the carry-forward lens
# permanently non-decisive with no test failure and no operator-visible
# signal.
# ---------------------------------------------------------------------------


def test_degraded_ledger_evidence_field_shape_matches_real_ledger_evidence() -> None:
    """Compares `_DegradedLedgerEvidence`'s field shape (names AND order)
    against the real `review_gate_corroboration.LedgerEvidence` NamedTuple,
    and additionally against `CosmeticCarryForwardEvidence`'s field set
    (subset, since the stand-in's fields are a superset covering both real
    shapes) — a future field added to either real shape without updating
    this hand-written stand-in now fails a test instead of silently
    drifting.

    Triggers the ImportError-fallback path in a FRESH subprocess, not via
    the in-process `sys.modules["artifact_paths"] = None` + re-exec trick
    `test_import_error_fallback_resolves_under_dot_claude` uses: that trick
    turns out not to reliably re-raise `ImportError` when
    `pre_commit_review.py` has already been exec'd once for real earlier in
    the same process (as `_pcr` at this file's collection time always
    does) — some CPython-version-dependent caching on the already-loaded
    code object appears to let the second `exec_module()` resolve
    `artifact_paths` successfully regardless of the poisoned entry. A
    subprocess sidesteps that entirely: `artifact_paths` is poisoned before
    `pre_commit_review.py` is ever imported for the first time in that
    process, which reliably raises. (`test_import_error_fallback_resolves_
    under_dot_claude` itself still passes today only because
    `artifact_paths.resolve_file`'s real, non-degraded implementation
    happens to return the identical path for that specific call — it does
    not actually prove the fallback path ran; not touched here since fixing
    that is outside this issue's scope.)"""
    script = (
        "import sys, importlib.util, json\n"
        "sys.modules['artifact_paths'] = None\n"
        "spec = importlib.util.spec_from_file_location('pcr_degraded_probe', "
        + repr(str(_HOOK))
        + ")\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(module)\n"
        "degraded = module._DegradedLedgerEvidence\n"
        "fields = [n for n in vars(degraded) if not n.startswith('__')]\n"
        "print(json.dumps(fields))\n"
    )
    proc = subprocess.run(
        ["python3", "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    degraded_fields = tuple(json.loads(proc.stdout))

    lib_dir = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"
    if str(lib_dir) not in sys.path:
        sys.path.insert(0, str(lib_dir))
    import review_gate_corroboration as _rgc  # type: ignore[import-not-found]

    assert degraded_fields == _rgc.LedgerEvidence._fields
    assert set(_rgc.CosmeticCarryForwardEvidence._fields) <= set(degraded_fields)


# ---------------------------------------------------------------------------
# #1476: `git commit -a`/`--all` and pathspec-form commits — tracked-file
# changes committed without ever being `git add`-ed used to skip the entire
# gate (empty staged index -> "nothing to gate"). These scenarios need a
# repo with a real HEAD commit, since the fix hashes `git diff HEAD`.
# ---------------------------------------------------------------------------


@pytest.fixture
def committed_repo(tmp_path: Path) -> Path:
    """A hermetic git repo with one real commit already on HEAD, then a
    further tracked-file edit left unstaged — the `git commit -a`/pathspec
    signature (nothing in the index, but tracked files differ from HEAD in
    the working tree)."""
    env = hermetic_git_env(home=tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, env=env, check=True)
    (tmp_path / "a.ts").write_text("v1\n")
    subprocess.run(["git", "add", "a.ts"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=tmp_path, env=env, check=True)
    # Modify the tracked file WITHOUT staging — the index still matches
    # HEAD; only the working tree differs.
    (tmp_path / "a.ts").write_text("v2\n")
    return tmp_path


def _current_working_tree_hash(repo: Path) -> str:
    """Compute the effective (`git diff HEAD`) hash via the Python lib."""
    lib_dir = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"
    if str(lib_dir) not in sys.path:
        sys.path.insert(0, str(lib_dir))
    import review_gate_hash as _rgh  # type: ignore[import-not-found]

    return _rgh.working_tree_gate_hash(cwd=repo)


def test_unstaged_a_flag_commit_blocks_with_git_add_guidance(committed_repo: Path) -> None:
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -a -m x"}},
        cwd=committed_repo,
    )
    assert r.returncode == 2
    assert "git add" in r.stdout
    assert "BLOCKED" in r.stdout
    assert r.stdout == r.stderr


def test_unstaged_pathspec_commit_blocks_with_git_add_guidance(committed_repo: Path) -> None:
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit a.ts -m x"}},
        cwd=committed_repo,
    )
    assert r.returncode == 2
    assert "git add" in r.stdout


def test_unstaged_a_flag_commit_with_matching_hash_and_dispatch_evidence_passes(
    committed_repo: Path,
) -> None:
    h = _current_working_tree_hash(committed_repo)
    gate_path = committed_repo / ".claude" / "memory" / ".review-passed"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(h)
    _write_dispatch_events(committed_repo, ["security-review", "structure-review"], h)
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -a -m x"}},
        cwd=committed_repo,
    )
    assert r.returncode == 0
    assert not gate_path.exists()


def test_unstaged_a_flag_commit_with_matching_hash_but_no_dispatch_evidence_blocks(
    committed_repo: Path,
) -> None:
    """Distinct from the missing-gate-file case: the hash matches (so the
    generic `git add` guidance doesn't apply), it's the dispatch-ledger
    corroboration lens that rejects — same as an ordinary staged commit
    with no genuine review dispatch."""
    h = _current_working_tree_hash(committed_repo)
    gate_path = committed_repo / ".claude" / "memory" / ".review-passed"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(h)
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -a -m x"}},
        cwd=committed_repo,
    )
    assert r.returncode == 2
    assert "git add" not in r.stdout
    assert "review-agent dispatch" in r.stdout.lower() or "dispatch" in r.stdout.lower()


def test_unstaged_a_flag_commit_stale_gate_hash_blocks_with_git_add_guidance(
    committed_repo: Path,
) -> None:
    """A gate file exists but for DIFFERENT content than the current
    working tree — still the unstaged-specific message, since a hash
    mismatch never proves this content was ever reviewed regardless."""
    gate_path = committed_repo / ".claude" / "memory" / ".review-passed"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text("0" * 64)
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -a -m x"}},
        cwd=committed_repo,
    )
    assert r.returncode == 2
    assert "git add" in r.stdout


def test_unstaged_a_flag_no_verify_without_reason_blocks(committed_repo: Path) -> None:
    """Secondary #1476 fix: `git commit -a --no-verify` used to skip the
    GATE_BYPASS_REASON audit requirement entirely (the old empty-staged
    early-return ran before the bypass-flag check)."""
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -a --no-verify -m x"}},
        cwd=committed_repo,
    )
    assert r.returncode == 2
    assert "GATE_BYPASS_REASON" in r.stdout
    assert not (committed_repo / ".claude" / "metrics" / "gate-bypass-audit.jsonl").exists()


def test_unstaged_a_flag_no_verify_with_reason_allows_and_audits(committed_repo: Path) -> None:
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -a --no-verify -m x"}},
        cwd=committed_repo,
        extra_env={"GATE_BYPASS_REASON": "hotfix, review to follow"},
    )
    assert r.returncode == 0
    audit = committed_repo / ".claude" / "metrics" / "gate-bypass-audit.jsonl"
    assert audit.exists()
    entry = json.loads(audit.read_text().splitlines()[0])
    assert entry["reason"] == "hotfix, review to follow"
    assert entry["stagedFileCount"] == 1


def test_unborn_head_with_nothing_staged_or_modified_stays_silent(tmp_path: Path) -> None:
    """Regression: an unborn-HEAD repo (no commits at all) with nothing
    staged and nothing tracked must still silently pass — the new
    `_working_tree_modified_names()` check must not itself misfire when
    there is no HEAD to compare against (a bare `git diff`, no target,
    needs no HEAD)."""
    env = hermetic_git_env(home=tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, env=env, check=True)
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -a -m x"}},
        cwd=tmp_path,
    )
    assert r.returncode == 0


def test_normal_staged_commit_on_repo_with_history_still_gated_normally(
    committed_repo: Path,
) -> None:
    """Regression: an ordinary `git add` + `git commit` on a repo that
    already has history (not the -a/pathspec path) must be completely
    unaffected — `_staged_names()` returns non-empty, so `unstaged_commit`
    is never set."""
    subprocess.run(
        ["git", "add", "a.ts"],
        cwd=committed_repo,
        env=hermetic_git_env(home=committed_repo),
        check=True,
    )
    h = _current_hash(committed_repo)
    gate_path = committed_repo / ".claude" / "memory" / ".review-passed"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(h)
    _write_dispatch_events(committed_repo, ["security-review", "structure-review"], h)
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}},
        cwd=committed_repo,
    )
    assert r.returncode == 0
    assert not gate_path.exists()
