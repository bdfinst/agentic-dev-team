#!/usr/bin/env python3
"""Python port of scripts/git-origin-host.sh (#613 / #572 Phase 3).

Classify the `origin` remote so /plan only offers GitHub issue creation on an
actual GitHub host.

Prints exactly one of:
    github  — github.com OR an enterprise GHE host (any dot-label equals "github")
    other   — a non-GitHub host, including lookalikes like notgithub.example.com
    none    — no origin remote, or an unparseable URL (fail-open: never blocks)

Reads `git remote get-url origin` unless a URL is given as argv[1] (for testing).

Usage: git_origin_host.py [remote-url]

Stdlib-only. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import subprocess
import sys


def classify(url: str) -> str:
    """Return "github", "other", or "none" for a remote URL string.

    Extracts the host from https://, ssh://, or scp-like (git@host:path) forms,
    lowercases it, then matches a whole dot-label of "github" (covers github.com
    and enterprise GHE such as github.example.com). A substring like "notgithub"
    or "mygithub" does NOT match, because the pattern requires a dot immediately
    before "github".
    """
    if not url:
        return "none"

    host = ""
    if "://" in url:
        rest = url.split("://", 1)[1]
        # Strip optional user@ prefix.
        if "@" in rest:
            rest = rest.split("@", 1)[1]
        # Take up to the first `/`, then trim port suffix `:PORT`.
        host = rest.split("/", 1)[0]
        host = host.split(":", 1)[0]
    elif "@" in url and ":" in url.split("@", 1)[1]:
        # scp-like: user@host:path
        rest = url.split("@", 1)[1]
        host = rest.split(":", 1)[0]
    else:
        host = url.split(":", 1)[0]

    host = host.lower()
    if not host:
        return "none"

    # Match a whole dot-label of "github".
    if ".github." in "." + host + ".":
        return "github"
    return "other"


def read_origin_url() -> str:
    """Return `git remote get-url origin` stdout, or "" on any failure."""
    try:
        completed = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=False,
        )
    except (FileNotFoundError, OSError):
        return ""
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def main(argv: list) -> int:
    url = argv[1] if len(argv) > 1 else ""
    if not url:
        url = read_origin_url()
    print(classify(url))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
