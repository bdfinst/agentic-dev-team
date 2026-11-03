"""Shared repo and record builders for the acceptance-examination tests (#2270).

Reachable from both test roots: `plugins/dev-team/tests/hooks` and
`tests/scripts` put this directory on `sys.path` and import it by bare name.

`make_repo` builds a pinned temp git repository: `main` with one commit and
`work` one commit ahead, holding `plans/x.md` and (by default) a source file.
`row` and `record` build the dict shapes the store, gate, and CLI read.

Every `git` call runs with `git_env`: no inherited repo redirection
(`GIT_DIR` and friends), no user git config, and no repository discovery
above the test's temp directory. A repository's root must be a direct child
of the temp directory it uses as `HOME`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from hermetic import hermetic_git_env  # type: ignore[import-not-found]

PLAN_ID = "plans/x.md"
RECORD_IGNORE = ".claude/memory/acceptance-examination-*.json*"  # plus its .lock
SOURCE_FILE = "docs/feature.md"  # documentation: no /verify log needed
RUN_COMMAND = "python3 -m pytest -q"
CRITERION_1 = "The first behavior works"
CRITERION_2 = "The second behavior works"
PLAN_TEXT = f"""# Plan x

## Acceptance Criteria

- [ ] {CRITERION_1}
- [ ] {CRITERION_2}

## Pre-PR Quality Gate

- `{RUN_COMMAND}`

## Build Progress

- [x] Slice 1: add feature

**Files:** `{SOURCE_FILE}`
"""
BINDING_HASH = "b" * 64
INPUTS_DIGEST = "d" * 64


def git_env(home: Path) -> dict[str, str]:
    """Hermetic git environment that also stops repository discovery at `home`."""
    env = hermetic_git_env(home)
    env["GIT_CEILING_DIRECTORIES"] = str(home.parent)
    return env


def git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        env=git_env(root.parent),
    )


def commit_file(root: Path, rel: str, content: str, message: str) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    git(root, "add", rel)
    git(root, "commit", "-q", "-m", message)


def init_repo(root: Path, branch: str = "main") -> None:
    """An empty repository at `root` with `branch` checked out."""
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", branch)
    git(root, "config", "init.defaultBranch", "main")
    git(root, "config", "user.name", "tester")
    git(root, "config", "user.email", "t@t.dev")


def make_repo(tmp_path: Path, *, with_source: bool = True) -> Path:
    """Repository root with `main` as base and `work` (checked out) one ahead.

    `work` adds the plan and, unless `with_source` is false, a source file,
    so a plan-only branch (an empty binding diff) is one argument away.
    """
    root = tmp_path / "repo"
    init_repo(root, "main")
    commit_file(root, ".gitignore", RECORD_IGNORE + "\n", "chore: base")
    git(root, "checkout", "-q", "-b", "work")
    (root / PLAN_ID).parent.mkdir(parents=True, exist_ok=True)
    (root / PLAN_ID).write_text(PLAN_TEXT, encoding="utf-8")
    git(root, "add", PLAN_ID)
    if with_source:
        commit_file(root, SOURCE_FILE, "feature\n", "feat: add feature")
    else:
        git(root, "commit", "-q", "-m", "docs: add plan")
    return root


def row(
    criterion: object = "AC1",
    verdict: str = "met",
    command: str = RUN_COMMAND,
    observation: str = "ok",
) -> dict:
    """One criterion row; `criterion` is deliberately untyped so tests can break it."""
    return {
        "criterion": criterion,
        "verdict": verdict,
        "command": command,
        "observation": observation,
    }


def record(
    rows: list[dict] | None = None,
    findings: list[dict] | None = None,
    **overrides: object,
) -> dict:
    """A full examination record; keyword overrides replace any field."""
    base = {
        "plan": PLAN_ID,
        "agent_id": "agent-7",
        "overall": "met",
        "criteria": [row("AC1"), row("AC2")] if rows is None else rows,
        "problems": [],
        "audit_findings": findings or [],
        "binding_hash": BINDING_HASH,
        "inputs_digest": INPUTS_DIGEST,
        "recorded_at": "2026-11-03T10:00:00+00:00",
    }
    base.update(overrides)
    return base
