"""Unit tests for hooks/agent_dispatch_ledger.py (#1461).

The PreToolUse dispatch-ledger hook: records a `boundary-events.jsonl`
`"record"` event when a real, registered review agent is dispatched via the
Agent/Task tool; records nothing for an unregistered/fabricated name. Always
exits 0 (fail-open) regardless of outcome.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from _repo_root import REPO_ROOT as _REPO_ROOT

_PLUGIN_DIR = _REPO_ROOT / "plugins" / "dev-team"
_HOOK = _PLUGIN_DIR / "hooks" / "agent_dispatch_ledger.py"

# A real registered review agent, confirmed present in the repo's own
# agents/ directory — this hook resolves its registry against the real
# plugin agents dir (relative to its own file location), not an injectable
# one, so tests exercise the real closed set.
_REAL_REVIEW_AGENT = "security-review"


def _run_hook(payload: dict) -> subprocess.CompletedProcess:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LANG": "C.UTF-8",
    }
    return subprocess.run(
        [sys.executable, str(_HOOK)],
        input=json.dumps(payload).encode(),
        env=env,
        capture_output=True,
        timeout=10,
        check=False,
    )


def _read_jsonl(path: Path) -> list:
    if not path.is_file():
        return []
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return [json.loads(ln) for ln in lines]


def test_registered_review_agent_dispatch_is_recorded(tmp_path: Path) -> None:
    result = _run_hook(
        {
            "tool_name": "Agent",
            "tool_input": {"subagent_type": _REAL_REVIEW_AGENT},
            "cwd": str(tmp_path),
            "session_id": "sess-1",
        }
    )
    assert result.returncode == 0
    events = _read_jsonl(tmp_path / ".claude" / "metrics" / "boundary-events.jsonl")
    assert len(events) == 1
    event = events[0]
    assert event["hook"] == "agent_dispatch_ledger"
    assert event["tool"] == "Agent"
    assert event["decision"] == "record"
    assert event["matched_rule"] == _REAL_REVIEW_AGENT
    assert event["session_id"] == "sess-1"


def test_unregistered_agent_name_is_never_recorded(tmp_path: Path) -> None:
    result = _run_hook(
        {
            "tool_name": "Agent",
            "tool_input": {"subagent_type": "totally-fabricated-agent-name"},
            "cwd": str(tmp_path),
        }
    )
    assert result.returncode == 0
    assert not (tmp_path / ".claude" / "metrics" / "boundary-events.jsonl").exists()


def test_non_review_team_agent_is_not_recorded(tmp_path: Path) -> None:
    """A real, non-review team agent (e.g. orchestrator) is not in the
    closed *-review registry and must not be recorded."""
    result = _run_hook(
        {
            "tool_name": "Agent",
            "tool_input": {"subagent_type": "orchestrator"},
            "cwd": str(tmp_path),
        }
    )
    assert result.returncode == 0
    assert not (tmp_path / ".claude" / "metrics" / "boundary-events.jsonl").exists()


def test_missing_subagent_type_is_silent_pass(tmp_path: Path) -> None:
    result = _run_hook({"tool_name": "Agent", "tool_input": {}, "cwd": str(tmp_path)})
    assert result.returncode == 0
    assert not (tmp_path / ".claude" / "metrics" / "boundary-events.jsonl").exists()


def test_malformed_stdin_is_silent_pass() -> None:
    result = subprocess.run(
        [sys.executable, str(_HOOK)],
        input=b"not json",
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0


def test_fabricated_name_never_appears_as_free_text(tmp_path: Path) -> None:
    """Even a fabricated name that LOOKS plausible must never leak into the
    ledger in any form — not even as a rejected/flagged entry."""
    sentinel = "sentinel-not-a-real-review-agent"
    _run_hook(
        {
            "tool_name": "Agent",
            "tool_input": {"subagent_type": sentinel},
            "cwd": str(tmp_path),
        }
    )
    log = tmp_path / ".claude" / "metrics" / "boundary-events.jsonl"
    if log.is_file():
        assert sentinel not in log.read_text(encoding="utf-8")


def test_recorded_dispatch_is_stamped_with_the_current_subject_hash(
    tmp_path: Path,
) -> None:
    """#1461 security re-review: the write side of the subject-hash binding
    fix was untested — a regression silently dropping `subject_hash` would
    make every future dispatch permanently uncorroborating (the gate
    requires an exact hash match), yet no test caught that class of bug.
    Uses a real hermetic git repo (not a bare tmp_path) so
    `review_gate_hash()` computes a genuine, non-None hash to assert
    against."""
    _tests_lib = Path(__file__).resolve().parents[2] / "tests" / "lib"
    if str(_tests_lib) not in sys.path:
        sys.path.insert(0, str(_tests_lib))
    from hermetic import hermetic_git_env  # type: ignore[import-not-found]

    lib_dir = _PLUGIN_DIR / "hooks" / "lib"
    if str(lib_dir) not in sys.path:
        sys.path.insert(0, str(lib_dir))
    import review_gate_hash as _rgh  # type: ignore[import-not-found]

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

    expected_hash = _rgh.review_gate_hash(cwd=tmp_path)
    assert expected_hash  # sanity: a real repo yields a non-empty hash

    result = _run_hook(
        {
            "tool_name": "Agent",
            "tool_input": {"subagent_type": _REAL_REVIEW_AGENT},
            "cwd": str(tmp_path),
        }
    )
    assert result.returncode == 0
    events = _read_jsonl(tmp_path / ".claude" / "metrics" / "boundary-events.jsonl")
    assert len(events) == 1
    assert events[0]["subject_hash"] == expected_hash


def test_plugin_qualified_dispatch_is_recorded_under_its_bare_name(tmp_path: Path) -> None:
    """#1461 follow-up: a real Agent-tool dispatch of this plugin's own
    installed review agent is named "dev-team:<agent-name>", not the bare
    stem — this must be recognized identically to the bare form, and
    recorded under the bare (closed-vocabulary) name, never the qualified
    string verbatim."""
    result = _run_hook(
        {
            "tool_name": "Agent",
            "tool_input": {"subagent_type": f"dev-team:{_REAL_REVIEW_AGENT}"},
            "cwd": str(tmp_path),
        }
    )
    assert result.returncode == 0
    events = _read_jsonl(tmp_path / ".claude" / "metrics" / "boundary-events.jsonl")
    assert len(events) == 1
    assert events[0]["matched_rule"] == _REAL_REVIEW_AGENT


def test_a_different_plugins_qualified_name_is_never_recorded(tmp_path: Path) -> None:
    result = _run_hook(
        {
            "tool_name": "Agent",
            "tool_input": {"subagent_type": f"other-plugin:{_REAL_REVIEW_AGENT}"},
            "cwd": str(tmp_path),
        }
    )
    assert result.returncode == 0
    assert not (tmp_path / ".claude" / "metrics" / "boundary-events.jsonl").exists()


def test_dispatch_with_clean_index_falls_back_to_branch_diff_hash(tmp_path: Path) -> None:
    """Issue #1904 Bug 1/2b: a `--since <base>`-scoped review (the only real
    path to `gh pr create`, per `skills/pr/SKILL.md` step 1) always runs
    with a CLEAN working tree, so `review_gate_hash()` (the staged diff) is
    empty by definition. Stamping the constant `EMPTY_DIGEST` in that case
    would defeat subject-binding (Bug 1) AND could never corroborate
    `hooks/pre_pr_review.py`'s gate, which always compares against
    `branch_diff_gate_hash()` (Bug 2b) — this pins the fix: the ledger falls
    back to that same branch-diff hash when nothing is staged."""
    _tests_lib = Path(__file__).resolve().parents[2] / "tests" / "lib"
    if str(_tests_lib) not in sys.path:
        sys.path.insert(0, str(_tests_lib))
    from hermetic import hermetic_git_env  # type: ignore[import-not-found]

    lib_dir = _PLUGIN_DIR / "hooks" / "lib"
    if str(lib_dir) not in sys.path:
        sys.path.insert(0, str(lib_dir))
    import review_gate_hash as _rgh  # type: ignore[import-not-found]

    env = hermetic_git_env(home=tmp_path)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, env=env, check=True)
    (tmp_path / "base.txt").write_text("base\n")
    subprocess.run(["git", "add", "base.txt"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "checkout", "-q", "-b", "feature"], cwd=tmp_path, env=env, check=True)
    (tmp_path / "feature.txt").write_text("new\n")
    subprocess.run(["git", "add", "feature.txt"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "feature work"], cwd=tmp_path, env=env, check=True)
    # Working tree is clean here — nothing staged, matching /pr's step 1
    # precondition for a --since-scoped /code-review run.

    assert _rgh.review_gate_hash(cwd=tmp_path) == _rgh.EMPTY_DIGEST  # sanity
    expected_branch_hash = _rgh.branch_diff_gate_hash("main", cwd=tmp_path)
    assert expected_branch_hash != _rgh.EMPTY_DIGEST  # sanity

    result = _run_hook(
        {
            "tool_name": "Agent",
            "tool_input": {"subagent_type": _REAL_REVIEW_AGENT},
            "cwd": str(tmp_path),
        }
    )
    assert result.returncode == 0
    events = _read_jsonl(tmp_path / ".claude" / "metrics" / "boundary-events.jsonl")
    assert len(events) == 1
    assert events[0]["subject_hash"] == expected_branch_hash
    assert events[0]["subject_hash"] != _rgh.EMPTY_DIGEST


def test_dispatch_with_clean_index_and_no_branch_diff_stamps_nothing(tmp_path: Path) -> None:
    """When BOTH the staged diff AND the branch diff are empty (a freshly
    checked-out branch with no commits of its own yet), the ledger must
    refuse to stamp `subject_hash` at all — never fall back to
    `EMPTY_DIGEST` a second time. The dispatch is still recorded (it just
    carries no `subject_hash`, so it can never satisfy an exact-hash gate
    check)."""
    _tests_lib = Path(__file__).resolve().parents[2] / "tests" / "lib"
    if str(_tests_lib) not in sys.path:
        sys.path.insert(0, str(_tests_lib))
    from hermetic import hermetic_git_env  # type: ignore[import-not-found]

    env = hermetic_git_env(home=tmp_path)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, env=env, check=True)
    (tmp_path / "base.txt").write_text("base\n")
    subprocess.run(["git", "add", "base.txt"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "checkout", "-q", "-b", "feature"], cwd=tmp_path, env=env, check=True)
    # No further commits on `feature` — both the staged diff and the
    # branch diff against `main` are empty.

    result = _run_hook(
        {
            "tool_name": "Agent",
            "tool_input": {"subagent_type": _REAL_REVIEW_AGENT},
            "cwd": str(tmp_path),
        }
    )
    assert result.returncode == 0
    events = _read_jsonl(tmp_path / ".claude" / "metrics" / "boundary-events.jsonl")
    assert len(events) == 1
    assert "subject_hash" not in events[0]
    assert events[0]["matched_rule"] == _REAL_REVIEW_AGENT


def test_two_distinct_registered_dispatches_recorded_as_two_events(tmp_path: Path) -> None:
    _run_hook(
        {
            "tool_name": "Agent",
            "tool_input": {"subagent_type": "security-review"},
            "cwd": str(tmp_path),
        }
    )
    _run_hook(
        {
            "tool_name": "Agent",
            "tool_input": {"subagent_type": "structure-review"},
            "cwd": str(tmp_path),
        }
    )
    events = _read_jsonl(tmp_path / ".claude" / "metrics" / "boundary-events.jsonl")
    assert len(events) == 2
    assert {e["matched_rule"] for e in events} == {"security-review", "structure-review"}
    assert all(e["decision"] == "record" for e in events)
