"""doctor_probe.py - the interpreter self-probe behind ``/doctor``'s two interpreter checks.

Runs ``sh py.sh doctor.py --probe`` once and parses the one line it prints.
``scripts/doctor.py`` loads this module lazily, after its own ``--probe`` branch,
so a too-old interpreter never needs it.

Stdlib only. The top level stays parseable by Python 3.8 (see ``doctor.py``).
"""

from __future__ import annotations

import dataclasses
import re
import subprocess
import tempfile
from collections.abc import Mapping
from pathlib import Path

#: Exit code py.sh uses for "no interpreter found".
SHIM_NO_INTERPRETER = 2
#: Where py.sh keeps its interpreter cache; the probe points it at a scratch directory.
PY_CACHE_ENV = "DEV_TEAM_PY_CACHE"

#: Each version component is at most 9 digits, the margin
#: ``doctor_checks.MAX_VERSION_DIGITS`` sets: ``int()`` raises ``ValueError`` above
#: ``sys.get_int_max_str_digits()`` (default 4300; present on every interpreter
#: the floor gate runs, checked on 3.8.20, 3.9.25, 3.10.20 and 3.13).
_PROBE_LINE = re.compile(
    r"(?P<path>.+) (?P<version>[0-9]{1,9}\.[0-9]{1,9}\.[0-9]{1,9})"
)


@dataclasses.dataclass(frozen=True)
class ProbeResult:
    """What ``sh py.sh doctor.py --probe`` yielded: ``detail`` says why not ``resolved``."""

    resolved: bool
    path: str = ""
    version: tuple[int, int, int] | None = None
    detail: str = ""


def _parse_probe(stdout: str) -> tuple[str, tuple[int, int, int]] | None:
    """``"<path> 3.12.1"`` (the last stdout line) -> ``(path, (3, 12, 1))``."""
    lines = stdout.strip().splitlines()
    match = _PROBE_LINE.fullmatch(lines[-1].strip()) if lines else None
    if match is None:
        return None
    major, minor, micro = (int(part) for part in match["version"].split("."))
    return match["path"], (major, minor, micro)


def _first_stderr_line(stderr: str) -> str:
    """The first non-blank line of ``stderr``, stripped; empty when there is none."""
    return next((line.strip() for line in stderr.splitlines() if line.strip()), "")


def _with_detail(prefix: str, detail: str) -> str:
    return f"{prefix}: {detail}" if detail else prefix


def run_probe(
    shim: Path,
    script: Path,
    probe_flag: str,
    env: Mapping[str, str],
    timeout: float,
) -> ProbeResult:
    """Run ``shim`` against ``script``'s ``probe_flag`` mode, never touching the cache."""
    if not shim.is_file():
        return ProbeResult(False, detail=f"shim not found: {shim}")
    if not script.is_file():
        return ProbeResult(False, detail=f"script not found: {script}")
    try:
        scratch_dir = tempfile.TemporaryDirectory()
    except OSError as exc:
        reason = exc.strerror or exc
        return ProbeResult(
            False, detail=f"cannot create probe scratch directory: {reason}"
        )
    with scratch_dir as scratch:
        probe_env = {**env, PY_CACHE_ENV: str(Path(scratch) / "python")}
        try:
            completed = subprocess.run(
                ["sh", str(shim), str(script), probe_flag],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=timeout,
                env=probe_env,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return ProbeResult(False, detail=f"probe timed out after {timeout} s")
        except OSError as exc:
            return ProbeResult(False, detail=f"cannot run sh: {exc}")
    reason = _first_stderr_line(completed.stderr)
    if completed.returncode == SHIM_NO_INTERPRETER:
        return ProbeResult(
            False, detail=_with_detail("py.sh found no interpreter", reason)
        )
    if completed.returncode != 0:
        return ProbeResult(
            False, detail=_with_detail(f"probe exited {completed.returncode}", reason)
        )
    parsed = _parse_probe(completed.stdout)
    if parsed is None:
        return ProbeResult(False, detail="probe printed no version line")
    return ProbeResult(True, path=parsed[0], version=parsed[1])
