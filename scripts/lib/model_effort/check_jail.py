"""Jail the fixture's test commands, which run code the agent wrote.

A jailed command may write only inside the trial's working copy and its own
temp dir, and has no network. macOS uses `sandbox-exec`; Linux uses `bwrap`
(bubblewrap).

On macOS the profile also refuses Launch Services opens (`lsopen`), Apple
events and preference writes (`defaults write`, which `cfprefsd` would make
outside the jail), and denies every Mach service except an allowlist the usual
test tools need (user lookups, notifications, logging, preference reads), so a
command cannot ask another, unjailed process to act for it. `launchctl submit`
is refused by launchd for a sandboxed caller. On Linux the jail runs in new
namespaces with an empty `/run` (and `/var/run`), so the user's D-Bus session
bus and the Docker socket are not reachable, and the bus variables are unset.

Reads are not confined: the command can still read files the user can read,
so the answer key lives in a directory no prompt names (see `snapshot`). A
platform with neither tool, or one whose tool fails a probe, has no jail; the
plan then refuses a test-graded run unless the operator passes
`--allow-unjailed-checks`.
"""

from __future__ import annotations

import os
import shutil
import socket
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
# The only Mach services a jailed command may look up; every other is denied, so
# no service can act for it outside the jail. User and group lookups (`getpwuid`,
# which Python, Node and git make), notifications, logging, and preference reads
# (writes are refused separately). pytest, node, git and npx run with only these.
ALLOWED_MACH_SERVICES = (
    "com.apple.system.opendirectoryd.libinfo",
    "com.apple.system.opendirectoryd.membership",
    "com.apple.system.notification_center",
    "com.apple.system.logger",
    "com.apple.logd",
    "com.apple.diagnosticd",
    "com.apple.cfprefsd.daemon",
    "com.apple.cfprefsd.agent",
)
# Variables that point a process at the user's session bus or runtime dir.
_SESSION_ENV_NAMES = ("DBUS_SESSION_BUS_ADDRESS", "XDG_RUNTIME_DIR")
# Runtime dirs hidden under an empty tmpfs: the session bus, the Docker socket.
_HIDDEN_RUNTIME_DIRS = ("/run", "/var/run")


def _sbpl_string(path: Path) -> str:
    return '"' + str(path).replace("\\", "\\\\").replace('"', '\\"') + '"'


def sandbox_exec_profile(writable: Sequence[Path]) -> str:
    """A `sandbox-exec` profile: allow everything except network, writes outside
    `writable`, Launch Services opens, Apple events, preference writes and any
    Mach service not in `ALLOWED_MACH_SERVICES`."""
    subpaths = " ".join(f"(subpath {_sbpl_string(path)})" for path in writable)
    devices = " ".join(f'(literal "{device}")' for device in _WRITABLE_DEVICES)
    services = " ".join(f'(global-name "{name}")' for name in ALLOWED_MACH_SERVICES)
    return (
        "(version 1)\n"
        "(allow default)\n"
        "(deny network*)\n"
        "(deny file-write*)\n"
        f"(allow file-write* {subpaths} {devices})\n"
        "(deny lsopen)\n"
        "(deny appleevent-send)\n"
        "(deny user-preference-write)\n"
        "(deny mach-lookup)\n"
        f"(allow mach-lookup {services})\n"
    )


def _hidden_runtime_dirs(is_symlink: Callable[[str], bool]) -> list[str]:
    """`/run`, and `/var/run` too when it is a real directory rather than a link to `/run`."""
    return [
        path
        for path in _HIDDEN_RUNTIME_DIRS
        if path == _HIDDEN_RUNTIME_DIRS[0] or not is_symlink(path)
    ]


@dataclass(frozen=True)
class CheckJail:
    """A way to jail one command: `tool` is `sandbox-exec` or `bwrap`, at `executable`."""

    tool: str
    executable: str

    def wrap(
        self,
        argv: Sequence[str],
        work_dir: Path,
        temp_dir: Path,
        is_symlink: Callable[[str], bool] = os.path.islink,
    ) -> list[str]:
        """`argv` run so that it can write only to `work_dir` and `temp_dir`, with no network."""
        writable = [work_dir.resolve(), temp_dir.resolve()]
        if self.tool == SANDBOX_EXEC:
            return [self.executable, "-p", sandbox_exec_profile(writable), *argv]
        binds = [arg for path in writable for arg in ("--bind", str(path), str(path))]
        hidden = [
            arg for path in _hidden_runtime_dirs(is_symlink) for arg in ("--tmpfs", path)
        ]
        unset = [arg for name in _SESSION_ENV_NAMES for arg in ("--unsetenv", name)]
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
            *hidden,
            *binds,
            *unset,
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


# A harmless Launch Services open: Finder always runs, and `-g` keeps it in the background.
_LSOPEN_PROBE_ARGV = ("/usr/bin/open", "-g", "-a", "Finder")
# A preference domain the probe tries to write; removed again whatever happens.
PREFERENCE_PROBE_DOMAIN = "com.example.model-effort-jail-probe"
_DEFAULTS = "/usr/bin/defaults"
_SESSION_BUS_TEMPLATE = "/run/user/{uid}/bus"
_DOCKER_SOCKET = "/var/run/docker.sock"
def _probe_script(
    outside: Path, port: int, lsopen: bool, session_bus: str | None, docker: bool
) -> str:
    """The jailed half of `probe`: exit 0 only when every escape it tries is refused.

    A nonzero exit names the escape: 3 wrote outside, 4 reached the network, 5
    opened through Launch Services, 6 reached the session bus, 7 saw the Docker
    socket, 8 wrote a preference. `lsopen` turns on the macOS cases (5 and 8).
    """
    return (
        "import os, pathlib, socket, subprocess, sys\n"
        "pathlib.Path('ok').write_text('x')\n"
        "try:\n"
        f"    pathlib.Path({str(outside / 'escaped')!r}).write_text('x')\n"
        "    sys.exit(3)\n"
        "except OSError:\n"
        "    pass\n"
        "try:\n"
        f"    socket.create_connection(('127.0.0.1', {port}), timeout=5).close()\n"
        "    sys.exit(4)\n"
        "except OSError:\n"
        "    pass\n"
        + (
            f"if subprocess.run({list(_LSOPEN_PROBE_ARGV)!r}, capture_output=True,"
            " timeout=20).returncode == 0:\n"
            "    sys.exit(5)\n"
            f"if subprocess.run([{_DEFAULTS!r}, 'write', {PREFERENCE_PROBE_DOMAIN!r},"
            " 'probe', 'x'], capture_output=True, timeout=20).returncode == 0:\n"
            "    sys.exit(8)\n"
            if lsopen
            else ""
        )
        + (
            "try:\n"
            "    s = socket.socket(socket.AF_UNIX)\n"
            f"    s.connect({session_bus!r})\n"
            "    sys.exit(6)\n"
            "except OSError:\n"
            "    pass\n"
            if session_bus
            else ""
        )
        + (f"if os.path.exists({_DOCKER_SOCKET!r}):\n    sys.exit(7)\n" if docker else "")
        + "sys.exit(0)\n"
    )


def probe(jail: CheckJail) -> bool:
    """True when the jail runs a command that writes inside it and refuses every escape tried.

    The jailed command must be refused a write outside the jail and a connection
    to a socket the harness listens on at 127.0.0.1. Under `sandbox-exec` it must
    also fail to open an app through Launch Services and to write a preference
    (`defaults write`; the probe domain is deleted afterwards). Under `bwrap` it must fail
    to reach the user's session bus and see no Docker socket, each checked only
    when the host has one.
    """
    session_bus = _SESSION_BUS_TEMPLATE.format(uid=os.getuid())
    with (
        tempfile.TemporaryDirectory(prefix="model-effort-jail-") as root,
        socket.create_server(("127.0.0.1", 0)) as listener,
    ):
        inside, outside = Path(root) / "in", Path(root) / "out"
        inside.mkdir()
        outside.mkdir()
        code = _probe_script(
            outside,
            listener.getsockname()[1],
            lsopen=jail.tool == SANDBOX_EXEC,
            session_bus=session_bus
            if jail.tool == BWRAP and os.path.exists(session_bus)
            else None,
            docker=jail.tool == BWRAP and os.path.exists(_DOCKER_SOCKET),
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
        finally:
            if jail.tool == SANDBOX_EXEC:
                _delete_probe_domain()
        return (
            completed.returncode == 0
            and (inside / "ok").exists()
            and not (outside / "escaped").exists()
        )


def _delete_probe_domain() -> None:
    try:
        subprocess.run(
            [_DEFAULTS, "delete", PREFERENCE_PROBE_DOMAIN],
            capture_output=True,
            timeout=PROBE_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass  # Nothing was written, or nothing more can be done.


def find_working_jail() -> CheckJail | None:
    """This platform's jail if it is installed and passes the probe, else None."""
    jail = candidate_jail()
    return jail if jail is not None and probe(jail) else None
