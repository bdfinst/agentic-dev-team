"""progress_guardian.py — Python plan validator for the progress-guardian agent.

Validates plan step completion, commit discipline, and scope creep.

Exit codes:
  0 = pass (all checks clean)
  1 = fail (hard errors: missing commits, uncommitted work, incomplete steps)
  2 = warn (warnings only or LLM check skipped)

Usage:
  python3 ${CLAUDE_PLUGIN_ROOT}/scripts/progress_guardian.py --plan <path> [--pre-pr] [--skip-llm]
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib.review_result import build_result, main_exit, make_issue, skipped_llm_warning

# ---------------------------------------------------------------------------
# Module constants (REFACTOR: extracted for easy maintenance)
# ---------------------------------------------------------------------------

# Matches: - [x] Step 1.1: Header text  OR  - [ ] Just a header
STEP_PATTERN = re.compile(r"^-\s+\[( |x|X)\]\s+(?:Step\s+[\d.]+:\s+)?(.+)$")

# Matches backtick-quoted paths in plan text (declared file references)
BACKTICK_PATH_RE = re.compile(r"`([^`\s]+\.[a-zA-Z0-9_]+)`")

# Matches backtick-quoted directory declarations (trailing '/'), e.g.
# `plugins/dev-team/skills/new-feature/`. Kept separate from
# BACKTICK_PATH_RE so extension-less, non-path backtick tokens (e.g.
# `runHook()`, `SomeClass`) are never mistaken for declared paths — see
# issue #713.
BACKTICK_DIR_RE = re.compile(r"`([^`\s]+/)`")

# Matches a slice's `**Files:** ...` declaration line. Captures the
# remainder of the line so BACKTICK_PATH_RE/BACKTICK_DIR_RE can extract
# the paths from it.
SLICE_FILES_RE = re.compile(r"^\*\*Files:\*\*\s*(.+)$")


def _extract_declared_paths(text: str) -> list[str]:
    """Return backtick-quoted file paths and directory paths declared in
    text: exact file paths (ending in a dot-extension) plus directory
    declarations (ending in '/'). A directory declaration means "this
    slice touches things under here" — matched with startswith, not
    equality, by callers. Bare backtick-quoted tokens with no extension
    and no trailing slash (e.g. `` `runHook()` ``) are not paths and are
    intentionally excluded (see issue #713).
    """
    return BACKTICK_PATH_RE.findall(text) + BACKTICK_DIR_RE.findall(text)


def _is_path_declared(file_path: str, declared_paths) -> bool:
    """True if file_path exactly matches a declared file, falls under
    a declared directory (trailing '/') prefix, or matches a declared glob
    pattern (fnmatch, stdlib — issue #865 AC9, e.g. `src/auth/**`). Single
    source of truth shared by check_commit_discipline, check_scope, and
    check_declared_scope_adherence so these checks cannot drift on what
    counts as "declared" (see issue #525/#713/#865).
    """
    for declared in declared_paths:
        if declared.endswith("/"):
            if file_path.startswith(declared):
                return True
        elif file_path == declared or any(ch in declared for ch in "*?[") and fnmatch.fnmatch(
            file_path, declared
        ):
            return True
    return False


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


# ---------------------------------------------------------------------------
# Core checks
# ---------------------------------------------------------------------------


def parse_plan(path: Path) -> tuple[list[Step], list[dict]]:
    """Parse plan file and return (steps, errors).

    Scopes checkbox parsing with two flags when a Build Progress section
    exists (issue #525):

    - `in_build_progress` (outer scope) — when the plan contains a
      `## Build Progress` heading, only lines between that heading and the
      next `## ` H2 are eligible for step parsing. This prevents the
      top-level `## Acceptance Criteria` section's checkboxes from being
      treated as Build Progress steps.
    - `in_acceptance` (inner skip) — within the Build Progress section,
      the `/plan` skill renders a documentation mirror of the top-level
      AC list under a `### Acceptance Criteria` H3 sub-heading. Those
      mirror items lack work-tracking semantics (no `### Slice` heading,
      no `**Files:**` line, no commit subject anchor). They are skipped
      so the pre-PR gate doesn't demand a commit for each one. The
      structural problem behind the workaround is tracked in #526.

    When no `## Build Progress` heading is present (legacy/minimal plans),
    falls back to whole-file scanning — preserves backward compatibility
    with the pre-existing bats fixtures that construct minimal plans.

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

    steps: list[Step] = []
    in_build_progress = not has_build_progress  # legacy plans: scan everything
    in_acceptance = False
    for raw in lines:
        line = raw.rstrip()
        if has_build_progress:
            if line.startswith("## Build Progress"):
                in_build_progress = True
                in_acceptance = False
                continue
            # Any other H2 closes the section.
            if in_build_progress and line.startswith("## "):
                in_build_progress = False
                continue
            # The `### Acceptance Criteria` subheading inside Build Progress
            # is a documentation mirror — the same items appear in the
            # top-level `## Acceptance Criteria`. Skip its checkboxes so
            # they don't demand commits of their own. The structural
            # redesign of where ACs live is tracked in #526; this PR
            # ships the workaround so the gate stops false-positiving.
            if in_build_progress and line.startswith("### Acceptance Criteria"):
                in_acceptance = True
                continue
            # Any other H3 within Build Progress exits the AC subsection.
            if in_acceptance and line.startswith("### "):
                in_acceptance = False
        if not in_build_progress or in_acceptance:
            continue
        m = STEP_PATTERN.match(line)
        if m:
            flag, header = m.group(1), m.group(2).strip()
            steps.append(Step(done=(flag.lower() == "x"), header=header))

    if not steps:
        return [], [
            make_issue(
                "error",
                message=f"No checkbox steps found in plan file: {path.name}",
                file=str(path),
                suggested_fix="Add steps with '- [ ] Step N.M: description' format.",
            )
        ]
    return steps, []


def _parse_slice_files(plan_text: str, slice_header: str) -> list[str]:
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
    minimal plans the existing bats fixtures construct.
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
            return _extract_declared_paths(fm.group(1))

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
            return _extract_declared_paths(fm.group(1))
    return []


def _branch_base_sha(repo_root: str) -> str | None:
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
    steps: list[Step], repo_root: str, plan_text: str = ""
) -> list[dict]:
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
            make_issue(
                "warning",
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

    errors: list[dict] = []
    for step in done_steps:
        declared = _parse_slice_files(plan_text, step.header) if plan_text else []
        if declared:
            # File-path path: pass when any declared file was touched on
            # this branch, or any branch file falls under a declared
            # directory (see issue #713).
            if any(_is_path_declared(bf, declared) for bf in branch_files):
                continue
            errors.append(
                make_issue(
                    "error",
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
                make_issue(
                    "error",
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
    repo_root: str, exclude_paths: list[str] | None = None
) -> list[dict]:
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
            make_issue(
                "error",
                message=(
                    "Uncommitted changes detected. All work must be committed "
                    "before plan steps can be considered complete."
                ),
                suggested_fix="Run 'git add' and 'git commit' to commit outstanding work.",
            )
        ]
    return []


def check_pre_pr(steps: list[Step]) -> list[dict]:
    """Assert all steps are done (checked). Returns error for each undone step."""
    errors: list[dict] = []
    for step in steps:
        if not step.done:
            errors.append(
                make_issue(
                    "error",
                    message=(
                        f"Pre-PR gate: step '{step.header}' is not done ([ ] unchecked). "
                        f"All plan steps must be complete before opening a PR."
                    ),
                    suggested_fix=f"Complete and commit work for '{step.header}', then mark it [x].",
                )
            )
    return errors


VERIFY_LOG_PATH = "metrics/verify-log.jsonl"

# Test-file indicators — kept in sync with knowledge/test-file-indicators.md
# so this Python check and the /build skill's prose classification agree on
# what counts as "a test" (see issue #727).
_TEST_NAME_RE = re.compile(r"\.(test|spec)\.[^./]+$")
_TEST_DIR_FRAGMENTS = ("__tests__/",)
_STEP_DEFINITION_RE = re.compile(
    r"(\.steps\.[^./]+$|StepDefinitions\.[^./]+$|Steps\.[^./]+$)", re.IGNORECASE
)
_TEST_CLASS_NAME_RE = re.compile(r"(Test|Tests|TestCase|Spec)\.java$")
_TEST_ATTRIBUTE_RE = re.compile(
    r"\[Fact\]|\[Theory\]|\[TestCase\]|\[TestMethod\]|\[TestClass\]|"
    r"(?<!Parameterized)(?<!Factory)\[Test\]|@Test\b|@ParameterizedTest|@TestFactory"
)

# Docs/config files never carry a runtime surface — no source ever executes
# from them, so a diff touching only these (plus tests) has nothing for
# /verify to drive.
_DOC_CONFIG_SUFFIXES = {
    ".md",
    ".mdx",
    ".txt",
    ".rst",
    ".adoc",
    ".yml",
    ".yaml",
    ".toml",
    ".ini",
    ".cfg",
    ".editorconfig",
}
_DOC_CONFIG_BASENAMES = {
    "LICENSE",
    "LICENSE.txt",
    ".gitignore",
    ".gitattributes",
    "CODEOWNERS",
}


def _is_test_file(path: str, repo_root: str) -> bool:
    """True when `path` looks like a test per knowledge/test-file-indicators.md."""
    if path.endswith(".feature"):
        return True
    if _TEST_NAME_RE.search(path):
        return True
    if any(frag in path for frag in _TEST_DIR_FRAGMENTS):
        return True
    if _STEP_DEFINITION_RE.search(path):
        return True
    if _TEST_CLASS_NAME_RE.search(path):
        return True
    suffix = Path(path).suffix.lower()
    if suffix in (".cs", ".java"):
        # Attribute-based test detection needs the file's content — best
        # effort only, and only when the file still exists on disk.
        try:
            content = (Path(repo_root) / path).read_text(
                encoding="utf-8", errors="replace"
            )
        except OSError:
            return False
        if _TEST_ATTRIBUTE_RE.search(content):
            return True
    return False


def _is_doc_or_config_file(path: str) -> bool:
    if path.startswith("metrics/") and path.endswith(".jsonl"):
        return True
    if Path(path).name in _DOC_CONFIG_BASENAMES:
        return True
    return Path(path).suffix.lower() in _DOC_CONFIG_SUFFIXES


def has_runtime_surface(changed_files: list[str], repo_root: str) -> bool:
    """True when at least one changed file is neither a test file nor a
    docs/config file — i.e. there is something for /verify to exercise.
    """
    return any(
        not _is_test_file(f, repo_root) and not _is_doc_or_config_file(f)
        for f in changed_files
    )


def _collect_branch_changed_files(repo_root: str) -> list[str]:
    """All files changed on this branch: the committed diff since the
    branch base, plus any currently uncommitted (staged/unstaged) files.
    Mirrors check_scope's branch-scope resolution (issue #727).
    """
    base_ref = _branch_base_sha(repo_root)
    if not base_ref:
        base_ref = run_git(["rev-list", "--max-parents=0", "HEAD"], repo_root).strip()

    diff_output = (
        run_git(["diff", "--name-only", base_ref + "..HEAD"], repo_root)
        if base_ref
        else ""
    )
    changed_files = (
        set(diff_output.strip().splitlines()) if diff_output.strip() else set()
    )

    status_output = run_git(["status", "--porcelain"], repo_root)
    for line in status_output.strip().splitlines():
        if line.strip():
            parts = line.strip().split(None, 1)
            if len(parts) == 2:
                changed_files.add(parts[1].strip())

    return sorted(changed_files)


def check_verify_log(repo_root: str, changed_files: list[str]) -> list[dict]:
    """Pre-PR gate (issue #727): if the branch touches any runtime-surface
    file (not exclusively tests/docs/config), require at least one entry
    in metrics/verify-log.jsonl for the current branch — evidence that
    `/verify` ran (or was explicitly skipped with a reason) before the
    slice was marked done. Fails closed, the same way an incomplete step
    or a missing commit does.
    """
    if not changed_files or not has_runtime_surface(changed_files, repo_root):
        return []

    branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"], repo_root).strip()
    log_path = Path(repo_root) / VERIFY_LOG_PATH

    entries: list[dict] = []
    if log_path.exists():
        for raw_line in log_path.read_text(encoding="utf-8").splitlines():
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                entries.append(json.loads(raw_line))
            except ValueError:
                continue

    if any(entry.get("branch") == branch for entry in entries):
        return []

    return [
        make_issue(
            "error",
            message=(
                "Pre-PR gate: this branch touches runtime-surface file(s) but no "
                f"entry in {VERIFY_LOG_PATH} matches branch '{branch}'. `/verify` "
                "(or an explicit skip-with-reason) is required before a PR can be "
                "opened."
            ),
            suggested_fix=(
                "Run /verify against the branch's changed runtime files (or record "
                "a skipped:<reason> entry if the diff genuinely has no runtime "
                f"surface to drive), then append the outcome to {VERIFY_LOG_PATH}."
            ),
        )
    ]


def _all_slice_headers(steps: list[Step]) -> list[str]:
    """Return the subset of Build Progress checkbox headers that are slice
    headers (`"Slice N: <title>"`), not step headers — the shape
    `_parse_slice_files` expects (issue #865 AC8)."""
    return [s.header for s in steps if s.header.startswith("Slice ")]


def check_declared_scope_adherence(
    steps: list[Step], plan_path: Path, repo_root: str, plan_text: str
) -> list[dict]:
    """Issue #865 AC8: compare the branch diff against the union of every
    slice's declared `**Files:**` scope (fnmatch-aware, glob-capable).

    This is a **named WARNING only** — never a pre-PR gate failure. When a
    plan opts into `Scope enforcement: freeze` (see `build_slice_scope.py`),
    freeze itself is the real enforcement mechanism (a blocked Write/Edit);
    this check exists for the *unfrozen* case, where out-of-scope edits are
    otherwise invisible until `/code-review` or a human catches them.

    Deterministic — no LLM call, unlike `check_scope` (which reasons about
    *all* backtick-quoted paths in the plan prose). A plan with no slice
    declaring `**Files:**` has nothing to compare against and returns `[]`.
    """
    declared: list[str] = []
    for header in _all_slice_headers(steps):
        declared.extend(_parse_slice_files(plan_text, header))
    if not declared:
        return []

    changed_files = _collect_branch_changed_files(repo_root)
    plan_name = plan_path.name
    changed_files = [
        f
        for f in changed_files
        if f != plan_name
        and not f.endswith(plan_name)
        and not (f.startswith("metrics/") and f.endswith(".jsonl"))
        and not f.startswith("memory/")
    ]
    if not changed_files:
        return []

    out_of_scope = sorted(f for f in changed_files if not _is_path_declared(f, declared))
    if not out_of_scope:
        return []

    return [
        make_issue(
            "warning",
            message=(
                "Scope adherence: out-of-scope edit(s) without freeze: "
                f"{', '.join(out_of_scope)} not covered by any slice's declared "
                f"Files ({', '.join(sorted(set(declared)))})."
            ),
            suggested_fix=(
                "Reconcile the plan's Files declarations, or engage scope "
                "enforcement (`**Scope enforcement:** freeze`) so out-of-scope "
                "writes are blocked rather than merely warned about."
            ),
            rule_id="declared-scope-warning",
        )
    ]


def check_scope(plan_path: Path, repo_root: str, skip_llm: bool) -> list[dict]:
    """Detect files in the branch diff that aren't declared in the plan.

    Declared paths are backtick-quoted filenames in the plan text.
    Compares all files touched in commits since the branch diverged from its
    base (merge-base with HEAD~N or the root commit) plus any uncommitted files.

    With --skip-llm: adds llm-skipped warning instead of calling LLM.
    LLM unavailability always produces a warning, never an error.
    """
    text = plan_path.read_text(encoding="utf-8")
    declared_paths = set(_extract_declared_paths(text))

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

    # Exclude the plan file itself from scope check, along with append-only
    # metrics artifacts (e.g. review-value.jsonl, verify-log.jsonl) — these
    # are pipeline instrumentation the plan never declares by name, not
    # plan-scoped work product (issue #727).
    plan_name = plan_path.name
    plan_rel = str(plan_path)
    changed_files = {
        f
        for f in changed_files
        if f != plan_name
        and f != plan_rel
        and not f.endswith(plan_name)
        and not (f.startswith("metrics/") and f.endswith(".jsonl"))
    }

    if not changed_files:
        return []

    # If no declared paths, any changed file is potentially out-of-plan.
    # Otherwise a file is "declared" (not out-of-plan) if it exactly
    # matches a declared file or falls under a declared directory prefix
    # (see issue #713).
    out_of_plan = (
        changed_files
        if not declared_paths
        else {f for f in changed_files if not _is_path_declared(f, declared_paths)}
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
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return [
                make_issue(
                    "warning",
                    message=(
                        f"LLM scope check unavailable: {len(out_of_plan)} file(s) not in plan "
                        f"({file_list}) — manual scope review recommended."
                    ),
                )
            ]
        return [
            make_issue(
                "warning",
                message=(
                    f"Scope check (LLM): {len(out_of_plan)} out-of-plan file(s): "
                    f"{file_list}. LLM assessment: {result.stdout.strip()[:300]}"
                ),
            )
        ]
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return [
            make_issue(
                "warning",
                message=(
                    f"LLM scope check unavailable (claude not on PATH or timed out): "
                    f"{len(out_of_plan)} file(s) not declared in plan — manual review needed."
                ),
            )
        ]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
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
            errors=[
                make_issue(
                    "error",
                    message=f"Plan file not found: {args.plan}",
                    file=args.plan,
                )
            ],
            warnings=[],
        )
        return main_exit(result)

    # Resolve the git repo root from the plan file's directory.
    # Falls back to the plan file's parent if not in a git repo.
    repo_root_output = run_git(
        ["rev-parse", "--show-toplevel"], str(plan_path.parent)
    ).strip()
    repo_root = repo_root_output if repo_root_output else str(plan_path.parent)

    errors: list[dict] = []
    warnings: list[dict] = []

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

            # 6. Verify-log gate (issue #727): runtime-surface changes need
            # evidence /verify ran before the PR can be opened.
            verify_changed_files = _collect_branch_changed_files(repo_root)
            verify_issues = check_verify_log(repo_root, verify_changed_files)
            errors.extend(verify_issues)

            # 7. Declared-scope adherence (issue #865 AC8): named warning
            # only, never a gate failure — freeze (when engaged) is the
            # real enforcement mechanism.
            warnings.extend(
                check_declared_scope_adherence(
                    steps, plan_path, repo_root, plan_text
                )
            )

    result = build_result(errors, warnings)
    return main_exit(result)


if __name__ == "__main__":
    sys.exit(main())
