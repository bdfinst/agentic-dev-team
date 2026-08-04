#!/usr/bin/env python3
"""coverage_discovery_js.py — JS/TS workspace test-package discovery (#1782).

Discovers every package in a monorepo by resolving the declared workspace globs
against the filesystem directly. No package-manager CLI is invoked, so discovery
does not depend on npm/yarn/pnpm being installed or correctly configured in the
run environment — the same reasoning behind this repo's stdlib-only rule for
shipped logic.

Three workspace-config shapes are read, and their patterns are **unioned** (a
repo can carry more than one; taking only the first would silently under-cover):

* root `package.json` `workspaces` — an array, or Yarn's `{"packages": [...]}`
* `pnpm-workspace.yaml` / `.yml` — `packages:` block-style sequence only
* `lerna.json` — `packages`

Each discovered package classifies `TEST` when it has a non-placeholder `test`
script **and** a coverage-capable runner dependency (`jest`, `vitest`, or
`mocha`/`ava` paired with `nyc`/`c8`), otherwise `NOT_TEST`. There is no
`AMBIGUOUS` state here: unlike MSBuild's conditioned references, a manifest
carries no build condition this discovery would have to decline to evaluate.

None of the three config shapes present → `DISCOVERY_NOT_APPLICABLE`, and the
caller keeps its existing single-command path. A malformed `lerna.json`, root
`package.json`, or workspace `package.json` is a discovery error naming it —
never an empty list.

The pnpm YAML parser is deliberately minimal and **documented-shape-only**: a
`packages:` key followed by a block sequence of quoted or bare scalars. A
syntactically-valid-but-unsupported shape (flow-style array, nested mapping,
block scalar, anchor/alias) is a discovery error, explicitly not
`DISCOVERY_NOT_APPLICABLE` and not a silent empty list — a shape we cannot read
must never look like a repo with no workspaces.

Paths are repo-relative with forward slashes. `coverage_config` matches identity
as an exact string, so this form is the recorded identity for the JS/TS stack.

Usage:
    coverage_discovery_js.py <repo-path>

Stdout: `{"applicable": <bool>, "projects": [{"path", "classification"}, ...]}`.
On a hard failure: `error: <message>` on stderr, exit 1, never a traceback.

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from pathlib import Path

from coverage_config import (
    DISCOVERY_NOT_APPLICABLE,
    DiscoveredProject,
    DiscoveryError,
    TestClassification,
    discovery_error,
)

PNPM_WORKSPACE_FILENAMES = ("pnpm-workspace.yaml", "pnpm-workspace.yml")
LERNA_FILENAME = "lerna.json"
PACKAGE_MANIFEST = "package.json"

#: Runners that measure coverage on their own.
SELF_COVERING_RUNNERS = ("jest", "vitest")
#: Runners that need a separate coverage tool alongside them.
PAIRED_RUNNERS = ("mocha", "ava")
#: The coverage tools those runners pair with.
COVERAGE_TOOLS = ("nyc", "c8")

#: Directory names a workspace glob match is never taken from. This filters
#: matches after the glob has produced them rather than pruning the walk, so a
#: `**` pattern in a repo with dependencies installed still walks `node_modules`
#: — correct, but not free.
EXCLUDED_DIRECTORY_NAMES = frozenset({"node_modules"})

#: `npm init`'s default `test` script. It exits non-zero by design and measures
#: nothing, so treating it as a real test script would classify every
#: freshly-initialized package as a test package. Deliberately narrow: an
#: unanchored `.*` would also swallow `echo linting && jest --coverage ||
#: exit 1`, a genuine test script, and drop that package from coverage — the
#: #1759 under-report direction.
_PLACEHOLDER_TEST_SCRIPT = re.compile(
    r"^\s*echo\s+[^&|;]*(?:&&|;)?\s*exit\s+1\s*$"
)

#: Recognizes `packages:` including YAML's quoted-key spelling. A quoted key read
#: as an absent key would silently yield zero patterns for a repo that does
#: declare workspaces.
_PACKAGES_KEY = re.compile(r"^[\"']?packages[\"']?\s*:")

#: Characters that must never appear in a declared glob — a workspace pattern is
#: interpolated into shell commands downstream, and `..`/absolute forms would
#: escape the repo. `{`/`}`/`,` are absent on purpose: brace alternations are
#: legal in all three managers and are expanded by `expand_braces` first.
_UNSAFE_PATTERN_CHARACTERS = frozenset(";&|$`\n<>()'\"")


# ---------------------------------------------------------------------------
# Manifest reading
# ---------------------------------------------------------------------------


def _read_json(path: Path, repo_path: Path) -> dict:
    label = _relative(path, repo_path)
    try:
        # utf-8-sig strips a BOM: npm reads a BOM'd package.json fine, so
        # reporting one as "malformed" would be a misleading label.
        parsed = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        discovery_error(f"malformed {label}: {exc}")
    except UnicodeDecodeError as exc:
        # A ValueError, not an OSError — it would otherwise escape uncaught.
        discovery_error(f"undecodable {label}: {exc}")
    except OSError as exc:
        discovery_error(f"unreadable {label}: {exc}")
    if not isinstance(parsed, dict):
        discovery_error(f"malformed {label}: top-level value is not an object")
    return parsed


def _relative(path: Path, repo_path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_path.resolve()).as_posix()
    except ValueError:
        return str(path)


# ---------------------------------------------------------------------------
# pnpm-workspace.yaml — minimal, documented-shape-only parser
# ---------------------------------------------------------------------------

_UNSUPPORTED_SHAPE_HINT = (
    "only the documented block-style form is supported:\n"
    "    packages:\n"
    "      - 'packages/*'\n"
    "      - 'apps/*'\n"
    "Rewrite the file in that form, or declare the workspaces in "
    "package.json's 'workspaces' field instead. This shape is refused rather "
    "than skipped, because silently reading no patterns would under-report "
    "coverage."
)


def parse_pnpm_workspace_packages(text: str, label: str) -> list[str]:
    """Extract the `packages:` block sequence from a `pnpm-workspace.yaml`.

    Supports exactly one shape — a `packages:` key whose value is a block
    sequence of quoted or bare scalars. Anything else that is nonetheless valid
    YAML (flow-style array, nested mapping, block scalar, anchor/alias) is a
    hard failure, never a silent empty result.

    A file with no `packages:` key at all returns `[]`: the file's existence is
    still a workspace signal, it just declares no globs. A file that declares
    `packages:` twice is a hard failure — a YAML loader that tolerates the
    duplicate is last-wins, so silently taking the first block would resolve
    patterns pnpm itself would not use.
    """
    lines = text.splitlines()
    key_indices = [
        index for index, raw_line in enumerate(lines) if _PACKAGES_KEY.match(raw_line)
    ]
    if not key_indices:
        return []
    if len(key_indices) > 1:
        discovery_error(
            f"unsupported {label} shape: 'packages:' appears {len(key_indices)} times "
            f"(lines {', '.join(str(index + 1) for index in key_indices)}). Declare it "
            f"once. {_UNSUPPORTED_SHAPE_HINT}"
        )
    index = key_indices[0]
    inline = lines[index].split(":", 1)[1]
    inline = re.sub(r"\s#.*$", "", inline).strip()
    if inline:
        discovery_error(
            f"unsupported {label} shape: 'packages:' has an inline value "
            f"({inline!r}), not a block sequence. {_UNSUPPORTED_SHAPE_HINT}"
        )
    return _parse_block_sequence(lines[index + 1 :], label)


def _parse_block_sequence(lines: Sequence[str], label: str) -> list[str]:
    patterns: list[str] = []
    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not raw_line.startswith((" ", "\t")) and not stripped.startswith("- "):
            break  # dedented back to another top-level key
        # A zero-indented `- item` is still a sequence item: YAML allows a block
        # sequence at the same indentation as the mapping key it belongs to.
        if not stripped.startswith("- "):
            discovery_error(
                f"unsupported {label} shape: expected a '- <pattern>' sequence item "
                f"under 'packages:', found {stripped!r}. {_UNSUPPORTED_SHAPE_HINT}"
            )
        item = re.sub(r"\s#.*$", "", stripped[2:]).strip()
        if item.startswith(("'", '"')) and len(item) > 1 and item[-1] == item[0]:
            item = item[1:-1]
        elif item.startswith(("'", '"', "*", "&")) or ":" in item:
            # A sequence of mappings, an anchor, or an unterminated quote.
            discovery_error(
                f"unsupported {label} shape: {item!r} is not a plain pattern scalar. "
                f"{_UNSUPPORTED_SHAPE_HINT}"
            )
        if not item:
            discovery_error(
                f"unsupported {label} shape: empty sequence item under 'packages:'. "
                f"{_UNSUPPORTED_SHAPE_HINT}"
            )
        patterns.append(item)
    if not patterns:
        discovery_error(
            f"unsupported {label} shape: 'packages:' declares no block-sequence "
            f"items. {_UNSUPPORTED_SHAPE_HINT}"
        )
    return patterns


# ---------------------------------------------------------------------------
# Workspace pattern collection
# ---------------------------------------------------------------------------


def _workspaces_patterns(manifest: dict, label: str) -> list[str]:
    workspaces = manifest["workspaces"]
    if isinstance(workspaces, dict):
        workspaces = workspaces.get("packages")
    if not isinstance(workspaces, list) or any(
        not isinstance(entry, str) for entry in workspaces
    ):
        discovery_error(
            f"malformed {label}: 'workspaces' must be an array of glob strings, or an "
            f"object with a 'packages' array — found {manifest['workspaces']!r}"
        )
    return workspaces


def collect_patterns(repo_path: Path) -> tuple[list[str], bool]:
    """Collect every declared workspace glob, and whether any signal was found.

    The boolean is the multi-project *signal*, not the pattern count: a config
    file that exists but declares no globs still means "this is a workspace
    repo", so the caller must not fall back to its single-command path.
    """
    patterns: list[str] = []
    signal = False

    root_manifest_path = repo_path / PACKAGE_MANIFEST
    if root_manifest_path.is_file():
        manifest = _read_json(root_manifest_path, repo_path)
        if "workspaces" in manifest:
            signal = True
            patterns.extend(_workspaces_patterns(manifest, PACKAGE_MANIFEST))

    for filename in PNPM_WORKSPACE_FILENAMES:
        pnpm_path = repo_path / filename
        if not pnpm_path.is_file():
            continue
        signal = True
        try:
            text = pnpm_path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as exc:
            discovery_error(f"undecodable {filename}: {exc}")
        except OSError as exc:
            discovery_error(f"unreadable {filename}: {exc}")
        patterns.extend(parse_pnpm_workspace_packages(text, filename))

    lerna_path = repo_path / LERNA_FILENAME
    if lerna_path.is_file():
        signal = True
        lerna = _read_json(lerna_path, repo_path)
        if "packages" in lerna:
            declared = lerna["packages"]
            if not isinstance(declared, list) or any(
                not isinstance(entry, str) for entry in declared
            ):
                discovery_error(
                    f"malformed {LERNA_FILENAME}: 'packages' must be an array of glob "
                    f"strings — found {declared!r}"
                )
            patterns.extend(declared)

    return patterns, signal


# ---------------------------------------------------------------------------
# Glob resolution
# ---------------------------------------------------------------------------


def _reject_unsafe_pattern(pattern: str) -> None:
    body = pattern.removeprefix("!")
    if body.startswith("/") or Path(body).is_absolute():
        discovery_error(f"unsafe workspace pattern (absolute): {pattern}")
    if ".." in Path(body).parts:
        discovery_error(f"unsafe workspace pattern (contains '..'): {pattern}")
    found = sorted(char for char in _UNSAFE_PATTERN_CHARACTERS if char in body)
    if found:
        discovery_error(
            f"unsafe workspace pattern (contains {found[0]!r}): {pattern}"
        )


def expand_braces(pattern: str) -> list[str]:
    """Expand `{a,b}` alternations into separate patterns.

    npm/yarn (minimatch), pnpm (fast-glob), and Lerna all accept
    `apps/{web,api}`; `pathlib.Path.glob` does not, and would look for a
    directory literally named `{web,api}`, match nothing, and drop two real test
    packages with no diagnostic. An unbalanced brace is a hard failure rather
    than a silent zero-match.
    """
    expanded = [pattern]
    while True:
        for index, candidate in enumerate(expanded):
            match = re.search(r"\{([^{}]*)\}", candidate)
            if match is None:
                continue
            prefix, suffix = candidate[: match.start()], candidate[match.end() :]
            alternatives = [
                prefix + alternative.strip() + suffix
                for alternative in match.group(1).split(",")
            ]
            expanded[index : index + 1] = alternatives
            break
        else:
            break
    for candidate in expanded:
        if "{" in candidate or "}" in candidate:
            discovery_error(
                f"unusable workspace pattern {pattern!r}: unbalanced brace. Brace "
                "alternations like 'apps/{web,api}' are supported; a stray brace is "
                "not, because it would silently match nothing."
            )
    return expanded


def _matches(repo_path: Path, pattern: str) -> set[str]:
    """Resolve one glob to the set of repo-relative package directories it names."""
    matched: set[str] = set()
    for expanded in expand_braces(pattern):
        matched |= _matches_one(repo_path, expanded)
    return matched


def _matches_one(repo_path: Path, pattern: str) -> set[str]:
    matched: set[str] = set()
    cleaned = pattern.rstrip("/")
    components = [part for part in cleaned.split("/") if part and part != "."]
    if not components:
        # `"."` and `"./"` name the repo root, which is never one of its own
        # workspaces. `Path.glob` rejects such a pattern outright, so it has to
        # be filtered here rather than let through as a crash.
        return matched
    # `Path.glob` matches leading-dot names; minimatch and fast-glob do not, so a
    # declared `packages/*` must not pick up `packages/.cache`. A pattern that
    # *explicitly* names a dot component is honoured — silently dropping those
    # would be the under-report direction.
    allows_dot_names = any(part.startswith(".") for part in components)
    try:
        candidates = list(repo_path.glob(cleaned))
    except (ValueError, NotImplementedError) as exc:
        discovery_error(f"unusable workspace pattern {pattern!r}: {exc}")
    for candidate in candidates:
        if not candidate.is_dir():
            continue
        try:
            # Deliberately not `candidate.resolve()`: resolving would rewrite a
            # symlinked workspace to its target, changing the recorded identity
            # that `coverage_config` matches as an exact string.
            relative = candidate.relative_to(repo_path)
        except ValueError:
            discovery_error(
                f"workspace pattern {pattern!r} matched {candidate}, which is not "
                f"under {repo_path}"
            )
        if not relative.parts:
            continue  # the repo root itself is not one of its own workspaces
        if EXCLUDED_DIRECTORY_NAMES.intersection(relative.parts):
            continue
        if not allows_dot_names and any(
            part.startswith(".") for part in relative.parts
        ):
            continue
        matched.add(relative.as_posix())
    return matched


def resolve_packages(repo_path: Path, patterns: Sequence[str]) -> list[str]:
    """Resolve every glob against the filesystem, honouring `!` negations.

    Only a directory that actually holds a `package.json` is a package — a glob
    routinely matches sibling directories that are not workspaces.
    """
    for pattern in patterns:
        _reject_unsafe_pattern(pattern)

    included: set[str] = set()
    excluded: set[str] = set()
    for pattern in patterns:
        if pattern.startswith("!"):
            excluded |= _matches(repo_path, pattern[1:])
        else:
            included |= _matches(repo_path, pattern)

    return sorted(
        relative
        for relative in included - excluded
        if (repo_path / relative / PACKAGE_MANIFEST).is_file()
    )


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def _declared_dependencies(manifest: dict) -> set[str]:
    """Every declared dependency name.

    Both `devDependencies` and `dependencies` are read. A runner misplaced in
    `dependencies` is common, and it is never a reason to leave a real test
    package out of coverage — that is the #1759 failure direction.
    """
    names: set[str] = set()
    for key in ("devDependencies", "dependencies"):
        declared = manifest.get(key)
        if isinstance(declared, dict):
            names |= {str(name) for name in declared}
    return names


def has_coverage_capable_runner(manifest: dict) -> bool:
    """True when the manifest declares a runner that can produce coverage."""
    dependencies = _declared_dependencies(manifest)
    if dependencies.intersection(SELF_COVERING_RUNNERS):
        return True
    return bool(
        dependencies.intersection(PAIRED_RUNNERS)
        and dependencies.intersection(COVERAGE_TOOLS)
    )


def has_real_test_script(manifest: dict) -> bool:
    """True when the manifest declares a `test` script that actually runs tests."""
    scripts = manifest.get("scripts")
    if not isinstance(scripts, dict):
        return False
    script = scripts.get("test")
    if not isinstance(script, str) or not script.strip():
        return False
    return _PLACEHOLDER_TEST_SCRIPT.match(script) is None


def classify(manifest: dict) -> TestClassification:
    """Classify a package by structural marker: a real `test` script plus a
    coverage-capable runner."""
    if has_real_test_script(manifest) and has_coverage_capable_runner(manifest):
        return TestClassification.TEST
    return TestClassification.NOT_TEST


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def discover(repo_path: Path) -> list[DiscoveredProject] | object:
    """Discover and classify every workspace package in the repo.

    Returns `DISCOVERY_NOT_APPLICABLE` when no workspace config exists — a
    single-`package.json` repo has no ambiguous package list, so the caller's
    existing single-command path is left untouched (epic #1766, criterion 10).
    """
    repo_path = Path(repo_path)
    if not repo_path.is_dir():
        # Not the same condition as "no workspace config here" — a path that is
        # not a repo at all must not read as "this stack does not apply".
        discovery_error(f"repo path is not a directory: {repo_path}")
    patterns, signal = collect_patterns(repo_path)
    if not signal:
        return DISCOVERY_NOT_APPLICABLE

    discovered: list[DiscoveredProject] = []
    for relative in resolve_packages(repo_path, patterns):
        manifest = _read_json(repo_path / relative / PACKAGE_MANIFEST, repo_path)
        discovered.append(
            DiscoveredProject(path=relative, classification=classify(manifest))
        )
    return discovered


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("repo", help="repo root to discover from")
    args = parser.parse_args(argv)

    try:
        result = discover(Path(args.repo))
    except DiscoveryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - the docstring promises no traceback
        print(f"error: unexpected failure: {exc!r}", file=sys.stderr)
        return 1

    if result is DISCOVERY_NOT_APPLICABLE:
        print(json.dumps({"applicable": False, "projects": []}, indent=2))
        return 0

    print(
        json.dumps(
            {
                "applicable": True,
                "projects": [
                    {
                        "path": project.path,
                        "classification": project.classification.value,
                    }
                    for project in result
                ],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
