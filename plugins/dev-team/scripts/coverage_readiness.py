#!/usr/bin/env python3
"""coverage_readiness.py — assess (and optionally patch) a JS/TS repo's
coverage config so `/coverage-baseline` can capture a line+branch floor.

`/coverage-baseline` (used by `/test-improve` Phase 2) parses
`coverage/coverage-summary.json` (`total.lines.pct` / `total.branches.pct`)
for Istanbul-family runners. Jest and Vitest only write that file when the
**`json-summary`** coverage reporter is enabled, and the baseline is only
meaningful when the runner measures the whole source tree rather than just
files already imported by a test (Jest `collectCoverageFrom` / Vitest
`coverage.include`). A repo can pass `/setup` and still miss both, aborting
Phase 2 (issue #1086).

This probe reports readiness as JSON and, in `--patch` mode, adds the
`json-summary` reporter to configs it can edit **deterministically and
safely** — JSON-shaped configs only (`package.json`'s `jest` block, or a
`jest.config.json`). JS/TS config files (`jest.config.js`, `vitest.config.ts`,
…) are never rewritten here; the report names the file and the exact edit so
the caller can apply it through the operator-confirmed edit path instead.

Detection is text/JSON based — no runner is executed and no JS is evaluated.

Report schema (stdout, one JSON object):

    {
      "runner": "jest" | "vitest" | null,
      "config_source": <repo-relative file, "package.json#jest", or null>,
      "config_kind": "json" | "js" | "none",
      "has_json_summary": bool,   # json-summary reporter enabled
      "has_scope": bool,          # collectCoverageFrom / coverage.include set
      "coverage_provider": <str or null>,  # Vitest provider pkg / "istanbul (built-in)"
      "has_provider": bool,       # Jest: always true; Vitest: provider installed
      "ready": bool,              # summary parseable AND (Vitest) provider present
      "meaningful": bool,         # has_scope (baseline reflects whole tree)
      "patchable": bool,          # --patch can add the reporter unaided
      "patched": bool,            # --patch actually wrote a change
      "reporter_hint": <str or null>,   # exact edit for a js/ts config
      "scope_hint": <str or null>,      # exact edit when scope is missing
      "provider_hint": <str or null>,   # install cmd when Vitest lacks a provider
      "notes": [<str>, ...]
    }

Exit status: 0 when `ready` (after any patch), 1 when a JS/TS repo is not
ready, 2 when the repo is not a JS/TS project (no package.json) — callers
treat 2 as "not applicable, skip".

Stdlib-only. Python 3.8+.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple

JSON_SUMMARY = "json-summary"

# Jest config files, highest precedence first. Jest ignores a package.json
# `jest` key when any of these exist.
JEST_CONFIG_FILES = (
    "jest.config.ts",
    "jest.config.mts",
    "jest.config.cts",
    "jest.config.js",
    "jest.config.mjs",
    "jest.config.cjs",
    "jest.config.json",
)

# Vitest config files, highest precedence first (a dedicated vitest.config.*
# wins over a shared vite.config.*).
VITEST_CONFIG_FILES = (
    "vitest.config.ts",
    "vitest.config.mts",
    "vitest.config.js",
    "vitest.config.mjs",
    "vite.config.ts",
    "vite.config.mts",
    "vite.config.js",
    "vite.config.mjs",
)

# Vitest emits no coverage at all unless one of these provider packages is a
# dependency — the analog to Jest's built-in Istanbul. Without it, `vitest run
# --coverage` errors, so the baseline can never be captured regardless of the
# reporter config (issue #1086, Vitest arm).
VITEST_COVERAGE_PROVIDERS = ("@vitest/coverage-v8", "@vitest/coverage-istanbul")

_JSON_SUFFIXES = frozenset({".json"})


class Report(dict):
    """Thin dict subclass so callers can build the JSON report incrementally."""

    def note(self, message: str) -> None:
        self.setdefault("notes", []).append(message)


# ---------------------------------------------------------------------------
# package.json helpers
# ---------------------------------------------------------------------------

def _load_package_json(root: Path) -> Optional[dict]:
    path = root / "package.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _all_deps(pkg: dict) -> dict:
    deps: dict = {}
    for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        section = pkg.get(key)
        if isinstance(section, dict):
            deps.update(section)
    return deps


def detect_runner(root: Path, pkg: Optional[dict]) -> Optional[str]:
    """Return "jest", "vitest", or None.

    Config files are the strongest signal; dependency names (including the
    Angular Jest presets) are the fallback.
    """
    for name in JEST_CONFIG_FILES:
        if (root / name).is_file():
            return "jest"
    for name in VITEST_CONFIG_FILES:
        # vite.config.* only counts as a vitest signal when vitest is a dep;
        # a plain Vite app without vitest has no coverage config to assess.
        if (root / name).is_file():
            if name.startswith("vitest.") or (pkg and "vitest" in _all_deps(pkg)):
                return "vitest"
    if pkg is None:
        return None
    deps = _all_deps(pkg)
    if "vitest" in deps:
        return "vitest"
    jest_signals = ("jest", "@angular-builders/jest", "jest-preset-angular", "ts-jest")
    if isinstance(pkg.get("jest"), dict) or any(dep in deps for dep in jest_signals):
        return "jest"
    return None


# ---------------------------------------------------------------------------
# Config source resolution
# ---------------------------------------------------------------------------

def resolve_config_source(root: Path, runner: str, pkg: Optional[dict]) -> Tuple[Optional[str], str]:
    """Return (config_source, config_kind).

    config_source is a repo-relative filename, the sentinel "package.json#jest",
    or None when the runner has no coverage config anywhere. config_kind is
    "json" (safely patchable), "js" (edit via the confirmed path), or "none".
    """
    candidates = JEST_CONFIG_FILES if runner == "jest" else VITEST_CONFIG_FILES
    for name in candidates:
        if (root / name).is_file():
            kind = "json" if Path(name).suffix in _JSON_SUFFIXES else "js"
            return name, kind
    if runner == "jest" and isinstance((pkg or {}).get("jest"), dict):
        return "package.json#jest", "json"
    return None, "none"


def detect_vitest_provider(pkg: Optional[dict]) -> Optional[str]:
    """Return the installed Vitest coverage provider package, or None.

    Jest ships Istanbul, so this is Vitest-only; for Jest the provider is
    always considered present.
    """
    if pkg is None:
        return None
    deps = _all_deps(pkg)
    for provider in VITEST_COVERAGE_PROVIDERS:
        if provider in deps:
            return provider
    return None


# ---------------------------------------------------------------------------
# Reporter / scope detection
# ---------------------------------------------------------------------------

def _reporters_from_obj(config: dict, runner: str) -> Optional[list]:
    if runner == "jest":
        reporters = config.get("coverageReporters")
        return reporters if isinstance(reporters, list) else None
    coverage = (config.get("test") or {}).get("coverage") if isinstance(config.get("test"), dict) else None
    if isinstance(coverage, dict):
        reporter = coverage.get("reporter")
        return reporter if isinstance(reporter, list) else None
    return None


def _scope_from_obj(config: dict, runner: str) -> bool:
    if runner == "jest":
        return isinstance(config.get("collectCoverageFrom"), list) and bool(config["collectCoverageFrom"])
    test = config.get("test")
    coverage = test.get("coverage") if isinstance(test, dict) else None
    return isinstance(coverage, dict) and bool(coverage.get("include"))


# Text-scan fallbacks for JS/TS config files, which we can read but not eval.
_REPORTER_KEY = re.compile(r"coverageReporters|\breporter\b")
_SCOPE_JEST = re.compile(r"collectCoverageFrom")
_SCOPE_VITEST = re.compile(r"include\s*:")


def _has_json_summary_text(text: str) -> bool:
    return bool(re.search(r"['\"]json-summary['\"]", text)) and bool(_REPORTER_KEY.search(text))


def _has_scope_text(text: str, runner: str) -> bool:
    if runner == "jest":
        return bool(_SCOPE_JEST.search(text))
    return bool(_SCOPE_VITEST.search(text))


def assess_source(
    root: Path, runner: str, config_source: Optional[str], config_kind: str
) -> Tuple[bool, bool]:
    """Return (has_json_summary, has_scope) for the resolved config source."""
    if config_source is None:
        return False, False
    if config_source == "package.json#jest":
        pkg = _load_package_json(root) or {}
        config = pkg.get("jest", {})
        reporters = _reporters_from_obj(config, runner) or []
        return JSON_SUMMARY in reporters, _scope_from_obj(config, runner)
    path = root / config_source
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False, False
    if config_kind == "json":
        try:
            config = json.loads(text)
        except json.JSONDecodeError:
            return _has_json_summary_text(text), _has_scope_text(text, runner)
        reporters = _reporters_from_obj(config, runner) or []
        return JSON_SUMMARY in reporters, _scope_from_obj(config, runner)
    return _has_json_summary_text(text), _has_scope_text(text, runner)


# ---------------------------------------------------------------------------
# Patch (JSON configs only)
# ---------------------------------------------------------------------------

def _add_reporter_to_config(config: dict, runner: str) -> bool:
    """Add json-summary to the config dict in place. Return True if changed."""
    if runner == "jest":
        reporters = config.get("coverageReporters")
        if not isinstance(reporters, list):
            reporters = []
        if JSON_SUMMARY in reporters:
            return False
        # Preserve any existing reporters; Istanbul writes all of them.
        config["coverageReporters"] = reporters + [JSON_SUMMARY] if reporters else ["text", JSON_SUMMARY]
        return True
    test = config.setdefault("test", {})
    coverage = test.setdefault("coverage", {})
    reporter = coverage.get("reporter")
    if not isinstance(reporter, list):
        reporter = []
    if JSON_SUMMARY in reporter:
        return False
    coverage["reporter"] = reporter + [JSON_SUMMARY] if reporter else ["text", JSON_SUMMARY]
    return True


def patch_json_config(root: Path, runner: str, config_source: str) -> bool:
    """Add the json-summary reporter to a JSON-shaped config. Return True if
    the file was changed. Only ``package.json#jest`` and ``*.json`` configs are
    handled; anything else is a no-op (the caller keeps config_kind == "js")."""
    if config_source == "package.json#jest":
        path = root / "package.json"
        pkg = json.loads(path.read_text(encoding="utf-8"))
        if not _add_reporter_to_config(pkg.setdefault("jest", {}), runner):
            return False
        path.write_text(json.dumps(pkg, indent=2) + "\n", encoding="utf-8")
        return True
    path = root / config_source
    config = json.loads(path.read_text(encoding="utf-8"))
    if not _add_reporter_to_config(config, runner):
        return False
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# Hints for the caller's confirmed-edit path (JS/TS configs)
# ---------------------------------------------------------------------------

def _reporter_hint(runner: str, config_source: str) -> str:
    if runner == "jest":
        return (
            f"Add '{JSON_SUMMARY}' to `coverageReporters` in {config_source} "
            f"(e.g. ['lcov', 'clover', 'json', '{JSON_SUMMARY}'])."
        )
    return (
        f"Add '{JSON_SUMMARY}' to `test.coverage.reporter` in {config_source} "
        f"(e.g. reporter: ['text', '{JSON_SUMMARY}'])."
    )


def _scope_hint(runner: str, config_source: Optional[str]) -> str:
    where = config_source or "the runner config"
    if runner == "jest":
        return (
            f"Set `collectCoverageFrom` in {where} so coverage measures the whole "
            "source tree (e.g. ['src/**/*.{js,ts}', '!**/*.spec.*'])."
        )
    return (
        f"Set `test.coverage.include` in {where} so coverage measures the whole "
        "source tree (e.g. ['src/**/*.{js,ts}'])."
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def build_report(root: Path, patch: bool) -> Report:
    report = Report(
        runner=None,
        config_source=None,
        config_kind="none",
        has_json_summary=False,
        has_scope=False,
        ready=False,
        meaningful=False,
        patchable=False,
        patched=False,
        coverage_provider=None,
        has_provider=True,
        reporter_hint=None,
        scope_hint=None,
        provider_hint=None,
        notes=[],
    )

    pkg = _load_package_json(root)
    runner = detect_runner(root, pkg)
    report["runner"] = runner
    if runner is None:
        report.note("No Jest or Vitest runner detected; coverage-baseline readiness is not applicable.")
        return report

    config_source, config_kind = resolve_config_source(root, runner, pkg)
    report["config_source"] = config_source
    report["config_kind"] = config_kind

    has_json_summary, has_scope = assess_source(root, runner, config_source, config_kind)

    if patch and not has_json_summary and config_kind == "json":
        try:
            if patch_json_config(root, runner, config_source):
                report["patched"] = True
                report.note(f"Added '{JSON_SUMMARY}' reporter to {config_source}.")
                has_json_summary = True
        except (OSError, json.JSONDecodeError) as exc:
            report.note(f"Could not patch {config_source}: {exc}")

    # Vitest emits no coverage without a provider package; Jest ships Istanbul.
    if runner == "vitest":
        provider = detect_vitest_provider(pkg)
        report["coverage_provider"] = provider
        report["has_provider"] = provider is not None
        if provider is None:
            report["provider_hint"] = (
                "Install a Vitest coverage provider so it can emit coverage "
                f"(e.g. `npm install --save-dev {VITEST_COVERAGE_PROVIDERS[0]}`)."
            )
            report.note(
                "Vitest has no coverage provider installed; `vitest run --coverage` "
                "will error before any report is written. Offer to install "
                f"{VITEST_COVERAGE_PROVIDERS[0]} (confirm first)."
            )
    else:
        report["coverage_provider"] = "istanbul (built-in)"

    report["has_json_summary"] = has_json_summary
    report["has_scope"] = has_scope
    # Readiness needs a parseable summary AND, for Vitest, an installed provider.
    report["ready"] = has_json_summary and report["has_provider"]
    report["meaningful"] = has_scope
    report["patchable"] = (config_kind == "json")

    if not has_json_summary:
        if config_kind == "none":
            report["reporter_hint"] = (
                f"No coverage config found for {runner}; add one that includes "
                f"the '{JSON_SUMMARY}' reporter."
            )
            report.note(
                f"{runner} has no coverage config; /coverage-baseline cannot parse a summary."
            )
        elif config_kind == "js":
            report["reporter_hint"] = _reporter_hint(runner, config_source)
            report.note(
                f"{config_source} is a JS/TS config; apply the reporter edit through the "
                "confirmed edit path (this probe does not rewrite JS config files)."
            )
        else:  # json but patch was not requested or failed
            report["reporter_hint"] = _reporter_hint(runner, config_source)

    if not has_scope:
        report["scope_hint"] = _scope_hint(runner, config_source)
        report.note(
            "Coverage scope is unset; the baseline would reflect only already-tested "
            "files. Offer to add a whole-tree scope so the floor is meaningful."
        )

    return report


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("repo", nargs="?", default=".", help="Repo root (default: cwd)")
    parser.add_argument(
        "--patch",
        action="store_true",
        help="Add the json-summary reporter to JSON-shaped configs (package.json#jest / *.json).",
    )
    args = parser.parse_args(argv)

    root = Path(args.repo).resolve()
    if not (root / "package.json").is_file():
        print(
            json.dumps(
                {
                    "runner": None,
                    "config_kind": "none",
                    "ready": False,
                    "notes": ["No package.json; not a JS/TS project."],
                },
                indent=2,
            )
        )
        return 2

    report = build_report(root, patch=args.patch)
    print(json.dumps(report, indent=2))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
