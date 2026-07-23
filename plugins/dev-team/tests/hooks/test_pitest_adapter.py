"""Tests for the pitest (Java/Kotlin) adapter — `mutation_adapters.pitest`.

The module was previously untested. These pin the real behaviour of the pure
helpers (report path, class-name derivation, Maven-module detection, gradle
detection, source-file predicate, -Dtest extraction), pitest_detect's build-file
probes, pitest_parse's XML + surefire-stdout zero-kill derivation, pitest_run's
argv construction and its timeout / no-report advisory branches, and main()'s
argument handling. Every assertion checks a specific value, not just a return
code.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
_PLUGIN_ROOT = _REPO_ROOT / "plugins" / "dev-team"
sys.path.insert(0, str(_PLUGIN_ROOT / "hooks"))

from mutation_adapters import pitest as pt  # noqa: E402


# ---------------------------------------------------------------------------
# _report_path() — default vs env override
# ---------------------------------------------------------------------------


def test_report_path_uses_documented_default(monkeypatch) -> None:
    monkeypatch.delenv("PITEST_REPORT", raising=False)
    assert pt._report_path() == pt.Path("target/pit-reports/mutations.xml")


def test_report_path_honors_env_override(monkeypatch) -> None:
    monkeypatch.setenv("PITEST_REPORT", "custom/pit.xml")
    assert pt._report_path() == pt.Path("custom/pit.xml")


# ---------------------------------------------------------------------------
# pitest_detect() — pom.xml / build.gradle / build.gradle.kts probes
# ---------------------------------------------------------------------------


def test_detect_true_when_pom_declares_pitest(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pom.xml").write_text("<plugin>pitest-maven</plugin>")
    assert pt.pitest_detect() is True


def test_detect_true_when_build_gradle_declares_pitest(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "build.gradle").write_text("id 'info.solidsoft.pitest'")
    assert pt.pitest_detect() is True


def test_detect_true_when_build_gradle_kts_declares_pitest(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "build.gradle.kts").write_text('id("info.solidsoft.pitest")')
    assert pt.pitest_detect() is True


def test_detect_false_when_pom_lacks_pitest(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pom.xml").write_text("<project>no mutation plugin here</project>")
    assert pt.pitest_detect() is False


def test_detect_false_advisory_names_setup_and_plugins(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    assert pt.pitest_detect() is False
    out = capsys.readouterr().out
    assert "pitest not found" in out
    assert "Run /setup to" in out
    assert "pitest-maven plugin to pom.xml" in out


# ---------------------------------------------------------------------------
# _java_class_from_file() — path → dotted class name
# ---------------------------------------------------------------------------


def test_java_class_from_maven_java_layout() -> None:
    assert (
        pt._java_class_from_file("src/main/java/com/example/Calculator.java")
        == "com.example.Calculator"
    )


def test_java_class_from_kotlin_layout() -> None:
    assert (
        pt._java_class_from_file("src/main/kotlin/com/example/Calc.kt")
        == "com.example.Calc"
    )


def test_java_class_strips_groovy_extension() -> None:
    assert (
        pt._java_class_from_file("src/main/groovy/com/example/Calc.groovy")
        == "com.example.Calc"
    )


def test_java_class_strips_scala_extension() -> None:
    assert pt._java_class_from_file("src/Calc.scala") == "Calc"


def test_java_class_empty_input_returns_empty() -> None:
    assert pt._java_class_from_file("") == ""


# ---------------------------------------------------------------------------
# _find_maven_module() — nearest submodule dir with a pom.xml
# ---------------------------------------------------------------------------


def test_find_maven_module_returns_submodule_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pom.xml").write_text("<project/>")
    module = tmp_path / "svc"
    module.mkdir()
    (module / "pom.xml").write_text("<project/>")
    result = pt._find_maven_module("svc/src/main/java/com/x/A.java")
    assert result == "svc"


def test_find_maven_module_empty_when_no_submodule(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pom.xml").write_text("<project/>")
    result = pt._find_maven_module("src/main/java/com/x/A.java")
    assert result == ""


def test_find_maven_module_empty_for_empty_input() -> None:
    assert pt._find_maven_module("") == ""


# ---------------------------------------------------------------------------
# _is_gradle() — presence of any gradle build/settings file
# ---------------------------------------------------------------------------


def test_is_gradle_true_when_build_gradle_present(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "build.gradle").write_text("")
    assert pt._is_gradle() is True


def test_is_gradle_true_when_settings_gradle_kts_present(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "settings.gradle.kts").write_text("")
    assert pt._is_gradle() is True


def test_is_gradle_false_when_no_gradle_files(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pom.xml").write_text("<project/>")
    assert pt._is_gradle() is False


# ---------------------------------------------------------------------------
# _is_pitest_source() — extension set + Test/Spec exclusion
# ---------------------------------------------------------------------------


def test_is_pitest_source_true_for_plain_java() -> None:
    assert pt._is_pitest_source("src/main/java/com/x/Calc.java") is True


def test_is_pitest_source_true_for_kotlin_and_scala() -> None:
    assert pt._is_pitest_source("src/main/kotlin/A.kt") is True
    assert pt._is_pitest_source("src/A.scala") is True


def test_is_pitest_source_excludes_test_file() -> None:
    assert pt._is_pitest_source("src/test/java/com/x/CalcTest.java") is False


def test_is_pitest_source_excludes_spec_file() -> None:
    assert pt._is_pitest_source("src/test/groovy/CalcSpec.groovy") is False


def test_is_pitest_source_false_for_non_source_extension() -> None:
    assert pt._is_pitest_source("README.md") is False


# ---------------------------------------------------------------------------
# _extract_test_class() — -Dtest=<x> parsing
# ---------------------------------------------------------------------------


def test_extract_test_class_returns_dtest_value() -> None:
    assert pt._extract_test_class("mvn test -Dtest=CalcTest") == "CalcTest"


def test_extract_test_class_empty_when_absent() -> None:
    assert pt._extract_test_class("mvn test") == ""


# ---------------------------------------------------------------------------
# pitest_parse() — XML + surefire stdout → zero-kill list
# ---------------------------------------------------------------------------


def test_parse_missing_report_writes_empty_and_advises(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.delenv("ADAPTER_RUNNER_STDOUT", raising=False)
    out = tmp_path / "zk.json"
    pt.pitest_parse(tmp_path / "nope.xml", out)
    assert out.read_text() == "[]"
    assert "pitest report not found" in capsys.readouterr().out


def test_parse_no_runner_stdout_advises_with_kill_count(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.delenv("ADAPTER_RUNNER_STDOUT", raising=False)
    xml = tmp_path / "mutations.xml"
    xml.write_text(
        '<mutations>'
        '<mutation status="KILLED"/>'
        '<mutation status="KILLED"/>'
        '<mutation status="SURVIVED"/>'
        '</mutations>'
    )
    out = tmp_path / "zk.json"
    pt.pitest_parse(xml, out)
    assert out.read_text() == "[]"
    assert "(2/3 mutants killed)" in capsys.readouterr().out


def test_parse_derives_zero_kill_from_surefire_and_killing_tests(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(
        "ADAPTER_RUNNER_STDOUT",
        "com.example.CalcTest.testAdd\ncom.example.CalcTest.testSub\n",
    )
    xml = tmp_path / "mutations.xml"
    xml.write_text(
        "<mutations><mutation><killingTest>com.example.CalcTest.testAdd"
        "</killingTest></mutation></mutations>"
    )
    out = tmp_path / "zk.json"
    pt.pitest_parse(xml, out)
    data = json.loads(out.read_text())
    names = [d["name"] for d in data]
    # testAdd killed a mutant; testSub killed none → only testSub is a zero-kill.
    assert names == ["com.example.CalcTest.testSub"]
    assert data[0]["covered"] == 0
    # zero-kill dict shape: file and line are explicit None.
    assert data[0]["file"] is None
    assert data[0]["line"] is None


# ---------------------------------------------------------------------------
# pitest_run() — argv construction (Maven)
# ---------------------------------------------------------------------------


def _capture_argv(monkeypatch, returncode: int = 0):
    captured = {}

    def fake_run(_seconds, argv, **_kwargs):
        captured["argv"] = argv
        return subprocess.CompletedProcess(args=argv, returncode=returncode)

    monkeypatch.setattr(pt.lib, "run_with_timeout", fake_run)
    monkeypatch.setattr(pt, "pitest_parse", lambda _rp, _of: None)
    return captured


def test_run_builds_maven_argv_with_scoping(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pom.xml").write_text("<project/>")
    monkeypatch.setenv("ADAPTER_COMMAND", "mvn test -Dtest=CalcTest")
    monkeypatch.setattr(
        pt, "_changed_source_file", lambda: "src/main/java/com/example/Calc.java"
    )
    # Report exists so pitest_parse (stubbed) is reached.
    report = tmp_path / "target" / "pit-reports"
    report.mkdir(parents=True)
    (report / "mutations.xml").write_text("<mutations/>")
    captured = _capture_argv(monkeypatch)

    assert pt.pitest_run(tmp_path / "out.json") == 0
    argv = captured["argv"]
    assert argv[0] in {"mvn", "./mvnw"}
    assert "pitest:mutationCoverage" in argv
    assert "-DtargetClasses=com.example.Calc*" in argv
    assert "-DtargetTests=CalcTest" in argv
    assert "-DwithHistory" in argv
    # Fixed pitest args must be present verbatim (kills the string mutants).
    assert "-DtimeoutConst=60" in argv
    assert "-DtimeoutFactor=2.5" in argv
    assert "-DoutputFormats=XML" in argv
    assert "-DtimestampedReports=false" in argv


def test_run_builds_gradle_argv_when_gradle_project(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "build.gradle").write_text("")
    monkeypatch.setenv("ADAPTER_COMMAND", "gradle test")
    monkeypatch.setattr(
        pt, "_changed_source_file", lambda: "src/main/java/com/example/Calc.java"
    )
    report = tmp_path / "build" / "reports" / "pitest"
    report.mkdir(parents=True)
    (report / "mutations.xml").write_text("<mutations/>")
    monkeypatch.setenv("PITEST_REPORT", str(report / "mutations.xml"))
    captured = _capture_argv(monkeypatch)

    assert pt.pitest_run(tmp_path / "out.json") == 0
    argv = captured["argv"]
    assert argv[0] in {"gradle", "./gradlew"}
    assert "pitest" in argv
    assert "-PtargetClasses=com.example.Calc*" in argv


# ---------------------------------------------------------------------------
# pitest_run() — timeout and no-report advisory paths
# ---------------------------------------------------------------------------


def test_run_timeout_writes_empty_and_advises(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pom.xml").write_text("<project/>")
    monkeypatch.setenv("ADAPTER_COMMAND", "mvn test")
    monkeypatch.setattr(pt, "_changed_source_file", lambda: "")
    _capture_argv(monkeypatch, returncode=124)

    out = tmp_path / "out.json"
    assert pt.pitest_run(out) == 0
    assert out.read_text() == "[]"
    text = capsys.readouterr().out
    assert "pitest timed out after 300s." in text
    assert "No source file detected for scoping" in text


def test_run_timeout_omits_scope_hint_when_source_detected(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pom.xml").write_text("<project/>")
    monkeypatch.setenv("ADAPTER_COMMAND", "mvn test")
    monkeypatch.setattr(
        pt, "_changed_source_file", lambda: "src/main/java/com/example/Calc.java"
    )
    _capture_argv(monkeypatch, returncode=124)

    out = tmp_path / "out.json"
    assert pt.pitest_run(out) == 0
    text = capsys.readouterr().out
    assert "No source file detected for scoping" not in text


def test_run_honors_custom_timeout_env(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pom.xml").write_text("<project/>")
    monkeypatch.setenv("ADAPTER_COMMAND", "mvn test")
    monkeypatch.setenv("ADAPTER_TIMEOUT", "42")
    monkeypatch.setattr(pt, "_changed_source_file", lambda: "")
    _capture_argv(monkeypatch, returncode=124)

    assert pt.pitest_run(tmp_path / "out.json") == 0
    assert "pitest timed out after 42s." in capsys.readouterr().out


def test_run_nonzero_exit_without_report_writes_empty_and_advises(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pom.xml").write_text("<project/>")
    monkeypatch.setenv("ADAPTER_COMMAND", "mvn test")
    monkeypatch.setattr(pt, "_changed_source_file", lambda: "")
    _capture_argv(monkeypatch, returncode=9)

    out = tmp_path / "out.json"
    assert pt.pitest_run(out) == 0
    assert out.read_text() == "[]"
    assert "exited with code 9 and produced no report" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# main() — argument handling + delegation
# ---------------------------------------------------------------------------


def test_main_no_args_returns_2_with_exact_message(capsys) -> None:
    rc = pt.main([])
    assert rc == 2
    assert capsys.readouterr().err == "pitest.py: OUTPUT_FILE argument required\n"


def test_main_delegates_first_arg_as_output_path(monkeypatch) -> None:
    captured = {}

    def fake_run(out_file):
        captured["out"] = out_file
        return 0

    monkeypatch.setattr(pt, "pitest_run", fake_run)
    rc = pt.main(["out.json", "extra.json"])
    assert rc == 0
    assert captured["out"] == pt.Path("out.json")


def test_main_reads_from_sys_argv_when_argv_none(monkeypatch):
    captured = {}

    def fake_run(out_file):
        captured["out"] = out_file
        return 0

    monkeypatch.setattr(pt.sys, "argv", ["pitest.py", "out.json"])
    monkeypatch.setattr(pt, "pitest_run", fake_run)
    assert pt.main() == 0
    assert captured["out"] == pt.Path("out.json")


# ---------------------------------------------------------------------------
# mutation-kill targeted survivors (#1354) — exact-text + argv-shape kills
# ---------------------------------------------------------------------------


def test_detect_false_advisory_exact_message(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert pt.pitest_detect() is False
    ctx = json.loads(capsys.readouterr().out)["hookSpecificOutput"]["additionalContext"]
    assert ctx == (
        "MUTATION GATE ADVISORY: pitest not found. Run /setup to configure it, "
        "or add the pitest-maven plugin to pom.xml / pitest plugin to build.gradle "
        "manually."
    )


def test_is_gradle_true_when_only_build_gradle_kts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "build.gradle.kts").write_text("")
    assert pt._is_gradle() is True


def test_is_gradle_true_when_only_settings_gradle(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "settings.gradle").write_text("")
    assert pt._is_gradle() is True


def test_parse_missing_report_advisory_message(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("ADAPTER_RUNNER_STDOUT", raising=False)
    out = tmp_path / "zk.json"
    missing = tmp_path / "nope.xml"
    pt.pitest_parse(missing, out)
    ctx = json.loads(capsys.readouterr().out)["hookSpecificOutput"]["additionalContext"]
    assert ctx == (
        f"MUTATION GATE ADVISORY: pitest report not found at {missing}. "
        "Skipping mutation gate."
    )


def test_parse_no_runner_stdout_advisory_exact_message(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("ADAPTER_RUNNER_STDOUT", raising=False)
    xml = tmp_path / "mutations.xml"
    xml.write_text('<m><x status="KILLED"/><x status="SURVIVED"/></m>')
    out = tmp_path / "zk.json"
    pt.pitest_parse(xml, out)
    ctx = json.loads(capsys.readouterr().out)["hookSpecificOutput"]["additionalContext"]
    assert ctx == (
        "MUTATION GATE ADVISORY: pitest completed (1/2 mutants killed) but "
        "per-test data unavailable — runner stdout was not captured. Manual "
        "review recommended."
    )


def test_parse_detects_surefire_method_as_zero_kill(tmp_path, monkeypatch):
    monkeypatch.setenv("ADAPTER_RUNNER_STDOUT", "testAdd   PASS\n")
    xml = tmp_path / "mutations.xml"
    xml.write_text("<mutations></mutations>")  # no killing tests
    out = tmp_path / "zk.json"
    pt.pitest_parse(xml, out)
    assert [d["name"] for d in json.loads(out.read_text())] == ["testAdd"]


def test_parse_ignores_dotted_non_method_lines(tmp_path, monkeypatch):
    # A line with a dot but not a fully-qualified method must be ignored
    # (the guard is `.match(...) and "." in line`, not `or`).
    monkeypatch.setenv("ADAPTER_RUNNER_STDOUT", "com.foo.Bar extra words\n")
    xml = tmp_path / "mutations.xml"
    xml.write_text("<mutations></mutations>")
    out = tmp_path / "zk.json"
    pt.pitest_parse(xml, out)
    assert json.loads(out.read_text()) == []


def test_run_adds_module_flag_for_submodule(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pom.xml").write_text("<project/>")
    sub = tmp_path / "svc"
    sub.mkdir()
    (sub / "pom.xml").write_text("<project/>")
    monkeypatch.setenv("ADAPTER_COMMAND", "mvn test")
    monkeypatch.setattr(
        pt, "_changed_source_file", lambda: "svc/src/main/java/com/x/A.java"
    )
    report = tmp_path / "target" / "pit-reports"
    report.mkdir(parents=True)
    (report / "mutations.xml").write_text("<mutations/>")
    captured = _capture_argv(monkeypatch)

    assert pt.pitest_run(tmp_path / "out.json") == 0
    argv = captured["argv"]
    i = argv.index("-pl")
    assert argv[i : i + 3] == ["-pl", "svc", "--also-make-dependents"]


def test_run_gradle_uses_gradlew_wrapper_when_present(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "build.gradle").write_text("")
    monkeypatch.setenv("ADAPTER_COMMAND", "gradle test")
    monkeypatch.setattr(
        pt, "_changed_source_file", lambda: "src/main/java/com/x/A.java"
    )
    monkeypatch.setattr(
        pt.shutil,
        "which",
        lambda name: "/x/gradlew" if name == "./gradlew" else None,
    )
    report = tmp_path / "build" / "reports" / "pitest"
    report.mkdir(parents=True)
    (report / "mutations.xml").write_text("<mutations/>")
    monkeypatch.setenv("PITEST_REPORT", str(report / "mutations.xml"))
    captured = _capture_argv(monkeypatch)

    assert pt.pitest_run(tmp_path / "out.json") == 0
    assert captured["argv"][0] == "./gradlew"


def test_run_maven_uses_mvnw_wrapper_when_present(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pom.xml").write_text("<project/>")
    (tmp_path / "mvnw").write_text("#!/bin/sh\n")  # ./mvnw exists in cwd
    monkeypatch.setenv("ADAPTER_COMMAND", "mvn test")
    monkeypatch.setattr(
        pt, "_changed_source_file", lambda: "src/main/java/com/x/A.java"
    )
    report = tmp_path / "target" / "pit-reports"
    report.mkdir(parents=True)
    (report / "mutations.xml").write_text("<mutations/>")
    captured = _capture_argv(monkeypatch)

    assert pt.pitest_run(tmp_path / "out.json") == 0
    assert captured["argv"][0] == "./mvnw"


def test_run_timeout_no_source_exact_message(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pom.xml").write_text("<project/>")
    monkeypatch.setenv("ADAPTER_COMMAND", "mvn test")
    monkeypatch.setattr(pt, "_changed_source_file", lambda: "")
    _capture_argv(monkeypatch, returncode=124)

    assert pt.pitest_run(tmp_path / "out.json") == 0
    ctx = json.loads(capsys.readouterr().out)["hookSpecificOutput"]["additionalContext"]
    assert ctx == (
        "MUTATION GATE SKIPPED: pitest timed out after 300s. No source file "
        "detected for scoping — scope manually with git diff. Or: "
        "MUTATION_GATE_TIMEOUT=<seconds> to extend the limit."
    )


def test_run_timeout_with_source_exact_message(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pom.xml").write_text("<project/>")
    monkeypatch.setenv("ADAPTER_COMMAND", "mvn test")
    monkeypatch.setattr(
        pt, "_changed_source_file", lambda: "src/main/java/com/x/A.java"
    )
    _capture_argv(monkeypatch, returncode=124)

    assert pt.pitest_run(tmp_path / "out.json") == 0
    ctx = json.loads(capsys.readouterr().out)["hookSpecificOutput"]["additionalContext"]
    assert ctx == (
        "MUTATION GATE SKIPPED: pitest timed out after 300s. Or: "
        "MUTATION_GATE_TIMEOUT=<seconds> to extend the limit."
    )


def test_run_exit_one_no_report_advises_exit_code(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pom.xml").write_text("<project/>")
    monkeypatch.setenv("ADAPTER_COMMAND", "mvn test")
    monkeypatch.setattr(
        pt, "_changed_source_file", lambda: "src/main/java/com/x/A.java"
    )
    _capture_argv(monkeypatch, returncode=1)  # no report on disk

    assert pt.pitest_run(tmp_path / "out.json") == 0
    ctx = json.loads(capsys.readouterr().out)["hookSpecificOutput"]["additionalContext"]
    assert ctx == (
        "MUTATION GATE ADVISORY: pitest exited with code 1 and produced no "
        "report. Skipping mutation gate."
    )


def test_run_exit_zero_no_report_reaches_parse(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pom.xml").write_text("<project/>")
    monkeypatch.setenv("ADAPTER_COMMAND", "mvn test")
    monkeypatch.setattr(
        pt, "_changed_source_file", lambda: "src/main/java/com/x/A.java"
    )

    # Real pitest_parse runs (not stubbed); with no report it reports "not found".
    def fake_run(_seconds, argv, **_kwargs):
        return subprocess.CompletedProcess(args=argv, returncode=0)

    monkeypatch.setattr(pt.lib, "run_with_timeout", fake_run)

    assert pt.pitest_run(tmp_path / "out.json") == 0
    ctx = json.loads(capsys.readouterr().out)["hookSpecificOutput"]["additionalContext"]
    assert "pitest report not found" in ctx
