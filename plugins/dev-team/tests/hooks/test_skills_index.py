"""Unit tests for hooks/skills_index.py (#604)."""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "hooks"))

import skills_index

# ---------------------------------------------------------------------------
# _extract_fields
# ---------------------------------------------------------------------------


def test_extract_fields_returns_tool_and_file_path():
    tool, path = skills_index._extract_fields(
        '{"tool_name":"Edit","tool_input":{"file_path":"plugins/dev-team/skills/foo/SKILL.md"}}'
    )
    assert tool == "Edit"
    assert path == "plugins/dev-team/skills/foo/SKILL.md"


def test_extract_fields_malformed_returns_none():
    assert skills_index._extract_fields("not json") == (None, None)


def test_extract_fields_missing_keys():
    tool, path = skills_index._extract_fields("{}")
    assert tool == ""
    assert path == ""


# ---------------------------------------------------------------------------
# _touches_skill_definition
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path,expected",
    [
        ("plugins/dev-team/skills/foo/SKILL.md", True),
        ("/abs/plugins/dev-team/skills/foo/SKILL.md", True),
        ("plugins/dev-team/skills/foo/README.md", False),
        ("plugins/dev-team/skills/foo/bar/SKILL.md", False),
        ("plugins/dev-team/agents/foo.md", False),
        ("src/app.py", False),
        ("", False),
        (r"C:\repo\plugins\dev-team\skills\foo\SKILL.md", False),
    ],
)
def test_touches_skill_definition(path, expected):
    assert skills_index._touches_skill_definition(path) is expected


# ---------------------------------------------------------------------------
# main() decision paths
# ---------------------------------------------------------------------------


def _feed(monkeypatch, text: str) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(text))


def test_main_ignores_non_edit_tool(monkeypatch, capsys):
    _feed(
        monkeypatch,
        '{"tool_name":"Read","tool_input":{"file_path":"plugins/dev-team/skills/foo/SKILL.md"}}',
    )
    assert skills_index.main() == 0
    assert capsys.readouterr().err == ""


def test_main_ignores_non_skill_edit(monkeypatch, capsys):
    _feed(monkeypatch, '{"tool_name":"Edit","tool_input":{"file_path":"src/app.py"}}')
    assert skills_index.main() == 0
    assert capsys.readouterr().err == ""


def test_main_silent_on_malformed_stdin(monkeypatch, capsys):
    _feed(monkeypatch, "totally not json")
    assert skills_index.main() == 0
    assert capsys.readouterr().err == ""


def test_main_silent_on_empty_stdin(monkeypatch, capsys):
    _feed(monkeypatch, "")
    assert skills_index.main() == 0
    assert capsys.readouterr().err == ""


def _make_builder(tmp_path: Path, script: str) -> Path:
    path = tmp_path / "builder.sh"
    path.write_text(script)
    return path


def test_main_reports_rebuild_on_success(monkeypatch, tmp_path, capsys):
    builder = _make_builder(tmp_path, "#!/usr/bin/env bash\nexit 0\n")
    monkeypatch.setenv("SKILLS_INDEX_BUILDER", str(builder))
    _feed(
        monkeypatch,
        '{"tool_name":"Edit","tool_input":{"file_path":"plugins/dev-team/skills/foo/SKILL.md"}}',
    )
    assert skills_index.main() == 0
    err = capsys.readouterr().err
    assert err.strip() == "[skills-index] rebuilt"


def test_main_reports_first_stderr_line_on_failure(monkeypatch, tmp_path, capsys):
    builder = _make_builder(
        tmp_path,
        '#!/usr/bin/env bash\necho "first line reason" >&2\necho "later line" >&2\nexit 1\n',
    )
    monkeypatch.setenv("SKILLS_INDEX_BUILDER", str(builder))
    _feed(
        monkeypatch,
        '{"tool_name":"Edit","tool_input":{"file_path":"plugins/dev-team/skills/foo/SKILL.md"}}',
    )
    assert skills_index.main() == 0
    err = capsys.readouterr().err.strip().splitlines()
    assert err == ["[skills-index] rebuild failed: first line reason"]


def test_main_missing_builder_fails_open(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("SKILLS_INDEX_BUILDER", str(tmp_path / "does-not-exist.sh"))
    _feed(
        monkeypatch,
        '{"tool_name":"Edit","tool_input":{"file_path":"plugins/dev-team/skills/foo/SKILL.md"}}',
    )
    assert skills_index.main() == 0
    err = capsys.readouterr().err
    # bash `bash <missing>` produces "No such file or directory" on first stderr line;
    # we surface it via the same reporting path.
    assert err.startswith("[skills-index] rebuild failed:")
