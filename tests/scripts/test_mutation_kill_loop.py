"""Pytest tests for mutation_kill_loop.py — the config-driven survivor-kill
loop mechanics (Slice 2 of the ACI mutation-pipeline fold, #1136).

Each test maps to a Slice 2 Gherkin scenario in
``plans/generalize-aci-mutation-pipeline-fold-into-mutation-kill.md``. Every
dotnet / git / Stryker subprocess is mocked — no real .NET tooling runs — and
every project name is generic. Fixtures write a minimal ``stryker-config.json``
and a fixed ``mutation-report.json`` to a tmp_path repo so path derivation and
survivor extraction are exercised without a live mutation run.

Insertion mechanics moved to ``test_mutation_kill_insert.py`` and headless
generation / CLI moved to ``test_mutation_kill_headless.py`` (#1562) — this
file now covers only config, the scoped Stryker run, verify/commit
subprocess wiring, and ``run_for_file`` orchestration.
"""

from __future__ import annotations

import dataclasses
import json
import subprocess
import sys
from pathlib import Path

import pytest
from _mutation_test_helpers import (
    FORBIDDEN_LITERALS,
    SCRIPTS_DIR,
    git_hermetic,
    hermetic_git_env,
)

# Ensure the module's dir is on the path so we can import it directly.
sys.path.insert(0, str(SCRIPTS_DIR))

import mutation_kill_headless  # module-split literal check below
import mutation_kill_insert  # module-split literal check below
import mutation_kill_loop as loop


# =============================================================================
# Fixture helpers
# =============================================================================
def _write_config(
    repo_root: Path,
    *,
    project: str = "src/Widget.WebApi/Widget.WebApi.csproj",
    test_projects=("test/Widget.WebApi.Tests/Widget.WebApi.Tests.csproj",),
    solution: str = "App.sln",
    wrapper_shape: bool = True,
) -> Path:
    inner = {
        "solution": solution,
        "project": project,
        "test-projects": list(test_projects),
        "mutate": ["**/*.cs"],
    }
    payload = {"stryker-config": inner} if wrapper_shape else inner
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


def _write_report(repo_root: Path, source_key: str, mutants) -> Path:
    report = repo_root / "reports" / "mutation-report.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps({"files": {source_key: {"mutants": list(mutants)}}}),
        encoding="utf-8",
    )
    return report


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

    def spy_resolve(preset, candidates):
        calls.append(("resolve_dotnet_root", candidates))
        return "/fake/dotnet-root", None

    def spy_candidates():
        calls.append(("default_probe_candidates", None))
        return ["/fake/candidate"]

    def spy_hide(sln, sln_hidden):
        calls.append(("hide_sln", str(sln)))

    def spy_restore(sln, sln_hidden):
        calls.append(("restore_sln", str(sln)))

    def fake_subprocess_run(argv, **kwargs):
        calls.append(("subprocess.run", argv, kwargs))

    monkeypatch.setattr(loop.wrapper, "resolve_dotnet_root", spy_resolve)
    monkeypatch.setattr(loop.wrapper, "default_probe_candidates", spy_candidates)
    monkeypatch.setattr(loop.wrapper, "hide_sln", spy_hide)
    monkeypatch.setattr(loop.wrapper, "restore_sln", spy_restore)
    monkeypatch.setattr(loop.subprocess, "run", fake_subprocess_run)

    report_path = loop.run_scoped_stryker(
        config, "PaymentService.cs", output_dir=tmp_path / "out", stryker_bin="dotnet-stryker"
    )

    kinds = [c[0] for c in calls]
    assert "default_probe_candidates" in kinds
    assert "resolve_dotnet_root" in kinds
    assert "hide_sln" in kinds
    assert "restore_sln" in kinds
    # restore runs after the Stryker subprocess (finally block).
    assert kinds.index("hide_sln") < kinds.index("subprocess.run") < kinds.index(
        "restore_sln"
    )
    # The Stryker subprocess is invoked through the configured bin.
    stryker_call = next(c for c in calls if c[0] == "subprocess.run")
    stryker_argv = stryker_call[1]
    assert stryker_argv[0] == "dotnet-stryker"
    # The RESOLVED DOTNET_ROOT (from the spied resolver) is threaded into the
    # Stryker subprocess environment — not merely resolved and dropped.
    stryker_kwargs = stryker_call[2]
    assert stryker_kwargs["env"]["DOTNET_ROOT"] == "/fake/dotnet-root"
    assert report_path == tmp_path / "out" / "reports" / "mutation-report.json"


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
# run_for_file harness — mocks every dotnet / git / Stryker touch.
# =============================================================================
def _loop_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutants=None,
    *,
    report_override: dict | None = None,
    log=lambda m: None,
):
    """Wire a run_for_file invocation with a fixed initial report and a
    generator that records its calls. Returns (source_file, ctx, kwargs, events).

    By default the initial report is the single-file shape ``_write_report``
    builds from ``mutants``. Pass ``report_override`` (a full report payload,
    e.g. a multi-file ``{"files": {...}}`` shape) instead when a caller needs
    a custom report; ``mutants`` is ignored in that case. Pass ``log`` to
    capture round log lines (it lives on ``RunContext``, not the caller's
    kwargs).
    """
    config = loop.load_loop_config(_write_config(tmp_path))
    test_file = tmp_path / "PaymentServiceTests.cs"
    test_file.write_text(
        (
            "namespace Widget.Tests\n"
            "{\n"
            "    public class PaymentServiceTests\n"
            "    {\n"
            "        [Test]\n"
            "        public async Task Existing_Case_Works()\n"
            "        {\n"
            "        }\n"
            "    }\n"
            "}\n"
        ),
        encoding="utf-8",
    )
    source_path = tmp_path / "PaymentService.cs"
    source_path.write_text("public class PaymentService {}\n", encoding="utf-8")
    if report_override is not None:
        report = tmp_path / "reports" / "mutation-report.json"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(report_override), encoding="utf-8")
    else:
        report = _write_report(tmp_path, "src/Widget.WebApi/PaymentService.cs", mutants)

    events: list = []

    new_method = (
        "        [Test]\n"
        "        public async Task New_Case_KillsMutant()\n"
        "        {\n"
        "        }\n"
    )

    def generator(src, survivors, src_text, test_text):
        events.append(("generate", len(survivors)))
        return new_method

    monkeypatch.setattr(
        loop, "git_revert", lambda tf, **k: events.append(("revert", str(tf))) or True
    )
    # git_reset_and_revert is what the commit-failure path actually calls
    # (#1598/#1584 review) — tagged "revert" too so the existing
    # kinds.count("revert") assertions keep meaning "a revert happened",
    # regardless of which of the two functions performed it.
    monkeypatch.setattr(
        loop,
        "git_reset_and_revert",
        lambda tf, **k: events.append(("revert", str(tf))) or True,
    )
    monkeypatch.setattr(
        loop, "git_commit", lambda msg, tf, **k: events.append(("commit", msg)) or True
    )

    ctx = loop.RunContext(
        config=config,
        test_file=test_file,
        source_path=source_path,
        output_dir=tmp_path / "out",
        log=log,
        initial_report_path=report,
    )
    kwargs = {
        "generate": generator,
        "max_rounds": 3,
    }
    return "PaymentService.cs", ctx, kwargs, events


# =============================================================================
# Scenario: A build failure after insertion is reverted
# =============================================================================
def test_build_failure_after_insertion_is_reverted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source_file, ctx, kwargs, events = _loop_fixture(tmp_path, monkeypatch, [_mutant("Survived")])
    monkeypatch.setattr(loop, "dotnet_build", lambda targets, **k: False)
    monkeypatch.setattr(
        loop, "dotnet_test", lambda *a, **k: pytest.fail("test must not run after build fail")
    )

    loop.run_for_file(source_file, ctx, **kwargs)

    kinds = [e[0] for e in events]
    assert "revert" in kinds
    assert "commit" not in kinds


# =============================================================================
# Scenario: A test failure after insertion is reverted
# =============================================================================
def test_test_failure_after_insertion_is_reverted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source_file, ctx, kwargs, events = _loop_fixture(tmp_path, monkeypatch, [_mutant("Survived")])
    monkeypatch.setattr(loop, "dotnet_build", lambda targets, **k: True)
    monkeypatch.setattr(loop, "dotnet_test", lambda targets, flt, **k: False)

    loop.run_for_file(source_file, ctx, **kwargs)

    kinds = [e[0] for e in events]
    assert "revert" in kinds
    assert "commit" not in kinds


# =============================================================================
# Green round commits (baseline for the revert scenarios above)
# =============================================================================
def test_green_round_commits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    source_file, ctx, kwargs, events = _loop_fixture(tmp_path, monkeypatch, [_mutant("Survived")])
    monkeypatch.setattr(loop, "dotnet_build", lambda targets, **k: True)
    monkeypatch.setattr(loop, "dotnet_test", lambda targets, flt, **k: True)
    # Second round: scoped run returns a clean report so the loop stops "done".
    clean = _write_report(tmp_path / "clean", "src/Widget.WebApi/PaymentService.cs", [])
    (tmp_path / "clean").mkdir(exist_ok=True)
    monkeypatch.setattr(loop, "run_scoped_stryker", lambda *a, **k: clean)

    loop.run_for_file(source_file, ctx, **kwargs)

    kinds = [e[0] for e in events]
    assert "commit" in kinds
    assert "revert" not in kinds


# =============================================================================
# Scenario: A headless (unattended, zero-human-review) commit carries an
# audit trail distinguishing it from an agent-driven one (#1560)
# =============================================================================
def test_commit_message_omits_generator_trailer_by_default():
    message = loop._commit_message(1, "Foo.cs", 2, "public async Task X() {}\n")
    assert "Generator:" not in message


def test_commit_message_includes_generator_trailer_when_labeled():
    message = loop._commit_message(
        1, "Foo.cs", 2, "public async Task X() {}\n", generator_label="headless (some-model)"
    )
    assert "Generator: headless (some-model)" in message


def test_commit_message_generator_label_newlines_cannot_forge_extra_lines():
    # A pipeline-supplied model string containing newlines must not be able
    # to inject a second, forged "Generator:" trailer *line* into the
    # commit — the injected text is neutralized onto the same line instead.
    message = loop._commit_message(
        1,
        "Foo.cs",
        2,
        "public async Task X() {}\n",
        generator_label="some-model\n\nGenerator: agent-driven (reviewed)",
    )
    lines_starting_with_generator = [
        line for line in message.splitlines() if line.startswith("Generator:")
    ]
    assert len(lines_starting_with_generator) == 1


def test_headless_commit_records_generator_label_via_run_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source_file, ctx, kwargs, events = _loop_fixture(tmp_path, monkeypatch, [_mutant("Survived")])
    ctx = dataclasses.replace(ctx, generator_label="headless (some-model)")
    monkeypatch.setattr(loop, "dotnet_build", lambda targets, **k: True)
    monkeypatch.setattr(loop, "dotnet_test", lambda targets, flt, **k: True)
    clean = _write_report(tmp_path / "clean", "src/Widget.WebApi/PaymentService.cs", [])
    (tmp_path / "clean").mkdir(exist_ok=True)
    monkeypatch.setattr(loop, "run_scoped_stryker", lambda *a, **k: clean)

    loop.run_for_file(source_file, ctx, **kwargs)

    commit_msg = next(e[1] for e in events if e[0] == "commit")
    assert "Generator: headless (some-model)" in commit_msg


# =============================================================================
# Scenario: A non-improving round ends the file
# =============================================================================
def test_non_improving_round_ends_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # Round 1 (initial report) has 2 survivors; the scoped run for round 2
    # returns a report that still has 2 survivors — no improvement.
    source_file, ctx, kwargs, events = _loop_fixture(
        tmp_path, monkeypatch, [_mutant("Survived", line=1), _mutant("Survived", line=2)]
    )
    monkeypatch.setattr(loop, "dotnet_build", lambda targets, **k: True)
    monkeypatch.setattr(loop, "dotnet_test", lambda targets, flt, **k: True)

    stalled = _write_report(
        tmp_path / "r2",
        "src/Widget.WebApi/PaymentService.cs",
        [_mutant("Survived", line=1), _mutant("Survived", line=2)],
    )
    monkeypatch.setattr(loop, "run_scoped_stryker", lambda *a, **k: stalled)

    loop.run_for_file(source_file, ctx, **kwargs)

    # Exactly one commit (round 1); round 2 detected no improvement and stopped.
    commits = [e for e in events if e[0] == "commit"]
    assert len(commits) == 1


# =============================================================================
# Scenario: The round's log line uses the file-scoped score (Step 3.1, #1545)
# =============================================================================
def test_round_log_line_uses_file_scoped_score_for_single_file_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A single-file scoped report — round log score must match that file's
    own counts (existing behavior, must stay equivalent)."""
    logs: list[str] = []
    source_file, ctx, kwargs, _events = _loop_fixture(
        tmp_path,
        monkeypatch,
        [_mutant("Survived", line=1), _mutant("Killed", line=2)],
        log=logs.append,
    )
    monkeypatch.setattr(loop, "dotnet_build", lambda targets, **k: True)
    monkeypatch.setattr(loop, "dotnet_test", lambda targets, flt, **k: True)
    clean = _write_report(tmp_path / "clean", "src/Widget.WebApi/PaymentService.cs", [])
    (tmp_path / "clean").mkdir(exist_ok=True)
    monkeypatch.setattr(loop, "run_scoped_stryker", lambda *a, **k: clean)

    loop.run_for_file(source_file, ctx, **kwargs)

    round_1_log = next(m for m in logs if m.startswith("  round 1:"))
    # 1 killed, 1 survived => honest = 1/2 * 100 = 50.0%
    assert "honest=50.0%" in round_1_log
    assert "survivors=1" in round_1_log


def test_round_log_line_scopes_to_target_file_in_multi_file_baseline_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A multi-file report seeded via ``initial_report_path`` — the printed
    score must reflect only the target file's own counts, never the whole
    report's, across multiple rounds."""
    # Multi-file baseline report: the target file scores 50% (1 killed, 1
    # survived); another file in the same report scores far worse (0%). A
    # whole-report score would leak that worse number into the target's line.
    report_override = {
        "files": {
            "src/Widget.WebApi/PaymentService.cs": {
                "mutants": [_mutant("Killed", line=1), _mutant("Survived", line=2)]
            },
            "src/Widget.WebApi/OtherService.cs": {
                "mutants": [
                    _mutant("Survived", line=1),
                    _mutant("Survived", line=2),
                    _mutant("Survived", line=3),
                ]
            },
        }
    }
    logs: list[str] = []
    source_file, ctx, kwargs, _events = _loop_fixture(
        tmp_path, monkeypatch, report_override=report_override, log=logs.append
    )
    kwargs["max_rounds"] = 2
    monkeypatch.setattr(loop, "dotnet_build", lambda targets, **k: True)
    monkeypatch.setattr(loop, "dotnet_test", lambda targets, flt, **k: True)

    # Round 2's scoped run reports only the target file, at the same score —
    # exercising round 2+'s equivalence claim alongside round 1's baseline seed.
    round2_report = _write_report(
        tmp_path / "r2",
        "src/Widget.WebApi/PaymentService.cs",
        [_mutant("Killed", line=1), _mutant("Survived", line=2)],
    )
    monkeypatch.setattr(loop, "run_scoped_stryker", lambda *a, **k: round2_report)

    loop.run_for_file(source_file, ctx, **kwargs)

    round_logs = [m for m in logs if m.startswith("  round")]
    assert len(round_logs) == 2, "expected both round 1 (baseline) and round 2 (scoped) to log"
    for msg in round_logs:
        assert "honest=50.0%" in msg
        assert "survivors=1" in msg


# =============================================================================
# Scenario: A baseline-seeded round 1 with 0 survivors skips the scoped run
# entirely (#1545 core value scenario)
# =============================================================================
def test_baseline_seeded_zero_survivors_never_calls_scoped_stryker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """When the baseline report seeded via ``initial_report_path`` already
    shows 0 survivors for the target file, round 1 must converge immediately
    on that baseline data — ``run_scoped_stryker`` must never be invoked. This
    is the redundant-run this whole issue exists to avoid."""
    report_override = {
        "files": {
            "src/Widget.WebApi/PaymentService.cs": {
                "mutants": [_mutant("Killed", line=1), _mutant("Killed", line=2)]
            },
        }
    }
    logs: list[str] = []
    source_file, ctx, kwargs, events = _loop_fixture(
        tmp_path, monkeypatch, report_override=report_override, log=logs.append
    )
    monkeypatch.setattr(
        loop,
        "run_scoped_stryker",
        lambda *a, **k: pytest.fail(
            "run_scoped_stryker must not be called when the baseline already "
            "shows 0 survivors"
        ),
    )

    loop.run_for_file(source_file, ctx, **kwargs)

    assert any("no survivors" in msg for msg in logs)
    assert not any(e[0] in ("generate", "commit", "revert") for e in events)


# =============================================================================
# Scenario: A failed commit is a round failure, not a silent success (#1598)
# =============================================================================
def test_failed_commit_reverts_and_stops_the_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source_file, ctx, kwargs, events = _loop_fixture(
        tmp_path, monkeypatch, [_mutant("Survived")]
    )
    monkeypatch.setattr(loop, "dotnet_build", lambda targets, **k: True)
    monkeypatch.setattr(loop, "dotnet_test", lambda targets, flt, **k: True)
    monkeypatch.setattr(
        loop, "git_commit", lambda msg, tf, **k: events.append(("commit", msg)) or False
    )

    loop.run_for_file(source_file, ctx, **kwargs)

    kinds = [e[0] for e in events]
    # The commit was attempted, failed, and was NOT mistaken for success:
    # exactly one revert follows it, and the loop stops (a second "generate"
    # would mean it wrongly believed round 1 had landed).
    assert kinds.count("commit") == 1
    assert kinds.count("revert") == 1
    assert kinds.count("generate") == 1


def test_revert_failure_after_failed_commit_is_fatal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source_file, ctx, kwargs, _events = _loop_fixture(
        tmp_path, monkeypatch, [_mutant("Survived")]
    )
    monkeypatch.setattr(loop, "dotnet_build", lambda targets, **k: True)
    monkeypatch.setattr(loop, "dotnet_test", lambda targets, flt, **k: True)
    monkeypatch.setattr(loop, "git_commit", lambda msg, tf, **k: False)
    # The commit-failure revert path calls git_reset_and_revert, not plain
    # git_revert (#1598/#1584 review) — that's the function that must fail
    # here for this scenario.
    monkeypatch.setattr(loop, "git_reset_and_revert", lambda tf, **k: False)

    with pytest.raises(RuntimeError, match="revert failed"):
        loop.run_for_file(source_file, ctx, **kwargs)


def test_revert_failure_after_build_failure_is_fatal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source_file, ctx, kwargs, _events = _loop_fixture(
        tmp_path, monkeypatch, [_mutant("Survived")]
    )
    monkeypatch.setattr(loop, "dotnet_build", lambda targets, **k: False)
    monkeypatch.setattr(loop, "git_revert", lambda tf, **k: False)

    with pytest.raises(RuntimeError, match="revert failed"):
        loop.run_for_file(source_file, ctx, **kwargs)


def test_revert_failure_after_test_failure_is_fatal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source_file, ctx, kwargs, _events = _loop_fixture(
        tmp_path, monkeypatch, [_mutant("Survived")]
    )
    monkeypatch.setattr(loop, "dotnet_build", lambda targets, **k: True)
    monkeypatch.setattr(loop, "dotnet_test", lambda targets, flt, **k: False)
    monkeypatch.setattr(loop, "git_revert", lambda tf, **k: False)

    with pytest.raises(RuntimeError, match="revert failed"):
        loop.run_for_file(source_file, ctx, **kwargs)


# =============================================================================
# Scenario (real git, no mocks): git_reset_and_revert actually leaves both
# the index AND the working tree matching HEAD after a commit-failure-style
# staged mutation — the exact #1598 regression a fully-mocked test (like
# test_failed_commit_reverts_and_stops_the_round above) cannot catch, since
# mocking git_revert/git_commit never exercises real git index state.
# =============================================================================
def test_git_reset_and_revert_restores_index_and_worktree_after_a_staged_mutation(
    tmp_path: Path,
):
    git_hermetic(tmp_path, "init", "-q")
    git_hermetic(tmp_path, "config", "user.email", "test@example.com")
    git_hermetic(tmp_path, "config", "user.name", "Test")
    git_hermetic(tmp_path, "config", "commit.gpgsign", "false")

    test_file = tmp_path / "PaymentServiceTests.cs"
    original = "namespace Widget.Tests\n{\n    // original\n}\n"
    test_file.write_text(original, encoding="utf-8")
    git_hermetic(tmp_path, "add", "-A")
    git_hermetic(tmp_path, "commit", "-q", "-m", "initial")

    # Simulate what git_commit does before a commit attempt fails: the loop
    # mutates the test file, then `git add`s it.
    mutated = original.replace("// original", "// mutated (never actually committed)")
    test_file.write_text(mutated, encoding="utf-8")
    git_hermetic(tmp_path, "add", "--", str(test_file))

    # Sanity: the mutation IS staged before the fix runs — this is what makes
    # a plain `git checkout --` (git_revert alone) insufficient, and what
    # this test would fail to prove without this check.
    staged = git_hermetic(tmp_path, "diff", "--cached", "--name-only")
    assert "PaymentServiceTests.cs" in staged.stdout

    # env= is the point of this test: the SUT's own git subprocess must run
    # hermetically too, not just this test's setup calls above (#1598/#1584
    # review, round 3 — test-smell-review/ai-provenance-review found the
    # round-2 fix scrubbed only the setup calls).
    assert (
        loop.git_reset_and_revert(
            test_file, cwd=tmp_path, env=hermetic_git_env(home=tmp_path)
        )
        is True
    )

    # Working tree matches HEAD (not the staged mutation).
    assert test_file.read_text(encoding="utf-8") == original
    # Index matches HEAD too — nothing left staged.
    status = git_hermetic(tmp_path, "status", "--porcelain")
    assert status.stdout.strip() == ""


# =============================================================================
# Scenario: A refused/duplicate insertion stops the round before build/test/
# commit ever run — orchestration-level coverage (previously only exercised
# via mutation_kill_insert's own functions directly, #1584)
# =============================================================================
def test_refused_insertion_stops_the_round_without_verify_or_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source_file, ctx, kwargs, events = _loop_fixture(
        tmp_path, monkeypatch, [_mutant("Survived")]
    )
    monkeypatch.setattr(
        loop, "dotnet_build", lambda *a, **k: pytest.fail("must not build after a refused insert")
    )
    monkeypatch.setattr(
        loop,
        "apply_generated_methods",
        lambda *a, **k: mutation_kill_insert.InsertOutcome(
            False, "duplicate method names: ['Existing_Case_Works']"
        ),
    )

    loop.run_for_file(source_file, ctx, **kwargs)

    kinds = [e[0] for e in events]
    assert kinds == ["generate"]


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


# =============================================================================
# Verify/commit subprocess wiring — targets come from config (no literals)
# =============================================================================
def test_dotnet_build_uses_configured_test_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config = loop.load_loop_config(
        _write_config(tmp_path, test_projects=("test/Foo.Tests/Foo.Tests.csproj",))
    )
    seen: list = []

    class _R:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(
        loop.subprocess, "run", lambda argv, **k: seen.append(argv) or _R()
    )

    assert loop.dotnet_build(loop.dotnet_test_project_targets(config)) is True
    assert seen[0] == [
        "dotnet",
        "build",
        "test/Foo.Tests/Foo.Tests.csproj",
        "-c",
        "Debug",
        "--nologo",
    ]


# =============================================================================
# Scenario: A hung `dotnet build`/`dotnet test` is bounded by a timeout — it
# fails (and reverts) rather than hanging the loop forever (#1558)
# =============================================================================
def test_dotnet_build_passes_a_timeout(monkeypatch: pytest.MonkeyPatch):
    captured: dict = {}

    def fake_run(argv, **kwargs):
        captured.update(kwargs)

        class _R:
            returncode = 0

        return _R()

    monkeypatch.setattr(loop.subprocess, "run", fake_run)

    loop.dotnet_build(["test/Foo.Tests/Foo.Tests.csproj"])

    assert captured["timeout"] == loop.DOTNET_BUILD_TIMEOUT_S


def test_dotnet_build_timeout_is_treated_as_a_build_failure(
    monkeypatch: pytest.MonkeyPatch, capsys
):
    def fake_run(argv, **kwargs):
        raise loop.subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(loop.subprocess, "run", fake_run)

    assert loop.dotnet_build(["test/Foo.Tests/Foo.Tests.csproj"]) is False
    err = capsys.readouterr().err
    assert str(loop.DOTNET_BUILD_TIMEOUT_S) in err
    assert "DEV_TEAM_MUTATION_BUILD_TIMEOUT_S" in err


def test_dotnet_build_returns_false_on_nonzero_returncode(
    monkeypatch: pytest.MonkeyPatch
):
    """dotnet_build's own failure-path logic (a non-zero exit, no timeout
    involved) — direct coverage, not mocked away at the orchestration level
    (#1584)."""

    class _R:
        returncode = 1
        stdout = ""
        stderr = "error CS0000: something broke\n"

    monkeypatch.setattr(loop.subprocess, "run", lambda argv, **k: _R())

    assert loop.dotnet_build(["Foo.Tests.csproj"]) is False


def test_dotnet_test_returns_false_on_nonzero_returncode_even_with_zero_failed(
    monkeypatch: pytest.MonkeyPatch
):
    """A non-zero `dotnet test` exit fails the round even when the "Failed:"
    line itself parses to 0 (e.g. the process crashed before reporting) —
    direct coverage of dotnet_test's own failure-path logic (#1584)."""

    class _R:
        returncode = 1
        stdout = "Failed: 0, Passed: 5\n"
        stderr = ""

    monkeypatch.setattr(loop.subprocess, "run", lambda argv, **k: _R())

    assert loop.dotnet_test(["Foo.Tests.csproj"], "FooTests") is False


def test_dotnet_test_accumulates_failed_count_across_multiple_assemblies(
    monkeypatch: pytest.MonkeyPatch
):
    """A single `dotnet test` invocation spanning multiple test assemblies
    prints one "Failed: N" line per assembly. The scan must SUM them, not
    let a later, clean assembly's "Failed: 0" line overwrite an earlier
    assembly's real failures — a last-match-wins scan would falsely report
    success here (#1598). Fixture shape matches real `dotnet test` per-
    assembly summary lines (item 11, #1598/#1584 review), not a synthetic
    shorthand — see also the rollup-line non-double-count test below."""

    class _R:
        returncode = 0
        stdout = (
            "Failed!  - Failed:     3, Passed:     7, Skipped:     0, "
            "Total:    10, Duration: 120 ms - Bar.Tests.dll\n"
            "Passed!  - Failed:     0, Passed:    12, Skipped:     0, "
            "Total:    12, Duration: 40 ms - Foo.Tests.dll\n"
        )
        stderr = ""

    monkeypatch.setattr(loop.subprocess, "run", lambda argv, **k: _R())

    assert loop.dotnet_test(["Foo.Tests.csproj"], "FooTests") is False


def test_dotnet_test_trailing_lowercase_rollup_line_does_not_flip_a_clean_run(
    monkeypatch: pytest.MonkeyPatch
):
    """Newer `dotnet test` SDKs (7/8) also print a final, lowercase rollup
    line ("Test summary: total: ... failed: 0 ...") after the per-assembly
    summaries. The scan is capital-F "Failed:" only, so this rollup line
    must not be mistaken for a second, independent "Failed:" occurrence —
    a fully clean multi-assembly run (returncode 0, every real "Failed:"
    count is 0) must still report success (item 11, #1598/#1584 review)."""

    class _R:
        returncode = 0
        stdout = (
            "Passed!  - Failed:     0, Passed:    10, Skipped:     0, "
            "Total:    10, Duration: 40 ms - Foo.Tests.dll\n"
            "\n"
            "Test summary: total: 10, failed: 0, succeeded: 10, skipped: 0, "
            "duration: 0.1s\n"
        )
        stderr = ""

    monkeypatch.setattr(loop.subprocess, "run", lambda argv, **k: _R())

    assert loop.dotnet_test(["Foo.Tests.csproj"], "FooTests") is True


def test_sum_failed_counts_is_case_sensitive_not_double_counting_the_rollup_line():
    """A fixture where both a correct (case-sensitive) scan and a buggy
    (case-insensitive) scan sum to 0 can't actually catch a regression to
    ``re.IGNORECASE`` (#1598/#1584 review, item 12) — the boolean
    ``dotnet_test`` result would be identical either way. Asserting the
    NUMERIC total directly against a nonzero per-assembly count (3) plus a
    nonzero lowercase rollup count (3) proves the scan is case-sensitive:
    a case-insensitive regex would sum both `Failed:`-shaped occurrences
    (3 + 3 = 6); the correct, case-sensitive scan counts only the real
    capital-F per-assembly line (3)."""
    text = (
        "Failed!  - Failed:     3, Passed:     7, Skipped:     0, "
        "Total:    10, Duration: 120 ms - Bar.Tests.dll\n"
        "\n"
        "Test summary: total: 10, failed: 3, succeeded: 7, skipped: 0, "
        "duration: 0.1s\n"
    )

    assert loop._sum_failed_counts(text) == 3


def test_dotnet_test_passes_a_timeout(monkeypatch: pytest.MonkeyPatch):
    captured: dict = {}

    class _R:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(argv, **kwargs):
        captured.update(kwargs)
        return _R()

    monkeypatch.setattr(loop.subprocess, "run", fake_run)

    assert loop.dotnet_test(["test/Foo.Tests/Foo.Tests.csproj"], "FooTests") is True
    assert captured["timeout"] == loop.DOTNET_TEST_TIMEOUT_S


def test_dotnet_test_timeout_is_treated_as_a_test_failure(
    monkeypatch: pytest.MonkeyPatch, capsys
):
    def fake_run(argv, **kwargs):
        raise loop.subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(loop.subprocess, "run", fake_run)

    assert loop.dotnet_test(["test/Foo.Tests/Foo.Tests.csproj"], "FooTests") is False
    err = capsys.readouterr().err
    assert str(loop.DOTNET_TEST_TIMEOUT_S) in err
    assert "DEV_TEAM_MUTATION_TEST_TIMEOUT_S" in err


def test_git_revert_checks_out_only_the_test_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    seen: list = []
    monkeypatch.setattr(loop.subprocess, "run", lambda argv, **k: seen.append(argv))

    loop.git_revert(tmp_path / "PaymentServiceTests.cs")

    assert seen[0] == [
        "git",
        "--literal-pathspecs",
        "checkout",
        "--",
        str(tmp_path / "PaymentServiceTests.cs"),
    ]


# =============================================================================
# Scenario: A hung `git checkout`/`git add`/`git commit` is bounded by a
# timeout, not left to hang the loop forever (#1572 — same class of fix as
# #1558's dotnet_build/dotnet_test/Stryker timeouts).
# =============================================================================
def test_git_revert_passes_a_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    captured: dict = {}
    monkeypatch.setattr(loop.subprocess, "run", lambda argv, **k: captured.update(k))

    loop.git_revert(tmp_path / "PaymentServiceTests.cs")

    assert captured["timeout"] == loop.GIT_TIMEOUT_S


def test_git_revert_timeout_is_logged_not_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    def fake_run(argv, **kwargs):
        raise loop.subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(loop.subprocess, "run", fake_run)

    loop.git_revert(tmp_path / "PaymentServiceTests.cs")  # must not raise

    err = capsys.readouterr().err
    assert str(loop.GIT_TIMEOUT_S) in err
    assert "DEV_TEAM_MUTATION_GIT_TIMEOUT_S" in err
    # git_revert, git_commit's "add" leg, and git_commit's "commit" leg all
    # share GIT_TIMEOUT_S/DEV_TEAM_MUTATION_GIT_TIMEOUT_S — the operation_label text
    # is what distinguishes their timeout messages from one another.
    assert "git checkout" in err


def test_git_commit_passes_a_timeout_to_add_and_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calls: list = []

    class _R:
        returncode = 0

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return _R()

    monkeypatch.setattr(loop.subprocess, "run", fake_run)

    result = loop.git_commit("msg", tmp_path / "PaymentServiceTests.cs")

    assert result is True
    assert calls[0][0] == [
        "git",
        "--literal-pathspecs",
        "add",
        "--",
        str(tmp_path / "PaymentServiceTests.cs"),
    ]
    assert calls[0][1]["timeout"] == loop.GIT_TIMEOUT_S
    assert calls[1][0][:3] == ["git", "--literal-pathspecs", "commit"]
    assert calls[1][1]["timeout"] == loop.GIT_TIMEOUT_S


def test_git_commit_add_leg_timeout_returns_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    def fake_run(argv, **kwargs):
        raise loop.subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(loop.subprocess, "run", fake_run)

    assert loop.git_commit("msg", tmp_path / "PaymentServiceTests.cs") is False
    err = capsys.readouterr().err
    assert str(loop.GIT_TIMEOUT_S) in err
    assert "DEV_TEAM_MUTATION_GIT_TIMEOUT_S" in err
    assert "git add" in err


def test_git_commit_commit_leg_timeout_returns_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    """The `git add` leg succeeds; only the `git commit` leg's own
    _run_with_timeout call times out — a distinct branch from the add-leg
    timeout above, since git_commit short-circuits on add before ever
    reaching commit."""

    calls: list = []

    class _R:
        returncode = 0

    def fake_run(argv, **kwargs):
        calls.append(argv)
        if len(calls) == 1:
            return _R()
        raise loop.subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(loop.subprocess, "run", fake_run)

    assert loop.git_commit("msg", tmp_path / "PaymentServiceTests.cs") is False
    # Pin the branch this test targets by call order, not just count — a
    # future reordering of the add/commit calls should fail loudly here
    # rather than silently exercising the wrong leg.
    assert calls[0][:3] == ["git", "--literal-pathspecs", "add"]
    err = capsys.readouterr().err
    assert str(loop.GIT_TIMEOUT_S) in err
    assert "DEV_TEAM_MUTATION_GIT_TIMEOUT_S" in err
    assert "git commit" in err


def test_git_commit_scopes_the_commit_call_to_the_test_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """git commit -m message with no pathspec commits the WHOLE index, not
    just test_file — the commit call must carry the same `-- <path>`
    pathspec `git add` already uses (#1598)."""
    calls: list = []

    class _R:
        returncode = 0

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return _R()

    monkeypatch.setattr(loop.subprocess, "run", fake_run)

    result = loop.git_commit("msg", tmp_path / "PaymentServiceTests.cs")

    assert result is True
    assert calls[1] == [
        "git",
        "--literal-pathspecs",
        "commit",
        "-m",
        "msg",
        "--",
        str(tmp_path / "PaymentServiceTests.cs"),
    ]


def test_git_revert_returns_true_on_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    class _R:
        returncode = 0

    monkeypatch.setattr(loop.subprocess, "run", lambda argv, **k: _R())

    assert loop.git_revert(tmp_path / "PaymentServiceTests.cs") is True


def test_git_revert_returns_false_on_nonzero_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    class _R:
        returncode = 1

    monkeypatch.setattr(loop.subprocess, "run", lambda argv, **k: _R())

    assert loop.git_revert(tmp_path / "PaymentServiceTests.cs") is False


def test_git_revert_returns_false_on_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    def fake_run(argv, **kwargs):
        raise loop.subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(loop.subprocess, "run", fake_run)

    assert loop.git_revert(tmp_path / "PaymentServiceTests.cs") is False


def test_git_commit_proceeds_to_commit_after_a_non_timeout_add_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Pins the documented (not-changed-by-#1593) behavior: git_commit only
    inspects git add's timeout, not its returncode, so a non-timeout git add
    failure (e.g. bad pathspec) still falls through to attempting the
    commit."""

    calls: list = []

    class _R:
        def __init__(self, returncode):
            self.returncode = returncode

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return _R(returncode=1) if len(calls) == 1 else _R(returncode=0)

    monkeypatch.setattr(loop.subprocess, "run", fake_run)

    result = loop.git_commit("msg", tmp_path / "PaymentServiceTests.cs")

    assert result is True
    assert len(calls) == 2
    assert calls[1][:3] == ["git", "--literal-pathspecs", "commit"]


# =============================================================================
# Scenario: git_reset_and_revert's own internal failure branches — every
# other test either exercises the full real-git success path or mocks
# git_reset_and_revert away wholesale (#1598/#1584 review, item 10).
# =============================================================================
def test_git_reset_and_revert_returns_false_when_reset_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calls: list = []

    class _R:
        def __init__(self, returncode):
            self.returncode = returncode

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return _R(1)  # reset fails

    monkeypatch.setattr(loop.subprocess, "run", fake_run)

    assert loop.git_reset_and_revert(tmp_path / "PaymentServiceTests.cs") is False
    # Only the reset call happens — checkout (git_revert) is never reached.
    assert len(calls) == 1
    assert calls[0][:3] == ["git", "--literal-pathspecs", "reset"]


def test_git_reset_and_revert_returns_false_when_checkout_fails_after_reset_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calls: list = []

    class _R:
        def __init__(self, returncode):
            self.returncode = returncode

    def fake_run(argv, **kwargs):
        calls.append(argv)
        if argv[2] == "reset":
            return _R(0)  # reset succeeds
        return _R(1)  # checkout (git_revert) fails

    monkeypatch.setattr(loop.subprocess, "run", fake_run)

    assert loop.git_reset_and_revert(tmp_path / "PaymentServiceTests.cs") is False
    assert [c[2] for c in calls] == ["reset", "checkout"]


def test_git_reset_and_revert_returns_true_when_both_steps_succeed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    class _R:
        returncode = 0

    monkeypatch.setattr(loop.subprocess, "run", lambda argv, **k: _R())

    assert loop.git_reset_and_revert(tmp_path / "PaymentServiceTests.cs") is True


# =============================================================================
# Scenario: `python mutation_kill_loop.py --headless ...` — the real
# subprocess entry point stryker_shard_pipeline.py invokes by filename —
# dispatches to mutation_kill_headless.main() without double-loading this
# module (the sys.modules aliasing in the __main__ guard).
# =============================================================================
def test_script_invocation_dispatches_to_headless_main():
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "mutation_kill_loop.py"), "--file", "Foo.cs"],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 1
    assert mutation_kill_headless.NO_GENERATOR_MESSAGE in result.stderr


# =============================================================================
# Scenario: No module in the mutation_kill_loop split carries a repo-specific
# literal (#1562 split into three files — every one is checked).
# =============================================================================
def test_module_source_carries_no_repo_specific_literal():
    for mod, filename in (
        (loop, "mutation_kill_loop.py"),
        (mutation_kill_insert, "mutation_kill_insert.py"),
        (mutation_kill_headless, "mutation_kill_headless.py"),
    ):
        source = (SCRIPTS_DIR / filename).read_text(encoding="utf-8")
        present = [lit for lit in FORBIDDEN_LITERALS if lit in source]
        assert present == [], f"repo-specific literals leaked into {mod.__name__}: {present}"
