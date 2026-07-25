"""Slice 9, Step 9.7 (= Slice 6, Step 6.2): `.gitignore`'s reports-domain block
consolidates `DEV_TEAM_REPORTS/` and `reports/` into one new top-level
`.dev-team-reports/` catch-all, carrying the union of both legacy blocks'
tracked exceptions. Both legacy blocks (bare `/reports/*` and the standalone
`DEV_TEAM_REPORTS/` line) stay completely unchanged as a safety net for
un-migrated content (AC19, plan Slice 9 Step 9.7).

These assertions run `git check-ignore` against the repo's real `.gitignore`
so they verify the shipped rule, not a copy. `git check-ignore` matches on the
path string and does not require the file to exist on disk.
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


def test_adhoc_dev_team_reports_output_is_ignored():
    assert _is_ignored(".dev-team-reports/code-review.md")
    assert _is_ignored(".dev-team-reports/triage/some-slug.md")
    assert _is_ignored(".dev-team-reports/review-agent-output.md")


def test_dev_team_reports_tracked_exceptions_are_unignored():
    assert not _is_ignored(".dev-team-reports/test-improve/some-repo/baseline.json")
    assert not _is_ignored(".dev-team-reports/orchestration-benchmark-2026-07-18.md")
    assert not _is_ignored(
        ".dev-team-reports/orchestration-benchmark-2026-07-18-data/raw.json"
    )
    assert not _is_ignored(".dev-team-reports/harness-audit-2026-07-20.md")


def test_legacy_dev_team_reports_root_stays_ignored_unchanged():
    assert _is_ignored("DEV_TEAM_REPORTS/code-review.md")
    assert _is_ignored("DEV_TEAM_REPORTS/triage/some-slug.md")


def test_legacy_reports_root_stays_unchanged():
    """#1412 (Slice 1, Step 1.4) removes the one now-confirmed-dead exception
    in this block — `!/reports/test-improve/` — since /test-improve no
    longer writes to that bare path (superseded by
    `.dev-team-reports/test-improve/`, see above); the other two tracked
    exceptions in this legacy block are untouched."""
    assert _is_ignored("reports/competitive-analysis.md")
    assert _is_ignored("reports/test-improve/some.md")
    assert not _is_ignored("reports/orchestration-benchmark-2026-07-18.md")
    assert not _is_ignored("reports/harness-audit-2026-07-20.md")
