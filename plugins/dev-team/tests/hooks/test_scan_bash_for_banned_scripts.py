"""Unit tests for hooks/scan_bash_for_banned_scripts.py (#1755).

Real-time PreToolUse denial of new shell-script writes under
plugins/dev-team/ — the point-of-write half of the #1755 hook pair.
scan_banned_scripts.py (PostToolUse, the working-tree backstop) has its own
test file.

No git repo needed: `project_root()` falls back to its `start` argument
when not inside a git repo, and pytest's `tmp_path` is never itself part of
one, so every scenario here treats `tmp_path` as the resolved root directly.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from _repo_root import REPO_ROOT as _REPO_ROOT

_HOOK = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "scan_bash_for_banned_scripts.py"


def _run(command: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "cwd": str(cwd),
        "tool_input": {"command": command},
    }
    return subprocess.run(
        [sys.executable, str(_HOOK)],
        input=json.dumps(payload),
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def test_allows_python_write(tmp_path: Path) -> None:
    result = _run("echo hi > plugins/dev-team/hooks/foo.py", tmp_path)
    assert result.returncode == 0


def test_blocks_new_shell_script_via_redirect(tmp_path: Path) -> None:
    result = _run("echo hi > plugins/dev-team/hooks/foo.sh", tmp_path)
    assert result.returncode == 2
    assert "plugins/dev-team/hooks/foo.sh" in result.stdout
    assert "plugins/dev-team/hooks/foo.sh" in result.stderr
    assert result.stdout.startswith("[BLOCK]")


def test_blocks_append_redirect(tmp_path: Path) -> None:
    result = _run("echo hi >> plugins/dev-team/scripts/run.bash", tmp_path)
    assert result.returncode == 2
    assert "run.bash" in result.stdout


def test_blocks_cp_destination(tmp_path: Path) -> None:
    result = _run("cp template.txt plugins/dev-team/scripts/run.sh", tmp_path)
    assert result.returncode == 2
    assert "run.sh" in result.stdout


def test_cp_multiple_sources_picks_last_arg_as_destination(tmp_path: Path) -> None:
    result = _run("cp a.py b.py plugins/dev-team/hooks/dest.cmd", tmp_path)
    assert result.returncode == 2
    assert "dest.cmd" in result.stdout


def test_flags_before_destination_are_ignored(tmp_path: Path) -> None:
    result = _run("cp -v a.py plugins/dev-team/hooks/dest.ps1", tmp_path)
    assert result.returncode == 2


def test_blocks_tee_destination(tmp_path: Path) -> None:
    result = _run("echo hi | tee plugins/dev-team/hooks/foo.sh", tmp_path)
    assert result.returncode == 2
    assert "foo.sh" in result.stdout


def test_blocks_mv_destination(tmp_path: Path) -> None:
    result = _run("mv /tmp/staged.txt plugins/dev-team/scripts/deploy.bat", tmp_path)
    assert result.returncode == 2


def test_allows_install_sh_carveout(tmp_path: Path) -> None:
    result = _run("cat > plugins/dev-team/install.sh", tmp_path)
    assert result.returncode == 0


def test_allows_py_sh_carveout(tmp_path: Path) -> None:
    result = _run("cp bootstrap.tpl plugins/dev-team/hooks/py.sh", tmp_path)
    assert result.returncode == 0


def test_ignores_repo_root_scripts_outside_plugin_scope(tmp_path: Path) -> None:
    result = _run("echo hi > scripts/dev-setup.sh", tmp_path)
    assert result.returncode == 0


def test_compound_command_still_matches_redirect(tmp_path: Path) -> None:
    result = _run(
        "git add -A && echo done > plugins/dev-team/hooks/generated.sh", tmp_path
    )
    assert result.returncode == 2
    assert "generated.sh" in result.stdout


def test_missing_command_passes(tmp_path: Path) -> None:
    payload = {"tool_name": "Bash", "cwd": str(tmp_path), "tool_input": {}}
    result = subprocess.run(
        [sys.executable, str(_HOOK)],
        input=json.dumps(payload),
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0


def test_malformed_json_stdin_passes(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(_HOOK)],
        input="not json{{{",
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0


def test_malformed_quoting_does_not_crash(tmp_path: Path) -> None:
    result = _run("echo 'unterminated", tmp_path)
    assert result.returncode == 0


def test_empty_stdin_passes(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(_HOOK)],
        input="",
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
