"""mutmut (Python) mutation-testing adapter — Python port of mutmut.sh.

mutmut scopes to a single file via `--paths-to-mutate` and completes in
seconds-to-minutes for typical Python unit test suites. Results come from
`mutmut results --json`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from . import lib


def mutmut_detect() -> bool:
    """Return True when mutmut is available in this project."""
    if shutil.which("mutmut") is not None:
        return True
    try:
        proc = subprocess.run(
            ["python3", "-m", "mutmut", "--version"],
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
    if base.startswith("test_"):
        base = base[len("test_") :]
    if base.endswith("_test"):
        base = base[: -len("_test")]
    for dir_ in ("src", "", "lib"):
        candidate = f"{dir_}/{base}.py" if dir_ else f"{base}.py"
        if Path(candidate).is_file():
            return candidate
    return test_file


def _is_python_source(line: str) -> bool:
    """True for a non-test Python source path."""
    if not line.endswith(".py"):
        return False
    if line.startswith("test_") or "_test.py" in line or "/test_" in line:
        return False
    return True


def _changed_python_source() -> str:
    return lib.first_changed_file(_is_python_source)


def _mutmut_argv() -> List[str]:
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
        stderr=subprocess.DEVNULL,
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

    # exit 1 with survivors is expected — still parse results.
    if exit_code >= 2:
        print(
            lib.emit_advisory(
                f"MUTATION GATE ADVISORY: mutmut exited with code {exit_code}. "
                "Skipping mutation gate."
            )
        )
        output_file.write_text("[]")
        return 0

    # Read survivors JSON.
    try:
        results = subprocess.run(
            [*mutmut_prefix, "results", "--json"],
            capture_output=True,
            text=True,
            check=False,
        )
        raw = results.stdout or "[]"
    except (FileNotFoundError, OSError):
        raw = "[]"

    try:
        data = json.loads(raw)
    except ValueError:
        data = []

    zero_kills = []
    for mutant in data:
        status = mutant.get("status", "")
        if status in ("survived", ""):
            zero_kills.append(
                {
                    "name": f"mutant_{mutant.get('id', '?')}",
                    "file": mutant.get("filename"),
                    "line": mutant.get("line_number"),
                    "covered": 0,
                }
            )

    output_file.write_text(json.dumps(zero_kills))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("mutmut.py: OUTPUT_FILE argument required", file=sys.stderr)
        return 2
    return mutmut_run(Path(args[0]))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
