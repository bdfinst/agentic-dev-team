"""Every benefit metric states a checked baseline status.

The ``baseline`` cell of each metric in ``docs/benefit-eval/preregistration.md`` begins with one status
token (``<token>: <text>``). This module holds the rules that keep those cells honest: the token and its
pinned assignment, the verdict-order text that follows from it, the record that backs a ``measured``
baseline, and the frozen thresholds. The rules are plain functions over the loaded pre-registration, so
each rule runs once against the real document and again against synthetic cases that break it.
"""

from __future__ import annotations

import copy
import getpass
import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from _benefit_eval_support import REAL_PREREG, World, cli_argv, load_cli, real_entries

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

#: The deliberate status of each metric. A downgrade edits this map in the same commit as the cell.
PINNED_STATUS = {
    "skip-rate": "by-definition",
    "findings-parity": "by-definition",
    "injection-overhead": "by-definition",
    "guard-false-positive": "by-definition",
    "pbt-mutants-killed": "measured",
    "test-review-tp-change": "measured",
    "injection-uptake": "forward-captured",
    "test-review-token-delta": "forward-captured",
    "abort-yield": "no-reference",
    "guard-divergence": "no-reference",
    "contradicted-rate": "no-reference",
    "expand-rate": "unmeasurable",
    "report-size-cut": "unmeasurable",
}

#: Metrics whose baseline a replayed record can back; their `no-reference` cells must give a reason.
RECORD_CAPABLE = ("pbt-mutants-killed", "test-review-tp-change")

#: The follow-up issue each blocked or unmeasurable cell must cite.
ISSUE_CITES = {
    "skip-rate": 2306,
    "abort-yield": 2306,
    "expand-rate": 2307,
    "report-size-cut": 2308,
}

NO_VERDICT_STATUSES = ("no-reference", "unmeasurable")


@dataclass
class Findings:
    """What a rule found: problems fail the run; skips name a check that could not run and why."""

    problems: list[str] = field(default_factory=list)
    skips: list[str] = field(default_factory=list)

    def report(self) -> str:
        return "\n".join(self.problems)


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


def check_baseline_cells(entries: dict[str, dict], findings: Findings) -> None:
    """Each cell has one allowed token that matches the pinned map; ids equal the pinned ids."""
    for missing in sorted(set(PINNED_STATUS) - set(entries)):
        findings.problems.append(
            f"{missing}: metric is pinned but absent from the pre-registration"
        )
    for extra in sorted(set(entries) - set(PINNED_STATUS)):
        findings.problems.append(
            f"{extra}: metric is registered but has no pinned status"
        )
    for metric_id in sorted(set(entries) & set(PINNED_STATUS)):
        token, text, problem = split_baseline(entries[metric_id]["baseline"])
        if problem:
            findings.problems.append(
                f"{metric_id}.baseline: {problem}; allowed tokens: {', '.join(ALLOWED_TOKENS)}"
            )
            continue
        expected = PINNED_STATUS[metric_id]
        if token == "no-reference" and metric_id in RECORD_CAPABLE:
            reason = text.split(";", 1)[0].strip() if ";" in text else ""
            if reason not in REASONS:
                findings.problems.append(
                    f"{metric_id}.baseline: reason {reason!r} is not one of {', '.join(REASONS)}"
                )
            elif expected == "measured" and reason != "not-yet-run":
                findings.problems.append(
                    f"{metric_id}.baseline: pinned status is measured, so only 'not-yet-run' is accepted "
                    f"until a record exists (a downgrade edits the pinned map)"
                )
        elif token != expected:
            findings.problems.append(
                f"{metric_id}.baseline: status {token!r} does not match pinned {expected!r}"
            )


def check_unmeasurable_matches_handling(
    entries: dict[str, dict], findings: Findings
) -> None:
    """A metric is `unmeasurable` exactly when its `id_less_handling` is `unmeasurable`."""
    for metric_id, entry in sorted(entries.items()):
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


def check_issue_cites(entries: dict[str, dict], findings: Findings) -> None:
    """The cells that wait on a follow-up issue cite it by number."""
    for metric_id, number in sorted(ISSUE_CITES.items()):
        cell = entries[metric_id]["baseline"]
        if not re.search(rf"(?<!\d)#{number}(?!\d)", cell):
            findings.problems.append(f"{metric_id}.baseline: cites no #{number}")


def status_table_tokens(doc_text: str) -> list[str]:
    """First-column tokens of the table under the `## Baseline status` heading."""
    section = re.search(
        r"^## Baseline status\s*$(.*?)(?=^## |\Z)", doc_text, re.MULTILINE | re.DOTALL
    )
    if not section:
        return []
    rows = [line for line in section.group(1).splitlines() if line.startswith("|")]
    first_cells = [
        row.split("|")[1].strip().strip("`") for row in rows[2:]
    ]  # skip header and divider
    return first_cells


def check_status_table(doc_text: str, findings: Findings) -> None:
    tokens = status_table_tokens(doc_text)
    if sorted(tokens) != sorted(ALLOWED_TOKENS):
        findings.problems.append(
            f"status table: tokens {tokens} differ from the pinned enum {list(ALLOWED_TOKENS)}"
        )


def verdict_paragraph(doc_text: str) -> str | None:
    """The `**Verdict order.**` paragraph under `## Rules`."""
    rules = re.search(r"^## Rules\s*$", doc_text, re.MULTILINE)
    if not rules:
        return None
    for paragraph in re.split(r"\n\s*\n", doc_text[rules.end() :]):
        if paragraph.lstrip().startswith("**Verdict order.**"):
            return paragraph
    return None


def check_verdict_order(
    doc_text: str, entries: dict[str, dict], findings: Findings
) -> None:
    """The verdict-order paragraph names exactly the no-reference and unmeasurable metrics, and says why."""
    paragraph = verdict_paragraph(doc_text)
    if paragraph is None:
        findings.problems.append(
            "verdict order: no '**Verdict order.**' paragraph under '## Rules'"
        )
        return
    named = {
        metric_id
        for metric_id in entries
        if re.search(rf"(?<![\w-]){re.escape(metric_id)}(?![\w-])", paragraph)
    }
    expected = {
        metric_id
        for metric_id, entry in entries.items()
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


RECORDS_DIR = ".dev-team-reports/baselines"
RECORD_PATH = re.compile(r"\.dev-team-reports/baselines/[^\s;,)`'\"]+")
SHA = re.compile(r"[0-9a-f]{40}")
GIT_ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}


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
    "pbt-mutants-killed": {
        "generated_properties": (lambda value: value is False, "false"),
        "target_ids": (_is_string_list, "a list of strings"),
    },
    "test-review-tp-change": {
        "introduced_by_sha": (_is_sha, "a 40-hex SHA"),
        "fixture_ids": (_is_string_list, "a list of strings"),
    },
}


def git(repo_root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        env=GIT_ENV,
        capture_output=True,
        text=True,
        check=False,
    )


def commit_resolves(repo_root: Path, sha: str) -> bool:
    return git(repo_root, "cat-file", "-e", f"{sha}^{{commit}}").returncode == 0


def is_shallow(repo_root: Path) -> bool:
    return (
        git(repo_root, "rev-parse", "--is-shallow-repository").stdout.strip() == "true"
    )


def check_measured_cells(
    entries: dict[str, dict], repo_root: Path, findings: Findings
) -> None:
    """A measured cell cites a record path that resolves, and the metric's own record exists."""
    for metric_id, entry in sorted(entries.items()):
        if cell_token(entry) != "measured":
            continue
        cited = RECORD_PATH.search(entry["baseline"])
        if not cited:
            findings.problems.append(
                f"{metric_id}.baseline: measured cell cites no path under {RECORDS_DIR}/"
            )
        elif not (repo_root / cited.group().rstrip("/.")).is_file():
            findings.problems.append(
                f"{metric_id}.baseline: cites {cited.group()}, which does not exist"
            )
        if not (repo_root / RECORDS_DIR / f"benefit-{metric_id}.json").is_file():
            findings.problems.append(
                f"{metric_id}: status is measured but {RECORDS_DIR}/benefit-{metric_id}.json is missing"
            )


def record_files(repo_root: Path) -> list[Path]:
    directory = repo_root / RECORDS_DIR
    if not directory.is_dir():
        return []
    return sorted(
        path
        for path in directory.iterdir()
        if path.name.lower().startswith("benefit-")
        and path.name.lower().endswith(".json")
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
        findings.skips.append(
            f"{name}: introduced_by_sha parent check skipped; the commit is absent"
        )
        return
    parent = git(repo_root, "rev-parse", f"{introduced}^")
    if parent.returncode != 0 and is_shallow(repo_root):
        findings.skips.append(
            f"{name}: introduced_by_sha parent check skipped; its parent is absent"
        )
    elif parent.stdout.strip() != data["commit"]:
        findings.problems.append(
            f"{name}: field 'commit' is not the parent of introduced_by_sha "
            f"(git rev-parse introduced_by_sha^ gave {parent.stdout.strip() or 'nothing'})"
        )


def check_record(repo_root: Path, path: Path, entry: dict, findings: Findings) -> None:
    """Fields, types, `n` against `minimum_n`, and the commit links of one `measured` record."""
    name = path.name
    metric_id = entry["id"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as error:
        findings.problems.append(f"{name}: unparseable record: {error}")
        return
    if not isinstance(data, dict):
        findings.problems.append(f"{name}: record is not a JSON object")
        return
    if "status" in data:
        findings.problems.append(
            f"{name}: field 'status' is not allowed; status lives in the baseline cell"
        )
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
    if "n" not in invalid and data["n"] < entry["minimum_n"]:
        findings.problems.append(
            f"{name}: field 'n' is {data['n']}, below minimum_n {entry['minimum_n']} for {metric_id}"
        )
    if "commit" not in invalid:
        _resolve_commit(repo_root, name, "commit", data["commit"], findings)
    if "introduced_by_sha" in METRIC_RECORD_FIELDS.get(
        metric_id, {}
    ) and not invalid & {"commit", "introduced_by_sha"}:
        _check_introducing_commit(repo_root, name, data, findings)


def check_records(
    entries: dict[str, dict], repo_root: Path, findings: Findings
) -> None:
    """Every benefit record belongs to a registered, measured metric and is well formed."""
    for path in record_files(repo_root):
        metric_id = path.name[len("benefit-") : -len(".json")]
        if metric_id not in entries:
            findings.problems.append(
                f"{path.name}: id {metric_id!r} is not a registered metric"
            )
        elif cell_token(entries[metric_id]) != "measured":
            findings.problems.append(
                f"{path.name}: stray record; {metric_id} is not measured, so it has no record file"
            )
        else:
            check_record(repo_root, path, entries[metric_id], findings)


#: Absolute locations and transcript directories that must not appear in a committed file. The root forms
#: match only where a path starts, so a repo-relative `docs/users/` stays valid.
PRIVATE_PATH = re.compile(
    r"(?<![\w./\\-])(?:/Users/|/home/|/private/var/|[A-Za-z]:\\{1,2}Users\\)|\.claude/projects/",
    re.IGNORECASE,
)

#: keep, tune, retire and minimum_n of every metric as merged, so a threshold cannot move in this change.
PINNED_THRESHOLDS = {
    "skip-rate": (">= 10", "< 10", "< 3", 10),
    "findings-parity": ("<= 0", "<= 2", ">= 3", 3),
    "abort-yield": ("<= 25", "> 25", "> 60", 10),
    "test-review-tp-change": (">= 0", "< 0", "< -10", 10),
    "test-review-token-delta": ("<= -15", "> -15", "> 0", 10),
    "expand-rate": ("<= 20", "> 20", "> 50", 10),
    "report-size-cut": (">= 40", "< 40", "< 15", 10),
    "injection-overhead": ("<= 400", "> 400", "> 1200", 10),
    "injection-uptake": (">= 50", "< 50", "< 10", 10),
    "guard-divergence": (">= 2", "< 2", "< 0.5", 10),
    "guard-false-positive": ("<= 5", "> 5", "> 30", 10),
    "contradicted-rate": (">= 0.2", "< 0.2", "< 0.05", 10),
    "pbt-mutants-killed": (">= 1", "< 1", "<= 0", 10),
}
THRESHOLD_FIELDS = ("keep", "tune", "retire", "minimum_n")


def current_usernames() -> list[str]:
    """The operating-system user and the git user name, read at run time so no name is stored here."""
    names = []
    try:
        names.append(getpass.getuser())
    except (KeyError, OSError):
        pass
    configured = subprocess.run(
        ["git", "config", "user.name"], cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )
    names.append(configured.stdout.strip())
    return [name for name in names if len(name) >= 3]


def _strings_in(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings_in(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings_in(item)


def _private_findings(text: str, usernames: list[str]) -> list[str]:
    found = []
    if path := PRIVATE_PATH.search(text):
        found.append(f"contains the absolute or transcript path {path.group()!r}")
    if any(re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", text, re.IGNORECASE) for name in usernames):
        found.append("contains the user name of the person running the test")
    return found


def check_no_private_paths(
    entries: dict[str, dict], doc_text: str, repo_root: Path, usernames: list[str], findings: Findings
) -> None:
    """No metric cell, line of the document or record holds an absolute path, transcript path or user name."""
    for metric_id, entry in sorted(entries.items()):
        for field_name, value in entry.items():
            for text in _strings_in(value):
                for problem in _private_findings(text, usernames):
                    findings.problems.append(f"{metric_id}.{field_name}: {problem}")
    for number, line in enumerate(doc_text.splitlines(), start=1):
        for problem in _private_findings(line, usernames):
            findings.problems.append(f"preregistration line {number}: {problem}")
    for path in record_files(repo_root):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            data = {"(file)": path.read_text(encoding="utf-8", errors="replace")}
        for field_name, value in (data if isinstance(data, dict) else {"(file)": data}).items():
            for text in _strings_in(value):
                for problem in _private_findings(text, usernames):
                    findings.problems.append(f"{path.name}: field {field_name!r} {problem}")


def check_thresholds(entries: dict[str, dict], findings: Findings) -> None:
    """keep, tune, retire and minimum_n equal the merged values for every metric."""
    for metric_id, pinned in PINNED_THRESHOLDS.items():
        if metric_id not in entries:
            findings.problems.append(f"{metric_id}: metric is missing, so its thresholds cannot be compared")
            continue
        for field_name, expected in zip(THRESHOLD_FIELDS, pinned):
            actual = entries[metric_id].get(field_name)
            if actual != expected:
                findings.problems.append(f"{metric_id}.{field_name}: is {actual!r}, merged value is {expected!r}")


# --- synthetic world -------------------------------------------------------------------------------------


def good_baseline(metric_id: str) -> str:
    """A valid cell for the metric's pinned status; a measured metric starts as not-yet-run."""
    status = PINNED_STATUS[metric_id]
    head = (
        "no-reference: not-yet-run; replay pending"
        if status == "measured"
        else f"{status}: reference text"
    )
    cite = ISSUE_CITES.get(metric_id)
    return f"{head} (#{cite})" if cite else head


def good_entries() -> dict[str, dict]:
    """The real entries, so thresholds and `minimum_n` come from the pre-registration, with valid cells."""
    entries = copy.deepcopy(real_entries())
    for metric_id, entry in entries.items():
        entry["baseline"] = good_baseline(metric_id)
    return entries


def good_doc(entries: dict[str, dict]) -> str:
    """A minimal document with a status table and a verdict-order paragraph that agree with the cells."""
    ids = ", ".join(
        f"`{metric_id}`"
        for metric_id, entry in entries.items()
        if cell_token(entry) in NO_VERDICT_STATUSES
    )
    table = "\n".join(f"| `{token}` | meaning |" for token in ALLOWED_TOKENS)
    return (
        "## Baseline status\n\n| Status | Meaning |\n| --- | --- |\n" + table + "\n\n"
        "## Rules\n\n**Verdict order.** Evaluate retire first. "
        f"No keep, tune, or retire verdict is posted for: {ids}.\n\n**Within and breach.** Text.\n"
    )


def problems_for(entries: dict[str, dict], *checks) -> list[str]:
    findings = Findings()
    for check in checks:
        check(entries, findings)
    return findings.problems


def with_baseline(metric_id: str, cell: str) -> dict[str, dict]:
    entries = good_entries()
    entries[metric_id]["baseline"] = cell
    return entries


# --- the real pre-registration ---------------------------------------------------------------------------


def test_real_baseline_cells_carry_the_pinned_status_token():
    findings = Findings()
    check_baseline_cells(real_entries(), findings)
    assert not findings.problems, findings.report()


def test_real_status_table_lists_exactly_the_pinned_tokens():
    findings = Findings()
    check_status_table(REAL_PREREG.read_text(), findings)
    assert not findings.problems, findings.report()


def test_real_unmeasurable_status_holds_exactly_when_handling_is_unmeasurable():
    findings = Findings()
    check_unmeasurable_matches_handling(real_entries(), findings)
    assert not findings.problems, findings.report()


def test_real_cells_cite_the_follow_up_issues():
    findings = Findings()
    check_issue_cites(real_entries(), findings)
    assert not findings.problems, findings.report()


def test_real_verdict_order_names_exactly_the_metrics_without_a_reference():
    findings = Findings()
    check_verdict_order(REAL_PREREG.read_text(), real_entries(), findings)
    assert not findings.problems, findings.report()


# --- the rules against synthetic cases -------------------------------------------------------------------


def test_synthetic_baseline_is_accepted():
    entries = good_entries()
    assert (
        problems_for(
            entries,
            check_baseline_cells,
            check_unmeasurable_matches_handling,
            check_issue_cites,
        )
        == []
    )
    findings = Findings()
    check_status_table(good_doc(entries), findings)
    check_verdict_order(good_doc(entries), entries, findings)
    assert findings.problems == []


@pytest.mark.parametrize(
    "cell",
    [
        "invented: text",
        "Measured: text",
        "BY-DEFINITION: text",
        "by-definition, measured: text",
        "by-definition: measured: text",
        "by-definition: ",
        "by-definition:",
        "no text token at all",
        "none: first measurement",
        "None: first measurement",
        "TBD: later",
    ],
    ids=[
        "unknown-token",
        "wrong-case-token",
        "upper-case-token",
        "two-tokens-before-colon",
        "two-tokens-chained",
        "empty-text",
        "missing-separator-space",
        "no-token",
        "none-prefix",
        "none-prefix-capitalised",
        "tbd-prefix",
    ],
)
def test_baseline_cell_with_a_bad_token_form_is_rejected_naming_metric_and_allowed_tokens(
    cell,
):
    (problem,) = problems_for(
        with_baseline("guard-false-positive", cell), check_baseline_cells
    )
    assert problem.startswith("guard-false-positive.baseline:")
    assert all(token in problem for token in ALLOWED_TOKENS)


def test_baseline_text_after_the_token_can_be_reworded():
    entries = with_baseline(
        "guard-false-positive", "by-definition: a different sentence entirely"
    )
    assert problems_for(entries, check_baseline_cells) == []


def test_baseline_status_that_differs_from_the_pinned_map_is_rejected():
    entries = with_baseline("guard-false-positive", "forward-captured: text")
    (problem,) = problems_for(entries, check_baseline_cells)
    assert "guard-false-positive.baseline" in problem
    assert "'by-definition'" in problem


def test_a_pinned_metric_missing_from_the_pre_registration_is_rejected():
    entries = good_entries()
    del entries["skip-rate"]
    assert any(
        p.startswith("skip-rate:") for p in problems_for(entries, check_baseline_cells)
    )


def test_a_registered_metric_with_no_pinned_status_is_rejected():
    entries = good_entries()
    entries["new-metric"] = {**entries["skip-rate"], "id": "new-metric"}
    assert any(
        p.startswith("new-metric:") for p in problems_for(entries, check_baseline_cells)
    )


@pytest.mark.parametrize("reason", REASONS)
def test_not_yet_run_is_the_only_reason_accepted_for_a_measured_pin(reason):
    entries = with_baseline("pbt-mutants-killed", f"no-reference: {reason}; text")
    problems = problems_for(entries, check_baseline_cells)
    assert (problems == []) == (reason == "not-yet-run")
    assert all(p.startswith("pbt-mutants-killed.baseline") for p in problems)


def test_a_downgrade_reason_outside_the_enum_is_rejected():
    entries = with_baseline("test-review-tp-change", "no-reference: gave-up; text")
    (problem,) = problems_for(entries, check_baseline_cells)
    assert "test-review-tp-change.baseline" in problem
    assert all(reason in problem for reason in REASONS)


def test_a_no_reference_cell_without_a_reason_is_rejected_for_a_record_capable_metric():
    entries = with_baseline(
        "pbt-mutants-killed", "no-reference: text with no reason separator"
    )
    (problem,) = problems_for(entries, check_baseline_cells)
    assert "pbt-mutants-killed.baseline" in problem


def test_a_downgraded_metric_accepts_any_enum_reason_once_the_pinned_map_follows(
    monkeypatch,
):
    monkeypatch.setitem(PINNED_STATUS, "pbt-mutants-killed", "no-reference")
    entries = with_baseline("pbt-mutants-killed", "no-reference: cost-declined; text")
    assert problems_for(entries, check_baseline_cells) == []


@pytest.mark.parametrize(
    ("metric_id", "cell"),
    [
        ("expand-rate", "by-definition: counted by hand"),
        ("skip-rate", "unmeasurable: no instrument (#2306)"),
    ],
    ids=[
        "unmeasurable-handling-without-the-status",
        "unmeasurable-status-without-the-handling",
    ],
)
def test_unmeasurable_status_that_disagrees_with_id_less_handling_is_rejected(
    metric_id, cell
):
    (problem,) = problems_for(
        with_baseline(metric_id, cell), check_unmeasurable_matches_handling
    )
    assert problem.startswith(f"{metric_id}.baseline:")


@pytest.mark.parametrize(
    ("metric_id", "number"), sorted(ISSUE_CITES.items()), ids=sorted(ISSUE_CITES)
)
def test_a_cell_missing_its_follow_up_issue_number_is_rejected_naming_the_metric(
    metric_id, number
):
    entries = with_baseline(
        metric_id, good_baseline(metric_id).replace(f"#{number}", "#9999")
    )
    (problem,) = problems_for(entries, check_issue_cites)
    assert problem == f"{metric_id}.baseline: cites no #{number}"


def test_an_issue_number_can_follow_the_reason_text():
    entries = with_baseline(
        "expand-rate",
        f"unmeasurable: nothing is counted; follow-up #{ISSUE_CITES['expand-rate']}",
    )
    assert problems_for(entries, check_issue_cites) == []


def test_an_issue_number_that_only_prefixes_the_cited_one_is_rejected():
    entries = with_baseline(
        "expand-rate", "unmeasurable: nothing is counted; follow-up #23071"
    )
    assert problems_for(entries, check_issue_cites) == [
        "expand-rate.baseline: cites no #2307"
    ]


@pytest.mark.parametrize(
    ("tokens", "label"),
    [
        (ALLOWED_TOKENS[:-1], "token-missing"),
        (ALLOWED_TOKENS + ("estimated",), "token-added"),
        (ALLOWED_TOKENS + ("measured",), "token-duplicated"),
    ],
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_status_table_that_differs_from_the_pinned_enum_is_rejected(tokens, label):
    table = "\n".join(f"| `{token}` | meaning |" for token in tokens)
    doc = f"## Baseline status\n\n| Status | Meaning |\n| --- | --- |\n{table}\n\n## Rules\n"
    findings = Findings()
    check_status_table(doc, findings)
    assert len(findings.problems) == 1, label


def test_a_document_without_a_status_table_is_rejected():
    findings = Findings()
    check_status_table("## Rules\n\ntext\n", findings)
    assert len(findings.problems) == 1


def doc_with_verdict_paragraph(entries: dict[str, dict], paragraph: str) -> str:
    return good_doc(entries).replace(
        next(
            p
            for p in good_doc(entries).split("\n\n")
            if p.startswith("**Verdict order.**")
        ),
        paragraph,
    )


def verdict_problems(entries: dict[str, dict], doc: str) -> list[str]:
    findings = Findings()
    check_verdict_order(doc, entries, findings)
    return findings.problems


def test_verdict_order_that_omits_a_no_reference_metric_is_rejected_naming_it():
    entries = good_entries()
    doc = good_doc(entries).replace("`abort-yield`, ", "")
    (problem,) = verdict_problems(entries, doc)
    assert "missing ['abort-yield']" in problem


def test_verdict_order_that_names_a_metric_with_a_reference_is_rejected_naming_it():
    entries = good_entries()
    doc = good_doc(entries).replace(
        "verdict is posted for: ", "verdict is posted for: `skip-rate`, "
    )
    (problem,) = verdict_problems(entries, doc)
    assert "extra ['skip-rate']" in problem


def test_verdict_order_follows_a_downgraded_metric_automatically():
    record_cell = (
        "measured: .dev-team-reports/baselines/benefit-pbt-mutants-killed.json"
    )
    stale_doc = good_doc(with_baseline("pbt-mutants-killed", record_cell))
    entries = with_baseline("pbt-mutants-killed", "no-reference: cost-declined; text")
    (problem,) = verdict_problems(entries, stale_doc)
    assert "missing ['pbt-mutants-killed']" in problem
    assert verdict_problems(entries, good_doc(entries)) == []


def test_verdict_order_without_the_no_verdict_statement_is_rejected():
    entries = good_entries()
    doc = good_doc(entries).replace(
        "No keep, tune, or retire verdict is posted for", "Metrics"
    )
    (problem,) = verdict_problems(entries, doc)
    assert "no keep, tune, or retire verdict" in problem


def test_verdict_order_can_be_reworded_around_the_id_list():
    entries = good_entries()
    doc = good_doc(entries).replace(
        "is posted for:", "is ever posted for these metrics:"
    )
    assert verdict_problems(entries, doc) == []


def test_a_document_without_a_verdict_order_paragraph_is_rejected():
    assert len(verdict_problems(good_entries(), "## Rules\n\n**Other.** text\n")) == 1


# --- records: the real repository ------------------------------------------------------------------------


def test_real_measured_baselines_cite_resolving_records_that_are_complete():
    findings = Findings()
    check_measured_cells(real_entries(), REPO_ROOT, findings)
    check_records(real_entries(), REPO_ROOT, findings)
    assert not findings.problems, findings.report()
    if findings.skips:
        pytest.skip("; ".join(findings.skips))


# --- records: synthetic cases ----------------------------------------------------------------------------


@pytest.fixture
def repo(tmp_path):
    """A throwaway git repository with two commits and an empty records directory."""
    root = tmp_path / "repo"
    (root / RECORDS_DIR).mkdir(parents=True)
    git(root, "init", "-q")
    identity = ["-c", "user.name=test", "-c", "user.email=test@example.invalid"]
    for message in ("first", "second"):
        git(root, *identity, "commit", "-q", "--allow-empty", "-m", message)
    head = git(root, "rev-parse", "HEAD").stdout.strip()
    parent = git(root, "rev-parse", "HEAD^").stdout.strip()
    return SimpleNamespace(root=root, head=head, parent=parent)


def record_cell(metric_id: str) -> str:
    return f"measured: replayed value in {RECORDS_DIR}/benefit-{metric_id}.json"


def measured_entries(*metric_ids: str) -> dict[str, dict]:
    entries = good_entries()
    for metric_id in metric_ids:
        entries[metric_id]["baseline"] = record_cell(metric_id)
    return entries


def valid_record(repo, metric_id: str) -> dict:
    record = {
        "command": "python3 scripts/replay.py --target one",
        "inputs": ["scripts/replay.py"],
        "commit": repo.head,
        "date": "2026-11-13",
        "value": 12,
        "n": good_entries()[metric_id]["minimum_n"],
    }
    if metric_id == "pbt-mutants-killed":
        record |= {"generated_properties": False, "target_ids": ["one"]}
    if metric_id == "test-review-tp-change":
        record |= {"commit": repo.parent, "introduced_by_sha": repo.head, "fixture_ids": ["tr-1"]}
    return record


def write_record(repo, metric_id: str, record: dict | str, filename: str | None = None) -> Path:
    path = repo.root / RECORDS_DIR / (filename or f"benefit-{metric_id}.json")
    path.write_text(record if isinstance(record, str) else json.dumps(record, indent=2) + "\n")
    return path


def record_problems(repo, entries: dict[str, dict]) -> Findings:
    findings = Findings()
    check_measured_cells(entries, repo.root, findings)
    check_records(entries, repo.root, findings)
    return findings


@pytest.mark.parametrize("metric_id", sorted(METRIC_RECORD_FIELDS))
def test_a_complete_record_for_a_measured_metric_is_accepted(repo, metric_id):
    write_record(repo, metric_id, valid_record(repo, metric_id))
    assert record_problems(repo, measured_entries(metric_id)).problems == []


def test_a_record_with_trailing_whitespace_is_accepted(repo):
    write_record(repo, "pbt-mutants-killed", json.dumps(valid_record(repo, "pbt-mutants-killed")) + "\n\n  \n")
    assert record_problems(repo, measured_entries("pbt-mutants-killed")).problems == []


def test_a_measured_metric_without_its_record_is_rejected_naming_the_record(repo):
    (_, missing) = record_problems(repo, measured_entries("pbt-mutants-killed")).problems
    assert f"{RECORDS_DIR}/benefit-pbt-mutants-killed.json is missing" in missing


def test_a_no_reference_metric_needs_no_record(repo):
    assert record_problems(repo, good_entries()).problems == []


def test_a_measured_cell_citing_a_missing_path_is_rejected_naming_metric_and_path(repo):
    entries = measured_entries("pbt-mutants-killed")
    cited = f"{RECORDS_DIR}/benefit-elsewhere.json"
    entries["pbt-mutants-killed"]["baseline"] = f"measured: see {cited}"
    write_record(repo, "pbt-mutants-killed", valid_record(repo, "pbt-mutants-killed"))
    (problem,) = record_problems(repo, entries).problems
    assert problem == f"pbt-mutants-killed.baseline: cites {cited}, which does not exist"


def test_a_measured_cell_citing_no_record_path_is_rejected(repo):
    entries = with_baseline("pbt-mutants-killed", "measured: replayed, no path given")
    write_record(repo, "pbt-mutants-killed", valid_record(repo, "pbt-mutants-killed"))
    (problem,) = record_problems(repo, entries).problems
    assert problem.startswith("pbt-mutants-killed.baseline: measured cell cites no path")


def test_a_cited_record_path_can_end_in_a_slash(repo):
    entries = with_baseline("pbt-mutants-killed", f"measured: see {RECORDS_DIR}/benefit-pbt-mutants-killed.json/")
    write_record(repo, "pbt-mutants-killed", valid_record(repo, "pbt-mutants-killed"))
    assert record_problems(repo, entries).problems == []


def test_a_cited_record_path_can_end_a_sentence_with_a_period(repo):
    entries = with_baseline("pbt-mutants-killed", f"measured: see {RECORDS_DIR}/benefit-pbt-mutants-killed.json.")
    write_record(repo, "pbt-mutants-killed", valid_record(repo, "pbt-mutants-killed"))
    assert record_problems(repo, entries).problems == []


def all_record_fields(metric_id: str) -> list[str]:
    return [*COMMON_RECORD_FIELDS, *METRIC_RECORD_FIELDS.get(metric_id, {})]


@pytest.mark.parametrize(
    ("metric_id", "field_name"),
    [(m, f) for m in sorted(METRIC_RECORD_FIELDS) for f in all_record_fields(m)],
)
@pytest.mark.parametrize("defect", ["missing", "null"])
def test_a_record_with_a_missing_or_null_field_is_rejected_naming_record_and_field(
    repo, metric_id, field_name, defect
):
    record = valid_record(repo, metric_id)
    if defect == "missing":
        del record[field_name]
    else:
        record[field_name] = None
    write_record(repo, metric_id, record)
    problems = record_problems(repo, measured_entries(metric_id)).problems
    assert any(
        p.startswith(f"benefit-{metric_id}.json: field {field_name!r} is {defect}") for p in problems
    ), problems


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("command", 7),
        ("command", "  "),
        ("inputs", "scripts/replay.py"),
        ("inputs", [1]),
        ("inputs", ["/etc/hosts"]),
        ("commit", "abc123"),
        ("commit", "A" * 40),
        ("date", "13/11/2026"),
        ("date", 20261113),
        ("value", "12"),
        ("value", True),
        ("generated_properties", True),
        ("generated_properties", "false"),
        ("target_ids", "one"),
        ("target_ids", [1]),
    ],
)
def test_a_record_field_of_the_wrong_type_is_rejected_naming_record_and_field(repo, field_name, bad_value):
    record = valid_record(repo, "pbt-mutants-killed") | {field_name: bad_value}
    write_record(repo, "pbt-mutants-killed", record)
    problems = record_problems(repo, measured_entries("pbt-mutants-killed")).problems
    assert any(p.startswith(f"benefit-pbt-mutants-killed.json: field {field_name!r}") for p in problems), problems


@pytest.mark.parametrize(
    ("bad_n", "reason"),
    [(-1, "expected an integer >= 0"), (2.5, "expected an integer >= 0"), ("10", "expected an integer >= 0"), (True, "expected an integer >= 0"), (None, "is null")],
    ids=["negative", "fraction", "string", "bool", "null"],
)
def test_a_record_with_an_invalid_n_is_rejected_naming_record_and_field(repo, bad_n, reason):
    write_record(repo, "pbt-mutants-killed", valid_record(repo, "pbt-mutants-killed") | {"n": bad_n})
    (problem,) = record_problems(repo, measured_entries("pbt-mutants-killed")).problems
    assert problem.startswith("benefit-pbt-mutants-killed.json: field 'n'")
    assert reason in problem


@pytest.mark.parametrize("metric_id", ["pbt-mutants-killed", "findings-parity"])
def test_n_below_minimum_n_is_rejected_and_n_at_minimum_n_is_accepted(repo, metric_id):
    entries = measured_entries(metric_id)
    minimum_n = entries[metric_id]["minimum_n"]
    record = valid_record(repo, metric_id)

    write_record(repo, metric_id, record | {"n": minimum_n - 1})
    (problem,) = record_problems(repo, entries).problems
    assert problem == (
        f"benefit-{metric_id}.json: field 'n' is {minimum_n - 1}, below minimum_n {minimum_n} for {metric_id}"
    )

    write_record(repo, metric_id, record | {"n": minimum_n})
    assert record_problems(repo, entries).problems == []


def test_minimum_n_is_read_from_the_pre_registration_entry(repo):
    entries = measured_entries("pbt-mutants-killed")
    entries["pbt-mutants-killed"]["minimum_n"] = 40
    write_record(repo, "pbt-mutants-killed", valid_record(repo, "pbt-mutants-killed") | {"n": 39})
    (problem,) = record_problems(repo, entries).problems
    assert "below minimum_n 40" in problem


def test_an_unparseable_record_is_rejected_naming_the_record(repo):
    write_record(repo, "pbt-mutants-killed", "{not json")
    (problem,) = record_problems(repo, measured_entries("pbt-mutants-killed")).problems
    assert problem.startswith("benefit-pbt-mutants-killed.json: unparseable record")


def test_a_record_that_is_not_a_json_object_is_rejected(repo):
    write_record(repo, "pbt-mutants-killed", "[1, 2]")
    (problem,) = record_problems(repo, measured_entries("pbt-mutants-killed")).problems
    assert problem == "benefit-pbt-mutants-killed.json: record is not a JSON object"


def test_a_record_that_carries_a_status_is_rejected(repo):
    write_record(repo, "pbt-mutants-killed", valid_record(repo, "pbt-mutants-killed") | {"status": "measured"})
    (problem,) = record_problems(repo, measured_entries("pbt-mutants-killed")).problems
    assert problem.startswith("benefit-pbt-mutants-killed.json: field 'status'")


@pytest.mark.parametrize("filename", ["benefit-unregistered.json", "benefit-unregistered.JSON"])
def test_a_record_for_an_unregistered_id_is_rejected_naming_the_file(repo, filename):
    write_record(repo, "unregistered", valid_record(repo, "pbt-mutants-killed"), filename)
    (problem,) = record_problems(repo, good_entries()).problems
    assert problem.startswith(f"{filename}: id 'unregistered' is not a registered metric")


@pytest.mark.parametrize("metric_id", ["skip-rate", "pbt-mutants-killed"])
def test_a_record_for_a_metric_that_is_not_measured_is_rejected_naming_the_file(repo, metric_id):
    write_record(repo, metric_id, valid_record(repo, "pbt-mutants-killed"))
    (problem,) = record_problems(repo, good_entries()).problems
    assert problem.startswith(f"benefit-{metric_id}.json: stray record")


def test_files_that_are_not_benefit_records_are_ignored(repo):
    write_record(repo, "other", "{not json", "bash-failure-taxonomy-2026-08-27.json")
    assert record_problems(repo, good_entries()).problems == []


def test_a_record_commit_that_does_not_resolve_is_rejected_in_a_full_repository(repo):
    write_record(repo, "pbt-mutants-killed", valid_record(repo, "pbt-mutants-killed") | {"commit": "1" * 40})
    findings = record_problems(repo, measured_entries("pbt-mutants-killed"))
    assert [p.split(" ")[0:3] for p in findings.problems] == [["benefit-pbt-mutants-killed.json:", "field", "'commit'"]]
    assert findings.skips == []


def test_a_record_commit_absent_from_a_shallow_repository_is_skipped_with_a_named_reason(repo, tmp_path):
    shallow = tmp_path / "shallow"
    git(tmp_path, "clone", "-q", "--depth", "1", f"file://{repo.root}", str(shallow))
    (shallow / RECORDS_DIR).mkdir(parents=True, exist_ok=True)
    shallow_repo = SimpleNamespace(root=shallow, head=repo.head, parent=repo.parent)
    write_record(shallow_repo, "pbt-mutants-killed", valid_record(repo, "pbt-mutants-killed") | {"commit": "1" * 40})
    findings = record_problems(shallow_repo, measured_entries("pbt-mutants-killed"))
    assert findings.problems == []
    assert findings.skips and "shallow" in findings.skips[0]


def test_introduced_by_sha_whose_parent_is_not_the_commit_is_rejected(repo):
    record = valid_record(repo, "test-review-tp-change") | {"commit": repo.head}
    write_record(repo, "test-review-tp-change", record)
    (problem,) = record_problems(repo, measured_entries("test-review-tp-change")).problems
    assert problem.startswith("benefit-test-review-tp-change.json: field 'commit' is not the parent")


# --- private paths and user names ------------------------------------------------------------------------

NO_USERNAMES: list[str] = []


def private_problems(entries, doc_text="", repo_root=None, usernames=NO_USERNAMES) -> list[str]:
    findings = Findings()
    check_no_private_paths(entries, doc_text, repo_root, usernames, findings)
    return findings.problems


def test_real_pre_registration_and_records_hold_no_private_path_or_user_name():
    findings = Findings()
    check_no_private_paths(real_entries(), REAL_PREREG.read_text(), REPO_ROOT, current_usernames(), findings)
    assert not findings.problems, findings.report()


@pytest.mark.parametrize(
    "text",
    [
        "/Users/someone/work/file.json",
        "see /home/someone/file",
        "/private/var/folders/x",
        "C:\\Users\\someone\\file",
        "/USERS/someone/file",
        "~/.claude/projects/abc/session.jsonl",
        ".claude/projects/abc",
    ],
    ids=["users", "home", "private-var", "windows-users", "upper-case", "tilde-transcript", "transcript"],
)
def test_a_baseline_cell_with_an_absolute_or_transcript_path_is_rejected_naming_metric_and_field(
    tmp_path, text
):
    entries = with_baseline("skip-rate", f"by-definition: reference at {text}")
    (problem,) = private_problems(entries, repo_root=tmp_path)
    assert problem.startswith("skip-rate.baseline: contains the absolute or transcript path")


def test_a_repo_relative_path_with_a_directory_named_users_is_accepted(tmp_path):
    entries = with_baseline("skip-rate", "by-definition: reference in docs/users/guide.md and src/home/x")
    assert private_problems(entries, repo_root=tmp_path) == []


def test_an_absolute_path_in_the_document_prose_is_rejected_naming_the_line(tmp_path):
    (problem,) = private_problems(good_entries(), "fine\nrun /Users/someone/tool\n", repo_root=tmp_path)
    assert problem.startswith("preregistration line 2: contains the absolute or transcript path")


def test_a_record_field_with_an_absolute_path_is_rejected_naming_record_and_field(repo):
    record = valid_record(repo, "pbt-mutants-killed") | {"inputs": ["/Users/someone/repo/file.py"]}
    write_record(repo, "pbt-mutants-killed", record)
    (problem,) = private_problems(good_entries(), repo_root=repo.root)
    assert problem.startswith("benefit-pbt-mutants-killed.json: field 'inputs' contains the absolute")


def test_an_unparseable_record_is_still_scanned_for_private_paths(repo):
    write_record(repo, "pbt-mutants-killed", "{ /Users/someone/x")
    (problem,) = private_problems(good_entries(), repo_root=repo.root)
    assert problem.startswith("benefit-pbt-mutants-killed.json: field '(file)' contains the absolute")


def test_the_user_name_of_the_person_running_the_test_is_rejected_without_being_stored_in_the_test(tmp_path):
    name = "synthetic-operator"
    entries = with_baseline("skip-rate", f"by-definition: measured by {name.upper()}")
    (problem,) = private_problems(entries, repo_root=tmp_path, usernames=[name])
    assert problem == "skip-rate.baseline: contains the user name of the person running the test"
    assert name not in problem


def test_a_user_name_inside_a_longer_word_is_accepted(tmp_path):
    entries = with_baseline("skip-rate", "by-definition: the carols collection covers it")
    assert private_problems(entries, repo_root=tmp_path, usernames=["carol"]) == []


def test_user_names_shorter_than_three_characters_are_ignored(monkeypatch):
    monkeypatch.setattr(getpass, "getuser", lambda: "ab")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="xy\n"))
    assert current_usernames() == []


def test_current_usernames_reads_the_operating_system_and_git_names(monkeypatch):
    monkeypatch.setattr(getpass, "getuser", lambda: "os-user")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="Git User\n"))
    assert current_usernames() == ["os-user", "Git User"]


def test_an_unset_git_user_name_is_ignored(monkeypatch):
    monkeypatch.setattr(getpass, "getuser", lambda: "os-user")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=""))
    assert current_usernames() == ["os-user"]


# --- thresholds ------------------------------------------------------------------------------------------


def test_real_thresholds_equal_the_merged_values():
    findings = Findings()
    check_thresholds(real_entries(), findings)
    assert not findings.problems, findings.report()


@pytest.mark.parametrize("field_name", THRESHOLD_FIELDS)
def test_a_moved_threshold_is_rejected_naming_metric_and_field(field_name):
    entries = good_entries()
    entries["skip-rate"][field_name] = 99 if field_name == "minimum_n" else "> 99"
    (problem,) = problems_for(entries, check_thresholds)
    assert problem.startswith(f"skip-rate.{field_name}: is ")


def test_a_rationale_can_be_reworded_without_moving_a_threshold():
    entries = good_entries()
    entries["skip-rate"]["rationale"] = "A different explanation."
    assert problems_for(entries, check_thresholds) == []


def test_a_metric_missing_from_the_pre_registration_is_reported_by_the_threshold_check():
    entries = good_entries()
    del entries["skip-rate"]
    (problem,) = problems_for(entries, check_thresholds)
    assert problem.startswith("skip-rate:")


def test_audit_still_reports_13_metrics_and_exits_1_for_the_pre_registration(tmp_path, capsys):
    cli = load_cli("benefit_baseline_status_cli")
    code = cli.main(cli_argv("audit", World(tmp_path), REAL_PREREG, "--json"))
    payload = json.loads(capsys.readouterr().out)
    assert code == payload["exit_code"] == 1
    assert sum(len(status["metrics"]) for status in payload["statuses"]) == 13
