"""Stryker (JS/TS) mutation-testing adapter — Python port of stryker.sh.

Contract mirrors the bash adapter:
  ADAPTER_SOURCE_FILE   — source file to mutate (scopes `--mutate`)
  ADAPTER_TIMEOUT       — outer wall-clock cap, seconds (default 300)
Output: writes zero-kill JSON to the caller-supplied output path.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from . import lib

DEFAULT_REPORT = "reports/mutation/mutation.json"


def _report_path() -> Path:
    return Path(os.environ.get("STRYKER_REPORT", DEFAULT_REPORT))


def stryker_detect() -> bool:
    """Return True when Stryker is available in the current project."""
    if Path("node_modules/.bin/stryker").is_file():
        return True
    pkg = Path("package.json")
    if pkg.is_file():
        try:
            if "@stryker-mutator/core" in pkg.read_text():
                return True
        except OSError:
            pass
    print(
        lib.emit_advisory(
            "MUTATION GATE ADVISORY: Stryker not installed. Run /setup to "
            "install it, or add @stryker-mutator/core manually."
        )
    )
    return False


def derive_source_file(test_file: str) -> str:
    """Strip .test./.spec. from a test filename to yield the source filename.

    e.g. calc.test.ts → calc.ts, calc.spec.js → calc.js.
    """
    return re.sub(r"\.(test|spec)\.(ts|tsx|js|jsx|mjs)$", r".\2", test_file)


def _read_configured_timeout_ms() -> int | None:
    """Return the project's `timeoutMS` from Stryker config, or None.

    Checks `.strykerrc.json` first (pure JSON), then greps `stryker.config.*`.
    """
    rc = Path(".strykerrc.json")
    if rc.is_file():
        try:
            cfg = json.loads(rc.read_text())
            val = cfg.get("timeoutMS") or cfg.get("timeout")
            if val:
                return int(val)
        except (OSError, ValueError):
            pass
        return None
    for name in (
        "stryker.config.js",
        "stryker.config.mjs",
        "stryker.config.cjs",
        "stryker.config.ts",
    ):
        p = Path(name)
        if not p.is_file():
            continue
        try:
            content = p.read_text()
        except OSError:
            continue
        m = re.search(r"timeoutMS[\s]*:[\s]*(\d+)", content)
        if m:
            return int(m.group(1))
        return None
    return None


def stryker_run(output_file: Path) -> int:
    """Run Stryker; write normalized zero-kills to `output_file`.

    Advisory paths write `[]` and return 0 — the orchestrator treats those as
    "gate skipped."
    """
    output_file = Path(output_file)
    timeout_seconds = int(os.environ.get("ADAPTER_TIMEOUT", "300"))
    src_file = os.environ.get("ADAPTER_SOURCE_FILE", "")

    report = _report_path()
    report.parent.mkdir(parents=True, exist_ok=True)

    stryker_args: list[str] = ["--reporters", "json", "--coverageAnalysis", "perTest"]
    if src_file:
        stryker_args += ["--mutate", src_file]

    argv = ["npx", "stryker", "run", *stryker_args]
    completed = lib.run_with_timeout(
        timeout_seconds,
        argv,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    exit_code = completed.returncode

    if exit_code == 124:
        configured = _read_configured_timeout_ms()
        hint = (
            ""
            if configured is not None
            else " Add 'timeoutMS: <ms>' to stryker.config.js to cap per-mutant runs."
        )
        print(
            lib.emit_advisory(
                f"MUTATION GATE SKIPPED: Stryker timed out after {timeout_seconds}s.{hint}"
                " Or: MUTATION_GATE_TIMEOUT=<seconds> to extend the outer limit."
            )
        )
        output_file.write_text("[]")
        return 0

    if exit_code != 0 and not report.is_file():
        print(
            lib.emit_advisory(
                f"MUTATION GATE ADVISORY: Stryker exited with code {exit_code} and "
                "produced no report. Skipping mutation gate."
            )
        )
        output_file.write_text("[]")
        return 0

    advisory = lib.parse_stryker_kills(report, output_file)
    if advisory is not None:
        print(advisory)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("stryker.py: OUTPUT_FILE argument required", file=sys.stderr)
        return 2
    return stryker_run(Path(args[0]))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
