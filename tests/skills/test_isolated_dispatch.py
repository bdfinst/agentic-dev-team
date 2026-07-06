"""Functional unit tests for isolated_dispatch.py (follow-up to issue #842).

These exercise the script's pure builder functions directly — they do NOT
spawn `claude`. The builders (`build_env`, `build_cmd`, `new_session_id`)
are importable so the isolation contract can be asserted without a subprocess:

  (a) build_env sets a fresh HOME/CLAUDE_CONFIG_DIR distinct from the parent;
  (b) build_env scrubs the enumerated Remote/session identity vars;
  (c) build_cmd contains `--session-id <valid uuid>` and never `--resume`.
"""

from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "plugins"
    / "dev-team"
    / "skills"
    / "headless-run"
    / "scripts"
    / "isolated_dispatch.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("isolated_dispatch", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_script_exists():
    assert _SCRIPT.is_file()


def test_build_env_sets_fresh_home_and_config_dir_distinct_from_parent(tmp_path):
    mod = _load()
    parent = {"HOME": "/home/parent", "CLAUDE_CONFIG_DIR": "/home/parent/.claude"}
    home = tmp_path / "cell-home"
    env = mod.build_env(home, base=parent)
    assert env["HOME"] == str(home)
    assert env["HOME"] != parent["HOME"]
    assert env["CLAUDE_CONFIG_DIR"] == str(home / ".claude")
    assert env["CLAUDE_CONFIG_DIR"] != parent["CLAUDE_CONFIG_DIR"]
    assert env["IS_SANDBOX"] == "1"
    assert env["DEV_TEAM_TELEMETRY"] == "off"


def test_build_env_scrubs_inherited_session_and_remote_vars(tmp_path):
    mod = _load()
    leaky = {
        "HOME": "/home/parent",
        "CLAUDE_SESSION_ID": "parent-session",
        "CLAUDE_CODE_SESSION_ID": "parent-session",
        "CLAUDE_CODE_ENTRYPOINT": "remote",
        "CLAUDE_CODE_REMOTE": "1",
        "CLAUDE_REMOTE_SESSION_ID": "abc",
        "PATH": "/usr/bin",
    }
    env = mod.build_env(tmp_path / "h", base=leaky)
    for scrubbed in (
        "CLAUDE_SESSION_ID",
        "CLAUDE_CODE_SESSION_ID",
        "CLAUDE_CODE_ENTRYPOINT",
        "CLAUDE_CODE_REMOTE",
        "CLAUDE_REMOTE_SESSION_ID",
    ):
        assert scrubbed not in env, f"{scrubbed} leaked into the child env"
    # Non-identity vars survive.
    assert env["PATH"] == "/usr/bin"


def test_new_session_id_is_a_valid_uuid():
    mod = _load()
    sid = mod.new_session_id()
    # Raises ValueError if not a valid uuid.
    assert str(uuid.UUID(sid)) == sid


def test_build_cmd_contains_session_id_uuid_and_no_resume():
    mod = _load()
    sid = mod.new_session_id()
    cmd = mod.build_cmd(
        prompt="/code-review",
        session_id=sid,
        model="sonnet",
        skip_permissions=True,
    )
    assert "--session-id" in cmd
    passed = cmd[cmd.index("--session-id") + 1]
    assert str(uuid.UUID(passed)) == passed  # a real uuid follows the flag
    assert "--output-format" in cmd and "json" in cmd
    assert "--resume" not in cmd
    assert "-r" not in cmd
    assert "--fork-session" not in cmd


def test_build_cmd_skip_permissions_flag_is_gated():
    mod = _load()
    sid = mod.new_session_id()
    with_skip = mod.build_cmd("p", sid, "sonnet", skip_permissions=True)
    without_skip = mod.build_cmd("p", sid, "sonnet", skip_permissions=False)
    assert "--dangerously-skip-permissions" in with_skip
    assert "--dangerously-skip-permissions" not in without_skip


def test_copy_auth_state_copies_claude_json_into_cell_home(tmp_path):
    mod = _load()
    source_home = tmp_path / "real-home"
    source_home.mkdir()
    (source_home / ".claude.json").write_text('{"userID": "abc"}', encoding="utf-8")

    cell_home = tmp_path / "cell-home"
    cell_home.mkdir()

    assert mod.copy_auth_state(cell_home, source_home=source_home) is True
    copied = (cell_home / ".claude.json").read_text(encoding="utf-8")
    assert copied == '{"userID": "abc"}'


def test_copy_auth_state_false_when_source_missing(tmp_path):
    mod = _load()
    source_home = tmp_path / "no-claude-json-here"
    source_home.mkdir()
    cell_home = tmp_path / "cell-home"
    cell_home.mkdir()

    assert mod.copy_auth_state(cell_home, source_home=source_home) is False
    assert not (cell_home / ".claude.json").exists()


def test_main_preserve_auth_flag_defaults_off(monkeypatch, tmp_path):
    mod = _load()
    captured = {}

    def fake_run(prompt, cwd, model, timeout, preserve_auth=False):
        captured["preserve_auth"] = preserve_auth
        return 0

    monkeypatch.setattr(mod, "run", fake_run)
    mod.main(["say hi"])
    assert captured["preserve_auth"] is False


def test_main_preserve_auth_flag_can_be_enabled(monkeypatch, tmp_path):
    mod = _load()
    captured = {}

    def fake_run(prompt, cwd, model, timeout, preserve_auth=False):
        captured["preserve_auth"] = preserve_auth
        return 0

    monkeypatch.setattr(mod, "run", fake_run)
    mod.main(["say hi", "--preserve-auth"])
    assert captured["preserve_auth"] is True
