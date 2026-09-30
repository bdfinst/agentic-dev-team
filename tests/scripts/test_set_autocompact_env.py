"""Tests for plugins/dev-team/scripts/set_autocompact_env.py (#2177 slice 2)."""

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


def _cli(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), "--project-dir", str(project), *args],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        check=False,
    )


def _settings(project: Path) -> Path:
    return project / ".claude" / "settings.json"


def _put(project: Path, content: str | dict) -> bytes:
    path = _settings(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = content if isinstance(content, str) else json.dumps(content)
    path.write_text(text, encoding="utf-8")
    return path.read_bytes()


def _env(project: Path) -> dict:
    return json.loads(_settings(project).read_text(encoding="utf-8"))["env"]


def test_default_written_as_string_and_other_keys_preserved(tmp_path):
    _put(tmp_path, {"env": {"FOO": "1"}, "permissions": {"allow": ["Bash(ls)"]}})
    result = _cli(tmp_path, "--yes")
    assert result.returncode == 0, result.stderr
    data = json.loads(_settings(tmp_path).read_text(encoding="utf-8"))
    assert data == {
        "env": {"FOO": "1", KEY: "40"},
        "permissions": {"allow": ["Bash(ls)"]},
    }
    assert isinstance(data["env"][KEY], str)


def test_fresh_repo_creates_settings_with_only_the_key(tmp_path):
    assert _cli(tmp_path, "--yes").returncode == 0
    assert json.loads(_settings(tmp_path).read_text(encoding="utf-8")) == {"env": {KEY: "40"}}


@pytest.mark.parametrize("value", ["1", "40", "100"])
def test_accepted_flag_values(tmp_path, value):
    assert _cli(tmp_path, "--autocompact-pct", value).returncode == 0
    assert _env(tmp_path)[KEY] == value


@pytest.mark.parametrize("value", ["0", "101", "-1", "40.0", " 40", "+40", "", "abc"])
def test_rejected_flag_values_leave_bytes_unchanged(tmp_path, value):
    before = _put(tmp_path, {"env": {"FOO": "1"}})
    result = _cli(tmp_path, f"--autocompact-pct={value}")
    assert result.returncode == 2
    assert f"invalid --autocompact-pct '{value}': expected integer 1-100" in result.stderr
    assert _settings(tmp_path).read_bytes() == before


@pytest.mark.parametrize(
    "existing,flag,final,needle",
    [
        (None, None, "40", "set CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=40"),
        (None, "55", "55", "set CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=55"),
        (
            "60",
            None,
            "60",
            "kept existing CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=60 (pass --autocompact-pct to change)",
        ),
        ("60", "55", "55", "set CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=55"),
        ("abc", None, "40", "replaced invalid value 'abc' with 40"),
    ],
)
def test_existing_value_truth_table_with_yes(tmp_path, existing, flag, final, needle):
    if existing is not None:
        _put(tmp_path, {"env": {KEY: existing}})
    args = ["--yes"] + (["--autocompact-pct", flag] if flag else [])
    result = _cli(tmp_path, *args)
    assert result.returncode == 0, result.stderr
    assert _env(tmp_path)[KEY] == final
    assert needle in result.stdout


def test_prompt_enter_keeps_existing_value(tmp_path):
    _put(tmp_path, {"env": {KEY: "60"}})
    lines = sae.run(tmp_path, None, False, False, interactive=True, input_fn=lambda _p: "")
    assert _env(tmp_path)[KEY] == "60"
    assert any("kept existing" in line for line in lines)


def test_prompt_answer_overrides_and_states_its_effect(tmp_path):
    seen: list[str] = []

    def fake_input(prompt: str) -> str:
        seen.append(prompt)
        return "55"

    sae.run(tmp_path, None, False, False, interactive=True, input_fn=fake_input)
    assert _env(tmp_path)[KEY] == "55"
    expected = (
        "Autocompact at what % of the window? [40] "
        "(40% ~ 80K tokens on a 200K window; lower = earlier compaction) "
    )
    assert seen == [expected]


def test_prompt_invalid_answer_aborts_without_writing(tmp_path):
    with pytest.raises(sae.SetupError):
        sae.run(tmp_path, None, False, False, interactive=True, input_fn=lambda _p: "abc")
    assert not _settings(tmp_path).exists()


def test_yes_never_prompts(tmp_path):
    def boom(_p: str) -> str:
        raise AssertionError("prompted under --yes")

    sae.run(tmp_path, None, True, False, interactive=True, input_fn=boom)
    assert _env(tmp_path)[KEY] == "40"


def test_lower_only_warning_when_above_harness_default(tmp_path):
    result = _cli(tmp_path, "--autocompact-pct", "90")
    assert result.returncode == 0
    assert _env(tmp_path)[KEY] == "90"
    assert (
        "90 exceeds the harness default (~83%); values above the default are ignored, "
        "so compaction will still occur at the default"
    ) in result.stdout


def test_no_autocompact_leaves_settings_alone_and_writes_marker(tmp_path):
    before = _put(tmp_path, {"env": {"FOO": "1"}})
    assert _cli(tmp_path, "--no-autocompact").returncode == 0
    assert _settings(tmp_path).read_bytes() == before
    assert (tmp_path / ".claude" / "memory" / "autocompact-nudge-off").exists()


def test_rerun_is_idempotent(tmp_path):
    assert _cli(tmp_path, "--yes").returncode == 0
    first = _settings(tmp_path).read_bytes()
    assert _cli(tmp_path, "--yes").returncode == 0
    assert _settings(tmp_path).read_bytes() == first


@pytest.mark.parametrize(
    "content,needle",
    [
        ("{not json", "malformed settings.json:"),
        ("[1, 2]", "top level is not an object"),
        ('{"env": "x"}', '"env" is not an object'),
    ],
)
def test_hostile_settings_abort_with_bytes_unchanged(tmp_path, content, needle):
    before = _put(tmp_path, content)
    result = _cli(tmp_path, "--yes")
    assert result.returncode == 2
    assert needle in result.stderr and str(_settings(tmp_path)) in result.stderr
    assert _settings(tmp_path).read_bytes() == before
    assert not list((tmp_path / ".claude").glob("*.tmp"))


def test_symlinked_settings_refused(tmp_path):
    target = tmp_path / "real.json"
    target.write_text("{}", encoding="utf-8")
    (tmp_path / ".claude").mkdir()
    os.symlink(target, _settings(tmp_path))
    result = _cli(tmp_path, "--yes")
    assert result.returncode == 2 and "symlink" in result.stderr
    assert target.read_text(encoding="utf-8") == "{}"


def test_write_permission_error_aborts_cleanly(tmp_path, monkeypatch):
    before = _put(tmp_path, {"env": {"FOO": "1"}})

    def deny(*_a, **_k):
        raise PermissionError("denied")

    monkeypatch.setattr(sae.os, "replace", deny)
    with pytest.raises(sae.SetupError, match="cannot write"):
        sae.run(tmp_path, None, True, False, interactive=False)
    assert _settings(tmp_path).read_bytes() == before
    assert not list((tmp_path / ".claude").glob("*.tmp"))


def test_only_the_one_key_differs_after_merge(tmp_path):
    original = {"env": {"A": "1", "B": "2"}, "hooks": {"x": [1]}, "model": "m"}
    _put(tmp_path, original)
    _cli(tmp_path, "--yes")
    merged = json.loads(_settings(tmp_path).read_text(encoding="utf-8"))
    merged["env"].pop(KEY)
    assert merged == original
