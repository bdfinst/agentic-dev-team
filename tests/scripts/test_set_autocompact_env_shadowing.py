"""Shadowing and atomic-write hardening for set_autocompact_env.py (#2177, PR #2232 review)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

_SCRIPT = REPO_ROOT / "plugins" / "dev-team" / "scripts" / "set_autocompact_env.py"
sys.path.insert(0, str(_SCRIPT.parent))

import set_autocompact_env as sae

KEY = "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE"


def _clean_env(extra: dict | None = None) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE_")}
    env.update(extra or {})
    return env


def _cli(project: Path, env: dict, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), "--project-dir", str(project), *args],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        env=env,
        check=False,
    )


def _settings(project: Path) -> Path:
    return project / ".claude" / "settings.json"


def _written_env(project: Path) -> dict:
    return json.loads(_settings(project).read_text(encoding="utf-8"))["env"]


@pytest.mark.parametrize("local_value", ["abc", "60"])
def test_settings_local_shadowing_is_reported_and_not_written_elsewhere(tmp_path, local_value):
    local = tmp_path / ".claude" / "settings.local.json"
    local.parent.mkdir(parents=True)
    local_bytes = json.dumps({"env": {KEY: local_value}}).encode()
    local.write_bytes(local_bytes)
    result = _cli(tmp_path, _clean_env(), "--yes", "--autocompact-pct", "40")
    assert result.returncode == 0, result.stderr
    assert _written_env(tmp_path)[KEY] == "40"
    assert local.read_bytes() == local_bytes
    assert "settings.local.json" in result.stdout
    assert "takes precedence" in result.stdout


def test_process_env_shadowing_is_reported(tmp_path):
    result = _cli(tmp_path, _clean_env({KEY: "abc"}), "--yes")
    assert result.returncode == 0
    assert "process env" in result.stdout
    assert "takes precedence" in result.stdout


def test_no_shadow_warning_when_settings_json_is_effective(tmp_path):
    result = _cli(tmp_path, _clean_env(), "--yes")
    assert "takes precedence" not in result.stdout


def test_user_settings_do_not_count_as_shadowing(tmp_path):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "settings.json").write_text(json.dumps({"env": {KEY: "abc"}}), "utf-8")
    proj = tmp_path / "proj"
    proj.mkdir()
    result = _cli(proj, _clean_env({"HOME": str(home)}), "--yes")
    assert "takes precedence" not in result.stdout


def test_atomic_write_does_not_follow_a_planted_fixed_tmp_symlink(tmp_path):
    victim = tmp_path / "victim.txt"
    victim.write_text("precious", encoding="utf-8")
    (tmp_path / ".claude").mkdir()
    os.symlink(victim, tmp_path / ".claude" / "settings.json.tmp")
    assert _cli(tmp_path, _clean_env(), "--yes").returncode == 0
    assert victim.read_text(encoding="utf-8") == "precious"
    assert _written_env(tmp_path)[KEY] == "40"


@pytest.mark.skipif(os.name == "nt", reason="POSIX modes")
def test_atomic_write_preserves_existing_file_mode(tmp_path):
    _settings(tmp_path).parent.mkdir()
    _settings(tmp_path).write_text(json.dumps({"env": {"FOO": "1"}}), encoding="utf-8")
    _settings(tmp_path).chmod(0o640)
    assert _cli(tmp_path, _clean_env(), "--yes").returncode == 0
    assert _settings(tmp_path).stat().st_mode & 0o777 == 0o640


def test_failed_write_leaves_no_temp_file(tmp_path, monkeypatch):
    _settings(tmp_path).parent.mkdir()
    _settings(tmp_path).write_text(json.dumps({"env": {"FOO": "1"}}), encoding="utf-8")

    def deny(*_a, **_k):
        raise PermissionError("denied")

    monkeypatch.setattr(sae.os, "replace", deny)
    with pytest.raises(sae.SetupError):
        sae.run(tmp_path, None, True, False, interactive=False, environ={})
    assert [p.name for p in (tmp_path / ".claude").iterdir()] == ["settings.json"]
