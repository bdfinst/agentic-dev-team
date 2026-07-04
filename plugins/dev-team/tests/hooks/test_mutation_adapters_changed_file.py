"""Unit tests for the shared `lib.first_changed_file` helper and its three
adapter callers (pitest, stryker_net, mutmut) — dedup of the "find first
changed non-test source file via git diff" logic that used to be copy-pasted
three times with only the extension set and test-name predicate varying.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parents[4] / "plugins" / "dev-team" / "hooks")
)

from mutation_adapters import lib, mutmut, pitest, stryker_net  # noqa: E402


# ---------------------------------------------------------------------------
# lib.first_changed_file — the shared helper
# ---------------------------------------------------------------------------


def test_first_changed_file_returns_first_predicate_match(monkeypatch):
    def fake_run(cmd, capture_output, text, check):  # noqa: ARG001
        return subprocess.CompletedProcess(
            cmd, 0, stdout="FooTest.java\nFoo.java\n", stderr=""
        )

    monkeypatch.setattr(lib.subprocess, "run", fake_run)
    result = lib.first_changed_file(lambda line: line == "Foo.java")
    assert result == "Foo.java"


def test_first_changed_file_falls_back_to_cached_diff(monkeypatch):
    calls = []

    def fake_run(cmd, capture_output, text, check):  # noqa: ARG001
        calls.append(cmd)
        if "--cached" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="Bar.py\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(lib.subprocess, "run", fake_run)
    result = lib.first_changed_file(lambda line: line.endswith(".py"))
    assert result == "Bar.py"
    assert len(calls) == 2


def test_first_changed_file_returns_empty_when_no_match(monkeypatch):
    def fake_run(cmd, capture_output, text, check):  # noqa: ARG001
        return subprocess.CompletedProcess(cmd, 0, stdout="README.md\n", stderr="")

    monkeypatch.setattr(lib.subprocess, "run", fake_run)
    assert lib.first_changed_file(lambda line: line.endswith(".py")) == ""


def test_first_changed_file_returns_empty_when_git_missing(monkeypatch):
    def fake_run(cmd, capture_output, text, check):  # noqa: ARG001
        raise FileNotFoundError()

    monkeypatch.setattr(lib.subprocess, "run", fake_run)
    assert lib.first_changed_file(lambda line: True) == ""


# ---------------------------------------------------------------------------
# pitest — extension set .java/.kt/.groovy/.scala, excludes Test/Spec
# ---------------------------------------------------------------------------


def test_pitest_changed_source_file_delegates_to_shared_helper(monkeypatch):
    captured = {}

    def fake_first_changed_file(predicate):
        captured["predicate"] = predicate
        return "src/main/java/com/example/Calculator.java"

    monkeypatch.setattr(pitest.lib, "first_changed_file", fake_first_changed_file)
    result = pitest._changed_source_file()

    assert result == "src/main/java/com/example/Calculator.java"
    predicate = captured["predicate"]
    assert predicate("src/main/java/com/example/Calculator.java") is True
    assert predicate("src/main/java/com/example/CalculatorTest.java") is False
    assert predicate("src/main/java/com/example/CalculatorSpec.kt") is False
    assert predicate("README.md") is False


# ---------------------------------------------------------------------------
# stryker_net — extension .cs, excludes Test/Spec
# ---------------------------------------------------------------------------


def test_stryker_net_changed_cs_file_delegates_to_shared_helper(monkeypatch):
    captured = {}

    def fake_first_changed_file(predicate):
        captured["predicate"] = predicate
        return "src/Foo.Bar/Calculator.cs"

    monkeypatch.setattr(stryker_net.lib, "first_changed_file", fake_first_changed_file)
    result = stryker_net._changed_cs_file()

    assert result == "src/Foo.Bar/Calculator.cs"
    predicate = captured["predicate"]
    assert predicate("src/Foo.Bar/Calculator.cs") is True
    assert predicate("src/Foo.Bar/CalculatorTest.cs") is False
    assert predicate("src/Foo.Bar/CalculatorSpec.cs") is False
    assert predicate("README.md") is False


# ---------------------------------------------------------------------------
# mutmut — extension .py, excludes test_*.py / *_test.py / dir "test_"
# ---------------------------------------------------------------------------


def test_mutmut_changed_python_source_delegates_to_shared_helper(monkeypatch):
    captured = {}

    def fake_first_changed_file(predicate):
        captured["predicate"] = predicate
        return "src/calculator.py"

    monkeypatch.setattr(mutmut.lib, "first_changed_file", fake_first_changed_file)
    result = mutmut._changed_python_source()

    assert result == "src/calculator.py"
    predicate = captured["predicate"]
    assert predicate("src/calculator.py") is True
    assert predicate("test_calculator.py") is False
    assert predicate("calculator_test.py") is False
    assert predicate("tests/test_calculator.py") is False
    assert predicate("README.md") is False
