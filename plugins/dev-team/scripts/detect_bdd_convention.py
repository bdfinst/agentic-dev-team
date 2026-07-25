#!/usr/bin/env python3
"""detect_bdd_convention.py — detect a target project's BDD convention.

Deterministic probe `/plan` shells to at plan-creation time, reporting
where derived .feature files should land:

    {"signal": "feature-files" | "manifest" | "none",
     "framework": <name or null>,
     "dir": <repo-relative destination or null>}

Precedence: existing .feature files > BDD dependency in a manifest > none.
Detection is conservative — a false negative (no signal, which prompts the
operator) is preferred over a false positive (the wrong directory), so any
ambiguity (multiple unrelated .feature roots) reports "none". Vendored and
generated trees (node_modules/, vendor/, dist/, build/, .git/, virtualenvs)
are never treated as a signal.

Stdlib-only. Python 3.8+.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import NamedTuple

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE / "lib"))

from _vendored_tree import iter_files as _iter_files


def _common_directory(paths: Iterable[Path]) -> Path:
    """Longest common ancestor of relative paths ('.' when they share none)."""
    common: list[str] = []
    for components in zip(*(p.parts for p in paths)):
        if len(set(components)) != 1:
            break
        common.append(components[0])
    return Path(*common) if common else Path(".")


def scan_feature_dir(root: Path) -> str | None:
    """Repo-relative common directory of the project's .feature files.

    None when no .feature file exists outside vendored trees, or when the
    files' common ancestor is the project root itself — which covers both
    multiple unrelated roots and root-level orphans (conservative: prompt
    rather than guess).
    """
    parents = sorted(
        {
            found.parent.relative_to(root)
            for found in _iter_files(root)
            if found.suffix == ".feature"
        }
    )
    if not parents:
        return None
    common = _common_directory(parents)
    if common == Path("."):
        return None
    return common.as_posix()


class ManifestRule(NamedTuple):
    """One supported BDD stack: which manifest declares it, and where its
    .feature files canonically live (repo-relative)."""

    framework: str
    manifests: tuple[str, ...]  # fnmatch patterns on the manifest file name
    tokens: tuple[str, ...]  # dependency tokens that signal the framework
    destination: str | None  # None => CSPROJ_FEATURES_SUBDIR under the manifest's dir


# Community convention for Reqnroll/SpecFlow: Features/ under the test csproj.
CSPROJ_FEATURES_SUBDIR = "Features"

# One row per stack; keep in sync with
# knowledge/test-stack-profiles/bdd-frameworks.md (guarded by
# tests/scripts/test_detect_bdd_convention.py::TestMappingDocSync).
MANIFEST_RULES: tuple[ManifestRule, ...] = (
    ManifestRule("cucumber-js", ("package.json",), ("@cucumber/cucumber",), "features"),
    ManifestRule(
        "pytest-bdd", ("pyproject.toml", "requirements*.txt"), ("pytest-bdd",), "features"
    ),
    ManifestRule(
        "behave", ("pyproject.toml", "requirements*.txt"), ("behave",), "features"
    ),
    ManifestRule("reqnroll", ("*.csproj",), ("Reqnroll",), None),
    ManifestRule("specflow", ("*.csproj",), ("SpecFlow",), None),
    ManifestRule(
        "cucumber-jvm",
        ("pom.xml", "build.gradle", "build.gradle.kts"),
        ("io.cucumber",),
        "src/test/resources/features",
    ),
    ManifestRule("godog", ("go.mod",), ("godog",), "features"),
)


def _package_json_declares(path: Path, token: str) -> bool:
    """True when `token` is a dependency or devDependency in a package.json."""
    try:
        manifest = json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, ValueError):
        return False
    if not isinstance(manifest, dict):
        return False
    for key in ("dependencies", "devDependencies"):
        dependencies = manifest.get(key)
        if isinstance(dependencies, dict) and token in dependencies:
            return True
    return False


def _text_declares(path: Path, token: str) -> bool:
    """True when `token` appears as a standalone name in the manifest's text.

    Hyphen/underscore continuations do not count: `behave-django` or
    `pytest-bdd-ng` must not signal `behave` / `pytest-bdd`.
    """
    try:
        text = path.read_text()
    except (OSError, UnicodeDecodeError):
        return False
    pattern = r"(?<![\w-])" + re.escape(token) + r"(?![\w-])"
    return re.search(pattern, text) is not None


def scan_manifests(root: Path) -> list[tuple[str, str]]:
    """(framework, destination) pairs for every manifest signal under `root`."""
    hits: list[tuple[str, str]] = []
    for path in _iter_files(root):
        for rule in MANIFEST_RULES:
            if not any(fnmatch.fnmatch(path.name, glob) for glob in rule.manifests):
                continue
            declares = (
                _package_json_declares if path.name == "package.json" else _text_declares
            )
            if not any(declares(path, token) for token in rule.tokens):
                continue
            if rule.destination is not None:
                destination = rule.destination
            else:
                destination = (
                    path.parent.relative_to(root) / CSPROJ_FEATURES_SUBDIR
                ).as_posix()
            hits.append((rule.framework, destination))
    return hits


def detect(root: Path) -> dict:
    """Detection result {signal, framework, dir} for the project at `root`.

    Precedence: existing .feature files > manifest dependency > none. Manifest
    hits pointing at more than one destination are a conflict and report
    "none" (conservative); several hits sharing one destination are not.
    """
    feature_dir = scan_feature_dir(root)
    if feature_dir is not None:
        return {"signal": "feature-files", "framework": None, "dir": feature_dir}

    hits = scan_manifests(root)
    destinations = {destination for _, destination in hits}
    if len(destinations) == 1:
        frameworks = sorted({framework for framework, _ in hits})
        return {
            "signal": "manifest",
            "framework": frameworks[0],
            "dir": destinations.pop(),
        }
    return {"signal": "none", "framework": None, "dir": None}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="detect_bdd_convention.py",
        description="Detect a target project's BDD convention and print it as JSON.",
    )
    parser.add_argument(
        "target",
        nargs="?",
        default=".",
        help="Project root to probe (default: current directory)",
    )
    args = parser.parse_args(argv)

    target = Path(args.target)
    if not target.is_dir():
        sys.stderr.write(
            f"detect-bdd-convention: target is not a directory: {args.target}\n"
        )
        return 2

    print(json.dumps(detect(target), sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
