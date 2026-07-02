"""Unit tests for the Python port of hooks/codegraph-turn-mark.sh (#594).

White-box tests on the port's helpers + end-to-end sentinel-write behavior.
Byte-parity with the .sh is enforced by the parity harness at
tests/hooks/parity/test_codegraph_turn_mark_parity.py.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


_HOOKS_DIR = Path(__file__).resolve().parents[2] / "hooks"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

import codegraph_turn_mark as hook  # type: ignore[import-not-found]  # noqa: E402


# ---------------------------------------------------------------------------
# _is_codegraph_tool
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tool_name,expected",
    [
        ("mcp__codegraph__codegraph_explore", True),
        ("mcp__codegraph__codegraph_node", True),
        ("mcp__codegraph__anything_else", True),
        ("mcp__othermcp__thing", False),
        ("Read", False),
        ("Bash", False),
        ("", False),
        ("codegraph_explore", False),
    ],
)
def test_is_codegraph_tool(tool_name: str, expected: bool) -> None:
    assert hook._is_codegraph_tool(tool_name) is expected


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
    assert hook._transcript_id(path) == expected


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
    assert hook._count_user_lines(transcript) == 2


def test_count_user_lines_zero_when_no_user_markers(tmp_path: Path) -> None:
    transcript = tmp_path / "t.jsonl"
    transcript.write_text('{"type":"assistant"}\n{"type":"tool_use"}\n')
    assert hook._count_user_lines(transcript) == 0


def test_count_user_lines_zero_when_file_missing(tmp_path: Path) -> None:
    assert hook._count_user_lines(tmp_path / "nope.jsonl") == 0


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
    assert hook._count_user_lines(transcript) == 2


# ---------------------------------------------------------------------------
# End-to-end via subprocess — sentinel write + fail-open on bad input
# ---------------------------------------------------------------------------


def _run_hook(stdin: str, cwd: Path, env: dict) -> subprocess.CompletedProcess:
    hook_path = _HOOKS_DIR / "codegraph_turn_mark.py"
    return subprocess.run(
        [sys.executable, str(hook_path)],
        input=stdin.encode("utf-8"),
        capture_output=True,
        cwd=str(cwd),
        env=env,
        check=False,
    )


def test_happy_path_writes_sentinel_with_expected_shape(tmp_path: Path) -> None:
    transcript = tmp_path / "t.jsonl"
    transcript.write_text('{"type":"user"}\n{"type":"assistant"}\n{"type":"user"}\n')
    stdin = json.dumps(
        {
            "tool_name": "mcp__codegraph__codegraph_explore",
            "transcript_path": "t.jsonl",
        }
    )
    result = _run_hook(
        stdin,
        tmp_path,
        {
            "CLAUDE_PROJECT_DIR": str(tmp_path),
            "PATH": "/usr/bin:/bin",
        },
    )
    assert result.returncode == 0
    assert result.stdout == b""

    sentinel = tmp_path / ".claude" / "codegraph-turn-state.json"
    assert sentinel.is_file()
    payload = json.loads(sentinel.read_text())
    assert payload == {"transcript_id": "t", "turn_counter": 2}


def test_non_codegraph_tool_writes_no_sentinel(tmp_path: Path) -> None:
    stdin = json.dumps({"tool_name": "Read", "transcript_path": "t.jsonl"})
    (tmp_path / "t.jsonl").write_text('{"type":"user"}\n')
    result = _run_hook(
        stdin,
        tmp_path,
        {
            "CLAUDE_PROJECT_DIR": str(tmp_path),
            "PATH": "/usr/bin:/bin",
        },
    )
    assert result.returncode == 0
    assert not (tmp_path / ".claude" / "codegraph-turn-state.json").exists()


def test_missing_transcript_writes_no_sentinel(tmp_path: Path) -> None:
    stdin = json.dumps(
        {
            "tool_name": "mcp__codegraph__codegraph_node",
            "transcript_path": "does-not-exist.jsonl",
        }
    )
    result = _run_hook(
        stdin,
        tmp_path,
        {
            "CLAUDE_PROJECT_DIR": str(tmp_path),
            "PATH": "/usr/bin:/bin",
        },
    )
    assert result.returncode == 0
    assert not (tmp_path / ".claude" / "codegraph-turn-state.json").exists()


def test_malformed_stdin_fails_open(tmp_path: Path) -> None:
    result = _run_hook(
        "this is {not[ json",
        tmp_path,
        {
            "CLAUDE_PROJECT_DIR": str(tmp_path),
            "PATH": "/usr/bin:/bin",
        },
    )
    assert result.returncode == 0
    assert result.stdout == b""
    assert result.stderr == b""


def test_empty_stdin_fails_open(tmp_path: Path) -> None:
    result = _run_hook(
        "",
        tmp_path,
        {
            "CLAUDE_PROJECT_DIR": str(tmp_path),
            "PATH": "/usr/bin:/bin",
        },
    )
    assert result.returncode == 0


def test_atomic_sentinel_write_leaves_no_temp_files(tmp_path: Path) -> None:
    (tmp_path / "t.jsonl").write_text('{"type":"user"}\n')
    stdin = json.dumps(
        {
            "tool_name": "mcp__codegraph__codegraph_explore",
            "transcript_path": "t.jsonl",
        }
    )
    _run_hook(
        stdin,
        tmp_path,
        {
            "CLAUDE_PROJECT_DIR": str(tmp_path),
            "PATH": "/usr/bin:/bin",
        },
    )
    files = sorted(p.name for p in (tmp_path / ".claude").iterdir())
    assert files == ["codegraph-turn-state.json"], f"leftover temp files: {files}"


def test_sentinel_json_bytes_match_jq_default_indent2(tmp_path: Path) -> None:
    """The .sh writes via `jq -n` which pretty-prints with indent=2.

    The port must match byte-for-byte so the parity harness passes.
    """
    (tmp_path / "t.jsonl").write_text('{"type":"user"}\n')
    stdin = json.dumps(
        {
            "tool_name": "mcp__codegraph__codegraph_explore",
            "transcript_path": "t.jsonl",
        }
    )
    _run_hook(
        stdin,
        tmp_path,
        {
            "CLAUDE_PROJECT_DIR": str(tmp_path),
            "PATH": "/usr/bin:/bin",
        },
    )
    sentinel = tmp_path / ".claude" / "codegraph-turn-state.json"
    raw = sentinel.read_bytes()
    assert raw == (b'{\n  "transcript_id": "t",\n  "turn_counter": 1\n}\n')


def test_project_dir_falls_back_to_cwd(tmp_path: Path) -> None:
    """CLAUDE_PROJECT_DIR unset → PROJECT_DIR = $PWD (subprocess cwd)."""
    (tmp_path / "t.jsonl").write_text('{"type":"user"}\n')
    stdin = json.dumps(
        {
            "tool_name": "mcp__codegraph__codegraph_explore",
            "transcript_path": "t.jsonl",
        }
    )
    result = _run_hook(stdin, tmp_path, {"PATH": "/usr/bin:/bin"})
    assert result.returncode == 0
    assert (tmp_path / ".claude" / "codegraph-turn-state.json").is_file()
