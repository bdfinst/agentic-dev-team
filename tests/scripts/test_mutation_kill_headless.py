"""Pytest tests for mutation_kill_headless.py — headless generation and the
``--headless`` CLI entry point, split out of mutation_kill_loop.py (#1562).

Monkeypatches target this module directly (not ``mutation_kill_loop``) so
patches actually take effect: ``main()``, ``claude_cli_available()``, and
``run_for_file`` (imported from ``mutation_kill_loop``) are all looked up in
*this* module's globals when called from here.

The ``claude --print`` invocation glue itself (``resolve_model``,
``strip_code_fences``, ``claude_cli_available``, ``run_claude_headless``) now
lives in ``mutation_kill_shared.py`` (#1601) — its full behavioral coverage
(timeout handling, argv/stdin shape, model-flag presence, fence-stripping,
nonzero-exit handling) lives in ``test_mutation_kill_shared.py`` as the
single source of truth. This file keeps only an identity check plus whatever
coverage is genuinely headless-CLI-specific: the C#-flavored prompt
``make_headless_generator`` builds, and the ``--headless`` CLI's own
argument parsing/dispatch/preflight behavior.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from _mutation_test_helpers import (
    FORBIDDEN_LITERALS,
    SCRIPTS_DIR,
    sequenced_run_claude_headless,
)

sys.path.insert(0, str(SCRIPTS_DIR))

import mutation_kill_headless as headless
import mutation_kill_shared as shared


def _write_config(repo_root: Path) -> Path:
    payload = {
        "stryker-config": {
            "solution": "App.sln",
            "project": "src/Widget.WebApi/Widget.WebApi.csproj",
            "test-projects": ["test/Widget.WebApi.Tests/Widget.WebApi.Tests.csproj"],
            "mutate": ["**/*.cs"],
        }
    }
    path = repo_root / "stryker-config.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _mutant(status: str, mutator: str = "ArithmeticOperator", line: int = 1) -> dict:
    return {
        "id": f"{mutator}-{status}-{line}",
        "mutatorName": mutator,
        "status": status,
        "location": {"start": {"line": line}},
        "replacement": "<replacement>",
    }


# =============================================================================
# Reused headless glue actually comes from mutation_kill_shared (#1601) —
# identity check, mirroring the Python loop's equivalent test.
# =============================================================================
def test_headless_glue_is_reused_not_duplicated():
    assert headless.resolve_model is shared.resolve_model
    assert headless.claude_cli_available is shared.claude_cli_available
    assert headless.CLAUDE_CLI == shared.CLAUDE_CLI
    assert headless.run_claude_headless is shared.run_claude_headless


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
    monkeypatch.setattr(shared.subprocess, "run", explode)

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
# Scenario: make_headless_generator builds the C#-flavored prompt (the
# headless-specific piece) and delegates everything else to the shared
# run_claude_headless (tested directly in test_mutation_kill_shared.py).
# =============================================================================
def test_make_headless_generator_builds_the_csharp_prompt_and_strips_fences(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict = {}

    class _R:
        returncode = 0
        stdout = "```csharp\n[Test]\npublic void New_Case_KillsMutant() {}\n```"
        stderr = ""

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return _R()

    monkeypatch.setattr(shared.subprocess, "run", fake_run)

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
    # The prompt is sent over stdin (#1607), not a trailing argv element —
    # assert its absence from argv, not just its presence in kwargs["input"],
    # so a regression back to argv-based passing at this call site is caught.
    prompt = captured["kwargs"]["input"]
    assert prompt not in argv
    # The existing test file is the pattern, and the survivor summary is present.
    assert "PaymentServiceTests" in prompt
    assert "ArithmeticOperator" in prompt
    # No hardcoded library name leaks into the prompt.
    assert not any(lit in prompt for lit in FORBIDDEN_LITERALS)
    # Fences stripped from the returned methods.
    assert "```" not in out
    assert "New_Case_KillsMutant" in out


# =============================================================================
# Scenario: Default (non-headless) mode spawns no Claude subprocess
# =============================================================================
def test_default_non_headless_spawns_no_claude_subprocess(
    monkeypatch: pytest.MonkeyPatch, capsys
):
    def explode(*a, **k):
        raise AssertionError("no subprocess may be spawned in the default mode")

    monkeypatch.setattr(shared.subprocess, "run", explode)
    monkeypatch.setattr(
        headless, "claude_cli_available", lambda: pytest.fail("must not probe the CLI")
    )

    rc = headless.main(["--config", "stryker-config.json", "--file", "Foo.cs"])

    assert rc != 0
    assert headless.NO_GENERATOR_MESSAGE in capsys.readouterr().err


# =============================================================================
# Scenario: Missing Claude CLI under headless fails cleanly and names the fix
# =============================================================================
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


# =============================================================================
# Scenario: A headless run's resolved model reaches the commit audit trail,
# including the unresolved-model fallback (#1560)
# =============================================================================
def test_headless_main_records_resolved_model_in_generator_label(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(headless, "claude_cli_available", lambda: True)
    captured: dict = {}
    monkeypatch.setattr(headless, "run_for_file", lambda *a, **k: captured.update(a[1].__dict__))
    config_path = _write_config(tmp_path)

    headless.main(
        [
            "--config", str(config_path),
            "--headless",
            "--model", "some-model",
            "--file", "Foo.cs",
            "--test-file", str(tmp_path / "FooTests.cs"),
            "--source-path", str(tmp_path / "Foo.cs"),
        ]
    )

    assert captured["generator_label"] == "headless (some-model)"


def test_headless_main_uses_default_label_when_model_unresolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(headless, "claude_cli_available", lambda: True)
    monkeypatch.delenv("DEV_TEAM_MUTATION_MODEL", raising=False)
    captured: dict = {}
    monkeypatch.setattr(headless, "run_for_file", lambda *a, **k: captured.update(a[1].__dict__))
    config_path = _write_config(tmp_path)

    headless.main(
        [
            "--config", str(config_path),
            "--headless",
            "--file", "Foo.cs",
            "--test-file", str(tmp_path / "FooTests.cs"),
            "--source-path", str(tmp_path / "Foo.cs"),
        ]
    )

    assert captured["generator_label"] == "headless (default)"


# =============================================================================
# Scenario: A round-abandoning RuntimeError (failed revert, failed commit —
# #1598) propagates to a non-zero exit code instead of a silent 0 return or
# a raw traceback (#1598/#1584 review, item 6).
# =============================================================================
def test_main_exits_non_zero_when_run_for_file_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    monkeypatch.setattr(headless, "claude_cli_available", lambda: True)

    def boom(*a, **k):
        raise RuntimeError("revert failed for FooTests.cs after a failed commit")

    monkeypatch.setattr(headless, "run_for_file", boom)
    config_path = _write_config(tmp_path)

    rc = headless.main(
        [
            "--config", str(config_path),
            "--headless",
            "--file", "Foo.cs",
            "--test-file", str(tmp_path / "FooTests.cs"),
            "--source-path", str(tmp_path / "Foo.cs"),
        ]
    )

    assert rc != 0
    assert rc not in (1, 2, 3)  # distinct from the existing preflight exit codes
    assert rc == 4
    err = capsys.readouterr().err
    assert "revert failed" in err


# =============================================================================
# Scenario: GenerationExhausted gets its OWN exit code (5), distinct from the
# generic RuntimeError exit code 4 above (#1908 review). Exit 4 most
# commonly means "a failed revert — the tree may be left in an
# unknown/possibly-mutated state", though it currently also absorbs other,
# actually-clean RuntimeErrors (#1930); exit 5 means "a clean
# retry-then-downgrade exhaustion — nothing was mutated" — stryker_shard_
# pipeline.py's shard driver treats the two very differently (abort the
# shard vs. continue to the next file).
# =============================================================================
def test_main_returns_exit_code_5_when_generation_exhausted_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    monkeypatch.setattr(headless, "claude_cli_available", lambda: True)

    def boom(*a, **k):
        raise shared.GenerationExhausted("foo.cs (round 3) exhausted its retry budget")

    monkeypatch.setattr(headless, "run_for_file", boom)
    config_path = _write_config(tmp_path)

    rc = headless.main(
        [
            "--config", str(config_path),
            "--headless",
            "--file", "Foo.cs",
            "--test-file", str(tmp_path / "FooTests.cs"),
            "--source-path", str(tmp_path / "Foo.cs"),
        ]
    )

    assert rc == 5
    err = capsys.readouterr().err
    assert "exhausted its retry budget" in err


# =============================================================================
# Scenario: make_headless_generator wires through
# mutation_kill_shared.make_retrying_headless_call (#1908, Slice 3 Step 3.2)
# — round tracking, per-closure isolation, and GenerationExhausted
# propagation. The retry/downgrade behavior itself is covered exhaustively
# in test_mutation_kill_shared.py; this file only proves the wiring.
# =============================================================================
def test_make_headless_generator_derives_round_number_from_call_count(
    monkeypatch: pytest.MonkeyPatch,
):
    """generate() carries no round parameter of its own (the shared
    Generator signature doesn't have one) — make_headless_generator derives
    it from how many times its own closure has been invoked."""
    logged: list[str] = []
    gw = lambda: RuntimeError("claude CLI failed (exit 1): 502 Bad Gateway")
    sequenced_run_claude_headless(
        monkeypatch,
        shared,
        "round-1-result",
        gw(),
        gw(),
        gw(),
        gw(),
        "round-2-result",
    )
    generate = headless.make_headless_generator(
        "opus", log=logged.append, sleep=lambda _s: None
    )
    survivors = [_mutant("Survived")]

    assert generate("Foo.cs", survivors, "src", "tests") == "round-1-result"
    assert generate("Foo.cs", survivors, "src", "tests") == "round-2-result"

    assert len(logged) == 1
    assert "round 2" in logged[0]


def test_make_headless_generator_propagates_generation_exhausted(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("DEV_TEAM_MUTATION_FALLBACK_MODEL", raising=False)
    gw = lambda: RuntimeError("claude CLI failed (exit 1): 502 Bad Gateway")
    sequenced_run_claude_headless(
        monkeypatch, shared, gw(), gw(), gw(), gw(), gw(), gw(), gw(), gw()
    )
    generate = headless.make_headless_generator(
        "opus", log=lambda _: None, sleep=lambda _s: None
    )

    with pytest.raises(shared.GenerationExhausted):
        generate("Foo.cs", [_mutant("Survived")], "src", "tests")


def test_make_headless_generator_closures_do_not_share_downgrade_state(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("DEV_TEAM_MUTATION_FALLBACK_MODEL", raising=False)
    gw = lambda: RuntimeError("claude CLI failed (exit 1): 502 Bad Gateway")
    seen = sequenced_run_claude_headless(
        monkeypatch, shared, gw(), gw(), gw(), gw(), "ok-on-sonnet"
    )
    generate_a = headless.make_headless_generator("opus", sleep=lambda _s: None)
    generate_a("FileA.cs", [_mutant("Survived")], "src", "tests")  # downgrades A to sonnet
    assert seen[-1][1] == "sonnet"

    seen = sequenced_run_claude_headless(monkeypatch, shared, "ok-on-opus")
    generate_b = headless.make_headless_generator("opus", sleep=lambda _s: None)
    generate_b("FileB.cs", [_mutant("Survived")], "src", "tests")

    # file B's fresh closure is unaffected by A's downgrade
    assert [model for _, model in seen] == ["opus"]


def test_main_wires_label_override_provider_into_runcontext(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """main() builds the on_downgrade/get_label_override audit-trail pair
    itself (#1908 review) and threads get_label_override straight into
    RunContext.label_override_provider — no monkey-patched attribute on
    generate() involved. Previously untested: the "assembly point" where
    main() actually wires make_downgrade_audit_hook()'s result into
    RunContext had zero coverage."""
    monkeypatch.setattr(headless, "claude_cli_available", lambda: True)
    sentinel_on_downgrade = lambda event: None
    sentinel_get_label_override = lambda: "sentinel-label"
    monkeypatch.setattr(
        headless,
        "make_downgrade_audit_hook",
        lambda: (sentinel_on_downgrade, sentinel_get_label_override),
    )
    captured: dict = {}
    monkeypatch.setattr(headless, "run_for_file", lambda *a, **k: captured.update(a[1].__dict__))
    config_path = _write_config(tmp_path)

    headless.main(
        [
            "--config", str(config_path),
            "--headless",
            "--file", "Foo.cs",
            "--test-file", str(tmp_path / "FooTests.cs"),
            "--source-path", str(tmp_path / "Foo.cs"),
        ]
    )

    assert captured["label_override_provider"] is sentinel_get_label_override


def test_make_headless_generator_label_override_reflects_a_downgrade(
    monkeypatch: pytest.MonkeyPatch,
):
    """make_headless_generator no longer builds its own audit-trail pair —
    the caller (here, the test itself, standing in for main()) constructs
    make_downgrade_audit_hook() and passes on_downgrade in; get_label_override
    is read from that same pair, not from a generate() attribute (#1908
    review)."""
    monkeypatch.delenv("DEV_TEAM_MUTATION_FALLBACK_MODEL", raising=False)
    gw = lambda: RuntimeError("claude CLI failed (exit 1): 502 Bad Gateway")
    sequenced_run_claude_headless(monkeypatch, shared, gw(), gw(), gw(), gw(), "ok-on-sonnet")
    on_downgrade, get_label_override = shared.make_downgrade_audit_hook()
    generate = headless.make_headless_generator(
        "opus", log=lambda _: None, on_downgrade=on_downgrade, sleep=lambda _s: None
    )

    generate("Foo.cs", [_mutant("Survived")], "src", "tests")

    label = get_label_override()
    assert label is not None
    assert "opus" in label and "sonnet" in label and "Foo.cs" in label
