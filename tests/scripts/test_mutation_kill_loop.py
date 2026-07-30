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

# Ensure the module's dir is on the path so we can import it directly.
SCRIPTS_DIR = (
    Path(__file__).resolve().parents[2]
    / "plugins"
    / "dev-team"
    / "skills"
    / "mutation-testing"
    / "scripts"
)
sys.path.insert(0, str(SCRIPTS_DIR))

import mutation_kill_headless  # module-split literal check below
import mutation_kill_insert  # module-split literal check below
import mutation_kill_loop as loop

FORBIDDEN_LITERALS = ["Aci.Speedpay", "Controllers", "AwesomeAssertions", "Moq", "AutoFixture"]


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

    assert loop.dotnet_build_targets(config) == ["test/Foo.Tests/Foo.Tests.csproj"]
    assert loop.dotnet_test_targets(config) == ["test/Foo.Tests/Foo.Tests.csproj"]


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
    assert loop.dotnet_build_targets(config) == [
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

    monkeypatch.setattr(loop, "git_revert", lambda tf, **k: events.append(("revert", str(tf))))
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

    assert loop.dotnet_build(loop.dotnet_build_targets(config)) is True
    assert seen[0] == [
        "dotnet",
        "build",
        "test/Foo.Tests/Foo.Tests.csproj",
        "-c",
        "Debug",
        "--nologo",
    ]


def test_git_revert_checks_out_only_the_test_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    seen: list = []
    monkeypatch.setattr(loop.subprocess, "run", lambda argv, **k: seen.append(argv))

    loop.git_revert(tmp_path / "PaymentServiceTests.cs")

    assert seen[0] == [
        "git",
        "checkout",
        "--",
        str(tmp_path / "PaymentServiceTests.cs"),
    ]


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
