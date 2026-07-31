"""Pytest tests for mutation_kill_loop.py — config loading and the scoped
Stryker-run mechanics (Slice 2 of the ACI mutation-pipeline fold, #1136).

Each test maps to a Slice 2 Gherkin scenario in
``plans/generalize-aci-mutation-pipeline-fold-into-mutation-kill.md``. Every
dotnet / git / Stryker subprocess is mocked — no real .NET tooling runs — and
every project name is generic. Fixtures write a minimal ``stryker-config.json``
and a fixed ``mutation-report.json`` to a tmp_path repo so path derivation and
survivor extraction are exercised without a live mutation run.

Insertion mechanics live in ``test_mutation_kill_insert.py`` and headless
generation / CLI in ``test_mutation_kill_headless.py`` (#1562). Split further
(#1564): run_for_file orchestration (insertion -> verify -> commit/revert)
moved to ``test_mutation_kill_loop_orchestration.py``, verify/commit
subprocess wiring moved to ``test_mutation_kill_loop_verify.py``, and the
CLI-dispatch/module-literal checks moved to ``test_mutation_kill_loop_cli.py``
— this file now covers only config
loading, the scoped Stryker run (timeouts, .sln handling, path validation),
``make_scoped_config``'s output shape, and env-var timeout parsing.
"""

from __future__ import annotations

import json
from pathlib import Path

import mutation_kill_loop as loop
import pytest
from _mutation_kill_loop_test_helpers import _mutant, _write_config, _write_report
from _mutation_test_helpers import FORBIDDEN_LITERALS


# =============================================================================
# Scenario: Build and test targets derive from config, not literals
# =============================================================================
def test_build_and_test_targets_derive_from_config(tmp_path: Path):
    config = loop.load_loop_config(
        _write_config(tmp_path, test_projects=("test/Foo.Tests/Foo.Tests.csproj",))
    )

    assert loop.dotnet_test_project_targets(config) == ["test/Foo.Tests/Foo.Tests.csproj"]


def test_config_supports_both_wrapper_and_flat_shapes(tmp_path: Path):
    wrapped = loop.load_loop_config(_write_config(tmp_path, wrapper_shape=True))
    flat_root = tmp_path / "flat"
    flat_root.mkdir()
    flat = loop.load_loop_config(_write_config(flat_root, wrapper_shape=False))

    assert wrapped.test_projects == flat.test_projects
    assert wrapped.project == flat.project
    assert wrapped.solution == flat.solution


# =============================================================================
# Scenario: End-to-end fixture path with only a stryker-config.json (AC2)
# =============================================================================
def test_end_to_end_fixture_derives_paths_and_extracts_survivors(tmp_path: Path):
    # A non-ACI fixture repo: only a stryker-config.json plus a fixed report.
    config = loop.load_loop_config(_write_config(tmp_path))
    report = _write_report(
        tmp_path,
        "src/Widget.WebApi/PaymentService.cs",
        [
            _mutant("Survived", "ArithmeticOperator", 10),
            _mutant("Survived", "EqualityOperator", 20),
            _mutant("Killed", "ArithmeticOperator", 30),
        ],
    )

    # Paths derive from config — the configured test-project, no ACI literal.
    assert loop.dotnet_test_project_targets(config) == [
        "test/Widget.WebApi.Tests/Widget.WebApi.Tests.csproj"
    ]

    survivors = loop.extract_survivors(report, "PaymentService.cs")

    assert len(survivors) == 2
    assert {m["mutatorName"] for m in survivors} == {
        "ArithmeticOperator",
        "EqualityOperator",
    }
    # No ACI-specific path referenced anywhere in the derived data.
    blob = json.dumps([config.__dict__, survivors])
    assert not any(lit in blob for lit in FORBIDDEN_LITERALS)


# =============================================================================
# Scenario: The loop delegates DOTNET_ROOT and .sln handling to the wrapper (AC4)
# =============================================================================
def test_scoped_run_delegates_dotnet_root_and_sln_to_wrapper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config = loop.load_loop_config(_write_config(tmp_path, solution="App.sln"))
    calls: list = []

    def spy_hide(sln, sln_hidden):
        calls.append(("hide_sln", str(sln)))

    def spy_restore(sln, sln_hidden):
        calls.append(("restore_sln", str(sln)))

    def fake_subprocess_run(argv, **kwargs):
        calls.append(("subprocess.run", argv, kwargs))

    monkeypatch.setattr(
        loop.wrapper, "resolve_dotnet_root", lambda preset, candidates: ("/fake/dotnet-root", None)
    )
    monkeypatch.setattr(
        loop.wrapper,
        "default_probe_candidates",
        lambda: calls.append(("default_probe_candidates",)) or ["/fake/candidate"],
    )
    monkeypatch.setattr(loop.wrapper, "hide_sln", spy_hide)
    monkeypatch.setattr(loop.wrapper, "restore_sln", spy_restore)
    monkeypatch.setattr(loop.subprocess, "run", fake_subprocess_run)

    report_path = loop.run_scoped_stryker(
        config, "PaymentService.cs", output_dir=tmp_path / "out", stryker_bin="dotnet-stryker"
    )

    # sln hidden/restored around the run, in that order (finally-block-runs-
    # after-subprocess is the actual behavior under test here — a legitimate
    # ordering assertion, unlike asserting exact call order between
    # default_probe_candidates and resolve_dotnet_root, which is incidental
    # implementation detail rather than an observable outcome (#1563 gap 8)).
    kinds = [c[0] for c in calls]
    assert kinds.index("hide_sln") < kinds.index("subprocess.run") < kinds.index(
        "restore_sln"
    )
    # The loop doesn't reimplement wrapper probe logic itself — it delegates
    # to wrapper.default_probe_candidates() for the candidate list handed to
    # resolve_dotnet_root (the AC4 delegation this test is named for).
    assert "default_probe_candidates" in kinds
    # The Stryker subprocess is invoked through the configured bin.
    stryker_call = next(c for c in calls if c[0] == "subprocess.run")
    stryker_argv = stryker_call[1]
    assert stryker_argv[0] == "dotnet-stryker"
    # Observable outcome: the RESOLVED DOTNET_ROOT is threaded into the
    # Stryker subprocess environment — not merely resolved and dropped.
    stryker_kwargs = stryker_call[2]
    assert stryker_kwargs["env"]["DOTNET_ROOT"] == "/fake/dotnet-root"
    assert report_path == tmp_path / "out" / "reports" / "mutation-report.json"


# =============================================================================
# Scenario: A DOTNET_ROOT resolution failure aborts the run with a named
# error, before any Stryker subprocess is spawned (#1563 gap 4)
# =============================================================================
def test_run_scoped_stryker_raises_when_dotnet_root_resolution_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config = loop.load_loop_config(_write_config(tmp_path, solution=None))
    monkeypatch.setattr(
        loop.wrapper,
        "resolve_dotnet_root",
        lambda preset, candidates: (None, "no DOTNET_ROOT candidate found"),
    )
    monkeypatch.setattr(loop.wrapper, "default_probe_candidates", list)

    def explode(*a, **k):
        raise AssertionError("Stryker must not run when DOTNET_ROOT can't resolve")

    monkeypatch.setattr(loop.subprocess, "run", explode)

    with pytest.raises(RuntimeError, match="no DOTNET_ROOT candidate found"):
        loop.run_scoped_stryker(config, "Foo.cs", output_dir=tmp_path / "out")


# =============================================================================
# Scenario: A hung Stryker subprocess is bounded by a timeout, not left to
# hang forever (#1558)
# =============================================================================
def test_scoped_stryker_run_passes_a_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config = loop.load_loop_config(_write_config(tmp_path, solution=None))
    monkeypatch.setattr(
        loop.wrapper, "resolve_dotnet_root", lambda preset, candidates: ("/fake", None)
    )
    monkeypatch.setattr(loop.wrapper, "default_probe_candidates", list)
    captured: dict = {}

    def fake_run(argv, **kwargs):
        captured.update(kwargs)

        class _R:
            returncode = 0

        return _R()

    monkeypatch.setattr(loop.subprocess, "run", fake_run)

    loop.run_scoped_stryker(config, "Foo.cs", output_dir=tmp_path / "out")

    assert captured["timeout"] == loop.STRYKER_RUN_TIMEOUT_S


def test_scoped_stryker_run_timeout_raises_a_named_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config = loop.load_loop_config(_write_config(tmp_path, solution=None))
    monkeypatch.setattr(
        loop.wrapper, "resolve_dotnet_root", lambda preset, candidates: ("/fake", None)
    )
    monkeypatch.setattr(loop.wrapper, "default_probe_candidates", list)

    def fake_run(argv, **kwargs):
        raise loop.subprocess.TimeoutExpired(argv, kwargs.get("timeout"))

    monkeypatch.setattr(loop.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError) as exc_info:
        loop.run_scoped_stryker(config, "Foo.cs", output_dir=tmp_path / "out")

    assert str(loop.STRYKER_RUN_TIMEOUT_S) in str(exc_info.value)
    assert "DEV_TEAM_MUTATION_STRYKER_TIMEOUT_S" in str(exc_info.value)


def test_scoped_stryker_run_restores_sln_even_on_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # A timeout is just another exception path through run_scoped_stryker's
    # try/finally — the .sln must be restored and the scoped config cleaned
    # up exactly as on any other failure, not just the happy path.
    config = loop.load_loop_config(_write_config(tmp_path, solution="App.sln"))
    monkeypatch.setattr(
        loop.wrapper, "resolve_dotnet_root", lambda preset, candidates: ("/fake", None)
    )
    monkeypatch.setattr(loop.wrapper, "default_probe_candidates", list)
    calls: list = []
    monkeypatch.setattr(
        loop.wrapper, "hide_sln", lambda sln, sln_hidden: calls.append("hide_sln")
    )
    monkeypatch.setattr(
        loop.wrapper, "restore_sln", lambda sln, sln_hidden: calls.append("restore_sln")
    )

    def fake_run(argv, **kwargs):
        raise loop.subprocess.TimeoutExpired(argv, kwargs.get("timeout"))

    monkeypatch.setattr(loop.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError):
        loop.run_scoped_stryker(config, "Foo.cs", output_dir=tmp_path / "out")

    assert calls == ["hide_sln", "restore_sln"]


# =============================================================================
# Scenario: Timeout env vars parse cleanly, or fail with a named message
# (#1558) — pinned against literal values, not the module constant under
# test, so a regression to the parsing logic itself is actually caught.
# =============================================================================
def test_timeout_from_env_returns_the_default_when_unset(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("SOME_TIMEOUT_VAR", raising=False)
    assert loop._timeout_from_env("SOME_TIMEOUT_VAR", 42) == 42


def test_timeout_from_env_parses_an_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SOME_TIMEOUT_VAR", "99")
    assert loop._timeout_from_env("SOME_TIMEOUT_VAR", 42) == 99


def test_timeout_from_env_rejects_a_non_numeric_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SOME_TIMEOUT_VAR", "not-a-number")
    with pytest.raises(ValueError, match="SOME_TIMEOUT_VAR"):
        loop._timeout_from_env("SOME_TIMEOUT_VAR", 42)


def test_timeout_from_env_rejects_a_non_positive_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SOME_TIMEOUT_VAR", "0")
    with pytest.raises(ValueError, match="SOME_TIMEOUT_VAR"):
        loop._timeout_from_env("SOME_TIMEOUT_VAR", 42)


# =============================================================================
# Scenario: _validate_solution_path requires a RELATIVE solution — an
# absolute value is rejected in every practical case, since pathlib's `/`
# silently discards `base` when the right operand is already absolute
# (#1598/#1584 review, item 11).
# =============================================================================
def test_validate_solution_path_rejects_an_absolute_solution_outside_cwd(
    tmp_path: Path,
):
    with pytest.raises(ValueError, match="escapes the working tree"):
        loop._validate_solution_path("/etc/passwd", cwd=tmp_path)


def test_validate_solution_path_accepts_an_absolute_solution_already_under_cwd(
    tmp_path: Path,
):
    """Pins the degenerate case the docstring names: `base / solution`
    discards `base` outright for an absolute `solution`, so an absolute
    value is accepted only when it already happens to lie under `base` —
    the resulting candidate is identical to the absolute value itself, not
    `base` joined with it."""
    absolute_solution = str((tmp_path / "App.sln").resolve())

    result = loop._validate_solution_path(absolute_solution, cwd=tmp_path)

    assert result == (tmp_path / "App.sln").resolve()


# =============================================================================
# Scenario: config.solution is sanitized before it's used to derive the
# hidden-.sln filename (#1598). The filename itself is FIXED, not
# process-unique — a PID-suffixed name was tried (#1584) to guard two
# concurrent scoped runs against the same solution, but reverted after
# review: it would be invisible to csharp_stryker_net_wrapper.py's
# check_stale_hidden_sln() crash-recovery, which looks for the exact literal
# ".stryker-hidden" suffix (see test_scoped_stryker_hidden_sln_name_has_no_pid_suffix
# below).
# =============================================================================
def test_run_scoped_stryker_rejects_a_traversal_solution_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config = loop.load_loop_config(
        _write_config(tmp_path, solution="../../etc/cron.d/evil.sln")
    )
    monkeypatch.setattr(
        loop.wrapper, "resolve_dotnet_root", lambda preset, candidates: ("/fake", None)
    )
    monkeypatch.setattr(loop.wrapper, "default_probe_candidates", list)
    monkeypatch.setattr(
        loop.wrapper,
        "hide_sln",
        lambda *a, **k: pytest.fail("must not hide before the solution path is validated"),
    )

    with pytest.raises(ValueError, match="escapes the working tree"):
        loop.run_scoped_stryker(
            config, "Foo.cs", output_dir=tmp_path / "out", cwd=tmp_path
        )


def test_run_scoped_stryker_accepts_a_normal_relative_solution_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Not just "must not raise" — the resolved, validated path is what
    actually gets hidden/restored, at the FIXED (no-PID) name (#1598/#1584
    review, item 10 test-review finding)."""
    config = loop.load_loop_config(_write_config(tmp_path, solution="App.sln"))
    monkeypatch.setattr(
        loop.wrapper, "resolve_dotnet_root", lambda preset, candidates: ("/fake", None)
    )
    monkeypatch.setattr(loop.wrapper, "default_probe_candidates", list)
    hide_calls: list = []
    restore_calls: list = []
    monkeypatch.setattr(
        loop.wrapper,
        "hide_sln",
        lambda sln, sln_hidden: hide_calls.append((sln, sln_hidden)),
    )
    monkeypatch.setattr(
        loop.wrapper,
        "restore_sln",
        lambda sln, sln_hidden: restore_calls.append((sln, sln_hidden)),
    )

    class _R:
        returncode = 0

    monkeypatch.setattr(loop.subprocess, "run", lambda *a, **k: _R())

    loop.run_scoped_stryker(config, "Foo.cs", output_dir=tmp_path / "out", cwd=tmp_path)

    expected_sln = (tmp_path / "App.sln").resolve()
    expected_hidden = Path(f"{expected_sln}.stryker-hidden")
    assert hide_calls == [(expected_sln, expected_hidden)]
    assert restore_calls == [(expected_sln, expected_hidden)]


def test_run_scoped_stryker_calls_check_stale_hidden_sln_before_hiding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Mirrors the wrapper's own main() and
    csharp_stryker_net_slice_runner.py's fleet-level caller (#1598/#1584
    review, item 6): the stale-hidden-.sln crash-recovery check must run
    BEFORE hide_sln, or a stale file left by a prior crash is never caught
    here."""
    config = loop.load_loop_config(_write_config(tmp_path, solution="App.sln"))
    monkeypatch.setattr(
        loop.wrapper, "resolve_dotnet_root", lambda preset, candidates: ("/fake", None)
    )
    monkeypatch.setattr(loop.wrapper, "default_probe_candidates", list)
    calls: list = []
    monkeypatch.setattr(
        loop.wrapper,
        "check_stale_hidden_sln",
        lambda sln, sln_hidden: calls.append("check_stale_hidden_sln") or None,
    )
    monkeypatch.setattr(loop.wrapper, "hide_sln", lambda *a, **k: calls.append("hide_sln"))
    monkeypatch.setattr(
        loop.wrapper, "restore_sln", lambda *a, **k: calls.append("restore_sln")
    )

    class _R:
        returncode = 0

    monkeypatch.setattr(loop.subprocess, "run", lambda *a, **k: _R())

    loop.run_scoped_stryker(config, "Foo.cs", output_dir=tmp_path / "out", cwd=tmp_path)

    assert calls[:2] == ["check_stale_hidden_sln", "hide_sln"]


def test_run_scoped_stryker_raises_when_stale_hidden_sln_check_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config = loop.load_loop_config(_write_config(tmp_path, solution="App.sln"))
    monkeypatch.setattr(
        loop.wrapper, "resolve_dotnet_root", lambda preset, candidates: ("/fake", None)
    )
    monkeypatch.setattr(loop.wrapper, "default_probe_candidates", list)
    monkeypatch.setattr(
        loop.wrapper,
        "check_stale_hidden_sln",
        lambda sln, sln_hidden: "error: stale .stryker-hidden present\n",
    )
    monkeypatch.setattr(
        loop.wrapper,
        "hide_sln",
        lambda *a, **k: pytest.fail("must not hide when the stale-hidden check refuses"),
    )

    with pytest.raises(RuntimeError, match="stale"):
        loop.run_scoped_stryker(config, "Foo.cs", output_dir=tmp_path / "out", cwd=tmp_path)


def test_scoped_stryker_hidden_sln_name_has_no_pid_suffix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """PID-suffixing the hidden .sln name was tried (#1584) and reverted
    after review: stryker_shard_pipeline.py runs shards sequentially (no
    concurrent race to guard against today), and a PID-suffixed name is
    invisible to csharp_stryker_net_wrapper.py's check_stale_hidden_sln()
    crash-recovery, which looks for the exact literal ".stryker-hidden"
    suffix."""
    config = loop.load_loop_config(_write_config(tmp_path, solution="App.sln"))
    monkeypatch.setattr(
        loop.wrapper, "resolve_dotnet_root", lambda preset, candidates: ("/fake", None)
    )
    monkeypatch.setattr(loop.wrapper, "default_probe_candidates", list)
    hidden_names: list = []
    monkeypatch.setattr(
        loop.wrapper, "hide_sln", lambda sln, sln_hidden: hidden_names.append(str(sln_hidden))
    )
    monkeypatch.setattr(loop.wrapper, "restore_sln", lambda *a, **k: None)

    class _R:
        returncode = 0

    monkeypatch.setattr(loop.subprocess, "run", lambda *a, **k: _R())

    loop.run_scoped_stryker(config, "Foo.cs", output_dir=tmp_path / "out", cwd=tmp_path)

    assert hidden_names == [str((tmp_path / "App.sln").resolve()) + ".stryker-hidden"]
    assert str(loop.os.getpid()) not in hidden_names[0]


# =============================================================================
# Scenario: make_scoped_config's output shape — mutate glob, coverage
# analysis, reporters, and dropping of unset (None) keys (#1584)
# =============================================================================
def test_make_scoped_config_shape(tmp_path: Path):
    config = loop.load_loop_config(_write_config(tmp_path, solution=None))

    scoped = loop.make_scoped_config(config, "PaymentService.cs")

    inner = scoped["stryker-config"]
    assert inner["mutate"] == ["**/PaymentService.cs"]
    assert inner["coverage-analysis"] == "perTest"
    assert inner["reporters"] == ["json"]
    assert inner["project"] == config.project
    assert inner["test-projects"] == config.test_projects
    # solution was unset (None) in the loaded config — dropped entirely,
    # never carried forward as a null value for Stryker to choke on.
    assert "solution" not in inner


def test_make_scoped_config_carries_a_set_solution_through(tmp_path: Path):
    """The solution=None branch above only proves dropping — this proves the
    opposite branch: a real configured solution is carried into the scoped
    config, not silently dropped too (#1598/#1584 review, item 10)."""
    config = loop.load_loop_config(_write_config(tmp_path, solution="App.sln"))

    scoped = loop.make_scoped_config(config, "PaymentService.cs")

    inner = scoped["stryker-config"]
    assert inner["solution"] == "App.sln"
