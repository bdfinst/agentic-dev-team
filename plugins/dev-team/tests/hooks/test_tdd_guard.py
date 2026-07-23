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


@pytest.fixture(autouse=True)
def _no_boundary_events(monkeypatch):
    """main() defaults cwd="." when the test payload omits it — without
    this, emit_boundary_event (#859) would resolve metrics/ against the
    test process's real OS cwd. Boundary-event emission itself is covered
    end-to-end in tests/hooks/test_boundary_events.py.
    """
    monkeypatch.setattr(tdd_guard, "emit_boundary_event", lambda *a, **k: None)


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


# ---------------------------------------------------------------------------
# _is_source_file — the .js / .jsx suffixes the parametrize above omits
# ---------------------------------------------------------------------------


def test_is_source_file_js_and_jsx():
    # The main parametrize covers .ts/.tsx but not the plain-JS suffixes;
    # a mutation dropping ".js"/".jsx" from the set would otherwise survive.
    assert tdd_guard._is_source_file("app.js") is True
    assert tdd_guard._is_source_file("app.jsx") is True


# ---------------------------------------------------------------------------
# _extract_file_path — non-dict JSON payloads
# ---------------------------------------------------------------------------


def test_extract_file_path_non_dict_payload_returns_empty():
    # A JSON array or scalar parses cleanly but isn't a dict — the
    # `if not isinstance(payload, dict)` guard must return exactly "".
    assert tdd_guard._extract_file_path("[1, 2, 3]") == ""
    assert tdd_guard._extract_file_path("42") == ""


# ---------------------------------------------------------------------------
# is_test_file — each directory fragment, and the L58 content patterns
# ---------------------------------------------------------------------------


def test_is_test_file_each_directory_fragment():
    # The directory check short-circuits before any file read, so the paths
    # need not exist. Each fragment string must independently trigger a match.
    assert tdd_guard.is_test_file("/proj/test/sample.py") is True
    assert tdd_guard.is_test_file("/proj/tests/sample.py") is True
    assert tdd_guard.is_test_file("/proj/__tests__/sample.py") is True
    assert tdd_guard.is_test_file("/proj/spec/sample.py") is True


def test_is_test_file_content_language_markers(tmp_path):
    # Filenames chosen so neither the suffix regex nor the dir fragments
    # match — detection must come from the L57/L58 content patterns.
    rust_test = tmp_path / "lib.rs"
    rust_test.write_text("#[test]\nfn t() {}\n")
    assert tdd_guard.is_test_file(str(rust_test)) is True

    rust_cfg = tmp_path / "lib2.rs"
    rust_cfg.write_text("#[cfg(test)]\nmod t {}\n")
    assert tdd_guard.is_test_file(str(rust_cfg)) is True

    xunit_fact = tmp_path / "Widget.cs"
    xunit_fact.write_text("[Fact]\npublic void T() {}\n")
    assert tdd_guard.is_test_file(str(xunit_fact)) is True

    xunit_theory = tmp_path / "Widget2.cs"
    xunit_theory.write_text("[Theory]\npublic void T() {}\n")
    assert tdd_guard.is_test_file(str(xunit_theory)) is True


def test_is_test_file_directory_path_returns_false(tmp_path):
    # A directory whose name matches no test pattern reaches the open() and
    # raises OSError (IsADirectoryError); the except branch must return False.
    plain_dir = tmp_path / "plainpkg"
    plain_dir.mkdir()
    assert tdd_guard.is_test_file(str(plain_dir)) is False


def test_is_test_file_content_beyond_30_lines_is_missed(tmp_path):
    # The head-read scans exactly 30 lines; a marker on line 31 is not seen.
    src = tmp_path / "big.ts"
    src.write_text("// pad\n" * 30 + "describe('x', () => {});\n")
    assert tdd_guard.is_test_file(str(src)) is False


# ---------------------------------------------------------------------------
# _STATE_TTL_SECONDS constant + _state_dir / _state_file
# ---------------------------------------------------------------------------


def test_state_ttl_seconds_is_four_hours():
    assert tdd_guard._STATE_TTL_SECONDS == 14400


def test_state_dir_defaults_to_tmp_when_no_tmpdir(monkeypatch):
    monkeypatch.delenv("TMPDIR", raising=False)
    assert tdd_guard._state_dir() == Path("/tmp") / "tdd-guard"


def test_state_dir_honors_tmpdir_env(monkeypatch):
    monkeypatch.setenv("TMPDIR", "/custom-tmp")
    assert tdd_guard._state_dir() == Path("/custom-tmp") / "tdd-guard"


def test_state_file_uses_cwd_arg_and_exact_digest():
    # str(Path("/known-cwd")) + "\n" hashed with md5, first 12 hex chars.
    # Pins the "\n" append, the [:12] slice, and the cwd-arg branch.
    path = tdd_guard._state_file(cwd=Path("/known-cwd"))
    assert path.name == "session-224ad4c75229"
    assert path.parent.name == "tdd-guard"


# ---------------------------------------------------------------------------
# _purge_stale
# ---------------------------------------------------------------------------


def test_purge_stale_removes_expired_sessions(monkeypatch, tmp_path):
    # A negative TTL makes every session file "expired" (now - mtime > -1).
    monkeypatch.setattr(tdd_guard, "_STATE_TTL_SECONDS", -1)
    state_dir = tmp_path / "tdd-guard"
    state_dir.mkdir()
    victim = state_dir / "session-abc"
    victim.write_text("x\n1\n")
    tdd_guard._purge_stale(state_dir)
    assert not victim.exists()


def test_purge_stale_keeps_fresh_sessions(monkeypatch, tmp_path):
    monkeypatch.setattr(tdd_guard, "_STATE_TTL_SECONDS", 10**9)
    state_dir = tmp_path / "tdd-guard"
    state_dir.mkdir()
    keeper = state_dir / "session-fresh"
    keeper.write_text("x\n1\n")
    tdd_guard._purge_stale(state_dir)
    assert keeper.exists()


def test_purge_stale_ignores_non_session_files(monkeypatch, tmp_path):
    # Even with an aggressive TTL, only `session-*` files are candidates.
    monkeypatch.setattr(tdd_guard, "_STATE_TTL_SECONDS", -1)
    state_dir = tmp_path / "tdd-guard"
    state_dir.mkdir()
    other = state_dir / "notes.txt"
    other.write_text("keep me")
    tdd_guard._purge_stale(state_dir)
    assert other.exists()


def test_purge_stale_missing_dir_is_noop(tmp_path):
    # Must not raise when the directory does not exist.
    assert tdd_guard._purge_stale(tmp_path / "absent") is None


# ---------------------------------------------------------------------------
# _read_state — empty file, multi-line, and non-integer timestamp
# ---------------------------------------------------------------------------


def test_read_state_empty_file(tmp_path):
    state = tmp_path / "session-empty"
    state.write_text("")
    assert tdd_guard._read_state(state) == ("", 0)


def test_read_state_uses_first_and_last_line(tmp_path):
    # Three lines prove last_edit == lines[0] and last_time == int(lines[-1]),
    # not lines[1] — the middle line is neither the path nor the timestamp.
    state = tmp_path / "session-three"
    state.write_text("real/file.ts\nMIDDLE\n42\n")
    edit, ts = tdd_guard._read_state(state)
    assert edit == "real/file.ts"
    assert ts == 42


def test_read_state_non_integer_timestamp_defaults_zero(tmp_path):
    state = tmp_path / "session-badtime"
    state.write_text("real/file.ts\nnot-a-number\n")
    edit, ts = tdd_guard._read_state(state)
    assert edit == "real/file.ts"
    assert ts == 0


# ---------------------------------------------------------------------------
# _write_state — creates missing parent directories
# ---------------------------------------------------------------------------


def test_write_state_creates_missing_parents(tmp_path):
    state = tmp_path / "deep" / "nested" / "session-z"
    tdd_guard._write_state(state, "src/calc.test.ts", 7)
    assert tdd_guard._read_state(state) == ("src/calc.test.ts", 7)


# ---------------------------------------------------------------------------
# main() warn path — exact output, basename, empty-edit, boundary-event args
# ---------------------------------------------------------------------------


def test_main_warn_emits_exact_output_block(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmp"))
    monkeypatch.chdir(tmp_path)
    # Nested dir proves the message uses os.path.basename, not the full path.
    sub = tmp_path / "sub"
    sub.mkdir()
    src = sub / "calc.ts"
    src.write_text("export const add = (a, b) => a + b;\n")
    _feed(monkeypatch, '{"tool_input":{"file_path":"' + str(src) + '"}}')
    assert tdd_guard.main() == 0
    assert capsys.readouterr().out == (
        "\n"
        "  TDD: Implementation file edited without a recent test edit.\n"
        "  File: calc.ts\n"
        "  Write a failing test FIRST, then implement. RED before GREEN.\n"
        "  If this is a refactor with passing tests, run the test suite to confirm.\n"
    )


def test_main_warns_when_last_edit_is_empty(monkeypatch, capsys, tmp_path):
    # A recent timestamp but an empty last_edit must still warn — the
    # `elapsed < window and last_edit` guard requires BOTH to be silent.
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmp"))
    monkeypatch.chdir(tmp_path)
    state_dir = tmp_path / "tmp" / "tdd-guard"
    state_dir.mkdir(parents=True)
    state_file = tdd_guard._state_file()
    state_file.parent.mkdir(parents=True, exist_ok=True)
    tdd_guard._write_state(state_file, "", int(time.time()))

    src = tmp_path / "calc.ts"
    src.write_text("export const add = (a, b) => a + b;\n")
    _feed(monkeypatch, '{"tool_input":{"file_path":"' + str(src) + '"}}')
    assert tdd_guard.main() == 0
    out = capsys.readouterr().out
    assert "TDD: Implementation file edited without a recent test edit." in out


def test_main_passes_cwd_and_session_to_boundary_event(monkeypatch, tmp_path):
    # cwd and session_id only ever flow into emit_boundary_event; capture the
    # call to pin those two extractions and the six literal event arguments.
    calls = []
    monkeypatch.setattr(
        tdd_guard, "emit_boundary_event", lambda *a, **k: calls.append(a)
    )
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmp"))
    monkeypatch.chdir(tmp_path)
    src = tmp_path / "calc.ts"
    src.write_text("export const add = (a, b) => a + b;\n")
    payload = (
        '{"tool_input":{"file_path":"'
        + str(src)
        + '"},"cwd":"/myproj","session_id":"sess-1"}'
    )
    _feed(monkeypatch, payload)
    assert tdd_guard.main() == 0
    assert calls == [
        ("/myproj", "tdd_guard", "Write", "warn", "tdd-red-before-green", "sess-1")
    ]
