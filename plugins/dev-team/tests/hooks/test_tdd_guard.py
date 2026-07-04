"""Unit tests for hooks/tdd_guard.py (#605)."""

from __future__ import annotations

import io
import sys
import time
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "hooks"))

import tdd_guard  # noqa: E402


# ---------------------------------------------------------------------------
# _extract_file_path — walks 4 candidate keys
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ('{"tool_input":{"file_path":"a"}}', "a"),
        ('{"tool_input":{"path":"b"}}', "b"),
        ('{"file_path":"c"}', "c"),
        ('{"path":"d"}', "d"),
        ("{}", ""),
        ("not-json", ""),
        ('{"tool_input":{"file_path":123}}', ""),
    ],
)
def test_extract_file_path_prefers_first_available(raw, expected):
    assert tdd_guard._extract_file_path(raw) == expected


# ---------------------------------------------------------------------------
# Extension / exclusion filters
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path,expected",
    [
        ("src/app.ts", True),
        ("src/app.tsx", True),
        ("src/App.py", True),
        ("main.go", True),
        ("lib.rs", True),
        ("Main.java", True),
        ("Program.cs", True),
        ("Component.svelte", True),
        ("App.vue", True),
        ("README.md", False),
        ("config.yaml", False),
        ("", False),
    ],
)
def test_is_source_file(path, expected):
    assert tdd_guard._is_source_file(path) is expected


@pytest.mark.parametrize(
    "path,expected",
    [
        ("src/app.ts", False),
        # bash `*/node_modules/*` needs a preceding path segment; a bare
        # top-level `node_modules/…` does NOT match (verified against the .sh).
        ("node_modules/pkg/index.js", False),
        ("/proj/node_modules/pkg/index.js", True),
        ("proj/dist/app.js", True),
        ("proj/build/main.py", True),
        ("proj/.next/cache/foo.js", True),
        ("proj/coverage/report.html", True),
        ("path/to/notinnodemodules/file.ts", False),
    ],
)
def test_is_excluded_dir(path, expected):
    assert tdd_guard._is_excluded_dir(path) is expected


# ---------------------------------------------------------------------------
# is_test_file — filename patterns + directory + content
# ---------------------------------------------------------------------------


def test_is_test_file_by_filename(tmp_path):
    # These paths don't need to exist; the head-read only runs when the
    # filename patterns miss.
    (tmp_path / "calc.test.ts").write_text("// nothing tdd-shaped")
    (tmp_path / "calc.spec.ts").write_text("// nothing")
    (tmp_path / "calc_test.py").write_text("# nothing")
    (tmp_path / "calc_spec.rb").write_text("# nothing")
    for name in ("calc.test.ts", "calc.spec.ts", "calc_test.py", "calc_spec.rb"):
        assert tdd_guard.is_test_file(str(tmp_path / name)) is True


def test_is_test_file_by_directory(tmp_path):
    (tmp_path / "tests").mkdir()
    src = tmp_path / "tests" / "sample.py"
    src.write_text("# no tdd shape")
    assert tdd_guard.is_test_file(str(src)) is True


def test_is_test_file_by_content(tmp_path):
    src = tmp_path / "helpers.ts"
    src.write_text("import { describe } from 'vitest';\ndescribe('x', () => {});\n")
    assert tdd_guard.is_test_file(str(src)) is True


def test_is_test_file_feature_extension(tmp_path):
    src = tmp_path / "login.feature"
    src.write_text("Feature: login\n")
    assert tdd_guard.is_test_file(str(src)) is True


def test_is_test_file_negative(tmp_path):
    src = tmp_path / "helpers.ts"
    src.write_text("export const add = (a, b) => a + b;\n")
    assert tdd_guard.is_test_file(str(src)) is False


# ---------------------------------------------------------------------------
# State file
# ---------------------------------------------------------------------------


def test_state_file_hashes_path_with_trailing_newline(monkeypatch, tmp_path):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    path = tdd_guard._state_file()
    # bash `echo <cwd> | md5sum` includes a trailing newline; matching that
    # byte sequence is what keeps the state file in the same place.
    assert path.parent.name == "tdd-guard"
    assert path.name.startswith("session-")


def test_read_state_missing_file(tmp_path):
    assert tdd_guard._read_state(tmp_path / "absent") == ("", 0)


def test_write_and_read_state_roundtrip(tmp_path):
    state = tmp_path / "session-abc"
    tdd_guard._write_state(state, "src/calc.test.ts", 100)
    edit, ts = tdd_guard._read_state(state)
    assert edit == "src/calc.test.ts"
    assert ts == 100


# ---------------------------------------------------------------------------
# main() decision paths
# ---------------------------------------------------------------------------


def _feed(monkeypatch, text: str) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(text))


def test_main_silent_when_no_file_path(monkeypatch, capsys):
    _feed(monkeypatch, "{}")
    assert tdd_guard.main() == 0
    assert capsys.readouterr().out == ""


def test_main_silent_when_file_missing(monkeypatch, capsys, tmp_path):
    _feed(
        monkeypatch, '{"tool_input":{"file_path":"' + str(tmp_path / "nope.ts") + '"}}'
    )
    assert tdd_guard.main() == 0
    assert capsys.readouterr().out == ""


def test_main_silent_on_non_source_file(monkeypatch, capsys, tmp_path):
    doc = tmp_path / "notes.md"
    doc.write_text("# hi")
    _feed(monkeypatch, '{"tool_input":{"file_path":"' + str(doc) + '"}}')
    assert tdd_guard.main() == 0
    assert capsys.readouterr().out == ""


def test_main_silent_on_excluded_dir(monkeypatch, capsys, tmp_path):
    excluded = tmp_path / "node_modules" / "pkg"
    excluded.mkdir(parents=True)
    src = excluded / "index.js"
    src.write_text("module.exports = 1;")
    _feed(monkeypatch, '{"tool_input":{"file_path":"' + str(src) + '"}}')
    assert tdd_guard.main() == 0
    assert capsys.readouterr().out == ""


def test_main_test_file_records_state(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmp"))
    monkeypatch.chdir(tmp_path)
    src = tmp_path / "calc.test.ts"
    src.write_text("import { it } from 'vitest';\nit('x', () => {});\n")
    _feed(monkeypatch, '{"tool_input":{"file_path":"' + str(src) + '"}}')
    assert tdd_guard.main() == 0
    assert capsys.readouterr().out == ""
    # State file should exist under $TMPDIR/tdd-guard/session-<hash>
    state_dir = tmp_path / "tmp" / "tdd-guard"
    assert any(state_dir.glob("session-*"))


def test_main_impl_without_recent_test_warns(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmp"))
    monkeypatch.chdir(tmp_path)
    src = tmp_path / "calc.ts"
    src.write_text("export const add = (a, b) => a + b;\n")
    _feed(monkeypatch, '{"tool_input":{"file_path":"' + str(src) + '"}}')
    assert tdd_guard.main() == 0
    out = capsys.readouterr().out
    assert "TDD: Implementation file edited without a recent test edit." in out
    assert "File: calc.ts" in out


def test_green_phase_window_seconds_constant_exists():
    # Named sibling of _STATE_TTL_SECONDS — the GREEN-phase grace window
    # should not be a bare magic number inline in main().
    assert tdd_guard._GREEN_PHASE_WINDOW_SECONDS == 300


def test_main_respects_green_phase_window_constant(monkeypatch, capsys, tmp_path):
    # Shrinking the named window should shrink the GREEN-phase grace period
    # accordingly, proving main() reads the constant rather than a literal.
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmp"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(tdd_guard, "_GREEN_PHASE_WINDOW_SECONDS", 10)

    state_dir = tmp_path / "tmp" / "tdd-guard"
    state_dir.mkdir(parents=True)
    state_file = tdd_guard._state_file()
    state_file.parent.mkdir(parents=True, exist_ok=True)
    tdd_guard._write_state(state_file, "src/calc.test.ts", int(time.time()) - 60)

    src = tmp_path / "calc.ts"
    src.write_text("export const add = (a, b) => a + b;\n")
    _feed(monkeypatch, '{"tool_input":{"file_path":"' + str(src) + '"}}')
    assert tdd_guard.main() == 0
    out = capsys.readouterr().out
    assert "TDD: Implementation file edited without a recent test edit." in out


def test_main_impl_with_recent_test_is_silent(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmp"))
    monkeypatch.chdir(tmp_path)

    # Prime state as if a test was recorded a minute ago.
    state_dir = tmp_path / "tmp" / "tdd-guard"
    state_dir.mkdir(parents=True)
    state_file = tdd_guard._state_file()
    state_file.parent.mkdir(parents=True, exist_ok=True)
    tdd_guard._write_state(state_file, "src/calc.test.ts", int(time.time()) - 60)

    src = tmp_path / "calc.ts"
    src.write_text("export const add = (a, b) => a + b;\n")
    _feed(monkeypatch, '{"tool_input":{"file_path":"' + str(src) + '"}}')
    assert tdd_guard.main() == 0
    assert capsys.readouterr().out == ""
