#!/usr/bin/env python3
"""coverage_discovery_js.py — discover and classify every package in a
JS/TS workspace for multi-project coverage discovery (issue #1759, Slice 3).

Resolves the declared workspace globs — from a root `package.json`'s
`workspaces` field (npm/yarn), `pnpm-workspace.yaml`'s `packages` list, or
`lerna.json`'s `packages` list, in that precedence order (first present
config wins; no cross-stack merge) — purely against the filesystem
(`pathlib`/`glob`, stdlib only). No package-manager CLI is invoked.

Each resolved package directory (a glob match that is a directory containing
its own `package.json`) is classified via `coverage_config.TestClassification`:
`TEST` when it has both a `test` script and a coverage-capable test-runner
devDependency (`jest`, `vitest`, or `mocha`/`ava` paired with `nyc`/`c8`),
`NOT_TEST` otherwise. Unlike .NET's discovery (Slice 2), there is no
`AMBIGUOUS` case for this stack — JS/TS has no analogue to MSBuild's
conditioned-property-inheritance ambiguity.

**Identity contract.** A package's "path" is its directory, resolved by
matching a workspace glob against the filesystem, expressed relative to
`repo_root` in POSIX form (matching the .NET discovery module's
repo-relative-path convention) — the exact, unmodified string every caller
compares against `included`/`excluded` entries, per `coverage_config`'s
identity contract (no normalization beyond this one POSIX-relative
rendering, which is applied once at resolution time, not per comparison).

**Security hardening.** Every glob-resolved package directory is verified to
stay within the resolved repository root before it is read or classified — a
workspace glob containing `..` can never cause this module to read or
classify a directory outside the repository.

**Minimal pnpm-workspace.yaml parser.** This module never imports PyYAML
(stdlib-only, ADR 0014/0015) and does not implement general YAML. It
recognizes exactly one documented subset of `packages:` — a top-level,
unindented `packages:` key followed by one or more indented `- 'glob'`
list-item lines. Any other shape (a flow-style array, a block scalar, an
anchor, a scalar value, or no top-level `packages:` key at all) is reported
as `coverage_config.discovery_error(...)` naming the unsupported shape —
never silently treated as `DISCOVERY_NOT_APPLICABLE` or an empty package
list, which would reintroduce this issue's exact silent-exclusion failure
mode one layer down in the parser.

Stdlib-only (ADR 0014/0015).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import coverage_config  # noqa: E402
from coverage_config import TestClassification  # noqa: E402

# Coverage-capable test-runner devDependencies. jest/vitest are
# self-contained; mocha/ava need a paired coverage tool.
_SELF_CONTAINED_RUNNERS = ("jest", "vitest")
_BARE_RUNNERS = ("mocha", "ava")
_COVERAGE_TOOLS = ("nyc", "c8")

_PNPM_PACKAGES_KEY_RE = re.compile(r"^packages:\s*(.*)$")
_YAML_LIST_ITEM_RE = re.compile(r"^\s+-\s*(.+)$")


def discover_js_packages(repo_root):
    """Discover and classify every package in `repo_root`'s JS/TS workspace.

    Returns a list of `{"path": <repo-relative POSIX package directory>,
    "classification": TestClassification}` entries on success,
    `coverage_config.DISCOVERY_NOT_APPLICABLE` when no workspace config
    (`package.json#workspaces`, `pnpm-workspace.yaml`, or `lerna.json`) is
    present, or `coverage_config.discovery_error(...)` for a parsing or
    path-containment failure.
    """
    root = Path(repo_root).resolve()

    globs = _package_json_workspace_globs(root)
    if isinstance(globs, dict):
        return globs  # a discovery_error propagated up
    if globs is None:
        pnpm_path = root / "pnpm-workspace.yaml"
        lerna_path = root / "lerna.json"
        if pnpm_path.is_file():
            parsed = _parse_pnpm_workspace_yaml(pnpm_path)
        elif lerna_path.is_file():
            parsed = _parse_lerna_json(lerna_path)
        else:
            return coverage_config.DISCOVERY_NOT_APPLICABLE
        if isinstance(parsed, dict):
            return parsed  # a discovery_error propagated up
        globs = parsed

    rel_paths = _resolve_globs_to_rel_paths(root, globs)
    if isinstance(rel_paths, dict):
        return rel_paths  # a discovery_error propagated up

    packages = []
    for rel_path in rel_paths:
        classification = _classify_package(root / rel_path, root)
        if isinstance(classification, dict):
            return classification  # a discovery_error propagated up
        packages.append({"path": rel_path, "classification": classification})
    return packages


# ---------------------------------------------------------------------------
# Workspace-glob resolution — package.json / pnpm-workspace.yaml / lerna.json
# ---------------------------------------------------------------------------


def _package_json_workspace_globs(root: Path):
    """Return the `workspaces` globs declared in `root`'s `package.json`
    (npm's plain array form, or yarn's `{"packages": [...]}` extended
    form); `None` when `package.json` is absent or has no `workspaces` key
    at all — callers fall through to `pnpm-workspace.yaml`/`lerna.json` on
    `None`, matching this module's precedence order (no workspace is
    declared here, so falling through is legitimate); or
    `coverage_config.discovery_error(...)` when `package.json` exists but
    fails to parse as JSON, isn't a JSON object, or declares `workspaces`
    in a shape this module doesn't recognize — that case must never
    silently fall through to a different workspace stack."""
    path = root / "package.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return coverage_config.discovery_error(
            f"Could not parse {str(path)!r} as JSON: {exc}"
        )
    if not isinstance(data, dict):
        return coverage_config.discovery_error(
            f"{str(path)!r} does not contain a JSON object."
        )
    if "workspaces" not in data:
        return None
    workspaces = data["workspaces"]
    if isinstance(workspaces, list):
        return workspaces
    if isinstance(workspaces, dict) and isinstance(workspaces.get("packages"), list):
        return workspaces["packages"]
    return coverage_config.discovery_error(
        f"{str(path)!r} declares 'workspaces' in an unsupported shape "
        "(expected an array of globs, or {\"packages\": [...]}); got "
        f"{type(workspaces).__name__} instead."
    )


def _parse_pnpm_workspace_yaml(path: Path):
    """Minimal, documented, block-style-only parser for `pnpm-workspace.yaml`'s
    `packages:` key — see the module docstring for the exact supported
    subset. Returns a list of glob strings, or
    `coverage_config.discovery_error(...)` naming the unsupported or
    unparseable shape."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return coverage_config.discovery_error(f"Could not read '{path}': {exc}")

    lines = text.splitlines()
    key_line_idx = None
    trailing = None
    for i, raw_line in enumerate(lines):
        if raw_line[:1].isspace():
            continue  # only a top-level (unindented) key is this document's own `packages:`
        stripped = raw_line.split("#", 1)[0].rstrip()
        match = _PNPM_PACKAGES_KEY_RE.match(stripped)
        if match:
            key_line_idx = i
            trailing = match.group(1).strip()
            break

    if key_line_idx is None:
        return coverage_config.discovery_error(
            f"'{path}' has no top-level 'packages:' key that this minimal "
            "parser recognizes (block-style list only, e.g. "
            "\"packages:\\n  - 'glob'\"); this shape is unsupported."
        )
    if trailing:
        return coverage_config.discovery_error(
            f"'{path}' declares 'packages:' with an unsupported shape "
            f"({trailing!r}); only a block-style list (packages:\\n  - "
            "'glob') is supported."
        )

    globs = []
    for raw_line in lines[key_line_idx + 1 :]:
        stripped_line = raw_line.strip()
        if not stripped_line:
            continue
        if stripped_line.startswith("#"):
            continue  # whole-line comment inside the block — not a dedent
        item_match = _YAML_LIST_ITEM_RE.match(raw_line)
        if item_match is None:
            break  # dedent, or the next top-level key, ends the list
        value = item_match.group(1).split("#", 1)[0].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        globs.append(value)

    if not globs:
        return coverage_config.discovery_error(
            f"'{path}' declares a top-level 'packages:' key but no "
            "recognized \"- 'glob'\" list items followed it; this minimal "
            "parser only supports a block-style list (packages:\\n  - "
            "'glob')."
        )
    return globs


def _parse_lerna_json(path: Path):
    """Return `lerna.json`'s `packages` list, or
    `coverage_config.discovery_error(...)` when the file fails to parse as
    JSON. A valid `lerna.json` with no `packages` list (or a non-list value)
    resolves to zero globs rather than an error — the file itself is a
    recognized, present workspace config; it simply declares no packages."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return coverage_config.discovery_error(f"Could not parse '{path}' as JSON: {exc}")
    if not isinstance(data, dict):
        return coverage_config.discovery_error(f"'{path}' does not contain a JSON object.")
    packages = data.get("packages")
    return packages if isinstance(packages, list) else []


def _resolve_globs_to_rel_paths(root: Path, globs: list):
    """Resolve each glob in `globs` against `root`'s filesystem, keeping
    only matches that are directories containing their own `package.json`.
    Returns a sorted list of repo-relative POSIX paths, or
    `coverage_config.discovery_error(...)` naming: the first resolved match
    found outside `root` (e.g. a glob containing `..`) — refusing to include
    or silently drop it; a glob pattern this module refuses to resolve at
    all (an absolute path, a malformed `**` placement, or more than one
    `**` segment); or a filesystem error encountered while resolving it."""
    rel_paths = set()
    for pattern in globs:
        if not isinstance(pattern, str) or not pattern:
            continue
        if pattern.count("**") > 1:
            return coverage_config.discovery_error(
                f"Workspace glob {pattern!r} contains more than one '**' "
                "segment; no legitimate npm/yarn/pnpm workspace glob needs "
                "more than one, and multiple non-adjacent '**' segments can "
                "cause pathological filesystem-walk cost. Refusing to "
                "resolve it."
            )
        try:
            matches = list(root.glob(pattern))
        except (ValueError, NotImplementedError, OSError) as exc:
            return coverage_config.discovery_error(
                f"Workspace glob {pattern!r} could not be resolved: {exc}"
            )
        for match in matches:
            resolved = match.resolve()
            if not (resolved == root or root in resolved.parents):
                return coverage_config.discovery_error(
                    f"Workspace glob {pattern!r} resolved to "
                    f"{str(resolved)!r}, which is outside the repository "
                    f"root ({str(root)!r}); refusing to include it."
                )
            if not resolved.is_dir():
                continue
            if not (resolved / "package.json").is_file():
                continue
            rel_paths.add(resolved.relative_to(root).as_posix())
    return sorted(rel_paths)


# ---------------------------------------------------------------------------
# Package classification
# ---------------------------------------------------------------------------


def _classify_package(pkg_dir: Path, root: Path):
    """`TEST` when `pkg_dir`'s `package.json` declares both a `test` script
    and a coverage-capable test-runner devDependency (`jest`, `vitest`, or
    `mocha`/`ava` paired with `nyc`/`c8`); `NOT_TEST` otherwise. No
    `AMBIGUOUS` case for this stack.

    Returns `coverage_config.discovery_error(...)` instead — never
    `NOT_TEST` — when `pkg_dir`'s `package.json` exists but is unreadable or
    fails to parse as a JSON object, or when the manifest file itself
    (resolved, to catch a symlink) escapes `root`. `_resolve_globs_to_rel_paths`
    already guarantees `pkg_dir`'s `package.json` exists as a plain
    containment check on the directory; this re-resolves the manifest FILE
    itself because a symlinked `package.json` inside an already-contained
    directory could still point outside the repository."""
    manifest_path = pkg_dir / "package.json"
    try:
        resolved_manifest = manifest_path.resolve()
    except OSError as exc:
        return coverage_config.discovery_error(
            f"Could not resolve manifest {str(manifest_path)!r}: {exc}"
        )
    if not (resolved_manifest == root or root in resolved_manifest.parents):
        return coverage_config.discovery_error(
            f"Package manifest {str(manifest_path)!r} resolves to "
            f"{str(resolved_manifest)!r}, which is outside the repository "
            f"root ({str(root)!r}); refusing to read it."
        )

    try:
        pkg = json.loads(resolved_manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return coverage_config.discovery_error(
            f"Could not parse {str(manifest_path)!r} as JSON: {exc}"
        )
    if not isinstance(pkg, dict):
        return coverage_config.discovery_error(
            f"{str(manifest_path)!r} does not contain a JSON object."
        )

    scripts = pkg.get("scripts")
    has_test_script = isinstance(scripts, dict) and bool(scripts.get("test"))

    dev_deps = pkg.get("devDependencies")
    dev_deps = dev_deps if isinstance(dev_deps, dict) else {}
    has_runner = any(runner in dev_deps for runner in _SELF_CONTAINED_RUNNERS) or (
        any(runner in dev_deps for runner in _BARE_RUNNERS)
        and any(tool in dev_deps for tool in _COVERAGE_TOOLS)
    )

    return TestClassification.TEST if (has_test_script and has_runner) else TestClassification.NOT_TEST
