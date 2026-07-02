"""Tests for scripts/lib/ci-changed-only.sh — the suite -> watched-path
mapping and change-matching logic behind ci-local.sh's --changed-only flag.
The git interaction stays in ci-local.sh; the pure matching logic lives here
so it is unit-testable without a contrived git history. These tests pin the
match contract: directory prefixes, exact files, globs, unmapped
(always-run) suites, and multi-file changesets.

Ported from tests/scripts/ci_changed_only_tests.bats (issue #676). The
underlying scripts/lib/ci-changed-only.sh stays bash — only the test
harness moves to pytest, per issue #676's note that scripts/ci-local.sh and
its lib are out of scope for this port (closing issue #677 handles that).
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
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
    r = _run_fn("ci_suite_has_changes", "chk_bats_repo", "tests/repo/foo_tests.bats")
    assert r.returncode == 0


def test_dir_prefix_path_a_change_outside_every_watched_dir_is_skipped() -> None:
    r = _run_fn("ci_suite_has_changes", "chk_bats_repo", "scripts/eval_grade.py")
    assert r.returncode == 1


def test_dir_prefix_path_any_one_of_several_watched_dirs_matching_runs_it() -> None:
    r = _run_fn(
        "ci_suite_has_changes", "chk_bats_content_rest", "tests/docs/some_doc_test.bats"
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
    r1 = _run_fn("ci_watched_paths", "chk_bats_repo")
    assert "tests/repo/" in r1.stdout

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
        "README.md plugins/dev-team/hooks/agent_model_resolve.py",
    )
    assert r.returncode == 0


def test_multi_file_changeset_no_matching_file_skips() -> None:
    r = _run_fn("ci_suite_has_changes", "chk_model_routing", "README.md docs/notes.md")
    assert r.returncode == 1


# --- empty changeset ---------------------------------------------------------


def test_empty_changeset_skips_a_mapped_suite() -> None:
    r = _run_fn("ci_suite_has_changes", "chk_bats_repo", "")
    assert r.returncode == 1
