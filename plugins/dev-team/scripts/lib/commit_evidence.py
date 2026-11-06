"""commit_evidence — the git evidence rule for "a ticked item has a commit".

A leaf module: stdlib only. It owns what `progress_guardian.py` and
`feature_record.py` both need, so there is one definition of "declared files"
and of "backed":

- `run_git`, `branch_base_sha` (None when no trunk ref diverges from HEAD)
- `extract_declared_paths`, `is_path_declared`, `parse_slice_files`
- `commits_since` (subjects and touched files past a base)
- `checked_commits_since` (the same, or None when git failed)
- `item_backed` (the per-item rule)

Policy stays with the callers. The guardian falls back to whole history when
there is no base and warns on zero commits; the feature record reports those
cases as unverifiable. This module only answers the questions.
"""

from __future__ import annotations

import fnmatch
import re
import subprocess

# Matches: - [x] Step 1.1: Header text  OR  - [ ] Just a header
# The checkbox start (group `state`) is the same grammar as
# `examination_inputs.CHECKBOX_PATTERN_PREFIX`; a test pins that they agree.
STEP_PATTERN = re.compile(r"^-\s+\[(?P<state>[ xX])\]\s+(?:Step\s+[\d.]+:\s+)?(.+)$")

# Matches backtick-quoted paths in plan text (declared file references)
BACKTICK_PATH_RE = re.compile(r"`([^`\s]+\.[a-zA-Z0-9_]+)`")

# Matches backtick-quoted directory declarations (trailing '/'), e.g.
# `plugins/dev-team/skills/new-feature/`. Kept separate from
# BACKTICK_PATH_RE so extension-less, non-path backtick tokens (e.g.
# `runHook()`, `SomeClass`) are never mistaken for declared paths.
BACKTICK_DIR_RE = re.compile(r"`([^`\s]+/)`")

# Matches a slice's `**Files:** ...` declaration line. Captures the
# remainder of the line so BACKTICK_PATH_RE/BACKTICK_DIR_RE can extract
# the paths from it.
SLICE_FILES_RE = re.compile(r"^\*\*Files:\*\*\s*(.+)$")


def run_git(args: list[str], cwd: str) -> str:
    """Run a git command in cwd, return stdout. Returns '' on failure."""
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            cwd=cwd,
            check=False,
        )
        return result.stdout
    except (FileNotFoundError, OSError):
        return ""


def extract_declared_paths(text: str) -> list[str]:
    """Return backtick-quoted file paths and directory paths declared in
    text: exact file paths (ending in a dot-extension) plus directory
    declarations (ending in '/'). A directory declaration means "this
    slice touches things under here" — matched with startswith, not
    equality, by callers. Bare backtick-quoted tokens with no extension
    and no trailing slash (e.g. `` `runHook()` ``) are not paths and are
    intentionally excluded.
    """
    return BACKTICK_PATH_RE.findall(text) + BACKTICK_DIR_RE.findall(text)


def is_path_declared(file_path: str, declared_paths) -> bool:
    """True if file_path exactly matches a declared file, falls under
    a declared directory (trailing '/') prefix, or matches a declared glob
    pattern (fnmatch, stdlib, e.g. `src/auth/**`). Single source of truth
    shared by the commit-discipline, scope and declared-scope checks so they
    cannot drift on what counts as "declared".
    """
    for declared in declared_paths:
        if declared.endswith("/"):
            if file_path.startswith(declared):
                return True
        elif (
            file_path == declared
            or any(ch in declared for ch in "*?[")
            and fnmatch.fnmatch(file_path, declared)
        ):
            return True
    return False


def parse_slice_files(plan_text: str, slice_header: str) -> list[str]:
    """Return backtick-quoted paths from the `**Files:**` line declared
    under the slice identified by `slice_header`. Empty list when not found.

    Two layouts are supported:
      1. **Heading-anchored** (the /plan skill convention): the slice is
         declared with `### Slice N: title` and `**Files:** ...` lives in
         that section's body. Build Progress checkboxes mirror the heading
         text — we match the heading and scan forward.
      2. **Inline** (minimal plans): `- [x] Slice N: title` followed by a
         `**Files:** ...` line in the same checkbox block. Scan forward
         from the checkbox until another checkbox or a heading.

    Heading-anchored is tried first because real plans always use it. The
    inline form preserves a smaller fixture surface for tests and the
    minimal plans the existing fixtures construct.
    """
    lines = plan_text.splitlines()

    # Try heading-anchored layout first.
    in_block = False
    for raw in lines:
        line = raw.rstrip()
        if line.startswith("### ") and line[4:].strip() == slice_header:
            in_block = True
            continue
        if not in_block:
            continue
        if line.startswith(("## ", "### ")):
            break
        fm = SLICE_FILES_RE.match(line)
        if fm:
            return extract_declared_paths(fm.group(1))

    # Fall back to inline layout: `**Files:**` line near a `- [x] <header>`.
    in_block = False
    for raw in lines:
        line = raw.rstrip()
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
        if line.startswith(("## ", "### ")):
            break
        fm = SLICE_FILES_RE.match(line)
        if fm:
            return extract_declared_paths(fm.group(1))
    return []


def branch_base_sha(repo_root: str) -> str | None:
    """Resolve the branch base SHA (the merge-base with trunk).

    Prefers remote tracking refs over local refs — local main lags
    origin/main the moment any work begins. Returns None when no
    trunk-like ref resolves to a divergence point (no repository, no git,
    an orphan or detached HEAD with no trunk ref, a git error); callers
    choose their own policy for None.
    """
    head_sha = run_git(["rev-parse", "HEAD"], repo_root).strip()
    for branch in ("origin/main", "origin/master", "main", "master"):
        out = run_git(["merge-base", "HEAD", branch], repo_root).strip()
        if out and out != head_sha:
            return out
    return None


def _git_succeeds(args: list[str], cwd: str) -> tuple[str, bool]:
    """Return `(stdout, succeeded)`. Unlike `run_git`, a non-zero exit, a
    missing git or a missing directory is reported, not folded into ''."""
    try:
        result = subprocess.run(
            ["git"] + args, capture_output=True, text=True, cwd=cwd, check=False
        )
    except (FileNotFoundError, OSError):
        return "", False
    return result.stdout, result.returncode == 0


def _range_commits(repo_root: str, base_sha: str) -> tuple[list[str], set[str], bool]:
    range_arg = f"{base_sha}..HEAD"
    subjects_out, log_ok = _git_succeeds(
        ["log", "--no-merges", "--format=%s", range_arg], repo_root
    )
    subjects = [s.lower() for s in subjects_out.strip().splitlines() if s.strip()]
    if not subjects:
        return [], set(), log_ok
    diff_out, diff_ok = _git_succeeds(["diff", "--name-only", range_arg], repo_root)
    files = {p for p in diff_out.strip().splitlines() if p.strip()}
    return subjects, files, log_ok and diff_ok


def commits_since(repo_root: str, base_sha: str) -> tuple[list[str], set[str]]:
    """Return `(subjects, files)` for the commits in `<base_sha>..HEAD`.

    `subjects` are lower-cased, non-blank, merges excluded. `files` is the
    set of paths the range touches. Both are empty when git fails or the
    range holds no commit; use `checked_commits_since` to tell the two
    apart. The whole-history view (no base) is the guardian's own fallback
    and is not offered here.
    """
    subjects, files, _ok = _range_commits(repo_root, base_sha)
    return subjects, files


def checked_commits_since(
    repo_root: str, base_sha: str
) -> tuple[list[str], set[str]] | None:
    """`commits_since`, or None when either git command failed, so a partial
    answer (subjects without the files they touched) is never used as evidence."""
    subjects, files, ok = _range_commits(repo_root, base_sha)
    return (subjects, files) if ok else None


def item_backed(
    header: str, plan_text: str, subjects: list[str], files: set[str]
) -> bool:
    """True when a commit backs the Build Progress item `header`.

    Two strategies, tried in order:
      1. **File-path match (preferred).** When the item's slice declares
         `**Files:** ...`, backed when any file in `files` is declared.
         This decouples the gate from commit-subject wording so
         Conventional Commits work.
      2. **Substring fallback.** With no `**Files:**` declared (legacy
         plans), backed when any lower-cased subject in `subjects`
         contains the header.
    """
    declared = parse_slice_files(plan_text, header) if plan_text else []
    if declared:
        return any(is_path_declared(f, declared) for f in files)
    header_lower = header.lower()
    return any(header_lower in subject for subject in subjects)
