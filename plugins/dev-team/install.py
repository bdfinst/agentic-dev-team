#!/usr/bin/env python3
"""Python port of install.sh (#616 / #572 Phase 3).

Verify prerequisites for the dev-team plugin.

Run this after installing the plugin to confirm all required and optional
dependencies are available. On Windows this file is invoked from a Git Bash
`install.sh` trampoline that runs before Python 3 is guaranteed on PATH —
so the .sh stays around per ADR 0014 as the platform-detection prelude, and
this script implements the actual dependency checks.

Usage:
    plugins/dev-team/install.py

Stdlib-only. Python 3.8+.
"""

from __future__ import annotations

import os
import platform
import shutil
import sys
from typing import List, Tuple


# ---------------------------------------------------------------------------
# Counters
# ---------------------------------------------------------------------------


class Result:
    def __init__(self) -> None:
        self.pass_ = 0
        self.warn = 0
        self.fail = 0


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def check_required(result: Result, cmd: str, install_hint: str) -> None:
    if shutil.which(cmd):
        print(f"[ok]   {cmd}")
        result.pass_ += 1
    else:
        print(f"[FAIL] {cmd} — required. {install_hint}")
        result.fail += 1


def check_optional(result: Result, cmd: str, purpose: str, install_hint: str) -> None:
    if shutil.which(cmd):
        print(f"[ok]   {cmd}")
        result.pass_ += 1
    else:
        print(f"[warn] {cmd} — optional ({purpose}). {install_hint}")
        result.warn += 1


def _detect_windows_uname() -> str:
    """On Git Bash / MSYS2 / Cygwin, `uname -s` reports MINGW64_NT-… /
    MSYS_NT-… / CYGWIN_NT-…. Python's platform.uname() surfaces the same
    string; we fall back to `os.name` on native Windows."""
    try:
        return platform.uname().system
    except Exception:  # noqa: BLE001
        return ""


def check_platform(result: Result) -> None:
    """Report the Windows shell environment, informationally only.

    Per ADR 0015 (docs/adr/0015-bash-removal-complete.md), every shipped
    hook and helper script under plugins/dev-team/ is now Python 3.8+
    stdlib-only — Windows CI is fully bash-free and nothing in the
    runtime requires Git Bash on Windows anymore. Native Windows without
    Git Bash is a legitimate install path, so this check never fails; it
    only surfaces which shell Claude Code is running under. It's a no-op
    on macOS and Linux."""
    if os.environ.get("OS", "") != "Windows_NT":
        return
    uname = _detect_windows_uname()
    if uname.startswith(("MINGW", "MSYS", "CYGWIN")):
        print(f"[ok]   Git Bash ({uname})")
    else:
        print("[ok]   native Windows (no Git Bash required — plugin is Python-only)")
    result.pass_ += 1


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    result = Result()

    print("Checking dev-team prerequisites...")
    print("")

    print("--- Required ---")
    check_platform(result)
    check_required(
        result,
        "claude",
        "Install from https://docs.anthropic.com/en/docs/claude-code",
    )
    check_required(result, "jq", "macOS: brew install jq  |  Linux: apt install jq")
    check_required(result, "gh", "macOS: brew install gh  |  https://cli.github.com/")

    print("")
    print("--- Optional ---")
    check_optional(
        result,
        "semgrep",
        "SAST scanning via /semgrep-analyze",
        "pip install semgrep  |  brew install semgrep",
    )
    check_optional(
        result,
        "hadolint",
        "Dockerfile linting via /docker-image-audit",
        "brew install hadolint  |  https://github.com/hadolint/hadolint/releases",
    )
    check_optional(
        result,
        "trivy",
        "image vulnerability scanning via /docker-image-audit",
        "brew install trivy  |  https://aquasecurity.github.io/trivy/",
    )
    check_optional(
        result,
        "grype",
        "second-opinion CVE scanning via /docker-image-audit",
        "brew install grype  |  https://github.com/anchore/grype",
    )

    print("")

    if result.fail > 0:
        print(
            f"Result: {result.fail} required dependency missing. Install it and re-run."
        )
        return 1
    if result.warn > 0:
        print(
            f"Result: All required dependencies present. {result.warn} optional "
            "dependency missing (see above)."
        )
        return 0
    print("Result: All dependencies present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
