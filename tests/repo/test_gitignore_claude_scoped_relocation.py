"""Plan Slice 6, Step 6.2: `.gitignore`'s `memory/`, `metrics/`, and `plans/`
rules relocate to match the `.claude/-scoped artifact migration (#1406).

The reports-domain consolidation (`.dev-team-reports/`) was already handled by
Slice 9's Step 9.7 — see `test_dev_team_reports_gitignore_consolidation.py` for
that coverage; this file covers only the memory/metrics/plans domains Step
6.2 was left to close, plus the two review-flagged gaps: `.claude/memory/
build-phase.json` and `.claude/memory/test-improve/` were previously
uncovered by any rule (AC11).

These assertions run `git check-ignore` against the repo's real `.gitignore`
so they verify the shipped rule, not a copy. `git check-ignore` matches on
the path string and does not require the file to exist on disk, but note it
also consults the git index: an already-tracked path is reported as
NOT ignored regardless of any matching pattern (this is why decisions.md's
test below is a true behavioral assertion, not just a pattern check — it
stays tracked because `git mv` kept it in the index, matching the deny-by-
absence mechanism the legacy memory/ block already used).
"""

from __future__ import annotations

import os
import subprocess

from _repo_root import REPO_ROOT

# Hermetic: ignore any host-level git ignore/config so the result reflects the
# repo's own .gitignore only (see the "Hermetic local tests" convention).
_ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}


def _is_ignored(relpath: str) -> bool:
    """True when git would ignore `relpath` (relative to the repo root)."""
    result = subprocess.run(
        ["git", "check-ignore", "-q", "--", relpath],
        cwd=REPO_ROOT,
        env=_ENV,
        check=False,
    )
    # exit 0 = ignored, 1 = not ignored, 128 = error.
    assert result.returncode in (0, 1), f"git check-ignore errored on {relpath}"
    return result.returncode == 0


def test_claude_memory_narrow_exceptions_relocated():
    assert _is_ignored(".claude/memory/recon-example.md")


def test_claude_memory_decisions_md_stays_tracked():
    # decisions.md was `git mv`-ed into .claude/memory/ (Step 6.1) and stays
    # in the index, so it is not ignored regardless of the `.claude/memory/
    # *.md` conversation-summaries rule matching its name.
    assert not _is_ignored(".claude/memory/decisions.md")


def test_claude_memory_build_phase_json_gap_closed():
    # AC11 gap: previously uncovered by any rule.
    assert _is_ignored(".claude/memory/build-phase.json")


def test_claude_memory_test_improve_nested_gap_closed():
    # AC11 gap: the legacy `.claude/memory/*.md` rule only matches direct
    # children, not nested dirs — previously uncovered.
    assert _is_ignored(".claude/memory/test-improve/some-slug/phase-0.md")
    assert _is_ignored(".claude/memory/test-improve/some-slug/refactor-backlog.md")


def test_security_assessment_memory_patterns_unaffected():
    # Sibling deny-prefix rules under bare memory/ belong to a different
    # plugin (security-assessment) with no Python writer touched by this
    # migration — must remain ignored at their original bare path.
    assert _is_ignored("memory/recon-something.md")
    assert _is_ignored("memory/audit-something.md")


def test_claude_metrics_ignored_by_default():
    assert _is_ignored(".claude/metrics/some-run.jsonl")


def test_claude_metrics_tracked_exceptions_relocated():
    assert not _is_ignored(".claude/metrics/config-changelog.jsonl")
    assert not _is_ignored(".claude/metrics/eval-variance.jsonl")


def test_bare_verify_log_stays_ignored_unrelocated():
    assert _is_ignored("metrics/verify-log.jsonl")


def test_claude_plans_ignored():
    assert _is_ignored(".claude/plans/test-improve/foo.md")


def test_bare_plans_still_ignored_as_safety_net():
    assert _is_ignored("plans/foo.md")
