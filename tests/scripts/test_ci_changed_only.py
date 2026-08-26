"""Tests for scripts/lib/ci-changed-only.sh — the suite -> watched-path
mapping and change-matching logic behind ci-local.sh's --changed-only flag.
The git interaction stays in ci-local.sh; the pure matching logic lives here
so it is unit-testable without a contrived git history. These tests pin the
match contract: directory prefixes, exact files, globs, unmapped
(always-run) suites, and multi-file changesets.

Ported from tests/scripts/ci_changed_only_tests.bats (issue #676). The
underlying scripts/lib/ci-changed-only.sh stays bash — only the test
harness moves to pytest, per issue #676's note that scripts/ci-local.sh and
its lib are out of scope for this port. Issue #677 retired the
chk_bats_repo/chk_bats_content_rest mapping entries these tests used to
exercise (folded into chk_hook_units) — the example suite names below were
swapped for still-mapped suites; the matcher contract under test is
unchanged.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from _repo_root import REPO_ROOT

LIB = REPO_ROOT / "scripts" / "lib" / "ci-changed-only.sh"


def _run_fn(
    fn: str, *args: str, cwd: Path | None = None
) -> subprocess.CompletedProcess:
    quoted_args = " ".join(f'"{a}"' for a in args)
    script = f'set -e; . "{LIB}"; {fn} {quoted_args}'
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(cwd) if cwd else None,
    )


def test_lib_sources_cleanly_and_exposes_the_matcher() -> None:
    result = subprocess.run(
        ["bash", "-c", f'. "{LIB}"; type ci_suite_has_changes; type ci_watched_paths'],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


# --- directory-prefix watched paths ---------------------------------------


def test_dir_prefix_path_a_change_under_the_directory_runs_the_suite() -> None:
    r = _run_fn(
        "ci_suite_has_changes",
        "chk_shellcheck_helpers",
        "plugins/security-assessment/scripts/foo.sh",
    )
    assert r.returncode == 0


def test_dir_prefix_path_a_change_outside_every_watched_dir_is_skipped() -> None:
    r = _run_fn(
        "ci_suite_has_changes", "chk_shellcheck_helpers", "scripts/eval_grade.py"
    )
    assert r.returncode == 1


def test_dir_prefix_path_any_one_of_several_watched_dirs_matching_runs_it() -> None:
    r = _run_fn(
        "ci_suite_has_changes",
        "chk_sa_shell_suite",
        "tests/security-assessment/run-all.sh",
    )
    assert r.returncode == 0


# --- exact-file watched paths ----------------------------------------------


def test_exact_file_path_the_named_file_matches() -> None:
    r = _run_fn(
        "ci_suite_has_changes",
        "chk_cost_regression",
        "scripts/cost-regression-check.sh",
    )
    assert r.returncode == 0


def test_exact_file_path_a_different_file_in_the_same_dir_does_not_match() -> None:
    r = _run_fn(
        "ci_suite_has_changes", "chk_cost_regression", "scripts/other-script.sh"
    )
    assert r.returncode == 1


# --- glob watched paths -----------------------------------------------------


def test_glob_path_a_js_file_anywhere_matches_the_eslint_suite() -> None:
    r = _run_fn("ci_suite_has_changes", "chk_eslint", "some/nested/dir/app.js")
    assert r.returncode == 0


def test_glob_path_a_ts_file_matches_the_eslint_suite() -> None:
    r = _run_fn("ci_suite_has_changes", "chk_eslint", "pkg/index.ts")
    assert r.returncode == 0


def test_glob_path_a_file_outside_every_watched_path_is_skipped() -> None:
    r = _run_fn("ci_suite_has_changes", "chk_eslint", "README.md")
    assert r.returncode == 1


def test_glob_path_the_eslint_dir_prefix_arm_matches_a_non_js_file_under_it() -> None:
    r = _run_fn(
        "ci_suite_has_changes", "chk_eslint", "plugins/dev-team/skills/foo/SKILL.md"
    )
    assert r.returncode == 0


def test_glob_path_the_json_arm_matches_a_manifest_change() -> None:
    r = _run_fn(
        "ci_suite_has_changes",
        "chk_eslint",
        "plugins/dev-team/.claude-plugin/plugin.json",
    )
    assert r.returncode == 0


def test_glob_match_is_filesystem_independent_noglob_guard() -> None:
    """Proves the set -f (noglob) guard is load-bearing: with real *.js files
    present in the working directory, an unquoted '*.js' watched entry would
    otherwise expand against the filesystem and stop matching the changed
    path. The matcher must still match 'app.js' (which does NOT exist on
    disk) via the glob."""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "decoy.js").touch()
        r = _run_fn("ci_suite_has_changes", "chk_eslint", "app.js", cwd=Path(d))
    assert r.returncode == 0


# --- unmapped suites always run (conservative fallback) --------------------


def test_unmapped_suite_always_runs_never_silently_skipped() -> None:
    r = _run_fn("ci_suite_has_changes", "chk_oe_staleness", "anything.txt")
    assert r.returncode == 0


def test_unmapped_suite_runs_even_with_an_empty_changeset() -> None:
    r = _run_fn("ci_suite_has_changes", "chk_oe_staleness", "")
    assert r.returncode == 0


def test_ci_watched_paths_pins_representative_suite_mappings() -> None:
    r1 = _run_fn("ci_watched_paths", "chk_shellcheck_helpers")
    assert "plugins/security-assessment/scripts/" in r1.stdout

    r2 = _run_fn("ci_watched_paths", "chk_cost_regression")
    assert "scripts/cost-regression-check.sh" in r2.stdout

    r3 = _run_fn("ci_watched_paths", "chk_eslint")
    assert "*.js" in r3.stdout

    r4 = _run_fn("ci_watched_paths", "chk_oe_staleness")
    assert r4.stdout == ""


# --- multi-file changesets ---------------------------------------------------


def test_multi_file_changeset_one_matching_file_is_enough_to_run() -> None:
    r = _run_fn(
        "ci_suite_has_changes",
        "chk_model_routing",
        "README.md plugins/dev-team/hooks/context_ceiling_guard.py",
    )
    assert r.returncode == 0


def test_multi_file_changeset_no_matching_file_skips() -> None:
    r = _run_fn("ci_suite_has_changes", "chk_model_routing", "README.md docs/notes.md")
    assert r.returncode == 1


# --- empty changeset ---------------------------------------------------------


def test_empty_changeset_skips_a_mapped_suite() -> None:
    r = _run_fn("ci_suite_has_changes", "chk_shellcheck_helpers", "")
    assert r.returncode == 1


# ===========================================================================
# #2003 — the inert-path lever. A SECOND, independent skip mechanism with the
# opposite quantifier to ci_suite_has_changes: skip only when EVERY changed
# file is provably inert, so a forgotten path costs a wasted run rather than
# a silent false skip.
# ===========================================================================
CHK_HOOK_UNITS_DIRS = (
    "plugins/dev-team/tests",
    "tests/repo",
    "tests/agents",
    "tests/commands",
    "tests/docs",
    "tests/knowledge",
    "tests/stack_aware",
    "tests/skills",
    "tests/scripts",
    "tests/hooks",
)


def _is_all_inert(fn: str, changed: str) -> bool:
    return _run_fn("ci_suite_is_all_inert", fn, changed).returncode == 0


def test_a_purely_inert_diff_skips_the_long_pole_suite():
    """#2003 AC: LICENSE / .gitignore-only diffs skip chk_hook_units."""
    assert _is_all_inert("chk_hook_units", "LICENSE")
    assert _is_all_inert("chk_hook_units", ".gitattributes")
    assert _is_all_inert("chk_hook_units", "LICENSE .gitattributes")


def test_a_docs_adr_diff_still_runs_the_suite():
    """#2003 AC, and the correction the issue makes to its own original
    framing: tests/repo/test_adr_readme_toc_complete.py exists because ADRs
    0013/0014/0015 landed without README entries (#732). Making docs/adr/
    inert would let exactly that recur, silently and CI-only."""
    assert not _is_all_inert("chk_hook_units", "docs/adr/0039-something.md")
    assert not _is_all_inert("chk_hook_units", "docs/adr/README.md")


def test_markdown_and_docs_are_not_inert():
    """Blanket docs/** and *.md are out for the same reason as docs/adr/**."""
    assert not _is_all_inert("chk_hook_units", "README.md")
    assert not _is_all_inert("chk_hook_units", "docs/cloud-setup.md")


def test_a_mixed_diff_runs_the_suite():
    """#2003 AC: the universal quantifier pinned in both directions — one
    live file among inert ones is enough to run."""
    assert not _is_all_inert("chk_hook_units", "LICENSE plugins/dev-team/hooks/x.py")
    assert not _is_all_inert("chk_hook_units", "plugins/dev-team/hooks/x.py LICENSE")


def test_an_unmapped_check_is_never_skipped_by_this_lever():
    """#2003 AC: mirrors the existing safe default — unmapped means run."""
    assert not _is_all_inert("chk_ruff", "LICENSE")
    assert not _is_all_inert("chk_some_future_check", "LICENSE")
    assert _run_fn("ci_inert_paths", "chk_ruff").stdout == ""


def test_an_empty_changed_set_is_never_skipped_by_this_lever():
    """Preserves today's behavior: ci-local.sh already disables --changed-only
    on an empty diff, and this lever must not invent a skip there either."""
    assert not _is_all_inert("chk_hook_units", "")


def test_the_two_levers_are_independent():
    """#2003 item 4: ci_watched_paths / ci_suite_has_changes are untouched.
    chk_hook_units still has no watched-path mapping, so the existential lever
    still always runs it — the inert lever is additive, not a replacement."""
    assert _run_fn("ci_watched_paths", "chk_hook_units").stdout == ""
    assert _run_fn("ci_suite_has_changes", "chk_hook_units", "LICENSE").returncode == 0


#: A mention of a filename is not an observation of it — `"LICENSE"` sitting in
#: a list of example filenames (tests/scripts/test_select_lenses.py) cannot
#: change its verdict when the real LICENSE is edited. What makes a path
#: observable is the suite READING it, so the discriminator is the path
#: appearing on a line that also performs filesystem access.
_FILESYSTEM_READ_IDIOMS = r"REPO_ROOT|read_text|open\(|Path\(|\.exists\(|is_file"


def _lines_reading(path: str, dirs: list[str]) -> list[str]:
    """Lines under `dirs` that name `path` AND touch the filesystem."""
    grep = subprocess.run(
        ["grep", "-rn", "--include=*.py", "-F", path, *dirs],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(REPO_ROOT),
    )
    if grep.returncode != 0:
        return []
    filtered = subprocess.run(
        ["grep", "-E", _FILESYSTEM_READ_IDIOMS],
        input=grep.stdout,
        capture_output=True,
        text=True,
        check=False,
    )
    return [line for line in filtered.stdout.splitlines() if line.strip()]


def test_every_inert_path_is_genuinely_unread_by_the_suite():
    """#2003 AC: the inert set cannot loosen unnoticed.

    Sweeps the ENTIRE chk_hook_units directory list for each inert path used
    as a filesystem target. If a test ever starts reading one, this fails and
    the path must leave the set.

    This guard already earned its keep: #2003 proposed seeding the set with
    `.gitignore`, and this test caught that the suite reads the root
    .gitignore in three places. A false skip there would have been silent and
    CI-only — exactly the failure mode the inert lever exists to avoid.
    """
    inert = _run_fn("ci_inert_paths", "chk_hook_units").stdout.split()
    assert inert, "chk_hook_units lost its inert set entirely"

    existing_dirs = [d for d in CHK_HOOK_UNITS_DIRS if (REPO_ROOT / d).is_dir()]
    assert existing_dirs, "none of the chk_hook_units directories exist"

    offenders = {
        path: lines
        for path in inert
        if (lines := _lines_reading(path, existing_dirs))
    }
    assert not offenders, (
        "these paths are in chk_hook_units's inert set but ARE read by tests "
        f"the suite runs, so the suite can observe them: {offenders}"
    )


def test_every_inert_path_actually_exists_in_the_repo():
    """An inert entry for a file this repo does not have is dead weight — the
    lever can never fire on it, so it only makes the set look broader than it
    is. (#2003's seed named .editorconfig and CODEOWNERS, neither present.)"""
    inert = _run_fn("ci_inert_paths", "chk_hook_units").stdout.split()
    missing = [p for p in inert if not (REPO_ROOT / p).exists()]
    assert not missing, f"inert paths that do not exist in this repo: {missing}"


def test_gitignore_is_not_inert_because_the_suite_reads_it():
    """Pinned as its own named case, not just an absence: #2003 proposed
    `.gitignore` and it is genuinely observed."""
    inert = _run_fn("ci_inert_paths", "chk_hook_units").stdout.split()
    assert ".gitignore" not in inert
    assert not _is_all_inert("chk_hook_units", ".gitignore")

    existing_dirs = [d for d in CHK_HOOK_UNITS_DIRS if (REPO_ROOT / d).is_dir()]
    assert _lines_reading(".gitignore", existing_dirs), (
        "the suite no longer reads .gitignore — if that is real, this test and "
        "the inert set can both be revisited"
    )


def test_inert_matcher_honours_the_directory_prefix_shape():
    """Entry shapes must not drift from ci_suite_has_changes's."""
    assert _run_fn("ci_path_is_inert", "vendor/x/y.py", "vendor/").returncode == 0
    assert _run_fn("ci_path_is_inert", "src/x.py", "vendor/").returncode != 0


def test_inert_matcher_honours_the_glob_shape():
    assert _run_fn("ci_path_is_inert", "a.lock", "*.lock").returncode == 0
    assert _run_fn("ci_path_is_inert", "a.py", "*.lock").returncode != 0


def test_inert_matcher_honours_the_exact_file_shape():
    assert _run_fn("ci_path_is_inert", "LICENSE", "LICENSE").returncode == 0
    assert _run_fn("ci_path_is_inert", "LICENSE.md", "LICENSE").returncode != 0
