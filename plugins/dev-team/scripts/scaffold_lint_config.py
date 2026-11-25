#!/usr/bin/env python3
"""Scaffold the dev-team ESLint config into a user's project.

The scaffold unit is exactly ``templates/eslint/payload/``. Each file in it is
written beside the project's own ``eslint.config.*`` and ``tsconfig.json``,
with a stamp as its first line::

    // devteam-lint v<plugin version> sha256:<sha256 of all bytes after this line>

The user's own ESLint config and tsconfig are never read for writing.

Usage:
    scaffold_lint_config.py [--project DIR]            scaffold (default)
    scaffold_lint_config.py [--project DIR] --check    JSON: file -> status
    scaffold_lint_config.py [--project DIR] --refresh  rewrite stale-unedited

Statuses: current, current-edited, stale-unedited, stale-edited, unstamped.
``--refresh`` also lists a symlinked file as skipped (``symlink``).
Scaffolding writes only when the project meets every precondition, never
overwrites an existing file, and otherwise prints a reason and one action.

Stdlib only.
"""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import re
import secrets
import stat
import sys
from dataclasses import dataclass, field
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
_HOOKS_LIB_DIR = PLUGIN_ROOT / "hooks" / "lib"
if str(_HOOKS_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_LIB_DIR))

import artifact_paths

PAYLOAD_DIR = PLUGIN_ROOT / "templates" / "eslint" / "payload"
MANIFEST_PATH = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"

# The scaffold unit. A test pins this list to the payload directory.
PAYLOAD_FILES = ("eslint.devteam.config.js",)
STAMP_PREFIX = "// devteam-lint"
STAMP_PATTERN = re.compile(rb"^// devteam-lint v(\S+) sha256:([0-9a-f]{64})\r?$")

SUPPORTED_ESLINT_MAJORS = (9, 10)
# Strict semver. A version string reaches skip messages the model reads, so
# anything that is not exactly semver is never echoed.
SEMVER_PATTERN = re.compile(
    r"(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?"
)

JS_SOURCE_SUFFIXES = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts")
DECLARATION_SUFFIXES = (".d.ts", ".d.mts", ".d.cts")
SKIPPED_DIRS = frozenset(
    {
        "node_modules",
        ".git",
        ".venv",
        "venv",
        "dist",
        "build",
        "coverage",
        "__pycache__",
        ".tox",
    }
)
FLAT_CONFIG_NAMES = tuple(
    f"eslint.config.{ext}" for ext in ("js", "mjs", "cjs", "ts", "mts", "cts")
)
LEGACY_CONFIG_NAMES = tuple(
    f".eslintrc{ext}" for ext in ("", ".js", ".cjs", ".json", ".yaml", ".yml")
)
TYPED_DEPENDENCIES = (
    "eslint-plugin-functional",
    "@typescript-eslint/parser",
    "typescript",
)
DEPENDENCY_SECTIONS = (
    "dependencies",
    "devDependencies",
    "peerDependencies",
    "optionalDependencies",
)

STATUS_CURRENT = "current"
STATUS_CURRENT_EDITED = "current-edited"
STATUS_STALE_UNEDITED = "stale-unedited"
STATUS_STALE_EDITED = "stale-edited"
STATUS_UNSTAMPED = "unstamped"
STATUS_SYMLINK = "symlink"  # refresh never writes through a link

EXIT_OK = 0
EXIT_FAILURE = 2

UNTYPED_MISSES = (
    "untyped mode does not report array mutations (push, pop, shift, unshift, "
    "splice, sort, reverse, fill) on parameters, captured arrays, module-level "
    "arrays, or local accumulators; add a tsconfig.json with allowJs and JSDoc "
    "types to close these gaps"
)

TYPED_HINT = (
    "typed rules expected (tsconfig.json and typed dependencies found; not "
    "checked: DEVTEAM_LINT_TYPED=0, whether the dependencies load, and whether "
    "the tsconfig covers each file)"
)

NEXT_WIRE = (
    "next: the config does nothing until it is wired. Import it first in your "
    'eslint.config.js: import devteam from "./eslint.devteam.config.js"; '
    "export default [...devteam, ...yourConfig];"
)
NEXT_HOOK = (
    "next: to get findings after each edit, set DEVTEAM_POST_LINT=1 under "
    '"env" in .claude/settings.json, only in a repository you trust '
    "(read the Security section of the plugin's post-edit-lint-hook.md first)"
)


class ScaffoldError(RuntimeError):
    """The plugin's own files are missing or unreadable."""


@dataclass(frozen=True)
class Skip:
    reason: str
    action: str


@dataclass
class Outcome:
    written: list[str] = field(default_factory=list)
    existing: list[str] = field(default_factory=list)
    typed: bool = False
    untyped_reason: str = ""
    skip: Skip | None = None


# --- pure helpers ----------------------------------------------------------


def parse_major(version: str) -> int | None:
    """Major number of ``9.0.0`` or ``10.0.0-rc.1``; ``None`` unless strict semver."""
    match = SEMVER_PATTERN.fullmatch(version)
    return int(match.group(1)) if match else None


def semver_key(version: str) -> tuple | None:
    """Sort key for strict semver (build metadata ignored, a release above its
    own pre-releases); ``None`` for anything else."""
    match = SEMVER_PATTERN.fullmatch(version)
    if match is None:
        return None
    major, minor, patch, pre = match.groups()
    identifiers = tuple(
        (0, int(part), "") if part.isdigit() else (1, 0, part)
        for part in (pre.split(".") if pre else ())
    )
    return (int(major), int(minor), int(patch), pre is None, identifiers)


def _supported_text() -> str:
    """``9 or 10``: the supported ESLint majors, for messages."""
    return " or ".join(str(major) for major in SUPPORTED_ESLINT_MAJORS)


def _latest_supported() -> int:
    return max(SUPPORTED_ESLINT_MAJORS)


def body_hash(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def make_stamp_line(version: str, body: bytes) -> bytes:
    return f"{STAMP_PREFIX} v{version} sha256:{body_hash(body)}\n".encode()


def stamp(version: str, body: bytes) -> bytes:
    return make_stamp_line(version, body) + body


def split_stamp(content: bytes) -> tuple[str, str, bytes] | None:
    """``(version, hash, body)`` of a stamped file, ``None`` when unstamped."""
    first, newline, body = content.partition(b"\n")
    match = STAMP_PATTERN.match(first)
    if not newline or match is None:
        return None
    return match.group(1).decode("ascii"), match.group(2).decode("ascii"), body


def classify(content: bytes, current_version: str) -> str:
    parts = split_stamp(content)
    if parts is None:
        return STATUS_UNSTAMPED
    version, stamped_hash, body = parts
    edited = body_hash(body) != stamped_hash
    if _is_current(version, current_version):
        return STATUS_CURRENT_EDITED if edited else STATUS_CURRENT
    return STATUS_STALE_EDITED if edited else STATUS_STALE_UNEDITED


def _is_current(stamped: str, running: str) -> bool:
    """A stamp from this plugin version or a newer one: refreshing it would
    downgrade a file a newer plugin wrote."""
    if stamped == running:
        return True
    stamped_key, running_key = semver_key(stamped), semver_key(running)
    return (
        stamped_key is not None
        and running_key is not None
        and stamped_key >= running_key
    )


def read_plugin_version(manifest: Path = MANIFEST_PATH) -> str:
    try:
        version = json.loads(manifest.read_text(encoding="utf-8"))["version"]
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ScaffoldError(
            f"cannot read plugin version from {manifest}: {error}"
        ) from error
    if not isinstance(version, str) or not version.strip():
        raise ScaffoldError(f"{manifest} has no version string")
    return version


def read_payload(name: str) -> bytes:
    try:
        return (PAYLOAD_DIR / name).read_bytes()
    except OSError as error:
        raise ScaffoldError(f"cannot read payload file {name}: {error}") from error


# --- project inspection ----------------------------------------------------


def _read_package_json(project: Path) -> dict | Skip:
    try:
        data = json.loads((project / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Skip(
            "package.json is not valid JSON",
            "fix package.json, then re-run /setup",
        )
    return (
        data
        if isinstance(data, dict)
        else Skip(
            "package.json is not a JSON object", "fix package.json, then re-run /setup"
        )
    )


def _has_js_source(project: Path) -> bool:
    for _dirpath, dirnames, filenames in os.walk(project):
        dirnames[:] = [d for d in dirnames if d not in SKIPPED_DIRS]
        for filename in filenames:
            if not filename.endswith(JS_SOURCE_SUFFIXES):
                continue
            if filename.endswith(DECLARATION_SUFFIXES) or ".config." in filename:
                continue
            return True
    return False


def _declares_eslint(package: dict) -> bool:
    return any(
        isinstance(package.get(section), dict) and "eslint" in package[section]
        for section in DEPENDENCY_SECTIONS
    )


def _installed_eslint_version(project: Path) -> str | None:
    try:
        data = json.loads(
            (project / "node_modules" / "eslint" / "package.json").read_text(
                encoding="utf-8"
            )
        )
    except (OSError, ValueError):
        return None
    version = data.get("version") if isinstance(data, dict) else None
    return version if isinstance(version, str) else None


def _eslint_gate(project: Path, package: dict) -> Skip | None:
    version = _installed_eslint_version(project)
    if version is None:
        if _declares_eslint(package):
            return Skip(
                "package.json declares ESLint but it is not installed",
                "run npm install, then re-run /setup",
            )
        return Skip(
            "ESLint is not installed",
            f"run npm install --save-dev eslint (version {_supported_text()}), "
            "then re-run /setup",
        )
    major = parse_major(version)
    if major is None:
        return Skip(
            "unparseable ESLint version in node_modules/eslint/package.json",
            f"reinstall ESLint {_supported_text()} "
            f"(npm install --save-dev eslint@{_latest_supported()}), "
            "then re-run /setup",
        )
    if major in SUPPORTED_ESLINT_MAJORS:
        return None
    if major > _latest_supported():
        return Skip(
            f"ESLint {version} found; dev-team config needs ESLint "
            f"{_supported_text()} and ESLint {major} is unsupported until "
            "tested",
            f"install ESLint {_latest_supported()} "
            f"(npm install --save-dev eslint@{_latest_supported()}), "
            "then re-run /setup",
        )
    return Skip(
        f"ESLint {version} found; dev-team config needs ESLint {_supported_text()}",
        "upgrade ESLint, then re-run /setup",
    )


def _config_gate(project: Path, package: dict) -> Skip | None:
    if any((project / name).is_file() for name in FLAT_CONFIG_NAMES):
        return None
    legacy = any((project / name).is_file() for name in LEGACY_CONFIG_NAMES) or (
        "eslintConfig" in package
    )
    if legacy:
        return Skip(
            "legacy eslintrc config found and no flat config; dev-team config "
            "needs a flat config (eslint.config.js)",
            "migrate to a flat config (npx @eslint/migrate-config), then re-run /setup",
        )
    return Skip(
        "no ESLint config found in the project root; dev-team config is "
        "imported from a flat config (eslint.config.js)",
        "create eslint.config.js in the project root, then re-run /setup",
    )


def gate(project: Path) -> Skip | None:
    """The first unmet precondition, or ``None`` when the project is supported."""
    if not (project / "package.json").is_file():
        return Skip(
            "no package.json in the project root",
            "run /setup from the project root that holds package.json",
        )
    package = _read_package_json(project)
    if isinstance(package, Skip):
        return package
    if not _has_js_source(project):
        return Skip(
            "no JavaScript or TypeScript source files found (a Python repo "
            "with a tooling package.json is not a JavaScript project)",
            "re-run /setup after adding JavaScript or TypeScript source",
        )
    return _eslint_gate(project, package) or _config_gate(project, package)


def detect_mode(project: Path) -> tuple[bool, str]:
    """``(is_typed, reason)``: whether the typed rules are expected to run, and
    why not when they are not. A hint only: the payload decides at lint time,
    and also skips them when ``DEVTEAM_LINT_TYPED=0`` or a dependency fails to
    load."""
    if not (project / "tsconfig.json").is_file():
        return False, "no tsconfig.json beside eslint.config.*"
    missing = [
        name
        for name in TYPED_DEPENDENCIES
        if not (project / "node_modules" / Path(name)).is_dir()
    ]
    if missing:
        return False, f"not installed: {', '.join(missing)}"
    return True, ""


# --- operations ------------------------------------------------------------


def _root_mismatch(project: Path) -> Skip | None:
    """The hook resolves the git top level; a config beside a subdirectory is never found."""
    top = artifact_paths.git_toplevel(project)
    if top is None or top.resolve() == project.resolve():
        return None
    return Skip(
        f"{project} is not the repository root ({top}); the post-edit hook "
        "looks for eslint.devteam.config.js in the repository root",
        "run /setup from the repository root",
    )


def scaffold(project: Path) -> Outcome:
    skip = _root_mismatch(project) or gate(project)
    if skip is not None:
        return Outcome(skip=skip)
    version = read_plugin_version()
    typed, untyped_reason = detect_mode(project)
    outcome = Outcome(typed=typed, untyped_reason=untyped_reason)
    for name in PAYLOAD_FILES:
        target = project / name
        content = stamp(version, read_payload(name))
        try:
            created = _create_new(target, content)
        except OSError as error:
            raise ScaffoldError(f"cannot write {target}: {error}") from error
        (outcome.written if created else outcome.existing).append(name)
    return outcome


def _write_temp(directory: Path, name: str, content: bytes) -> Path:
    """Write ``content`` to a new hidden file beside the target, with the mode a
    plain create would give."""
    temp = directory / f".{name}.{secrets.token_hex(6)}.tmp"
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    return temp


def _create_new(target: Path, content: bytes) -> bool:
    """Create ``target`` with all of ``content`` or not at all, never replacing
    an existing file. ``False`` when it already exists. A hard link of a fully
    written temp file makes the stamped file appear whole; on a filesystem
    without hard links, an exclusive create is the fallback."""
    temp = _write_temp(target.parent, target.name, content)
    try:
        try:
            os.link(temp, target)
        except FileExistsError:
            return False
        except OSError:
            return _create_exclusive(target, content)
        return True
    finally:
        temp.unlink(missing_ok=True)


def _create_exclusive(target: Path, content: bytes) -> bool:
    try:
        with open(target, "xb") as handle:
            handle.write(content)
    except FileExistsError:
        return False
    return True


def check(project: Path) -> dict[str, str]:
    """Status of each scaffolded file present in the project."""
    version = read_plugin_version()
    return {
        name: classify((project / name).read_bytes(), version)
        for name in PAYLOAD_FILES
        if (project / name).is_file()
    }


def _read_status(target: Path, version: str) -> tuple[bytes, str]:
    content = target.read_bytes()
    return content, classify(content, version)


def _refresh_one(target: Path, version: str, replacement: bytes) -> bool:
    """Replace ``target`` only if it is still stale-unedited at the moment of
    the swap. The new bytes are written beside it first and swapped in with
    ``os.replace``, so an interrupt never leaves a partial file."""
    if not os.access(target, os.W_OK):
        raise PermissionError(errno.EACCES, "file is read-only", str(target))
    temp = _write_temp(target.parent, target.name, replacement)
    try:
        temp.chmod(stat.S_IMODE(target.stat().st_mode))
        if _read_status(target, version)[1] != STATUS_STALE_UNEDITED:
            return False
        os.replace(temp, target)
        return True
    finally:
        temp.unlink(missing_ok=True)


def refresh(project: Path) -> dict[str, object]:
    """Rewrite only stale-unedited files; report every other status as skipped."""
    version = read_plugin_version()
    refreshed: list[str] = []
    skipped: dict[str, str] = {}
    for name in PAYLOAD_FILES:
        target = project / name
        if not target.is_file():
            continue
        if target.is_symlink():
            skipped[name] = STATUS_SYMLINK
            continue
        status = _read_status(target, version)[1]
        if status != STATUS_STALE_UNEDITED:
            skipped[name] = status
            continue
        try:
            replaced = _refresh_one(target, version, stamp(version, read_payload(name)))
        except OSError as error:
            raise ScaffoldError(f"cannot write {target}: {error}") from error
        if replaced:
            refreshed.append(name)
        else:
            skipped[name] = _read_status(target, version)[1]
    return {"refreshed": refreshed, "skipped": skipped}


def render(outcome: Outcome) -> str:
    if outcome.skip is not None:
        return "\n".join(
            [
                "dev-team lint config: nothing written",
                f"reason: {outcome.skip.reason}",
                f"action: {outcome.skip.action}",
            ]
        )
    lines = ["dev-team lint config"]
    lines += [f"written: {name}" for name in outcome.written]
    lines += [f"skipped (exists): {name}" for name in outcome.existing]
    if not outcome.written and not outcome.existing:
        lines.append("written: none")
    if outcome.typed:
        lines.append(f"mode: {TYPED_HINT}")
    else:
        lines.append(f"mode: untyped ({outcome.untyped_reason})")
        lines.append(f"untyped misses: {UNTYPED_MISSES}")
    lines.append(NEXT_WIRE)
    lines.append(NEXT_HOOK)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project", type=Path, default=Path.cwd(), help="project root")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check", action="store_true", help="print each file's status as JSON"
    )
    mode.add_argument(
        "--refresh", action="store_true", help="rewrite stale-unedited files only"
    )
    args = parser.parse_args(argv)
    project = args.project.resolve()
    try:
        if args.check:
            print(json.dumps(check(project), indent=2))
        elif args.refresh:
            print(json.dumps(refresh(project), indent=2))
        else:
            print(render(scaffold(project)))
    except ScaffoldError as error:
        print(f"scaffold_lint_config: {error}", file=sys.stderr)
        return EXIT_FAILURE
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
