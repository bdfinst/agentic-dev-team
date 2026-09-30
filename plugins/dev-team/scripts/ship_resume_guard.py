#!/usr/bin/env python3
"""Deterministic /ship resume-guard verdict (#2213).

Replaces the model-applied verdict tree in ``skills/ship`` Step 1a. ``verdict``
is pure; ``probe`` is the I/O boundary (``gh`` via argv lists, never a shell
string). Verdicts: ``shipped | monitor | resume | batch-blocked |
partial-batch | first-run | probe-failed``. ``probe-failed`` is fail-safe —
the caller must ask the human, never assume ``first-run``.

Stdlib-only. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

CLOSE_KEYWORDS = r"(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)"


def batch_key(issues: list[int]) -> str:
    return "issues-" + "-".join(str(n) for n in sorted(issues))


def _closes(pr: dict, n: int) -> bool:
    body = pr.get("body") or ""
    return bool(re.search(rf"(?i)\b{CLOSE_KEYWORDS}\s+#{n}\b", body)) or \
        pr.get("headRefName") == f"issue-{n}"


def _own_batch_pr(pr: dict, key: str) -> bool:
    return pr.get("headRefName") == key and not pr.get("isCrossRepository", False)


def verdict(issues: list[int], issue_state: dict, prs: list[dict],
            artifacts: bool) -> dict:
    """``issue_state``: {n: "OPEN"|"CLOSED"}; ``prs``: gh pr rows (all states)."""
    batch = len(issues) > 1
    key = batch_key(issues)
    closed = [n for n in issues if issue_state.get(n) == "CLOSED"]
    open_ = [n for n in issues if n not in closed]

    if not open_:
        return {"verdict": "shipped", "signal": "all-issues-closed", "closed": closed}

    merged = [p for p in prs if p.get("state") == "MERGED"
              and any(_closes(p, n) for n in open_)]
    if not batch and merged:
        return {"verdict": "shipped", "signal": "merged-pr", "pr": merged[0]["number"]}

    own = [p for p in prs if p.get("state") == "OPEN" and batch and _own_batch_pr(p, key)]
    if own:
        return {"verdict": "monitor", "signal": "own-batch-pr", "pr": own[0]["number"]}
    if closed:
        return {"verdict": "partial-batch", "signal": "mixed-closed-state",
                "closed": closed, "open": open_}

    blockers = [p for p in prs if p.get("state") == "OPEN"
                and any(_closes(p, n) for n in open_)]
    if blockers:
        if batch:
            return {"verdict": "batch-blocked", "signal": "foreign-open-pr",
                    "pr": blockers[0]["number"]}
        return {"verdict": "monitor", "signal": "open-pr", "pr": blockers[0]["number"]}

    if artifacts:
        return {"verdict": "resume", "signal": "spec-or-plan-exists"}
    return {"verdict": "first-run", "signal": "nothing-found"}


def _gh(args: list[str]):
    out = subprocess.run(["gh", *args], capture_output=True, text=True, check=True)
    return json.loads(out.stdout or "null")


def probe(issues: list[int], root: Path):
    """Return ``(issue_state, prs, artifacts)`` or raise on any probe error."""
    issue_state = {n: _gh(["issue", "view", str(n), "--json", "state"])["state"]
                   for n in issues}
    fields = "number,state,headRefName,body,isCrossRepository"
    seen: dict[int, dict] = {}
    queries = [["--search", str(n)] for n in issues]
    queries += [["--head", f"issue-{n}"] for n in issues]
    if len(issues) > 1:
        queries.append(["--head", batch_key(issues)])
    for q in queries:
        for pr in _gh(["pr", "list", "--state", "all", "--json", fields, *q]) or []:
            seen[pr["number"]] = pr
    return issue_state, list(seen.values()), _artifacts_exist(issues, root)


def _artifacts_exist(issues: list[int], root: Path) -> bool:
    needles = [f"#{n}" for n in issues]
    for pattern in ("docs/specs/**/plans/*.md", "docs/specs/**/spec.md", "plans/*.md"):
        for f in root.glob(pattern):
            try:
                text = f.read_text(encoding="utf-8")
            except OSError:
                continue
            if any(re.search(rf"{re.escape(t)}\b", text) for t in needles):
                return True
    return False


def parse_issues(raw: str) -> list[int]:
    tokens = [t.strip() for t in raw.split(",")]
    for t in tokens:
        if not re.fullmatch(r"[0-9]+", t):
            raise ValueError(f"invalid issue token: {t!r}")
    return [int(t) for t in tokens]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--issues", required=True, help="comma-separated issue numbers")
    p.add_argument("--root", type=Path, default=Path("."))
    args = p.parse_args(argv)
    try:
        issues = parse_issues(args.issues)
    except ValueError as exc:
        p.error(str(exc))
    try:
        state, prs, artifacts = probe(issues, args.root)
    except (OSError, subprocess.CalledProcessError, ValueError, KeyError) as exc:
        print(json.dumps({"verdict": "probe-failed", "error": str(exc)}))
        return 0
    print(json.dumps(verdict(issues, state, prs, artifacts)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
