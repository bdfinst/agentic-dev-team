"""Unit tests for skills/upgrade/scripts/check_version_drift.py.

Covers the drift comparison (installed vs catalog), the silent-when-current and
silent-when-indeterminate contracts, and the two output modes (plain line vs
SessionStart hookSpecificOutput JSON).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(
    0, str(_REPO_ROOT / "plugins" / "dev-team" / "skills" / "upgrade" / "scripts")
)

import check_version_drift


def _seed(cfg: Path, *, installed="10.1.0", catalog="10.1.0", registry=True):
    plugins = cfg / "plugins"
    plugins.mkdir(parents=True, exist_ok=True)
    if installed is not None:
        (plugins / "installed_plugins.json").write_text(
            json.dumps(
                {"plugins": {"dev-team@bfinster": [{"scope": "user", "version": installed}]}}
            )
        )
    market_dir = cfg / "marketplaces" / "bfinster"
    if registry:
        (plugins / "known_marketplaces.json").write_text(
            json.dumps({"bfinster": {"installLocation": str(market_dir)}})
        )
    if catalog is not None:
        cp = market_dir / ".claude-plugin"
        cp.mkdir(parents=True, exist_ok=True)
        (cp / "marketplace.json").write_text(
            json.dumps({"plugins": [{"name": "dev-team", "version": catalog}]})
        )


@pytest.fixture()
def cfg(tmp_path, monkeypatch):
    d = tmp_path / "config"
    d.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(d))
    return d


def test_silent_when_current(cfg):
    _seed(cfg, installed="10.1.0", catalog="10.1.0")
    assert check_version_drift.advisory(str(cfg)) == ""


def test_advisory_when_catalog_ahead(cfg):
    _seed(cfg, installed="9.9.0", catalog="10.1.0")
    msg = check_version_drift.advisory(str(cfg))
    assert "v9.9.0" in msg and "v10.1.0" in msg and "/upgrade" in msg


def test_silent_when_not_installed(cfg):
    _seed(cfg, installed=None)
    assert check_version_drift.advisory(str(cfg)) == ""


def test_silent_when_catalog_missing(cfg):
    _seed(cfg, catalog=None)
    assert check_version_drift.advisory(str(cfg)) == ""


def test_silent_when_registry_missing(cfg):
    _seed(cfg, registry=False, catalog=None)
    assert check_version_drift.advisory(str(cfg)) == ""


def test_main_plain_prints_line(cfg, capsys):
    _seed(cfg, installed="9.9.0", catalog="10.1.0")
    rc = check_version_drift.main([])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert out.startswith("dev-team plugin is v9.9.0")


def test_main_session_start_emits_hook_json(cfg, capsys):
    _seed(cfg, installed="9.9.0", catalog="10.1.0")
    rc = check_version_drift.main(["--session-start"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    hso = payload["hookSpecificOutput"]
    assert hso["hookEventName"] == "SessionStart"
    assert "v10.1.0" in hso["additionalContext"]


def test_main_session_start_silent_when_current(cfg, capsys):
    _seed(cfg, installed="10.1.0", catalog="10.1.0")
    rc = check_version_drift.main(["--session-start"])
    assert rc == 0
    assert capsys.readouterr().out.strip() == ""
