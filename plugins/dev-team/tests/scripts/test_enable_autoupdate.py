"""Unit tests for skills/upgrade/scripts/enable_autoupdate.py.

The single source of truth for the marketplace ``autoUpdate`` flag, shared by
the ``/upgrade`` skill and the cloud bootstrap scripts. Exercises the two modes
(``--check`` reporting, ``--enable`` writing), idempotency, config-dir isolation,
registry seeding, and the fail-open contract.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(
    0, str(_REPO_ROOT / "plugins" / "dev-team" / "skills" / "upgrade" / "scripts")
)

import enable_autoupdate  # noqa: E402


def _seed_config(cfg: Path, *, installed=True, registry=True):
    """Write a minimal config dir: installed_plugins.json + known_marketplaces.json."""
    plugins = cfg / "plugins"
    plugins.mkdir(parents=True, exist_ok=True)
    if installed:
        (plugins / "installed_plugins.json").write_text(
            json.dumps(
                {"plugins": {"dev-team@bfinster": [{"scope": "user", "version": "9.9.9"}]}}
            )
        )
    if registry:
        (plugins / "known_marketplaces.json").write_text(
            json.dumps(
                {"bfinster": {"source": {"source": "github", "repo": "bdfinst/agentic-dev-team"}}}
            )
        )


@pytest.fixture()
def cfg(tmp_path, monkeypatch):
    d = tmp_path / "config"
    d.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(d))
    # Run from an empty cwd so a real project .claude/settings.json can't interfere.
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    return d


def _settings(cfg: Path) -> dict:
    return json.loads((cfg / "settings.json").read_text())


def test_check_disabled_by_default(cfg):
    _seed_config(cfg)
    assert enable_autoupdate.check(str(cfg)) == "disabled"


def test_check_unknown_when_not_installed(cfg):
    _seed_config(cfg, installed=False)
    assert enable_autoupdate.check(str(cfg)) == "unknown"


def test_enable_sets_flag_and_seeds_source(cfg):
    _seed_config(cfg)
    msg = enable_autoupdate.enable(str(cfg))
    assert "enabled for 'bfinster'" in msg
    data = _settings(cfg)
    mk = data["extraKnownMarketplaces"]["bfinster"]
    assert mk["autoUpdate"] is True
    # Seeded from the registry so the flag has a valid home.
    assert mk["source"] == {"source": "github", "repo": "bdfinst/agentic-dev-team"}
    assert enable_autoupdate.check(str(cfg)) == "enabled"


def test_enable_is_idempotent(cfg):
    _seed_config(cfg)
    enable_autoupdate.enable(str(cfg))
    msg = enable_autoupdate.enable(str(cfg))
    assert "already enabled" in msg
    assert enable_autoupdate.check(str(cfg)) == "enabled"


def test_enable_preserves_existing_settings(cfg):
    _seed_config(cfg)
    (cfg / "settings.json").write_text(
        json.dumps({"enabledPlugins": {"dev-team@bfinster": True}})
    )
    enable_autoupdate.enable(str(cfg))
    data = _settings(cfg)
    assert data["enabledPlugins"] == {"dev-team@bfinster": True}
    assert data["extraKnownMarketplaces"]["bfinster"]["autoUpdate"] is True


def test_enable_no_plugin_is_noop(cfg):
    _seed_config(cfg, installed=False)
    msg = enable_autoupdate.enable(str(cfg))
    assert "nothing to do" in msg
    assert not (cfg / "settings.json").exists()


def test_main_enable_never_fails_on_bad_settings(cfg, capsys):
    _seed_config(cfg)
    (cfg / "settings.json").write_text("{ this is not json")
    # Malformed settings.json is treated as absent; enable still succeeds fail-open.
    rc = enable_autoupdate.main(["--enable"])
    assert rc == 0
    assert enable_autoupdate.check(str(cfg)) == "enabled"


def test_main_check_prints_status(cfg, capsys):
    _seed_config(cfg)
    rc = enable_autoupdate.main(["--check"])
    assert rc == 0
    assert capsys.readouterr().out.strip() == "disabled"
