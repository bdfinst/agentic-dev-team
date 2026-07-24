"""pitest (Java/Kotlin) mutation-testing adapter — Python port of pitest.sh.

Key features (mirroring bash):
  - ADAPTER_TIMEOUT default 300s (Maven startup alone can eat 20-30s).
  - Source class derived from the changed file → `-DtargetClasses`.
  - `-DwithHistory` for incremental runs.
  - `-DtimeoutConst` / `-DtimeoutFactor` cap per-mutant wall-clock time.
  - Multi-module Maven: detect the module containing the changed file → `-pl`.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from . import lib

DEFAULT_REPORT = "target/pit-reports/mutations.xml"


def _report_path() -> Path:
    return Path(os.environ.get("PITEST_REPORT", DEFAULT_REPORT))


def pitest_detect() -> bool:
    """Return True when pitest is configured in this project."""
    for name, needle in (
        ("pom.xml", "pitest"),
        ("build.gradle", "pitest"),
        ("build.gradle.kts", "pitest"),
    ):
        p = Path(name)
        if not p.is_file():
            continue
        try:
            if needle in p.read_text():
                return True
        except OSError:
            continue
    print(
        lib.emit_advisory(
            "MUTATION GATE ADVISORY: pitest not found. Run /setup to "
            "configure it, or add the pitest-maven plugin to pom.xml / pitest "
            "plugin to build.gradle manually."
        )
    )
    return False


_SOURCE_ROOT_RE = re.compile(
    r"^.*(?:src/main/java/|src/main/kotlin/|src/main/groovy/|src/)"
)


def _java_class_from_file(file: str) -> str:
    """Convert a Java/Kotlin source path to a dotted class name.

    src/main/java/com/example/Calculator.java → com.example.Calculator
    """
    if not file:
        return ""
    rel = _SOURCE_ROOT_RE.sub("", file, count=1)
    rel = re.sub(r"\.(java|kt|groovy|scala)$", "", rel)
    return rel.replace("/", ".")


def _find_maven_module(file: str) -> str:
    """Return the nearest sub-module dir containing `file`, or '' for root."""
    if not file:
        return ""
    dir_ = os.path.dirname(file)
    while dir_ and dir_ != ".":
        if Path(dir_, "pom.xml").is_file() and Path("pom.xml").is_file():
            return dir_
        dir_ = os.path.dirname(dir_)
    return ""


def _is_gradle() -> bool:
    return any(
        Path(name).is_file()
        for name in (
            "build.gradle",
            "build.gradle.kts",
            "settings.gradle",
            "settings.gradle.kts",
        )
    )


def _is_pitest_source(line: str) -> bool:
    """True for a non-test Java/Kotlin/Groovy/Scala source path."""
    if not re.search(r"\.(java|kt|groovy|scala)$", line):
        return False
    if "Test" in line or "Spec" in line:
        return False
    return True


def _changed_source_file() -> str:
    """Return the first non-test Java/Kotlin/Groovy/Scala file from git diff."""
    return lib.first_changed_file(_is_pitest_source)


def _extract_test_class(command: str) -> str:
    """Return the value of `-Dtest=<x>` in `command`, or ''."""
    m = re.search(r"-Dtest=(\S+)", command)
    return m.group(1) if m else ""


_KILLING_TEST_RE = re.compile(r"<killingTest>([^<]+)</killingTest>")
_FQ_METHOD_RE = re.compile(r"^[\w.]+\.\w+$")
_SUREFIRE_RE = re.compile(r"^(\w+)\s+(Time elapsed|PASS|FAIL)")


def pitest_parse(xml_file: Path, output_file: Path) -> None:
    """Parse pitest XML + captured runner stdout; write zero-kills."""
    xml_file = Path(xml_file)
    output_file = Path(output_file)
    runner_stdout = os.environ.get("ADAPTER_RUNNER_STDOUT", "")

    if not xml_file.is_file():
        print(
            lib.emit_advisory(
                f"MUTATION GATE ADVISORY: pitest report not found at {xml_file}. "
                "Skipping mutation gate."
            )
        )
        try:
            output_file.write_text("[]")
        except OSError:
            pass
        return

    if not runner_stdout:
        try:
            content = xml_file.read_text()
        except OSError:
            content = ""
        killed = content.count('status="KILLED"')
        survived = content.count('status="SURVIVED"')
        total = killed + survived
        print(
            lib.emit_advisory(
                f"MUTATION GATE ADVISORY: pitest completed ({killed}/{total} "
                "mutants killed) but per-test data unavailable — runner stdout "
                "was not captured. Manual review recommended."
            )
        )
        try:
            output_file.write_text("[]")
        except OSError:
            pass
        return

    content = xml_file.read_text()
    killing_set = {m.group(1).strip() for m in _KILLING_TEST_RE.finditer(content)}

    test_methods = set()
    for raw in runner_stdout.splitlines():
        line = raw.strip()
        if _FQ_METHOD_RE.match(line) and "." in line:
            test_methods.add(line)
        m = _SUREFIRE_RE.match(line)
        if m:
            test_methods.add(m.group(1))

    zero_kills = []
    for test in sorted(test_methods - killing_set):
        zero_kills.append({"name": test, "file": None, "line": None, "covered": 0})
    output_file.write_text(json.dumps(zero_kills))


def pitest_run(output_file: Path) -> int:
    """Run pitest via Maven or Gradle and write zero-kills."""
    output_file = Path(output_file)
    timeout_seconds = int(os.environ.get("ADAPTER_TIMEOUT", "300"))
    command = os.environ.get("ADAPTER_COMMAND", "")

    changed_file = _changed_source_file()
    target_class = _java_class_from_file(changed_file) if changed_file else ""
    target_tests = _extract_test_class(command)

    pitest_args: list[str] = [
        "-DtimeoutConst=60",
        "-DtimeoutFactor=2.5",
        "-DoutputFormats=XML",
        "-DtimestampedReports=false",
        "-DwithHistory",
    ]
    if target_class:
        pitest_args.append(f"-DtargetClasses={target_class}*")
    if target_tests:
        pitest_args.append(f"-DtargetTests={target_tests}")

    module_flag: list[str] = []
    if changed_file:
        module_dir = _find_maven_module(changed_file)
        if module_dir:
            module_flag = ["-pl", module_dir, "--also-make-dependents"]

    report_path = _report_path()

    if _is_gradle():
        gradle_cmd = "./gradlew" if shutil.which("./gradlew") else "gradle"
        gradle_args = ["pitest"]
        if target_class:
            gradle_args.append(f"-PtargetClasses={target_class}*")
        argv = [gradle_cmd, *gradle_args]
        report_path = Path(
            os.environ.get("PITEST_REPORT", "build/reports/pitest/mutations.xml")
        )
    else:
        mvn_cmd = "./mvnw" if Path("./mvnw").is_file() else "mvn"
        argv = [mvn_cmd, "pitest:mutationCoverage", *module_flag, *pitest_args]

    completed = lib.run_with_timeout(
        timeout_seconds,
        argv,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    exit_code = completed.returncode

    if exit_code == 124:
        hint = (
            " No source file detected for scoping — scope manually with git diff."
            if not target_class
            else ""
        )
        print(
            lib.emit_advisory(
                f"MUTATION GATE SKIPPED: pitest timed out after {timeout_seconds}s.{hint}"
                " Or: MUTATION_GATE_TIMEOUT=<seconds> to extend the limit."
            )
        )
        output_file.write_text("[]")
        return 0

    if exit_code != 0 and not report_path.is_file():
        print(
            lib.emit_advisory(
                f"MUTATION GATE ADVISORY: pitest exited with code {exit_code} and "
                "produced no report. Skipping mutation gate."
            )
        )
        output_file.write_text("[]")
        return 0

    pitest_parse(report_path, output_file)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("pitest.py: OUTPUT_FILE argument required", file=sys.stderr)
        return 2
    return pitest_run(Path(args[0]))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
