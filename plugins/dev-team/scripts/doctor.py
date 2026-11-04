#!/usr/bin/env python3
"""doctor.py - diagnose the installed dev-team plugin (``/doctor``).

Read-only. Runs deterministic checks and prints each as ``ok``, ``warn`` or
``fail`` with the command that repairs it. Exit 0 when the overall status is
``ok`` or ``warn``, 1 when it is ``fail`` or a ``--fix`` action failed, 2 on a
usage error.

Stdlib only. The top level stays parseable by Python 3.8 and imports nothing
from the plugin, so a too-old interpreter reaches ``--probe`` and reports its
version instead of crashing; the 3.10 floor is enforced by the
``python-floor`` check, not by this module's syntax.
"""

from __future__ import annotations

import argparse
import dataclasses
import enum
import functools
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from doctor_report import Check, Report, Status

_HERE = Path(__file__).resolve().parent

ISSUES_URL = "https://github.com/bdfinst/agentic-dev-team/issues"

PROBE_FLAG = "--probe"
PLUGIN_ROOT_ENV = "CLAUDE_PLUGIN_ROOT"
CONFIG_DIR_ENV = "CLAUDE_CONFIG_DIR"
PY_CACHE_ENV = "DEV_TEAM_PY_CACHE"

UPGRADE_FIX = "/upgrade"
SETUP_FIX = "/setup"
INSTALL_FIX = "claude plugin install dev-team@bfinster"
REPORT_FIX = f"report this at {ISSUES_URL}"

DEFAULT_PROBE_TIMEOUT_SECONDS = 20

#: Where each plugin helper module lives, relative to the plugin root.
HELPER_DIRS = {
    "artifact_paths": ("hooks", "lib"),
    "autocompact_config": ("hooks", "lib"),
    "check_version_drift": ("skills", "upgrade", "scripts"),
}


def _model():
    """The report-model module, imported lazily so ``--probe`` never needs it."""
    lib = str(_HERE / "lib")
    if lib not in sys.path:
        sys.path.insert(0, lib)
    import doctor_report

    return doctor_report


def _status():
    """The ``Status`` enum, obtained lazily for the same reason as ``_model``."""
    return _model().Status


def _make_check(status: Status, summary: str, fix: str | None = None) -> Check:
    """An id-less ``Check``; ``_run_isolated`` stamps the id from ``CHECKS``."""
    return _model().Check("", status, summary, fix)


def _format_internal_error(exc: Exception) -> str:
    return f"internal error: {type(exc).__name__}: {exc}"


def _run_isolated(check_id: str, check_fn: Callable[..., Check], ctx) -> Check:
    """Run one check under the id the table gives it.

    An exception becomes that check's ``fail`` result; whatever id the check
    function put on its result is replaced, so ``CHECKS`` is the only place an
    id is spelled.
    """
    status = _status()
    try:
        result = check_fn(ctx)
    except ImportError as exc:
        # A plugin helper module is missing: the install is incomplete.
        result = _make_check(status.FAIL, _format_internal_error(exc), UPGRADE_FIX)
    except Exception as exc:  # noqa: BLE001 -- isolation: any check failure becomes that check's fail result
        result = _make_check(status.FAIL, _format_internal_error(exc), REPORT_FIX)
    return dataclasses.replace(result, id=check_id)


def run(
    ctx,
    fix: bool = False,
    checks: Iterable[tuple[str, Callable[..., Check]]] | None = None,
) -> Report:
    """Run every check, each isolated, and collect the report.

    ``fix`` is accepted for the CLI and does nothing yet.
    """
    table = CHECKS if checks is None else checks
    return _model().Report(
        plugin_root=str(ctx.plugin_root),
        project_root=str(ctx.project_root),
        checks=[_run_isolated(check_id, check_fn, ctx) for check_id, check_fn in table],
    )


def _helper(plugin_root: Path, name: str):
    """Load plugin helper ``name`` from ``plugin_root``, on demand.

    Loaded by path, not through ``sys.path``, so the install being diagnosed is
    the one inspected and a missing or broken helper is an ``ImportError``
    (reported as an incomplete install) on every call.
    """
    path = plugin_root.joinpath(*HELPER_DIRS[name], f"{name}.py")
    if not path.is_file():
        raise ImportError(f"{name} not found at {path}")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise ImportError(f"cannot load {name}: {exc}") from exc
    return module


def _plugin_root(env: Mapping[str, str]) -> Path:
    """``CLAUDE_PLUGIN_ROOT`` when it names a directory, else this script's plugin."""
    configured = env.get(PLUGIN_ROOT_ENV)
    if configured and Path(configured).is_dir():
        return Path(configured).resolve()
    return _HERE.parent


def _resolve_project_root(plugin_root: Path, start: Path) -> tuple[Path, bool]:
    """``(root, helper_loaded)``: the git toplevel of ``start``, else ``start``.

    ``helper_loaded`` is False when ``artifact_paths`` cannot be loaded; the
    root is then ``start`` and nothing was asked of git.
    """
    try:
        resolve = _helper(plugin_root, "artifact_paths").project_root
    except ImportError:
        return start, False
    return Path(resolve(start=start)), True


def _is_inside_git(project_root: Path, run_process: Callable[..., Any]) -> bool:
    """True when git resolves a toplevel for ``project_root``; git absent is False."""
    try:
        completed = run_process(
            ["git", "-C", str(project_root), "rev-parse", "--show-toplevel"],
            capture_output=True,
            timeout=DEFAULT_PROBE_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def _probe_write(directory: Path) -> None:
    """Create and remove a uniquely named file in ``directory``; ``OSError`` if it cannot.

    The random suffix means a ``.doctor-probe-*`` left by an earlier crash never
    collides and is left untouched.
    """
    descriptor, name = tempfile.mkstemp(dir=directory, prefix=".doctor-probe-")
    os.close(descriptor)
    os.unlink(name)


@dataclasses.dataclass(frozen=True)
class Context:
    """Everything a check reads. Tests construct it directly with temp roots."""

    plugin_root: Path
    project_root: Path
    config_dir: Path
    env: Mapping[str, str] = dataclasses.field(default_factory=dict)
    which: Callable[[str], str | None] = shutil.which
    shim: Path | None = None
    script: Path | None = None
    probe_timeout: float = DEFAULT_PROBE_TIMEOUT_SECONDS
    probe_write: Callable[[Path], None] = _probe_write
    in_git: bool = True

    def __post_init__(self) -> None:
        if self.shim is None:
            object.__setattr__(self, "shim", self.plugin_root / "hooks" / "py.sh")
        if self.script is None:
            object.__setattr__(
                self, "script", self.plugin_root / "scripts" / "doctor.py"
            )

    @functools.cached_property
    def _probe_result(self) -> ProbeResult:
        return _run_probe(self)

    def probe(self) -> ProbeResult:
        """The interpreter self-probe, run once per Context."""
        return self._probe_result

    @classmethod
    def from_args(
        cls,
        args,
        env: Mapping[str, str],
        run_process: Callable[..., Any] = subprocess.run,
    ) -> Context:
        """Resolve the roots, config dir and git membership from ``args`` and ``env``.

        ``run_process`` is how the one git membership call is made; tests inject
        a fake so no git runs.
        """
        plugin_root = _plugin_root(env)
        start = (args.project or Path.cwd()).resolve()
        project_root, helper_loaded = _resolve_project_root(plugin_root, start)
        return cls(
            plugin_root=plugin_root,
            project_root=project_root,
            config_dir=Path(env.get(CONFIG_DIR_ENV) or Path.home() / ".claude"),
            env=env,
            in_git=helper_loaded and _is_inside_git(project_root, run_process),
        )


def _version_tuple(text) -> tuple[int, ...] | None:
    """``"14.0.10"`` -> ``(14, 0, 10)``; anything that is not dotted digits -> None."""
    parts = text.split(".") if isinstance(text, str) else [""]
    if all(part.isascii() and part.isdigit() for part in parts):
        return tuple(int(part) for part in parts)
    return None


def _call_or_none(call, *args):
    """Run a helper lookup over untrusted JSON; a shape it cannot read is no answer."""
    try:
        return call(*args)
    except (AttributeError, TypeError, LookupError, ValueError):
        return None


def check_plugin_version(ctx: Context) -> Check:
    """Compare the installed plugin version with the cached marketplace catalog."""
    status = _status()
    drift = _helper(ctx.plugin_root, "check_version_drift")
    record_path = ctx.config_dir / "plugins" / "installed_plugins.json"
    if not record_path.is_file():
        return _make_check(
            status.WARN, f"no install record ({record_path})", INSTALL_FIX
        )
    installed_version, marketplace = _call_or_none(
        drift.installed, str(ctx.config_dir)
    ) or (None, None)
    if not installed_version:
        return _make_check(
            status.WARN,
            f"{record_path.name}: no usable version for dev-team",
            INSTALL_FIX,
        )
    catalog_version = _call_or_none(drift.latest, str(ctx.config_dir), marketplace)
    if not catalog_version:
        return _make_check(
            status.OK, f"{installed_version} installed; catalog not cached"
        )
    installed_tuple = _version_tuple(installed_version)
    offered_tuple = _version_tuple(catalog_version)
    if installed_tuple is None or offered_tuple is None:
        return _make_check(
            status.OK, f"cannot compare {installed_version} to {catalog_version}"
        )
    if offered_tuple > installed_tuple:
        return _make_check(
            status.WARN,
            f"{installed_version} installed, {catalog_version} available",
            UPGRADE_FIX,
        )
    return _make_check(
        status.OK, f"{installed_version} installed (catalog {catalog_version})"
    )


PLUGIN_ROOT_PREFIX = "${" + PLUGIN_ROOT_ENV + "}/"
SCRIPT_SUFFIXES = (".py", ".sh")


class LoadKind(enum.Enum):
    """How reading a JSON file ended."""

    MISSING = "missing"
    INVALID = "invalid"
    NOT_OBJECT = "not-object"
    OK = "ok"


#: How ``_load_json`` outcomes read in a summary: ``<file>: <phrase>``.
UNLOADABLE_PHRASES = {
    LoadKind.MISSING: "missing",
    LoadKind.INVALID: "invalid JSON",
    LoadKind.NOT_OBJECT: "not an object",
}


@dataclasses.dataclass(frozen=True)
class Loaded:
    """A JSON file read: ``kind`` says how, ``data`` is the object when ``OK``."""

    kind: LoadKind
    data: Any = None


def _load_json(path: Path) -> Loaded:
    """Read ``path`` as a JSON object; other OSErrors propagate to the caller."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, NotADirectoryError):
        return Loaded(LoadKind.MISSING)
    except ValueError:  # JSONDecodeError and UnicodeDecodeError
        return Loaded(LoadKind.INVALID)
    if not isinstance(data, dict):
        return Loaded(LoadKind.NOT_OBJECT)
    return Loaded(LoadKind.OK, data)


def _commands(node: Any) -> list[str]:
    """Every ``command`` string anywhere under ``node``, in document order."""
    if isinstance(node, dict):
        found = []
        for key, value in node.items():
            if key == "command" and isinstance(value, str):
                found.append(value)
            else:
                found.extend(_commands(value))
        return found
    if isinstance(node, list):
        return [command for item in node for command in _commands(item)]
    return []


def _script_tokens(command: str) -> list[str]:
    """The words of ``command`` that name a ``.py`` or ``.sh`` file, quotes stripped."""
    try:
        words = shlex.split(command)
    except ValueError:  # unbalanced quote: fall back to whitespace words
        words = [word.strip("\"'") for word in command.split()]
    return [word for word in words if word.endswith(SCRIPT_SUFFIXES)]


def _missing_scripts(plugin_root: Path, commands: list[str]) -> list[str]:
    """Script tokens that resolve to no file, once each, in first-seen order."""
    missing: list[str] = []
    for command in commands:
        for token in _script_tokens(command):
            relative_path = token.removeprefix(PLUGIN_ROOT_PREFIX)
            target = plugin_root / relative_path  # an absolute token replaces the root
            if not target.is_file() and relative_path not in missing:
                missing.append(relative_path)
    return missing


def check_hook_registration(ctx: Context) -> Check:
    """Every script a registered hook command names must exist."""
    status = _status()
    label = "hooks/hooks.json"
    loaded = _load_json(ctx.plugin_root / "hooks" / "hooks.json")
    if loaded.kind is not LoadKind.OK:
        phrase = UNLOADABLE_PHRASES[loaded.kind]
        return _make_check(status.FAIL, f"{label}: {phrase}", UPGRADE_FIX)
    hooks = loaded.data.get("hooks")
    if not isinstance(hooks, dict):
        return _make_check(status.FAIL, f"{label}: no hooks object", UPGRADE_FIX)
    commands = _commands(hooks)
    if not commands:
        return _make_check(status.FAIL, f"{label}: no hook commands", UPGRADE_FIX)
    missing = _missing_scripts(ctx.plugin_root, commands)
    if missing:
        return _make_check(status.FAIL, f"missing: {', '.join(missing)}", UPGRADE_FIX)
    return _make_check(
        status.OK, f"{len(commands)} hook commands, every script present"
    )


PYTHON_FLOOR = (3, 10)
INTERPRETER_FIX = "set DEV_TEAM_PYTHON to a Python 3 path"
FLOOR_FIX = "install Python 3.10+ (ADR 0031)"
#: Exit code py.sh uses for "no interpreter found".
SHIM_NO_INTERPRETER = 2

_PROBE_LINE = re.compile(r"(?P<path>.+) (?P<version>[0-9]+\.[0-9]+\.[0-9]+)")


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


def _run_probe(ctx: Context) -> ProbeResult:
    """Run the shim against the script's ``--probe`` mode, never touching the cache."""
    if not ctx.shim.is_file():
        return ProbeResult(False, detail=f"shim not found: {ctx.shim}")
    with tempfile.TemporaryDirectory() as scratch:
        env = {**ctx.env, PY_CACHE_ENV: str(Path(scratch) / "python")}
        try:
            completed = subprocess.run(
                ["sh", str(ctx.shim), str(ctx.script), PROBE_FLAG],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=ctx.probe_timeout,
                env=env,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return ProbeResult(
                False, detail=f"probe timed out after {ctx.probe_timeout} s"
            )
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


def check_interpreter(ctx: Context) -> Check:
    """py.sh must resolve a Python 3 that answers the ``--probe`` request."""
    status = _status()
    probe = ctx.probe()
    if not probe.resolved:
        return _make_check(status.FAIL, probe.detail, INTERPRETER_FIX)
    return _make_check(status.OK, f"py.sh resolved {probe.path}")


def check_python_floor(ctx: Context) -> Check:
    """The interpreter py.sh resolves must meet the shipped Python floor."""
    status = _status()
    probe = ctx.probe()
    if probe.version is None:
        return _make_check(status.FAIL, "no interpreter resolved", FLOOR_FIX)
    dotted = ".".join(str(part) for part in probe.version)
    if probe.version[:2] < PYTHON_FLOOR:
        floor = ".".join(str(part) for part in PYTHON_FLOOR)
        return _make_check(
            status.FAIL, f"{probe.path} is {dotted}; floor is {floor}", FLOOR_FIX
        )
    return _make_check(status.OK, f"{probe.path} is {dotted}")


REQUIRED_TOOLS = ("jq",)
OPTIONAL_TOOLS = ("gh", "semgrep", "adr", "shellcheck", "uv")


def _partition_by_availability(
    ctx: Context, names: tuple[str, ...]
) -> tuple[list[str], list[str]]:
    """Split ``names`` into those ``ctx.which`` finds and those it does not."""
    present = [name for name in names if ctx.which(name)]
    return present, [name for name in names if name not in present]


def _join_or_none(names: list[str]) -> str:
    return ", ".join(names) or "none"


def check_required_tools(ctx: Context) -> Check:
    """``jq`` backs the shell hooks; its absence degrades them, so it only warns."""
    status = _status()
    present, absent = _partition_by_availability(ctx, REQUIRED_TOOLS)
    if not absent:
        return _make_check(status.OK, f"{', '.join(present)} on PATH")
    return _make_check(
        status.WARN,
        f"{', '.join(absent)} not on PATH (manual: brew install {' '.join(absent)})",
        SETUP_FIX,
    )


def check_optional_tools(ctx: Context) -> Check:
    """Optional tools only extend what the plugin can do; absence is never a problem."""
    present, absent = _partition_by_availability(ctx, OPTIONAL_TOOLS)
    return _make_check(
        _status().OK,
        f"present: {_join_or_none(present)}; absent: {_join_or_none(absent)}",
    )


CHECKS = (
    ("plugin-version", check_plugin_version),
    ("hook-registration", check_hook_registration),
    ("interpreter", check_interpreter),
    ("python-floor", check_python_floor),
    ("required-tools", check_required_tools),
    ("optional-tools", check_optional_tools),
)

DESCRIPTION = (
    "Diagnose the installed dev-team plugin and report each check as ok, warn "
    "or fail with the command that repairs it. Exit codes: 0 when the overall "
    "status is ok or warn; 1 when a check failed or a --fix action failed; "
    "2 on a usage error."
)


def _directory(text: str) -> Path:
    """argparse ``type=`` for ``--project``: an existing directory."""
    path = Path(text)
    if not path.is_dir():
        raise argparse.ArgumentTypeError(f"not a directory: {text}")
    return path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="doctor.py", description=DESCRIPTION, allow_abbrev=False
    )
    parser.add_argument("--json", action="store_true", help="print the JSON report")
    parser.add_argument(
        "--fix",
        action="store_true",
        help="create the missing .claude/metrics and .claude/memory directories",
    )
    parser.add_argument(
        "--project",
        type=_directory,
        metavar="DIR",
        help="diagnose the project containing DIR (default: the current directory)",
    )
    # Internal: main() answers it before argparse runs; registered so it parses.
    parser.add_argument(PROBE_FLAG, action="store_true", help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if PROBE_FLAG in argv:  # before any import beyond the standard library
        version = sys.version_info
        print(f"{sys.executable} {version[0]}.{version[1]}.{version[2]}")
        return 0
    args = _parser().parse_args(argv)
    ctx = Context.from_args(args, dict(os.environ))
    report = run(ctx, fix=args.fix)
    for line in report.errors:
        print(line, file=sys.stderr)
    if args.json:
        print(json.dumps(report.to_json(), indent=2))
    else:
        print(
            _model().format_human(report, ctx.in_git, fix_ran=args.fix),
            end="",
        )
    failed = report.overall is _status().FAIL
    return 1 if failed or report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
