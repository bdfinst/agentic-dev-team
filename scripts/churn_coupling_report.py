#!/usr/bin/env python3
"""churn_coupling_report.py -- rank high-churn test files by how often they
change WITHOUT their subject changing (issue #2004, part of epic #1999).

## Why this exists

Session-report data across 78 projects showed test files are the largest edit
category (4,528 of 13,196 file mutations, 34%), and the distribution says
rework rather than authoring: 277 files edited >=10 times, 96 edited >=20
times, the top 12% of paths absorbing 50% of all edits.

A test file edited 89 times in a month is either testing something genuinely
volatile or is coupled to implementation detail. Those two have opposite
remedies, and edit count alone cannot tell them apart.

## The discriminator, and why it is a script and not an agent

For each high-churn test file: how often does it change **in the same commit
as its subject** versus **independently**?

- Test changes *with* its subject -> the behavior moved and the test moved.
  Normal TDD. Healthy.
- Test changes *without* its subject -> the test is tracking something other
  than behavior. That is the implementation-coupling smell.

That question is `git log` plus a test->subject path mapping: reproducible,
rerunnable next month, and falsifiable -- which a model's judgment over 20
files is not. Per this repo's CLAUDE.md, a model's answer to a mechanical
question is a guess that looks like a result, and it fails silently in the
confident direction. So this is a deterministic script; deciding what to *do*
about a flagged file is deliberately out of scope and left to a human or a
lens. That division is the point.

## Shallow clones are refused, not approximated

Churn counts read off a shallow clone measure clone depth, not history: a
59-commit checkout of a 2,000-commit repo yields numbers that look like a
result and are an artifact. `main()` refuses to run on a shallow repository
with a named reason (`shallow-clone`) and a remedy, rather than reporting a
confidently wrong ranking. The same reasoning applies to `--max-commits`: when
the cap truncates the window the report says so (`truncated`), because a
truncated window has the same failure mode.

## Mapping misses are reported, never silently scored

A test file whose subject cannot be located is NOT scored zero-co-change (which
would rank it as maximally coupled -- exactly backwards). It is reported in a
separate `unmapped` section together with the candidate paths that were tried,
so a convention this script does not know about shows up as a gap in the
mapping rather than as a false finding.

The same section absorbs the one false-positive class this classifier has: a
PRODUCTION file that happens to match a test naming convention -- this repo's
own `plugins/dev-team/scripts/test_improve_resume.py` is the `/test-improve`
skill's resume module, not a test. Classification is filename-driven (a
`tests/` directory also holds fixtures, helpers, and conftest files, so the
directory is the weaker signal), so such a file is picked up as a test, finds
no subject, and lands in `unmapped` -- visible and unscored, which is the
intended failure mode rather than a phantom row at 100% solo.

## Relation to the co-evolution-audit skill

`plugins/dev-team/skills/co-evolution-audit/` asks the mirror-image question --
which PRODUCTION files churn while their tests stay still (stale coverage). This
script asks which TEST files churn while their subject stays still (coupling to
implementation detail). Same git data, opposite direction, and the two rank
disjoint sets of files. This one is a script rather than a skill because its
question has a mechanical answer.

## Known limits

- Rename detection is git's default for `--name-only`: a renamed file reports
  only its new path, so a test renamed mid-window has its history split across
  two rows. Both halves are still real edits; neither is inflated.
- `--max-commits` reports `truncated` conservatively -- a window whose commit
  count exactly equals the cap is flagged, since the script cannot tell a cap
  that just fit from one that cut.

## Ranking

Rows are ranked by the issue's rule, "solo-edit ratio x volume". With volume
taken as the file's own total edit count that product reduces exactly to the
solo-edit count (`solo/total * total == solo`), so `score` is computed as the
integer solo-edit count -- same ordering, no float noise in ties. The ratio is
still reported per row and is the first tie-breaker, so a file that is 100%
solo ranks above an equally-solo-count file that is only 50% solo.

## Usage

    scripts/churn_coupling_report.py [--repo PATH] [--since DAYS]
        [--max-commits N] [--min-edits N] [--top N] [--exclude GLOB] [--json]

Exit codes: 0 on a completed report (including an empty one), 2 on a refusal
(not a git repository, shallow clone, no commits in the window).
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

DEFAULT_SINCE_DAYS = 90
DEFAULT_MIN_EDITS = 5
DEFAULT_TOP = 25

#: Generated, vendored, or build-output paths whose churn is not hand-authored
#: and would inflate both the ranking and the subject universe.
DEFAULT_EXCLUDES = (
    "node_modules/*",
    "*/node_modules/*",
    "vendor/*",
    "*/vendor/*",
    "dist/*",
    "*/dist/*",
    "build/*",
    "*/build/*",
    "coverage/*",
    "*/coverage/*",
    "graphify-out/*",
    "*.min.js",
    "*.lock",
    "*.snap",
)

#: Directory names that mark a test tree. Used to derive the subject directory
#: by removing or rewriting the segment.
_TEST_DIR_SEGMENTS = frozenset(
    {"test", "tests", "__tests__", "__test__", "spec", "specs", "testing"}
)

#: What a test directory segment may be replaced with when looking for the
#: subject tree. "main" covers Java's src/test/java -> src/main/java.
_SUBJECT_DIR_REPLACEMENTS = ("src", "lib", "app", "source", "main")

#: A C#/.NET sibling test project: Foo.Tests/ -> Foo/.
_DOTNET_TEST_PROJECT_RE = re.compile(r"^(?P<base>.+)\.(Tests?|Specs?)$")

#: Source extensions a JS/TS `foo.spec.ts` may be testing, beyond its own.
_JS_SUBJECT_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte")

_JS_TEST_RE = re.compile(
    r"^(?P<stem>.+)\.(?:test|spec)(?P<ext>\.[A-Za-z0-9]+)$",
)
_PY_TEST_PREFIX_RE = re.compile(r"^test_(?P<stem>.+)\.py$")
_PY_TEST_SUFFIX_RE = re.compile(r"^(?P<stem>.+)_test\.py$")
_GO_TEST_RE = re.compile(r"^(?P<stem>.+)_test\.go$")
_JVM_TEST_RE = re.compile(r"^(?P<stem>.+?)(?:Test|Tests|Spec|Specs|IT)\.java$")
_JVM_TEST_PREFIX_RE = re.compile(r"^Test(?P<stem>.+)\.java$")
_DOTNET_TEST_RE = re.compile(r"^(?P<stem>.+?)(?:Test|Tests|Spec|Specs)\.cs$")


class Refusal(Exception):
    """Raised when the input cannot support a trustworthy number.

    Carries a machine-readable `reason` so the refusal is named rather than
    just printed -- the acceptance criterion is that the script says *why*.
    """

    def __init__(self, reason: str, detail: str, remedy: str = "") -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail
        self.remedy = remedy


@dataclass(frozen=True)
class Commit:
    sha: str
    paths: frozenset


@dataclass
class Mapping:
    """The resolved (or unresolved) test -> subject relationship."""

    subjects: tuple = ()
    #: How the subject was found: "path" (a structural candidate path existed),
    #: "basename" (exactly one non-test file anywhere shares the basename),
    #: "basename-ambiguous" (several did -- all are kept, and the row is
    #: flagged), or "" when nothing matched.
    method: str = ""
    tried: tuple = ()

    @property
    def mapped(self) -> bool:
        return bool(self.subjects)


@dataclass
class Row:
    test_file: str
    edits: int
    with_subject: int
    solo: int
    solo_ratio: float
    subjects: tuple
    method: str
    score: int = field(default=0)


# --------------------------------------------------------------------------
# Path classification
# --------------------------------------------------------------------------


def is_excluded(path: str, patterns) -> bool:
    """True when `path` matches any exclusion glob (matched on the full path)."""
    return any(fnmatch.fnmatch(path, pat) for pat in patterns)


def is_test_path(path: str) -> bool:
    """True when `path` looks like a test file under any supported convention.

    Deliberately filename-driven rather than directory-driven: a file under a
    `tests/` directory that is a fixture, a helper, or a conftest is not a test
    file whose churn we can pair against a subject, and treating it as one
    would manufacture unmapped rows.
    """
    name = PurePosixPath(path).name
    if _JS_TEST_RE.match(name):
        return True
    if name.endswith(".py"):
        return bool(_PY_TEST_PREFIX_RE.match(name) or _PY_TEST_SUFFIX_RE.match(name))
    if name.endswith(".go"):
        return bool(_GO_TEST_RE.match(name))
    if name.endswith(".java"):
        return bool(_JVM_TEST_RE.match(name) or _JVM_TEST_PREFIX_RE.match(name))
    if name.endswith(".cs"):
        return bool(_DOTNET_TEST_RE.match(name))
    return False


def subject_basenames(name: str) -> list:
    """Candidate subject file names for a test file name, best guess first.

    Empty when `name` is not a recognized test file name.
    """
    js = _JS_TEST_RE.match(name)
    if js:
        stem, ext = js.group("stem"), js.group("ext")
        ordered = [ext] + [e for e in _JS_SUBJECT_EXTS if e != ext]
        return [stem + e for e in ordered]

    for pattern in (_PY_TEST_PREFIX_RE, _PY_TEST_SUFFIX_RE):
        match = pattern.match(name)
        if match:
            return [match.group("stem") + ".py"]

    match = _GO_TEST_RE.match(name)
    if match:
        return [match.group("stem") + ".go"]

    for pattern in (_JVM_TEST_RE, _JVM_TEST_PREFIX_RE):
        match = pattern.match(name)
        if match:
            return [match.group("stem") + ".java"]

    match = _DOTNET_TEST_RE.match(name)
    if match:
        return [match.group("stem") + ".cs"]

    return []


def subject_dirs(directory: str) -> list:
    """Candidate subject directories for a test file's directory, best first.

    The test directory itself comes first (Go's strict same-directory
    convention, and JS's common co-located `foo.spec.ts`), then each rewrite of
    a test-tree segment: removed (`tests/scripts` -> `scripts`) or replaced
    (`src/test/java` -> `src/main/java`, `Foo.Tests` -> `Foo`).
    """
    parts = [p for p in PurePosixPath(directory).parts if p not in (".", "")]
    candidates = ["/".join(parts)]

    for index, part in enumerate(parts):
        rewrites = []
        if part.lower() in _TEST_DIR_SEGMENTS:
            rewrites.append(None)  # drop the segment entirely
            rewrites.extend(_SUBJECT_DIR_REPLACEMENTS)
        dotnet = _DOTNET_TEST_PROJECT_RE.match(part)
        if dotnet:
            rewrites.append(dotnet.group("base"))
            rewrites.append(None)
        for rewrite in rewrites:
            rebuilt = list(parts)
            if rewrite is None:
                del rebuilt[index]
            else:
                rebuilt[index] = rewrite
            candidates.append("/".join(rebuilt))

    ordered = []
    for candidate in candidates:
        if candidate not in ordered:
            ordered.append(candidate)
    return ordered


def candidate_paths(test_path: str) -> list:
    """Ordered structural candidate subject paths for one test path."""
    pure = PurePosixPath(test_path)
    names = subject_basenames(pure.name)
    if not names:
        return []
    dirs = subject_dirs(str(pure.parent))
    ordered = []
    for name in names:
        for directory in dirs:
            candidate = f"{directory}/{name}" if directory else name
            if candidate != test_path and candidate not in ordered:
                ordered.append(candidate)
    return ordered


def resolve_subjects(test_path: str, universe, by_basename) -> Mapping:
    """Map one test path to its subject(s) against the known-path universe.

    `universe` is the set of non-test, non-excluded paths known to the repo
    (tracked now or touched in the scanned window); `by_basename` indexes that
    same set by file name. Structural candidates win; a bare basename match
    anywhere is the fallback, and is flagged when it is ambiguous.
    """
    tried = candidate_paths(test_path)
    for candidate in tried:
        if candidate in universe:
            return Mapping(subjects=(candidate,), method="path", tried=tuple(tried))

    for name in subject_basenames(PurePosixPath(test_path).name):
        matches = sorted(by_basename.get(name, ()))
        if len(matches) == 1:
            return Mapping(subjects=tuple(matches), method="basename", tried=tuple(tried))
        if matches:
            return Mapping(
                subjects=tuple(matches),
                method="basename-ambiguous",
                tried=tuple(tried),
            )

    return Mapping(tried=tuple(tried))


# --------------------------------------------------------------------------
# git I/O
# --------------------------------------------------------------------------


def run_git(repo, args, check=True):
    """Run a read-only git command in `repo` and return its stdout."""
    completed = subprocess.run(
        ["git", "-C", str(repo), "-c", "core.quotePath=false", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if check and completed.returncode != 0:
        raise Refusal(
            "git-command-failed",
            f"`git {' '.join(args)}` failed in {repo}: "
            f"{completed.stderr.strip() or completed.stdout.strip()}",
        )
    return completed.stdout


def ensure_git_repo(repo) -> None:
    completed = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--git-dir"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise Refusal(
            "not-a-git-repository",
            f"{repo} is not inside a git repository.",
            "Run this from a full clone of the repository you want to measure.",
        )


def is_shallow(repo) -> bool:
    """True when `repo` is a shallow clone.

    Primary mechanism is `git rev-parse --is-shallow-repository` (git >= 2.15).
    Older git does not know that flag, so fall back to the presence of the
    `shallow` file in the git dir, which is what the flag reports on.
    """
    completed = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--is-shallow-repository"],
        capture_output=True,
        text=True,
        check=False,
    )
    answer = completed.stdout.strip().lower()
    if completed.returncode == 0 and answer in ("true", "false"):
        return answer == "true"

    git_dir = run_git(repo, ["rev-parse", "--absolute-git-dir"]).strip()
    return bool(git_dir) and (Path(git_dir) / "shallow").exists()


def git_log_commits(repo, since_days=None, max_commits=None) -> list:
    """Return the scanned window's commits, newest first, as (sha, paths).

    Merge commits are excluded: their `--name-only` output either is empty or
    re-reports every path on the merged side, which would inflate both edit
    counts and co-change counts in a merge-heavy history.
    """
    if not _has_commits(repo):
        return []

    args = ["log", "--no-merges", "--name-only", "--pretty=format:%x00%H"]
    if since_days is not None:
        args.append(f"--since={since_days} days ago")
    if max_commits:
        args.append(f"--max-count={max_commits}")
    out = run_git(repo, args)

    commits = []
    for chunk in out.split("\0"):
        if not chunk.strip():
            continue
        lines = chunk.splitlines()
        sha = lines[0].strip()
        paths = frozenset(line for line in lines[1:] if line.strip())
        commits.append(Commit(sha=sha, paths=paths))
    return commits


def _has_commits(repo) -> bool:
    """True when `repo` has at least one commit.

    A freshly-initialized repository has no HEAD, and `git log` there exits
    non-zero with "does not have any commits yet" -- which would surface as a
    generic git-command failure instead of the accurate "empty window".
    """
    completed = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--quiet", "--verify", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode == 0


def tracked_paths(repo) -> set:
    """Currently-tracked paths, always relative to the repository root.

    `--full-name` is load-bearing: a bare `git ls-files` reports paths relative
    to the CWD, so pointing `--repo` at a subdirectory would yield a universe
    of subdirectory-relative paths while `git log` reports root-relative ones.
    Nothing would error -- every structural mapping would just silently miss.
    """
    return {
        line
        for line in run_git(repo, ["ls-files", "--full-name"]).splitlines()
        if line.strip()
    }


# --------------------------------------------------------------------------
# Analysis
# --------------------------------------------------------------------------


def build_report(commits, tracked, min_edits, excludes) -> dict:
    """Compute the ranked rows and the unmapped list from scanned commits.

    Commits are indexed by path once (`commit_ids`), so co-change is a set
    intersection per row rather than a rescan of the window per row.
    """
    commit_ids = {}
    for index, commit in enumerate(commits):
        for path in commit.paths:
            if is_excluded(path, excludes):
                continue
            commit_ids.setdefault(path, set()).add(index)

    historical = set(commit_ids)
    universe = {
        path
        for path in (historical | {p for p in tracked if not is_excluded(p, excludes)})
        if not is_test_path(path)
    }
    by_basename = {}
    for path in universe:
        by_basename.setdefault(PurePosixPath(path).name, []).append(path)

    test_files = sorted(path for path in historical if is_test_path(path))
    considered = [path for path in test_files if len(commit_ids[path]) >= min_edits]

    rows = []
    unmapped = []
    for path in considered:
        mapping = resolve_subjects(path, universe, by_basename)
        total = len(commit_ids[path])
        if not mapping.mapped:
            unmapped.append(
                {"test_file": path, "edits": total, "tried": list(mapping.tried)}
            )
            continue
        subject_commits = set()
        for subject in mapping.subjects:
            subject_commits |= commit_ids.get(subject, set())
        with_subject = len(commit_ids[path] & subject_commits)
        solo = total - with_subject
        rows.append(
            Row(
                test_file=path,
                edits=total,
                with_subject=with_subject,
                solo=solo,
                solo_ratio=(solo / total) if total else 0.0,
                subjects=mapping.subjects,
                method=mapping.method,
                score=solo,
            )
        )

    rows.sort(key=lambda r: (-r.score, -r.solo_ratio, -r.edits, r.test_file))
    unmapped.sort(key=lambda u: (-u["edits"], u["test_file"]))

    return {
        "commits_scanned": len(commits),
        "test_files_seen": len(test_files),
        "test_files_considered": len(considered),
        "min_edits": min_edits,
        "rows": rows,
        "unmapped": unmapped,
    }


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def render_json(report, top) -> str:
    payload = dict(report)
    payload["rows"] = [
        {
            "rank": index,
            "test_file": row.test_file,
            "edits": row.edits,
            "with_subject": row.with_subject,
            "solo": row.solo,
            "solo_ratio": round(row.solo_ratio, 4),
            "score": row.score,
            "subjects": list(row.subjects),
            "match": row.method,
        }
        for index, row in enumerate(report["rows"][:top], start=1)
    ]
    return json.dumps(payload, indent=2, sort_keys=True)


def render_text(report, top) -> str:
    lines = []
    window = report["window"]
    lines.append(
        f"Churn vs coupling  window: {window}  commits scanned: "
        f"{report['commits_scanned']}"
    )
    if report.get("truncated"):
        lines.append(
            "  NOTE: --max-commits truncated the window; counts describe the "
            "scanned slice, not the full window."
        )
    lines.append(
        f"  test files touched: {report['test_files_seen']}  "
        f"at/above --min-edits {report['min_edits']}: "
        f"{report['test_files_considered']}  "
        f"mapped: {len(report['rows'])}  unmapped: {len(report['unmapped'])}"
    )
    lines.append("")

    rows = report["rows"][:top]
    if not rows:
        lines.append(
            "No mapped test file reached --min-edits "
            f"{report['min_edits']} in this window."
        )
    else:
        header = f"{'#':>3}  {'edits':>5} {'with':>5} {'solo':>5} {'solo%':>6}  test file -> subject(s)"
        lines.append(header)
        lines.append("-" * len(header))
        for index, row in enumerate(rows, start=1):
            subjects = ", ".join(row.subjects)
            flag = "  [ambiguous mapping]" if row.method == "basename-ambiguous" else ""
            lines.append(
                f"{index:>3}  {row.edits:>5} {row.with_subject:>5} {row.solo:>5} "
                f"{row.solo_ratio * 100:>5.0f}%  {row.test_file} -> {subjects}{flag}"
            )

    if report["unmapped"]:
        lines.append("")
        lines.append(
            f"Unmapped ({len(report['unmapped'])}) -- no subject located, so NOT "
            "scored. A miss here is a gap in the mapping conventions, not a finding:"
        )
        for item in report["unmapped"][:top]:
            tried = ", ".join(item["tried"][:3]) or "(no candidate form recognized)"
            lines.append(f"  {item['edits']:>5} edits  {item['test_file']}")
            lines.append(f"            tried: {tried}")
        hidden = len(report["unmapped"]) - top
        if hidden > 0:
            # Named, not dropped: --top caps the display, and --json still
            # carries every unmapped file.
            lines.append(f"  ... and {hidden} more (raise --top, or use --json)")

    lines.append("")
    lines.append(
        "Reading it: a high solo% means the test changed without its subject "
        "changing -- the implementation-coupling smell. A low solo% means the "
        "test moved when behavior moved. This script ranks; it does not decide "
        "what to do about a row."
    )
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _positive_int(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return number


def build_parser():
    parser = argparse.ArgumentParser(
        prog="churn_coupling_report.py",
        description=(
            "Rank high-churn test files by how often they change without their "
            "subject changing."
        ),
    )
    parser.add_argument("--repo", default=".", help="repository to measure (default: .)")
    parser.add_argument(
        "--since",
        metavar="DAYS",
        type=_positive_int,
        default=DEFAULT_SINCE_DAYS,
        help=f"lookback window in days (default: {DEFAULT_SINCE_DAYS})",
    )
    parser.add_argument(
        "--max-commits",
        metavar="N",
        type=_positive_int,
        default=None,
        help="cap commits scanned; the report flags the window as truncated",
    )
    parser.add_argument(
        "--min-edits",
        metavar="N",
        type=_positive_int,
        default=DEFAULT_MIN_EDITS,
        help=f"only consider test files with >= N edits (default: {DEFAULT_MIN_EDITS})",
    )
    parser.add_argument(
        "--top",
        metavar="N",
        type=_positive_int,
        default=DEFAULT_TOP,
        help="show at most N ranked rows, and at most N unmapped files, in the text report; --json always carries every row "
        "(default: " + str(DEFAULT_TOP) + ")",
    )
    parser.add_argument(
        "--exclude",
        metavar="GLOB",
        action="append",
        default=[],
        help="extra path glob to exclude (repeatable; adds to the defaults)",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    return parser


def run(args) -> str:
    ensure_git_repo(args.repo)
    if is_shallow(args.repo):
        raise Refusal(
            "shallow-clone",
            f"{args.repo} is a shallow clone. Churn counts from a shallow clone "
            "measure clone depth, not history, so this report would be "
            "confidently wrong rather than merely incomplete.",
            "git fetch --unshallow",
        )

    commits = git_log_commits(args.repo, since_days=args.since, max_commits=args.max_commits)
    if not commits:
        raise Refusal(
            "empty-window",
            f"No non-merge commits in the last {args.since} days.",
            "Widen the window with --since.",
        )

    excludes = tuple(DEFAULT_EXCLUDES) + tuple(args.exclude)
    report = build_report(commits, tracked_paths(args.repo), args.min_edits, excludes)
    report["window"] = f"{args.since} days"
    report["truncated"] = bool(args.max_commits and len(commits) >= args.max_commits)
    return render_json(report, args.top) if args.json else render_text(report, args.top)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        print(run(args))
    except Refusal as refusal:
        print(
            f"churn_coupling_report: refusing to run -- reason: {refusal.reason}",
            file=sys.stderr,
        )
        print(f"  {refusal.detail}", file=sys.stderr)
        if refusal.remedy:
            print(f"  fix: {refusal.remedy}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
