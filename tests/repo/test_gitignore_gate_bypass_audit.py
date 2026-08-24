"""Slice 1 (#1945, following up #1831): `.claude/metrics/gate-bypass-audit.jsonl`
must survive worktree removal like its siblings `config-changelog.jsonl` /
`eval-variance.jsonl` already do, instead of falling under the
`**/metrics/*` catch-all with no exception line.

Scenario (a) runs `git check-ignore` against an isolated tmp_path git repo
seeded with a copy of the shipped `.gitignore` — mirroring the scratch-repo
pattern in tests/repo/test_pre_push_ref_guard.py — rather than the real repo
directly, so the assertion is about the *rule shape* and is unaffected by
anything else present in this checkout.

Scenario (b) reads the real `.gitignore` and pins the rationale comment
required by AC2 (an otherwise-untestable prose requirement): the comment
block immediately preceding the new exception line must name
`pre_pr_review.py` and `review_gate_corroboration` as the mechanism that
already satisfies "a delegated subagent can be PR-gated without a bypass,
without self-writing the gate file" — so a future edit that drops the
rationale without touching the ignore rule itself still fails this test.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

GITIGNORE = REPO_ROOT / ".gitignore"
EXCEPTION_LINE = "!**/metrics/gate-bypass-audit.jsonl"


@pytest.fixture
def scratch_repo(tmp_path: Path, hermetic_env: dict[str, str]) -> Path:
    """An isolated git repo seeded with a copy of the shipped .gitignore."""
    subprocess.run(
        ["git", "init", "-q", "-b", "main"],
        cwd=str(tmp_path),
        env=hermetic_env,
        check=True,
    )
    (tmp_path / ".gitignore").write_text(GITIGNORE.read_text())
    return tmp_path


def _is_ignored(root: Path, env: dict[str, str], relpath: str) -> bool:
    """True when git would ignore `relpath` relative to `root`."""
    result = subprocess.run(
        ["git", "check-ignore", "-q", "--", relpath],
        cwd=str(root),
        env=env,
        check=False,
    )
    assert result.returncode in (0, 1), (
        f"git check-ignore errored on {relpath}: "
        f"exit={result.returncode}"
    )
    return result.returncode == 0


def test_gate_bypass_audit_file_is_not_ignored(
    scratch_repo: Path, hermetic_env: dict[str, str]
) -> None:
    assert not _is_ignored(
        scratch_repo, hermetic_env, ".claude/metrics/gate-bypass-audit.jsonl"
    )


def test_catch_all_still_denies_other_runtime_metrics(
    scratch_repo: Path, hermetic_env: dict[str, str]
) -> None:
    assert _is_ignored(
        scratch_repo, hermetic_env, ".claude/metrics/some-other-runtime-metric.jsonl"
    )


def _rationale_comment_block() -> str:
    """The contiguous `#`-prefixed comment lines immediately preceding the
    new `!**/metrics/gate-bypass-audit.jsonl` exception line."""
    lines = GITIGNORE.read_text().splitlines()
    exception_index = lines.index(EXCEPTION_LINE)

    comment_lines: list[str] = []
    i = exception_index - 1
    while i >= 0 and lines[i].lstrip().startswith("#"):
        comment_lines.append(lines[i])
        i -= 1
    comment_lines.reverse()

    assert comment_lines, (
        f"expected a comment block immediately preceding {EXCEPTION_LINE!r} "
        "in .gitignore, found none"
    )
    return "\n".join(comment_lines)


def test_rationale_comment_names_the_corroboration_mechanism() -> None:
    block = _rationale_comment_block()
    assert "pre_pr_review.py" in block
    assert "review_gate_corroboration" in block


def test_rationale_comment_states_bypass_and_self_writing() -> None:
    block = _rationale_comment_block().lower()
    assert "bypass" in block
    assert "self-writing" in block
