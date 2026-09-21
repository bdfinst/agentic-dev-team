"""Unit tests for hooks/subagent_skill_context.py (#2187, Slice 1 Step 1.2).

Mixes in-process calls (for the fixture-agents-dir / stdout-shape assertions,
where a production `agents/` dir can't be injected via subprocess) with
subprocess invocation of the real script (for the fail-open/no-op contract,
where the real `agents/` dir is irrelevant to the outcome) — matching this
repo's existing `context_ceiling_guard.py` test convention of importing the
hook module directly for logic-level assertions and only shelling out for the
full stdin/stdout/exit-code contract.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

from _repo_root import REPO_ROOT as _REPO_ROOT

_HOOKS_DIR = _REPO_ROOT / "plugins" / "dev-team" / "hooks"
_HOOK_PY = _HOOKS_DIR / "subagent_skill_context.py"

if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

import subagent_skill_context as hook  # type: ignore[import-not-found]


def _write_agent(agents_dir: Path, name: str, body: str) -> None:
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / f"{name}.md").write_text(body, encoding="utf-8")


def _run_hook(raw_stdin: bytes) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_HOOK_PY)],
        input=raw_stdin,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        capture_output=True,
        timeout=10,
        check=False,
    )


def _run_hook_main_inprocess(monkeypatch, payload: dict) -> str:
    """Invoke `hook.main()` in-process, capturing whatever it prints to
    stdout. Used only where a fixture `agents_dir` must be injected — the
    subprocess path has no way to override the hook's own resolved
    `agents/` directory."""
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    captured = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured)
    exit_code = hook.main()
    assert exit_code == 0
    return captured.getvalue()


def test_known_agent_type_with_skills_emits_additional_context(
    monkeypatch, tmp_path: Path
) -> None:
    _write_agent(
        tmp_path,
        "fixture-agent",
        "---\n"
        "name: fixture-agent\n"
        "description: test fixture\n"
        "skills:\n"
        "  - test-driven-development\n"
        "  - systematic-debugging\n"
        "---\n\n# Fixture Agent\n",
    )
    monkeypatch.setattr(hook, "_DEFAULT_AGENTS_DIR", tmp_path)

    payload = {
        "tool_name": "Agent",
        "tool_input": {
            "subagent_type": "fixture-agent",
            "description": "do the thing",
            "prompt": "original dispatch prompt",
        },
    }
    stdout = _run_hook_main_inprocess(monkeypatch, payload)

    assert stdout.strip()
    emitted = json.loads(stdout)
    updated_input = emitted["hookSpecificOutput"]["updatedInput"]
    assert emitted["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert "test-driven-development" in updated_input["additionalContext"]
    assert "systematic-debugging" in updated_input["additionalContext"]
    # Original tool_input keys preserved unchanged, not replaced.
    assert updated_input["subagent_type"] == "fixture-agent"
    assert updated_input["description"] == "do the thing"
    assert updated_input["prompt"] == "original dispatch prompt"


def test_resolve_updated_input_returns_none_for_unrecognized_type(
    tmp_path: Path,
) -> None:
    payload = {
        "tool_name": "Agent",
        "tool_input": {"subagent_type": "not-a-real-agent"},
    }
    assert hook.resolve_updated_input(payload, agents_dir=tmp_path) is None


def test_unrecognized_agent_type_is_silent_pass_via_subprocess() -> None:
    result = _run_hook(
        json.dumps(
            {
                "tool_name": "Agent",
                "tool_input": {"subagent_type": "not-a-real-agent-xyz"},
            }
        ).encode()
    )
    assert result.returncode == 0
    assert result.stdout == b""


def test_missing_subagent_type_key_is_silent_pass() -> None:
    for tool_name in ("Agent", "Task"):
        result = _run_hook(
            json.dumps({"tool_name": tool_name, "tool_input": {}}).encode()
        )
        assert result.returncode == 0
        assert result.stdout == b""


def test_malformed_stdin_is_silent_pass_no_traceback() -> None:
    result = _run_hook(b"not json")
    assert result.returncode == 0
    assert result.stdout == b""
    assert result.stderr == b""


def test_bash_tool_name_is_clean_no_op() -> None:
    result = _run_hook(
        json.dumps(
            {"tool_name": "Bash", "tool_input": {"command": "echo hi"}}
        ).encode()
    )
    assert result.returncode == 0
    assert result.stdout == b""


def test_hook_is_idempotent_across_repeated_invocations() -> None:
    """Same input, invoked twice, produces the same result both times — a
    stdin-in/stdout-out script with no on-disk state has nothing to leak
    between runs, but this pins that property rather than assuming it."""
    payload_bytes = json.dumps(
        {
            "tool_name": "Agent",
            "tool_input": {"subagent_type": "not-a-real-agent-xyz"},
        }
    ).encode()

    first = _run_hook(payload_bytes)
    second = _run_hook(payload_bytes)

    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout == b""
