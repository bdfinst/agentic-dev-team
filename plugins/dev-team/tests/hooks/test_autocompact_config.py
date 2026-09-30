"""Unit tests for hooks/lib/autocompact_config.py (#2177 slice 2)."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

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


def _user(env, value):
    path = Path(env["HOME"]) / ".claude" / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"env": {KEY: value}}), encoding="utf-8")
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
    [
        "0", "101", "-1", "40.0", " 40", "40 ", "+40", "", "abc", "040", "1e1",
        "40\n", "\n40", "４０", "٤٠", "00", "0100", "1_0", "0x28", "100 ", "1000",
        40, None, True, 40.0, ["40"],
    ],
)  # fmt: skip
def test_validate_rejects_everything_else(raw):
    assert validate_pct(raw) is None


def test_absent_everywhere(proj, env):
    assert autocompact_configured(proj, env) is Status.ABSENT


def test_process_env_configures(proj, env):
    assert autocompact_configured(proj, {**env, KEY: "40"}) is Status.CONFIGURED


def test_process_env_invalid(proj, env):
    d = detect(proj, {**env, KEY: "abc"})
    assert (d.status, d.raw, d.source) == (Status.INVALID, "abc", "process env")


def test_empty_process_env_value_is_invalid_not_absent(proj, env):
    d = detect(proj, {**env, KEY: ""})
    assert (d.status, d.raw, d.source) == (Status.INVALID, "", "process env")


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
    _user(env, "30")
    assert autocompact_configured(proj, env) is Status.CONFIGURED


def test_claude_config_dir_wins_over_home(proj, env, tmp_path):
    _user(env, "abc")  # HOME copy is invalid
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / "settings.json").write_text(json.dumps({"env": {KEY: "30"}}), encoding="utf-8")
    d = detect(proj, {**env, "CLAUDE_CONFIG_DIR": str(cfg)})
    assert (d.status, d.source) == (Status.CONFIGURED, "user settings.json")


def test_json_number_value_is_invalid_not_configured(proj, env):
    _settings(proj, "settings.json", 40)
    d = detect(proj, env)
    assert d.status is Status.INVALID and d.raw == 40


@pytest.mark.parametrize(
    "layers,expected_source,expected_status",
    [
        # env > local > project > user; first source defining the key decides
        ({"env": "10", "local": "20", "project": "30", "user": "40"}, "process env", Status.CONFIGURED),
        ({"local": "20", "project": "30", "user": "40"}, "settings.local.json", Status.CONFIGURED),
        ({"project": "30", "user": "40"}, "settings.json", Status.CONFIGURED),
        ({"user": "40"}, "user settings.json", Status.CONFIGURED),
        ({"local": "20", "project": "abc"}, "settings.local.json", Status.CONFIGURED),
        ({"local": "abc", "project": "30"}, "settings.local.json", Status.INVALID),
        ({"env": "abc", "local": "20"}, "process env", Status.INVALID),
        ({"project": "abc", "user": "40"}, "settings.json", Status.INVALID),
    ],
)  # fmt: skip
def test_precedence_matrix(proj, env, layers, expected_source, expected_status):
    process_env = dict(env)
    if "env" in layers:
        process_env[KEY] = layers["env"]
    if "local" in layers:
        _settings(proj, "settings.local.json", layers["local"])
    if "project" in layers:
        _settings(proj, "settings.json", layers["project"])
    if "user" in layers:
        _user(env, layers["user"])
    d = detect(proj, process_env)
    assert (d.source, d.status) == (expected_source, expected_status)


def test_local_overrides_project(proj, env):
    _settings(proj, "settings.json", "40")
    _settings(proj, "settings.local.json", "abc")
    d = detect(proj, env)
    assert (d.status, d.source) == (Status.INVALID, "settings.local.json")


@pytest.mark.parametrize(
    "raw",
    ["{not json", "[]", '{"env": "x"}', '{"env": {}}', '{"env": {"OTHER": "1"}}', "", "null"],
)
def test_malformed_or_keyless_settings_are_absent(proj, env, raw):
    _settings(proj, "settings.json", raw=raw)
    assert autocompact_configured(proj, env) is Status.ABSENT


def test_invalid_utf8_settings_are_skipped(proj, env):
    path = _settings(proj, "settings.json", raw="")
    path.write_bytes(b"\xff\xfe\x00")
    assert autocompact_configured(proj, env) is Status.ABSENT


def test_settings_path_that_is_a_directory_is_skipped(proj, env):
    (proj / ".claude" / "settings.json").mkdir(parents=True)
    assert autocompact_configured(proj, env) is Status.ABSENT


def test_deeply_nested_settings_json_is_skipped(proj, env):
    _settings(proj, "settings.json", raw="[" * 200_000)
    assert autocompact_configured(proj, env) is Status.ABSENT


def test_module_imports_nothing_from_scripts_or_claude_lib():
    tree = ast.parse((_LIB / "autocompact_config.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not imported & {"scripts", "session_start_common", "set_autocompact_env"}
