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

import mutation_kill_loop_python as loop
import mutation_kill_retry as retry
import mutation_kill_shared as shared
import pytest
from _mutation_kill_loop_python_test_helpers import _junit, _survived
from _mutation_test_helpers import (
    FORBIDDEN_LITERALS,
    SCRIPTS_DIR,
    gateway_error,
    sequenced_run_claude_headless,
)


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
    assert rc == 4
    assert "revert failed" in capsys.readouterr().err


# =============================================================================
# Scenario: GenerationExhausted gets its OWN exit code (5), distinct from the
# generic RuntimeError exit code 4 above (#1908 review). Exit 4 most
# commonly means "a failed revert — the tree may be left in an
# unknown/possibly-mutated state", though it currently also absorbs other,
# actually-clean RuntimeErrors (#1930); exit 5 means "a clean
# retry-then-downgrade exhaustion — nothing was mutated by the
# insertion-revert paths this covers" (run_scoped_mutmut's best-effort
# post-mutmut-crash revert is deliberately not checked, so a
# mutmut-crash leftover is the one on-disk mutation exit 5 does not rule
# out — #1928) — stryker_shard_pipeline.py's shard driver treats the two
# very differently (abort the shard vs. continue to the next file).
# =============================================================================
def test_main_returns_exit_code_5_when_generation_exhausted_propagates(
    monkeypatch, capsys, tmp_path: Path
):
    monkeypatch.setattr(loop, "claude_cli_available", lambda: True)

    def boom(*a, **k):
        raise retry.GenerationExhausted("a.py (round 3) exhausted its retry budget")

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

    assert rc == 5
    assert "exhausted its retry budget" in capsys.readouterr().err


# =============================================================================
# Scenario: make_headless_generator wires through
# mutation_kill_retry.make_retrying_headless_call (#1908, Slice 3 Step 3.2)
# — round tracking, per-closure isolation, and GenerationExhausted
# propagation. The retry/downgrade behavior itself is covered exhaustively
# in test_mutation_kill_retry.py; this file only proves the wiring.
# =============================================================================
def test_make_headless_generator_derives_round_number_from_call_count(
    monkeypatch: pytest.MonkeyPatch,
):
    """generate() carries no round parameter of its own (the shared
    Generator signature doesn't have one) — make_headless_generator derives
    it from how many times its own closure has been invoked."""
    logged: list[str] = []
    sequenced_run_claude_headless(
        monkeypatch, shared,
        "round-1-result",
        gateway_error(), gateway_error(), gateway_error(), gateway_error(),
        "round-2-result",
    )
    generate = loop.make_headless_generator(
        "opus", log=logged.append, sleep=lambda _s: None
    )

    assert generate("a.py", [], "x = 1\n", "def test_existing(): pass\n") == "round-1-result"
    assert generate("a.py", [], "x = 1\n", "def test_existing(): pass\n") == "round-2-result"

    assert len(logged) == 1
    assert "round 2" in logged[0]


def test_make_headless_generator_propagates_generation_exhausted(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("DEV_TEAM_MUTATION_FALLBACK_MODEL", raising=False)
    sequenced_run_claude_headless(
        monkeypatch, shared,
        *([gateway_error()] * 8),
    )
    generate = loop.make_headless_generator(
        "opus", log=lambda _: None, sleep=lambda _s: None
    )

    with pytest.raises(retry.GenerationExhausted):
        generate("a.py", [], "x = 1\n", "def test_existing(): pass\n")


def test_make_headless_generator_closures_do_not_share_downgrade_state(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("DEV_TEAM_MUTATION_FALLBACK_MODEL", raising=False)
    seen = sequenced_run_claude_headless(
        monkeypatch, shared,
        gateway_error(), gateway_error(), gateway_error(), gateway_error(),
        "ok-on-sonnet",
    )
    generate_a = loop.make_headless_generator("opus", sleep=lambda _s: None)
    generate_a("a.py", [], "x = 1\n", "def test_existing(): pass\n")  # downgrades A to sonnet
    assert seen[-1][1] == "sonnet"

    seen = sequenced_run_claude_headless(monkeypatch, shared, "ok-on-opus")
    generate_b = loop.make_headless_generator("opus", sleep=lambda _s: None)
    generate_b("b.py", [], "x = 1\n", "def test_existing(): pass\n")

    # file B's fresh closure is unaffected by A's downgrade
    assert [model for _, model in seen] == ["opus"]


def test_main_wires_label_override_provider_into_runcontext(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """main() builds the on_downgrade/get_label_override audit-trail pair
    itself (#1908 review) and threads get_label_override straight into
    RunContext.label_override_provider — no monkey-patched attribute on
    generate() involved. Previously untested: the "assembly point" where
    main() actually wires make_downgrade_audit_hook()'s result into
    RunContext had zero coverage."""
    monkeypatch.setattr(loop, "claude_cli_available", lambda: True)
    def sentinel_on_downgrade(event):
        return None

    def sentinel_get_label_override():
        return "sentinel-label"
    monkeypatch.setattr(
        loop,
        "make_downgrade_audit_hook",
        lambda: (sentinel_on_downgrade, sentinel_get_label_override),
    )
    captured: dict = {}
    monkeypatch.setattr(loop, "run_for_file", lambda *a, **k: captured.update(a[1].__dict__))

    loop.main(
        [
            "--headless",
            "--file", "a.py",
            "--test-file", str(tmp_path / "test_a.py"),
            "--source-path", str(tmp_path / "a.py"),
            "--test-command", "pytest",
        ]
    )

    assert captured["label_override_provider"] is sentinel_get_label_override


# =============================================================================
# Scenario: the full #1917 -> #1918 -> #1919 chain, unmocked at the
# generation-classification layer (#1938 review gap). Every other test in
# this file either injects GenerationExhausted directly via a mocked
# run_for_file (bypassing #1917's HeadlessCallFailed classification and
# #1918's _RetryState machine entirely) or, at stryker_shard_pipeline.py's
# layer, a raw subprocess rc=5 with no connection to a real gateway-class
# failure. Here neither run_for_file nor generate is monkeypatched: a real
# HeadlessCallFailed (raised by mutation_kill_shared.run_claude_headless's
# non-zero-exit shape via sequenced_run_claude_headless/gateway_error) drives
# make_retrying_headless_call's real _RetryState through the same
# 3-failure-threshold -> 1 retry -> downgrade -> repeat-until-ladder-floor
# sequence exercised elsewhere in this file
# (test_make_headless_generator_propagates_generation_exhausted), but through
# main() end-to-end so GenerationExhausted must actually propagate out of the
# real mutation_kill_loop_python.run_for_file and be caught by main() itself.
# run_scoped_mutmut (the real mutmut subprocess boundary run_for_file also
# calls) is mocked — that's the build/test-adjacent side effect this loop
# performs beyond generation, not the generation-classification layer under
# test here.
# =============================================================================
def test_main_returns_exit_code_5_via_real_retry_downgrade_chain_unmocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    monkeypatch.setattr(loop, "claude_cli_available", lambda: True)
    monkeypatch.delenv("DEV_TEAM_MUTATION_FALLBACK_MODEL", raising=False)
    monkeypatch.setattr(
        loop,
        "run_scoped_mutmut",
        lambda *a, **k: _junit(_survived("Mutant #1", "a.py", 3), failures=1),
    )
    # 8 gateway-class failures: 3 + 1 retry exhausts opus and spends the
    # file's one downgrade to sonnet; 3 + 1 retry then exhausts sonnet with
    # no further downgrade available.
    sequenced_run_claude_headless(monkeypatch, shared, *([gateway_error()] * 8))

    test_file = tmp_path / "test_a.py"
    test_file.write_text("def test_existing():\n    assert True\n", encoding="utf-8")
    source_file = tmp_path / "a.py"
    source_file.write_text("x = 1\n", encoding="utf-8")

    rc = loop.main(
        [
            "--headless",
            "--model", "opus",
            "--file", "a.py",
            "--test-file", str(test_file),
            "--source-path", str(source_file),
            "--test-command", "pytest",
        ]
    )

    assert rc == 5
    err = capsys.readouterr().err
    assert "exhausted its retry budget" in err


def test_make_headless_generator_label_override_reflects_a_downgrade(
    monkeypatch: pytest.MonkeyPatch,
):
    """make_headless_generator no longer builds its own audit-trail pair —
    the caller (here, the test itself, standing in for main()) constructs
    make_downgrade_audit_hook() and passes on_downgrade in; get_label_override
    is read from that same pair, not from a generate() attribute (#1908
    review)."""
    monkeypatch.delenv("DEV_TEAM_MUTATION_FALLBACK_MODEL", raising=False)
    sequenced_run_claude_headless(
        monkeypatch, shared,
        gateway_error(), gateway_error(), gateway_error(), gateway_error(),
        "ok-on-sonnet",
    )
    on_downgrade, get_label_override = retry.make_downgrade_audit_hook()
    generate = loop.make_headless_generator(
        "opus", log=lambda _: None, on_downgrade=on_downgrade, sleep=lambda _s: None
    )

    generate("a.py", [], "x = 1\n", "def test_existing(): pass\n")

    label = get_label_override()
    assert label is not None
    assert "opus" in label and "sonnet" in label and "a.py" in label
