"""Edge cases for set_autocompact_env.py (#2177, PR #2232 test review)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

_SCRIPT = REPO_ROOT / "plugins" / "dev-team" / "scripts" / "set_autocompact_env.py"
sys.path.insert(0, str(_SCRIPT.parent))

import set_autocompact_env as sae

KEY = "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE"


def _settings(project: Path) -> Path:
    return project / ".claude" / "settings.json"


def _put(project: Path, content) -> bytes:
    path = _settings(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content if isinstance(content, bytes) else json.dumps(content).encode())
    return path.read_bytes()


def _run(project: Path, *args, **kwargs):
    kwargs.setdefault("environ", {})
    return sae.run(project, *args, **kwargs)


def _cli(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), "--project-dir", str(project), *args],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        check=False,
    )


def _value(project: Path):
    return json.loads(_settings(project).read_text(encoding="utf-8"))["env"][KEY]


@pytest.mark.parametrize("pct,warns", [("83", False), ("84", True), ("100", True), ("1", False)])
def test_harness_default_boundary_warning(tmp_path, pct, warns):
    lines = _run(tmp_path, pct, True, False, interactive=False)
    assert any("exceeds the harness default" in line for line in lines) is warns
    assert _value(tmp_path) == pct


def test_existing_invalid_with_valid_flag_is_replaced(tmp_path):
    _put(tmp_path, {"env": {KEY: "abc"}})
    lines = _run(tmp_path, "55", True, False, interactive=False)
    assert "replaced invalid value 'abc' with 55" in lines
    assert _value(tmp_path) == "55"


@pytest.mark.parametrize(
    "existing,shown", [(60, "60"), (None, "None"), ("", ""), (["60"], "['60']")]
)
def test_existing_non_string_values_are_replaced(tmp_path, existing, shown):
    _put(tmp_path, {"env": {KEY: existing}})
    lines = _run(tmp_path, None, True, False, interactive=False)
    assert f"replaced invalid value '{shown}' with 40" in lines
    assert _value(tmp_path) == "40"


def test_existing_equal_to_flag_reports_already_set_and_changes_nothing(tmp_path):
    before = _put(tmp_path, {"env": {KEY: "55"}})
    lines = _run(tmp_path, "55", True, False, interactive=False)
    assert lines == [f"{KEY}=55 already set in {_settings(tmp_path)}"]
    assert _settings(tmp_path).read_bytes() == before


@pytest.mark.parametrize("answer,final", [("1", "1"), ("100", "100"), (" 55 ", "55"), ("", "40")])
def test_prompt_accepts_valid_answers(tmp_path, answer, final):
    _run(tmp_path, None, False, False, interactive=True, input_fn=lambda _p: answer)
    assert _value(tmp_path) == final


@pytest.mark.parametrize("answer", ["0", "101", "-5", "abc", "4 0"])
def test_prompt_rejects_invalid_answers_and_keeps_bytes(tmp_path, answer):
    before = _put(tmp_path, {"env": {"FOO": "1"}})
    with pytest.raises(sae.SetupError, match="expected integer 1-100"):
        _run(tmp_path, None, False, False, interactive=True, input_fn=lambda _p: answer)
    assert _settings(tmp_path).read_bytes() == before


def test_no_autocompact_on_fresh_repo_creates_no_settings_file(tmp_path):
    lines = _run(tmp_path, None, False, True, interactive=False)
    assert lines and not _settings(tmp_path).exists()
    assert (tmp_path / ".claude" / "memory" / "autocompact-nudge-off").exists()


def test_no_autocompact_ignores_an_invalid_pct_flag(tmp_path):
    result = _cli(tmp_path, "--no-autocompact", "--autocompact-pct", "abc")
    assert result.returncode == 0, result.stderr
    assert not _settings(tmp_path).exists()


def test_eof_on_prompt_exits_2(tmp_path, monkeypatch, capsys):
    class _Tty:
        def isatty(self):
            return True

        def readline(self):
            return ""  # EOF: input() raises EOFError

    monkeypatch.setattr(sys, "stdin", _Tty())
    assert sae.main(["--project-dir", str(tmp_path)]) == 2
    assert "pass --yes or --autocompact-pct" in capsys.readouterr().err
    assert not _settings(tmp_path).exists()


def test_empty_settings_file_is_treated_as_an_empty_object(tmp_path):
    _put(tmp_path, b"")
    _run(tmp_path, None, True, False, interactive=False)
    assert json.loads(_settings(tmp_path).read_text(encoding="utf-8")) == {"env": {KEY: "40"}}


@pytest.mark.parametrize(
    "content,needle",
    [
        (b"null", "top level is not an object"),
        (b'{"env": null}', '"env" is not an object'),
        (b"\xff\xfe{}", "malformed settings.json"),
    ],
)
def test_hostile_settings_abort_with_bytes_unchanged(tmp_path, content, needle):
    before = _put(tmp_path, content)
    with pytest.raises(sae.SetupError, match=needle):
        _run(tmp_path, None, True, False, interactive=False)
    assert _settings(tmp_path).read_bytes() == before


def test_settings_path_that_is_a_directory_aborts(tmp_path):
    _settings(tmp_path).mkdir(parents=True)
    with pytest.raises(sae.SetupError, match="cannot read"):
        _run(tmp_path, None, True, False, interactive=False)
    assert _settings(tmp_path).is_dir()
