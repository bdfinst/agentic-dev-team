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

from hermetic import hermetic_git_env  # type: ignore[import-not-found]

# Direct module import (not subprocess) for unit-level testing of pure
# helpers like `_is_doc_only_changeset` — safe because `main()` only runs
# under `if __name__ == "__main__":`, so importing has no side effects.
import importlib.util as _importlib_util

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
    gate_path.write_text(h)
    stale_ts = datetime.now(timezone.utc) - timedelta(seconds=_WINDOW_SECONDS + 600)
    _write_dispatch_events(repo, ["security-review"], h, ts=stale_ts)
    _write_dispatch_events(repo, ["structure-review"], h)
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
    code, not a LICENSE file, regardless of its basename."""
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
    extension is."""
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
