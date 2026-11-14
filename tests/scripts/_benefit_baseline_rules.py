"""Rules that keep the ``baseline`` cells of the benefit pre-registration honest.

Each metric's ``baseline`` cell in ``docs/benefit-eval/preregistration.md`` begins with one status token
(``<token>: <text>``). The rules here check the token and its pinned assignment, the verdict-order text that
follows from it, the record behind a ``measured`` baseline, the absence of private paths, and the frozen
thresholds. Every rule is ``check(ctx, findings)`` over one ``Context``, so a rule runs once against the real
document and again against a synthetic ``Context`` that breaks it. Named without a leading ``test_`` so pytest
does not collect it; the tests are in ``test_benefit_baseline_status.py``.
"""

from __future__ import annotations

import getpass
import json
import re
import subprocess
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from lane_fixtures import git_env, git_succeeds

from _repo_root import REPO_ROOT

#: The status vocabulary, pinned so a change to the document's status table is deliberate.
ALLOWED_TOKENS = (
    "by-definition",
    "measured",
    "forward-captured",
    "no-reference",
    "unmeasurable",
)

#: Reasons a `no-reference` cell may give for a metric that could hold a record.
REASONS = (
    "not-yet-run",
    "tool-unavailable",
    "fixture-missing",
    "cost-declined",
    "commit-unreproducible",
)

PBT = "pbt-mutants-killed"
TR_TP = "test-review-tp-change"

#: The deliberate status of each metric. A downgrade edits this map in the same commit as the cell.
PINNED_STATUS = {
    "skip-rate": "by-definition",
    "findings-parity": "by-definition",
    "injection-overhead": "by-definition",
    "guard-false-positive": "by-definition",
    PBT: "measured",
    TR_TP: "no-reference",
    "injection-uptake": "forward-captured",
    "test-review-token-delta": "forward-captured",
    "abort-yield": "no-reference",
    "guard-divergence": "no-reference",
    "contradicted-rate": "no-reference",
    "expand-rate": "no-reference",
    "report-size-cut": "unmeasurable",
}

#: Metrics whose baseline a replayed record can back; their `no-reference` cells must give a reason.
RECORD_CAPABLE = (PBT, TR_TP)

#: The follow-up issue each blocked or unmeasurable cell must cite.
ISSUE_CITES = {
    "skip-rate": 2306,
    "abort-yield": 2306,
    "expand-rate": 2307,
    "report-size-cut": 2308,
}

NO_VERDICT_STATUSES = ("no-reference", "unmeasurable")

#: keep, tune, retire and minimum_n of every metric as merged at commit 02201d4d, so a threshold cannot move
#: in this change. Rows for ids missing from PINNED_STATUS are ignored; a pinned id with no row fails at import.
_MERGED_THRESHOLDS = {
    "skip-rate": (">= 10", "< 10", "< 3", 10),
    "findings-parity": ("<= 0", "<= 2", ">= 3", 3),
    "abort-yield": ("<= 25", "> 25", "> 60", 10),
    TR_TP: (">= 0", "< 0", "< -10", 10),
    "test-review-token-delta": ("<= -15", "> -15", "> 0", 10),
    "expand-rate": ("<= 20", "> 20", "> 50", 10),
    "report-size-cut": (">= 40", "< 40", "< 15", 10),
    "injection-overhead": ("<= 400", "> 400", "> 1200", 10),
    "injection-uptake": (">= 50", "< 50", "< 10", 10),
    "guard-divergence": (">= 2", "< 2", "< 0.5", 10),
    "guard-false-positive": ("<= 5", "> 5", "> 30", 10),
    "contradicted-rate": (">= 0.2", "< 0.2", "< 0.05", 10),
    PBT: (">= 1", "< 1", "<= 0", 10),
}
PINNED_THRESHOLDS = {
    metric_id: _MERGED_THRESHOLDS[metric_id] for metric_id in PINNED_STATUS
}
THRESHOLD_FIELDS = ("keep", "tune", "retire", "minimum_n")

VERDICT_MARKER = "**Verdict order.**"
RECORDS_DIR = ".dev-team-reports/baselines"
RECORD_PATH = re.compile(r"\.dev-team-reports/baselines/[^\s;,)`'\"]+")
SHA = re.compile(r"[0-9a-f]{40}")

#: Absolute locations and transcript directories that must not appear in a committed file. The root forms
#: match only where a path starts, so a repo-relative `docs/users/` stays valid.
PRIVATE_PATH = re.compile(
    r"(?<![\w.\\-])(?:/Users/|/home/|/root/|/tmp/|/var/folders/|/private/var/|/private/tmp/|[A-Za-z]:\\{1,2}Users\\)"
    r"|\.claude/projects/",
    re.IGNORECASE,
)


@dataclass
class Findings:
    """What a rule found: problems fail the run; skips name a check that could not run and why."""

    problems: list[str] = field(default_factory=list)
    skips: list[str] = field(default_factory=list)

    def report(self) -> str:
        return "\n".join(self.problems)


@dataclass
class Context:
    """Everything a rule may read. `pinned` is injectable so a downgrade needs no global patch."""

    entries: dict[str, dict]
    doc_text: str = ""
    repo_root: Path | None = None
    usernames: tuple[str, ...] = ()
    pinned: Mapping[str, str] = field(default_factory=lambda: PINNED_STATUS)


Check = Callable[[Context, Findings], None]


def run_checks(ctx: Context, *checks: Check) -> Findings:
    findings = Findings()
    for check in checks:
        check(ctx, findings)
    return findings


def problems_for(ctx: Context, *checks: Check) -> list[str]:
    return run_checks(ctx, *checks).problems


# --- baseline cells --------------------------------------------------------------------------------------


def split_baseline(cell: str) -> tuple[str | None, str, str | None]:
    """The (token, text, problem) of a `<token>: <text>` cell; problem is None when the form is valid."""
    if re.match(r"(none|tbd)\b", cell.strip(), re.IGNORECASE):
        return None, "", "begins with 'none' or 'TBD'"
    token, separator, text = cell.partition(": ")
    if not separator:
        return None, "", "has no '<token>: <text>' form"
    if token not in ALLOWED_TOKENS:
        return None, "", f"unknown token {token!r}"
    if not text.strip():
        return token, "", "has an empty text after the token"
    if re.match(rf"({'|'.join(ALLOWED_TOKENS)})\s*:", text.lstrip(), re.IGNORECASE):
        return token, text, "carries two status tokens"
    return token, text, None


def cell_token(entry: dict) -> str | None:
    token, _, problem = split_baseline(entry["baseline"])
    return None if problem else token


def _status_mismatch(
    metric_id: str, token: str, text: str, expected: str
) -> str | None:
    """Why a well-formed cell disagrees with the pinned status, or None when it agrees."""
    if token == "no-reference" and metric_id in RECORD_CAPABLE:
        reason = text.split(";", 1)[0].strip() if ";" in text else ""
        if reason not in REASONS:
            return f"reason {reason!r} is not one of {', '.join(REASONS)}"
        if expected == "measured" and reason != "not-yet-run":
            return (
                "pinned status is measured, so only 'not-yet-run' is accepted until a record exists "
                "(a downgrade edits the pinned map)"
            )
        if expected not in ("measured", "no-reference"):
            return f"status {token!r} does not match pinned {expected!r}"
        return None
    if token != expected:
        return f"status {token!r} does not match pinned {expected!r}"
    return None


def check_baseline_cells(ctx: Context, findings: Findings) -> None:
    """Each cell has one allowed token that matches the pinned map; ids equal the pinned ids."""
    for missing in sorted(set(ctx.pinned) - set(ctx.entries)):
        findings.problems.append(
            f"{missing}: metric is pinned but absent from the pre-registration"
        )
    for extra in sorted(set(ctx.entries) - set(ctx.pinned)):
        findings.problems.append(
            f"{extra}: metric is registered but has no pinned status"
        )
    for metric_id in sorted(set(ctx.entries) & set(ctx.pinned)):
        token, text, problem = split_baseline(ctx.entries[metric_id]["baseline"])
        if problem:
            findings.problems.append(
                f"{metric_id}.baseline: {problem}; allowed tokens: {', '.join(ALLOWED_TOKENS)}"
            )
            continue
        mismatch = _status_mismatch(metric_id, token, text, ctx.pinned[metric_id])
        if mismatch:
            findings.problems.append(f"{metric_id}.baseline: {mismatch}")


def check_unmeasurable_matches_handling(ctx: Context, findings: Findings) -> None:
    """A metric is `unmeasurable` exactly when its `id_less_handling` is `unmeasurable`."""
    for metric_id, entry in sorted(ctx.entries.items()):
        token = cell_token(entry)
        if token is None:
            continue
        if (token == "unmeasurable") != (
            entry.get("id_less_handling") == "unmeasurable"
        ):
            findings.problems.append(
                f"{metric_id}.baseline: status {token!r} disagrees with id_less_handling "
                f"{entry.get('id_less_handling')!r}; unmeasurable holds exactly when handling is unmeasurable"
            )


def check_issue_cites(ctx: Context, findings: Findings) -> None:
    """Cells that wait on a follow-up cite its pinned number; any other unmeasurable cell cites some issue."""
    for metric_id, number in sorted(ISSUE_CITES.items()):
        if metric_id in ctx.entries and not re.search(
            rf"(?<!\d)#{number}(?!\d)", ctx.entries[metric_id]["baseline"]
        ):
            findings.problems.append(f"{metric_id}.baseline: cites no #{number}")
    for metric_id, entry in sorted(ctx.entries.items()):
        uncited = not re.search(r"#\d+", entry["baseline"])
        if (
            metric_id not in ISSUE_CITES
            and cell_token(entry) == "unmeasurable"
            and uncited
        ):
            findings.problems.append(
                f"{metric_id}.baseline: unmeasurable cell cites no follow-up issue (#<number>)"
            )


# --- document text ---------------------------------------------------------------------------------------


def status_table_tokens(doc_text: str) -> list[str]:
    """First-column tokens of the table under the `## Baseline status` heading."""
    section = re.search(
        r"^## Baseline status\s*$(.*?)(?=^## |\Z)", doc_text, re.MULTILINE | re.DOTALL
    )
    if not section:
        return []
    rows = [line for line in section.group(1).splitlines() if line.startswith("|")]
    return [
        row.split("|")[1].strip().strip("`") for row in rows[2:]
    ]  # skip header and divider


def check_status_table(ctx: Context, findings: Findings) -> None:
    tokens = status_table_tokens(ctx.doc_text)
    if sorted(tokens) != sorted(ALLOWED_TOKENS):
        findings.problems.append(
            f"status table: tokens {tokens} differ from the pinned enum {list(ALLOWED_TOKENS)}"
        )


def verdict_paragraph(doc_text: str) -> str | None:
    """The `**Verdict order.**` paragraph under `## Rules`, before the next `## ` heading."""
    rules = re.search(r"^## Rules\s*$", doc_text, re.MULTILINE)
    if not rules:
        return None
    section = doc_text[rules.end() :]
    if next_heading := re.search(r"^## ", section, re.MULTILINE):
        section = section[: next_heading.start()]
    for paragraph in re.split(r"\n\s*\n", section):
        if paragraph.lstrip().startswith(VERDICT_MARKER):
            return paragraph
    return None


def check_verdict_order(ctx: Context, findings: Findings) -> None:
    """The verdict-order paragraph names exactly the no-reference and unmeasurable metrics, and says why."""
    paragraph = verdict_paragraph(ctx.doc_text)
    if paragraph is None:
        findings.problems.append(
            f"verdict order: no '{VERDICT_MARKER}' paragraph under '## Rules'"
        )
        return
    named = {
        metric_id
        for metric_id in ctx.entries
        if re.search(rf"(?<![\w-]){re.escape(metric_id)}(?![\w-])", paragraph)
    }
    expected = {
        metric_id
        for metric_id, entry in ctx.entries.items()
        if cell_token(entry) in NO_VERDICT_STATUSES
    }
    if named != expected:
        findings.problems.append(
            f"verdict order: names {sorted(named)} but the no-reference and unmeasurable metrics are "
            f"{sorted(expected)} (missing {sorted(expected - named)}, extra {sorted(named - expected)})"
        )
    if not re.search(r"no keep, tune, or retire verdict", paragraph, re.IGNORECASE):
        findings.problems.append(
            "verdict order: does not state that no keep, tune, or retire verdict is posted"
        )


# --- records ---------------------------------------------------------------------------------------------


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_string_list(value) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _is_relative_string_list(value) -> bool:
    return _is_string_list(value) and not any(
        re.match(r"([A-Za-z]:)?[\\/]", item) for item in value
    )


def _is_iso_date(value) -> bool:
    try:
        return isinstance(value, str) and bool(date.fromisoformat(value))
    except ValueError:
        return False


def _is_sha(value) -> bool:
    return isinstance(value, str) and bool(SHA.fullmatch(value))


#: field name -> (predicate, what the field must be), for every record.
COMMON_RECORD_FIELDS = {
    "command": (
        lambda value: isinstance(value, str) and bool(value.strip()),
        "a non-empty string",
    ),
    "inputs": (_is_relative_string_list, "a list of repo-relative strings"),
    "commit": (_is_sha, "a 40-hex SHA"),
    "date": (_is_iso_date, "an ISO 8601 date"),
    "value": (_is_number, "a number"),
    "n": (lambda value: _is_int(value) and value >= 0, "an integer >= 0"),
}

#: The fields that only some metrics' records carry.
METRIC_RECORD_FIELDS = {
    PBT: {
        "generated_properties": (lambda value: value is False, "false"),
        "target_ids": (_is_string_list, "a list of strings"),
    },
    TR_TP: {
        "introduced_by_sha": (_is_sha, "a 40-hex SHA"),
        "fixture_ids": (_is_string_list, "a list of strings"),
    },
}


def run_git(repo_root: Path, *args: str) -> subprocess.CompletedProcess:
    """A hermetic git command that never raises: the checks read the return code themselves."""
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        env=git_env(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )


def commit_resolves(repo_root: Path, sha: str) -> bool:
    return git_succeeds(repo_root, "cat-file", "-e", f"{sha}^{{commit}}")


def is_shallow(repo_root: Path) -> bool:
    return (
        run_git(repo_root, "rev-parse", "--is-shallow-repository").stdout.strip()
        == "true"
    )


@dataclass
class LoadedRecord:
    """A record file read once: `data` is None when it does not parse; `text` is empty when unreadable."""

    data: object | None
    text: str
    error: str | None


def load_record(path: Path) -> LoadedRecord:
    try:
        raw = path.read_bytes()
    except OSError as error:
        return LoadedRecord(None, "", str(error))
    try:
        return LoadedRecord(json.loads(raw.decode("utf-8")), raw.decode("utf-8"), None)
    except ValueError as error:
        return LoadedRecord(None, raw.decode("utf-8", errors="replace"), str(error))


def record_files(repo_root: Path | None) -> list[Path]:
    """The benefit records under the repository; none when the context names no repository."""
    directory = repo_root / RECORDS_DIR if repo_root else None
    if directory is None or not directory.is_dir():
        return []
    return sorted(
        path
        for path in directory.iterdir()
        if path.name.lower().startswith("benefit-")
        and path.name.lower().endswith(".json")
    )


def check_measured_cells(ctx: Context, findings: Findings) -> None:
    """A measured cell cites a record path that resolves, and the metric's own record exists."""
    measured = [
        (metric_id, entry)
        for metric_id, entry in sorted(ctx.entries.items())
        if cell_token(entry) == "measured"
    ]
    if measured and ctx.repo_root is None:
        findings.problems.append(
            f"{', '.join(metric_id for metric_id, _ in measured)}: measured cells cannot be checked; "
            "the context names no repository root"
        )
        return
    for metric_id, entry in measured:
        cited = RECORD_PATH.search(entry["baseline"])
        if not cited:
            findings.problems.append(
                f"{metric_id}.baseline: measured cell cites no path under {RECORDS_DIR}/"
            )
        elif not (ctx.repo_root / cited.group().rstrip("/.")).is_file():
            findings.problems.append(
                f"{metric_id}.baseline: cites {cited.group()}, which does not exist"
            )
        if not (ctx.repo_root / RECORDS_DIR / f"benefit-{metric_id}.json").is_file():
            findings.problems.append(
                f"{metric_id}: status is measured but {RECORDS_DIR}/benefit-{metric_id}.json is missing"
            )


def _resolve_commit(
    repo_root: Path, name: str, field_name: str, sha: str, findings: Findings
) -> bool:
    if commit_resolves(repo_root, sha):
        return True
    if is_shallow(repo_root):
        findings.skips.append(
            f"{name}: {field_name} {sha[:8]} is absent from this shallow repository; resolve check skipped"
        )
    else:
        findings.problems.append(
            f"{name}: field {field_name!r} {sha} does not resolve with git cat-file -e"
        )
    return False


def _check_introducing_commit(
    repo_root: Path, name: str, data: dict, findings: Findings
) -> None:
    """The record's `commit` is the parent of `introduced_by_sha`."""
    introduced = data["introduced_by_sha"]
    if not _resolve_commit(repo_root, name, "introduced_by_sha", introduced, findings):
        if is_shallow(repo_root):
            findings.skips.append(
                f"{name}: introduced_by_sha parent check skipped; the commit is absent"
            )
        return
    parent = run_git(repo_root, "rev-parse", f"{introduced}^")
    if parent.returncode != 0 and is_shallow(repo_root):
        findings.skips.append(
            f"{name}: introduced_by_sha parent check skipped; its parent is absent"
        )
    elif parent.stdout.strip() != data["commit"]:
        findings.problems.append(
            f"{name}: field 'commit' is not the parent of introduced_by_sha "
            f"(git rev-parse introduced_by_sha^ gave {parent.stdout.strip() or 'nothing'})"
        )


def _invalid_fields(
    name: str, data: dict, metric_id: str, findings: Findings
) -> set[str]:
    """Report each missing, null or wrongly typed field; return the names reported."""
    invalid: set[str] = set()
    for field_name, (is_valid, expected) in {
        **COMMON_RECORD_FIELDS,
        **METRIC_RECORD_FIELDS.get(metric_id, {}),
    }.items():
        if field_name not in data:
            findings.problems.append(f"{name}: field {field_name!r} is missing")
        elif data[field_name] is None:
            findings.problems.append(f"{name}: field {field_name!r} is null")
        elif not is_valid(data[field_name]):
            findings.problems.append(
                f"{name}: field {field_name!r} is {data[field_name]!r}, expected {expected}"
            )
        else:
            continue
        invalid.add(field_name)
    return invalid


def _check_record(repo_root: Path, path: Path, entry: dict, findings: Findings) -> None:
    """Fields, types, `n` against `minimum_n`, and the commit links of one `measured` record."""
    name, metric_id = path.name, entry["id"]
    loaded = load_record(path)
    if loaded.error:
        findings.problems.append(f"{name}: unparseable record: {loaded.error}")
        return
    data = loaded.data
    if not isinstance(data, dict):
        findings.problems.append(f"{name}: record is not a JSON object")
        return
    if "status" in data:
        findings.problems.append(
            f"{name}: field 'status' is not allowed; status lives in the baseline cell"
        )
    invalid = _invalid_fields(name, data, metric_id, findings)
    if "n" not in invalid and data["n"] < entry["minimum_n"]:
        findings.problems.append(
            f"{name}: field 'n' is {data['n']}, below minimum_n {entry['minimum_n']} for {metric_id}"
        )
    if "commit" not in invalid:
        _resolve_commit(repo_root, name, "commit", data["commit"], findings)
    if "introduced_by_sha" in METRIC_RECORD_FIELDS.get(
        metric_id, {}
    ) and not invalid & {
        "commit",
        "introduced_by_sha",
    }:
        _check_introducing_commit(repo_root, name, data, findings)


def check_records(ctx: Context, findings: Findings) -> None:
    """Every benefit record belongs to a registered, measured metric and is well formed."""
    for path in record_files(ctx.repo_root):
        metric_id = path.name[len("benefit-") : -len(".json")]
        if metric_id not in ctx.entries:
            findings.problems.append(
                f"{path.name}: id {metric_id!r} is not a registered metric"
            )
        elif cell_token(ctx.entries[metric_id]) != "measured":
            findings.problems.append(
                f"{path.name}: stray record; {metric_id} is not measured, so it has no record file"
            )
        else:
            _check_record(ctx.repo_root, path, ctx.entries[metric_id], findings)


# --- private paths and user names ------------------------------------------------------------------------


def _git_user_name() -> str:
    done = subprocess.run(
        ["git", "config", "user.name"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return done.stdout.strip()


#: Account names shared by many machines. A document may use them as ordinary words, and they identify no one,
#: so they are never treated as a user name.
GENERIC_ACCOUNTS = frozenset(
    {
        "user",
        "test",
        "admin",
        "administrator",
        "runner",
        "runneradmin",
        "root",
        "ubuntu",
        "ci",
        "builder",
        "build",
        "github",
        "docker",
        "jenkins",
    }
)


def current_usernames(
    getuser: Callable[[], str] = getpass.getuser,
    git_name: Callable[[], str] = _git_user_name,
) -> list[str]:
    """The operating-system user and the git user name, read at run time so no name is stored here.

    Names under three characters and generic account names are left out, so the result does not depend on
    which shared account runs the test."""
    names = []
    try:
        names.append(getuser())
    except (KeyError, OSError):
        pass
    names.append(git_name())
    return [
        name
        for name in names
        if len(name) >= 3 and name.strip().lower() not in GENERIC_ACCOUNTS
    ]


def _strings_in(value) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings_in(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings_in(item)


def _private_findings(text: str, usernames) -> list[str]:
    found = []
    if path := PRIVATE_PATH.search(text):
        found.append(f"contains the absolute or transcript path {path.group()!r}")
    if any(
        re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", text, re.IGNORECASE)
        for name in usernames
    ):
        found.append("contains the user name of the person running the test")
    return found


def _scan_fields(
    fields: dict, usernames, locate: Callable[[str], str], findings: Findings
) -> None:
    """Report each private-path or user-name hit in the string values of `fields`, located by `locate(field)`."""
    for field_name, value in fields.items():
        for text in _strings_in(value):
            for problem in _private_findings(text, usernames):
                findings.problems.append(f"{locate(field_name)} {problem}")


def check_no_private_paths(ctx: Context, findings: Findings) -> None:
    """No metric cell, line of the document or record holds an absolute path, transcript path or user name."""
    for metric_id, entry in sorted(ctx.entries.items()):
        _scan_fields(
            entry, ctx.usernames, lambda name, m=metric_id: f"{m}.{name}:", findings
        )
    for number, line in enumerate(ctx.doc_text.splitlines(), start=1):
        for problem in _private_findings(line, ctx.usernames):
            findings.problems.append(f"preregistration line {number}: {problem}")
    for path in record_files(ctx.repo_root):
        loaded = load_record(path)
        fields = (
            loaded.data
            if isinstance(loaded.data, dict)
            else {"(file)": loaded.data or loaded.text}
        )
        _scan_fields(
            fields,
            ctx.usernames,
            lambda name, p=path: f"{p.name}: field {name!r}",
            findings,
        )


# --- thresholds ------------------------------------------------------------------------------------------


def check_thresholds(ctx: Context, findings: Findings) -> None:
    """keep, tune, retire and minimum_n equal the merged values for every pinned metric."""
    for metric_id in ctx.pinned:
        if metric_id not in ctx.entries:
            findings.problems.append(
                f"{metric_id}: metric is missing, so its thresholds cannot be compared"
            )
            continue
        for field_name, expected in zip(THRESHOLD_FIELDS, PINNED_THRESHOLDS[metric_id]):
            actual = ctx.entries[metric_id].get(field_name)
            if actual != expected:
                findings.problems.append(
                    f"{metric_id}.{field_name}: is {actual!r}, merged value is {expected!r}"
                )
