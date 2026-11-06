"""Pre-PR acceptance-examination gate (#2270).

`check_acceptance_examination` is the one pure status function: given a record
(or its absence) and the current `Binding` (branch hash and plan-inputs
digest), it returns zero or one issue; `is_stale` is the one staleness rule. `progress_guardian --pre-pr` calls it
through `load_and_check`; the `acceptance_examination.py status` CLI reuses it,
so every caller shows the same text.

Precedence when several conditions hold: exempt, absent, unreadable, other
plan, older than `after`, base unresolvable (current binding), empty diff
(current binding), stale diff, stale inputs, then the record's verdict
(not-met, indeterminate, tainted). A record stored with a sentinel hash is
stale once the current binding resolves, so it is re-dispatchable. Exactly
one issue is returned. A caller passes `after` (an ISO 8601 time) to say "only
a record written after this moment counts": a record whose `recorded_at` is
missing, unparsable, or not strictly newer is reported absent. Message text
lives in `_MESSAGES`, keyed by condition id, and is copied from the plan's
`## Refusal messages` table.

`info` issues are non-blocking; callers keep only `error` rows as failures.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
_HOOKS_LIB_DIR = _SCRIPTS_DIR.parent / "hooks" / "lib"
for _entry in (_SCRIPTS_DIR, _HOOKS_LIB_DIR):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

from examination_inputs import is_exempt  # type: ignore[import-not-found]
from examination_store import (  # type: ignore[import-not-found]
    BASE_UNRESOLVABLE,
    EMPTY_DIFF,
    Binding,
    NotARepository,
    RecordUnreadable,
    binding_for_plan,
    canonical_plan_id,
    is_binding_hash,
    load_record,
    record_path,
    repo_root,
)
from examination_verdict import (  # type: ignore[import-not-found]
    INDETERMINATE,
    MET,
    NOT_MET,
    PROBLEM_BASE_UNRESOLVABLE,
    PROBLEM_COMMAND_NOT_RUN,
    PROBLEM_DUPLICATE,
    PROBLEM_EMPTY_DIFF,
    PROBLEM_INCOMPLETE_ROW,
    PROBLEM_INVALID_SHAPE,
    PROBLEM_INVALID_VERDICT,
    PROBLEM_MISSING,
    PROBLEM_NO_CRITERIA,
    PROBLEM_UNKNOWN,
    PROBLEM_UNPARSEABLE,
    TAINTED,
    parse_problem,
)
from lib.review_result import make_issue

SEVERITY_ERROR = "error"
SEVERITY_INFO = "info"
#: Longest observation line shown in a refusal message or the rendered section.
OBSERVATION_CHAR_LIMIT = 500
_CLIP_MARKER = "…"

RULE_MISSING = "examination-missing"
RULE_UNREADABLE = "examination-unreadable"
RULE_OTHER_PLAN = "examination-other-plan"
RULE_BASE_UNRESOLVABLE = "examination-base-unresolvable"
RULE_EMPTY_DIFF = "examination-empty-diff"
RULE_STALE_DIFF = "examination-stale-diff"
RULE_STALE_INPUTS = "examination-stale-inputs"
RULE_NOT_MET = "examination-not-met"
RULE_UNOBSERVABLE = "examination-unobservable"
RULE_MALFORMED = "examination-malformed"
RULE_TAINTED = "examination-tainted"
RULE_NOT_APPLICABLE = "examination-not-applicable"
RULE_CANNOT_CHECK = "examination-cannot-check"

_RERUN = "Run: /build {plan}; it re-runs the examiner."
_RUN_BUILD = "Run: /build {plan}."
_MALFORMED_REMEDY_AGAIN = "Run: /build {plan} again without changing the plan."
_MALFORMED_REMEDY_NO_CRITERIA = (
    "Add acceptance criteria to the plan, then run: /build {plan}."
)
_REMEDY_COMMIT = "Commit your changes, then run: /build {plan}."
_REMEDY_FETCH = (
    "Fetch the default branch (git fetch origin && git remote set-head origin -a), "
    "then run: /build {plan}."
)

# condition id -> (text template, remedy template)
_MESSAGES: dict[str, tuple[str, str]] = {
    RULE_MISSING: (
        (
            "Acceptance examination missing for {plan}: no record at {path}. "
            "The examiner has not run on this branch."
        ),
        "Run: /build {plan} (Step 7.6 examines the plan).",
    ),
    RULE_UNREADABLE: (
        "Acceptance examination record unreadable: {path} ({problem}).",
        "Delete the file, then run: /build {plan}.",
    ),
    RULE_OTHER_PLAN: (
        "Acceptance examination record at {path} belongs to {other}, not {plan}.",
        _RUN_BUILD,
    ),
    RULE_BASE_UNRESOLVABLE: (
        (
            "Acceptance examination cannot be verified: "
            "the branch base could not be resolved."
        ),
        _REMEDY_FETCH,
    ),
    RULE_EMPTY_DIFF: (
        (
            "Acceptance examination cannot run: this branch has no commits ahead of "
            "the branch base, so there is nothing to examine."
        ),
        _REMEDY_COMMIT,
    ),
    RULE_STALE_DIFF: (
        "Acceptance examination is out of date: commits landed after it ran.",
        _RERUN,
    ),
    RULE_STALE_INPUTS: (
        (
            "Acceptance examination is out of date: the plan's acceptance criteria, "
            "Gherkin, or run commands changed after it ran."
        ),
        _RERUN,
    ),
    RULE_NOT_MET: (
        "Acceptance criteria not met: {ids}. {details}.",
        "Fix the delivered behavior, commit, then run: /build {plan}.",
    ),
    RULE_UNOBSERVABLE: (
        (
            "Acceptance examination inconclusive: the examiner could not observe "
            "{ids}. {details}."
        ),
        (
            "Make each criterion observable (name a run command in the plan or "
            "reword it), then run: /build {plan}."
        ),
    ),
    RULE_MALFORMED: (
        (
            "Acceptance examination inconclusive: the examiner's result was "
            "incomplete. {glosses}."
        ),
        "{remedy}",
    ),
    RULE_TAINTED: (
        (
            "Acceptance examination cannot be trusted: the examiner ran commands it "
            "must not ({commands}). Detection is by pattern and may be a false "
            'positive; "acceptance_examination.py show --plan {plan}" prints the '
            "full record."
        ),
        (
            "Name a run command for each criterion in the plan so the examiner has "
            "no reason to explore, then run: /build {plan}."
        ),
    ),
    RULE_NOT_APPLICABLE: (
        (
            "Acceptance examination not applicable: the plan declares "
            "Examination: not-applicable."
        ),
        "",
    ),
    RULE_CANNOT_CHECK: (
        "Acceptance examination cannot run: {problem}.",
        "Run from a git checkout that contains the plan, then run: /build {plan}.",
    ),
}

# problem kind -> gloss template; `{ids}` is the criterion id list, `{id}` the first id
_GLOSSES: dict[str, str] = {
    PROBLEM_MISSING: "no row for {ids}",
    PROBLEM_DUPLICATE: "{id} has more than one row",
    PROBLEM_UNKNOWN: "{id} is not a criterion in the plan",
    PROBLEM_INCOMPLETE_ROW: "{id} has no observation or no command",
    PROBLEM_INVALID_VERDICT: "{id} has a verdict that is not met, not-met, or indeterminate",
    PROBLEM_COMMAND_NOT_RUN: "{id} names a command it never ran",
    PROBLEM_INVALID_SHAPE: "the result did not have the expected shape",
    PROBLEM_UNPARSEABLE: "the result could not be parsed",
    PROBLEM_NO_CRITERIA: "the plan lists no acceptance criteria",
    PROBLEM_BASE_UNRESOLVABLE: "the branch base could not be resolved",
    PROBLEM_EMPTY_DIFF: "the branch has no commits ahead of its base",
}

_BINDING_RULES = {
    BASE_UNRESOLVABLE: RULE_BASE_UNRESOLVABLE,
    EMPTY_DIFF: RULE_EMPTY_DIFF,
}
_MAX_LISTED_COMMANDS = 3
_NO_OBSERVATION = "(no observation recorded)"


def parse_timestamp(text: object) -> datetime | None:
    """`text` as a timezone-aware time, or `None` when it is not ISO 8601.

    Python 3.10's `fromisoformat` rejects a trailing `Z`, so it is read as
    `+00:00`. A time without an offset is read as UTC.
    """
    if not isinstance(text, str):
        return None
    normalised = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalised)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _is_newer_than(record: dict, after: datetime) -> bool:
    """True when `record["recorded_at"]` parses and is strictly after `after`."""
    recorded = parse_timestamp(record.get("recorded_at"))
    return recorded is not None and recorded > after


def refusal_message(rule: str, plan_id: str, **fields: object) -> str:
    """The message text for `rule` from the one message table."""
    return _MESSAGES[rule][0].format(plan=plan_id, **fields)


def _issue(
    rule: str, plan_id: str, severity: str = SEVERITY_ERROR, **fields: object
) -> dict:
    return make_issue(
        severity=severity,
        file=plan_id,
        message=refusal_message(rule, plan_id, **fields),
        suggested_fix=_MESSAGES[rule][1].format(plan=plan_id, **fields),
        rule_id=rule,
    )


def blocking_issues(issues: list[dict]) -> list[dict]:
    """The issues that refuse the gate; `info` issues never do."""
    return [issue for issue in issues if issue["severity"] == SEVERITY_ERROR]


def clip_line(text: str) -> str:
    """`text` cut to `OBSERVATION_CHAR_LIMIT` characters, marked when cut."""
    if len(text) <= OBSERVATION_CHAR_LIMIT:
        return text
    return text[:OBSERVATION_CHAR_LIMIT] + _CLIP_MARKER


def _first_line(value: object) -> str:
    lines = str(value or "").strip().splitlines()
    return clip_line(lines[0].strip()) if lines else _NO_OBSERVATION


def _rows_with_verdict(record: dict, verdict: str) -> list[dict]:
    rows = record.get("criteria") or []
    return [r for r in rows if isinstance(r, dict) and r.get("verdict") == verdict]


def _row_fields(rows: list[dict]) -> dict:
    pairs = [
        (str(row.get("criterion")), _first_line(row.get("observation"))) for row in rows
    ]
    return {
        "ids": ", ".join(cid for cid, _ in pairs),
        "details": ". ".join(f"{cid}: {line}" for cid, line in pairs),
    }


def _gloss(problem: str) -> str:
    kind, ids = parse_problem(str(problem))
    template = _GLOSSES.get(kind)
    if template is None:
        return str(problem)
    first_id = ids[0] if ids else ""
    return template.format(id=first_id, ids=first_id.replace(",", ", "))


def _malformed_fields(problems: list, plan_id: str) -> dict:
    kinds = {parse_problem(str(p))[0] for p in problems}
    if PROBLEM_NO_CRITERIA in kinds:
        remedy = _MALFORMED_REMEDY_NO_CRITERIA
    else:
        remedy = _MALFORMED_REMEDY_AGAIN
    return {
        "glosses": "; ".join(_gloss(p) for p in problems),
        "remedy": remedy.format(plan=plan_id),
    }


def _tainted_fields(record: dict) -> dict:
    findings = record.get("audit_findings") or []
    commands = [
        str(f["command"]) for f in findings if isinstance(f, dict) and f.get("command")
    ]
    listed = "; ".join(commands[:_MAX_LISTED_COMMANDS])
    extra = len(commands) - _MAX_LISTED_COMMANDS
    return {"commands": f"{listed} (+{extra} more)" if extra > 0 else listed}


def _verdict_refusal(record: dict, plan_id: str) -> tuple[str, dict] | None:
    overall = record.get("overall")
    if overall == MET:
        return None
    if overall == NOT_MET:
        return RULE_NOT_MET, _row_fields(_rows_with_verdict(record, NOT_MET))
    if overall == TAINTED:
        return RULE_TAINTED, _tainted_fields(record)
    problems = record.get("problems") or []
    if problems:
        return RULE_MALFORMED, _malformed_fields(problems, plan_id)
    return RULE_UNOBSERVABLE, _row_fields(_rows_with_verdict(record, INDETERMINATE))


def stale_rule(record: dict, binding: Binding) -> str | None:
    """The staleness rule `record` trips against `binding`, or `None`.

    A hash that is not a binding hash (a sentinel such as `BASE_UNRESOLVABLE`
    or `EMPTY_DIFF`) on either side is always stale, even when both sides hold
    the same sentinel: a sentinel says "no hash was available", not "the diff
    is unchanged". The gate reports `RULE_STALE_DIFF` and `/build`
    re-dispatches the examiner. When the current binding is itself a
    sentinel, `_refusal` returns that sentinel's rule before this function
    runs.
    """
    stored = record.get("binding_hash")
    if not (is_binding_hash(stored) and is_binding_hash(binding.hash)):
        return RULE_STALE_DIFF
    if stored != binding.hash:
        return RULE_STALE_DIFF
    if record.get("inputs_digest") != binding.inputs_digest:
        return RULE_STALE_INPUTS
    return None


def is_stale(record: dict, binding: Binding) -> bool:
    """True when the branch diff or the plan's inputs moved since `record`."""
    return stale_rule(record, binding) is not None


def _refusal(
    plan_id: str,
    record: dict | RecordUnreadable | None,
    path: Path | str,
    binding: Binding,
    after: datetime | None = None,
) -> tuple[str, dict] | None:
    if record is None:
        return RULE_MISSING, {"path": path}
    if isinstance(record, RecordUnreadable):
        return RULE_UNREADABLE, {"path": path, "problem": record.problem}
    if record.get("plan") != plan_id:
        return RULE_OTHER_PLAN, {"path": path, "other": record.get("plan")}
    if after is not None and not _is_newer_than(record, after):
        return RULE_MISSING, {"path": path}
    if binding.hash in _BINDING_RULES:
        return _BINDING_RULES[binding.hash], {}
    if stale := stale_rule(record, binding):
        return stale, {}
    return _verdict_refusal(record, plan_id)


def check_acceptance_examination(
    plan_id: str,
    record: dict | RecordUnreadable | None,
    path: Path | str,
    binding: Binding,
    exempt: bool,
    after: datetime | None = None,
) -> list[dict]:
    """Zero or one issue for `plan_id`; see the module docstring for precedence.

    `binding.hash` is the current branch hash, or `BASE_UNRESOLVABLE` /
    `EMPTY_DIFF`. An exempt plan yields one non-blocking `info` issue. With
    `after`, a record not written strictly after it counts as absent.
    """
    if exempt:
        return [_issue(RULE_NOT_APPLICABLE, plan_id, severity=SEVERITY_INFO)]
    refusal = _refusal(plan_id, record, path, binding, after)
    if refusal is None:
        return []
    rule, fields = refusal
    return [_issue(rule, plan_id, **fields)]


def _cannot_check(plan_path: Path | str, problem: str) -> list[dict]:
    return [_issue(RULE_CANNOT_CHECK, str(plan_path), problem=problem)]


def load_and_check(
    plan_path: Path | str,
    *,
    after: str | None = None,
    binding: Binding | None = None,
) -> list[dict]:
    """Check the plan at `plan_path` against its record in the plan's repo.

    `after` is an ISO 8601 time; see the module docstring. A value that does
    not parse is a caller bug and raises `ValueError`; every other failure
    becomes one error issue, never an exception. `binding` is a precomputed
    current binding for this plan: a caller that checks the same plan
    repeatedly (a poll loop) computes it once, and the call reuses its
    branch-diff hash and inputs digest. The repository root and plan id are
    still resolved on each call, the record is re-read, and the plan text is
    read only for the exemption check
    (and to compute the binding when none is supplied).
    """
    after_time = None
    if after is not None:
        after_time = parse_timestamp(after)
        if after_time is None:
            raise ValueError(f"not an ISO 8601 time: {after!r}")
    try:
        root = repo_root(plan_path)
        plan_id = canonical_plan_id(plan_path, root)
        plan_text = Path(plan_path).read_text(encoding="utf-8")
    except NotARepository:
        return _cannot_check(plan_path, "not a git repository")
    except (ValueError, OSError, UnicodeDecodeError) as exc:
        return _cannot_check(plan_path, f"the plan could not be read ({exc})")
    path = record_path(root, plan_id)
    return check_acceptance_examination(
        plan_id,
        load_record(path),
        path,
        binding if binding is not None else binding_for_plan(root, plan_id, plan_text),
        is_exempt(plan_text),
        after_time,
    )
