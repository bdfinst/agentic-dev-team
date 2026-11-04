#!/usr/bin/env python3
"""build_candidates.py — candidate lifecycle for `/build --candidates N`.

Subcommands: validate-flags, collect, rank, project, reconcile, cleanup.

This is the one command-line entry point. The data model and ranking live in
`build_candidates_model`, the git-facing operations in `build_candidates_git`;
both are re-exported here, so `build_candidates.collect` and friends work.

Exit codes:
  0  success.
  1  invalid input data: message on stderr, empty stdout, nothing touched.
     Exceptions: `reconcile` exits 1 when the candidate was not merged (its
     JSON is then on stdout and the build branch has been restored), and a
     `cleanup` git failure part-way exits 1 with the earlier branches
     already removed (the message names the branch that failed).
  2  usage error (argparse or validate-flags), or `reconcile` could not
     restore the build branch. That message names the pre-merge SHA and the
     manual `git reset --keep <sha>`.

All JSON output is `json.dumps(..., sort_keys=True)` plus one newline.

Stdlib only (ADR 0014, ADR 0015, ADR 0031).
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:  # sibling imports under -I / -P / PYTHONSAFEPATH
    sys.path.insert(0, _HERE)

from build_candidates_git import (
    cleanup,
    collect,
    reconcile,
    restore_branch,
)
from build_candidates_model import (
    SCREENING_OK,
    SCREENING_UNPARSEABLE_PREFIX,
    STEP_ID_RE,
    Candidate,
    DataError,
    FlagError,
    GitError,
    RestoreFailedError,
    disqualified,
    load_candidates,
    load_json_object,
    rank,
    scenarios_met,
    sort_key,
)

__all__ = [
    "SCREENING_OK",
    "SCREENING_UNPARSEABLE_PREFIX",
    "Candidate",
    "DataError",
    "FlagError",
    "GitError",
    "RestoreFailedError",
    "cleanup",
    "collect",
    "disqualified",
    "load_candidates",
    "load_json_object",
    "main",
    "project",
    "rank",
    "reconcile",
    "restore_branch",
    "scenarios_met",
    "sort_key",
    "validate_flags",
]

EXIT_OK = 0
EXIT_INVALID_DATA = 1
EXIT_NOT_MERGED = 1
EXIT_USAGE = 2
# Deliberately the same value as EXIT_USAGE: both mean "the caller must act
# before retrying".
EXIT_RESTORE_FAILED = 2

_MIN_CANDIDATES = 1
MAX_CANDIDATES = 8
_SPECULATIVE_MIN_CANDIDATES = 2

_ASCII_INT_RE = re.compile(r"-?[0-9]+")
_ASCII_NUMBER_RE = re.compile(r"(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")

_PROJECTED_DECIMALS = 4
_DECISION_HALT = "halt"
_DECISION_STOP = "stop"
_DECISION_CONTINUE = "continue"
_HALT_REASON_NO_SPEND = (
    "cost meter recorded no spend for the last batch; --max-cost-usd cannot be enforced"
)
_STOP_REASON_CAP_REACHED = "spent has reached the cap"
_STOP_REASON_PROJECTION_EXCEEDS_CAP = "projected spend exceeds the cap"


def _fail(code: int, message: str) -> int:
    """Write one message line to stderr and return the exit code."""
    print(message, file=sys.stderr)
    return code


def _emit(payload: object) -> None:
    sys.stdout.write(json.dumps(payload, sort_keys=True) + "\n")


def _emit_or_fail(
    compute: Callable[[], object],
    error_codes: Mapping[type[Exception], int],
    exit_code_of: Callable[[object], int] = lambda _result: EXIT_OK,
) -> int:
    """Print `compute()` as JSON and return `exit_code_of(result)`. An
    exception listed in `error_codes` prints its message to stderr, leaves
    stdout empty and returns the mapped code (first matching entry wins)."""
    try:
        result = compute()
    except tuple(error_codes) as exc:
        code = next(c for kind, c in error_codes.items() if isinstance(exc, kind))
        return _fail(code, str(exc))
    _emit(result)
    return exit_code_of(result)


def _parse_ascii_int(raw: str) -> int | None:
    if not _ASCII_INT_RE.fullmatch(raw):
        return None
    try:
        return int(raw)
    except ValueError:  # over the interpreter's digit limit
        return None


def _parse_number_or_none(raw: str) -> float | None:
    """Parse a plain ASCII decimal; None when the spelling is not one or the
    magnitude is not finite."""
    if not _ASCII_NUMBER_RE.fullmatch(raw):
        return None
    value = float(raw)
    return value if math.isfinite(value) else None


def _is_valid_cost_cap(value: float | None) -> bool:
    return value is not None and value > 0


def _parse_candidates(raw: str) -> int:
    value = _parse_ascii_int(raw)
    if value is None or not _MIN_CANDIDATES <= value <= MAX_CANDIDATES:
        raise FlagError(
            f"--candidates must be an integer between {_MIN_CANDIDATES} "
            f"and {MAX_CANDIDATES}; got '{raw}'"
        )
    return value


def _parse_cost_cap(raw: str) -> float:
    value = _parse_number_or_none(raw)
    if value is None or not _is_valid_cost_cap(value):
        raise FlagError(f"--max-cost-usd must be a number greater than 0; got '{raw}'")
    return value


def validate_flags(
    candidates: str | None, max_cost_usd: str | None, jobs: str | None
) -> dict:
    """Validate the raw `/build` flag strings; raise FlagError on the first
    failure (candidates syntax, cap syntax, pairing rules, then --jobs)."""
    count = _MIN_CANDIDATES if candidates is None else _parse_candidates(candidates)
    cap = None if max_cost_usd is None else _parse_cost_cap(max_cost_usd)
    speculative = count >= _SPECULATIVE_MIN_CANDIDATES
    if speculative and cap is None:
        raise FlagError(
            f"--candidates N with N >= {_SPECULATIVE_MIN_CANDIDATES} "
            "requires --max-cost-usd"
        )
    if cap is not None and not speculative:
        raise FlagError(
            "--max-cost-usd requires --candidates N with "
            f"N >= {_SPECULATIVE_MIN_CANDIDATES}"
        )
    requested_jobs = None if jobs is None else _parse_ascii_int(jobs)
    if speculative and requested_jobs is not None and requested_jobs > 1:
        raise FlagError(
            f"--candidates N with N >= {_SPECULATIVE_MIN_CANDIDATES} "
            "cannot be combined with --jobs greater than 1"
        )
    return {"candidates": count, "max_cost_usd": cap, "speculative": speculative}


def project(
    cap: float, spent: float, completed: int, remaining: int, last_batch_delta: float
) -> dict:
    """Decide whether to dispatch the next batch: halt when the meter saw no
    spend, stop when spent has reached the cap or the linear projection
    exceeds it, else continue."""
    per_candidate = spent / completed if completed > 0 else 0.0
    projected = spent + remaining * per_candidate
    if last_batch_delta == 0:
        decision, reason = _DECISION_HALT, _HALT_REASON_NO_SPEND
    elif spent >= cap:
        decision, reason = _DECISION_STOP, _STOP_REASON_CAP_REACHED
    elif projected > cap:
        decision, reason = _DECISION_STOP, _STOP_REASON_PROJECTION_EXCEEDS_CAP
    else:
        decision, reason = _DECISION_CONTINUE, ""
    return {
        "cap": cap,
        "completed": completed,
        "decision": decision,
        "last_batch_delta": last_batch_delta,
        "projected": round(projected, _PROJECTED_DECIMALS),
        "reason": reason,
        "remaining": remaining,
        "spent": spent,
    }


def _argparse_finite_non_negative(raw: str) -> float:
    value = _parse_number_or_none(raw)
    if value is None:
        raise argparse.ArgumentTypeError(f"must be a finite number >= 0; got '{raw}'")
    return value


def _argparse_positive_cap(raw: str) -> float:
    value = _parse_number_or_none(raw)
    if value is None or not _is_valid_cost_cap(value):
        raise argparse.ArgumentTypeError(f"must be a finite number > 0; got '{raw}'")
    return value


def _argparse_ascii_int(raw: str) -> int:
    value = _parse_ascii_int(raw)
    if value is None:
        raise argparse.ArgumentTypeError(f"must be an integer; got '{raw}'")
    return value


def _argparse_positive_int(raw: str) -> int:
    value = _parse_ascii_int(raw)
    if value is None or value < 1:
        raise argparse.ArgumentTypeError(f"must be an integer >= 1; got '{raw}'")
    return value


def _argparse_int_between(low: int, high: int) -> Callable[[str], int]:
    def convert(raw: str) -> int:
        value = _parse_ascii_int(raw)
        if value is None or not low <= value <= high:
            raise argparse.ArgumentTypeError(
                f"must be an integer between {low} and {high}; got '{raw}'"
            )
        return value

    return convert


def _argparse_step_id(raw: str) -> str:
    if not STEP_ID_RE.fullmatch(raw):
        raise argparse.ArgumentTypeError(f"must look like N.M; got '{raw}'")
    return raw


def _argparse_non_blank(raw: str) -> str:
    if not raw.strip():
        raise argparse.ArgumentTypeError("must not be empty or blank")
    return raw


def _cmd_validate_flags(args: argparse.Namespace) -> int:
    return _emit_or_fail(
        lambda: validate_flags(args.candidates, args.max_cost_usd, args.jobs),
        {FlagError: EXIT_USAGE},
    )


def _cmd_project(args: argparse.Namespace) -> int:
    return _emit_or_fail(
        lambda: project(
            args.cap, args.spent, args.completed, args.remaining, args.last_batch_delta
        ),
        {},
    )


def _cmd_collect(args: argparse.Namespace) -> int:
    return _emit_or_fail(
        lambda: collect(
            candidate_id=args.id,
            branch=args.branch,
            worktree=args.worktree,
            base=args.base,
            suite_exit=args.suite_exit,
            spec_json=args.spec_json,
            correctness_json=args.correctness_json,
            plan=args.plan,
            step=args.step,
            cost_usd=args.cost_usd,
        ),
        {DataError: EXIT_INVALID_DATA},
    )


def _cmd_rank(args: argparse.Namespace) -> int:
    return _emit_or_fail(
        lambda: rank(load_candidates(args.candidates_json)),
        {DataError: EXIT_INVALID_DATA},
    )


def _cmd_reconcile(args: argparse.Namespace) -> int:
    return _emit_or_fail(
        lambda: reconcile(
            repo=args.repo,
            into=args.into,
            base=args.base,
            test_cmd=args.test_cmd,
            branch=args.branch,
        ),
        {RestoreFailedError: EXIT_RESTORE_FAILED, DataError: EXIT_INVALID_DATA},
        lambda result: EXIT_OK if result["merged"] else EXIT_NOT_MERGED,
    )


def _cmd_cleanup(args: argparse.Namespace) -> int:
    return _emit_or_fail(
        lambda: cleanup(repo=args.repo, branches=args.remove),
        {DataError: EXIT_INVALID_DATA},
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="build_candidates.py", description="Candidate lifecycle for /build."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    flags = sub.add_parser("validate-flags", help="validate the raw /build flags")
    flags.add_argument("--candidates", help="raw --candidates value from /build")
    flags.add_argument("--max-cost-usd", help="raw --max-cost-usd value from /build")
    flags.add_argument("--jobs", help="raw --jobs value from /build")
    flags.set_defaults(handler=_cmd_validate_flags)

    collecting = sub.add_parser("collect", help="measure and screen one candidate")
    collecting.add_argument(
        "--id", required=True, type=_argparse_positive_int, help="candidate id"
    )
    collecting.add_argument("--branch", required=True, help="candidate branch name")
    collecting.add_argument(
        "--worktree", required=True, help="path of the candidate worktree"
    )
    collecting.add_argument(
        "--base", required=True, help="commit the candidate branched from"
    )
    collecting.add_argument(
        "--suite-exit",
        required=True,
        type=_argparse_ascii_int,
        help="exit code of the plan's suite run in the worktree",
    )
    collecting.add_argument(
        "--spec-json", required=True, help="spec-compliance-review JSON output file"
    )
    collecting.add_argument(
        "--correctness-json",
        required=True,
        help="correctness-review JSON output file",
    )
    collecting.add_argument("--plan", required=True, help="plan file path")
    collecting.add_argument(
        "--step",
        required=True,
        type=_argparse_step_id,
        help="plan step the candidate implements, as N.M",
    )
    collecting.add_argument(
        "--cost-usd",
        required=True,
        type=_argparse_finite_non_negative,
        help="dispatch cost attributed to this candidate, in dollars",
    )
    collecting.set_defaults(handler=_cmd_collect)

    reconciling = sub.add_parser(
        "reconcile",
        help="merge a candidate branch; restore the build branch on failure",
    )
    reconciling.add_argument("--repo", required=True, help="path of the build worktree")
    reconciling.add_argument(
        "--into", required=True, help="build branch the worktree must be on"
    )
    reconciling.add_argument(
        "--base", required=True, help="commit the candidates branched from"
    )
    reconciling.add_argument(
        "--test-cmd",
        required=True,
        type=_argparse_non_blank,
        help="suite command that must pass after the merge",
    )
    reconciling.add_argument("branch", help="candidate branch to merge")
    reconciling.set_defaults(handler=_cmd_reconcile)

    cleaning = sub.add_parser(
        "cleanup", help="remove candidate branches and their worktrees"
    )
    cleaning.add_argument("--repo", required=True, help="path of the build worktree")
    cleaning.add_argument(
        "--remove",
        required=True,
        nargs="+",
        metavar="BRANCH",
        help="candidate branches to remove, with their worktrees",
    )
    cleaning.set_defaults(handler=_cmd_cleanup)

    ranking = sub.add_parser("rank", help="rank candidates and pick a winner")
    ranking.add_argument(
        "--candidates-json",
        required=True,
        help='JSON file holding {"candidates": [...]}',
    )
    ranking.set_defaults(handler=_cmd_rank)

    projection = sub.add_parser(
        "project", help="decide whether to dispatch another batch"
    )
    projection.add_argument(
        "--cap",
        required=True,
        type=_argparse_positive_cap,
        help="spend cap in dollars",
    )
    projection.add_argument(
        "--spent",
        required=True,
        type=_argparse_finite_non_negative,
        help="dollars spent so far",
    )
    projection.add_argument(
        "--completed",
        required=True,
        type=_argparse_int_between(1, MAX_CANDIDATES),
        help=f"candidates dispatched so far (1..{MAX_CANDIDATES})",
    )
    projection.add_argument(
        "--remaining",
        required=True,
        type=_argparse_int_between(1, MAX_CANDIDATES - 1),
        help=f"candidates still to dispatch (1..{MAX_CANDIDATES - 1})",
    )
    projection.add_argument(
        "--last-batch-delta",
        required=True,
        type=_argparse_finite_non_negative,
        help="dollars the last batch spent",
    )
    projection.set_defaults(handler=_cmd_project)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
