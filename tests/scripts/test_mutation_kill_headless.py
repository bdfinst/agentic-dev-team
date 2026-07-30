"""Pytest tests for mutation_kill_headless.py — headless generation and the
``--headless`` CLI entry point, split out of mutation_kill_loop.py (#1562).

Monkeypatches target this module directly (not ``mutation_kill_loop``) so
patches actually take effect: ``main()``, ``claude_cli_available()``, and
``run_for_file`` (imported from ``mutation_kill_loop``) are all looked up in
*this* module's globals when called from here.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = (
    Path(__file__).resolve().parents[2]
    / "plugins"
    / "dev-team"
    / "skills"
    / "mutation-testing"
    / "scripts"
)
sys.path.insert(0, str(SCRIPTS_DIR))

import mutation_kill_headless as headless

FORBIDDEN_LITERALS = ["Aci.Speedpay", "Controllers", "AwesomeAssertions", "Moq", "AutoFixture"]


def _mutant(status: str, mutator: str = "ArithmeticOperator", line: int = 1) -> dict:
    return {
        "id": f"{mutator}-{status}-{line}",
        "mutatorName": mutator,
        "status": status,
        "location": {"start": {"line": line}},
        "replacement": "<replacement>",
    }


# =============================================================================
# Scenario: Bare-CLI default mode with no generator fails fast at startup
# =============================================================================
def test_bare_cli_no_generator_fails_fast_at_startup(
    monkeypatch: pytest.MonkeyPatch, capsys
):
    # Guard: neither a scoped Stryker run nor any subprocess may fire.
    def explode(*a, **k):
        raise AssertionError("startup preflight must run before any subprocess")

    monkeypatch.setattr(headless, "run_for_file", explode)
    monkeypatch.setattr(headless.subprocess, "run", explode)

    rc = headless.main(["--config", "stryker-config.json", "--file", "PaymentService.cs"])

    assert rc != 0
    err = capsys.readouterr().err
    assert (
        "no test generator available — invoke via the mutation-kill agent "
        "or pass --headless"
    ) in err


def test_headless_flag_does_not_trip_the_no_generator_preflight(
    monkeypatch: pytest.MonkeyPatch, capsys
):
    # --headless is accepted (Slice 3 wires it); it must NOT emit the
    # no-generator message. With the CLI present, the next gate is the
    # required-file-args check — assert that exact message is emitted, which
    # positively proves the no-generator preflight was passed (not merely that
    # the no-generator text is absent). Pin claude_cli_available so the emitted
    # message is deterministic regardless of the host's PATH.
    monkeypatch.setattr(headless, "claude_cli_available", lambda: True)

    rc = headless.main(["--headless"])

    err = capsys.readouterr().err
    assert headless.NO_GENERATOR_MESSAGE not in err
    assert "--headless requires --file, --test-file, and --source-path" in err
    assert rc != 0


# =============================================================================
# Slice 3 — Optional --headless generation mode
# =============================================================================
# Scenario: Headless mode generates via the Claude CLI
def test_headless_generator_invokes_claude_print_and_strips_fences(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict = {}

    class _R:
        returncode = 0
        stdout = "```csharp\n[Test]\npublic void New_Case_KillsMutant() {}\n```"
        stderr = ""

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return _R()

    monkeypatch.setattr(headless.subprocess, "run", fake_run)

    generate = headless.make_headless_generator("some-test-model")
    survivors = [_mutant("Survived", "ArithmeticOperator", 10)]
    out = generate(
        "PaymentService.cs",
        survivors,
        "public class PaymentService {}",
        "public class PaymentServiceTests { }",
    )

    argv = captured["argv"]
    assert argv[0] == headless.CLAUDE_CLI
    assert "--print" in argv
    # --model carries the resolved model.
    assert argv[argv.index("--model") + 1] == "some-test-model"
    prompt = argv[-1]
    # The existing test file is the pattern, and the survivor summary is present.
    assert "PaymentServiceTests" in prompt
    assert "ArithmeticOperator" in prompt
    # No hardcoded library name leaks into the prompt.
    assert not any(lit in prompt for lit in FORBIDDEN_LITERALS)
    # Fences stripped from the returned methods.
    assert "```" not in out
    assert "New_Case_KillsMutant" in out


# Scenario: --model resolves from the flag, then the env var, else None
def test_model_resolves_from_env_when_set(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DEV_TEAM_MUTATION_MODEL", "env-model")
    assert headless.resolve_model() == "env-model"
    # An explicit --model wins over the env var.
    assert headless.resolve_model("flag-model") == "flag-model"


def test_model_resolves_to_none_when_env_unset(
    monkeypatch: pytest.MonkeyPatch,
):
    # No model snapshot id is pinned in source (cf. ADR 0008 / no-pinned-snapshots
    # guard); unresolved means None so `claude --print` uses its own default.
    monkeypatch.delenv("DEV_TEAM_MUTATION_MODEL", raising=False)
    assert headless.resolve_model() is None


def test_headless_omits_model_flag_when_unresolved(monkeypatch: pytest.MonkeyPatch):
    captured = {}

    class _R:
        returncode = 0
        stdout = "void New_Case() {}"
        stderr = ""

    def fake_run(argv, **k):
        captured["argv"] = argv
        return _R()

    monkeypatch.setattr(headless.subprocess, "run", fake_run)
    generate = headless.make_headless_generator(None)
    generate("S.cs", [_mutant("Survived", "ArithmeticOperator", 10)], "class S {}", "class T {}")
    # --model is absent entirely; claude --print falls back to its own default.
    assert "--model" not in captured["argv"]
    assert "--print" in captured["argv"]


# Scenario: Default (non-headless) mode spawns no Claude subprocess
def test_default_non_headless_spawns_no_claude_subprocess(
    monkeypatch: pytest.MonkeyPatch, capsys
):
    def explode(*a, **k):
        raise AssertionError("no subprocess may be spawned in the default mode")

    monkeypatch.setattr(headless.subprocess, "run", explode)
    monkeypatch.setattr(
        headless, "claude_cli_available", lambda: pytest.fail("must not probe the CLI")
    )

    rc = headless.main(["--config", "stryker-config.json", "--file", "Foo.cs"])

    assert rc != 0
    assert headless.NO_GENERATOR_MESSAGE in capsys.readouterr().err


# Scenario: Missing Claude CLI under headless fails cleanly and names the fix
def test_missing_claude_cli_under_headless_names_remediation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    monkeypatch.setattr(headless, "claude_cli_available", lambda: False)
    # No file may be mutated: run_for_file must never be reached.
    monkeypatch.setattr(
        headless, "run_for_file", lambda *a, **k: pytest.fail("must not run — CLI missing")
    )

    rc = headless.main(
        [
            "--headless",
            "--file", "Foo.cs",
            "--test-file", str(tmp_path / "FooTests.cs"),
            "--source-path", str(tmp_path / "Foo.cs"),
        ]
    )

    assert rc != 0
    err = capsys.readouterr().err
    # Names how to install AND authenticate the CLI.
    assert "install" in err.lower()
    assert "claude" in err.lower()
    assert "authenticate" in err.lower() or "ANTHROPIC_API_KEY" in err


def test_claude_cli_available_reflects_subprocess_outcome(
    monkeypatch: pytest.MonkeyPatch,
):
    class _OK:
        returncode = 0

    monkeypatch.setattr(headless.subprocess, "run", lambda *a, **k: _OK())
    assert headless.claude_cli_available() is True

    def _missing(*a, **k):
        raise FileNotFoundError("claude")

    monkeypatch.setattr(headless.subprocess, "run", _missing)
    assert headless.claude_cli_available() is False
