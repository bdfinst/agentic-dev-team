"""Pytest tests for mutation_kill_loop_python.py's headless-generation glue,
``--headless`` CLI dispatch, and the whole-module no-repo-specific-literal
sweep (#1604 split of ``test_mutation_kill_loop_python.py``, mirroring the
C# loop's own #1564 split into ``test_mutation_kill_loop_cli.py``).

The ``claude --print`` invocation glue itself (``resolve_model``,
``strip_code_fences``, ``claude_cli_available``, ``run_claude_headless``)
lives in ``mutation_kill_shared.py`` (#1601) — its full behavioral coverage
lives in ``test_mutation_kill_shared.py`` as the single source of truth.
This file keeps only an identity check plus what's genuinely specific to
this loop: the Python-flavored prompt ``make_headless_generator`` builds,
and the ``--headless`` CLI's own argument parsing/dispatch/preflight
behavior.
"""

from __future__ import annotations

from pathlib import Path

import _mutation_kill_loop_python_test_helpers  # noqa: F401 (sys.path side effect)
import mutation_kill_loop_python as loop
import mutation_kill_shared as shared
import pytest
from _mutation_test_helpers import FORBIDDEN_LITERALS, SCRIPTS_DIR


# =============================================================================
# Reused headless glue actually comes from mutation_kill_shared (#1601) — this
# loop no longer imports mutation_kill_headless (the C#/Stryker.NET CLI
# module) at all, since doing so previously dragged the entire C# stack in
# transitively just to reuse these language-neutral names.
# =============================================================================
def test_headless_helpers_are_reused_not_duplicated():
    assert loop.resolve_model is shared.resolve_model
    assert loop.claude_cli_available is shared.claude_cli_available
    assert loop.CLAUDE_CLI == shared.CLAUDE_CLI
    assert loop.run_claude_headless is shared.run_claude_headless


def test_loop_python_does_not_import_mutation_kill_headless():
    """The actual bug #1601 fixes: this module must not reach for
    mutation_kill_headless (the C#/Stryker.NET CLI module) at all — its own
    module-scope `from mutation_kill_loop import ...` would otherwise pull
    the entire C# stack into a Python-only loop."""
    assert "mutation_kill_headless" not in vars(loop)


# =============================================================================
# Scenario: make_headless_generator delegates to the shared run_claude_headless
# glue — a hung `claude --print` call is bounded by a timeout, not left to
# hang forever (mirrors mutation_kill_shared.py's own coverage of the same
# glue; #1583 fixed this loop's copy previously having NO timeout at all).
# =============================================================================
def test_make_headless_generator_passes_a_timeout(monkeypatch: pytest.MonkeyPatch):
    captured: dict = {}

    def fake_run(argv, **kwargs):
        captured.update(kwargs)

        class _R:
            returncode = 0
            stdout = "def test_new(): pass"
            stderr = ""

        return _R()

    monkeypatch.setattr(shared.subprocess, "run", fake_run)
    generate = loop.make_headless_generator(None)
    generate("a.py", [], "x = 1\n", "def test_existing():\n    pass\n")

    assert captured["timeout"] == shared.CLAUDE_GENERATION_TIMEOUT_S


def test_make_headless_generator_timeout_raises_a_named_error(monkeypatch: pytest.MonkeyPatch):
    def fake_run(argv, **kwargs):
        raise shared.subprocess.TimeoutExpired(argv, kwargs.get("timeout"))

    monkeypatch.setattr(shared.subprocess, "run", fake_run)
    generate = loop.make_headless_generator(None)

    with pytest.raises(RuntimeError) as exc_info:
        generate("a.py", [], "x = 1\n", "def test_existing():\n    pass\n")

    assert str(shared.CLAUDE_GENERATION_TIMEOUT_S) in str(exc_info.value)
    assert "DEV_TEAM_MUTATION_GENERATION_TIMEOUT_S" in str(exc_info.value)


def test_make_headless_generator_strips_fences_and_matches_the_test_file_pattern(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs

        class _R:
            returncode = 0
            stdout = "```python\ndef test_new():\n    assert True\n```"
            stderr = ""

        return _R()

    monkeypatch.setattr(shared.subprocess, "run", fake_run)
    generate = loop.make_headless_generator("some-test-model")

    out = generate(
        "a.py",
        [{"location": {"start": {"line": 3}}}],
        "x = 1\n",
        "def test_existing():\n    pass\n",
    )

    argv = captured["argv"]
    assert argv[argv.index("--model") + 1] == "some-test-model"
    # The prompt is sent over stdin (#1607), not a trailing argv element —
    # assert its absence from argv, not just its presence in kwargs["input"],
    # so a regression back to argv-based passing at this call site is caught.
    prompt = captured["kwargs"]["input"]
    assert prompt not in argv
    assert "test_existing" in prompt
    assert not any(lit in prompt for lit in FORBIDDEN_LITERALS)
    assert "```" not in out
    assert "test_new" in out


# =============================================================================
# No repo-specific literal leaked into the module
# =============================================================================
def test_module_source_carries_no_repo_specific_literal():
    source = (SCRIPTS_DIR / "mutation_kill_loop_python.py").read_text(encoding="utf-8")
    present = [literal for literal in FORBIDDEN_LITERALS if literal in source]
    assert present == [], f"repo-specific literals leaked into module: {present}"


# =============================================================================
# CLI preflight — mirrors mutation_kill_loop.py's fail-fast contract
# =============================================================================
def test_main_without_headless_fails_fast_with_no_generator_message(capsys):
    rc = loop.main([])
    assert rc == 1
    assert loop.NO_GENERATOR_MESSAGE in capsys.readouterr().err


def test_main_headless_without_required_flags_errors(monkeypatch, capsys):
    monkeypatch.setattr(loop, "claude_cli_available", lambda: True)
    rc = loop.main(["--headless"])
    assert rc == 2
    assert "requires --file" in capsys.readouterr().err


def test_main_headless_missing_claude_cli_fails_before_touching_files(monkeypatch, capsys):
    monkeypatch.setattr(loop, "claude_cli_available", lambda: False)
    rc = loop.main(["--headless", "--file", "a.py"])
    assert rc == 3
    assert "Claude CLI" in capsys.readouterr().err


# =============================================================================
# Scenario: A round-abandoning RuntimeError (failed revert, failed commit —
# #1598) propagates to a non-zero exit code instead of a silent 0 return or
# a raw traceback (#1598/#1584 review, item 6).
# =============================================================================
def test_main_exits_non_zero_when_run_for_file_raises(monkeypatch, capsys, tmp_path: Path):
    monkeypatch.setattr(loop, "claude_cli_available", lambda: True)

    def boom(*a, **k):
        raise RuntimeError("revert failed for test_a.py after a failed commit")

    monkeypatch.setattr(loop, "run_for_file", boom)

    rc = loop.main(
        [
            "--headless",
            "--file", "a.py",
            "--test-file", str(tmp_path / "test_a.py"),
            "--source-path", str(tmp_path / "a.py"),
            "--test-command", "pytest",
        ]
    )

    assert rc != 0
    assert rc not in (1, 2, 3)
    assert "revert failed" in capsys.readouterr().err
