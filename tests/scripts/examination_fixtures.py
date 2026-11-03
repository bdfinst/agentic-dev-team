"""Shared builders for acceptance-examination tests (#2270).

`make_repo` builds a pinned temp git repository: `main` with one commit and
`work` one commit ahead, holding `plans/x.md` and a source file.
`write_met_record` writes a record bound to the repository's real branch
binding and the plan's real inputs digest, so it counts as current.

Callers that run git in-process (not through a subprocess given `git_env`)
must pin their own environment; `git_env` returns the isolated one.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

_PLUGIN = Path(__file__).resolve().parents[2] / "plugins" / "dev-team"
for _entry in (_PLUGIN / "hooks" / "lib", _PLUGIN / "scripts" / "lib"):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

import examination_store as store  # type: ignore[import-not-found]
from examination_inputs import (  # type: ignore[import-not-found]
    criteria_ids,
    plan_examination_inputs,
)
from examination_verdict import (
    build_record,  # type: ignore[import-not-found]
)

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
_GIT_VARS_DROPPED = (
    "GIT_DIR",
    "GIT_INDEX_FILE",
    "GIT_WORK_TREE",
    "GIT_PREFIX",
    "GIT_REFLOG_ACTION",
)


def git_env(home: Path) -> dict[str, str]:
    """Environment with no inherited repo redirection and no user git config."""
    env = {k: v for k, v in os.environ.items() if k not in _GIT_VARS_DROPPED}
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    env["GIT_CEILING_DIRECTORIES"] = str(home.parent)
    env["HOME"] = str(home)
    return env


def _git(root: Path, home: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        env=git_env(home),
    )


def _commit_file(root: Path, home: Path, rel: str, content: str, message: str) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    _git(root, home, "add", rel)
    _git(root, home, "commit", "-q", "-m", message)


def make_repo(tmp_path: Path) -> Path:
    """Repository root with `main` as base and `work` (checked out) one ahead."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, tmp_path, "init", "-q", "-b", "main")
    _git(root, tmp_path, "config", "init.defaultBranch", "main")
    _git(root, tmp_path, "config", "user.name", "tester")
    _git(root, tmp_path, "config", "user.email", "t@t.dev")
    _commit_file(root, tmp_path, ".gitignore", RECORD_IGNORE + "\n", "chore: base")
    _git(root, tmp_path, "checkout", "-q", "-b", "work")
    (root / PLAN_ID).parent.mkdir(parents=True, exist_ok=True)
    (root / PLAN_ID).write_text(PLAN_TEXT, encoding="utf-8")
    _git(root, tmp_path, "add", PLAN_ID)
    _commit_file(root, tmp_path, SOURCE_FILE, "feature\n", "feat: add feature")
    return root


def _met_rows(plan_text: str) -> list[dict]:
    return [
        {
            "criterion": cid,
            "verdict": "met",
            "command": RUN_COMMAND,
            "observation": f"{cid} passed",
        }
        for cid in criteria_ids(plan_examination_inputs(plan_text))
    ]


def write_met_record(
    root: Path, plan_id: str = PLAN_ID, overall: str = "met", **overrides: object
) -> Path:
    """Write a record bound to the real binding and inputs digest; return its path.

    `overall` and any keyword override replace the matching record field.
    The binding is whatever `current_binding` reports now, so a repository
    with no base or no diff gets a sentinel `binding_hash`, which the store
    refuses to read back (an unreadable record).
    """
    plan_text = (root / plan_id).read_text(encoding="utf-8")
    record = build_record(
        plan_id,
        _met_rows(plan_text),
        [],
        [],
        store.binding_for_plan(root, plan_id, plan_text),
        "agent-1",
    )
    record["overall"] = overall
    record.update(overrides)
    path = store.record_path(root, plan_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    store.write_record(path, record)
    return path


EXEMPT_HEADER = "**Examination**: not-applicable\n\n"


def _exclude_records(root: Path) -> None:
    """Keep the record out of `git status` without touching tracked files."""
    exclude = root / ".git" / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    with exclude.open("a", encoding="utf-8") as handle:
        handle.write(RECORD_IGNORE + "\n")


def give_current_met_record(plan: Path) -> None:
    """Make `plan` pass the examination gate in an ad-hoc test repository.

    Writes a current `met` record when the repository has a real binding (a
    resolvable base and a non-empty branch diff). Otherwise no record can be
    current, so the plan declares the documented `not-applicable` exemption.
    """
    with mock.patch.dict(os.environ, git_env(plan.parent), clear=True):
        root = store.repo_root(plan)
        plan_id = store.canonical_plan_id(plan, root)
        if store.is_binding_hash(store.current_binding(root, plan_id)):
            _exclude_records(root)
            write_met_record(root, plan_id)
            return
    plan.write_text(EXEMPT_HEADER + plan.read_text(encoding="utf-8"), encoding="utf-8")
