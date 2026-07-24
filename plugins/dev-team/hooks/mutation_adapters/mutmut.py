"""mutmut (Python) mutation-testing adapter — Python port of mutmut.sh.

mutmut scopes to a single file via `--paths-to-mutate` and completes in
seconds-to-minutes for typical Python unit test suites. mutmut has no
`--json` results output; survivors are read from `mutmut junitxml`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from . import lib


def mutmut_detect() -> bool:
    """Return True when mutmut is available in this project."""
    if shutil.which("mutmut") is not None:
        return True
    try:
        # `mutmut` is a `version` subcommand, not a `--version` flag — the
        # flag form exits nonzero on the real CLI and always reads as absent.
        proc = subprocess.run(
            ["python3", "-m", "mutmut", "version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if proc.returncode == 0:
            return True
    except (FileNotFoundError, OSError):
        pass
    print(
        lib.emit_advisory(
            "MUTATION GATE ADVISORY: mutmut not installed. Run /setup to "
            "install it, or: pip install mutmut"
        )
    )
    return False


def _derive_python_source(test_file: str) -> str:
    """Strip test_ prefix / _test suffix from `test_file` to find the source."""
    base = Path(test_file).stem
    base = base.removeprefix("test_")
    base = base.removesuffix("_test")
    for dir_ in ("src", "", "lib"):
        candidate = f"{dir_}/{base}.py" if dir_ else f"{base}.py"
        if Path(candidate).is_file():
            return candidate
    return test_file


def _is_python_source(line: str) -> bool:
    """True for a non-test Python source path."""
    if not line.endswith(".py"):
        return False
    return not (line.startswith("test_") or "_test.py" in line or "/test_" in line)


def _changed_python_source() -> str:
    return lib.first_changed_file(_is_python_source)


def _mutmut_argv() -> list[str]:
    """Return the argv prefix for invoking mutmut — either `mutmut` or `python3 -m mutmut`."""
    if shutil.which("mutmut") is not None:
        return ["mutmut"]
    return ["python3", "-m", "mutmut"]


def mutmut_run(output_file: Path) -> int:
    """Run mutmut scoped to the changed Python file; write zero-kills."""
    output_file = Path(output_file)
    timeout_seconds = int(os.environ.get("ADAPTER_TIMEOUT", "120"))

    src_file = _changed_python_source()

    mutmut_prefix = _mutmut_argv()
    mutmut_args = ["run"]
    if src_file:
        mutmut_args.append(f"--paths-to-mutate={src_file}")

    argv = [*mutmut_prefix, *mutmut_args]
    completed = lib.run_with_timeout(
        timeout_seconds,
        argv,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    exit_code = completed.returncode

    if exit_code == 124:
        hint = (
            ""
            if src_file
            else " No source file detected — scope with --paths-to-mutate."
        )
        print(
            lib.emit_advisory(
                f"MUTATION GATE SKIPPED: mutmut timed out after {timeout_seconds}s.{hint}"
                " Or: MUTATION_GATE_TIMEOUT=<seconds> to extend the limit."
            )
        )
        output_file.write_text("[]")
        return 0

    # mutmut's exit code is a bitmask: 1=fatal error, 2=survived, 4=timeout,
    # 8=slow (any combination ORs together; 0 means every mutant was
    # killed). Bit 1 (fatal error — e.g. the baseline test run itself
    # failed) is the only outcome that invalidates the run; survivors
    # (bit 2) are the expected, common case and must still be parsed.
    if exit_code & 1:
        stderr = completed.stderr or ""
        if "cannot pickle" in stderr and "itertools.count" in stderr:
            hint = (
                " Known cause: mutmut<3 crashes on Python 3.13+ "
                "('TypeError: cannot pickle itertools.count object', a "
                "parso/pony-ORM deepcopy incompatibility) — install mutmut "
                "into a venv running Python <=3.12; the --runner test "
                "command can stay on the project's real interpreter."
            )
        else:
            hint = ""
        print(
            lib.emit_advisory(
                f"MUTATION GATE ADVISORY: mutmut exited with code {exit_code}. "
                f"Skipping mutation gate.{hint}"
            )
        )
        output_file.write_text("[]")
        return 0

    # Read survivors from `mutmut junitxml` — mutmut's `results` subcommand
    # has no `--json` output; junitxml is the only structured report it
    # ships. A <testcase> with a <failure> child is a survived mutant under
    # the default suspicious/untested policies (both "ignore").
    try:
        junit = subprocess.run(
            [*mutmut_prefix, "junitxml"],
            capture_output=True,
            text=True,
            check=False,
        )
        raw = junit.stdout or ""
    except (FileNotFoundError, OSError):
        raw = ""

    try:
        root = ET.fromstring(raw) if raw.strip() else None
    except ET.ParseError:
        root = None

    zero_kills = []
    if root is not None:
        for testcase in root.iter("testcase"):
            if testcase.find("failure") is None:
                continue
            line = testcase.get("line")
            zero_kills.append(
                {
                    "name": f"mutant_{testcase.get('name', '?')}",
                    "file": testcase.get("file"),
                    "line": int(line) if line and line.isdigit() else None,
                    "covered": 0,
                }
            )

    output_file.write_text(json.dumps(zero_kills))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("mutmut.py: OUTPUT_FILE argument required", file=sys.stderr)
        return 2
    return mutmut_run(Path(args[0]))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
