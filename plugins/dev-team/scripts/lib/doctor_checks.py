"""doctor_checks.py - the nine ``/doctor`` checks and their table.

Each check takes a ``CheckContext`` (``doctor.Context`` satisfies it) and returns
an id-less ``Check``; the runner in ``scripts/doctor.py`` stamps the id from
``CHECKS`` and isolates a check that raises. Everything a check reads comes
through its context (roots, config dir, ``which``, the interpreter probe,
``probe_write``, ``load_helper``), so tests drive it with temp directories and
fakes.

Stdlib only, plus ``doctor_report`` and ``doctor_files``. The top level stays
parseable by Python 3.8 (see ``doctor.py``). Plugin helper modules are reached
only through ``ctx.load_helper(name)``, inside function bodies. Also owns the runtime layout
(``CLAUDE_DIR_NAME``, ``RUNTIME_DIRS``, ``runtime_dir``, ``directory_blocker``)
and ``apply_fixes``, which share one blocker predicate with
``check_metrics_writable``.
"""

from __future__ import annotations

import errno
import re
import shlex
import stat
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple, Protocol

from doctor_files import LoadKind, LoadResult, load_json, read_bounded
from doctor_report import (
    INSTALL_FIX,
    SETUP_FIX,
    UPGRADE_FIX,
    Check,
    Status,
    abs_path,
    edit_fix,
    make_check,
)

if TYPE_CHECKING:
    from doctor_probe import ProbeResult

DOCTOR_FIX = "/doctor --fix"
CLAUDE_DIR_NAME = ".claude"
#: The directories under ``<project>/.claude`` that ``/doctor --fix`` creates.
RUNTIME_DIRS = ("metrics", "memory")
_ABSENT = object()  # a JSON key that is not there, as distinct from null


class CheckContext(Protocol):
    """What a check may read; ``doctor.Context`` is the one real implementation."""

    @property
    def plugin_root(self) -> Path: ...

    @property
    def project_root(self) -> Path: ...

    @property
    def config_dir(self) -> Path: ...

    @property
    def which(self) -> Callable[[str], str | None]: ...

    @property
    def probe_write(self) -> Callable[[Path], None]: ...

    def probe(self) -> ProbeResult: ...

    def load_helper(self, name: str) -> Any: ...


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


def check_plugin_version(ctx: CheckContext) -> Check:
    """Compare the installed plugin version with the cached marketplace catalog."""
    drift = ctx.load_helper("check_version_drift")
    record_path = ctx.config_dir / "plugins" / "installed_plugins.json"
    if not record_path.is_file():
        return make_check(
            Status.WARN, f"no install record ({record_path})", INSTALL_FIX
        )
    installed_version, marketplace = _call_or_none(
        drift.installed, str(ctx.config_dir)
    ) or (None, None)
    if not installed_version:
        return make_check(
            Status.WARN,
            f"{record_path.name}: no usable version for dev-team",
            INSTALL_FIX,
        )
    catalog_version = _call_or_none(drift.latest, str(ctx.config_dir), marketplace)
    if not catalog_version:
        return make_check(
            Status.OK, f"{installed_version} installed; catalog not cached"
        )
    installed_tuple = _version_tuple(installed_version)
    offered_tuple = _version_tuple(catalog_version)
    if installed_tuple is None or offered_tuple is None:
        return make_check(
            Status.OK, f"cannot compare {installed_version} to {catalog_version}"
        )
    if offered_tuple > installed_tuple:
        return make_check(
            Status.WARN,
            f"{installed_version} installed, {catalog_version} available",
            UPGRADE_FIX,
        )
    return make_check(
        Status.OK, f"{installed_version} installed (catalog {catalog_version})"
    )


PLUGIN_ROOT_PREFIX = "${CLAUDE_PLUGIN_ROOT}/"
SCRIPT_SUFFIXES = (".py", ".sh")

#: How unloadable outcomes read in a summary: ``<file>: <phrase>``.
UNLOADABLE_PHRASES = {
    LoadKind.MISSING: "missing",
    LoadKind.NOT_REGULAR: "not a regular file",
    LoadKind.TOO_LARGE: "too large",
    LoadKind.INVALID: "invalid JSON",
    LoadKind.NOT_OBJECT: "not an object",
}


def _unloadable(label: str, loaded: LoadResult, fix: str) -> Check:
    """The ``fail`` result for a file that did not load: ``<label>: <phrase>``."""
    phrase = UNLOADABLE_PHRASES[loaded.kind]
    return make_check(Status.FAIL, f"{label}: {phrase}", fix)


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


def check_hook_registration(ctx: CheckContext) -> Check:
    """Every script a registered hook command names must exist."""
    label = "hooks/hooks.json"
    loaded = load_json(ctx.plugin_root / "hooks" / "hooks.json")
    if loaded.kind is not LoadKind.LOADED:
        return _unloadable(label, loaded, UPGRADE_FIX)
    hooks = loaded.data.get("hooks")
    if not isinstance(hooks, dict):
        return make_check(Status.FAIL, f"{label}: no hooks object", UPGRADE_FIX)
    commands = _commands(hooks)
    if not commands:
        return make_check(Status.FAIL, f"{label}: no hook commands", UPGRADE_FIX)
    missing = _missing_scripts(ctx.plugin_root, commands)
    if missing:
        return make_check(Status.FAIL, f"missing: {', '.join(missing)}", UPGRADE_FIX)
    return make_check(Status.OK, f"{len(commands)} hook commands, every script present")


PYTHON_FLOOR = (3, 10)
INTERPRETER_FIX = "set DEV_TEAM_PYTHON to a Python 3 path"
FLOOR_FIX = "install Python 3.10+ (ADR 0031)"


def check_interpreter(ctx: CheckContext) -> Check:
    """py.sh must resolve a Python 3 that answers the ``--probe`` request."""
    probe = ctx.probe()
    if not probe.resolved:
        return make_check(Status.FAIL, probe.detail, INTERPRETER_FIX)
    return make_check(Status.OK, f"py.sh resolved {probe.path}")


def _dotted(version: tuple[int, ...]) -> str:
    """``(3, 10)`` -> ``"3.10"``."""
    return ".".join(str(part) for part in version)


def check_python_floor(ctx: CheckContext) -> Check:
    """The interpreter py.sh resolves must meet the shipped Python floor."""
    probe = ctx.probe()
    if probe.version is None:
        return make_check(Status.FAIL, "no interpreter resolved", FLOOR_FIX)
    dotted = _dotted(probe.version)
    if probe.version[:2] < PYTHON_FLOOR:
        return make_check(
            Status.FAIL,
            f"{probe.path} is {dotted}; floor is {_dotted(PYTHON_FLOOR)}",
            FLOOR_FIX,
        )
    return make_check(Status.OK, f"{probe.path} is {dotted}")


REQUIRED_TOOLS = ("jq",)
OPTIONAL_TOOLS = ("gh", "semgrep", "adr", "shellcheck", "uv")


def _partition_by_availability(
    ctx: CheckContext, names: tuple[str, ...]
) -> tuple[list[str], list[str]]:
    """Split ``names`` into those ``ctx.which`` finds and those it does not."""
    present = [name for name in names if ctx.which(name)]
    return present, [name for name in names if name not in present]


def _join_or_none(names: list[str]) -> str:
    return ", ".join(names) or "none"


def check_required_tools(ctx: CheckContext) -> Check:
    """``jq`` backs the shell hooks; its absence degrades them, so it only warns."""
    present, absent = _partition_by_availability(ctx, REQUIRED_TOOLS)
    if not absent:
        return make_check(Status.OK, f"{', '.join(present)} on PATH")
    return make_check(
        Status.WARN,
        f"{', '.join(absent)} not on PATH (manual: brew install {' '.join(absent)})",
        SETUP_FIX,
    )


def check_optional_tools(ctx: CheckContext) -> Check:
    """Optional tools only extend what the plugin can do; absence is never a problem."""
    present, absent = _partition_by_availability(ctx, OPTIONAL_TOOLS)
    return make_check(
        Status.OK,
        f"present: {_join_or_none(present)}; absent: {_join_or_none(absent)}",
    )


def _mv_aside_fix(where: str) -> str:
    """The shell command that moves ``where`` aside, then lets ``--fix`` recreate it."""
    return f"mv {shlex.quote(where)} {shlex.quote(where + '.bak')} && {DOCTOR_FIX}"


def _make_writable_fix(where: str) -> str:
    """The shell command that gives the owner write permission on ``where``."""
    return f"chmod u+w {shlex.quote(where)}"


def runtime_dir(project_root: Path, name: str) -> Path:
    """``<project_root>/.claude/<name>``: the one place the runtime layout is spelled."""
    return project_root / CLAUDE_DIR_NAME / name


#: ``stat`` errors on a symlink that mean it leads nowhere: missing, through a
#: non-directory, or round a loop.
_DANGLING_ERRNOS = (errno.ENOENT, errno.ENOTDIR, errno.ELOOP)


def _is_non_directory(path: Path) -> bool:
    """True when ``path`` exists as a name but is no directory; ``OSError`` if unknowable.

    ``path.lstat()`` first: ``FileNotFoundError`` or ``NotADirectoryError`` means
    absent, so False. A symlink is followed with ``path.stat()``: ENOENT,
    ENOTDIR or ELOOP means it dangles or loops back on itself, so True;
    otherwise its target decides. A path that is not a symlink is a directory
    exactly when ``S_ISDIR`` holds for its ``lstat``. Any other ``OSError``
    propagates.
    """
    try:
        info = path.lstat()
    except (FileNotFoundError, NotADirectoryError):
        return False
    if stat.S_ISLNK(info.st_mode):
        try:
            info = path.stat()
        except OSError as exc:
            if exc.errno in _DANGLING_ERRNOS:
                return True
            raise
    return not stat.S_ISDIR(info.st_mode)


def directory_blocker(project_root: Path, name: str) -> Path | None:
    """The path standing where a directory should be, or None; ``OSError`` if unknowable.

    Checks ``<project_root>/.claude`` first, then ``runtime_dir(project_root,
    name)``, and returns the first that exists as a name but is no directory
    (a dangling or self-looping symlink counts, a symlink to a directory does
    not). An absent path is no blocker. Decided by ``lstat`` and ``stat``, so
    the answer does not depend on the interpreter's ``Path.exists`` semantics.
    """
    for path in (project_root / CLAUDE_DIR_NAME, runtime_dir(project_root, name)):
        if _is_non_directory(path):
            return path
    return None


def apply_fixes(ctx: CheckContext, fixed: list[str], errors: list[str]) -> None:
    """Create the missing runtime directories, appending to ``fixed`` and ``errors``.

    A target that is a directory is skipped. A target blocked by a non-directory
    (see ``directory_blocker``) is never replaced: its blocker appends
    ``fix failed: <blocker>: not a directory, move it aside`` to ``errors``
    once, however many targets it blocks, and nothing is created for those
    targets. Any other target is created, and a failed
    ``mkdir`` appends its ``OSError``. The caller owns both lists, so what was
    created survives a later raise. A missing ``.claude`` parent is created too,
    without being listed in ``fixed``.
    """
    reported: set[Path] = set()
    for name in RUNTIME_DIRS:
        target = runtime_dir(ctx.project_root, name)
        if target.is_dir():
            continue
        blocker = directory_blocker(ctx.project_root, name)
        if blocker is not None:
            if blocker not in reported:
                reported.add(blocker)
                errors.append(
                    f"fix failed: {abs_path(blocker)}: not a directory, move it aside"
                )
            continue
        try:
            target.mkdir(parents=True, exist_ok=False)
        except OSError as exc:
            errors.append(f"fix failed: {abs_path(target)}: {exc}")
        else:
            fixed.append(f"created {abs_path(target)}")


def check_metrics_writable(ctx: CheckContext) -> Check:
    """``.claude/metrics`` must be a directory this user can create files in."""
    metrics = runtime_dir(ctx.project_root, "metrics")
    where = abs_path(metrics)
    try:
        blocker = directory_blocker(ctx.project_root, "metrics")
        is_present = blocker is None and metrics.is_dir()
    except OSError as exc:
        # Stat was denied: the ancestor lacks search permission.
        parent = Path(exc.filename).parent if exc.filename else ctx.project_root
        return make_check(
            Status.FAIL,
            f"{where}: {type(exc).__name__}",
            f"chmod u+rwx {shlex.quote(abs_path(parent))}",
        )
    if blocker is not None:
        blocked = abs_path(blocker)
        return make_check(
            Status.FAIL,
            f"{blocked} is not a directory",
            _mv_aside_fix(blocked),
        )
    if not is_present:
        return make_check(Status.WARN, f"{where} missing", DOCTOR_FIX)
    try:
        ctx.probe_write(metrics)
    except OSError as exc:
        return make_check(Status.FAIL, f"{where}: {exc}", _make_writable_fix(where))
    return make_check(Status.OK, f"{where} writable")


def check_project_settings(ctx: CheckContext) -> Check:
    """The project's ``.claude/settings.json`` should carry a valid autocompact value."""
    autocompact = ctx.load_helper("autocompact_config")
    path = ctx.project_root / CLAUDE_DIR_NAME / "settings.json"
    where = abs_path(path)
    try:
        loaded = load_json(path)
    except OSError as exc:
        return make_check(
            Status.FAIL,
            f"cannot read {where}: {type(exc).__name__}",
            edit_fix(where),
        )
    if loaded.kind is LoadKind.MISSING:
        return make_check(Status.WARN, f"{where}: missing", SETUP_FIX)
    if loaded.kind is not LoadKind.LOADED:
        return _unloadable(where, loaded, edit_fix(where))
    settings_env = loaded.data.get("env", _ABSENT)
    if settings_env is not _ABSENT and not isinstance(settings_env, dict):
        return make_check(
            Status.FAIL, f"{where}: env is not an object", edit_fix(where)
        )
    if not isinstance(settings_env, dict) or autocompact.KEY not in settings_env:
        return make_check(Status.WARN, f"env.{autocompact.KEY} not set", SETUP_FIX)
    value = settings_env[autocompact.KEY]
    if autocompact.validate_pct(value) is None:
        return make_check(
            Status.WARN,
            f"{autocompact.KEY} has type {type(value).__name__}"
            f" and length {len(str(value))}, expected a percent string 1-100",
            SETUP_FIX,
        )
    return make_check(Status.OK, f"env.{autocompact.KEY} is {value!r}")


class ManagedSection(NamedTuple):
    """A section ``/setup`` writes into a project file and versions with a marker line.

    ``marker_pattern``'s one group is the optional ``v<N>`` suffix; no suffix
    means version 0.
    """

    path: str
    marker_pattern: str
    current_version: int


MANAGED_SECTIONS = (
    ManagedSection(
        ".claude/CLAUDE.md",
        r"<!-- dev-team: concise-response preference(?: v(\d+))? -->",
        1,
    ),
    ManagedSection(
        ".gitignore",
        (
            r"# dev-team workflow runtime artifacts "
            r"\(\.claude/-scoped \+ \.dev-team-reports/, #1406\)(?: v(\d+))?"
        ),
        2,
    ),
)


def _marker_version(text: str, pattern: str) -> int | None:
    """The highest marker version in ``text``: None without a marker, 0 without a suffix.

    ``/setup`` appends its marker block and never removes a marker line, so an
    upgraded file can carry an older marker line before the current one.
    """
    versions = [int(match.group(1) or 0) for match in re.finditer(pattern, text)]
    return max(versions, default=None)


def _marker_label(relative: str, version: int) -> str:
    return f"{relative} at v{version}"


def check_managed_sections(ctx: CheckContext) -> Check:
    """Sections ``/setup`` manages must be at its current version once opted in."""
    opted_in: list[tuple[ManagedSection, int]] = []
    for section in MANAGED_SECTIONS:
        path = ctx.project_root / section.path
        where = abs_path(path)
        try:
            loaded = read_bounded(path)
            text = loaded.data.decode("utf-8") if loaded.kind is LoadKind.LOADED else ""
        except (OSError, UnicodeDecodeError) as exc:
            return make_check(
                Status.FAIL,
                f"cannot read {section.path}: {type(exc).__name__}",
                edit_fix(where),
            )
        if loaded.kind is LoadKind.MISSING:
            continue
        if loaded.kind is not LoadKind.LOADED:
            return _unloadable(where, loaded, edit_fix(where))
        version = _marker_version(text, section.marker_pattern)
        if version is not None:
            opted_in.append((section, version))
    stale = [
        f"{_marker_label(section.path, version)} (current v{section.current_version})"
        for section, version in opted_in
        if version < section.current_version
    ]
    if stale:
        return make_check(Status.WARN, f"stale: {', '.join(stale)}", SETUP_FIX)
    if not opted_in:
        return make_check(Status.OK, "not opted in")
    descriptions = ", ".join(
        _marker_label(section.path, version) for section, version in opted_in
    )
    return make_check(Status.OK, f"opted in: {descriptions}")


CHECKS = (
    ("plugin-version", check_plugin_version),
    ("hook-registration", check_hook_registration),
    ("interpreter", check_interpreter),
    ("python-floor", check_python_floor),
    ("required-tools", check_required_tools),
    ("optional-tools", check_optional_tools),
    ("metrics-writable", check_metrics_writable),
    ("project-settings", check_project_settings),
    ("managed-sections", check_managed_sections),
)
