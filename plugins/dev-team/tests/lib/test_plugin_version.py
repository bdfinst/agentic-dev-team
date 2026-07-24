"""Unit tests for hooks/lib/plugin_version.py (#1078).

Covers scope resolution (project-for-cwd wins, else user, else first), exact
plugin-id matching (a sibling like aci-dev-team is never mistaken for it), and
the exit-code contract (0 printed / 1 not-installed / 2 record missing or
malformed).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(
    0, str(_REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib")
)

import plugin_version


def _seed(cfg: Path, record) -> None:
    plugins = cfg / "plugins"
    plugins.mkdir(parents=True, exist_ok=True)
    (plugins / "installed_plugins.json").write_text(json.dumps(record))


def _user(version="10.4.0"):
    return {"scope": "user", "version": version}


def _project(project_path, version="9.9.9"):
    return {"scope": "project", "projectPath": str(project_path), "version": version}


def test_user_scope_resolves(tmp_path):
    _seed(tmp_path, {"plugins": {"dev-team@bfinster": [_user("10.4.0")]}})
    line, code = plugin_version.resolve(str(tmp_path), str(tmp_path))
    assert code == 0
    assert line == "dev-team@bfinster v10.4.0 (scope: user)"


def test_project_scope_wins_for_matching_cwd(tmp_path):
    proj = tmp_path / "work"
    proj.mkdir()
    _seed(
        tmp_path,
        {"plugins": {"dev-team@bfinster": [_user("10.4.0"), _project(proj, "9.9.9")]}},
    )
    line, code = plugin_version.resolve(str(tmp_path), str(proj))
    assert code == 0
    assert line == "dev-team@bfinster v9.9.9 (scope: project)"


def test_project_scope_matches_nested_cwd(tmp_path):
    proj = tmp_path / "work"
    nested = proj / "src" / "deep"
    nested.mkdir(parents=True)
    _seed(tmp_path, {"plugins": {"dev-team@bfinster": [_project(proj, "9.9.9"), _user()]}})
    line, code = plugin_version.resolve(str(tmp_path), str(nested))
    assert code == 0 and "scope: project" in line


def test_project_scope_ignored_when_cwd_elsewhere(tmp_path):
    proj = tmp_path / "work"
    other = tmp_path / "other"
    proj.mkdir()
    other.mkdir()
    _seed(
        tmp_path,
        {"plugins": {"dev-team@bfinster": [_project(proj, "9.9.9"), _user("10.4.0")]}},
    )
    line, code = plugin_version.resolve(str(tmp_path), str(other))
    assert code == 0
    assert line == "dev-team@bfinster v10.4.0 (scope: user)"


def test_sibling_plugin_not_matched(tmp_path):
    _seed(tmp_path, {"plugins": {"aci-dev-team@tools": [_user("0.1.0")]}})
    line, code = plugin_version.resolve(str(tmp_path), str(tmp_path))
    assert code == 1 and line is None


def test_not_installed_exit_1(tmp_path):
    _seed(tmp_path, {"plugins": {"other@market": [_user()]}})
    _, code = plugin_version.resolve(str(tmp_path), str(tmp_path))
    assert code == 1


def test_missing_record_exit_2(tmp_path):
    # No installed_plugins.json written at all.
    _, code = plugin_version.resolve(str(tmp_path), str(tmp_path))
    assert code == 2


def test_malformed_record_exit_2(tmp_path):
    plugins = tmp_path / "plugins"
    plugins.mkdir(parents=True)
    (plugins / "installed_plugins.json").write_text("{not json")
    _, code = plugin_version.resolve(str(tmp_path), str(tmp_path))
    assert code == 2


def test_missing_version_falls_back_to_unknown(tmp_path):
    _seed(tmp_path, {"plugins": {"dev-team@bfinster": [{"scope": "user"}]}})
    line, code = plugin_version.resolve(str(tmp_path), str(tmp_path))
    assert code == 0
    assert line == "dev-team@bfinster vunknown (scope: user)"


def test_config_dir_honors_env(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    assert plugin_version.config_dir() == str(tmp_path)


def test_config_dir_defaults_to_home_claude(monkeypatch):
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    assert plugin_version.config_dir().endswith(".claude")
