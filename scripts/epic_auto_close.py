#!/usr/bin/env python3
"""Close an epic issue once every one of its sub-issues is closed (#987).

GitHub's native sub-issues feature tracks completion percentage only — it
does not close a parent/epic issue when every sub-issue closes (verified
directly on epic #971, which stayed OPEN at 100% sub-issue completion until
closed by hand). This script is invoked by
`.github/workflows/epic-auto-close.yml` on every `issues: closed` event; it
inspects the closed issue's parent (if any) and closes the parent once every
sibling sub-issue is closed.

Usage: epic_auto_close.py --repo OWNER/REPO --issue N

Stdlib-only. Python 3.8+.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys


def should_close_parent(sub_issues: list) -> bool:
    """Return True only when every sub-issue is closed.

    `state_reason` is never inspected — a "closed" issue is closed regardless
    of whether it was completed or marked not-planned. An empty list returns
    False: there is nothing to confirm complete.
    """
    if not sub_issues:
        return False
    return all(issue.get("state") == "closed" for issue in sub_issues)


def _gh_api(path: str) -> dict:
    """Run `gh api <path>` and return the parsed JSON response.

    Lets `subprocess.CalledProcessError` (non-zero exit) and
    `json.JSONDecodeError` (malformed output) propagate uncaught — a `gh api`
    failure must surface as a non-zero process exit, never be swallowed.
    """
    result = subprocess.run(
        ["gh", "api", path],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def get_issue(repo: str, number: int) -> dict:
    """Fetch a single issue's JSON representation."""
    return _gh_api(f"repos/{repo}/issues/{number}")


def get_sub_issues(repo: str, number: int) -> list:
    """Fetch the list of an issue's sub-issues."""
    return _gh_api(f"repos/{repo}/issues/{number}/sub_issues")


def parent_number_from_url(url: str) -> int:
    """Extract the trailing issue number from a `parent_issue_url`.

    e.g. "https://api.github.com/repos/OWNER/REPO/issues/971" -> 971.
    Tolerates a trailing slash.
    """
    return int(url.rstrip("/").rsplit("/", 1)[-1])


def close_parent(repo: str, parent_number: int, closed_child: int) -> None:
    """Close the parent issue with an explanatory comment."""
    comment = (
        "Closed automatically by the epic-auto-close workflow: every "
        f"sub-issue is now closed (triggered by #{closed_child})."
    )
    subprocess.run(
        [
            "gh",
            "issue",
            "close",
            str(parent_number),
            "--repo",
            repo,
            "--comment",
            comment,
        ],
        check=True,
    )


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="OWNER/REPO")
    parser.add_argument("--issue", required=True, type=int, help="Closed issue number")
    args = parser.parse_args(argv)

    issue = get_issue(args.repo, args.issue)

    parent_url = issue.get("parent_issue_url")
    if not parent_url:
        print(f"Issue #{args.issue} has no parent issue; nothing to do.")
        return 0

    parent_number = parent_number_from_url(parent_url)
    parent = get_issue(args.repo, parent_number)

    if parent.get("state") == "closed":
        print(f"Parent issue #{parent_number} is already closed; nothing to do.")
        return 0

    sub_issues = get_sub_issues(args.repo, parent_number)

    if not should_close_parent(sub_issues):
        print(f"Parent issue #{parent_number} still has open sub-issues; not closing.")
        return 0

    close_parent(args.repo, parent_number, args.issue)
    print(
        f"Closed parent issue #{parent_number}: all sub-issues closed "
        f"(triggered by #{args.issue})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
