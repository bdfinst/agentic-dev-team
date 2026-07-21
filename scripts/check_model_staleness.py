#!/usr/bin/env python3
"""Keep model-routing.json pinned to the latest version of each model family (#1271).

`plugins/dev-team/knowledge/model-routing.json` pins exact model IDs. Anthropic
ships new versions and retires old ones on a timeline. This script (invoked
weekly by `.github/workflows/model-staleness.yml`, or on demand) reconciles the
pins against the live catalog from the Models API (`GET /v1/models`):

  * For each pinned ID it derives the model *family* (the tier word, ignoring
    version digits — e.g. `claude-opus-4-8` -> `opus`) and finds the newest
    member of that family in the live catalog, ranked by `created_at`.
    `created_at` — not version-digit parsing — is used deliberately: the old
    `claude-3-haiku-20240307` naming puts the number first, so digit parsing
    mis-sorts across naming schemes.
  * When the newest family member differs from the pinned ID, it opens (or
    reuses) a PR that repoints `model-routing.json` to the newer ID. The PR's
    commit is created through the GitHub GraphQL API (`createCommitOnBranch`),
    so it is verified/signed and satisfies the branch ruleset.
  * When a pinned family has NO live members at all (whole tier removed — can't
    be auto-fixed), it opens a deduped tracking issue instead.

Auth: `ANTHROPIC_API_KEY` for the catalog; `GH_TOKEN` for GitHub. The workflow
supplies a token minted from the release-bot GitHub App (the same identity
release-please uses) with contents + pull-requests write, so the opened PR
triggers the required checks and its API-created commit is verified.
`ANTHROPIC_BASE_URL` overrides the API host (self-hosted-runner/proxy variant).

Usage: check_model_staleness.py --repo OWNER/REPO [--base BRANCH]
                                [--routing PATH] [--dry-run]

Stdlib-only. Python 3.8+.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request

DEFAULT_ROUTING = "plugins/dev-team/knowledge/model-routing.json"
DEFAULT_BASE_URL = "https://api.anthropic.com"
DEFAULT_BASE_BRANCH = "main"
ANTHROPIC_VERSION = "2023-06-01"
BRANCH_PREFIX = "chore/pin-latest-models-"
PR_TITLE = "chore: pin latest model versions in model-routing.json"
ISSUE_TITLE = "chore: pinned model family in model-routing.json has no live successor"

_MODEL_PREFIX = "claude-"
_DIGITS = re.compile(r"^\d+$")


def pinned_model_ids(routing: dict) -> list:
    """Distinct model IDs pinned in routing.json, sorted.

    Only values that look like model IDs (start with `claude-`) are returned,
    so convention markers such as `rounding: round_half_up` are skipped. Keys
    are irrelevant — a model listed under several keys collapses to one entry.
    """
    ids = {
        v
        for v in routing.values()
        if isinstance(v, str) and v.startswith(_MODEL_PREFIX)
    }
    return sorted(ids)


def family_of(model_id: str) -> str:
    """The tier word of a model ID, with `claude-` and all version digits removed.

    `claude-opus-4-8` -> `opus`; `claude-sonnet-5` -> `sonnet`;
    `claude-3-7-sonnet-20250219` -> `sonnet`; `claude-haiku-4-5` -> `haiku`.
    Non-numeric tokens (other than the `claude` marker) are joined with `-`, so
    a hypothetical multi-word family still round-trips.
    """
    tokens = model_id.split("-")
    words = [t for t in tokens if t != "claude" and t and not _DIGITS.match(t)]
    return "-".join(words)


def latest_in_family(family: str, live_models: list) -> dict:
    """The newest live model in `family` (by `created_at`), or {} if none.

    `live_models` is a list of `{"id", "created_at"}`. `created_at` is ISO-8601
    UTC, so lexical max is chronological max.
    """
    members = [m for m in live_models if family_of(m["id"]) == family]
    if not members:
        return {}
    return max(members, key=lambda m: m.get("created_at", ""))


def plan_bumps(pinned: list, live_models: list):
    """Return (bumps, gone).

    `bumps` maps each pinned ID whose family has a newer member to that newer
    ID. `gone` lists pinned IDs whose family has no live members at all (no
    successor — cannot be auto-bumped).
    """
    bumps: dict = {}
    gone: list = []
    for old in pinned:
        latest = latest_in_family(family_of(old), live_models)
        if not latest:
            gone.append(old)
        elif latest["id"] != old:
            bumps[old] = latest["id"]
    return bumps, gone


def rewrite_routing_text(raw: str, id_map: dict) -> str:
    """Replace each old model ID with its new ID in the raw JSON text.

    Operates on the quoted string form (`"<id>"`) so formatting and comments-as-
    blank-lines are preserved and a shorter ID can't match inside a longer one.
    """
    for old, new in id_map.items():
        raw = raw.replace(f'"{old}"', f'"{new}"')
    return raw


def branch_name(bumps: dict) -> str:
    """Deterministic branch name for a given target set of bumps.

    Same desired bumps -> same branch (dedup); a new target -> a new branch.
    """
    digest = hashlib.sha1(
        json.dumps(bumps, sort_keys=True).encode("utf-8")
    ).hexdigest()[:12]
    return f"{BRANCH_PREFIX}{digest}"


def pr_body(bumps: dict) -> str:
    rows = "\n".join(f"- `{old}` → `{new}`" for old, new in sorted(bumps.items()))
    return (
        "The weekly model-staleness check found newer versions available for "
        "model families pinned in `plugins/dev-team/knowledge/model-routing.json`.\n\n"
        "## Proposed bumps\n\n"
        f"{rows}\n\n"
        '"Newest" is the family member with the latest `created_at` in the '
        "Models API (`GET /v1/models`) — not a version-digit sort, which "
        "mis-orders the older `claude-3-*` naming.\n\n"
        "Review that each new ID is the intended tier before merging.\n\n"
        "---\n"
        "_Opened automatically by `scripts/check_model_staleness.py` "
        "(`.github/workflows/model-staleness.yml`)._"
    )


def issue_body(gone: list, live_ids: list) -> str:
    gone_lines = "\n".join(f"- `{m}`" for m in gone)
    active = "\n".join(
        f"- `{m}`" for m in sorted(live_ids) if m.startswith(_MODEL_PREFIX)
    )
    return (
        "The weekly model-staleness check found pinned model ID(s) whose whole "
        "family has disappeared from the Models API — there is no newer version "
        "to bump to automatically, so this needs a human decision.\n\n"
        "## No live successor\n\n"
        f"{gone_lines}\n\n"
        "Repoint each affected band in `model-routing.json` to a current, bare "
        "canonical ID (no dated snapshot suffix — see ADR 0024), then run:\n\n"
        "```\n"
        "pytest tests/knowledge/test_model_routing_defaults.py \\\n"
        "  plugins/dev-team/tests/hooks/test_model_resolve.py\n"
        "```\n\n"
        "## Currently served `claude-*` models\n\n"
        f"{active}\n\n"
        "---\n"
        "_Filed automatically by `scripts/check_model_staleness.py`._"
    )


# --- I/O boundaries --------------------------------------------------------


def fetch_live_models(base_url: str, api_key: str) -> list:
    """Every served model as `{"id", "created_at"}` via `GET /v1/models`.

    Raises on transport/auth failure so an infra problem surfaces as a non-zero
    process exit (CI red) rather than being mistaken for "nothing to do".
    """
    models: list = []
    after: str = ""
    while True:
        url = f"{base_url.rstrip('/')}/v1/models?limit=100"
        if after:
            url += f"&after_id={after}"
        req = urllib.request.Request(
            url,
            headers={"x-api-key": api_key, "anthropic-version": ANTHROPIC_VERSION},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        for model in payload.get("data", []):
            models.append(
                {"id": model["id"], "created_at": model.get("created_at", "")}
            )
        if not payload.get("has_more"):
            break
        after = payload.get("last_id") or ""
        if not after:
            break
    return models


def _gh(args: list, check: bool = True, stdin: str = None) -> str:
    result = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        check=check,
        input=stdin,
    )
    return result.stdout


def open_pr_for_branch(repo: str, branch: str) -> int:
    """Number of an open PR whose head is `branch`, or 0 if none."""
    out = _gh(
        [
            "pr",
            "list",
            "--repo",
            repo,
            "--head",
            branch,
            "--state",
            "open",
            "--json",
            "number",
        ]
    )
    prs = json.loads(out)
    return int(prs[0]["number"]) if prs else 0


def _ref_sha(repo: str, ref: str) -> str:
    out = _gh(["api", f"repos/{repo}/git/ref/heads/{ref}"])
    return json.loads(out)["object"]["sha"]


def create_branch(repo: str, branch: str, sha: str) -> None:
    _gh(
        [
            "api",
            f"repos/{repo}/git/refs",
            "-f",
            f"ref=refs/heads/{branch}",
            "-f",
            f"sha={sha}",
        ]
    )


def commit_file(
    repo: str, branch: str, expected_head: str, path: str, content: str, message: str
) -> None:
    """Create a verified commit on `branch` via the GraphQL API."""
    payload = {
        "query": (
            "mutation($input: CreateCommitOnBranchInput!) {"
            " createCommitOnBranch(input: $input) { commit { oid } } }"
        ),
        "variables": {
            "input": {
                "branch": {
                    "repositoryNameWithOwner": repo,
                    "branchName": branch,
                },
                "message": {"headline": message},
                "expectedHeadOid": expected_head,
                "fileChanges": {
                    "additions": [
                        {
                            "path": path,
                            "contents": base64.b64encode(
                                content.encode("utf-8")
                            ).decode("ascii"),
                        }
                    ]
                },
            }
        },
    }
    _gh(["api", "graphql", "--input", "-"], stdin=json.dumps(payload))


def create_pr(repo: str, base: str, branch: str, title: str, body: str) -> None:
    _gh(
        [
            "pr",
            "create",
            "--repo",
            repo,
            "--base",
            base,
            "--head",
            branch,
            "--title",
            title,
            "--body",
            body,
        ]
    )


def open_bump_pr(
    repo: str, base: str, branch: str, path: str, content: str, title: str, body: str
) -> None:
    """Create `branch` at base head, commit the rewritten file, and open a PR."""
    base_sha = _ref_sha(repo, base)
    create_branch(repo, branch, base_sha)
    commit_file(repo, branch, base_sha, path, content, title)
    create_pr(repo, base, branch, title, body)


def close_superseded_bump_prs(repo: str, keep_branch: str) -> None:
    """Close any older open bump PRs (branch prefix) that aren't `keep_branch`."""
    out = _gh(
        [
            "pr",
            "list",
            "--repo",
            repo,
            "--state",
            "open",
            "--json",
            "number,headRefName",
        ]
    )
    for pr in json.loads(out):
        head = pr.get("headRefName", "")
        if head.startswith(BRANCH_PREFIX) and head != keep_branch:
            _gh(
                [
                    "pr",
                    "close",
                    str(pr["number"]),
                    "--repo",
                    repo,
                    "--comment",
                    f"Superseded by a newer pin PR (#{keep_branch}).",
                ],
                check=False,
            )


def find_open_issue(repo: str, title: str) -> int:
    out = _gh(
        [
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
        ]
    )
    for issue in json.loads(out):
        if issue.get("title") == title:
            return int(issue["number"])
    return 0


def create_issue(repo: str, title: str, body: str) -> None:
    _gh(["issue", "create", "--repo", repo, "--title", title, "--body", body])


# --- orchestration ---------------------------------------------------------


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="OWNER/REPO")
    parser.add_argument("--base", default=DEFAULT_BASE_BRANCH, help="Base branch")
    parser.add_argument(
        "--routing", default=DEFAULT_ROUTING, help="Path to routing.json"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report bumps but open no PR or issue.",
    )
    args = parser.parse_args(argv)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ANTHROPIC_API_KEY is not set.", file=sys.stderr)
        return 2
    base_url = os.environ.get("ANTHROPIC_BASE_URL") or DEFAULT_BASE_URL

    with open(args.routing, "r", encoding="utf-8") as fh:
        raw = fh.read()
    routing = json.loads(raw)
    pinned = pinned_model_ids(routing)
    if not pinned:
        print(f"No pinned model IDs found in {args.routing}; nothing to check.")
        return 0

    live_models = fetch_live_models(base_url, api_key)
    live_ids = [m["id"] for m in live_models]
    bumps, gone = plan_bumps(pinned, live_models)

    print(f"Pinned: {', '.join(pinned)}")
    print(f"Live catalog: {len(live_ids)} models")

    if not bumps and not gone:
        print("All pinned models are the latest in their family. Nothing to do.")
        return 0

    if bumps:
        summary = ", ".join(f"{o}->{n}" for o, n in sorted(bumps.items()))
        print(f"BUMPS: {summary}")
        branch = branch_name(bumps)
        if args.dry_run:
            print(f"Dry run — would open PR on branch {branch}.")
        else:
            existing = open_pr_for_branch(args.repo, branch)
            if existing:
                print(f"Bump PR already open (#{existing}); not duplicating.")
            else:
                new_content = rewrite_routing_text(raw, bumps)
                open_bump_pr(
                    args.repo,
                    args.base,
                    branch,
                    args.routing,
                    new_content,
                    PR_TITLE,
                    pr_body(bumps),
                )
                close_superseded_bump_prs(args.repo, branch)
                print(f"Opened bump PR on branch {branch}.")

    if gone:
        print(f"NO SUCCESSOR (family removed): {', '.join(gone)}")
        if args.dry_run:
            print("Dry run — would file a tracking issue.")
        else:
            existing = find_open_issue(args.repo, ISSUE_TITLE)
            if existing:
                print(f"Tracking issue already open (#{existing}); not duplicating.")
            else:
                create_issue(args.repo, ISSUE_TITLE, issue_body(gone, live_ids))
                print("Opened tracking issue.")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
