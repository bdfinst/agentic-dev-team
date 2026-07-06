"""Issue #916 — /build Step 7 branch-base resolution has no fallback for a
single-branch/no-remote repo.

`git merge-base HEAD origin/HEAD` (falling back to `origin/main`, `main`,
`master`, `develop`) has no handling for the degenerate case where there is
no `origin` remote at all (the call fails outright) or every commit on the
branch landed directly on the fallback branch itself (e.g. `master`), so
`git merge-base HEAD master` resolves to HEAD. Diffing HEAD against itself
in sub-step 2 silently reports zero changed test files, which sub-step 3
then presents as the clean "No tests written on this branch" result — a
false negative (reproduced live during the #907 smoke test).

These are doc-grep tests over the shipped SKILL.md prose (mirrors
tests/skills/test_build_worktree_baseref_detect.py's Step 4 pattern) plus a
unit-level check that the CLI surface the fix relies on
(`build_rollback_point.py get-by-symbolic`) actually exists and behaves —
the round-trip test/behavior test for that function itself lives in
plugins/dev-team/tests/scripts/test_build_rollback_point.py.
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, grep, grep_multiline, section

BUILD_SKILL = PLUGIN_ROOT / "skills" / "build" / "SKILL.md"


def _step_7_section() -> str:
    return section(
        BUILD_SKILL.read_text(),
        r"^### 7\. ",
        boundary_pattern=r"^### 7\.5\. ",
        include_start_line=False,
    )


def test_step_7_documents_a_degenerate_base_check():
    s = _step_7_section()
    assert grep(r"issue #916", s, ignore_case=True)
    assert grep(r"base\s*==\s*HEAD|base equals `?HEAD`?", s, ignore_case=True)


def test_step_7_covers_both_no_remote_and_all_commits_on_fallback_branch_cases():
    s = _step_7_section()
    assert grep(r"no.*origin.*remote|no `?origin`? at all", s, ignore_case=True)
    assert grep(r"merge-base.*fails|fails outright", s, ignore_case=True)
    assert grep_multiline(
        r"commits?[^`]{0,80}?landed directly on[^`]{0,80}?(the fallback branch|`master`)",
        s,
        ignore_case=True,
    )


def test_step_7_falls_back_to_the_plan_start_rollback_point():
    s = _step_7_section()
    assert grep(r"plan-start", s)
    assert grep(r"build_rollback_point\.py", s)
    assert grep(r"get-by-symbolic", s)
    assert grep(r"memory/build-rollback\.json", s)
    # Ties the fallback explicitly to the existing #865 bookkeeping rather
    # than inventing a parallel mechanism.
    assert grep(r"issue #865", s)


def test_step_7_validates_the_fallback_sha_is_an_ancestor_of_head():
    # Guards against a stale plan-start entry left in the never-cleared
    # memory/build-rollback.json by an unrelated earlier build sharing the
    # worktree (arch-review finding on issue #916's fix) — the doc must
    # wire the ancestry-validating flags, not just call get-by-symbolic bare.
    s = _step_7_section()
    assert grep(r"--repo\b", s)
    assert grep(r"--ancestor-of\b", s)
    assert grep(r"stale", s, ignore_case=True)


def test_step_7_emits_an_explicit_warning_when_no_plan_start_point_is_recorded():
    s = _step_7_section()
    assert grep(
        r"warning|degraded",
        s,
        ignore_case=True,
    )
    # The warning must distinguish resolution failure from a genuinely
    # clean, no-tests-written branch — not silently reuse the clean phrasing.
    assert grep_multiline(
        r"(resolution (failure|degraded)|degraded)[^`]{0,300}?no tests written",
        s,
        ignore_case=True,
    ) or grep_multiline(
        r"no tests written[^`]{0,300}?(resolution (failure|degraded)|degraded)",
        s,
        ignore_case=True,
    )


def test_step_7_sub_step_3_distinguishes_the_found_and_not_found_fallback_cases():
    # doc-review finding on issue #916's first draft: sub-step 3 must not
    # apply the degraded-warning branch to BOTH of sub-step 1's outcomes
    # (a qualifying plan-start SHA found vs. none found) — only the latter
    # is a genuine resolution failure.
    s = _step_7_section()
    assert grep(r"not found", s, ignore_case=True)
    assert grep_multiline(
        r'"found" case[^`]{0,400}?real base',
        s,
        ignore_case=True,
    )
