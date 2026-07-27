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


def test_doc_only_exemption_satisfies_the_gate_without_dispatch_evidence(
    repo: Path,
) -> None:
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
