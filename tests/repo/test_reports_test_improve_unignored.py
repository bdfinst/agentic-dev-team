"""#1126 introduced a `reports/test-improve/` un-ignore rule so an opt-in
`/test-improve` baseline-metrics report could land in the run's PR. #1412
removes that opt-in entirely and its baseline data (Slice 1): every run now
writes unconditionally under the git-tracked `.dev-team-reports/test-improve/`
domain instead (see `test_dev_team_reports_gitignore_consolidation.py`), so
the bare `reports/test-improve/` rule is dead — nothing writes there anymore
— and this file now pins that it correctly falls back to the ad-hoc
`reports/` ignore-by-default, alongside the parity-fixture reports path
(see #574 / #572), which stays tracked.

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


def test_bare_reports_test_improve_is_no_longer_tracked():
    """#1412: the `!/reports/test-improve/` exception is removed — nothing
    writes to the bare (non-`.dev-team-reports/`-prefixed) path anymore, so
    it now falls back to the ad-hoc `/reports/*` deny-all like any other
    untracked reports/ content."""
    assert _is_ignored("reports/test-improve/some-repo-2026-01-01.md")
    assert _is_ignored("reports/test-improve/baseline-coverage.json")


def test_adhoc_reports_output_stays_ignored():
    assert _is_ignored("reports/competitive-analysis.md")
    assert _is_ignored("reports/some-other-run/output.json")


def test_parity_fixture_reports_stay_tracked():
    assert not _is_ignored(
        "plugins/dev-team/tests/hooks/parity/fixtures/case1/reports/expected.json"
    )
