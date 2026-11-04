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
    from doctor_report import Check, Report

_HERE = Path(__file__).resolve().parent

ISSUES_URL = "https://github.com/bdfinst/agentic-dev-team/issues"

OK = "ok"
WARN = "warn"
FAIL = "fail"

DEFAULT_PROBE_TIMEOUT = 20

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


def _check(check_id: str, status: str, summary: str, fix: str | None = None):
    """Build a ``Check`` from a plain status string."""
    model = _model()
    return model.Check(check_id, model.Status(status), summary, fix)


def _isolated(check_id: str, check: Callable[..., Check], context) -> Check:
    """Run one check; an exception becomes that check's ``fail`` result."""
    try:
        return check(context)
    except ImportError as exc:
        # A plugin helper module is missing: the install is incomplete.
        return _check(check_id, FAIL, _internal_error(exc), "/upgrade")
    except Exception as exc:  # noqa: BLE001 -- isolation: any check failure becomes that check's fail result
        return _check(
            check_id, FAIL, _internal_error(exc), f"report this at {ISSUES_URL}"
        )


def _internal_error(exc: Exception) -> str:
    return f"internal error: {type(exc).__name__}: {exc}"


def run(
    context,
    fix: bool = False,
    checks: Iterable[tuple[str, Callable[..., Check]]] | None = None,
) -> Report:
    """Run every check, each isolated, and collect the report.

    ``fix`` is accepted for the CLI and does nothing yet.
    """
    model = _model()
    table = CHECKS if checks is None else checks
    return model.Report(
        plugin_root=str(context.plugin_root),
        project_root=str(context.project_root),
        checks=[_isolated(check_id, check, context) for check_id, check in table],
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
    configured = env.get("CLAUDE_PLUGIN_ROOT")
    if configured and Path(configured).is_dir():
        return Path(configured).resolve()
    return _HERE.parent


def _project_root(plugin_root: Path, start: Path) -> Path:
    """The git toplevel of ``start``; ``start`` itself when that cannot be resolved."""
    try:
        resolve = _helper(plugin_root, "artifact_paths").project_root
    except ImportError:
        return start
    return Path(resolve(start=start))


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
    probe_timeout: float = DEFAULT_PROBE_TIMEOUT

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
    def from_args(cls, args, env: Mapping[str, str]) -> Context:
        """Resolve the roots and config dir from the CLI arguments and ``env``."""
        plugin_root = _plugin_root(env)
        start = (args.project or Path.cwd()).resolve()
        return cls(
            plugin_root=plugin_root,
            project_root=_project_root(plugin_root, start),
            config_dir=Path(env.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude"),
            env=env,
        )


def _version_tuple(text) -> tuple[int, ...] | None:
    """``"14.0.10"`` -> ``(14, 0, 10)``; anything that is not dotted digits -> None."""
    parts = text.split(".") if isinstance(text, str) else [""]
    if all(part.isascii() and part.isdigit() for part in parts):
        return tuple(int(part) for part in parts)
    return None


def _guarded(call, *args):
    """Run a helper lookup over untrusted JSON; a shape it cannot read is no answer."""
    try:
        return call(*args)
    except (AttributeError, TypeError):
        return None


def check_plugin_version(ctx: Context):
    """Compare the installed plugin version with the cached marketplace catalog."""
    drift = _helper(ctx.plugin_root, "check_version_drift")
    record = ctx.config_dir / "plugins" / "installed_plugins.json"
    install_fix = "claude plugin install dev-team@bfinster"
    if not record.is_file():
        return _check(
            "plugin-version", WARN, f"no install record ({record})", install_fix
        )
    installed, market = _guarded(drift.installed, str(ctx.config_dir)) or (None, None)
    if not installed:
        return _check(
            "plugin-version",
            WARN,
            f"{record.name}: no usable version for dev-team",
            install_fix,
        )
    catalog = _guarded(drift.latest, str(ctx.config_dir), market)
    if not catalog:
        return _check(
            "plugin-version", OK, f"{installed} installed; catalog not cached"
        )
    have, offered = _version_tuple(installed), _version_tuple(catalog)
    if have is None or offered is None:
        return _check("plugin-version", OK, f"cannot compare {installed} to {catalog}")
    if offered > have:
        return _check(
            "plugin-version",
            WARN,
            f"{installed} installed, {catalog} available",
            "/upgrade",
        )
    return _check("plugin-version", OK, f"{installed} installed (catalog {catalog})")


PLUGIN_ROOT_PREFIX = "${CLAUDE_PLUGIN_ROOT}/"
SCRIPT_SUFFIXES = (".py", ".sh")

#: How ``_load_json`` outcomes read in a summary: ``<file>: <phrase>``.
UNLOADABLE_PHRASES = {
    "missing": "missing",
    "invalid": "invalid JSON",
    "not-object": "not an object",
}


@dataclasses.dataclass(frozen=True)
class Loaded:
    """A JSON file read: ``kind`` is ``missing``, ``invalid``, ``not-object`` or ``ok``."""

    kind: str
    data: Any = None


def _load_json(path: Path) -> Loaded:
    """Read ``path`` as a JSON object; other OSErrors propagate to the caller."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, NotADirectoryError):
        return Loaded("missing")
    except ValueError:  # JSONDecodeError and UnicodeDecodeError
        return Loaded("invalid")
    if not isinstance(data, dict):
        return Loaded("not-object")
    return Loaded("ok", data)


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
            shown = token.removeprefix(PLUGIN_ROOT_PREFIX)
            target = plugin_root / shown  # an absolute token replaces the root
            if not target.is_file() and shown not in missing:
                missing.append(shown)
    return missing


def check_hook_registration(ctx: Context):
    """Every script a registered hook command names must exist."""
    label = "hooks/hooks.json"
    loaded = _load_json(ctx.plugin_root / "hooks" / "hooks.json")
    if loaded.kind != "ok":
        phrase = UNLOADABLE_PHRASES[loaded.kind]
        return _check("hook-registration", FAIL, f"{label}: {phrase}", "/upgrade")
    hooks = loaded.data.get("hooks")
    if not isinstance(hooks, dict):
        return _check(
            "hook-registration", FAIL, f"{label}: no hooks object", "/upgrade"
        )
    commands = _commands(hooks)
    if not commands:
        return _check(
            "hook-registration", FAIL, f"{label}: no hook commands", "/upgrade"
        )
    missing = _missing_scripts(ctx.plugin_root, commands)
    if missing:
        return _check(
            "hook-registration", FAIL, f"missing: {', '.join(missing)}", "/upgrade"
        )
    return _check(
        "hook-registration", OK, f"{len(commands)} hook commands, every script present"
    )


PYTHON_FLOOR = (3, 10)
INTERPRETER_FIX = "set DEV_TEAM_PYTHON to a Python 3 path"
FLOOR_FIX = "install Python 3.10+ (ADR 0031)"
#: Exit code py.sh uses for "no interpreter found".
SHIM_NO_INTERPRETER = 2

_PROBE_LINE = re.compile(r"(?P<path>.+) (?P<version>[0-9]+\.[0-9]+\.[0-9]+)")


@dataclasses.dataclass(frozen=True)
class ProbeResult:
    """What ``sh py.sh doctor.py --probe`` yielded: ``detail`` says why not ``ok``."""

    ok: bool
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
        env = {**ctx.env, "DEV_TEAM_PY_CACHE": str(Path(scratch) / "python")}
        try:
            done = subprocess.run(
                ["sh", str(ctx.shim), str(ctx.script), "--probe"],
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
    reason = _first_stderr_line(done.stderr)
    if done.returncode == SHIM_NO_INTERPRETER:
        return ProbeResult(
            False, detail=_with_detail("py.sh found no interpreter", reason)
        )
    if done.returncode != 0:
        return ProbeResult(
            False, detail=_with_detail(f"probe exited {done.returncode}", reason)
        )
    parsed = _parse_probe(done.stdout)
    if parsed is None:
        return ProbeResult(False, detail="probe printed no version line")
    return ProbeResult(True, path=parsed[0], version=parsed[1])


def check_interpreter(ctx: Context):
    """py.sh must resolve a Python 3 that answers the ``--probe`` request."""
    probe = ctx.probe()
    if not probe.ok:
        return _check("interpreter", FAIL, probe.detail, INTERPRETER_FIX)
    return _check("interpreter", OK, f"py.sh resolved {probe.path}")


def check_python_floor(ctx: Context):
    """The interpreter py.sh resolves must meet the shipped Python floor."""
    probe = ctx.probe()
    if probe.version is None:
        return _check("python-floor", FAIL, "no interpreter resolved", FLOOR_FIX)
    dotted = ".".join(str(part) for part in probe.version)
    if probe.version[:2] < PYTHON_FLOOR:
        floor = ".".join(str(part) for part in PYTHON_FLOOR)
        return _check(
            "python-floor",
            FAIL,
            f"{probe.path} is {dotted}; floor is {floor}",
            FLOOR_FIX,
        )
    return _check("python-floor", OK, f"{probe.path} is {dotted}")


REQUIRED_TOOL = "jq"
OPTIONAL_TOOLS = ("gh", "semgrep", "adr", "shellcheck", "uv")
GIT_PROBE_TIMEOUT = 10


def _which_set(ctx: Context, names: tuple[str, ...]) -> tuple[list[str], list[str]]:
    """Split ``names`` into those ``ctx.which`` finds and those it does not."""
    present = [name for name in names if ctx.which(name)]
    return present, [name for name in names if name not in present]


def _listing(names: list[str]) -> str:
    return ", ".join(names) or "none"


def check_required_tools(ctx: Context):
    """``jq`` backs the shell hooks; its absence degrades them, so it only warns."""
    if ctx.which(REQUIRED_TOOL):
        return _check("required-tools", OK, f"{REQUIRED_TOOL} on PATH")
    return _check(
        "required-tools",
        WARN,
        f"{REQUIRED_TOOL} not on PATH (manual: brew install {REQUIRED_TOOL})",
        "/setup",
    )


def check_optional_tools(ctx: Context):
    """Optional tools only extend what the plugin can do; absence is never a problem."""
    present, absent = _which_set(ctx, OPTIONAL_TOOLS)
    return _check(
        "optional-tools",
        OK,
        f"present: {_listing(present)}; absent: {_listing(absent)}",
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
    parser.add_argument("--probe", action="store_true", help=argparse.SUPPRESS)
    return parser


def _in_git_repository(directory: Path) -> bool:
    try:
        done = subprocess.run(
            ["git", "-C", str(directory), "rev-parse", "--show-toplevel"],
            capture_output=True,
            timeout=GIT_PROBE_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return done.returncode == 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    if "--probe" in args:  # before any import beyond the standard library
        version = sys.version_info
        print(f"{sys.executable} {version[0]}.{version[1]}.{version[2]}")
        return 0
    parsed = _parser().parse_args(args)
    context = Context.from_args(parsed, dict(os.environ))
    report = run(context, fix=parsed.fix)
    for line in report.errors:
        print(line, file=sys.stderr)
    if parsed.json:
        print(json.dumps(report.to_json(), indent=2))
    else:
        text = _model().format_human(
            report, _in_git_repository(context.project_root), fix_ran=parsed.fix
        )
        print(text, end="")
    failed = report.overall.value == FAIL
    return 1 if failed or report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
