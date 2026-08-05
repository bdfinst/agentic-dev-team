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
classify a directory outside the repository. Brace expansion (below) happens
*before* that containment check, so an escaping path hidden inside a single
brace alternative (`{apps,../outside}/*`) is refused exactly like a bare
`../outside/*`.

**Brace expansion (issue #1827).** npm, yarn and pnpm all accept shell-style
brace alternations in workspace globs (`apps/{web,api}`), but `pathlib` does
not expand them — it looks for a literal directory named `{web,api}` and
finds nothing. Each declared glob is therefore expanded into its
alternatives here before being resolved. Multiple groups expand as a
cartesian product and nested groups expand recursively, matching the package
managers. An unbalanced brace is a `discovery_error`, never a silent
fallthrough to zero matches.

**Explicit `**` validation (issue #1832).** `**` placement is validated by
inspecting each path component rather than by catching `ValueError` from
`Path.glob`. CPython 3.13+ accepts a non-component `**` and treats it as
`*`, so the exception this module previously relied on is no longer raised
there — which turned a `discovery_error` into a silent empty result.

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

import coverage_config
from coverage_config import TestClassification

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


class _UnbalancedBrace(Exception):
    """Raised internally by `_expand_braces` for a glob whose braces do not
    pair up. Converted to a `coverage_config.discovery_error` by the caller —
    never allowed to surface as an empty match set."""


class _BraceExpansionTooLarge(Exception):
    """Raised internally by `_expand_braces` for a glob whose expansion would
    exceed `_MAX_BRACE_EXPANSIONS` alternatives or `_MAX_BRACE_NESTING` levels
    of nesting. Converted to a `coverage_config.discovery_error` by the
    caller. Brace expansion is a cartesian product, so a modest-looking
    pattern (20 two-way groups) yields 2**20 globs and as many filesystem
    walks; deep nesting recurses per level and would otherwise surface as an
    uncaught `RecursionError` traceback rather than a discovery error."""


# Generous enough that no legitimate npm/yarn/pnpm workspace declaration comes
# close, small enough that a pathological `package.json` cannot turn discovery
# into a filesystem-walk bomb.
_MAX_BRACE_EXPANSIONS = 256
_MAX_BRACE_NESTING = 16


def _brace_balance_problem(pattern: str) -> str | None:
    """Return a reason when `pattern`'s braces do not pair up, else `None`.

    Validated across the WHOLE pattern in one pass, deliberately: an earlier
    version of this module scanned only from the first `{` onward, so a stray
    `}` to its left (`apps/}x{a,b}`) was copied verbatim into the literal
    prefix and expanded to globs that match nothing — reintroducing the exact
    silent-zero-packages outcome #1827 exists to prevent. Both reviewers of
    that change caught it independently; hence a single global check rather
    than a per-recursion one."""
    depth = 0
    max_depth = 0
    for index, char in enumerate(pattern):
        if char == "{":
            depth += 1
            max_depth = max(max_depth, depth)
        elif char == "}":
            depth -= 1
            if depth < 0:
                return (
                    f"closes a brace group at position {index} that was never "
                    "opened"
                )
    if depth > 0:
        return f"leaves {depth} brace group(s) unclosed"
    if max_depth > _MAX_BRACE_NESTING:
        return (
            f"nests brace groups {max_depth} deep, beyond the supported "
            f"maximum of {_MAX_BRACE_NESTING}"
        )
    return None


def _expand_braces(pattern: str) -> list:
    """Expand shell-style brace alternations in `pattern` into the list of
    concrete globs npm/yarn/pnpm would resolve (issue #1827).

    `apps/{web,api}` -> `['apps/web', 'apps/api']`. Multiple groups expand as
    a cartesian product; nested groups expand recursively. A pattern with no
    braces returns itself unchanged, so this is safe to apply to every glob.

    Raises `_UnbalancedBrace` when the braces do not pair up anywhere in the
    pattern — the package managers reject those too, and treating them as a
    literal path would silently resolve to nothing. Raises
    `_BraceExpansionTooLarge` when the expansion would exceed
    `_MAX_BRACE_EXPANSIONS`."""
    problem = _brace_balance_problem(pattern)
    if problem is not None:
        raise _UnbalancedBrace(problem)
    return _expand_braces_balanced(pattern)


def _expand_braces_balanced(pattern: str) -> list:
    """Recursive worker for `_expand_braces`, assuming `pattern`'s braces are
    already known to balance (every sub-pattern of a balanced pattern is
    itself balanced, so the global check runs once at entry, not per level)."""
    open_idx = pattern.find("{")
    if open_idx == -1:
        return [pattern]

    depth = 0
    close_idx = -1
    alternatives = []
    alt_start = open_idx + 1
    for i in range(open_idx, len(pattern)):
        char = pattern[i]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                alternatives.append(pattern[alt_start:i])
                close_idx = i
                break
        elif char == "," and depth == 1:
            alternatives.append(pattern[alt_start:i])
            alt_start = i + 1
    prefix = pattern[:open_idx]
    expanded_suffixes = _expand_braces_balanced(pattern[close_idx + 1 :])
    expanded = []
    for alternative in alternatives:
        for expanded_alt in _expand_braces_balanced(alternative):
            for suffix in expanded_suffixes:
                expanded.append(prefix + expanded_alt + suffix)
                if len(expanded) > _MAX_BRACE_EXPANSIONS:
                    raise _BraceExpansionTooLarge(
                        f"expands to more than {_MAX_BRACE_EXPANSIONS} "
                        "alternatives"
                    )
    return expanded


def _double_star_placement_problem(pattern: str) -> str | None:
    """Return a human-readable reason when `pattern`'s `**` usage is one this
    module refuses to resolve, else `None` (issue #1832).

    Checked by inspecting path components rather than by catching `ValueError`
    from `Path.glob`: CPython 3.13+ accepts a non-component `**` and silently
    treats it as `*`, so the exception this module used to depend on is not
    raised on every supported interpreter. A version-dependent guard here
    meant a malformed glob became an empty result instead of an error."""
    if pattern.count("**") > 1:
        return (
            "contains more than one '**' segment; no legitimate "
            "npm/yarn/pnpm workspace glob needs more than one, and multiple "
            "non-adjacent '**' segments can cause pathological "
            "filesystem-walk cost"
        )
    for component in pattern.split("/"):
        if "**" in component and component != "**":
            return (
                f"places '**' inside the path component {component!r}; '**' "
                "must be an entire path component of its own"
            )
    return None


def _resolve_globs_to_rel_paths(root: Path, globs: list):
    """Resolve each glob in `globs` against `root`'s filesystem, keeping
    only matches that are directories containing their own `package.json`.
    Returns a sorted list of repo-relative POSIX paths, or
    `coverage_config.discovery_error(...)` naming: the first resolved match
    found outside `root` (e.g. a glob containing `..`) — refusing to include
    or silently drop it; a glob pattern this module refuses to resolve at
    all (an absolute path, an unbalanced brace, a malformed `**` placement,
    or more than one `**` segment); or a filesystem error encountered while
    resolving it.

    Brace alternations are expanded first (`_expand_braces`), so every check
    below — including the containment guard — runs against each concrete
    alternative rather than the unexpanded pattern."""
    rel_paths = set()
    for declared_pattern in globs:
        if not isinstance(declared_pattern, str) or not declared_pattern:
            continue
        # The `**` budget is enforced on the DECLARED pattern, not only on each
        # expanded alternative: brace multiplication would otherwise smuggle
        # several `**` walks past a per-alternative check ({**/x,**/y,**/z} is
        # three single-`**` alternatives), defeating the cost guard's purpose.
        if declared_pattern.count("**") > 1:
            return coverage_config.discovery_error(
                f"Workspace glob {declared_pattern!r} contains more than one "
                "'**' segment; no legitimate npm/yarn/pnpm workspace glob "
                "needs more than one, and multiple non-adjacent '**' segments "
                "can cause pathological filesystem-walk cost. Refusing to "
                "resolve it."
            )
        try:
            expanded_patterns = _expand_braces(declared_pattern)
        except _UnbalancedBrace as exc:
            return coverage_config.discovery_error(
                f"Workspace glob {declared_pattern!r} {exc}; npm/yarn/pnpm "
                "reject unbalanced braces too, and resolving the pattern as a "
                "literal path would silently match nothing. Refusing to "
                "resolve it."
            )
        except _BraceExpansionTooLarge as exc:
            return coverage_config.discovery_error(
                f"Workspace glob {declared_pattern!r} {exc}; each alternative "
                "costs a separate filesystem walk. Refusing to resolve it."
            )
        for pattern in expanded_patterns:
            # An empty or bare-`/` alternative ({packages/*,} — legal in
            # npm/minimatch, where it simply contributes nothing) must not
            # reach `Path.glob`, which rejects '' outright and treats a
            # trailing separator version-dependently. Dropping it here keeps
            # one empty alternative from failing the whole workspace.
            pattern = pattern.rstrip("/")
            if not pattern:
                continue
            result = _resolve_one_glob(root, pattern, declared_pattern, rel_paths)
            if result is not None:
                return result
    return sorted(rel_paths)


def _resolve_one_glob(root: Path, pattern: str, declared_pattern: str, rel_paths: set):
    """Resolve a single brace-expanded `pattern`, adding every qualifying
    match to `rel_paths`. Returns `None` on success, or a
    `coverage_config.discovery_error(...)` to propagate. `declared_pattern` is
    the original glob as written in the manifest — named in every error
    alongside the expanded form so a brace-expanded failure is traceable back
    to what the operator actually declared."""

    def described(reason: str) -> str:
        if pattern == declared_pattern:
            return f"Workspace glob {pattern!r} {reason}."
        return (
            f"Workspace glob {pattern!r} (expanded from "
            f"{declared_pattern!r}) {reason}."
        )

    placement_problem = _double_star_placement_problem(pattern)
    if placement_problem is not None:
        return coverage_config.discovery_error(
            described(f"{placement_problem}. Refusing to resolve it")
        )
    try:
        matches = list(root.glob(pattern))
    except (ValueError, NotImplementedError, OSError) as exc:
        return coverage_config.discovery_error(
            described(f"could not be resolved: {exc}")
        )
    for match in matches:
        resolved = match.resolve()
        if not (resolved == root or root in resolved.parents):
            return coverage_config.discovery_error(
                described(
                    f"resolved to {str(resolved)!r}, which is outside the "
                    f"repository root ({str(root)!r}); refusing to include it"
                )
            )
        if not resolved.is_dir():
            continue
        if not (resolved / "package.json").is_file():
            continue
        rel_paths.add(resolved.relative_to(root).as_posix())
    return None


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
