"""Pytest tests for mutation_nightwatch.py / mutation_nightwatch_stacks.py —
the unattended, LLM-free overnight mutation night-watch runner (#1754).

Every subprocess boundary (npm/npx/mutmut/dotnet/caffeinate/systemd-inhibit/
the C# wrapper script) is mocked or dependency-injected — this suite never
shells to a real mutation tool. It asserts the orchestration, detection,
report-writing, sleep-inhibition selection, and detach mechanics in
isolation.

Monkeypatches target the module that actually defines the patched name (not
whichever module happens to import it) so patches take effect — detection/
repair/measurement live in ``mutation_nightwatch_stacks`` (imported as
``stacks_lib``, matching production's own import alias); orchestration
(``SleepInhibitor``, the report writer, ``--detach``, the CLI) lives in
``mutation_nightwatch`` (``nightwatch``). Same rule
``test_mutation_kill_headless.py`` documents for its own module split.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from _mutation_test_helpers import SCRIPTS_DIR

sys.path.insert(0, str(SCRIPTS_DIR))

import mutation_nightwatch as nightwatch
import mutation_nightwatch_stacks as stacks_lib
import mutation_report

# =============================================================================
# Stack detection
# =============================================================================


def test_detect_javascript_via_stryker_devdependency(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"devDependencies": {"@stryker-mutator/core": "^8.0.0"}}),
        encoding="utf-8",
    )
    assert stacks_lib._detect_javascript(tmp_path) is True


def test_detect_javascript_via_stryker_conf_file(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(json.dumps({}), encoding="utf-8")
    (tmp_path / "stryker.conf.json").write_text("{}", encoding="utf-8")
    assert stacks_lib._detect_javascript(tmp_path) is True


def test_detect_javascript_absent_without_package_json(tmp_path: Path) -> None:
    assert stacks_lib._detect_javascript(tmp_path) is False


def test_detect_javascript_tolerates_malformed_package_json(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("not json", encoding="utf-8")
    assert stacks_lib._detect_javascript(tmp_path) is False


def test_detect_python_via_requirements_dev(tmp_path: Path) -> None:
    (tmp_path / "requirements-dev.txt").write_text("mutmut<3\npytest\n", encoding="utf-8")
    assert stacks_lib._detect_python(tmp_path) is True


def test_detect_python_absent(tmp_path: Path) -> None:
    (tmp_path / "requirements-dev.txt").write_text("pytest\n", encoding="utf-8")
    assert stacks_lib._detect_python(tmp_path) is False


def test_detect_csharp_via_tool_manifest(tmp_path: Path) -> None:
    config_dir = tmp_path / ".config"
    config_dir.mkdir()
    (config_dir / "dotnet-tools.json").write_text(
        json.dumps({"tools": {"dotnet-stryker": {"version": "4.0.0"}}}),
        encoding="utf-8",
    )
    assert stacks_lib._detect_csharp(tmp_path) is True


def test_detect_csharp_absent_without_manifest(tmp_path: Path) -> None:
    assert stacks_lib._detect_csharp(tmp_path) is False


def test_detect_java_via_pom_xml(tmp_path: Path) -> None:
    (tmp_path / "pom.xml").write_text("<project><plugin>pitest</plugin></project>", encoding="utf-8")
    assert stacks_lib._detect_java(tmp_path) is True


def test_detect_go_via_go_mod(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module example.com/foo\n", encoding="utf-8")
    assert stacks_lib._detect_go(tmp_path) is True


def test_detect_stacks_returns_every_known_stack(tmp_path: Path) -> None:
    detected = stacks_lib.detect_stacks(tmp_path)
    assert detected == {
        "javascript": False,
        "python": False,
        "csharp": False,
        "java": False,
        "go": False,
    }


def test_supported_stacks_excludes_unscored_ecosystems() -> None:
    # pitest/go-mutesting have no mutation_report.py parser yet — detected,
    # never guessed at.
    assert stacks_lib.SUPPORTED_STACKS == {"javascript", "python", "csharp"}
    assert "java" not in stacks_lib.SUPPORTED_STACKS
    assert "go" not in stacks_lib.SUPPORTED_STACKS


# =============================================================================
# Mechanical repair — package-pin sync only, never code
# =============================================================================


def test_mechanical_repair_runs_npm_ci_when_node_modules_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []

    def fake_run_logged(cmd, cwd, log_path, *, timeout=None):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(stacks_lib, "_run_logged", fake_run_logged)
    note = stacks_lib.mechanical_repair("javascript", tmp_path, tmp_path)
    assert calls == [["npm", "ci"]]
    assert note == "npm ci: package-pin sync OK"


def test_mechanical_repair_skips_npm_ci_when_node_modules_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "node_modules").mkdir()
    monkeypatch.setattr(
        stacks_lib,
        "_run_logged",
        lambda *a, **k: pytest.fail("must not run npm ci when node_modules exists"),
    )
    assert stacks_lib.mechanical_repair("javascript", tmp_path, tmp_path) is None


def test_mechanical_repair_reports_note_on_npm_ci_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        stacks_lib, "_run_logged", lambda cmd, cwd, log_path, **k: subprocess.CompletedProcess(cmd, 1)
    )
    note = stacks_lib.mechanical_repair("javascript", tmp_path, tmp_path)
    assert note is not None
    assert "npm ci" in note and "failed" in note


def test_mechanical_repair_runs_dotnet_restore_for_csharp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []

    def fake_run_logged(cmd, cwd, log_path, *, timeout=None):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(stacks_lib, "_run_logged", fake_run_logged)
    note = stacks_lib.mechanical_repair("csharp", tmp_path, tmp_path)
    assert calls == [["dotnet", "restore"]]
    assert note == "dotnet restore: package-pin sync OK"


def test_mechanical_repair_no_step_for_python() -> None:
    assert stacks_lib.mechanical_repair("python", Path("."), Path(".")) is None


def test_mechanical_repair_missing_binary_reports_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(stacks_lib, "_run_logged", lambda *a, **k: None)
    note = stacks_lib.mechanical_repair("javascript", tmp_path, tmp_path)
    assert note is not None and "failed" in note


# =============================================================================
# Per-stack measurement
# =============================================================================


def _write_stryker_report(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "files": {
                    "src/calculator.ts": {
                        "mutants": [
                            {
                                "id": "1",
                                "mutatorName": "ConditionalBoundary",
                                "status": "Survived",
                                "location": {"start": {"line": 42}},
                                "replacement": "x >= 0",
                            },
                            {"id": "2", "mutatorName": "ArithmeticOperator", "status": "Killed"},
                        ]
                    }
                }
            }
        ),
        encoding="utf-8",
    )


def test_measure_javascript_scores_the_written_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        stacks_lib, "_run_logged", lambda cmd, cwd, log_path, **k: subprocess.CompletedProcess(cmd, 1)
    )
    _write_stryker_report(tmp_path / "reports" / "mutation" / "mutation.json")
    result = stacks_lib.measure_javascript(tmp_path, tmp_path)
    assert result.status == "measured"
    assert result.summary is not None
    assert result.summary.killed == 1
    assert result.summary.survived == 1
    assert result.survivors == [
        {
            "stack": "javascript",
            "module": "javascript",
            "file": "src/calculator.ts",
            "line": 42,
            "mutator": "ConditionalBoundary",
            "change": "x >= 0",
            "status": "survived",
        }
    ]


def test_measure_javascript_errors_when_report_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        stacks_lib, "_run_logged", lambda cmd, cwd, log_path, **k: subprocess.CompletedProcess(cmd, 0)
    )
    result = stacks_lib.measure_javascript(tmp_path, tmp_path)
    assert result.status == "error"
    assert result.summary is None


def test_measure_javascript_errors_when_tool_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(stacks_lib, "_run_logged", lambda *a, **k: None)
    result = stacks_lib.measure_javascript(tmp_path, tmp_path)
    assert result.status == "error"


def test_measure_python_parses_mutmut_junitxml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    junit_xml = """<?xml version="1.0"?>
<testsuite>
  <testcase name="mut1" file="calc.py" line="10">
    <failure message="bad_survived"/>
  </testcase>
  <testcase name="mut2" file="calc.py" line="20"/>
</testsuite>"""

    monkeypatch.setattr(
        stacks_lib, "_run_logged", lambda cmd, cwd, log_path, **k: subprocess.CompletedProcess(cmd, 1)
    )
    monkeypatch.setattr(
        stacks_lib.subprocess,
        "run",
        lambda cmd, **k: subprocess.CompletedProcess(cmd, 0, stdout=junit_xml, stderr=""),
    )
    result = stacks_lib.measure_python(tmp_path, tmp_path)
    assert result.status == "measured"
    assert result.summary.killed == 1
    assert result.summary.survived == 1
    assert result.survivors[0]["file"] == "calc.py"
    assert result.survivors[0]["status"] == "survived"


def test_measure_python_errors_when_run_does_not_execute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(stacks_lib, "_run_logged", lambda *a, **k: None)
    result = stacks_lib.measure_python(tmp_path, tmp_path)
    assert result.status == "error"


def test_measure_csharp_skips_without_unique_sln(tmp_path: Path) -> None:
    result = stacks_lib.measure_csharp(tmp_path, tmp_path)
    assert result.status == "skipped"
    assert "sln" in result.detail


def test_measure_csharp_skips_without_stryker_config(tmp_path: Path) -> None:
    (tmp_path / "App.sln").write_text("", encoding="utf-8")
    result = stacks_lib.measure_csharp(tmp_path, tmp_path)
    assert result.status == "skipped"
    assert "stryker-config.json" in result.detail


def test_measure_csharp_scores_the_written_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "App.sln").write_text("", encoding="utf-8")
    (tmp_path / "stryker-config.json").write_text("{}", encoding="utf-8")

    def fake_run_logged(cmd, cwd, log_path, **k):
        assert "--sln" in cmd and "App.sln" in cmd
        report_path = (
            tmp_path
            / "reports"
            / "mutation-nightwatch"
            / "run"
            / "csharp"
            / "reports"
            / "mutation-report.json"
        )
        _write_stryker_report(report_path)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(stacks_lib, "_run_logged", fake_run_logged)
    run_dir = tmp_path / "reports" / "mutation-nightwatch" / "run"
    result = stacks_lib.measure_csharp(tmp_path, run_dir)
    assert result.status == "measured"
    assert result.summary.killed == 1


# =============================================================================
# SleepInhibitor
# =============================================================================


def test_sleep_inhibitor_uses_caffeinate_on_macos() -> None:
    popen_calls = []

    class FakeProc:
        def terminate(self):
            pass

        def wait(self, timeout=None):
            pass

    def fake_popen(cmd, **kwargs):
        popen_calls.append(cmd)
        return FakeProc()

    inhibitor = nightwatch.SleepInhibitor(
        system_name="Darwin", which=lambda name: "/usr/bin/caffeinate", popen=fake_popen
    )
    with inhibitor:
        assert inhibitor.method == "caffeinate"
        assert inhibitor.note is None
    assert popen_calls == [["caffeinate", "-dims"]]


def test_sleep_inhibitor_uses_systemd_inhibit_on_linux() -> None:
    class FakeProc:
        def terminate(self):
            pass

        def wait(self, timeout=None):
            pass

    inhibitor = nightwatch.SleepInhibitor(
        system_name="Linux",
        which=lambda name: "/usr/bin/systemd-inhibit",
        popen=lambda cmd, **k: FakeProc(),
    )
    with inhibitor:
        assert inhibitor.method == "systemd-inhibit"


def test_sleep_inhibitor_notes_when_nothing_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inhibitor = nightwatch.SleepInhibitor(system_name="Darwin", which=lambda name: None)
    with inhibitor:
        assert inhibitor.method is None
        assert inhibitor.note is not None
        assert "NOTE" in inhibitor.note


def test_sleep_inhibitor_windows_calls_set_thread_execution_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    class FakeKernel32:
        def SetThreadExecutionState(self, flags):
            calls.append(flags)

    class FakeWindll:
        kernel32 = FakeKernel32()

    monkeypatch.setattr(nightwatch.ctypes, "windll", FakeWindll(), raising=False)
    inhibitor = nightwatch.SleepInhibitor(system_name="Windows")
    with inhibitor:
        assert inhibitor.method == "SetThreadExecutionState"
    assert len(calls) == 2  # one on enter (with ES_SYSTEM_REQUIRED), one on exit (reset)


def test_sleep_inhibitor_unknown_platform_without_tools_notes() -> None:
    inhibitor = nightwatch.SleepInhibitor(system_name="Plan9", which=lambda name: None)
    with inhibitor:
        assert inhibitor.note is not None


# =============================================================================
# Report writer
# =============================================================================


def test_write_reports_mirrors_into_latest_dir(tmp_path: Path) -> None:
    run_dir = tmp_path / "20260804T000000Z"
    latest_dir = tmp_path / "LATEST"
    results = [
        stacks_lib.StackResult(
            "javascript",
            "stryker",
            "measured",
            summary=mutation_report.ScoreSummary(
                killed=1, survived=1, timeout=0, no_coverage=0, honest_score=50.0, reported_score=50.0
            ),
            survivors=[
                {
                    "stack": "javascript",
                    "module": "javascript",
                    "file": "a.ts",
                    "line": 1,
                    "mutator": "X",
                    "change": "y",
                    "status": "survived",
                }
            ],
        )
    ]
    nightwatch.write_reports(run_dir, latest_dir, results, "2026-08-04T00:00:00Z", [])

    for target in (run_dir, latest_dir):
        summary = (target / "MORNING-SUMMARY.md").read_text(encoding="utf-8")
        assert "javascript" in summary
        assert "50.0%" in summary
        survivors = json.loads((target / "SURVIVORS.json").read_text(encoding="utf-8"))
        assert survivors["schema_version"] == 1
        assert len(survivors["survivors"]) == 1

    assert (run_dir / "MORNING-SUMMARY.md").read_text(encoding="utf-8") == (
        latest_dir / "MORNING-SUMMARY.md"
    ).read_text(encoding="utf-8")


def test_write_reports_includes_notes_and_no_survivor_message(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    latest_dir = tmp_path / "LATEST"
    nightwatch.write_reports(
        run_dir, latest_dir, [], "2026-08-04T00:00:00Z", ["NOTE: sleep inhibition unavailable"]
    )
    summary = (run_dir / "MORNING-SUMMARY.md").read_text(encoding="utf-8")
    assert "NOTE: sleep inhibition unavailable" in summary
    assert "No surviving mutants captured this run." in summary


# =============================================================================
# Orchestration
# =============================================================================


def test_run_nightwatch_skips_unsupported_detected_stack(tmp_path: Path) -> None:
    (tmp_path / "pom.xml").write_text("<plugin>pitest</plugin>", encoding="utf-8")
    output_dir = tmp_path / "reports" / "mutation-nightwatch"

    run_dir = nightwatch.run_nightwatch(
        tmp_path,
        output_dir,
        stacks=["java"],
        inhibit_sleep=False,
        started_at="2026-08-04T03:00:00Z",
    )

    survivors = json.loads((run_dir / "SURVIVORS.json").read_text(encoding="utf-8"))
    assert survivors["survivors"] == []
    summary = (run_dir / "MORNING-SUMMARY.md").read_text(encoding="utf-8")
    assert "skipped_no_parser" in summary


def test_run_nightwatch_runs_supported_stacks_and_writes_latest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "reports" / "mutation-nightwatch"
    called = []

    def fake_measure(repo_root, run_dir, *, timeout=None):
        called.append("javascript")
        return stacks_lib.StackResult("javascript", "stryker", "measured")

    monkeypatch.setitem(stacks_lib.MEASURERS, "javascript", fake_measure)
    monkeypatch.setattr(stacks_lib, "mechanical_repair", lambda *a, **k: None)

    run_dir = nightwatch.run_nightwatch(
        tmp_path,
        output_dir,
        stacks=["javascript"],
        inhibit_sleep=False,
        started_at="2026-08-04T03:00:00Z",
    )

    assert called == ["javascript"]
    assert (output_dir / "LATEST" / "MORNING-SUMMARY.md").exists()
    assert run_dir.name == "20260804T030000Z"


def test_run_nightwatch_autodetects_when_stacks_not_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"devDependencies": {"@stryker-mutator/core": "^8.0.0"}}), encoding="utf-8"
    )
    monkeypatch.setattr(
        stacks_lib,
        "MEASURERS",
        {
            "javascript": lambda repo_root, run_dir, **k: stacks_lib.StackResult(
                "javascript", "stryker", "measured"
            )
        },
    )
    monkeypatch.setattr(stacks_lib, "mechanical_repair", lambda *a, **k: None)

    run_dir = nightwatch.run_nightwatch(
        tmp_path,
        tmp_path / "out",
        inhibit_sleep=False,
        started_at="2026-08-04T03:00:00Z",
    )
    survivors_json = json.loads((run_dir / "SURVIVORS.json").read_text(encoding="utf-8"))
    assert survivors_json["survivors"] == []


# =============================================================================
# --detach
# =============================================================================


def test_relaunch_detached_strips_detach_flag_and_uses_start_new_session(
    tmp_path: Path,
) -> None:
    captured = {}

    class FakeProc:
        pid = 4321

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return FakeProc()

    log_path = tmp_path / "detached-launch.log"
    pid = nightwatch.relaunch_detached(["--detach", "--repo-root", "."], log_path, popen=fake_popen)

    assert pid == 4321
    assert "--detach" not in captured["cmd"]
    assert "--repo-root" in captured["cmd"]
    if __import__("os").name == "posix":
        assert captured["kwargs"].get("start_new_session") is True
    else:
        assert captured["kwargs"].get("creationflags") == 0x00000008


# =============================================================================
# CLI
# =============================================================================


def test_parse_args_defaults() -> None:
    args = nightwatch.parse_args([])
    assert args.repo_root == "."
    assert args.output_dir == nightwatch.DEFAULT_OUTPUT_DIR
    assert args.detach is False
    assert args.stacks is None
    assert args.no_sleep_inhibit is False


def test_parse_args_stacks_override() -> None:
    args = nightwatch.parse_args(["--stacks", "javascript,python"])
    assert args.stacks == "javascript,python"


def test_main_detach_path_calls_relaunch_and_returns_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setattr(nightwatch, "relaunch_detached", lambda argv, log_path, **k: 999)
    rc = nightwatch.main(["--detach", "--repo-root", str(tmp_path)])
    assert rc == 0
    assert "999" in capsys.readouterr().out


def test_main_runs_nightwatch_and_returns_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setattr(
        nightwatch, "run_nightwatch", lambda repo_root, output_dir, **k: tmp_path / "run"
    )
    rc = nightwatch.main(["--repo-root", str(tmp_path), "--no-sleep-inhibit"])
    assert rc == 0
    assert "run complete" in capsys.readouterr().out
