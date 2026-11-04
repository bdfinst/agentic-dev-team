"""build_candidates_git.py — the git-facing half of the candidate lifecycle.

Measures a candidate worktree (`collect`), merges a winner and restores the
build branch on failure (`reconcile`, `restore_branch`), and removes candidate
branches and worktrees (`cleanup`). Every git call goes through `_git`, which
bounds it with a timeout.

Stdlib only, plus `lib/plan_parse` (ADR 0014, ADR 0015, ADR 0031).
"""

from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from build_candidates_model import (
    SCREENING_OK,
    SCREENING_UNPARSEABLE_PREFIX,
    Candidate,
    DataError,
    GitError,
    RestoreFailedError,
    load_json_object,
)

_HERE = Path(__file__).resolve().parent

_GIT_TIMEOUT_SECONDS = 120
# build_wave_reconcile.py bounds its own suite run with this variable; the
# wrapper allows that bound plus a margin for the merge and checkout around it.
_RECONCILE_TIMEOUT_ENV = "BUILD_WAVE_RECONCILE_TEST_CMD_TIMEOUT"
_RECONCILE_DEFAULT_SUITE_TIMEOUT_SECONDS = 1800.0
_RECONCILE_MARGIN_SECONDS = 300.0
_RECONCILE_SCRIPT = _HERE / "build_wave_reconcile.py"

_LENS_SPEC_COMPLIANCE = "spec-compliance-review"
_LENS_CORRECTNESS = "correctness-review"
_UNMET_SCENARIO_CATEGORIES = frozenset({"uncovered-scenario", "unmet-criterion"})

_SCENARIO_LINE_RE = re.compile(r"^\s*Scenario( Outline)?:")


def _git(repo: str, *args: str) -> subprocess.CompletedProcess:
    """Run `git -C <repo> <args>`, bounded by a timeout; raise GitError when
    git cannot be run at all. A non-zero exit is returned, not raised."""
    try:
        return subprocess.run(
            ["git", "-C", repo, *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitError(f"git {' '.join(args)} could not run in {repo}: {exc}") from None


def _diff_line_count(worktree: str, base: str) -> int:
    """Added plus deleted lines in `base..HEAD`; a binary file counts 0."""
    result = _git(worktree, "diff", "--numstat", "--end-of-options", f"{base}..HEAD")
    if result.returncode != 0:
        raise GitError(
            f"collect: git diff --numstat {base}..HEAD failed in {worktree}: "
            f"{result.stderr.strip()}"
        )
    total = 0
    for line in result.stdout.splitlines():
        added, deleted, _path = line.split("\t", 2)
        total += sum(int(n) for n in (added, deleted) if n.isdigit())
    return total


def _require_commit(worktree: str, base: str) -> None:
    """Raise DataError unless `base` names a commit in `worktree`; a ref that
    starts with `-` is rejected before git sees it."""
    if base.startswith("-"):
        raise DataError(f"collect: base must not start with '-'; got '{base}'")
    result = _git(
        worktree, "rev-parse", "--verify", "--end-of-options", f"{base}^{{commit}}"
    )
    if result.returncode != 0:
        raise GitError(
            f"collect: base '{base}' is not a commit in {worktree}: "
            f"{result.stderr.strip()}"
        )


def _count_scenarios_in_slice(plan_path: str, step: str) -> int:
    """Scenario and Scenario Outline lines in the first Gherkin block of the
    slice that owns `step`."""
    lib_dir = str(_HERE / "lib")
    if lib_dir not in sys.path:
        sys.path.insert(0, lib_dir)
    import plan_parse

    try:
        text = Path(plan_path).read_text(encoding="utf-8")
    except OSError as exc:
        raise DataError(
            f"collect: cannot read plan {plan_path}: {exc.strerror}"
        ) from None
    except ValueError:
        raise DataError(f"collect: plan {plan_path} is not valid UTF-8") from None
    slice_id = step.split(".", 1)[0]
    blocks = {
        block_slice_id: gherkin
        for block_slice_id, _title, gherkin in plan_parse.slice_gherkin_blocks(
            text.splitlines()
        )
    }
    if slice_id not in blocks:
        raise DataError(f"collect: step {step} is outside any slice in {plan_path}")
    gherkin = blocks[slice_id]
    if gherkin is None:
        raise DataError(f"collect: slice {slice_id} (step {step}) has no gherkin block")
    return sum(1 for line in gherkin.splitlines() if _SCENARIO_LINE_RE.match(line))


def _lens_issues(path: str, lens: str) -> list[dict] | None:
    """The issue objects of a review-lens JSON file, or None when the file is
    missing, not JSON, or lacks a string `status` and a list `issues`."""
    try:
        data = load_json_object(path, lens)
    except DataError:
        return None
    issues = data.get("issues")
    if not isinstance(data.get("status"), str) or not isinstance(issues, list):
        return None
    return [issue for issue in issues if isinstance(issue, dict)]


def collect(
    *,
    candidate_id: int,
    branch: str,
    worktree: str,
    base: str,
    suite_exit: int,
    spec_json: str,
    correctness_json: str,
    plan: str,
    step: str,
    cost_usd: float,
) -> dict:
    """Build one candidate dict from the suite exit code, the worktree diff,
    the plan's Gherkin block and the two review-lens files."""
    _require_commit(worktree, base)
    total = _count_scenarios_in_slice(plan, step)
    diff_lines = _diff_line_count(worktree, base)
    spec_issues = _lens_issues(spec_json, _LENS_SPEC_COMPLIANCE)
    correctness_issues = _lens_issues(correctness_json, _LENS_CORRECTNESS)
    unparseable_lenses = [
        lens
        for lens, issues in (
            (_LENS_SPEC_COMPLIANCE, spec_issues),
            (_LENS_CORRECTNESS, correctness_issues),
        )
        if issues is None
    ]
    unmet = sum(
        1
        for issue in spec_issues or []
        if issue.get("category") in _UNMET_SCENARIO_CATEGORIES
    )

    def severity_count(severity: str) -> int:
        return sum(1 for i in correctness_issues or [] if i.get("severity") == severity)

    candidate = {
        "id": candidate_id,
        "branch": branch,
        "suite_green": suite_exit == 0,
        "scenarios_total": total,
        "scenarios_unmet": min(total, unmet),
        "errors": severity_count("error"),
        "warnings": severity_count("warning"),
        "diff_lines": diff_lines,
        "cost_usd": cost_usd,
        "screening": (
            f"{SCREENING_UNPARSEABLE_PREFIX}{unparseable_lenses[0]}"
            if unparseable_lenses
            else SCREENING_OK
        ),
    }
    try:
        return asdict(Candidate.from_dict(candidate))
    except ValueError as exc:
        raise DataError(f"collect: {exc}") from None


def _head_sha(repo: str) -> str:
    result = _git(repo, "rev-parse", "HEAD")
    if result.returncode != 0:
        raise GitError(
            f"reconcile: cannot resolve HEAD in {repo}: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def _current_branch(repo: str) -> str:
    return _git(repo, "symbolic-ref", "--short", "-q", "HEAD").stdout.strip()


def reconcile_timeout_seconds() -> float:
    """The suite bound build_wave_reconcile.py applies (same parsing rule as
    that script) plus the margin for the merge and checkout around it."""
    suite = _RECONCILE_DEFAULT_SUITE_TIMEOUT_SECONDS
    raw = os.environ.get(_RECONCILE_TIMEOUT_ENV)
    if raw:
        try:
            suite = float(raw)
        except ValueError:
            pass
    return suite + _RECONCILE_MARGIN_SECONDS


def _run_reconcile_script(
    repo: str, into: str, base: str, test_cmd: str, branch: str
) -> bool:
    """Run build_wave_reconcile.py in `repo`; True when it exits 0. Its stderr
    is passed through; its stdout is dropped. On timeout the script's whole
    process group is killed, so a hung suite does not outlive the wrapper."""
    command = [
        sys.executable,
        str(_RECONCILE_SCRIPT),
        "--into",
        into,
        "--base",
        base,
        "--test-cmd",
        test_cmd,
        branch,
    ]
    timeout = reconcile_timeout_seconds()
    with subprocess.Popen(
        command,
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    ) as process:
        try:
            _stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            print(
                f"reconcile: build_wave_reconcile.py timed out after {timeout:g}s",
                file=sys.stderr,
            )
            return False
    sys.stderr.write(stderr)
    return process.returncode == 0


def _merge_head_path(repo: str) -> Path:
    relative = _git(repo, "rev-parse", "--git-path", "MERGE_HEAD").stdout.strip()
    return Path(repo) / relative


def restore_branch(repo: str, pre_merge_sha: str) -> None:
    """Return HEAD to `pre_merge_sha`: abort a merge in progress, then
    `reset --keep` (never --hard: the worktree holds uncommitted plan edits).
    Raise RestoreFailedError unless HEAD is `pre_merge_sha`, no merge is in
    progress and no path is unmerged afterwards."""
    failure = RestoreFailedError(
        f"reconcile: could not restore the build branch to {pre_merge_sha}; "
        f"save your uncommitted edits, then run: git reset --keep {pre_merge_sha}"
    )
    try:
        merge_head = _merge_head_path(repo)
        if merge_head.exists():
            abort = _git(repo, "merge", "--abort")
            if abort.returncode != 0 and merge_head.exists():
                sys.stderr.write(abort.stderr)
                raise failure
        reset = _git(repo, "reset", "--keep", pre_merge_sha)
        if reset.returncode != 0:
            sys.stderr.write(reset.stderr)
        unmerged = _git(repo, "diff", "--name-only", "--diff-filter=U")
        restored = (
            _head_sha(repo) == pre_merge_sha
            and not merge_head.exists()
            and unmerged.returncode == 0
            and unmerged.stdout.strip() == ""
        )
    except GitError:
        raise failure from None
    if not restored:
        raise failure


def reconcile(*, repo: str, into: str, base: str, test_cmd: str, branch: str) -> dict:
    """Merge `branch` into the build branch with build_wave_reconcile.py. On
    failure restore the build branch to its pre-merge SHA and report
    merged=False; raise RestoreFailedError when that restore fails."""
    if _current_branch(repo) != into:
        raise DataError(f"reconcile: {repo} is not on build branch '{into}'")
    pre_merge_sha = _head_sha(repo)
    merged = _run_reconcile_script(repo, into, base, test_cmd, branch)
    if not merged:
        restore_branch(repo, pre_merge_sha)
    return {
        "branch": branch,
        "head": _head_sha(repo),
        "merged": merged,
        "pre_merge_sha": pre_merge_sha,
    }


def _worktree_entries(repo: str) -> list[tuple[str, str | None]]:
    """`(path, branch)` per worktree from `git worktree list --porcelain`,
    main worktree first; branch is None for a detached HEAD."""
    result = _git(repo, "worktree", "list", "--porcelain")
    if result.returncode != 0:
        raise GitError(f"cleanup: git worktree list failed: {result.stderr.strip()}")
    entries: list[tuple[str, str | None]] = []
    for block in result.stdout.split("\n\n"):
        path, branch = None, None
        for line in block.splitlines():
            if line.startswith("worktree "):
                path = line[len("worktree ") :]
            elif line.startswith("branch refs/heads/"):
                branch = line[len("branch refs/heads/") :]
        if path is not None:
            entries.append((path, branch))
    return entries


def _existing_branches(repo: str) -> set[str]:
    result = _git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads")
    if result.returncode != 0:
        raise GitError(f"cleanup: git for-each-ref failed: {result.stderr.strip()}")
    return set(result.stdout.splitlines())


def _git_or_fail(repo: str, branch: str, *args: str) -> None:
    result = _git(repo, *args)
    if result.returncode != 0:
        raise GitError(
            f"cleanup: git {' '.join(args)} failed for branch '{branch}': "
            f"{result.stderr.strip()}"
        )


def cleanup(*, repo: str, branches: Sequence[str]) -> dict:
    """Remove each listed branch and its worktree; a branch that is already
    gone is reported as absent.

    Refuses, removing nothing, when a listed branch is checked out in `repo`
    or in the main worktree. A git failure part-way leaves the branches
    removed before it removed, and the error names the branch that failed.
    The worktree-list failure comes before any branch is touched and names
    only the command."""
    entries = _worktree_entries(repo)
    protected = {_current_branch(repo), entries[0][1] if entries else None}
    wanted = sorted(set(branches))
    for branch in wanted:
        if branch in protected:
            raise DataError(
                f"cleanup: refusing to remove '{branch}': it is checked out in "
                f"the build or main worktree; nothing was removed"
            )
    worktree_of = {branch: path for path, branch in entries if branch}
    existing = _existing_branches(repo)
    removed: list[str] = []
    absent: list[str] = []
    for branch in wanted:
        if branch not in existing:
            absent.append(branch)
            continue
        if branch in worktree_of:
            _git_or_fail(
                repo, branch, "worktree", "remove", "--force", worktree_of[branch]
            )
        _git_or_fail(repo, branch, "branch", "-D", "--", branch)
        removed.append(branch)
    return {"absent": absent, "removed": removed}
