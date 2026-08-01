#!/usr/bin/env python3
"""Verify the dev/CI toolchain by RUNNING each tool, not by looking for it.

Why this exists: `command -v semgrep` and `importlib.util.find_spec("semgrep")`
both succeed for a semgrep that dies on startup. That is not hypothetical — a
provisioning run on a fresh container installed semgrep, printed a green
checkmark for it, declared "Dev environment ready", and left an interpreter
where `semgrep --version` aborted with
`ModuleNotFoundError: No module named '_cffi_backend'`. Every
`plugins/security-assessment/` rule then reported NO-FIRE and the fixture audit
failed with no hint as to why.

That is the repo's own rule from CLAUDE.md, learned again the expensive way:
*verify a runtime property by exercising it at runtime*, and *a gate that
cannot fail is worse than no gate*. So every check here spawns the real thing
and reads its exit status. A tool that cannot execute fails, however tidy its
presence on `PATH` looks.

Usage:
    python3 scripts/verify_toolchain.py            # required + optional
    python3 scripts/verify_toolchain.py --quiet    # only failures
    python3 scripts/verify_toolchain.py --json     # machine-readable

Exit status is 0 when every REQUIRED check passes (optional failures only
warn), 1 otherwise. Callers that must not fail their caller — the cloud Setup
script, which fails session startup on a non-zero exit — should invoke it and
report, rather than propagate.

Stdlib only, Python 3.9+ (repo-root tooling is outside ADR 0014's 3.8 floor).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections.abc import Sequence

TIMEOUT_SECONDS = 120

# (label, argv, required, why-it-matters)
COMMAND_CHECKS: list[tuple[str, Sequence[str], bool, str]] = [
    ("jq", ["jq", "--version"], True, "mutation gate + ci-local.sh"),
    ("python3", ["python3", "--version"], True, "everything"),
    ("shellcheck", ["shellcheck", "--version"], True, "ci-local.sh shell lint"),
    ("ruff", ["ruff", "--version"], True, "chk_ruff + Python static-analysis lane"),
    ("mypy", ["mypy", "--version"], True, "Python diagnostic slot"),
    ("semgrep", ["semgrep", "--version"], True, "chk_semgrep_fixtures + security-assessment"),
    ("git", ["git", "--version"], True, "everything"),
    ("node", ["node", "--version"], False, "husky git hooks"),
    ("npm", ["npm", "--version"], False, "npm ci -> husky hooks"),
    ("gh", ["gh", "--version"], False, "PR/issue skills"),
    ("mutmut", ["mutmut", "version"], False, "Python mutation lane (/mutation-testing)"),
    ("adr", ["adr", "help"], False, "/adr-tools + adr-author agent"),
    ("uv", ["uv", "--version"], False, "installs mutmut/graphify/python3.8 floor"),
    ("graphify", ["graphify", "--version"], False, "code knowledge graph"),
]

# (module, required, why-it-matters)
IMPORT_CHECKS: list[tuple[str, bool, str]] = [
    ("yaml", True, "agent-readiness scanner, static-analysis adapter"),
    ("pytest", True, "every content-guard suite"),
    ("httpx", True, "red-team harness smoke test"),
    ("jsonschema", True, "codebase_recon.py envelope validation"),
    ("pytest_asyncio", True, "tests/scripts/test_orchestrator.py"),
    ("xdist", True, "parallel content-guard run"),
    ("pytest_cov", False, "chk_coverage_report (opt-in)"),
]


class Result:
    def __init__(self, label: str, ok: bool, required: bool, why: str, detail: str) -> None:
        self.label = label
        self.ok = ok
        self.required = required
        self.why = why
        self.detail = detail

    def as_dict(self) -> dict:
        return {
            "label": self.label,
            "ok": self.ok,
            "required": self.required,
            "why": self.why,
            "detail": self.detail,
        }


def _first_line(text: str) -> str:
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:200]
    return ""


def _run(argv: Sequence[str]) -> tuple[bool, str]:
    """Execute argv. Return (ok, detail). Never raises."""
    if shutil.which(argv[0]) is None:
        return False, "not on PATH"
    try:
        proc = subprocess.run(
            list(argv),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, f"timed out after {TIMEOUT_SECONDS}s"
    except OSError as exc:
        return False, f"could not execute: {exc}"

    output = proc.stdout.decode("utf-8", "replace")
    if proc.returncode != 0:
        # This is the branch presence-checks miss: the binary exists and still
        # cannot run. Surface the interpreter's own words — they name the
        # missing extension module or broken dependency.
        return False, "exit {}: {}".format(proc.returncode, _first_line(output) or "(no output)")
    return True, _first_line(output)


def check_commands() -> list[Result]:
    results = []
    for label, argv, required, why in COMMAND_CHECKS:
        ok, detail = _run(argv)
        results.append(Result(label, ok, required, why, detail))
    return results


def check_imports() -> list[Result]:
    """Import each module in a SUBPROCESS.

    A broken native extension does not raise a catchable ImportError — the
    PyJWT/cryptography breakage this script was written for aborted the whole
    interpreter through a pyo3 panic. Importing in-process would take this
    verifier down with it and report nothing.
    """
    results = []
    for module, required, why in IMPORT_CHECKS:
        ok, detail = _run([sys.executable, "-c", f"import {module}"])
        results.append(Result(f"python: {module}", ok, required, why, detail))
    return results


def render(results: Sequence[Result], quiet: bool) -> None:
    for r in results:
        if r.ok:
            if not quiet:
                suffix = f" ({r.detail})" if r.detail else ""
                print(f"  ✓ {r.label}{suffix}")
        else:
            tag = "✗" if r.required else "∼"
            scope = "REQUIRED" if r.required else "optional"
            print(f"  {tag} {r.label} [{scope}] — {r.detail}")
            print(f"      needed for: {r.why}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--quiet", action="store_true", help="print only failures")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    args = parser.parse_args(list(argv) if argv is not None else None)

    results = check_commands() + check_imports()
    failed_required = [r for r in results if not r.ok and r.required]
    failed_optional = [r for r in results if not r.ok and not r.required]

    if args.json:
        print(
            json.dumps(
                {
                    "ok": not failed_required,
                    "required_failures": [r.label for r in failed_required],
                    "optional_failures": [r.label for r in failed_optional],
                    "results": [r.as_dict() for r in results],
                },
                indent=2,
            )
        )
        return 1 if failed_required else 0

    if not args.quiet:
        print("== toolchain verification (executing each tool) ==")
    render(results, args.quiet)

    if failed_required:
        print(
            "\nFAILED: {} required tool(s) could not run: {}".format(
                len(failed_required), ", ".join(r.label for r in failed_required)
            )
        )
        print("These are execution failures, not missing-binary reports — a tool")
        print("can be installed and on PATH and still be unable to start.")
        return 1

    if not args.quiet:
        print("\nAll required tools executed successfully.")
        if failed_optional:
            print(
                "Optional not available: {}".format(
                    ", ".join(r.label for r in failed_optional)
                )
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
