"""progress_guardian.py — Python plan validator for the progress-guardian agent.

Validates plan step completion, commit discipline, and scope creep.

Exit codes:
  0 = pass (all checks clean)
  1 = fail (hard errors: missing commits, uncommitted work, incomplete steps)
  2 = warn (warnings only or LLM check skipped)

Usage:
  python3 scripts/progress_guardian.py --plan <path> [--pre-pr] [--skip-llm]
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).parent))
from lib.review_result import build_result, main_exit, skipped_llm_warning

# ---------------------------------------------------------------------------
# Module constants (REFACTOR: extracted for easy maintenance)
# ---------------------------------------------------------------------------

# Matches: - [x] Step 1.1: Header text  OR  - [ ] Just a header
STEP_PATTERN = re.compile(r"^-\s+\[( |x|X)\]\s+(?:Step\s+[\d.]+:\s+)?(.+)$")

# Matches backtick-quoted paths in plan text (declared file references)
BACKTICK_PATH_RE = re.compile(r"`([^`\s]+\.[a-zA-Z0-9_]+)`")

# Matches a slice's `**Files:** ...` declaration line. Captures the
# remainder of the line so BACKTICK_PATH_RE can extract the paths from it.
SLICE_FILES_RE = re.compile(r"^\*\*Files:\*\*\s*(.+)$")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Step:
    done: bool
    header: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_error(
    message: str,
    file: str = "",
    line: int = 0,
    suggested_fix: str = "",
) -> dict:
    return {
        "severity": "error",
        "confidence": "high",
        "file": file,
        "line": line,
        "message": message,
        "suggestedFix": suggested_fix,
    }


def _make_warning(
    message: str,
    file: str = "",
    line: int = 0,
    suggested_fix: str = "",
) -> dict:
    return {
        "severity": "warning",
        "confidence": "high",
        "file": file,
        "line": line,
        "message": message,
        "suggestedFix": suggested_fix,
    }


def run_git(args: List[str], cwd: str) -> str:
    """Run a git command in cwd, return stdout. Returns '' on failure."""
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        return result.stdout
    except (FileNotFoundError, OSError):
        return ""


# ---------------------------------------------------------------------------
# Core checks
# ---------------------------------------------------------------------------


def parse_plan(path: Path) -> tuple[List[Step], List[dict]]:
    """Parse plan file and return (steps, errors).

    When the plan contains a `## Build Progress` heading, only checkboxes
    between that heading and the next H2 are parsed. This prevents the
    `## Acceptance Criteria` section's checkboxes from being treated as
    Build Progress steps (issue #525). When no `## Build Progress` heading
    is present (legacy/minimal plans), falls back to whole-file scanning.

    Returns an error finding (naming the file) if no checkboxes found.
    """
    text = path.read_text(encoding="utf-8")

    # First, see whether the plan has a `## Build Progress` heading. If it
    # does, narrow the scan to that section only. Otherwise, scan the whole
    # file (preserves backward compatibility with plans that don't carry
    # the section structure).
    lines = text.splitlines()
    has_build_progress = any(
        line.rstrip().startswith("## Build Progress") for line in lines
    )

    steps: List[Step] = []
    in_build_progress = not has_build_progress  # legacy plans: scan everything
    for raw in lines:
        line = raw.rstrip()
        if has_build_progress:
            if line.startswith("## Build Progress"):
                in_build_progress = True
                continue
            # Any other H2 closes the section.
            if in_build_progress and line.startswith("## "):
                in_build_progress = False
                continue
        if not in_build_progress:
            continue
        m = STEP_PATTERN.match(line)
        if m:
            flag, header = m.group(1), m.group(2).strip()
            steps.append(Step(done=(flag.lower() == "x"), header=header))

    if not steps:
        return [], [
            _make_error(
                message=f"No checkbox steps found in plan file: {path.name}",
                file=str(path),
                suggested_fix="Add steps with '- [ ] Step N.M: description' format.",
            )
        ]
    return steps, []


def _parse_slice_files(plan_text: str, slice_header: str) -> List[str]:
    """Return backtick-quoted paths from the `**Files:**` line that follows
    the slice declaring `slice_header`. Empty list when not found.

    The slice block is the run of lines starting at the heading whose text
    contains `slice_header` (after the STEP_PATTERN match strips the
    `- [x] Step N.M: ` prefix), and ending at the next blank line followed
    by another `- [` checkbox, or at the next `## ` H2. We scan forward
    looking for a `**Files:**` line within that block.
    """
    lines = plan_text.splitlines()
    in_block = False
    for raw in lines:
        line = raw.rstrip()
        # Start the block when we see the checkbox line whose header matches.
        m = STEP_PATTERN.match(line)
        if m:
            header = m.group(2).strip()
            if header == slice_header:
                in_block = True
                continue
            if in_block:
                # A different checkbox closes the block.
                break
        if not in_block:
            continue
        # Within the block: stop at next H2.
        if line.startswith("## "):
            break
        # Look for the **Files:** line.
        fm = SLICE_FILES_RE.match(line)
        if fm:
            return BACKTICK_PATH_RE.findall(fm.group(1))
    return []


def _branch_base_sha(repo_root: str) -> Optional[str]:
    """Resolve the branch base SHA (the merge-base with trunk).

    Prefers remote tracking refs over local refs — local main lags
    origin/main the moment any work begins. Returns None when no
    trunk-like ref resolves to a divergence point; callers should
    treat None as "no meaningful branch base — use whole history."
    See issue #525.
    """
    head_sha = run_git(["rev-parse", "HEAD"], repo_root).strip()
    for branch in ("origin/main", "origin/master", "main", "master"):
        out = run_git(["merge-base", "HEAD", branch], repo_root).strip()
        if out and out != head_sha:
            return out
    return None


def check_commit_discipline(
    steps: List[Step], repo_root: str, plan_text: str = ""
) -> List[dict]:
    """For each done step, verify a matching commit exists on this branch.

    Two strategies, tried in order per step:
      1. **File-path match (preferred).** When the slice declares
         `**Files:** ...`, pass when any commit since the branch base
         touched one of the declared files. This decouples the gate
         from commit-subject wording so Conventional Commits work.
      2. **Substring fallback.** When the slice has no `**Files:**`
         line (legacy plans), pass when any commit subject since the
         branch base contains the slice header. Same matcher as before,
         but scoped to `<base>..HEAD` so both strategies see the same
         commit range (cannot diverge — see issue #525).

    Returns error findings for any done step with no matching commit.
    """
    done_steps = [s for s in steps if s.done]
    if not done_steps:
        return []

    base_sha = _branch_base_sha(repo_root)

    # Build the commit range. When no base resolves (orphan HEAD), fall
    # back to whole-history matching so legacy behavior is preserved.
    if base_sha:
        range_arg = f"{base_sha}..HEAD"
        log_subjects_out = run_git(
            ["log", "--no-merges", "--format=%s", range_arg], repo_root
        )
    else:
        range_arg = "HEAD"
        log_subjects_out = run_git(
            ["log", "--no-merges", "--format=%s", "HEAD"], repo_root
        )
    if not log_subjects_out.strip():
        # Zero commits on this branch — emit a warning, not a hard error.
        return [
            _make_warning(
                message="No commits found on this branch — cannot verify commit discipline.",
                suggested_fix="Commit work before marking steps done.",
            )
        ]
    commit_subjects = [
        s.lower() for s in log_subjects_out.strip().splitlines() if s.strip()
    ]

    # Collect file paths touched by commits in the range (file-path path).
    if base_sha:
        diff_out = run_git(["diff", "--name-only", range_arg], repo_root)
    else:
        diff_out = run_git(
            ["log", "--name-only", "--pretty=format:", "HEAD"], repo_root
        )
    branch_files = {p for p in diff_out.strip().splitlines() if p.strip()}

    errors: List[dict] = []
    for step in done_steps:
        declared = _parse_slice_files(plan_text, step.header) if plan_text else []
        if declared:
            # File-path path: pass when any declared path was touched on this branch.
            if any(p in branch_files for p in declared):
                continue
            errors.append(
                _make_error(
                    message=(
                        f"Done step '{step.header}' has no matching commit in git log. "
                        f"Expected a commit on this branch that touched one of: "
                        f"{', '.join(declared)}"
                    ),
                    suggested_fix=(
                        f"Commit your work touching one of the declared files "
                        f"({', '.join(declared)}) before marking '{step.header}' done."
                    ),
                )
            )
            continue
        # Substring fallback: no `**Files:**` declared.
        header_lower = step.header.lower()
        if not any(header_lower in subject for subject in commit_subjects):
            errors.append(
                _make_error(
                    message=(
                        f"Done step '{step.header}' has no matching commit in git log. "
                        f"Expected a commit whose subject contains: '{step.header}'"
                    ),
                    suggested_fix=(
                        f"Commit your work with a message containing '{step.header}' "
                        f"before marking this step done."
                    ),
                )
            )
    return errors


def check_uncommitted(
    repo_root: str, exclude_paths: Optional[List[str]] = None
) -> List[dict]:
    """Check for staged or unstaged changes. Returns an error if any exist.

    exclude_paths: relative or absolute paths to ignore (e.g. the plan file itself).
    """
    status_output = run_git(["status", "--porcelain"], repo_root)
    if not status_output.strip():
        return []

    # Filter out excluded paths
    excluded = set(exclude_paths or [])
    non_excluded_lines = []
    for line in status_output.strip().splitlines():
        if not line.strip():
            continue
        parts = line.strip().split(None, 1)
        file_path = parts[1].strip() if len(parts) == 2 else ""
        # Normalize: check both basename and full relative path
        if file_path and file_path not in excluded:
            import os

            basename = os.path.basename(file_path)
            if basename not in excluded:
                non_excluded_lines.append(line)

    if non_excluded_lines:
        return [
            _make_error(
                message=(
                    "Uncommitted changes detected. All work must be committed "
                    "before plan steps can be considered complete."
                ),
                suggested_fix="Run 'git add' and 'git commit' to commit outstanding work.",
            )
        ]
    return []


def check_pre_pr(steps: List[Step]) -> List[dict]:
    """Assert all steps are done (checked). Returns error for each undone step."""
    errors: List[dict] = []
    for step in steps:
        if not step.done:
            errors.append(
                _make_error(
                    message=(
                        f"Pre-PR gate: step '{step.header}' is not done ([ ] unchecked). "
                        f"All plan steps must be complete before opening a PR."
                    ),
                    suggested_fix=f"Complete and commit work for '{step.header}', then mark it [x].",
                )
            )
    return errors


def check_scope(plan_path: Path, repo_root: str, skip_llm: bool) -> List[dict]:
    """Detect files in the branch diff that aren't declared in the plan.

    Declared paths are backtick-quoted filenames in the plan text.
    Compares all files touched in commits since the branch diverged from its
    base (merge-base with HEAD~N or the root commit) plus any uncommitted files.

    With --skip-llm: adds llm-skipped warning instead of calling LLM.
    LLM unavailability always produces a warning, never an error.
    """
    text = plan_path.read_text(encoding="utf-8")
    declared_paths = set(BACKTICK_PATH_RE.findall(text))

    # Single source of truth for base-ref resolution — shared with
    # check_commit_discipline so the two checks cannot drift on what
    # counts as "trunk" (see issue #525). When no meaningful divergence
    # point exists (no remote, no local trunk), fall back to the root
    # commit so check_scope can still flag every file touched in the repo.
    base_ref = _branch_base_sha(repo_root)
    if not base_ref:
        base_ref = run_git(["rev-list", "--max-parents=0", "HEAD"], repo_root).strip()

    # Collect files changed in commits since base_ref
    if base_ref:
        diff_output = run_git(["diff", "--name-only", base_ref + "..HEAD"], repo_root)
    else:
        diff_output = ""
    changed_files = (
        set(diff_output.strip().splitlines()) if diff_output.strip() else set()
    )

    # Also collect uncommitted files from status
    status_output = run_git(["status", "--porcelain"], repo_root)
    for line in status_output.strip().splitlines():
        if line.strip():
            # porcelain format: XY <path>
            parts = line.strip().split(None, 1)
            if len(parts) == 2:
                changed_files.add(parts[1].strip())

    # Exclude the plan file itself from scope check
    plan_name = plan_path.name
    plan_rel = str(plan_path)
    changed_files = {
        f
        for f in changed_files
        if f != plan_name and f != plan_rel and not f.endswith(plan_name)
    }

    if not changed_files:
        return []

    # If no declared paths, any changed file is potentially out-of-plan
    out_of_plan = (
        changed_files if not declared_paths else (changed_files - declared_paths)
    )

    if not out_of_plan:
        return []

    # We have out-of-plan files — check with LLM or emit skipped warning
    if skip_llm:
        return [
            skipped_llm_warning(
                message=(
                    f"LLM check skipped (--skip-llm): {len(out_of_plan)} file(s) not declared "
                    f"in plan may represent scope creep — manual review required."
                )
            )
        ]

    # Call LLM for scope assessment
    file_list = ", ".join(sorted(out_of_plan))
    prompt = (
        f"These files were changed but are not declared in the plan '{plan_path.name}': "
        f"{file_list}. "
        f"Is this likely scope creep or acceptable collateral changes? "
        f'Reply with a brief JSON assessment: {{"scope_creep": true/false, "reason": "..."}}.'
    )
    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return [
                _make_warning(
                    message=(
                        f"LLM scope check unavailable: {len(out_of_plan)} file(s) not in plan "
                        f"({file_list}) — manual scope review recommended."
                    ),
                )
            ]
        return [
            _make_warning(
                message=(
                    f"Scope check (LLM): {len(out_of_plan)} out-of-plan file(s): "
                    f"{file_list}. LLM assessment: {result.stdout.strip()[:300]}"
                ),
            )
        ]
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return [
            _make_warning(
                message=(
                    f"LLM scope check unavailable (claude not on PATH or timed out): "
                    f"{len(out_of_plan)} file(s) not declared in plan — manual review needed."
                ),
            )
        ]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate plan step completion and commit discipline."
    )
    parser.add_argument("--plan", required=True, help="Path to the plan markdown file.")
    parser.add_argument(
        "--pre-pr",
        action="store_true",
        help="Assert all plan steps are complete (pre-PR gate).",
    )
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="Skip LLM scope check and emit a warning finding instead.",
    )
    args = parser.parse_args(argv)

    plan_path = Path(args.plan).resolve()
    if not plan_path.exists():
        result = build_result(
            errors=[_make_error(f"Plan file not found: {args.plan}", file=args.plan)],
            warnings=[],
        )
        return main_exit(result)

    # Resolve the git repo root from the plan file's directory.
    # Falls back to the plan file's parent if not in a git repo.
    repo_root_output = run_git(
        ["rev-parse", "--show-toplevel"], str(plan_path.parent)
    ).strip()
    repo_root = repo_root_output if repo_root_output else str(plan_path.parent)

    errors: List[dict] = []
    warnings: List[dict] = []

    # 1. Parse plan checkboxes
    steps, parse_errors = parse_plan(plan_path)
    errors.extend(parse_errors)

    # Pre-read the plan text once so check_commit_discipline can locate
    # per-slice `**Files:**` declarations (file-path matcher path).
    plan_text = plan_path.read_text(encoding="utf-8")
    if not parse_errors:
        # 2. Uncommitted change check (always runs; ignore the plan file itself)
        uncommitted_issues = check_uncommitted(
            repo_root, exclude_paths=[plan_path.name]
        )
        errors.extend(uncommitted_issues)

        # 3. Commit discipline (runs regardless of uncommitted state — both issues matter)
        commit_issues = check_commit_discipline(steps, repo_root, plan_text)
        for issue in commit_issues:
            if issue["severity"] == "error":
                errors.append(issue)
            else:
                warnings.append(issue)

        # 4. Scope creep check (only when tree is clean — avoids double-counting uncommitted)
        if not uncommitted_issues:
            scope_issues = check_scope(plan_path, repo_root, args.skip_llm)
            for issue in scope_issues:
                if issue["severity"] == "error":
                    errors.append(issue)
                else:
                    warnings.append(issue)

        # 5. Pre-PR gate (runs regardless of uncommitted state)
        if args.pre_pr:
            pre_pr_issues = check_pre_pr(steps)
            errors.extend(pre_pr_issues)

    result = build_result(errors, warnings)
    return main_exit(result)


if __name__ == "__main__":
    sys.exit(main())
