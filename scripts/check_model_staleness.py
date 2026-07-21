#!/usr/bin/env python3
"""Detect pinned models in model-routing.json that are no longer served (#1271).

`plugins/dev-team/knowledge/model-routing.json` pins exact model IDs. Anthropic
deprecates and retires models on a timeline, so a pinned ID can silently go
stale. This script is invoked by `.github/workflows/model-staleness.yml` on a
weekly cron: it reads the pinned IDs, fetches the live catalog from the Models
API (`GET /v1/models`), and opens (or leaves alone, if already open) a single
deduped tracking issue when any pinned ID has disappeared from the catalog.

Auth: `ANTHROPIC_API_KEY` in the environment. Endpoint host is `ANTHROPIC_BASE_URL`
if set (so a self-hosted-runner/proxy variant is a config change, not a rewrite),
else api.anthropic.com. GitHub calls go through `gh` (needs `GH_TOKEN`), mirroring
scripts/epic_auto_close.py.

Usage: check_model_staleness.py --repo OWNER/REPO [--routing PATH] [--dry-run]

Stdlib-only. Python 3.8+.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request

DEFAULT_ROUTING = "plugins/dev-team/knowledge/model-routing.json"
DEFAULT_BASE_URL = "https://api.anthropic.com"
ANTHROPIC_VERSION = "2023-06-01"
ISSUE_TITLE = "chore: pinned model(s) in model-routing.json are no longer served"


def pinned_model_ids(routing: dict) -> list:
    """Distinct model IDs pinned in routing.json, sorted.

    Only values that look like model IDs (start with `claude-`) are returned,
    so convention markers such as `rounding: round_half_up` are skipped. Keys
    are irrelevant — a model listed under several keys collapses to one entry.
    """
    ids = {
        v for v in routing.values() if isinstance(v, str) and v.startswith("claude-")
    }
    return sorted(ids)


def stale_models(pinned: list, live_ids) -> list:
    """Pinned IDs absent from the live catalog, order-preserved."""
    live = set(live_ids)
    return [model for model in pinned if model not in live]


def issue_body(stale: list, live_ids: list) -> str:
    """Markdown body for the tracking issue."""
    stale_lines = "\n".join(f"- `{m}`" for m in stale)
    active = "\n".join(f"- `{m}`" for m in sorted(live_ids) if m.startswith("claude-"))
    return (
        "The weekly model-staleness check found pinned model ID(s) in "
        "`plugins/dev-team/knowledge/model-routing.json` that the Models API "
        "(`GET /v1/models`) no longer returns — they are deprecated or "
        "retired.\n\n"
        "## No longer served\n\n"
        f"{stale_lines}\n\n"
        "## Fix\n\n"
        "Repoint each stale band in `model-routing.json` to a current, "
        "bare canonical ID (no dated snapshot suffix — see ADR 0024), then "
        "run the routing tests:\n\n"
        "```\n"
        "pytest tests/knowledge/test_model_routing_defaults.py \\\n"
        "  plugins/dev-team/tests/hooks/test_model_resolve.py\n"
        "```\n\n"
        "## Currently served `claude-*` models\n\n"
        f"{active}\n\n"
        "---\n"
        "_Filed automatically by `scripts/check_model_staleness.py` "
        "(`.github/workflows/model-staleness.yml`)._"
    )


def fetch_live_model_ids(base_url: str, api_key: str) -> list:
    """Every served model ID via `GET /v1/models`, following pagination.

    Raises on transport/auth failure so an infra problem surfaces as a
    non-zero process exit (CI red) rather than being mistaken for "nothing
    stale".
    """
    ids: list = []
    after: str = ""
    while True:
        url = f"{base_url.rstrip('/')}/v1/models?limit=100"
        if after:
            url += f"&after_id={after}"
        req = urllib.request.Request(
            url,
            headers={
                "x-api-key": api_key,
                "anthropic-version": ANTHROPIC_VERSION,
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        ids.extend(model["id"] for model in payload.get("data", []))
        if not payload.get("has_more"):
            break
        after = payload.get("last_id") or ""
        if not after:
            break
    return ids


def find_open_issue(repo: str, title: str) -> int:
    """Number of an open issue whose title matches exactly, or 0 if none."""
    result = subprocess.run(
        [
            "gh",
            "issue",
            "list",
            "--repo",
            repo,
            "--state",
            "open",
            "--search",
            f'"{title}" in:title',
            "--json",
            "number,title",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    for issue in json.loads(result.stdout):
        if issue.get("title") == title:
            return int(issue["number"])
    return 0


def create_issue(repo: str, title: str, body: str) -> None:
    subprocess.run(
        ["gh", "issue", "create", "--repo", repo, "--title", title, "--body", body],
        check=True,
    )


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="OWNER/REPO")
    parser.add_argument(
        "--routing", default=DEFAULT_ROUTING, help="Path to routing.json"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report staleness but do not open an issue.",
    )
    args = parser.parse_args(argv)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ANTHROPIC_API_KEY is not set.", file=sys.stderr)
        return 2
    base_url = os.environ.get("ANTHROPIC_BASE_URL") or DEFAULT_BASE_URL

    with open(args.routing, "r", encoding="utf-8") as fh:
        routing = json.load(fh)
    pinned = pinned_model_ids(routing)
    if not pinned:
        print(f"No pinned model IDs found in {args.routing}; nothing to check.")
        return 0

    live_ids = fetch_live_model_ids(base_url, api_key)
    stale = stale_models(pinned, live_ids)

    print(f"Pinned: {', '.join(pinned)}")
    print(f"Live catalog: {len(live_ids)} models")

    if not stale:
        print("All pinned models are currently served. Nothing to do.")
        return 0

    print(f"STALE (no longer served): {', '.join(stale)}")
    if args.dry_run:
        print("Dry run — not opening an issue.")
        return 0

    existing = find_open_issue(args.repo, ISSUE_TITLE)
    if existing:
        print(f"Tracking issue already open (#{existing}); not filing a duplicate.")
        return 0

    create_issue(args.repo, ISSUE_TITLE, issue_body(stale, live_ids))
    print("Opened tracking issue.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
