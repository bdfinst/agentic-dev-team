"""Unit tests for the Python port of hooks/codegraph-turn-mark.sh (#594).

White-box tests on the port's helpers + end-to-end sentinel-write behavior.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_HOOKS_DIR = Path(__file__).resolve().parents[2] / "hooks"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

import code_intelligence_turn_mark as hook  # type: ignore[import-not-found]

_SENTINEL_NAME = "code-intelligence-turn-state.json"


# ---------------------------------------------------------------------------
# _tool_family
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tool_name",
    [
        "mcp__codegraph__codegraph_explore",
        "mcp__codegraph__codegraph_node",
        "mcp__codegraph__anything_else",
    ],
)
def test_tool_family_codegraph(tool_name: str) -> None:
    assert hook._tool_family(tool_name) == "codegraph"


@pytest.mark.parametrize(
    "tool_name",
    [
        "mcp__plugin_repowise_repowise__get_context",
        "mcp__plugin_repowise_repowise__get_risk",
        "mcp__plugin_repowise_repowise__get_why",
    ],
)
def test_tool_family_repowise(tool_name: str) -> None:
    assert hook._tool_family(tool_name) == "repowise"


@pytest.mark.parametrize(
    "tool_name",
    [
        "mcp__othermcp__thing",
        "Read",
        "Bash",
        "",
        "codegraph_explore",
    ],
)
def test_tool_family_none_for_other_tools(tool_name: str) -> None:
    assert hook._tool_family(tool_name) is None


def test_uses_shared_turn_identity_lib() -> None:
    """No local duplicate of the tail-window logic remains — both
    `transcript_id` and `count_user_lines` must be the shared-lib
    functions imported from `turn_identity.py`, not local reimplementations.
    Binding names are unprefixed, matching the shared module's own export
    names (not the hook-local `_transcript_id`/`_count_user_lines` aliases
    this hook used before the naming-review cleanup).
    """
    import turn_identity  # type: ignore[import-not-found]

    assert hook.transcript_id is turn_identity.transcript_id
    assert hook.count_user_lines is turn_identity.count_user_lines
    assert hook.matches_current_turn is turn_identity.matches_current_turn
    assert not hasattr(hook, "_TAIL_WINDOW_BYTES")
    assert not hasattr(hook, "_USER_LINE_RE")
    assert not hasattr(hook, "_matches_current_turn")


# ---------------------------------------------------------------------------
# _transcript_id — mirrors bash `basename ${x%.*}`
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path,expected",
    [
        ("/tmp/session-abc.jsonl", "session-abc"),
        ("session.json", "session"),
        ("/a/b/no-extension", "no-extension"),
        ("/tmp/multi.dot.file.jsonl", "multi.dot.file"),
    ],
)
def test_transcript_id(path: str, expected: str) -> None:
    assert hook.transcript_id(path) == expected


# ---------------------------------------------------------------------------
# _count_user_lines
# ---------------------------------------------------------------------------


def test_count_user_lines_counts_type_user_markers(tmp_path: Path) -> None:
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(
        '{"type":"user","content":"a"}\n'
        '{"type":"assistant","content":"b"}\n'
        '{"type":"user","content":"c"}\n'
    )
    assert hook.count_user_lines(transcript) == 2


def test_count_user_lines_zero_when_no_user_markers(tmp_path: Path) -> None:
    transcript = tmp_path / "t.jsonl"
    transcript.write_text('{"type":"assistant"}\n{"type":"tool_use"}\n')
    assert hook.count_user_lines(transcript) == 0


def test_count_user_lines_zero_when_file_missing(tmp_path: Path) -> None:
    assert hook.count_user_lines(tmp_path / "nope.jsonl") == 0


def test_count_user_lines_scans_tail_only_for_large_transcript(
    tmp_path: Path,
) -> None:
    """A 2 MiB transcript must be scanned only in the last 1 MiB window.

    Prepend 1.5 MiB of assistant lines, then two user markers in the last
    500 KiB. The count is 2, proving the head is not being scanned.
    """
    transcript = tmp_path / "big.jsonl"
    head = '{"type":"assistant"}\n' * (1_500_000 // len('{"type":"assistant"}\n') + 1)
    tail = '{"type":"user"}\n{"type":"user"}\n'
    transcript.write_text(head + tail)
    assert hook.count_user_lines(transcript) == 2


# ---------------------------------------------------------------------------
# End-to-end via subprocess — sentinel write + fail-open on bad input
# ---------------------------------------------------------------------------


def _run_hook(stdin: str, cwd: Path, env: dict) -> subprocess.CompletedProcess:
    hook_path = _HOOKS_DIR / "code_intelligence_turn_mark.py"
    return subprocess.run(
        [sys.executable, str(hook_path)],
        input=stdin.encode("utf-8"),
        capture_output=True,
        cwd=str(cwd),
        env=env,
        check=False,
    )


def _stdin_for(tool_name: str, transcript_path: str) -> str:
    return json.dumps({"tool_name": tool_name, "transcript_path": transcript_path})


def _write_sentinel(tmp_path: Path, payload: dict) -> Path:
    sentinel = tmp_path / ".claude" / _SENTINEL_NAME
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    sentinel.write_text(json.dumps(payload))
    return sentinel


def test_writes_fresh_sentinel_when_none_exists_codegraph(tmp_path: Path) -> None:
    transcript = tmp_path / "t.jsonl"
    transcript.write_text('{"type":"user"}\n{"type":"assistant"}\n{"type":"user"}\n')
    result = _run_hook(
        _stdin_for("mcp__codegraph__codegraph_explore", "t.jsonl"),
        tmp_path,
        {"CLAUDE_PROJECT_DIR": str(tmp_path), "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0
    assert result.stdout == b""

    sentinel = tmp_path / ".claude" / _SENTINEL_NAME
    assert sentinel.is_file()
    payload = json.loads(sentinel.read_text())
    assert payload == {"transcript_id": "t", "turn_counter": 2, "tools_used": ["codegraph"]}


def test_writes_fresh_sentinel_when_none_exists_repowise(tmp_path: Path) -> None:
    transcript = tmp_path / "t.jsonl"
    transcript.write_text('{"type":"user"}\n')
    result = _run_hook(
        _stdin_for("mcp__plugin_repowise_repowise__get_context", "t.jsonl"),
        tmp_path,
        {"CLAUDE_PROJECT_DIR": str(tmp_path), "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0

    sentinel = tmp_path / ".claude" / _SENTINEL_NAME
    payload = json.loads(sentinel.read_text())
    assert payload == {"transcript_id": "t", "turn_counter": 1, "tools_used": ["repowise"]}


def test_accumulates_within_same_turn(tmp_path: Path) -> None:
    transcript = tmp_path / "t.jsonl"
    transcript.write_text('{"type":"user"}\n')
    _write_sentinel(
        tmp_path,
        {"transcript_id": "t", "turn_counter": 1, "tools_used": ["codegraph"]},
    )
    result = _run_hook(
        _stdin_for("mcp__plugin_repowise_repowise__get_risk", "t.jsonl"),
        tmp_path,
        {"CLAUDE_PROJECT_DIR": str(tmp_path), "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0

    sentinel = tmp_path / ".claude" / _SENTINEL_NAME
    payload = json.loads(sentinel.read_text())
    assert payload == {
        "transcript_id": "t",
        "turn_counter": 1,
        "tools_used": ["codegraph", "repowise"],
    }


def test_resets_on_new_turn_counter(tmp_path: Path) -> None:
    transcript = tmp_path / "t.jsonl"
    # Two user markers now — a later turn_counter than the sentinel's 1.
    transcript.write_text('{"type":"user"}\n{"type":"user"}\n')
    _write_sentinel(
        tmp_path,
        {"transcript_id": "t", "turn_counter": 1, "tools_used": ["codegraph"]},
    )
    result = _run_hook(
        _stdin_for("mcp__plugin_repowise_repowise__get_risk", "t.jsonl"),
        tmp_path,
        {"CLAUDE_PROJECT_DIR": str(tmp_path), "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0

    sentinel = tmp_path / ".claude" / _SENTINEL_NAME
    payload = json.loads(sentinel.read_text())
    assert payload == {
        "transcript_id": "t",
        "turn_counter": 2,
        "tools_used": ["repowise"],
    }


def test_resets_on_new_transcript_id(tmp_path: Path) -> None:
    transcript = tmp_path / "other.jsonl"
    transcript.write_text('{"type":"user"}\n')
    # Sentinel belongs to a different transcript_id at the same turn_counter.
    _write_sentinel(
        tmp_path,
        {"transcript_id": "t", "turn_counter": 1, "tools_used": ["codegraph"]},
    )
    result = _run_hook(
        _stdin_for("mcp__plugin_repowise_repowise__get_risk", "other.jsonl"),
        tmp_path,
        {"CLAUDE_PROJECT_DIR": str(tmp_path), "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0

    sentinel = tmp_path / ".claude" / _SENTINEL_NAME
    payload = json.loads(sentinel.read_text())
    assert payload == {
        "transcript_id": "other",
        "turn_counter": 1,
        "tools_used": ["repowise"],
    }


def test_corrupt_tools_used_field_recovers_on_write(tmp_path: Path) -> None:
    transcript = tmp_path / "t.jsonl"
    transcript.write_text('{"type":"user"}\n')
    # Same transcript/turn, but tools_used is a string, not a list.
    _write_sentinel(
        tmp_path,
        {"transcript_id": "t", "turn_counter": 1, "tools_used": "codegraph"},
    )
    result = _run_hook(
        _stdin_for("mcp__plugin_repowise_repowise__get_context", "t.jsonl"),
        tmp_path,
        {"CLAUDE_PROJECT_DIR": str(tmp_path), "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0

    sentinel = tmp_path / ".claude" / _SENTINEL_NAME
    payload = json.loads(sentinel.read_text())
    assert payload == {
        "transcript_id": "t",
        "turn_counter": 1,
        "tools_used": ["repowise"],
    }


def test_legacy_schema_without_tools_used_fails_open(tmp_path: Path) -> None:
    transcript = tmp_path / "t.jsonl"
    transcript.write_text('{"type":"user"}\n')
    # Pre-Slice-2 schema: matches transcript/turn but has no tools_used at all.
    _write_sentinel(tmp_path, {"transcript_id": "t", "turn_counter": 1})
    result = _run_hook(
        _stdin_for("mcp__codegraph__codegraph_explore", "t.jsonl"),
        tmp_path,
        {"CLAUDE_PROJECT_DIR": str(tmp_path), "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0

    sentinel = tmp_path / ".claude" / _SENTINEL_NAME
    payload = json.loads(sentinel.read_text())
    assert payload == {
        "transcript_id": "t",
        "turn_counter": 1,
        "tools_used": ["codegraph"],
    }


def test_non_codegraph_tool_writes_no_sentinel(tmp_path: Path) -> None:
    stdin = _stdin_for("Read", "t.jsonl")
    (tmp_path / "t.jsonl").write_text('{"type":"user"}\n')
    result = _run_hook(
        stdin,
        tmp_path,
        {"CLAUDE_PROJECT_DIR": str(tmp_path), "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0
    assert not (tmp_path / ".claude" / _SENTINEL_NAME).exists()


def test_missing_transcript_writes_no_sentinel(tmp_path: Path) -> None:
    stdin = _stdin_for("mcp__codegraph__codegraph_node", "does-not-exist.jsonl")
    result = _run_hook(
        stdin,
        tmp_path,
        {"CLAUDE_PROJECT_DIR": str(tmp_path), "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0
    assert not (tmp_path / ".claude" / _SENTINEL_NAME).exists()


def test_malformed_stdin_fails_open(tmp_path: Path) -> None:
    result = _run_hook(
        "this is {not[ json",
        tmp_path,
        {"CLAUDE_PROJECT_DIR": str(tmp_path), "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0
    assert result.stdout == b""
    assert result.stderr == b""


def test_empty_stdin_fails_open(tmp_path: Path) -> None:
    result = _run_hook(
        "",
        tmp_path,
        {"CLAUDE_PROJECT_DIR": str(tmp_path), "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0


def test_atomic_write_preserved(tmp_path: Path) -> None:
    """Carried-over non-functional regression guard (not new behavior in
    this step): the write is still tempfile+rename, leaving no stray
    mkstemp temp files behind in `.claude/`. The `.lock` file is a new,
    intentional, persistent artifact from the read-modify-write lock
    (concurrency-review fix) — not a leftover temp file — so it's expected
    here, not absent."""
    (tmp_path / "t.jsonl").write_text('{"type":"user"}\n')
    stdin = _stdin_for("mcp__codegraph__codegraph_explore", "t.jsonl")
    _run_hook(
        stdin,
        tmp_path,
        {"CLAUDE_PROJECT_DIR": str(tmp_path), "PATH": "/usr/bin:/bin"},
    )
    files = sorted(p.name for p in (tmp_path / ".claude").iterdir())
    assert files == sorted([_SENTINEL_NAME, f"{_SENTINEL_NAME}.lock"]), (
        f"leftover temp files: {files}"
    )


def test_sentinel_json_bytes_match_pretty_indent2(tmp_path: Path) -> None:
    """Pretty-printed with `indent=2` and a trailing newline, matching the
    original .sh's `jq -n` output shape."""
    (tmp_path / "t.jsonl").write_text('{"type":"user"}\n')
    stdin = _stdin_for("mcp__codegraph__codegraph_explore", "t.jsonl")
    _run_hook(
        stdin,
        tmp_path,
        {"CLAUDE_PROJECT_DIR": str(tmp_path), "PATH": "/usr/bin:/bin"},
    )
    sentinel = tmp_path / ".claude" / _SENTINEL_NAME
    raw = sentinel.read_bytes()
    assert raw == (
        b'{\n'
        b'  "transcript_id": "t",\n'
        b'  "turn_counter": 1,\n'
        b'  "tools_used": [\n'
        b'    "codegraph"\n'
        b'  ]\n'
        b'}\n'
    )


def test_project_dir_falls_back_to_cwd(tmp_path: Path) -> None:
    """CLAUDE_PROJECT_DIR unset → PROJECT_DIR = $PWD (subprocess cwd)."""
    (tmp_path / "t.jsonl").write_text('{"type":"user"}\n')
    stdin = _stdin_for("mcp__codegraph__codegraph_explore", "t.jsonl")
    result = _run_hook(stdin, tmp_path, {"PATH": "/usr/bin:/bin"})
    assert result.returncode == 0
    assert (tmp_path / ".claude" / _SENTINEL_NAME).is_file()


# ---------------------------------------------------------------------------
# Read-modify-write lock — no lost updates under concurrent writers
# (concurrency-review)
# ---------------------------------------------------------------------------


def test_concurrent_writes_do_not_lose_updates(tmp_path: Path) -> None:
    """Two concurrent PostToolUse invocations for *different* tool families
    in the same turn must both survive in the final `tools_used` list.

    `CODE_INTELLIGENCE_TURN_MARK_TEST_DELAY_MS` widens the window between
    each process's read and write so the two subprocesses are guaranteed to
    overlap — without the read-modify-write lock, both would read the same
    empty `tools_used`, and whichever writes last would clobber the other's
    update (lost-update race). With the lock, the second process's read
    can't happen until the first's write (and lock release) completes, so
    both families accumulate correctly regardless of interleaving.
    """
    transcript = tmp_path / "t.jsonl"
    transcript.write_text('{"type":"user"}\n')

    hook_path = _HOOKS_DIR / "code_intelligence_turn_mark.py"
    env = {
        "CLAUDE_PROJECT_DIR": str(tmp_path),
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "CODE_INTELLIGENCE_TURN_MARK_TEST_DELAY_MS": "300",
    }
    stdins = [
        _stdin_for("mcp__codegraph__codegraph_explore", "t.jsonl"),
        _stdin_for("mcp__plugin_repowise_repowise__get_context", "t.jsonl"),
    ]
    procs = [
        subprocess.Popen(
            [sys.executable, str(hook_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(tmp_path),
            env=env,
        )
        for _ in stdins
    ]
    for proc, stdin in zip(procs, stdins):
        proc.stdin.write(stdin.encode("utf-8"))
        proc.stdin.close()
    for proc in procs:
        assert proc.wait(timeout=10) == 0

    sentinel = tmp_path / ".claude" / _SENTINEL_NAME
    payload = json.loads(sentinel.read_text())
    assert sorted(payload["tools_used"]) == ["codegraph", "repowise"]


# ---------------------------------------------------------------------------
# __main__ guard — fail-open on an uncaught exception (correctness-review)
# ---------------------------------------------------------------------------


def test_main_guard_fails_open_on_unexpected_exception(monkeypatch) -> None:
    """An exception `main()` itself doesn't catch (here: stdin.read() raising
    something other than the `(OSError, ValueError)` `_read_stdin` guards
    against) must still exit 0, per the module's own documented "fail-open,
    any internal error -> exit 0" posture and to match the sibling nudge
    hook's identical `__main__` guard.

    Runs the real file via `runpy.run_path(..., run_name="__main__")` so this
    exercises the actual `if __name__ == "__main__":` block, not a
    reimplementation of it.
    """
    import runpy
    import sys as _sys

    class _BoomStdin:
        def read(self) -> str:
            raise RuntimeError("boom — not OSError/ValueError, so _read_stdin can't swallow it")

    monkeypatch.setattr(_sys, "stdin", _BoomStdin())
    hook_path = _HOOKS_DIR / "code_intelligence_turn_mark.py"
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(str(hook_path), run_name="__main__")
    assert exc_info.value.code == 0
