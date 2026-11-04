#!/usr/bin/env python3
"""build_candidates.py — candidate lifecycle for `/build --candidates N` (#2273).

Subcommands: validate-flags, collect, rank, project, reconcile, cleanup.

Exit codes: 0 success; 1 invalid input data (message on stderr, nothing on
stdout, no file touched); 2 usage error (argparse or validate-flags).
All JSON output is `json.dumps(..., sort_keys=True)` plus one newline.

Stdlib-only. (ADR 0014/0015).
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import NoReturn

EXIT_OK = 0
EXIT_INVALID_DATA = 1
EXIT_USAGE = 2
EXIT_RESTORE_FAILED = 2

MIN_CANDIDATES = 1
MAX_CANDIDATES = 8
SPECULATIVE_MIN_CANDIDATES = 2

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE / "lib"))

import plan_parse

GIT_TIMEOUT_SECONDS = 120
# build_wave_reconcile.py bounds its own suite run at 1800s; allow it that
# plus the merge and checkout around it.
RECONCILE_TIMEOUT_SECONDS = 2100
RECONCILE_SCRIPT = _HERE / "build_wave_reconcile.py"
LENS_SPEC_COMPLIANCE = "spec-compliance-review"
LENS_CORRECTNESS = "correctness-review"
UNMET_SCENARIO_CATEGORIES = frozenset({"uncovered-scenario", "unmet-criterion"})

_SCENARIO_LINE_RE = re.compile(r"^\s*Scenario( Outline)?:")
_STEP_RE = re.compile(r"[0-9]+\.[0-9]+")
_ASCII_INT_RE = re.compile(r"-?[0-9]+")
_ASCII_NUMBER_RE = re.compile(r"(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")


PROJECTED_DECIMALS = 4
HALT_REASON_NO_SPEND = (
    "cost meter recorded no spend for the last batch; --max-cost-usd cannot be enforced"
)

SCREENING_OK = "ok"
SCREENING_UNPARSEABLE_PREFIX = "unparseable: "


class FlagError(ValueError):
    """A `/build` flag combination that validate-flags rejects (exit 2)."""


class DataError(ValueError):
    """Input data a subcommand rejects (exit 1)."""


class RestoreFailedError(RuntimeError):
    """The build branch could not be returned to its pre-merge SHA (exit 2)."""


def _fail(code: int, message: str) -> int:
    """Write one message line to stderr and return the exit code."""
    print(message, file=sys.stderr)
    return code


def _emit(payload: object) -> None:
    sys.stdout.write(json.dumps(payload, sort_keys=True) + "\n")


def _parse_ascii_int(raw: str) -> int | None:
    return int(raw) if _ASCII_INT_RE.fullmatch(raw) else None


def _parse_candidates(raw: str) -> int:
    value = _parse_ascii_int(raw)
    if value is None or not MIN_CANDIDATES <= value <= MAX_CANDIDATES:
        raise FlagError(
            f"--candidates must be an integer between {MIN_CANDIDATES} "
            f"and {MAX_CANDIDATES}; got '{raw}'"
        )
    return value


def _parse_finite_number(raw: str) -> float:
    """Parse a plain ASCII decimal; NaN when the spelling or magnitude is not
    a finite number."""
    value = float(raw) if _ASCII_NUMBER_RE.fullmatch(raw) else math.nan
    return value if math.isfinite(value) else math.nan


def _parse_cost_cap(raw: str) -> float:
    value = _parse_finite_number(raw)
    if not value > 0:
        raise FlagError(f"--max-cost-usd must be a number greater than 0; got '{raw}'")
    return value


def validate_flags(
    candidates: str | None, max_cost_usd: str | None, jobs: str | None
) -> dict:
    """Validate the raw `/build` flag strings; raise FlagError on the first
    failure (candidates syntax, cap syntax, pairing rules, then --jobs)."""
    count = MIN_CANDIDATES if candidates is None else _parse_candidates(candidates)
    cap = None if max_cost_usd is None else _parse_cost_cap(max_cost_usd)
    speculative = count >= SPECULATIVE_MIN_CANDIDATES
    if speculative and cap is None:
        raise FlagError(
            f"--candidates N with N >= {SPECULATIVE_MIN_CANDIDATES} "
            "requires --max-cost-usd"
        )
    if cap is not None and not speculative:
        raise FlagError(
            "--max-cost-usd requires --candidates N with "
            f"N >= {SPECULATIVE_MIN_CANDIDATES}"
        )
    requested_jobs = None if jobs is None else _parse_ascii_int(jobs)
    if speculative and requested_jobs is not None and requested_jobs > 1:
        raise FlagError(
            f"--candidates N with N >= {SPECULATIVE_MIN_CANDIDATES} "
            "cannot be combined with --jobs greater than 1"
        )
    return {"candidates": count, "max_cost_usd": cap, "speculative": speculative}


def _load_json_object(path: str, label: str) -> dict:
    """Read `path` as a JSON object; raise DataError prefixed with `label`."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        raise DataError(f"{label}: no such file: {path}") from None
    except OSError as exc:
        raise DataError(f"{label}: cannot read {path}: {exc.strerror}") from None
    except ValueError:
        raise DataError(f"{label}: not JSON (not valid UTF-8): {path}") from None
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise DataError(f"{label}: not JSON: {path}: {exc}") from None
    if not isinstance(data, dict):
        raise DataError(f"{label}: JSON root is not an object: {path}")
    return data


def _reject(label: str, message: str) -> NoReturn:
    raise ValueError(f"{label}: {message}")


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


@dataclass(frozen=True)
class Candidate:
    id: int
    branch: str
    suite_green: bool
    scenarios_total: int
    scenarios_unmet: int
    errors: int
    warnings: int
    diff_lines: int
    cost_usd: float
    screening: str

    @classmethod
    def from_dict(cls, data: object) -> Candidate:
        """Validate `data` field by field; raise ValueError naming the id and
        the offending field. Unknown keys are ignored."""
        if not isinstance(data, dict):
            _reject("candidate entry", "not an object")
        cid = data.get("id")
        if not (_is_int(cid) and cid >= 1):
            _reject(f"candidate {cid!r}", "id must be a positive int")
        label = f"candidate {cid}"

        def field(name: str) -> object:
            if name not in data:
                _reject(label, f"{name} is missing")
            return data[name]

        def count(name: str) -> int:
            value = field(name)
            if not (_is_int(value) and value >= 0):
                _reject(label, f"{name} must be a non-negative int")
            return value

        branch = field("branch")
        if not isinstance(branch, str):
            _reject(label, "branch must be a string")
        suite_green = field("suite_green")
        if not isinstance(suite_green, bool):
            _reject(label, "suite_green must be a boolean")
        if branch == "" and suite_green:
            _reject(label, "branch may be empty only when suite_green is false")
        total = count("scenarios_total")
        unmet = count("scenarios_unmet")
        if unmet > total:
            _reject(label, f"scenarios_unmet {unmet} exceeds scenarios_total {total}")
        cost = field("cost_usd")
        if not (_is_number(cost) and math.isfinite(cost) and cost >= 0):
            _reject(label, "cost_usd must be a finite non-negative number")
        screening = field("screening")
        if not _is_valid_screening(screening):
            _reject(
                label,
                f"screening must be '{SCREENING_OK}' or "
                f"'{SCREENING_UNPARSEABLE_PREFIX}<lens>'",
            )
        return cls(
            id=cid,
            branch=branch,
            suite_green=suite_green,
            scenarios_total=total,
            scenarios_unmet=unmet,
            errors=count("errors"),
            warnings=count("warnings"),
            diff_lines=count("diff_lines"),
            cost_usd=float(cost),
            screening=screening,
        )


def _is_valid_screening(value: object) -> bool:
    if value == SCREENING_OK:
        return True
    return (
        isinstance(value, str)
        and value.startswith(SCREENING_UNPARSEABLE_PREFIX)
        and len(value) > len(SCREENING_UNPARSEABLE_PREFIX)
    )


def disqualified(candidate: Candidate) -> bool:
    return (not candidate.suite_green) or candidate.screening != SCREENING_OK


def scenarios_met(candidate: Candidate) -> int:
    return candidate.scenarios_total - candidate.scenarios_unmet


def sort_key(candidate: Candidate) -> tuple:
    """Ranking key: qualified first, then more scenarios met, fewer errors,
    fewer warnings, fewer diff lines, lower id. cost_usd never participates."""
    return (
        disqualified(candidate),
        -scenarios_met(candidate),
        candidate.errors,
        candidate.warnings,
        candidate.diff_lines,
        candidate.id,
    )


def rank(candidates: Sequence[Candidate]) -> dict:
    """Order candidates by `sort_key`; the winner is the first unless it is
    disqualified."""
    ordered = sorted(candidates, key=sort_key)
    winner = ordered[0] if ordered and not disqualified(ordered[0]) else None
    return {
        "disqualified": sorted(c.id for c in candidates if disqualified(c)),
        "order": [c.id for c in ordered],
        "rank": {str(c.id): position for position, c in enumerate(ordered, start=1)},
        "scenarios_met": {str(c.id): scenarios_met(c) for c in ordered},
        "winner": None if winner is None else winner.id,
    }


def _load_candidates(path: str) -> list[Candidate]:
    data = _load_json_object(path, "rank")
    raw = data.get("candidates")
    if not isinstance(raw, list):
        raise DataError("rank: 'candidates' must be a list")
    if not raw:
        raise DataError("rank: no candidates")
    try:
        candidates = [Candidate.from_dict(entry) for entry in raw]
    except ValueError as exc:
        raise DataError(f"rank: {exc}") from None
    seen: set[int] = set()
    for candidate in candidates:
        if candidate.id in seen:
            raise DataError(f"rank: duplicate candidate id {candidate.id}")
        seen.add(candidate.id)
    return candidates


def project(
    cap: float, spent: float, completed: int, remaining: int, last_batch_delta: float
) -> dict:
    """Decide whether to dispatch the next batch: halt when the meter saw no
    spend, stop when spent has reached the cap or the linear projection
    exceeds it, else continue."""
    per_candidate = spent / completed if completed > 0 else 0.0
    projected = spent + remaining * per_candidate
    if last_batch_delta == 0:
        decision, reason = "halt", HALT_REASON_NO_SPEND
    elif spent >= cap:
        decision, reason = "stop", "spent has reached the cap"
    elif projected > cap:
        decision, reason = "stop", "projected spend exceeds the cap"
    else:
        decision, reason = "continue", ""
    return {
        "cap": cap,
        "completed": completed,
        "decision": decision,
        "last_batch_delta": last_batch_delta,
        "projected": round(projected, PROJECTED_DECIMALS),
        "reason": reason,
        "remaining": remaining,
        "spent": spent,
    }


def _finite_non_negative(raw: str) -> float:
    value = _parse_finite_number(raw)
    if not value >= 0:
        raise argparse.ArgumentTypeError(f"must be a finite number >= 0; got '{raw}'")
    return value


def _positive_cap(raw: str) -> float:
    value = _parse_finite_number(raw)
    if not value > 0:
        raise argparse.ArgumentTypeError(f"must be a finite number > 0; got '{raw}'")
    return value


def _positive_int(raw: str) -> int:
    value = _parse_ascii_int(raw)
    if value is None or value < 1:
        raise argparse.ArgumentTypeError(f"must be an integer >= 1; got '{raw}'")
    return value


def _cmd_project(args: argparse.Namespace) -> int:
    _emit(
        project(
            args.cap, args.spent, args.completed, args.remaining, args.last_batch_delta
        )
    )
    return EXIT_OK


def _cmd_validate_flags(args: argparse.Namespace) -> int:
    try:
        result = validate_flags(args.candidates, args.max_cost_usd, args.jobs)
    except FlagError as exc:
        return _fail(EXIT_USAGE, str(exc))
    _emit(result)
    return EXIT_OK


def _git(repo: str, *args: str) -> subprocess.CompletedProcess:
    """Run `git -C <repo> <args>`, bounded by a timeout; raise DataError when
    git cannot be run at all. A non-zero exit is returned, not raised."""
    try:
        return subprocess.run(
            ["git", "-C", repo, *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DataError(
            f"git {' '.join(args)} could not run in {repo}: {exc}"
        ) from None


def _diff_line_count(worktree: str, base: str) -> int:
    """Added plus deleted lines in `base..HEAD`; a binary file counts 0."""
    result = _git(worktree, "diff", "--numstat", f"{base}..HEAD")
    if result.returncode != 0:
        raise DataError(
            f"collect: git diff --numstat {base}..HEAD failed in {worktree}: "
            f"{result.stderr.strip()}"
        )
    total = 0
    for line in result.stdout.splitlines():
        added, deleted, _path = line.split("\t", 2)
        total += sum(int(n) for n in (added, deleted) if n.isdigit())
    return total


def _scenario_total(plan_path: str, step: str) -> int:
    """Scenario and Scenario Outline lines in the first Gherkin block of the
    slice that owns `step`."""
    try:
        text = Path(plan_path).read_text(encoding="utf-8")
    except OSError as exc:
        raise DataError(
            f"collect: cannot read plan {plan_path}: {exc.strerror}"
        ) from None
    slice_id = step.split(".", 1)[0]
    blocks = {
        sid: gherkin
        for sid, _title, gherkin in plan_parse.slice_gherkin_blocks(text.splitlines())
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
        data = _load_json_object(path, lens)
    except DataError:
        return None
    issues = data.get("issues")
    if not isinstance(data.get("status"), str) or not isinstance(issues, list):
        return None
    return [issue for issue in issues if isinstance(issue, dict)]


def collect(
    *,
    cid: int,
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
    total = _scenario_total(plan, step)
    diff_lines = _diff_line_count(worktree, base)
    spec_issues = _lens_issues(spec_json, LENS_SPEC_COMPLIANCE)
    correctness_issues = _lens_issues(correctness_json, LENS_CORRECTNESS)
    unparseable = [
        lens
        for lens, issues in (
            (LENS_SPEC_COMPLIANCE, spec_issues),
            (LENS_CORRECTNESS, correctness_issues),
        )
        if issues is None
    ]
    unmet = sum(
        1
        for issue in spec_issues or []
        if issue.get("category") in UNMET_SCENARIO_CATEGORIES
    )

    def severity_count(severity: str) -> int:
        return sum(1 for i in correctness_issues or [] if i.get("severity") == severity)

    candidate = {
        "id": cid,
        "branch": branch,
        "suite_green": suite_exit == 0,
        "scenarios_total": total,
        "scenarios_unmet": min(total, unmet),
        "errors": severity_count("error"),
        "warnings": severity_count("warning"),
        "diff_lines": diff_lines,
        "cost_usd": cost_usd,
        "screening": (
            f"{SCREENING_UNPARSEABLE_PREFIX}{unparseable[0]}"
            if unparseable
            else SCREENING_OK
        ),
    }
    try:
        return asdict(Candidate.from_dict(candidate))
    except ValueError as exc:
        raise DataError(f"collect: {exc}") from None


def _step_id(raw: str) -> str:
    if not _STEP_RE.fullmatch(raw):
        raise argparse.ArgumentTypeError(f"must look like N.M; got '{raw}'")
    return raw


def _cmd_collect(args: argparse.Namespace) -> int:
    try:
        result = collect(
            cid=args.id,
            branch=args.branch,
            worktree=args.worktree,
            base=args.base,
            suite_exit=args.suite_exit,
            spec_json=args.spec_json,
            correctness_json=args.correctness_json,
            plan=args.plan,
            step=args.step,
            cost_usd=args.cost_usd,
        )
    except DataError as exc:
        return _fail(EXIT_INVALID_DATA, str(exc))
    _emit(result)
    return EXIT_OK


def _head_sha(repo: str) -> str:
    result = _git(repo, "rev-parse", "HEAD")
    if result.returncode != 0:
        raise DataError(
            f"reconcile: cannot resolve HEAD in {repo}: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def _current_branch(repo: str) -> str:
    return _git(repo, "symbolic-ref", "--short", "-q", "HEAD").stdout.strip()


def _run_reconcile_script(
    repo: str, into: str, base: str, test_cmd: str, branch: str
) -> bool:
    """Run build_wave_reconcile.py in `repo`; True when it exits 0. Its stderr
    is passed through; its stdout is dropped."""
    command = [
        sys.executable,
        str(RECONCILE_SCRIPT),
        "--into",
        into,
        "--base",
        base,
        "--test-cmd",
        test_cmd,
        branch,
    ]
    try:
        proc = subprocess.run(
            command,
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
            timeout=RECONCILE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        print(
            f"reconcile: build_wave_reconcile.py timed out after {RECONCILE_TIMEOUT_SECONDS}s",
            file=sys.stderr,
        )
        return False
    sys.stderr.write(proc.stderr)
    return proc.returncode == 0


def _restore_branch(repo: str, pre: str) -> None:
    """Return HEAD to `pre`: abort a merge in progress, then `reset --keep`
    (never --hard: the worktree holds uncommitted plan edits). Raise
    RestoreFailedError when HEAD is not `pre` afterwards."""
    failure = RestoreFailedError(
        f"reconcile: could not restore the build branch to {pre}; "
        f"save your uncommitted edits, then run: git reset --keep {pre}"
    )
    try:
        merge_head = _git(repo, "rev-parse", "--git-path", "MERGE_HEAD").stdout.strip()
        if merge_head and (Path(repo) / merge_head).exists():
            _git(repo, "merge", "--abort")
        reset = _git(repo, "reset", "--keep", pre)
        if reset.returncode != 0:
            sys.stderr.write(reset.stderr)
        restored = _head_sha(repo) == pre
    except DataError:
        raise failure from None
    if not restored:
        raise failure


def reconcile(*, repo: str, into: str, base: str, test_cmd: str, branch: str) -> dict:
    """Merge `branch` into the build branch with build_wave_reconcile.py. On
    failure restore the build branch to its pre-merge SHA and report
    merged=False; raise RestoreFailedError when that restore fails."""
    if _current_branch(repo) != into:
        raise DataError(f"reconcile: {repo} is not on build branch '{into}'")
    pre = _head_sha(repo)
    merged = _run_reconcile_script(repo, into, base, test_cmd, branch)
    if not merged:
        _restore_branch(repo, pre)
    return {
        "branch": branch,
        "head": _head_sha(repo),
        "merged": merged,
        "pre_merge_sha": pre,
    }


def _cmd_reconcile(args: argparse.Namespace) -> int:
    try:
        result = reconcile(
            repo=args.repo,
            into=args.into,
            base=args.base,
            test_cmd=args.test_cmd,
            branch=args.branch,
        )
    except DataError as exc:
        return _fail(EXIT_INVALID_DATA, str(exc))
    except RestoreFailedError as exc:
        return _fail(EXIT_RESTORE_FAILED, str(exc))
    _emit(result)
    return EXIT_OK if result["merged"] else EXIT_INVALID_DATA


def _cmd_rank(args: argparse.Namespace) -> int:
    try:
        result = rank(_load_candidates(args.candidates))
    except DataError as exc:
        return _fail(EXIT_INVALID_DATA, str(exc))
    _emit(result)
    return EXIT_OK


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="build_candidates.py", description="Candidate lifecycle for /build."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    flags = sub.add_parser("validate-flags", help="validate the raw /build flags")
    flags.add_argument("--candidates")
    flags.add_argument("--max-cost-usd")
    flags.add_argument("--jobs")
    flags.set_defaults(handler=_cmd_validate_flags)

    collecting = sub.add_parser("collect", help="build one candidate dict")
    collecting.add_argument("--id", required=True, type=_positive_int)
    collecting.add_argument("--branch", required=True)
    collecting.add_argument("--worktree", required=True)
    collecting.add_argument("--base", required=True)
    collecting.add_argument("--suite-exit", required=True, type=int)
    collecting.add_argument("--spec-json", required=True)
    collecting.add_argument("--correctness-json", required=True)
    collecting.add_argument("--plan", required=True)
    collecting.add_argument("--step", required=True, type=_step_id)
    collecting.add_argument("--cost-usd", required=True, type=_finite_non_negative)
    collecting.set_defaults(handler=_cmd_collect)

    reconciling = sub.add_parser(
        "reconcile", help="merge the winner; restore the build branch on failure"
    )
    reconciling.add_argument("--repo", required=True)
    reconciling.add_argument("--into", required=True)
    reconciling.add_argument("--base", required=True)
    reconciling.add_argument("--test-cmd", required=True)
    reconciling.add_argument("branch")
    reconciling.set_defaults(handler=_cmd_reconcile)

    ranking = sub.add_parser("rank", help="rank candidates and pick a winner")
    ranking.add_argument("--candidates", required=True, help="candidates JSON file")
    ranking.set_defaults(handler=_cmd_rank)

    projection = sub.add_parser(
        "project", help="decide whether to dispatch another batch"
    )
    projection.add_argument("--cap", required=True, type=_positive_cap)
    projection.add_argument("--spent", required=True, type=_finite_non_negative)
    projection.add_argument("--completed", required=True, type=_positive_int)
    projection.add_argument("--remaining", required=True, type=_positive_int)
    projection.add_argument(
        "--last-batch-delta", required=True, type=_finite_non_negative
    )
    projection.set_defaults(handler=_cmd_project)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
