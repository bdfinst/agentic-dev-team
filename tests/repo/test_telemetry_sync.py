"""telemetry-sync.sh config validation (#178). Network/git paths aren't
exercised in CI; these cover the deterministic config-resolution + --check
contract that /session-review relies on to decide whether to prompt for a
repo location.

Ported from tests/repo/telemetry_sync_tests.bats (issue #672).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from _repo_root import REPO_ROOT

SYNC = REPO_ROOT / "scripts" / "telemetry-sync.sh"


def _check(tmp_path: Path, env_overrides: dict) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "DEV_TEAM_TELEMETRY_REMOTE"}
    env.update(env_overrides)
    return subprocess.run(
        ["bash", str(SYNC), "--check"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_sync_check_unconfigured_exits_3_with_guidance(tmp_path: Path) -> None:
    res = _check(tmp_path, {"DEV_TEAM_TELEMETRY_CONFIG": str(tmp_path / "none.json")})
    assert res.returncode == 3
    out = res.stdout + res.stderr
    assert "No telemetry repository configured" in out
    assert "telemetry-repo-security.md" in out


def test_sync_check_env_var_configures_the_remote_exit_0(tmp_path: Path) -> None:
    res = _check(
        tmp_path,
        {
            "DEV_TEAM_TELEMETRY_REMOTE": "git@github.com:o/r.git",
            "DEV_TEAM_TELEMETRY_CONFIG": str(tmp_path / "none.json"),
        },
    )
    assert res.returncode == 0, res.stdout + res.stderr
    assert "git@github.com:o/r.git" in res.stdout + res.stderr


def test_sync_check_config_file_configures_the_remote_exit_0(tmp_path: Path) -> None:
    cfg = tmp_path / "cfg.json"
    cfg.write_text('{"remote":"git@github.com:o/r.git","host":"box1"}\n')
    res = _check(tmp_path, {"DEV_TEAM_TELEMETRY_CONFIG": str(cfg)})
    assert res.returncode == 0, res.stdout + res.stderr
    out = res.stdout + res.stderr
    assert "git@github.com:o/r.git" in out
    assert "box1" in out


def test_sync_check_env_var_overrides_the_config_file(tmp_path: Path) -> None:
    cfg = tmp_path / "cfg.json"
    cfg.write_text('{"remote":"git@github.com:from/config.git"}\n')
    res = _check(
        tmp_path,
        {
            "DEV_TEAM_TELEMETRY_REMOTE": "git@github.com:from/env.git",
            "DEV_TEAM_TELEMETRY_CONFIG": str(cfg),
        },
    )
    assert res.returncode == 0, res.stdout + res.stderr
    out = res.stdout + res.stderr
    assert "from/env.git" in out
    assert "from/config.git" not in out
