"""Jail the fixture's test commands, which run code the agent wrote.

A jailed command may write only inside the trial's working copy and its own
temp dir, and has no network. macOS uses `sandbox-exec`; Linux uses `bwrap`
(bubblewrap). Reads are not confined: the command can still read files the
user can read, so the answer key lives in a directory no prompt names (see
`snapshot`). A platform with neither tool, or one whose tool fails a probe, has
no jail; the plan then refuses a test-graded run unless the operator passes
`--allow-unjailed-checks`.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

SANDBOX_EXEC = "sandbox-exec"
BWRAP = "bwrap"
PROBE_TIMEOUT_SECONDS = 30
# Device files a test runner writes to; everything else outside the jail is read-only.
_WRITABLE_DEVICES = ("/dev/null", "/dev/zero", "/dev/stdout", "/dev/stderr", "/dev/tty")


def _sbpl_string(path: Path) -> str:
    return '"' + str(path).replace("\\", "\\\\").replace('"', '\\"') + '"'


def sandbox_exec_profile(writable: Sequence[Path]) -> str:
    """A `sandbox-exec` profile: allow everything except network and writes outside `writable`."""
    subpaths = " ".join(f"(subpath {_sbpl_string(path)})" for path in writable)
    devices = " ".join(f'(literal "{device}")' for device in _WRITABLE_DEVICES)
    return (
        "(version 1)\n"
        "(allow default)\n"
        "(deny network*)\n"
        "(deny file-write*)\n"
        f"(allow file-write* {subpaths} {devices})\n"
    )


@dataclass(frozen=True)
class CheckJail:
    """A way to jail one command: `tool` is `sandbox-exec` or `bwrap`, at `executable`."""

    tool: str
    executable: str

    def wrap(self, argv: Sequence[str], work_dir: Path, temp_dir: Path) -> list[str]:
        """`argv` run so that it can write only to `work_dir` and `temp_dir`, with no network."""
        writable = [work_dir.resolve(), temp_dir.resolve()]
        if self.tool == SANDBOX_EXEC:
            return [self.executable, "-p", sandbox_exec_profile(writable), *argv]
        binds = [arg for path in writable for arg in ("--bind", str(path), str(path))]
        return [
            self.executable,
            "--ro-bind",
            "/",
            "/",
            "--dev",
            "/dev",
            "--proc",
            "/proc",
            "--tmpfs",
            "/tmp",
            *binds,
            "--unshare-all",
            "--die-with-parent",
            "--new-session",
            "--chdir",
            str(work_dir.resolve()),
            *argv,
        ]


def candidate_jail(
    platform: str = sys.platform, which: Callable[[str], str | None] = shutil.which
) -> CheckJail | None:
    """The jail tool this platform would use, if it is installed; not yet probed."""
    tool = (
        SANDBOX_EXEC
        if platform == "darwin"
        else BWRAP
        if platform.startswith("linux")
        else None
    )
    if tool is None:
        return None
    executable = which(tool)
    return CheckJail(tool, executable) if executable else None


def probe(jail: CheckJail) -> bool:
    """True when the jail runs a command that writes inside it and is refused a write outside it."""
    with tempfile.TemporaryDirectory(prefix="model-effort-jail-") as root:
        inside, outside = Path(root) / "in", Path(root) / "out"
        inside.mkdir()
        outside.mkdir()
        code = (
            "import pathlib, sys\n"
            "pathlib.Path('ok').write_text('x')\n"
            "try:\n"
            f"    pathlib.Path({str(outside / 'escaped')!r}).write_text('x')\n"
            "except OSError:\n"
            "    sys.exit(0)\n"
            "sys.exit(3)\n"
        )
        argv = jail.wrap([sys.executable, "-c", code], inside, inside)
        try:
            completed = subprocess.run(
                argv,
                cwd=inside,
                capture_output=True,
                timeout=PROBE_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return (
            completed.returncode == 0
            and (inside / "ok").exists()
            and not (outside / "escaped").exists()
        )


def find_working_jail() -> CheckJail | None:
    """This platform's jail if it is installed and passes the probe, else None."""
    jail = candidate_jail()
    return jail if jail is not None and probe(jail) else None
