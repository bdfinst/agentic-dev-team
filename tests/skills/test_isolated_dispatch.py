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


def test_build_cmd_resume_true_uses_resume_flag_not_session_id():
    """#999/#1002's harness-side retry-once backstop resumes the SAME
    session (`--resume <session_id>`) for a cheap follow-up dispatch,
    rather than starting a fresh one (`--session-id`)."""
    mod = _load()
    sid = mod.new_session_id()
    cmd = mod.build_cmd(
        prompt="re-emit the JSON only",
        session_id=sid,
        model="sonnet",
        skip_permissions=True,
        resume=True,
    )
    assert "--resume" in cmd
    passed = cmd[cmd.index("--resume") + 1]
    assert passed == sid
    assert "--session-id" not in cmd
    assert "--output-format" in cmd and "json" in cmd
    assert "--model" in cmd and "sonnet" in cmd


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


def test_copy_auth_state_copies_claude_dir_excluding_bulky_state(tmp_path):
    """#957 correction: ~/.claude.json alone doesn't restore login —
    confirmed empirically. Most of ~/.claude/ must come along too, minus
    the clearly bulky, clearly-not-auth-related entries."""
    mod = _load()
    source_home = tmp_path / "real-home"
    claude_dir = source_home / ".claude"
    claude_dir.mkdir(parents=True)
    (source_home / ".claude.json").write_text("{}", encoding="utf-8")

    # A kept entry (settings, plugins) alongside every excluded one.
    (claude_dir / "settings.json").write_text("{}", encoding="utf-8")
    (claude_dir / "history.jsonl").write_text("conversation history\n")
    for excluded_dir in (
        "file-history",
        "session-env",
        "paste-cache",
        "shell-snapshots",
        "debug",
        "telemetry",
        "downloads",
    ):
        (claude_dir / excluded_dir).mkdir()
        (claude_dir / excluded_dir / "some-file").write_text("stub")

    cell_home = tmp_path / "cell-home"
    cell_home.mkdir()
    (cell_home / ".claude").mkdir()

    assert mod.copy_auth_state(cell_home, source_home=source_home) is True

    copied_claude = cell_home / ".claude"
    assert (copied_claude / "settings.json").is_file()
    assert not (copied_claude / "history.jsonl").exists()
    for excluded_dir in (
        "file-history",
        "session-env",
        "paste-cache",
        "shell-snapshots",
        "debug",
        "telemetry",
        "downloads",
    ):
        assert not (copied_claude / excluded_dir).exists(), excluded_dir


def test_copy_auth_state_does_not_exclude_same_named_nested_dirs(tmp_path):
    """The exclude list is scoped to the TOP level of ~/.claude/ only —
    a plugin's own nested `debug/`-or-similar-named subdir must survive."""
    mod = _load()
    source_home = tmp_path / "real-home"
    claude_dir = source_home / ".claude"
    (claude_dir / "plugins" / "some-plugin" / "debug").mkdir(parents=True)
    (claude_dir / "plugins" / "some-plugin" / "debug" / "keep-me").write_text("stub")
    (source_home / ".claude.json").write_text("{}", encoding="utf-8")

    cell_home = tmp_path / "cell-home"
    cell_home.mkdir()
    (cell_home / ".claude").mkdir()

    assert mod.copy_auth_state(cell_home, source_home=source_home) is True
    nested = cell_home / ".claude" / "plugins" / "some-plugin" / "debug" / "keep-me"
    assert nested.is_file()


def test_copy_auth_state_handles_dangling_symlinks(tmp_path):
    """A stale plugin-marketplace symlink under ~/.claude/ must not crash
    the copy — copied as a (broken) link, not followed/failed on."""
    mod = _load()
    source_home = tmp_path / "real-home"
    claude_dir = source_home / ".claude"
    claude_dir.mkdir(parents=True)
    (source_home / ".claude.json").write_text("{}", encoding="utf-8")
    dangling = claude_dir / "broken-link"
    dangling.symlink_to(source_home / "does-not-exist")

    cell_home = tmp_path / "cell-home"
    cell_home.mkdir()
    (cell_home / ".claude").mkdir()

    assert mod.copy_auth_state(cell_home, source_home=source_home) is True
    copied_link = cell_home / ".claude" / "broken-link"
    assert copied_link.is_symlink()


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
