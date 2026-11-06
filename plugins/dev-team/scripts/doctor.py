#!/usr/bin/env python3
"""doctor.py - diagnose the installed dev-team plugin (``/doctor``).

Diagnoses by default and leaves the project unchanged; the only side effect is a
transient probe file created, and on a normal run removed, in ``.claude/metrics``. With ``--fix``,
creates the missing ``.claude/metrics`` and ``.claude/memory`` directories and
their missing ``.claude`` parent, and changes no other file.
Runs deterministic checks and prints each as ``ok``, ``warn`` or ``fail`` with
the command that repairs it. Exit 0 when the overall status is ``ok`` or
``warn``, 1 when it is ``fail`` or a ``--fix`` action failed, 2 on a usage error.

Stdlib only. The top level stays parseable by Python 3.8 and imports nothing
from the plugin at run time (type-only imports sit under ``TYPE_CHECKING``), so
a too-old interpreter reaches ``--probe`` and reports its version instead of
crashing; the 3.10 floor is enforced by the
``python-floor`` check, not by this module's syntax.
"""

from __future__ import annotations

import argparse
import dataclasses
import functools
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from doctor_checks import CheckContext
    from doctor_probe import ProbeResult
    from doctor_report import Check, Report

_HERE = Path(__file__).resolve().parent

PROBE_FLAG = "--probe"
PLUGIN_ROOT_ENV = "CLAUDE_PLUGIN_ROOT"
CONFIG_DIR_ENV = "CLAUDE_CONFIG_DIR"
PROBE_FILE_PREFIX = ".doctor-probe-"

DEFAULT_PROBE_TIMEOUT_SECONDS = 20
GIT_TIMEOUT_SECONDS = 10


def _use_lib_path() -> None:
    lib = str(_HERE / "lib")
    if lib not in sys.path:
        sys.path.insert(0, lib)


def _model():
    """The report-model module, imported lazily so ``--probe`` never needs it."""
    _use_lib_path()
    import doctor_report

    return doctor_report


def _probe():
    """The interpreter-probe module, imported lazily for the same reason as ``_model``."""
    _use_lib_path()
    import doctor_probe

    return doctor_probe


def _checks():
    """The checks module, imported lazily for the same reason as ``_model``."""
    _use_lib_path()
    import doctor_checks

    return doctor_checks


def _files():
    """The bounded-file-reader module, imported lazily for the same reason as ``_model``."""
    _use_lib_path()
    import doctor_files

    return doctor_files


def _format_internal_error(exc: Exception) -> str:
    return f"internal error: {type(exc).__name__}: {exc}"


def _run_isolated(
    check_id: str, check_fn: Callable[[CheckContext], Check], ctx: CheckContext
) -> Check:
    """Run one check under the id the table gives it.

    An exception, or a result that is not a ``Check``, becomes that check's
    ``fail`` result; whatever id the check function put on its result is
    replaced, so ``doctor_checks.CHECKS`` is the only place an id is spelled.
    """
    model = _model()
    try:
        result = check_fn(ctx)
        if not isinstance(result, model.Check):
            raise TypeError(f"check returned {type(result).__name__}, not a Check")
    except ImportError as exc:
        # A plugin helper module is missing: the install is incomplete.
        result = model.make_check(
            model.Status.FAIL, _format_internal_error(exc), model.UPGRADE_FIX
        )
    except Exception as exc:  # noqa: BLE001 -- isolation: any check failure becomes that check's fail result
        result = model.make_check(
            model.Status.FAIL, _format_internal_error(exc), model.REPORT_FIX
        )
    return dataclasses.replace(result, id=check_id)


def _apply_fixes_isolated(ctx: CheckContext) -> tuple[list[str], list[str]]:
    """``doctor_checks.apply_fixes`` under the isolation a check gets: a raise becomes one error.

    Whatever was created before the raise stays in ``fixed``.
    """
    fixed: list[str] = []
    errors: list[str] = []
    try:
        _checks().apply_fixes(ctx, fixed, errors)
    except Exception as exc:  # noqa: BLE001 -- isolation: the checks still run
        errors.append(f"{_model().FIX_FAILED_PREFIX}{type(exc).__name__}: {exc}")
    return fixed, errors


def run(
    ctx: CheckContext,
    fix: bool = False,
    checks: Iterable[tuple[str, Callable[[CheckContext], Check]]] | None = None,
) -> Report:
    """Run every check, each isolated, and collect the report.

    ``fix`` applies the safe repairs first, so the checks report the repaired state.
    """
    table = _checks().CHECKS if checks is None else checks
    fixed, errors = _apply_fixes_isolated(ctx) if fix else ([], [])
    return _model().Report(
        plugin_root=str(ctx.plugin_root),
        project_root=str(ctx.project_root),
        checks=[_run_isolated(check_id, check_fn, ctx) for check_id, check_fn in table],
        fixed=fixed,
        errors=errors,
    )


def _load_helper(plugin_root: Path, name: str):
    """Load plugin helper ``name`` from ``plugin_root``, on demand.

    Loaded by path, not through ``sys.path``, so the install being diagnosed is
    the one inspected and a missing or broken helper is an ``ImportError``
    (reported as an incomplete install) on every call. Nothing stays in
    ``sys.modules`` afterwards.
    """
    path = plugin_root.joinpath(*_checks().HELPER_DIRS[name], f"{name}.py")
    if not path.is_file():
        raise ImportError(f"{name} not found at {path}")
    spec = importlib.util.spec_from_file_location(name, path)
    assert (
        spec is not None and spec.loader is not None
    )  # a ``.py`` path always has both
    module = importlib.util.module_from_spec(spec)
    # ``@dataclass`` looks its own module up in sys.modules while it runs, so the
    # helper is registered for the load and the previous entry restored after.
    previous = sys.modules.get(name)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise ImportError(f"cannot load {name}: {exc}") from exc
    finally:
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous
    return module


def _plugin_root(env: Mapping[str, str]) -> Path:
    """``CLAUDE_PLUGIN_ROOT`` when it names a directory, else this script's plugin."""
    configured = env.get(PLUGIN_ROOT_ENV)
    if configured and Path(configured).is_dir():
        return Path(configured).resolve()
    return _HERE.parent


def _resolve_project(start: Path, run_process: Callable[..., Any]) -> tuple[Path, bool]:
    """``(project_root, in_git)`` from one ``git rev-parse --show-toplevel`` call.

    Exit 0 with a path: git's toplevel and True. A non-zero exit, empty output,
    git absent or a timeout: ``start`` itself and False.
    """
    try:
        completed = run_process(
            ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return start, False
    toplevel = completed.stdout.strip()
    if completed.returncode != 0 or not toplevel:
        return start, False
    return Path(toplevel).resolve(), True


def _probe_write(directory: Path) -> None:
    """Create and remove a uniquely named file in ``directory``; ``OSError`` if it cannot.

    The random suffix means a ``.doctor-probe-*`` left by an earlier crash never
    collides and is left untouched.
    """
    descriptor, name = tempfile.mkstemp(dir=directory, prefix=PROBE_FILE_PREFIX)
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

    def load_helper(self, name: str):
        """Plugin helper module ``name``, loaded from this context's plugin root."""
        return _load_helper(self.plugin_root, name)

    @functools.cached_property
    def _probe_result(self) -> ProbeResult:
        assert self.shim is not None and self.script is not None  # set in __post_init__
        return _probe().run_probe(
            self.shim, self.script, PROBE_FLAG, self.env, self.probe_timeout
        )

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

        ``run_process`` makes the one git call both ``project_root`` and
        ``in_git`` come from; tests inject a fake so no git runs.
        """
        plugin_root = _plugin_root(env)
        start = (args.project or Path.cwd()).resolve()
        project_root, in_git = _resolve_project(start, run_process)
        return cls(
            plugin_root=plugin_root,
            project_root=project_root,
            config_dir=Path(env.get(CONFIG_DIR_ENV) or Path.home() / ".claude"),
            env=env,
            in_git=in_git,
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
    runtime_dirs = ", ".join(f".claude/{name}" for name in _checks().RUNTIME_DIRS)
    parser = argparse.ArgumentParser(
        prog="doctor.py", description=DESCRIPTION, allow_abbrev=False
    )
    parser.add_argument("--json", action="store_true", help="print the JSON report")
    parser.add_argument(
        "--fix",
        action="store_true",
        help=f"create the missing {runtime_dirs} directories",
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
    failed = report.overall is _model().Status.FAIL
    return 1 if failed or report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
