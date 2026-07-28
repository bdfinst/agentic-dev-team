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
