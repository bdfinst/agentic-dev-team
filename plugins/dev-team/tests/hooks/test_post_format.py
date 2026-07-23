"""Unit tests for hooks/post_format.py (#601).

Behavioural coverage of the dispatch table (`format_file`) plus the stdin
plumbing in `main()`. Parity against the bash implementation lives in
`tests/hooks/parity/test_post_format_parity.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "hooks"))

import post_format  # noqa: E402


# ---------------------------------------------------------------------------
# _extract_file_path — stdin JSON plumbing
# ---------------------------------------------------------------------------


def test_extract_file_path_returns_path_when_present():
    raw = '{"tool_input":{"file_path":"src/app.py"}}'
    assert post_format._extract_file_path(raw) == "src/app.py"


def test_extract_file_path_none_when_missing():
    assert post_format._extract_file_path('{"tool_input":{}}') is None


def test_extract_file_path_none_when_empty_stdin():
    assert post_format._extract_file_path("") is None


def test_extract_file_path_none_on_malformed_json():
    assert post_format._extract_file_path("{not valid") is None


def test_extract_file_path_rejects_non_string():
    raw = '{"tool_input":{"file_path":123}}'
    assert post_format._extract_file_path(raw) is None


# ---------------------------------------------------------------------------
# format_file dispatch — one assertion per extension
# ---------------------------------------------------------------------------


@pytest.fixture
def mocked(monkeypatch):
    """Patch shutil.which + subprocess.run captured in `format_file`.

    Returns (which_map, calls). Set entries in which_map to make the code think
    a formatter is (not) on PATH; calls records every subprocess argv the hook
    would have launched.
    """
    which_map = {}
    calls = []

    def fake_which(cmd):
        return which_map.get(cmd)

    def fake_run(argv, **_kwargs):
        calls.append(argv)

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr(post_format.shutil, "which", fake_which)
    monkeypatch.setattr(post_format.subprocess, "run", fake_run)
    return which_map, calls


@pytest.mark.parametrize(
    "filename",
    ["a.ts", "a.tsx", "a.js", "a.jsx", "a.mjs", "a.cjs"],
)
def test_js_family_runs_prettier_then_eslint(mocked, filename):
    which_map, calls = mocked
    which_map["npx"] = "/usr/bin/npx"
    post_format.format_file(filename)
    assert calls == [
        ["npx", "prettier", "--write", filename],
        ["npx", "eslint", "--fix", filename],
    ]


def test_js_family_noop_when_npx_absent(mocked):
    _, calls = mocked
    post_format.format_file("app.tsx")
    assert calls == []


def test_python_prefers_ruff_over_black(mocked):
    which_map, calls = mocked
    which_map["ruff"] = "/usr/bin/ruff"
    which_map["black"] = "/usr/bin/black"
    post_format.format_file("app.py")
    assert calls == [
        ["ruff", "format", "app.py"],
        ["ruff", "check", "--fix", "app.py"],
    ]


def test_python_falls_back_to_black(mocked):
    which_map, calls = mocked
    which_map["black"] = "/usr/bin/black"
    post_format.format_file("app.py")
    assert calls == [["black", "app.py"]]


def test_go_dispatches_to_gofmt(mocked):
    which_map, calls = mocked
    which_map["gofmt"] = "/usr/bin/gofmt"
    post_format.format_file("main.go")
    assert calls == [["gofmt", "-w", "main.go"]]


def test_rust_dispatches_to_rustfmt(mocked):
    which_map, calls = mocked
    which_map["rustfmt"] = "/usr/bin/rustfmt"
    post_format.format_file("lib.rs")
    assert calls == [["rustfmt", "lib.rs"]]


def test_ruby_dispatches_to_rubocop(mocked):
    which_map, calls = mocked
    which_map["bundle"] = "/usr/bin/bundle"
    post_format.format_file("app.rb")
    assert calls == [["bundle", "exec", "rubocop", "-A", "app.rb"]]


def test_java_dispatches_to_google_java_format(mocked):
    which_map, calls = mocked
    which_map["google-java-format"] = "/usr/local/bin/google-java-format"
    post_format.format_file("Main.java")
    assert calls == [["google-java-format", "-i", "Main.java"]]


def test_kotlin_dispatches_to_ktlint(mocked):
    which_map, calls = mocked
    which_map["ktlint"] = "/usr/local/bin/ktlint"
    post_format.format_file("Main.kt")
    assert calls == [["ktlint", "-F", "Main.kt"]]


def test_csharp_dispatches_to_dotnet_format(mocked):
    which_map, calls = mocked
    which_map["dotnet"] = "/usr/local/bin/dotnet"
    post_format.format_file("Program.cs")
    assert calls == [["dotnet", "format", "--include", "Program.cs"]]


def test_unknown_extension_is_noop(mocked):
    _, calls = mocked
    post_format.format_file("readme.md")
    assert calls == []


def test_case_insensitive_extension(mocked):
    which_map, calls = mocked
    which_map["gofmt"] = "/usr/bin/gofmt"
    post_format.format_file("Main.GO")
    assert calls == [["gofmt", "-w", "Main.GO"]]


# ---------------------------------------------------------------------------
# main() end-to-end
# ---------------------------------------------------------------------------


def test_main_returns_zero_on_empty_stdin(monkeypatch):
    monkeypatch.setattr(
        "sys.stdin", type("S", (), {"read": staticmethod(lambda: "")})()
    )
    assert post_format.main() == 0


def test_main_returns_zero_when_file_missing(monkeypatch, tmp_path):
    payload = f'{{"tool_input":{{"file_path":"{tmp_path / "nope.py"}"}}}}'
    monkeypatch.setattr(
        "sys.stdin",
        type("S", (), {"read": staticmethod(lambda: payload)})(),
    )
    assert post_format.main() == 0


def test_main_dispatches_when_file_exists(monkeypatch, tmp_path):
    src = tmp_path / "sample.py"
    src.write_text("x = 1\n")
    dispatched = []
    monkeypatch.setattr(post_format, "format_file", lambda p: dispatched.append(p))
    payload = f'{{"tool_input":{{"file_path":"{src}"}}}}'
    monkeypatch.setattr(
        "sys.stdin",
        type("S", (), {"read": staticmethod(lambda: payload)})(),
    )
    assert post_format.main() == 0
    assert dispatched == [str(src)]
