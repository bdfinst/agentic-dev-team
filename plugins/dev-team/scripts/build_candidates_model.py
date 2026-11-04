"""build_candidates_model.py — candidate data model and ranking.

The pure half of the candidate lifecycle: the `FlagError` and `DataError`
types every `build_candidates` module shares, JSON input loading, the
`Candidate` record with its field validation and its screening rule, and
`rank`. No git, no subprocess. The git-facing errors, `GitError` and
`RestoreFailedError`, live in `build_candidates_git`, which raises them.

Stdlib only (ADR 0014, ADR 0015, ADR 0031).
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

SCREENING_OK = "ok"
SCREENING_UNPARSEABLE_PREFIX = "unparseable: "

LENS_SPEC_COMPLIANCE = "spec-compliance-review"
LENS_CORRECTNESS = "correctness-review"
_UNMET_SCENARIO_CATEGORIES = frozenset({"uncovered-scenario", "unmet-criterion"})

_REASON_RED_SUITE = "red suite"

#: A plan step id, `N.M`: digits, a dot, digits.
STEP_ID_RE = re.compile(r"[0-9]+\.[0-9]+")


class FlagError(ValueError):
    """A `/build` flag combination that validate-flags rejects (exit 2)."""


class DataError(ValueError):
    """Input data a subcommand rejects (exit 1)."""


def load_json_object(path: str, label: str) -> dict:
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
    except (ValueError, RecursionError) as exc:
        raise DataError(f"{label}: not JSON: {path}: {exc}") from None
    if not isinstance(data, dict):
        raise DataError(f"{label}: JSON root is not an object: {path}")
    return data


def _reject(label: str, message: str) -> NoReturn:
    raise ValueError(f"{label}: {message}")


def _is_plain_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_plain_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_finite_non_negative(value: object) -> bool:
    """A real number that is finite and >= 0; an int too large for a float
    counts as not finite."""
    if not _is_plain_number(value):
        return False
    try:
        return math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def _is_valid_screening(value: object) -> bool:
    if value == SCREENING_OK:
        return True
    return (
        isinstance(value, str)
        and value.startswith(SCREENING_UNPARSEABLE_PREFIX)
        and len(value) > len(SCREENING_UNPARSEABLE_PREFIX)
    )


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
        candidate_id = data.get("id")
        if not (_is_plain_int(candidate_id) and candidate_id >= 1):
            _reject(f"candidate {candidate_id!r}", "id must be a positive int")
        label = f"candidate {candidate_id}"

        def field(name: str) -> object:
            if name not in data:
                _reject(label, f"{name} is missing")
            return data[name]

        def count(name: str) -> int:
            value = field(name)
            if not (_is_plain_int(value) and value >= 0):
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
        if not _is_finite_non_negative(cost):
            _reject(label, "cost_usd must be a finite non-negative number")
        screening = field("screening")
        if not _is_valid_screening(screening):
            _reject(
                label,
                f"screening must be '{SCREENING_OK}' or "
                f"'{SCREENING_UNPARSEABLE_PREFIX}<lens>'",
            )
        return cls(
            id=candidate_id,
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

    @classmethod
    def no_commits(
        cls, candidate_id: int, branch: str, scenarios_total: int, cost_usd: float
    ) -> Candidate:
        """A candidate whose dispatch left no commit beyond the base: red
        suite, every scenario unmet, no findings, zero diff. The model gives
        it the ordinary `red suite` reason; the skill supplies `no commits`
        when it records the row (plan decision 3)."""
        return cls.from_dict(
            {
                "id": candidate_id,
                "branch": branch,
                "suite_green": False,
                "scenarios_total": scenarios_total,
                "scenarios_unmet": scenarios_total,
                "errors": 0,
                "warnings": 0,
                "diff_lines": 0,
                "cost_usd": cost_usd,
                "screening": SCREENING_OK,
            }
        )

    @classmethod
    def from_screening(
        cls,
        candidate_id: int,
        branch: str,
        suite_exit: int,
        scenarios_total: int,
        diff_lines: int,
        cost_usd: float,
        spec_issues: Sequence[dict] | None,
        correctness_issues: Sequence[dict] | None,
    ) -> Candidate:
        """Build a candidate from a suite exit code, measurements and the two
        review-lens issue lists (None marks an unparseable lens). Unmet
        findings are clamped to `scenarios_total`; the first unparseable lens
        in (spec-compliance, correctness) order names the screening."""
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
            if issue.get("category") in _UNMET_SCENARIO_CATEGORIES
        )

        def severity_count(severity: str) -> int:
            return sum(
                1
                for issue in correctness_issues or []
                if issue.get("severity") == severity
            )

        return cls.from_dict(
            {
                "id": candidate_id,
                "branch": branch,
                "suite_green": suite_exit == 0,
                "scenarios_total": scenarios_total,
                "scenarios_unmet": min(scenarios_total, unmet),
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
        )

    @property
    def is_disqualified(self) -> bool:
        return (not self.suite_green) or self.screening != SCREENING_OK

    @property
    def scenarios_met(self) -> int:
        return self.scenarios_total - self.scenarios_unmet

    @property
    def rank_key(self) -> tuple:
        """Qualified first, then more scenarios met, fewer errors, fewer
        warnings, fewer diff lines, lower id. cost_usd never participates."""
        return (
            self.is_disqualified,
            -self.scenarios_met,
            self.errors,
            self.warnings,
            self.diff_lines,
            self.id,
        )

    @property
    def disqualification_reason(self) -> str:
        """Why the candidate cannot win; empty when it can."""
        if not self.suite_green:
            return _REASON_RED_SUITE
        if self.screening != SCREENING_OK:
            lens = self.screening[len(SCREENING_UNPARSEABLE_PREFIX) :]
            return f"screening: {lens} unparseable"
        return ""


def disqualified(candidate: Candidate) -> bool:
    return candidate.is_disqualified


def scenarios_met(candidate: Candidate) -> int:
    return candidate.scenarios_met


def sort_key(candidate: Candidate) -> tuple:
    return candidate.rank_key


def rank(candidates: Sequence[Candidate]) -> dict:
    """Order candidates by `rank_key`; the winner is the first unless it is
    disqualified."""
    ordered = sorted(candidates, key=sort_key)
    winner = ordered[0] if ordered and not ordered[0].is_disqualified else None
    return {
        "disqualified": sorted(c.id for c in candidates if c.is_disqualified),
        "order": [c.id for c in ordered],
        "rank": {str(c.id): position for position, c in enumerate(ordered, start=1)},
        "reasons": {str(c.id): c.disqualification_reason for c in ordered},
        "scenarios_met": {str(c.id): c.scenarios_met for c in ordered},
        "winner": None if winner is None else winner.id,
    }


def load_candidates(path: str) -> list[Candidate]:
    """The candidates of a `{"candidates": [...]}` file; raise DataError
    prefixed `rank:` for anything unreadable, empty, invalid or duplicated."""
    data = load_json_object(path, "rank")
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
