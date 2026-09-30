"""Unit tests for hooks/lib/autocompact_config.py (#2177 slice 2)."""

from __future__ import annotations

import ast
import json
import os
import sys

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_LIB = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"
sys.path.insert(0, str(_LIB))

from autocompact_config import (
    KEY,
    Status,
    autocompact_configured,
    detect,
    validate_pct,
)


def _settings(root, name, env_value=None, raw=None):
    path = root / ".claude" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if raw is not None:
        path.write_text(raw, encoding="utf-8")
    else:
        path.write_text(json.dumps({"env": {KEY: env_value}}), encoding="utf-8")
    return path


@pytest.fixture
def env(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    return {"HOME": str(home)}


@pytest.fixture
def proj(tmp_path):
    p = tmp_path / "proj"
    p.mkdir()
    return p


@pytest.mark.parametrize("raw,expected", [("1", 1), ("40", 40), ("99", 99), ("100", 100)])
def test_validate_accepts_integers_1_to_100(raw, expected):
    assert validate_pct(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["0", "101", "-1", "40.0", " 40", "40 ", "+40", "", "abc", "040", "1e1", 40, None, True],
)
def test_validate_rejects_everything_else(raw):
    assert validate_pct(raw) is None


def test_absent_everywhere(proj, env):
    assert autocompact_configured(proj, env) is Status.ABSENT


def test_process_env_configures(proj, env):
    assert autocompact_configured(proj, {**env, KEY: "40"}) is Status.CONFIGURED


def test_process_env_invalid(proj, env):
    d = detect(proj, {**env, KEY: "abc"})
    assert (d.status, d.raw, d.source) == (Status.INVALID, "abc", "process env")


@pytest.mark.parametrize("name", ["settings.json", "settings.local.json"])
def test_project_files_configure(proj, env, name):
    _settings(proj, name, "50")
    assert autocompact_configured(proj, env) is Status.CONFIGURED


def test_user_settings_via_claude_config_dir(proj, env, tmp_path):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / "settings.json").write_text(json.dumps({"env": {KEY: "30"}}), encoding="utf-8")
    assert autocompact_configured(proj, {**env, "CLAUDE_CONFIG_DIR": str(cfg)}) is Status.CONFIGURED


def test_user_settings_via_home(proj, env):
    user = _settings_home(env)
    user.write_text(json.dumps({"env": {KEY: "30"}}), encoding="utf-8")
    assert autocompact_configured(proj, env) is Status.CONFIGURED


def _settings_home(env):
    from pathlib import Path

    path = Path(env["HOME"]) / ".claude" / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def test_json_number_value_is_invalid_not_configured(proj, env):
    _settings(proj, "settings.json", 40)
    d = detect(proj, env)
    assert d.status is Status.INVALID and d.raw == 40


def test_local_overrides_project(proj, env):
    _settings(proj, "settings.json", "40")
    _settings(proj, "settings.local.json", "abc")
    d = detect(proj, env)
    assert (d.status, d.source) == (Status.INVALID, "settings.local.json")


@pytest.mark.parametrize(
    "raw",
    ["{not json", "[]", '{"env": "x"}', '{"env": {}}', '{"env": {"OTHER": "1"}}', ""],
)
def test_malformed_or_keyless_settings_are_absent(proj, env, raw):
    _settings(proj, "settings.json", raw=raw)
    assert autocompact_configured(proj, env) is Status.ABSENT


@pytest.mark.skipif(
    os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="chmod 000 is not enforced for root / Windows",
)
def test_unreadable_settings_file_is_skipped(proj, env):
    path = _settings(proj, "settings.json", "40")
    path.chmod(0)
    try:
        assert autocompact_configured(proj, env) is Status.ABSENT
    finally:
        path.chmod(0o644)


def test_module_imports_nothing_from_scripts_or_claude_lib():
    tree = ast.parse((_LIB / "autocompact_config.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not imported & {"scripts", "session_start_common", "set_autocompact_env"}
