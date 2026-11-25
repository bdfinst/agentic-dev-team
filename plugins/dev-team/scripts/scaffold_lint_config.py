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
import hashlib
import json
import os
import re
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
SEMVER_PATTERN = re.compile(r"(\d+)\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?")
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
    mode: str = ""
    skip: Skip | None = None


# --- pure helpers ----------------------------------------------------------


def parse_major(version: str) -> int | None:
    """Major number of ``9.0.0`` or ``10.0.0-rc.1``; ``None`` unless strict semver."""
    match = SEMVER_PATTERN.fullmatch(version)
    return int(match.group(1)) if match else None


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
    if version == current_version:
        return STATUS_CURRENT_EDITED if edited else STATUS_CURRENT
    return STATUS_STALE_EDITED if edited else STATUS_STALE_UNEDITED


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
            "run npm install --save-dev eslint (version 9 or 10), then re-run /setup",
        )
    major = parse_major(version)
    if major is None:
        return Skip(
            "unparseable ESLint version in node_modules/eslint/package.json",
            "reinstall ESLint 9 or 10 (npm install --save-dev eslint@10), then re-run /setup",
        )
    if major in SUPPORTED_ESLINT_MAJORS:
        return None
    if major > max(SUPPORTED_ESLINT_MAJORS):
        return Skip(
            f"ESLint {version} found; dev-team config needs ESLint 9 or 10 "
            f"and ESLint {major} is unsupported until tested",
            "install ESLint 10 (npm install --save-dev eslint@10), then re-run /setup",
        )
    return Skip(
        f"ESLint {version} found; dev-team config needs ESLint 9 or 10",
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


def detect_mode(project: Path) -> str:
    """``typed`` when type information is available, else ``untyped`` with why."""
    if not (project / "tsconfig.json").is_file():
        return "untyped (no tsconfig.json beside eslint.config.*)"
    missing = [
        name
        for name in TYPED_DEPENDENCIES
        if not (project / "node_modules" / Path(name)).is_dir()
    ]
    if missing:
        return f"untyped (not installed: {', '.join(missing)})"
    return "typed"


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
    outcome = Outcome(mode=detect_mode(project))
    for name in PAYLOAD_FILES:
        target = project / name
        content = stamp(version, read_payload(name))
        try:
            with open(target, "xb") as handle:
                handle.write(content)
        except FileExistsError:
            outcome.existing.append(name)
        except OSError as error:
            raise ScaffoldError(f"cannot write {target}: {error}") from error
        else:
            outcome.written.append(name)
    return outcome


def check(project: Path) -> dict[str, str]:
    """Status of each scaffolded file present in the project."""
    version = read_plugin_version()
    return {
        name: classify((project / name).read_bytes(), version)
        for name in PAYLOAD_FILES
        if (project / name).is_file()
    }


def refresh(project: Path) -> dict[str, object]:
    """Rewrite only stale-unedited files; report every other status as skipped."""
    version = read_plugin_version()
    refreshed: list[str] = []
    skipped: dict[str, str] = {}
    for name, status in check(project).items():
        target = project / name
        if target.is_symlink():
            skipped[name] = STATUS_SYMLINK
        elif status == STATUS_STALE_UNEDITED:
            try:
                target.write_bytes(stamp(version, read_payload(name)))
            except OSError as error:
                raise ScaffoldError(f"cannot write {target}: {error}") from error
            refreshed.append(name)
        else:
            skipped[name] = status
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
    lines.append(f"mode: {outcome.mode}")
    if outcome.mode != "typed":
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
