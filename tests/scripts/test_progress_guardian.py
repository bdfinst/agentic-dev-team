"""Slice 3 — scripts/progress_guardian.py
Covers checkbox parsing, git-log cross-reference, uncommitted-change check,
pre-PR flag, and scope creep.

Ported from tests/scripts/progress_guardian_tests.bats (issue #676).
pytest's tmp_path fixture replaces the bash hermetic helper's mktemp -d +
rm -rf isolation (see tests/lib/hermetic.bash / issue #546) — every git
fixture below runs against its own tmp_path, never the parent worktree's
gitdir.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PG = REPO_ROOT / "scripts" / "progress_guardian.py"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _init_repo(cwd: Path) -> None:
    _git(cwd, "init", "-q")
    _git(cwd, "config", "user.email", "test@test.com")
    _git(cwd, "config", "user.name", "Test")


def make_plan(path: Path, content: str) -> None:
    path.write_text(content + "\n")


def run_pg(plan: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(PG), "--plan", str(plan), *args],
        capture_output=True,
        text=True,
        check=False,
    )


# ---------------------------------------------------------------------------
# Step 3.1 — Checkbox state parser
# ---------------------------------------------------------------------------


def test_3_1a_done_checkbox_is_parsed_as_done_true_with_header_captured(
    tmp_path: Path,
) -> None:
    plan = tmp_path / "plan.md"
    make_plan(plan, "- [x] Step 1.1: Do something")
    _init_repo(tmp_path)
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "initial commit")

    result = run_pg(plan, "--skip-llm")
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert any("Do something" in i["message"] for i in data["issues"]), data


def test_3_1b_undone_checkbox_is_parsed_as_done_false_no_error(tmp_path: Path) -> None:
    plan = tmp_path / "plan.md"
    make_plan(plan, "- [ ] Step 1.2: Another thing")
    _init_repo(tmp_path)
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "initial commit")

    result = run_pg(plan, "--skip-llm")
    assert result.returncode != 1


def test_3_1c_plan_file_with_no_checkboxes_exits_1_with_file_name_in_output(
    tmp_path: Path,
) -> None:
    plan = tmp_path / "plan.md"
    make_plan(plan, "# Plan\n\nSome text without any checkboxes.")
    _init_repo(tmp_path)
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "initial commit")

    result = run_pg(plan, "--skip-llm")
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert any(
        "plan.md" in i["message"] or "plan.md" in i["file"] for i in data["issues"]
    ), data


# ---------------------------------------------------------------------------
# Step 3.2 — Git-log cross-reference and uncommitted change check
# ---------------------------------------------------------------------------


def test_3_2a_done_step_with_matching_commit_exits_0_clean_tree(tmp_path: Path) -> None:
    plan = tmp_path / "plan.md"
    make_plan(plan, "- [x] Step 1.1: add checkbox parser")
    _init_repo(tmp_path)
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "feat: add checkbox parser")
    _git(tmp_path, "add", "plan.md")
    _git(tmp_path, "commit", "-q", "-m", "add plan")

    result = run_pg(plan, "--skip-llm")
    assert result.returncode == 0


def test_3_2b_done_step_with_no_matching_commit_exits_1_naming_the_step_header(
    tmp_path: Path,
) -> None:
    plan = tmp_path / "plan.md"
    make_plan(plan, "- [x] Step 1.1: Add something specific")
    _init_repo(tmp_path)
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "feat: something unrelated")

    result = run_pg(plan, "--skip-llm")
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert any("Add something specific" in i["message"] for i in data["issues"]), data


def test_3_2c_staged_file_with_a_done_step_exits_1_uncommitted_work(
    tmp_path: Path,
) -> None:
    plan = tmp_path / "plan.md"
    make_plan(plan, "- [x] Step 1.1: add checkbox parser")
    _init_repo(tmp_path)
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "feat: add checkbox parser")
    (tmp_path / "staged.txt").write_text("staged content\n")
    _git(tmp_path, "add", "staged.txt")

    result = run_pg(plan, "--skip-llm")
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert any("uncommit" in i["message"].lower() for i in data["issues"]), data


def test_3_2d_unstaged_modification_with_a_done_step_exits_1_uncommitted_work(
    tmp_path: Path,
) -> None:
    plan = tmp_path / "plan.md"
    _init_repo(tmp_path)
    (tmp_path / "tracked.txt").write_text("original\n")
    _git(tmp_path, "add", "tracked.txt")
    _git(tmp_path, "commit", "-q", "-m", "feat: add checkbox parser")
    (tmp_path / "tracked.txt").write_text("modified\n")

    make_plan(plan, "- [x] Step 1.1: add checkbox parser")

    result = run_pg(plan, "--skip-llm")
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert any("uncommit" in i["message"].lower() for i in data["issues"]), data


# ---------------------------------------------------------------------------
# Step 3.3 — Pre-PR flag, scope creep, and agent update
# ---------------------------------------------------------------------------


def test_3_3a_pre_pr_with_all_done_steps_matching_commits_clean_tree_exits_0(
    tmp_path: Path,
) -> None:
    plan = tmp_path / "plan.md"
    make_plan(
        plan,
        "- [x] Step 1.1: add checkbox parser\n- [x] Step 1.2: add git log check",
    )
    _init_repo(tmp_path)
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "feat: add checkbox parser")
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "feat: add git log check")

    result = run_pg(plan, "--pre-pr", "--skip-llm")
    assert result.returncode == 0


def test_3_3b_pre_pr_with_an_undone_step_exits_1(tmp_path: Path) -> None:
    plan = tmp_path / "plan.md"
    make_plan(
        plan,
        "- [x] Step 1.1: add checkbox parser\n- [ ] Step 1.2: add git log check",
    )
    _init_repo(tmp_path)
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "feat: add checkbox parser")

    result = run_pg(plan, "--pre-pr", "--skip-llm")
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert any(
        "incomplete" in i["message"].lower()
        or "unchecked" in i["message"].lower()
        or "not done" in i["message"].lower()
        for i in data["issues"]
    ), data


def test_3_3c_skip_llm_with_out_of_plan_staged_file_uncommitted_check_fires_first(
    tmp_path: Path,
) -> None:
    plan = tmp_path / "plan.md"
    # Plan declares no file paths; extra.py is out-of-plan
    make_plan(plan, "- [x] Step 1.1: add checkbox parser")
    _init_repo(tmp_path)
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "feat: add checkbox parser")
    (tmp_path / "extra.py").write_text("extra code\n")
    _git(tmp_path, "add", "extra.py")

    result = run_pg(plan, "--skip-llm")
    # Uncommitted staged file -> exit 1 (uncommitted check fires before scope check)
    assert result.returncode == 1


def test_3_3d_clean_tree_with_out_of_plan_file_in_committed_diff_emits_warning(
    tmp_path: Path,
) -> None:
    plan = tmp_path / "plan.md"
    # Plan declares no backtick-paths; extra.py is out-of-plan
    make_plan(plan, "- [x] Step 1.1: add checkbox parser")
    _init_repo(tmp_path)
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "initial")
    _git(tmp_path, "add", "plan.md")
    _git(tmp_path, "commit", "-q", "-m", "feat: add checkbox parser")
    (tmp_path / "extra.py").write_text("extra code\n")
    _git(tmp_path, "add", "extra.py")
    _git(tmp_path, "commit", "-q", "-m", "feat: add checkbox parser extra")

    result = run_pg(plan, "--skip-llm")
    # With clean tree and [x] steps + matching commits, scope check fires ->
    # llm-skipped warning -> exit 2
    assert result.returncode == 2
    data = json.loads(result.stdout)
    assert any(i.get("rule_id") == "llm-skipped" for i in data["issues"]), data


# ---------------------------------------------------------------------------
# Step 4.1 — Issue #525 regressions: origin/main preference
# Bug: check_scope's branch tuple was ("main", "master", "origin/main",
# "origin/master") — preferring stale local main. When local main lags
# origin/main, the resulting merge-base sweeps in every commit landed on
# trunk while the contributor was working.
# ---------------------------------------------------------------------------


def _setup_stale_main_repo(work: Path, ahead_file: str) -> None:
    """Sets up work/remote.git/sibling as siblings under work.parent, with
    origin/main exactly one commit ahead of local main, and HEAD on a
    feature branch off origin/main."""
    parent = work.parent
    remote = parent / "remote.git"
    sibling = parent / "sibling"

    def _init_main(path: Path, bare: bool = False) -> None:
        args = ["init", "-q", "--initial-branch=main"]
        if bare:
            args.append("--bare")
        args.append(str(path))
        result = subprocess.run(["git", *args], capture_output=True)
        if result.returncode != 0:
            fallback = ["git", "init", "-q"]
            if bare:
                fallback.append("--bare")
            fallback.append(str(path))
            subprocess.run(fallback, check=True, capture_output=True)
            subprocess.run(
                ["git", "-C", str(path), "symbolic-ref", "HEAD", "refs/heads/main"],
                check=True,
                capture_output=True,
            )

    _init_main(remote, bare=True)
    _init_main(work)
    _git(work, "config", "user.email", "test@test.com")
    _git(work, "config", "user.name", "Test")
    _git(work, "remote", "add", "origin", str(remote))
    (work / "seed.txt").write_text("seed\n")
    _git(work, "add", "seed.txt")
    _git(work, "commit", "-q", "-m", "chore: seed")
    _git(work, "push", "-q", "origin", "main")

    subprocess.run(
        ["git", "clone", "-q", str(remote), str(sibling)],
        check=True,
        capture_output=True,
    )
    _git(sibling, "config", "user.email", "test@test.com")
    _git(sibling, "config", "user.name", "Test")
    (sibling / ahead_file).write_text("ahead\n")
    _git(sibling, "add", ahead_file)
    _git(sibling, "commit", "-q", "-m", "feat: ahead on main")
    _git(sibling, "push", "-q", "origin", "main")

    _git(work, "fetch", "-q", "origin")
    _git(work, "checkout", "-q", "-b", "feature", "origin/main")


def test_4_1a_local_main_lags_origin_main_on_branch_file_not_reported_out_of_plan(
    tmp_path: Path,
) -> None:
    work = tmp_path / "work"
    _setup_stale_main_repo(work, "unrelated.py")
    (work / "a.py").write_text("branch work\n")
    _git(work, "add", "a.py")
    # Slice 1 isolates scope-check; the commit subject must substring-match
    # the slice header so commit-discipline passes and only scope-check is
    # under test.
    _git(work, "commit", "-q", "-m", "feat: write a.py for the slice")
    plan = work / "plan.md"
    plan.write_text("- [x] write a.py for the slice\n\n**Files:** `a.py`\n")

    result = run_pg(plan, "--skip-llm")
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["issues"] == [], data


def test_4_1b_local_main_equals_origin_main_on_branch_file_not_reported_out_of_plan(
    tmp_path: Path,
) -> None:
    work = tmp_path / "work"
    remote = tmp_path / "remote.git"

    def _init_main(path: Path, bare: bool = False) -> None:
        args = ["init", "-q", "--initial-branch=main"]
        if bare:
            args.append("--bare")
        args.append(str(path))
        result = subprocess.run(["git", *args], capture_output=True)
        if result.returncode != 0:
            fallback = ["git", "init", "-q"]
            if bare:
                fallback.append("--bare")
            fallback.append(str(path))
            subprocess.run(fallback, check=True, capture_output=True)
            subprocess.run(
                ["git", "-C", str(path), "symbolic-ref", "HEAD", "refs/heads/main"],
                check=True,
                capture_output=True,
            )

    _init_main(remote, bare=True)
    _init_main(work)
    _git(work, "config", "user.email", "test@test.com")
    _git(work, "config", "user.name", "Test")
    _git(work, "remote", "add", "origin", str(remote))
    (work / "seed.txt").write_text("seed\n")
    _git(work, "add", "seed.txt")
    _git(work, "commit", "-q", "-m", "chore: seed")
    _git(work, "push", "-q", "origin", "main")
    _git(work, "fetch", "-q", "origin")
    _git(work, "checkout", "-q", "-b", "feature")
    (work / "a.py").write_text("branch work\n")
    _git(work, "add", "a.py")
    _git(work, "commit", "-q", "-m", "feat: write a.py for the slice")
    plan = work / "plan.md"
    plan.write_text("- [x] write a.py for the slice\n\n**Files:** `a.py`\n")

    result = run_pg(plan, "--skip-llm")
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["issues"] == [], data


# ---------------------------------------------------------------------------
# Step 4.2 — Issue #525 regressions: file-path matcher
# ---------------------------------------------------------------------------


def test_4_2a_conventional_commit_on_declared_file_satisfies_the_matcher(
    tmp_path: Path,
) -> None:
    _init_repo(tmp_path)
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "chore: initial")
    (tmp_path / "a.py").write_text("branch work\n")
    _git(tmp_path, "add", "a.py")
    _git(
        tmp_path,
        "commit",
        "-q",
        "-m",
        "feat(scope): wording unrelated to the slice header",
    )
    plan = tmp_path / "plan.md"
    plan.write_text("- [x] Slice 1: do thing\n\n**Files:** `a.py`\n")

    result = run_pg(plan, "--skip-llm")
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["issues"] == [], data


def test_4_2b_commit_touches_one_of_multiple_declared_files_any_of_semantics(
    tmp_path: Path,
) -> None:
    _init_repo(tmp_path)
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "chore: initial")
    (tmp_path / "b.py").write_text("branch work\n")
    _git(tmp_path, "add", "b.py")
    _git(tmp_path, "commit", "-q", "-m", "feat: anything")
    plan = tmp_path / "plan.md"
    plan.write_text("- [x] Slice 1: do thing\n\n**Files:** `a.py`, `b.py`\n")

    result = run_pg(plan, "--skip-llm")
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["issues"] == [], data


def test_4_2c_commit_modifies_only_undeclared_files_matcher_fails_naming_the_slice(
    tmp_path: Path,
) -> None:
    _init_repo(tmp_path)
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "chore: initial")
    (tmp_path / "b.py").write_text("branch work\n")
    _git(tmp_path, "add", "b.py")
    _git(tmp_path, "commit", "-q", "-m", "feat: do thing")
    plan = tmp_path / "plan.md"
    plan.write_text("- [x] do thing\n\n**Files:** `a.py`\n")

    result = run_pg(plan, "--skip-llm")
    assert result.returncode == 1
    data = json.loads(result.stdout)
    errs = [
        i
        for i in data["issues"]
        if i["severity"] == "error" and "'do thing'" in i["message"]
    ]
    assert len(errs) == 1, data


# ---------------------------------------------------------------------------
# Step 4.3 — Issue #525 regressions: Build Progress anchor + AC mirror skip
# ---------------------------------------------------------------------------


def test_4_3_mirror_ac_mirror_inside_build_progress_is_skipped(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "feat: do the slice work")
    plan = tmp_path / "plan.md"
    plan.write_text(
        "## Build Progress\n\n"
        "### Slices (grouped by wave)\n\n"
        "- [x] do the slice work\n\n"
        "### Acceptance Criteria\n\n"
        "- [ ] A1: aspirational outcome 1\n"
        "- [ ] A2: aspirational outcome 2\n"
    )

    result = run_pg(plan, "--pre-pr", "--skip-llm")
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["issues"] == [], data


def test_4_3a_build_progress_done_plus_ac_undone_pre_pr_exits_0_acs_ignored(
    tmp_path: Path,
) -> None:
    _init_repo(tmp_path)
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "feat: do the slice work")
    plan = tmp_path / "plan.md"
    plan.write_text(
        "## Build Progress\n\n"
        "- [x] do the slice work\n\n"
        "## Acceptance Criteria\n\n"
        "- [ ] A1: foo\n"
        "- [ ] A2: bar\n"
        "- [ ] A3: baz\n"
    )

    result = run_pg(plan, "--pre-pr", "--skip-llm")
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["issues"] == [], data


def test_4_3b_build_progress_undone_plus_ac_undone_pre_pr_exits_1_naming_slice_not_acs(
    tmp_path: Path,
) -> None:
    _init_repo(tmp_path)
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "chore: initial")
    plan = tmp_path / "plan.md"
    plan.write_text(
        "## Build Progress\n\n"
        "- [ ] Slice 1: do thing\n\n"
        "## Acceptance Criteria\n\n"
        "- [ ] A1: foo\n"
        "- [ ] A2: bar\n"
        "- [ ] A3: baz\n"
    )

    result = run_pg(plan, "--pre-pr", "--skip-llm")
    assert result.returncode == 1
    data = json.loads(result.stdout)
    errs = [i for i in data["issues"] if i["severity"] == "error"]
    assert any("Slice 1: do thing" in i["message"] for i in errs), data
    for i in errs:
        msg = i["message"]
        assert "A1:" not in msg and "A2:" not in msg and "A3:" not in msg, (
            "AC item leaked into errors: " + msg
        )


def test_4_3c_build_progress_section_with_no_checkboxes_exits_1_naming_plan_file(
    tmp_path: Path,
) -> None:
    _init_repo(tmp_path)
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "chore: initial")
    plan = tmp_path / "plan.md"
    plan.write_text(
        "## Build Progress\n\n"
        "Some prose, no checkboxes.\n\n"
        "## Acceptance Criteria\n\n"
        "- [ ] A1: foo\n"
    )

    result = run_pg(plan, "--skip-llm")
    assert result.returncode == 1
    data = json.loads(result.stdout)
    errs = [i for i in data["issues"] if i["severity"] == "error"]
    assert any("plan.md" in (i.get("message", "") + i.get("file", "")) for i in errs), (
        data
    )
    for i in errs:
        assert "A1:" not in i["message"], "AC item leaked into errors: " + i["message"]


def test_4_3d_legacy_plan_with_no_build_progress_heading_falls_back_to_whole_file_scan(
    tmp_path: Path,
) -> None:
    _init_repo(tmp_path)
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "feat: do thing")
    plan = tmp_path / "plan.md"
    plan.write_text("- [x] Step 1.1: do thing\n")

    result = run_pg(plan, "--skip-llm")
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["issues"] == [], data


# ---------------------------------------------------------------------------
# Step 4.4 — Issue #525 end-to-end
# ---------------------------------------------------------------------------


def test_4_4_realistic_plan_with_all_three_525_patterns_passes_the_pre_pr_gate(
    tmp_path: Path,
) -> None:
    work = tmp_path / "work"
    _setup_stale_main_repo(work, "unrelated.py")
    (work / "a.py").write_text("branch work\n")
    _git(work, "add", "a.py")
    _git(
        work, "commit", "-q", "-m", "feat(scope): wording unrelated to the slice header"
    )
    plan = work / "plan.md"
    plan.write_text(
        "## Build Progress\n\n"
        "- [x] Slice 1: do thing\n\n"
        "**Files:** `a.py`\n\n"
        "## Acceptance Criteria\n\n"
        "- [ ] A1: foo\n"
        "- [ ] A2: bar\n"
        "- [ ] A3: baz\n"
    )

    result = run_pg(plan, "--pre-pr", "--skip-llm")
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["issues"] == [], data
