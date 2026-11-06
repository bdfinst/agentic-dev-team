"""Slice 3 — plugins/dev-team/scripts/progress_guardian.py
Covers checkbox parsing, git-log cross-reference, uncommitted-change check,
pre-PR flag, and scope creep.

Ported from tests/scripts/progress_guardian_tests.bats (issue #676).
pytest's tmp_path fixture replaces the bash hermetic helper's mktemp -d +
rm -rf isolation (see tests/lib/hermetic.bash / issue #546) — every git
fixture below runs against its own tmp_path, never the parent worktree's
gitdir. Every `git` subprocess also scrubs the git-exported env vars and
redirects global/system config to /dev/null (issue #546/#715): a host
~/.gitconfig with `commit.gpgsign = true` otherwise leaks into these `git
commit` calls and races the gpg-agent when this file's tests run in parallel
across pytest-xdist workers, producing flaky exit-128 failures — this is why
ci-local.sh previously had to pin this file to a single worker via `--dist
loadfile` (see scripts/ci-local.sh's chk_hook_units comment).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from _repo_root import REPO_ROOT

PG = REPO_ROOT / "plugins" / "dev-team" / "scripts" / "progress_guardian.py"

_GIT_SCRUB_ENV_VARS = (
    "GIT_DIR",
    "GIT_COMMON_DIR",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_NAMESPACE",
    "GIT_WORK_TREE",
    "GIT_PREFIX",
    "GIT_REFLOG_ACTION",
)


def _hermetic_env() -> dict:
    env = {k: v for k, v in os.environ.items() if k not in _GIT_SCRUB_ENV_VARS}
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    env["GIT_CONFIG_SYSTEM"] = "/dev/null"
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    return env


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, env=_hermetic_env()
    )


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
        env=_hermetic_env(),
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
        result = subprocess.run(["git", *args], capture_output=True, check=False)
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
        result = subprocess.run(["git", *args], capture_output=True, check=False)
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
    _write_verify_log(work, branch="feature")

    result = run_pg(plan, "--pre-pr", "--skip-llm")
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["issues"] == [], data


# ---------------------------------------------------------------------------
# Step 5 — Issue #713: directory-style `**Files:**` declarations
# Bug: BACKTICK_PATH_RE only captures backtick-quoted paths that end in a
# dot-extension, so a `**Files:** `some/dir/`` declaration (a common way to
# scope a slice that adds several new files under one folder) is invisible
# to _parse_slice_files and check_scope's declared_paths, silently falling
# through to the pre-#525 substring fallback / flagging every file as
# out-of-plan.
# ---------------------------------------------------------------------------


def test_5_1_directory_declaration_satisfies_commit_discipline(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "chore: initial")
    (tmp_path / "new_feature").mkdir()
    (tmp_path / "new_feature" / "SKILL.md").write_text("skill\n")
    _git(tmp_path, "add", "new_feature/SKILL.md")
    _git(tmp_path, "commit", "-q", "-m", "feat: add new-feature skill")
    plan = tmp_path / "plan.md"
    plan.write_text(
        "- [x] Slice 1: add new-feature skill\n\n**Files:** `new_feature/`\n"
    )

    result = run_pg(plan, "--skip-llm")
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["issues"] == [], data


def test_5_2_directory_declaration_still_catches_real_gaps(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "chore: initial")
    (tmp_path / "unrelated.py").write_text("code\n")
    _git(tmp_path, "add", "unrelated.py")
    _git(tmp_path, "commit", "-q", "-m", "feat: add unrelated file")
    plan = tmp_path / "plan.md"
    plan.write_text("- [x] add new-feature skill\n\n**Files:** `new_feature/`\n")

    result = run_pg(plan, "--skip-llm")
    assert result.returncode == 1
    data = json.loads(result.stdout)
    errs = [
        i
        for i in data["issues"]
        if i["severity"] == "error" and "'add new-feature skill'" in i["message"]
    ]
    assert len(errs) == 1, data


def test_5_3a_check_scope_does_not_flag_file_under_declared_directory(
    tmp_path: Path,
) -> None:
    _init_repo(tmp_path)
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "initial")
    plan = tmp_path / "plan.md"
    make_plan(
        plan,
        "- [x] Slice 1: add new-feature skill\n\n**Files:** `new_feature/`",
    )
    _git(tmp_path, "add", "plan.md")
    _git(tmp_path, "commit", "-q", "-m", "feat: add new-feature skill")
    (tmp_path / "new_feature").mkdir()
    (tmp_path / "new_feature" / "SKILL.md").write_text("skill\n")
    _git(tmp_path, "add", "new_feature/SKILL.md")
    _git(tmp_path, "commit", "-q", "-m", "feat: add new-feature skill impl")

    result = run_pg(plan, "--skip-llm")
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["issues"] == [], data


def test_5_3b_check_scope_still_flags_file_outside_declared_directory(
    tmp_path: Path,
) -> None:
    _init_repo(tmp_path)
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "initial")
    plan = tmp_path / "plan.md"
    make_plan(
        plan,
        "- [x] Slice 1: add new-feature skill\n\n**Files:** `new_feature/`",
    )
    _git(tmp_path, "add", "plan.md")
    _git(tmp_path, "commit", "-q", "-m", "feat: add new-feature skill")
    (tmp_path / "new_feature").mkdir()
    (tmp_path / "new_feature" / "SKILL.md").write_text("skill\n")
    _git(tmp_path, "add", "new_feature/SKILL.md")
    (tmp_path / "extra.py").write_text("extra\n")
    _git(tmp_path, "add", "extra.py")
    _git(tmp_path, "commit", "-q", "-m", "feat: add new-feature skill plus extra")

    result = run_pg(plan, "--skip-llm")
    assert result.returncode == 2
    data = json.loads(result.stdout)
    assert any(i.get("rule_id") == "llm-skipped" for i in data["issues"]), data


def test_5_4_non_path_backtick_token_not_mis_captured_as_declared_path(
    tmp_path: Path,
) -> None:
    _init_repo(tmp_path)
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "chore: initial")
    (tmp_path / "unrelated.py").write_text("code\n")
    _git(tmp_path, "add", "unrelated.py")
    _git(tmp_path, "commit", "-q", "-m", "feat: unrelated change")
    plan = tmp_path / "plan.md"
    plan.write_text("- [x] wire up the hook\n\n**Files:** `runHook()`\n")

    result = run_pg(plan, "--skip-llm")
    # `runHook()` has no extension and no trailing slash -> not captured as
    # a declared path, so the slice falls back to substring matching on
    # "wire up the hook" (which isn't in any commit subject) -> exit 1 with
    # the substring-fallback message, proving the token was never absorbed
    # into declared_paths.
    assert result.returncode == 1
    data = json.loads(result.stdout)
    errs = [
        i
        for i in data["issues"]
        if i["severity"] == "error" and "'wire up the hook'" in i["message"]
    ]
    assert len(errs) == 1, data
    assert "whose subject contains" in errs[0]["message"], errs[0]


# ---------------------------------------------------------------------------
# Step 6 — issue #727: pre-PR gate requires evidence of /verify for
# runtime-surface changes (metrics/verify-log.jsonl)
# ---------------------------------------------------------------------------


def _write_verify_log(repo: Path, branch: str, outcome: str = "ran") -> None:
    metrics_dir = repo / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": "2026-07-02T00:00:00Z",
        "plan": "plans/plan.md",
        "slice": "1",
        "branch": branch,
        "files": ["a.py"],
        "outcome": outcome,
    }
    log_path = metrics_dir / "verify-log.jsonl"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")
    # Commit it so it doesn't trip the uncommitted-changes check — the
    # scenario under test is "does a committed verify-log entry satisfy
    # the gate", isolated from check_uncommitted (issue #727).
    _git(repo, "add", "metrics/verify-log.jsonl")
    _git(repo, "commit", "-q", "-m", "chore: record verify-log entry")


def _current_branch(repo: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def test_6a_pre_pr_with_runtime_file_and_no_verify_log_exits_1(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "chore: initial")
    (tmp_path / "a.py").write_text("branch work\n")
    _git(tmp_path, "add", "a.py")
    _git(tmp_path, "commit", "-q", "-m", "feat: do thing")
    plan = tmp_path / "plan.md"
    plan.write_text("- [x] do thing\n\n**Files:** `a.py`\n")

    result = run_pg(plan, "--pre-pr", "--skip-llm")
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert any("verify-log" in i["message"] for i in data["issues"]), data


def test_6b_pre_pr_with_runtime_file_and_matching_verify_log_entry_exits_0(
    tmp_path: Path,
) -> None:
    _init_repo(tmp_path)
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "chore: initial")
    (tmp_path / "a.py").write_text("branch work\n")
    _git(tmp_path, "add", "a.py")
    _git(tmp_path, "commit", "-q", "-m", "feat: do thing")
    plan = tmp_path / "plan.md"
    plan.write_text("- [x] do thing\n\n**Files:** `a.py`\n")
    _write_verify_log(tmp_path, branch=_current_branch(tmp_path))

    result = run_pg(plan, "--pre-pr", "--skip-llm")
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["issues"] == [], data


def test_6c_pre_pr_with_verify_log_for_a_different_branch_still_fails(
    tmp_path: Path,
) -> None:
    _init_repo(tmp_path)
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "chore: initial")
    (tmp_path / "a.py").write_text("branch work\n")
    _git(tmp_path, "add", "a.py")
    _git(tmp_path, "commit", "-q", "-m", "feat: do thing")
    plan = tmp_path / "plan.md"
    plan.write_text("- [x] do thing\n\n**Files:** `a.py`\n")
    _write_verify_log(tmp_path, branch="some-other-branch")

    result = run_pg(plan, "--pre-pr", "--skip-llm")
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert any("verify-log" in i["message"] for i in data["issues"]), data


def test_6d_pre_pr_with_test_only_changes_skips_the_verify_log_check(
    tmp_path: Path,
) -> None:
    _init_repo(tmp_path)
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "chore: initial")
    (tmp_path / "a.test.js").write_text("test('x', () => {})\n")
    _git(tmp_path, "add", "a.test.js")
    _git(tmp_path, "commit", "-q", "-m", "test: add test")
    plan = tmp_path / "plan.md"
    plan.write_text("- [x] add test\n\n**Files:** `a.test.js`\n")

    result = run_pg(plan, "--pre-pr", "--skip-llm")
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["issues"] == [], data


def test_6e_pre_pr_with_docs_only_changes_skips_the_verify_log_check(
    tmp_path: Path,
) -> None:
    _init_repo(tmp_path)
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "chore: initial")
    (tmp_path / "notes.md").write_text("# Notes\n")
    _git(tmp_path, "add", "notes.md")
    _git(tmp_path, "commit", "-q", "-m", "docs: add notes")
    plan = tmp_path / "plan.md"
    plan.write_text("- [x] add notes\n\n**Files:** `notes.md`\n")

    result = run_pg(plan, "--pre-pr", "--skip-llm")
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["issues"] == [], data


def test_865_1_pre_pr_with_matching_declared_scope_emits_no_warning(
    tmp_path: Path,
) -> None:
    """Issue #865 AC8: a branch that only touches declared Files gets no
    scope-adherence warning."""
    _init_repo(tmp_path)
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "chore: initial")
    (tmp_path / "a.py").write_text("branch work\n")
    _git(tmp_path, "add", "a.py")
    _git(tmp_path, "commit", "-q", "-m", "feat: do thing")
    plan = tmp_path / "plan.md"
    plan.write_text("- [x] Slice 1: do thing\n\n**Files:** `a.py`\n")
    _write_verify_log(tmp_path, branch=_current_branch(tmp_path))

    result = run_pg(plan, "--pre-pr", "--skip-llm")
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert not any(
        i.get("rule_id") == "declared-scope-warning" for i in data["issues"]
    ), data


def test_865_2_pre_pr_with_out_of_scope_edit_emits_named_warning_not_a_gate_failure(
    tmp_path: Path,
) -> None:
    """Out-of-scope edits without freeze are a NAMED WARNING, never a
    pre-PR gate failure (#865 Ambiguity Log Q2)."""
    _init_repo(tmp_path)
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "chore: initial")
    (tmp_path / "a.py").write_text("branch work\n")
    (tmp_path / "extra.py").write_text("out of scope\n")
    _git(tmp_path, "add", "a.py", "extra.py")
    _git(tmp_path, "commit", "-q", "-m", "feat: do thing plus extra")
    plan = tmp_path / "plan.md"
    plan.write_text("- [x] Slice 1: do thing\n\n**Files:** `a.py`\n")
    _write_verify_log(tmp_path, branch=_current_branch(tmp_path))

    result = run_pg(plan, "--pre-pr", "--skip-llm")
    # Not a gate failure — exit 2 (warn) or better, never 1 (fail) for this
    # reason. (--skip-llm's existing check_scope may also warn; either way
    # returncode must never be 1 here.)
    assert result.returncode != 1
    data = json.loads(result.stdout)
    warning = next(
        i for i in data["issues"] if i.get("rule_id") == "declared-scope-warning"
    )
    assert warning["severity"] == "warning"
    assert "extra.py" in warning["message"]


def test_865_3_pre_pr_with_no_slice_declaring_files_emits_no_warning(
    tmp_path: Path,
) -> None:
    """A plan where no slice declares Files has nothing to compare against."""
    _init_repo(tmp_path)
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "chore: initial")
    (tmp_path / "a.py").write_text("branch work\n")
    _git(tmp_path, "add", "a.py")
    _git(tmp_path, "commit", "-q", "-m", "feat: do thing")
    plan = tmp_path / "plan.md"
    plan.write_text("- [x] Slice 1: do thing\n")
    _write_verify_log(tmp_path, branch=_current_branch(tmp_path))

    result = run_pg(plan, "--pre-pr", "--skip-llm")
    data = json.loads(result.stdout)
    assert not any(
        i.get("rule_id") == "declared-scope-warning" for i in data["issues"]
    ), data


def test_865_4_glob_pattern_in_files_covers_matching_file(tmp_path: Path) -> None:
    """Issue #865 AC9: glob patterns (fnmatch) are accepted in Files."""
    _init_repo(tmp_path)
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "chore: initial")
    (tmp_path / "session.py").write_text("branch work\n")
    _git(tmp_path, "add", "session.py")
    _git(tmp_path, "commit", "-q", "-m", "feat: do thing")
    plan = tmp_path / "plan.md"
    plan.write_text("- [x] Slice 1: do thing\n\n**Files:** `*.py`\n")
    _write_verify_log(tmp_path, branch=_current_branch(tmp_path))

    result = run_pg(plan, "--pre-pr", "--skip-llm")
    data = json.loads(result.stdout)
    assert not any(
        i.get("rule_id") == "declared-scope-warning" for i in data["issues"]
    ), data


def test_6f_non_pre_pr_run_does_not_enforce_the_verify_log_check(
    tmp_path: Path,
) -> None:
    _init_repo(tmp_path)
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "chore: initial")
    (tmp_path / "a.py").write_text("branch work\n")
    _git(tmp_path, "add", "a.py")
    _git(tmp_path, "commit", "-q", "-m", "feat: do thing")
    plan = tmp_path / "plan.md"
    plan.write_text("- [x] do thing\n\n**Files:** `a.py`\n")

    result = run_pg(plan, "--skip-llm")
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["issues"] == [], data


# ---------------------------------------------------------------------------
# #2275 Step 3.1 — pins for the git evidence rule moved to
# scripts/lib/commit_evidence.py. The guardian keeps its own policy where the
# feature record reports "unverifiable": whole-history matching with no base,
# a warning on zero commits.
# ---------------------------------------------------------------------------


def _init_trunk_and_feature(cwd: Path) -> None:
    """Repo with `main` holding one seed commit and HEAD on `feature`."""
    _git(cwd, "init", "-q", "--initial-branch=main")
    _git(cwd, "config", "user.email", "test@test.com")
    _git(cwd, "config", "user.name", "Test")
    (cwd / "seed.txt").write_text("seed\n")
    _git(cwd, "add", "seed.txt")
    _git(cwd, "commit", "-q", "-m", "chore: seed")
    _git(cwd, "checkout", "-q", "-b", "feature")


def _commit_file(cwd: Path, name: str, message: str) -> None:
    target = cwd / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("work\n")
    _git(cwd, "add", name)
    _git(cwd, "commit", "-q", "-m", message)


def test_3_1_pin_orphan_head_matches_against_whole_history(tmp_path: Path) -> None:
    # No trunk ref: the only commit touching a.py is the root commit, which a
    # branch-bounded range would never reach. Whole-history matching passes it.
    _git(tmp_path, "init", "-q", "--initial-branch=dev")
    _git(tmp_path, "config", "user.email", "test@test.com")
    _git(tmp_path, "config", "user.name", "Test")
    _commit_file(tmp_path, "a.py", "chore: root")
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "chore: later")
    plan = tmp_path / "plan.md"
    plan.write_text("- [x] Slice 1: do thing\n\n**Files:** `a.py`\n")

    result = run_pg(plan, "--skip-llm")
    assert result.returncode == 0, result.stdout
    assert json.loads(result.stdout)["issues"] == []


def test_3_1_pin_orphan_head_subject_fallback_reaches_the_root_commit(
    tmp_path: Path,
) -> None:
    _git(tmp_path, "init", "-q", "--initial-branch=dev")
    _git(tmp_path, "config", "user.email", "test@test.com")
    _git(tmp_path, "config", "user.name", "Test")
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "feat: add the parser")
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "chore: later")
    plan = tmp_path / "plan.md"
    plan.write_text("- [x] add the parser\n")

    result = run_pg(plan, "--skip-llm")
    assert result.returncode == 0, result.stdout
    assert json.loads(result.stdout)["issues"] == []


def test_3_1_pin_zero_commits_is_a_warning_not_an_error(tmp_path: Path) -> None:
    _init_repo(tmp_path)  # no commit at all
    plan = tmp_path / "plan.md"
    plan.write_text("- [x] Slice 1: do thing\n\n**Files:** `a.py`\n")

    result = run_pg(plan, "--skip-llm")
    assert result.returncode == 2, result.stdout
    issues = json.loads(result.stdout)["issues"]
    assert [(i["severity"], i["message"]) for i in issues] == [
        (
            "warning",
            "No commits found on this branch — cannot verify commit discipline.",
        )
    ]


def test_3_1_pin_commit_older_than_the_branch_base_does_not_back_a_step(
    tmp_path: Path,
) -> None:
    _init_trunk_and_feature(tmp_path)
    _git(tmp_path, "checkout", "-q", "main")
    _commit_file(tmp_path, "a.py", "feat: on main before the branch point")
    _git(tmp_path, "checkout", "-q", "-b", "feature2")
    _commit_file(tmp_path, "other.py", "feat: unrelated branch work")
    plan = tmp_path / "plan.md"
    plan.write_text("- [x] Slice 1: do thing\n\n**Files:** `a.py`\n")

    result = run_pg(plan, "--skip-llm")
    assert result.returncode == 1, result.stdout
    errors = [
        i for i in json.loads(result.stdout)["issues"] if i["severity"] == "error"
    ]
    assert len(errors) == 1
    assert errors[0]["message"] == (
        "Done step 'Slice 1: do thing' has no matching commit in git log. "
        "Expected a commit on this branch that touched one of: a.py"
    )


def test_3_1_pin_heading_anchored_files_back_a_slice_item(tmp_path: Path) -> None:
    _init_trunk_and_feature(tmp_path)
    _commit_file(tmp_path, "docs/a.md", "feat: wording that never names the slice")
    plan = tmp_path / "plan.md"
    plan.write_text(
        "### Slice 1: Parse\n\n**Files:** `docs/a.md`\n\n"
        "## Build Progress\n\n- [x] Slice 1: Parse\n"
    )

    result = run_pg(plan, "--skip-llm")
    assert result.returncode == 0, result.stdout
    assert json.loads(result.stdout)["issues"] == []


def test_3_1_pin_heading_anchored_files_name_the_declared_files_when_unbacked(
    tmp_path: Path,
) -> None:
    _init_trunk_and_feature(tmp_path)
    _commit_file(tmp_path, "docs/a.md", "feat: parse")
    plan = tmp_path / "plan.md"
    plan.write_text(
        "### Slice 1: Parse\n\n**Files:** `docs/b.md`\n\n"
        "## Build Progress\n\n- [x] Slice 1: Parse\n"
    )

    result = run_pg(plan, "--skip-llm")
    assert result.returncode == 1, result.stdout
    messages = [i["message"] for i in json.loads(result.stdout)["issues"]]
    assert any(
        "Done step 'Slice 1: Parse'" in m and "touched one of: docs/b.md" in m
        for m in messages
    ), messages


def test_3_1_pin_check_scope_honours_a_declared_glob_and_directory(
    tmp_path: Path,
) -> None:
    _init_trunk_and_feature(tmp_path)
    _commit_file(tmp_path, "src/auth/login.py", "feat: do thing")
    _commit_file(tmp_path, "docs/guide/intro.txt", "feat: do thing too")
    plan = tmp_path / "plan.md"
    plan.write_text(
        "- [x] do thing\n- [x] do thing too\n\n"
        "**Files:** `src/auth/*.py` and `docs/guide/`\n"
    )

    result = run_pg(plan, "--skip-llm")
    assert result.returncode == 0, result.stdout
    assert json.loads(result.stdout)["issues"] == []


def test_3_1_pin_check_scope_still_flags_a_file_outside_a_declared_glob(
    tmp_path: Path,
) -> None:
    _init_trunk_and_feature(tmp_path)
    _commit_file(tmp_path, "src/auth/ok.py", "feat: do thing")
    _commit_file(tmp_path, "src/other/x.py", "feat: stray edit")
    plan = tmp_path / "plan.md"
    plan.write_text("- [x] do thing\n\n**Files:** `src/auth/*.py`\n")

    result = run_pg(plan, "--skip-llm")
    assert result.returncode == 2, result.stdout
    issues = json.loads(result.stdout)["issues"]
    skipped = [i for i in issues if i.get("rule_id") == "llm-skipped"]
    assert len(skipped) == 1, issues
    assert "1 file(s) not declared in plan" in skipped[0]["message"]


def test_3_1_pin_a_range_of_only_merge_commits_is_a_warning_not_an_error(
    tmp_path: Path,
) -> None:
    # The base resolves (main moved on), but `--no-merges` leaves the range
    # with no subject: the zero-commit warning, not a matching error.
    _init_trunk_and_feature(tmp_path)
    _git(tmp_path, "checkout", "-q", "main")
    _commit_file(tmp_path, "a.py", "feat: lands on main")
    _git(tmp_path, "checkout", "-q", "feature")
    _git(tmp_path, "merge", "-q", "--no-ff", "-m", "Merge main", "main")
    plan = tmp_path / "plan.md"
    plan.write_text("- [x] Slice 1: do thing\n\n**Files:** `a.py`\n")

    result = run_pg(plan, "--skip-llm")
    assert result.returncode == 2, result.stdout
    issues = json.loads(result.stdout)["issues"]
    assert [(i["severity"], i["message"]) for i in issues] == [
        (
            "warning",
            "No commits found on this branch — cannot verify commit discipline.",
        )
    ]


def test_3_1_pin_a_branch_level_with_trunk_matches_against_whole_history(
    tmp_path: Path,
) -> None:
    # Branch and trunk share HEAD, so no base diverges: whole history applies,
    # and the declared file is in the seed commit.
    _git(tmp_path, "init", "-q", "--initial-branch=main")
    _git(tmp_path, "config", "user.email", "test@test.com")
    _git(tmp_path, "config", "user.name", "Test")
    _commit_file(tmp_path, "a.py", "chore: seed")
    _git(tmp_path, "checkout", "-q", "-b", "feature")
    plan = tmp_path / "plan.md"
    plan.write_text("- [x] Slice 1: do thing\n\n**Files:** `a.py`\n")

    result = run_pg(plan, "--skip-llm")
    assert result.returncode == 0, result.stdout
    assert json.loads(result.stdout)["issues"] == []


def _init_orphan(cwd: Path) -> None:
    _git(cwd, "init", "-q", "--initial-branch=dev")
    _git(cwd, "config", "user.email", "test@test.com")
    _git(cwd, "config", "user.name", "Test")
    _commit_file(cwd, "other.py", "chore: root")
    _git(cwd, "commit", "-q", "--allow-empty", "-m", "chore: later")


def test_3_1_pin_orphan_head_with_a_declared_file_never_committed_fails(
    tmp_path: Path,
) -> None:
    _init_orphan(tmp_path)
    plan = tmp_path / "plan.md"
    plan.write_text("- [x] Slice 1: do thing\n\n**Files:** `a.py`\n")

    result = run_pg(plan, "--skip-llm")
    assert result.returncode == 1, result.stdout
    messages = [
        i["message"]
        for i in json.loads(result.stdout)["issues"]
        if i["severity"] == "error"
    ]
    assert messages == [
        (
            "Done step 'Slice 1: do thing' has no matching commit in git log. "
            "Expected a commit on this branch that touched one of: a.py"
        )
    ]


def test_3_1_pin_orphan_head_with_a_subject_that_matches_nothing_fails(
    tmp_path: Path,
) -> None:
    _init_orphan(tmp_path)
    plan = tmp_path / "plan.md"
    plan.write_text("- [x] add the parser\n")

    result = run_pg(plan, "--skip-llm")
    assert result.returncode == 1, result.stdout
    messages = [
        i["message"]
        for i in json.loads(result.stdout)["issues"]
        if i["severity"] == "error"
    ]
    assert messages == [
        (
            "Done step 'add the parser' has no matching commit in git log. "
            "Expected a commit whose subject contains: 'add the parser'"
        )
    ]


# ---------------------------------------------------------------------------
# #2275 — the steps come from the feature record's Build Progress view
# ---------------------------------------------------------------------------


def _clean_repo_with_plan(tmp_path: Path, content: str) -> Path:
    plan = tmp_path / "plan.md"
    make_plan(plan, content)
    _init_repo(tmp_path)
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "initial commit")
    return plan


def _messages(result: subprocess.CompletedProcess) -> list[str]:
    return [i["message"] for i in json.loads(result.stdout)["issues"]]


def test_2275_acceptance_criteria_mirror_is_not_read_as_steps(tmp_path: Path) -> None:
    plan = _clean_repo_with_plan(
        tmp_path,
        "## Build Progress\n\n"
        "### Acceptance Criteria\n"
        "- [x] AC1 mirrored criterion\n\n"
        "### Slices\n"
        "- [ ] Slice 1: the real work\n",
    )

    result = run_pg(plan, "--skip-llm", "--pre-pr")

    messages = _messages(result)
    assert not any("mirrored criterion" in m for m in messages), messages
    assert any("Slice 1: the real work" in m for m in messages), messages


def test_2275_legacy_plan_without_build_progress_heading_is_read_whole(
    tmp_path: Path,
) -> None:
    plan = _clean_repo_with_plan(
        tmp_path,
        "## Acceptance Criteria\n"
        "- [ ] AC1 a criterion\n\n"
        "- [ ] Step 1.1: first legacy step\n",
    )

    result = run_pg(plan, "--skip-llm", "--pre-pr")

    messages = _messages(result)
    assert any("AC1 a criterion" in m for m in messages), messages
    assert any("first legacy step" in m for m in messages), messages


def test_2275_build_progress_with_only_a_mirror_is_the_no_checkbox_error(
    tmp_path: Path,
) -> None:
    plan = _clean_repo_with_plan(
        tmp_path,
        "## Build Progress\n\n### Acceptance Criteria\n- [ ] AC1 only the mirror\n",
    )

    result = run_pg(plan, "--skip-llm")

    assert result.returncode == 1
    issues = json.loads(result.stdout)["issues"]
    assert [(i["severity"], i["message"], i["file"]) for i in issues] == [
        (
            "error",
            "No checkbox steps found in plan file: plan.md",
            str(plan.resolve()),
        )
    ]
