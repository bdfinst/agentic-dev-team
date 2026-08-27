"""Tests for .claude/ensure_session_archive.py — the SessionStart hook that
archives new/changed sessions to a durable local file before Claude Code's
30-day transcript retention ages them out (#2018, the "small and urgent"
archival half — the per-session plugin-version attribution half is tracked
separately and this hook does not touch it).

Every test runs the real script as a subprocess against a throwaway
``tmp_path`` standing in for both the project root and ``$HOME`` (so
``~/.claude/projects`` and ``~/.cache/...`` never touch the real machine),
using the REAL ``scripts/session_extract.py`` from this checkout — it is
deterministic and stdlib-only, so running it for real against a tiny
synthetic transcript is both faithful and safe.
"""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
from pathlib import Path

from _repo_root import REPO_ROOT

SCRIPT = REPO_ROOT / ".claude" / "ensure_session_archive.py"


def _scaffold_repo(root: Path, *, in_repo: bool = True) -> None:
    if in_repo:
        (root / "requirements-dev.txt").write_text("")
        plugin_dir = root / "plugins" / "dev-team" / ".claude-plugin"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.json").write_text(json.dumps({"version": "9.9.9"}))
        (root / "scripts").mkdir(parents=True, exist_ok=True)
        shutil.copy(
            REPO_ROOT / "scripts" / "session_extract.py",
            root / "scripts" / "session_extract.py",
        )
        # session_extract.py imports from plugins/dev-team/scripts/lib/
        # session_log/ (#2042-#2044, epic #2040) -- the fake checkout needs
        # that real dependency too, not just the script itself.
        session_log_dir = (
            root / "plugins" / "dev-team" / "scripts" / "lib" / "session_log"
        )
        shutil.copytree(
            REPO_ROOT
            / "plugins"
            / "dev-team"
            / "scripts"
            / "lib"
            / "session_log",
            session_log_dir,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
    claude_lib = root / ".claude" / "lib"
    claude_lib.mkdir(parents=True, exist_ok=True)
    shutil.copy(
        REPO_ROOT / ".claude" / "lib" / "session_start_common.py",
        claude_lib / "session_start_common.py",
    )


def _write_transcript(home: Path, project_slug: str, session_id: str) -> Path:
    proj = home / ".claude" / "projects" / project_slug
    proj.mkdir(parents=True, exist_ok=True)
    rec = {
        "type": "assistant",
        "sessionId": session_id,
        "cwd": "/fake/proj",
        "timestamp": "2026-08-27T00:00:00Z",
        "isSidechain": False,
        "message": {
            "role": "assistant",
            "model": "claude-sonnet-5",
            "content": [{"type": "text", "text": "hi"}],
            "usage": {"input_tokens": 10, "output_tokens": 5},
        },
    }
    path = proj / f"{session_id}.jsonl"
    path.write_text(json.dumps(rec) + "\n")
    return path


def _run(root: Path, home: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(root)
    env["HOME"] = str(home)
    return subprocess.run(
        ["python3", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_syntax_is_valid() -> None:
    ast.parse(SCRIPT.read_text())


def test_noop_outside_this_repos_own_checkout(tmp_path: Path) -> None:
    """A downstream project that merely has the plugin installed must never
    have this hook try to run scripts/session_extract.py, which only ships
    in THIS repo's own checkout."""
    root = tmp_path / "downstream"
    root.mkdir()
    home = tmp_path / "home"
    _scaffold_repo(root, in_repo=False)
    result = _run(root, home)
    assert result.returncode == 0
    assert result.stdout == ""
    assert not (root / ".claude" / "metrics").exists()


def test_noop_when_session_start_common_missing(tmp_path: Path) -> None:
    """Fail-open: a partial checkout missing the shared lib must not crash
    or block session start."""
    root = tmp_path / "repo"
    root.mkdir()
    home = tmp_path / "home"
    (root / "requirements-dev.txt").write_text("")
    result = _run(root, home)
    assert result.returncode == 0


def test_archives_a_new_session_and_writes_the_watermark(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    home = tmp_path / "home"
    _scaffold_repo(root)
    _write_transcript(home, "-fake-proj", "session-one")

    result = _run(root, home)
    assert result.returncode == 0, result.stdout + result.stderr

    digest_path = root / ".claude" / "metrics" / "session-digest.jsonl"
    assert digest_path.is_file()
    lines = [json.loads(line) for line in digest_path.read_text().splitlines()]
    assert len(lines) == 1
    assert lines[0]["session_id"] == "session-one"
    assert lines[0]["tokens"]["input_tokens"] == 10

    watermark_path = root / ".claude" / "metrics" / "session-digest-watermark.json"
    assert watermark_path.is_file()
    assert "session-one" in json.loads(watermark_path.read_text())["synced"]


def test_second_run_is_a_true_noop_via_the_watermark(tmp_path: Path) -> None:
    """The watermark must make a re-run genuinely incremental -- a session
    already archived is never re-appended, so the file this hook writes on
    every session start does not grow unbounded with duplicates."""
    root = tmp_path / "repo"
    root.mkdir()
    home = tmp_path / "home"
    _scaffold_repo(root)
    _write_transcript(home, "-fake-proj", "session-one")

    first = _run(root, home)
    assert first.returncode == 0, first.stdout + first.stderr
    second = _run(root, home)
    assert second.returncode == 0, second.stdout + second.stderr

    digest_path = root / ".claude" / "metrics" / "session-digest.jsonl"
    lines = digest_path.read_text().splitlines()
    assert len(lines) == 1


def test_never_writes_outside_dot_claude_metrics(tmp_path: Path) -> None:
    """This hook must never touch the cross-machine telemetry-sync
    mechanism (scripts/telemetry-sync.sh) -- no git clone, commit, or push.
    Confirmed by construction: no .git directory appears anywhere under
    tmp_path after a run."""
    root = tmp_path / "repo"
    root.mkdir()
    home = tmp_path / "home"
    _scaffold_repo(root)
    _write_transcript(home, "-fake-proj", "session-one")

    result = _run(root, home)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not list(tmp_path.rglob(".git"))


def test_hook_is_registered_in_settings_json() -> None:
    """An unregistered SessionStart hook script is a silent no-op in
    practice -- it never runs. Pin the registration alongside its siblings."""
    settings = json.loads((REPO_ROOT / ".claude" / "settings.json").read_text())
    commands = [
        h["command"] for h in settings["hooks"]["SessionStart"][0]["hooks"]
    ]
    assert any("ensure_session_archive.py" in c for c in commands)
