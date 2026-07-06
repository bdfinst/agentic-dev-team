"""Stryker.NET (C#) mutation-testing adapter — Python port of stryker-net.sh.

Uses the same JSON schema as Stryker JS, so `lib.parse_stryker_kills` is
shared. `stryker_net_run` intentionally stays separate from `stryker_run`:
the CLI surfaces diverge, only the JSON parser is the stable contract.
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


DEFAULT_REPORT = "StrykerOutput/mutation-report.json"


def _default_report_path() -> Path:
    return Path(os.environ.get("STRYKER_NET_REPORT", DEFAULT_REPORT))


def stryker_net_detect() -> bool:
    """Return True when Stryker.NET is available."""
    tools = Path(".config/dotnet-tools.json")
    if tools.is_file():
        try:
            if "dotnet-stryker" in tools.read_text():
                return True
        except OSError:
            pass
    if shutil.which("dotnet") is not None:
        try:
            proc = subprocess.run(
                ["dotnet", "stryker", "--version"],
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
            "MUTATION GATE ADVISORY: Stryker.NET not installed. Run /setup "
            "to install it, or run: dotnet tool install dotnet-stryker"
        )
    )
    return False


def _shard_for_file(changed_file: str) -> Optional[Path]:
    """Return the stryker-config.shard-*.json whose `mutate` pattern covers
    `changed_file`, or None when no shard matches.
    """
    if not changed_file:
        return None
    for shard_cfg in sorted(Path(".").glob("stryker-config.shard-*.json")):
        try:
            cfg = json.loads(shard_cfg.read_text())
            stryker_cfg = cfg.get("stryker-config") or {}
            patterns = stryker_cfg.get("mutate") or []
            if not patterns:
                continue
            pattern = patterns[0]
            # pattern is like 'src/Foo.Bar/**/*.cs' — extract prefix before '/**'
            src_prefix = pattern.split("/**")[0]
        except (OSError, ValueError):
            continue
        if not src_prefix:
            continue
        if changed_file.startswith(src_prefix + "/") or changed_file.startswith(
            src_prefix
        ):
            return shard_cfg
    return None


def _is_cs_source(line: str) -> bool:
    """True for a non-test C# source path."""
    if not line.endswith(".cs"):
        return False
    if "Test" in line or "Spec" in line:
        return False
    return True


def _changed_cs_file() -> str:
    """Return the newest non-test C# file changed in HEAD (or cached), or ''."""
    return lib.first_changed_file(_is_cs_source)


def stryker_net_run(output_file: Path) -> int:
    """Run dotnet-stryker; write normalized zero-kills to `output_file`."""
    output_file = Path(output_file)
    timeout_seconds = int(os.environ.get("ADAPTER_TIMEOUT", "600"))

    report_path = _default_report_path()
    report_path.parent.mkdir(parents=True, exist_ok=True)

    stryker_args: List[str] = [
        "--reporter",
        "json",
        "--coverage-analysis",
        "perTest",
        "--mutation-level",
        "Standard",
    ]

    changed_file = _changed_cs_file()
    config_flag: List[str] = []
    if changed_file:
        shard_cfg = _shard_for_file(changed_file)
        if shard_cfg is not None:
            config_flag = ["--config-file", str(shard_cfg)]
            report_path = Path("StrykerOutput/gate-shard/reports/mutation-report.json")
            report_path.parent.mkdir(parents=True, exist_ok=True)

    if not config_flag and Path("stryker-config.json").is_file():
        config_flag = ["--config-file", "stryker-config.json"]

    if changed_file and config_flag:
        stryker_args += ["--mutate", f"**/{Path(changed_file).name}"]
        report_path = Path("StrykerOutput/gate-shard/reports/mutation-report.json")

    stryker_args += ["--output", "StrykerOutput/gate-shard"]

    if os.environ.get("CI") != "true":
        since = os.environ.get("STRYKER_SINCE_TARGET", "")
        if since:
            # bash used `--since:<ref>`; keep the same wire form
            stryker_args.append(f"--since:{since}")

    argv = ["dotnet", "stryker", *config_flag, *stryker_args]

    completed = lib.run_with_timeout(
        timeout_seconds,
        argv,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    exit_code = completed.returncode

    if exit_code == 124:
        print(
            lib.emit_advisory(
                f"MUTATION GATE SKIPPED: Stryker.NET timed out after {timeout_seconds}s. "
                "For large repos, run stryker-setup.py to generate shard configs "
                "(reduces scope to one project). Or: ADAPTER_TIMEOUT=<seconds> to "
                "extend the limit."
            )
        )
        output_file.write_text("[]")
        return 0

    if exit_code != 0 and not report_path.is_file():
        print(
            lib.emit_advisory(
                f"MUTATION GATE ADVISORY: Stryker.NET exited with code {exit_code} "
                "and produced no report. Skipping mutation gate."
            )
        )
        output_file.write_text("[]")
        return 0

    advisory = lib.parse_stryker_kills(report_path, output_file)
    if advisory is not None:
        print(advisory)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("stryker_net.py: OUTPUT_FILE argument required", file=sys.stderr)
        return 2
    return stryker_net_run(Path(args[0]))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
