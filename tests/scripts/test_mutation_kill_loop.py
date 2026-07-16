"""Pytest tests for mutation_kill_loop.py — the config-driven survivor-kill
loop mechanics (Slice 2 of the ACI mutation-pipeline fold, #1136).

Each test maps to a Slice 2 Gherkin scenario in
``plans/generalize-aci-mutation-pipeline-fold-into-mutation-kill.md``. Every
dotnet / git / Stryker subprocess is mocked — no real .NET tooling runs — and
every project name is generic. Fixtures write a minimal ``stryker-config.json``
and a fixed ``mutation-report.json`` to a tmp_path repo so path derivation and
survivor extraction are exercised without a live mutation run.
"""

from __future__ import annotations

import json
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

import mutation_kill_loop as loop  # noqa: E402

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
        calls.append(("subprocess.run", argv))
        return None

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
    stryker_argv = next(c[1] for c in calls if c[0] == "subprocess.run")
    assert stryker_argv[0] == "dotnet-stryker"
    assert report_path == tmp_path / "out" / "reports" / "mutation-report.json"


# =============================================================================
# Scenario: Bare-CLI default mode with no generator fails fast at startup
# =============================================================================
def test_bare_cli_no_generator_fails_fast_at_startup(
    monkeypatch: pytest.MonkeyPatch, capsys
):
    # Guard: neither a scoped Stryker run nor any subprocess may fire.
    def explode(*a, **k):
        raise AssertionError("startup preflight must run before any subprocess")

    monkeypatch.setattr(loop, "run_scoped_stryker", explode)
    monkeypatch.setattr(loop.subprocess, "run", explode)

    rc = loop.main(["--config", "stryker-config.json", "--file", "PaymentService.cs"])

    assert rc != 0
    err = capsys.readouterr().err
    assert (
        "no test generator available — invoke via the mutation-kill agent "
        "or pass --headless"
    ) in err


def test_headless_flag_does_not_trip_the_no_generator_preflight(capsys):
    # --headless is accepted (Slice 3 wires it); it must NOT emit the
    # no-generator message. In Slice 2 it reports "not yet implemented".
    rc = loop.main(["--headless"])

    err = capsys.readouterr().err
    assert loop.NO_GENERATOR_MESSAGE not in err
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

    monkeypatch.setattr(loop.subprocess, "run", fake_run)

    generate = loop.make_headless_generator("some-test-model")
    survivors = [_mutant("Survived", "ArithmeticOperator", 10)]
    out = generate(
        "PaymentService.cs",
        survivors,
        "public class PaymentService {}",
        "public class PaymentServiceTests { }",
    )

    argv = captured["argv"]
    assert argv[0] == loop.CLAUDE_CLI
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
    assert loop.resolve_model() == "env-model"
    # An explicit --model wins over the env var.
    assert loop.resolve_model("flag-model") == "flag-model"


def test_model_resolves_to_none_when_env_unset(
    monkeypatch: pytest.MonkeyPatch,
):
    # No model snapshot id is pinned in source (cf. ADR 0008 / no-pinned-snapshots
    # guard); unresolved means None so `claude --print` uses its own default.
    monkeypatch.delenv("DEV_TEAM_MUTATION_MODEL", raising=False)
    assert loop.resolve_model() is None


def test_headless_omits_model_flag_when_unresolved(monkeypatch: pytest.MonkeyPatch):
    captured = {}

    class _R:
        returncode = 0
        stdout = "void New_Case() {}"
        stderr = ""

    def fake_run(argv, **k):
        captured["argv"] = argv
        return _R()

    monkeypatch.setattr(loop.subprocess, "run", fake_run)
    generate = loop.make_headless_generator(None)
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

    monkeypatch.setattr(loop.subprocess, "run", explode)
    monkeypatch.setattr(
        loop, "claude_cli_available", lambda: pytest.fail("must not probe the CLI")
    )

    rc = loop.main(["--config", "stryker-config.json", "--file", "Foo.cs"])

    assert rc != 0
    assert loop.NO_GENERATOR_MESSAGE in capsys.readouterr().err


# Scenario: Missing Claude CLI under headless fails cleanly and names the fix
def test_missing_claude_cli_under_headless_names_remediation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    monkeypatch.setattr(loop, "claude_cli_available", lambda: False)
    # No file may be mutated: run_for_file must never be reached.
    monkeypatch.setattr(
        loop, "run_for_file", lambda *a, **k: pytest.fail("must not run — CLI missing")
    )

    rc = loop.main(
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

    monkeypatch.setattr(loop.subprocess, "run", lambda *a, **k: _OK())
    assert loop.claude_cli_available() is True

    def _missing(*a, **k):
        raise FileNotFoundError("claude")

    monkeypatch.setattr(loop.subprocess, "run", _missing)
    assert loop.claude_cli_available() is False


# =============================================================================
# Insert-mechanics fixtures
# =============================================================================
_BLOCK_NAMESPACE_CLASS = (
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
)

_FILE_SCOPED_CLASS = (
    "namespace Widget.Tests;\n"
    "\n"
    "public class PaymentServiceTests\n"
    "{\n"
    "    [Test]\n"
    "    public async Task Existing_Case_Works()\n"
    "    {\n"
    "    }\n"
    "}\n"
)

_NEW_METHOD = (
    "        [Test]\n"
    "        public async Task New_Case_KillsMutant()\n"
    "        {\n"
    "        }\n"
)


# =============================================================================
# Scenario: Duplicate method names abort insertion
# =============================================================================
def test_duplicate_method_names_abort_insertion(tmp_path: Path):
    test_file = tmp_path / "PaymentServiceTests.cs"
    test_file.write_text(_BLOCK_NAMESPACE_CLASS, encoding="utf-8")
    before = test_file.read_text(encoding="utf-8")

    dup_block = (
        "        [Test]\n"
        "        public async Task Existing_Case_Works()\n"
        "        {\n"
        "        }\n"
    )

    outcome = loop.apply_generated_methods(test_file, dup_block)

    assert outcome.inserted is False
    assert "duplicate" in outcome.reason.lower()
    # File is unchanged.
    assert test_file.read_text(encoding="utf-8") == before


def test_detect_duplicate_methods_reports_only_collisions():
    dupes = loop.detect_duplicate_methods(
        _BLOCK_NAMESPACE_CLASS,
        "public async Task Existing_Case_Works() {}\n"
        "public async Task Brand_New_Case() {}\n",
    )
    assert dupes == ["Existing_Case_Works"]


# =============================================================================
# Scenario: Generated methods are inserted before the class-closing brace
# =============================================================================
def test_methods_inserted_before_class_closing_brace(tmp_path: Path):
    test_file = tmp_path / "PaymentServiceTests.cs"
    test_file.write_text(_BLOCK_NAMESPACE_CLASS, encoding="utf-8")

    outcome = loop.apply_generated_methods(test_file, _NEW_METHOD)

    assert outcome.inserted is True
    lines = test_file.read_text(encoding="utf-8").splitlines()
    new_idx = next(i for i, l in enumerate(lines) if "New_Case_KillsMutant" in l)
    # The class-close ("    }") and namespace-close ("}") follow the new method.
    class_close_idx = next(
        i for i in range(new_idx + 1, len(lines)) if lines[i].rstrip("\r\n") == "    }"
    )
    ns_close_idx = next(
        i for i in range(class_close_idx + 1, len(lines)) if lines[i].strip() == "}"
    )
    assert new_idx < class_close_idx < ns_close_idx


# =============================================================================
# Scenario: Insertion into a file-scoped-namespace class is handled or refused
# =============================================================================
def test_file_scoped_namespace_is_refused_not_corrupted(tmp_path: Path):
    test_file = tmp_path / "PaymentServiceTests.cs"
    test_file.write_text(_FILE_SCOPED_CLASS, encoding="utf-8")
    before = test_file.read_text(encoding="utf-8")

    with pytest.raises(loop.InsertionRefused) as exc:
        loop.insert_before_class_close(test_file, _NEW_METHOD)

    assert "file-scoped" in str(exc.value).lower()
    # Never silently appended — file is byte-for-byte unchanged.
    assert test_file.read_text(encoding="utf-8") == before


def test_non_four_space_indent_is_refused(tmp_path: Path):
    # Block namespace but the class body is tab-indented — the 4-space
    # class-close heuristic must refuse rather than mis-insert.
    tabbed = (
        "namespace Widget.Tests\n"
        "{\n"
        "\tpublic class PaymentServiceTests\n"
        "\t{\n"
        "\t}\n"
        "}\n"
    )
    test_file = tmp_path / "PaymentServiceTests.cs"
    test_file.write_text(tabbed, encoding="utf-8")
    before = test_file.read_text(encoding="utf-8")

    with pytest.raises(loop.InsertionRefused):
        loop.insert_before_class_close(test_file, _NEW_METHOD)

    assert test_file.read_text(encoding="utf-8") == before


def test_apply_wraps_refusal_as_outcome_without_writing(tmp_path: Path):
    test_file = tmp_path / "PaymentServiceTests.cs"
    test_file.write_text(_FILE_SCOPED_CLASS, encoding="utf-8")
    before = test_file.read_text(encoding="utf-8")

    outcome = loop.apply_generated_methods(test_file, _NEW_METHOD)

    assert outcome.inserted is False
    assert "file-scoped" in outcome.reason.lower()
    assert test_file.read_text(encoding="utf-8") == before


# =============================================================================
# run_for_file harness — mocks every dotnet / git / Stryker touch.
# =============================================================================
def _loop_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutants):
    """Wire a run_for_file invocation with a fixed initial report and a
    generator that records its calls. Returns (kwargs, events)."""
    config = loop.load_loop_config(_write_config(tmp_path))
    test_file = tmp_path / "PaymentServiceTests.cs"
    test_file.write_text(_BLOCK_NAMESPACE_CLASS, encoding="utf-8")
    source_path = tmp_path / "PaymentService.cs"
    source_path.write_text("public class PaymentService {}\n", encoding="utf-8")
    report = _write_report(tmp_path, "src/Widget.WebApi/PaymentService.cs", mutants)

    events: list = []

    def generator(src, survivors, src_text, test_text):
        events.append(("generate", len(survivors)))
        return _NEW_METHOD

    monkeypatch.setattr(loop, "git_revert", lambda tf, **k: events.append(("revert", str(tf))))
    monkeypatch.setattr(
        loop, "git_commit", lambda msg, tf, **k: events.append(("commit", msg)) or True
    )

    kwargs = dict(
        source_file="PaymentService.cs",
        config=config,
        test_file=test_file,
        source_path=source_path,
        output_dir=tmp_path / "out",
        generate=generator,
        initial_report_path=report,
        max_rounds=3,
        log=lambda m: None,
    )
    return kwargs, events


# =============================================================================
# Scenario: A build failure after insertion is reverted
# =============================================================================
def test_build_failure_after_insertion_is_reverted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    kwargs, events = _loop_fixture(tmp_path, monkeypatch, [_mutant("Survived")])
    monkeypatch.setattr(loop, "dotnet_build", lambda targets, **k: False)
    monkeypatch.setattr(
        loop, "dotnet_test", lambda *a, **k: pytest.fail("test must not run after build fail")
    )

    loop.run_for_file(**kwargs)

    kinds = [e[0] for e in events]
    assert "revert" in kinds
    assert "commit" not in kinds


# =============================================================================
# Scenario: A test failure after insertion is reverted
# =============================================================================
def test_test_failure_after_insertion_is_reverted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    kwargs, events = _loop_fixture(tmp_path, monkeypatch, [_mutant("Survived")])
    monkeypatch.setattr(loop, "dotnet_build", lambda targets, **k: True)
    monkeypatch.setattr(loop, "dotnet_test", lambda targets, flt, **k: False)

    loop.run_for_file(**kwargs)

    kinds = [e[0] for e in events]
    assert "revert" in kinds
    assert "commit" not in kinds


# =============================================================================
# Green round commits (baseline for the revert scenarios above)
# =============================================================================
def test_green_round_commits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    kwargs, events = _loop_fixture(tmp_path, monkeypatch, [_mutant("Survived")])
    monkeypatch.setattr(loop, "dotnet_build", lambda targets, **k: True)
    monkeypatch.setattr(loop, "dotnet_test", lambda targets, flt, **k: True)
    # Second round: scoped run returns a clean report so the loop stops "done".
    clean = _write_report(tmp_path / "clean", "src/Widget.WebApi/PaymentService.cs", [])
    (tmp_path / "clean").mkdir(exist_ok=True)
    monkeypatch.setattr(loop, "run_scoped_stryker", lambda *a, **k: clean)

    loop.run_for_file(**kwargs)

    kinds = [e[0] for e in events]
    assert "commit" in kinds
    assert "revert" not in kinds


# =============================================================================
# Scenario: A non-improving round ends the file
# =============================================================================
def test_non_improving_round_ends_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # Round 1 (initial report) has 2 survivors; the scoped run for round 2
    # returns a report that still has 2 survivors — no improvement.
    kwargs, events = _loop_fixture(
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

    loop.run_for_file(**kwargs)

    # Exactly one commit (round 1); round 2 detected no improvement and stopped.
    commits = [e for e in events if e[0] == "commit"]
    assert len(commits) == 1


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
# Scenario: The module carries no repo-specific literal
# =============================================================================
def test_module_source_carries_no_repo_specific_literal():
    source = (SCRIPTS_DIR / "mutation_kill_loop.py").read_text(encoding="utf-8")

    present = [lit for lit in FORBIDDEN_LITERALS if lit in source]
    assert present == [], f"repo-specific literals leaked into module: {present}"
