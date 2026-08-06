#!/usr/bin/env python3
"""Operator decision gate for the xunit.v3 / Stryker shim block (#1791).

Detection of the xunit.v3-blocks-Stryker problem already existed in three
places — the ``stryker_xunit_shim_guard.py`` PreToolUse hook,
``xunit_v3_feature_detector.py``, and ``mutation_feasibility_gate.py`` — but
none of it guaranteed the **operator** saw a clear explanation and a set of
choices. The guard printed what it scaffolded and blocked; the detector
classified constructs for a gate that was never wired end-to-end; the
feasibility gate recorded a fixed waiver string. All three are informative
for a report, not a decision point: the operator could discover after a
multi-hour run that the shim was silently built, silently declined, or
silently degraded, and never learn what their options had been.

This module is that decision point. It has two halves, both pure/stdlib:

1. **The question.** :func:`build_question` turns the detector's per-construct
   classification into an :class:`OperatorQuestion` — what is blocking (per
   construct, per file, with coverage impact) plus the four remediation
   options with their tradeoffs. :func:`render_question` renders it for the
   guard's block body and the feasibility gate's ``ask-operator`` payload, so
   both decision points speak with one voice.

2. **The guarantee.** A rendered question is still just text an agent could
   paraphrase or skip. What makes the gate enforceable is that the guard stays
   blocked until the operator's choice is *recorded* — :func:`record_decision`
   writes it, :func:`decision_for` reads it back, and a decision only covers
   the blocker set it was made about (:attr:`OperatorQuestion.fingerprint`),
   so a newly-appeared blocker re-asks instead of riding on a stale answer.

The four options mirror the issue verbatim: ``port`` the flagged files,
``exclude`` them from the shim's compile set, ``skip`` (temporarily
deactivate) just the offending tests, or ``degrade`` to the no-shim floor.

Audit trail (#1870): the decision store on its own is silent — the same
agent the gate constrains can record its own choice (most plausibly
``exclude``, narrowing mutation coverage) with nothing else in the harness
ever seeing it happen. :func:`record_decision` and :func:`decision_for`
each emit a `boundary_events` entry (a "record"-decision `matched_rule` of
`xunit-v3-shim-decision-record-<choice>` on write, `-honor-<choice>` when a
stored decision is read back and used to drive the guard's outcome), bound
to the question's `fingerprint` as `subject_hash` — the same audit stream
`hooks/pre_commit_review.py`'s dispatch-ledger corroboration is reviewed
from. This does not stop a self-recorded `exclude` from taking effect (the
operator's call is still trusted, per this module's whole design) — it
makes the choice visible to anyone auditing the stream, closing the
"nothing else in the harness ever seeing it happen" gap #1870 raised.

Formerly, ``DEV_TEAM_XUNIT3_SHIM_DECISION_FILE`` let any caller relocate the
decision store at runtime with no audit trail on either the record or honor
path — dropped entirely (#1870): no legitimate caller needs to relocate the
store, so removing the seam closes the unaudited-relocation vector outright
rather than trying to retrofit an audit onto it. The store's location is
always ``artifact_paths.resolve_file(DECISION_CATEGORY, DECISION_FILENAME,
cwd)``.

Stdlib-only. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:  # pragma: no cover - import bootstrap
    sys.path.insert(0, str(_LIB_DIR))

import artifact_paths

try:
    from boundary_events import emit_boundary_event as _emit_boundary_event
except ImportError:  # pragma: no cover - degraded fallback, hooks/lib unreachable

    def _emit_boundary_event(*_args, **_kwargs) -> None:  # type: ignore[misc]
        return None


#: Where a recorded choice lives, relative to `.claude/`.
DECISION_CATEGORY = "metrics"
DECISION_FILENAME = "xunit-v3-shim-decisions.json"


@dataclass(frozen=True)
class Option:
    """One remediation the operator can choose, with its cost stated.

    ``tradeoff`` is not decoration: the whole point of the gate is that the
    operator picks with the cost in view, so an option without one is a
    non-choice dressed up as a choice.
    """

    id: str
    label: str
    tradeoff: str


#: The four choices, in the issue's order — cheapest/most-faithful first,
#: the measurement floor last. `degrade` is deliberately NOT the default:
#: silently taking it on the operator's behalf is the defect this gate fixes.
REMEDIATION_OPTIONS: tuple[Option, ...] = (
    Option(
        id="port",
        label="Port the flagged files to v2-compatible syntax",
        tradeoff="Cheapest when only a couple of files/constructs are flagged, and "
        "the only option that leaves mutation coverage complete. Costs test edits "
        "in the real project (the shim links the same sources, so one edit serves "
        "both) and each replacement must still compile under v3.",
    ),
    Option(
        id="exclude",
        label="Exclude the flagged files from the shim's compile set",
        tradeoff="No test edits — generate_shim.py --compile-exclude drops them and "
        "the shim measures the rest. The excluded files stay UNMEASURED by "
        "mutation, so every mutant they alone would have killed shows up as a "
        "survivor. Safe for coverage-neutral hits, blinding for coverage-bearing "
        "ones.",
    ),
    Option(
        id="skip",
        label="Temporarily deactivate/skip just the offending tests",
        tradeoff="Deactivate the tests instead of rewriting what they assert — a "
        "smaller edit than a full port. It clears the gate ONLY where the "
        "deactivation itself removes the offending construct, e.g. "
        '[Fact(Explicit = true)] becoming [Fact(Skip = "...")]. A construct in the '
        "test BODY (Assert.Skip, TestContext) or on a data attribute ([AutoData], "
        "TheoryDataRow) stays in the source the shim links, so deactivating alone "
        "will not make it compile — those need port or exclude. The deactivated "
        "tests stop protecting their code meanwhile: scaffolding to undo at "
        "teardown, not a permanent change.",
    ),
    Option(
        id="degrade",
        label="Degrade to the no-shim floor (single slow advisory pass)",
        tradeoff="Drives the REAL v3 suite (dotnet-stryker -t mtp with "
        "coverage-analysis off), so nothing is excluded and nothing is edited — "
        "but it is whole-suite-per-mutant, so expect a single, much slower "
        "advisory pass and no mutant-kill loop.",
    ),
)

VALID_CHOICES: tuple[str, ...] = tuple(option.id for option in REMEDIATION_OPTIONS)


@dataclass(frozen=True)
class ConstructGroup:
    """One classified construct rolled up across the files that use it."""

    construct: str
    compile_ability: str
    coverage_impact: str
    count: int
    files: tuple[str, ...]
    example: str


@dataclass(frozen=True)
class Blocker:
    """One detector finding, normalised to this module's shape."""

    file: str
    line: int
    construct: str
    compile_ability: str
    coverage_impact: str
    snippet: str


@dataclass(frozen=True)
class OperatorQuestion:
    """The always-fires question: what blocks, and which four ways out."""

    project: str
    blockers: tuple[Blocker, ...]
    breakdown: tuple[ConstructGroup, ...]
    files: tuple[str, ...]
    unclassified_files: tuple[str, ...]
    fingerprint: str
    options: tuple[Option, ...] = REMEDIATION_OPTIONS

    @property
    def blocking(self) -> bool:
        """True when there is something to ask about at all."""
        return bool(self.blockers or self.unclassified_files)

    @property
    def bearing_count(self) -> int:
        return sum(1 for b in self.blockers if b.coverage_impact == "bearing")

    @property
    def neutral_count(self) -> int:
        return sum(1 for b in self.blockers if b.coverage_impact == "neutral")

    @property
    def headline(self) -> str:
        """The one-sentence "what's blocking" the issue asks for by example."""
        if not self.blocking:
            return (
                f"No shim-breaking xunit.v3 constructs in '{self.project}' — "
                "the v2 shim path is viable as-is."
            )
        file_count = len(set(self.files) | set(self.unclassified_files))
        names = ", ".join(group.construct for group in self.breakdown)
        if self.unclassified_files:
            names = f"{names}, unclassified" if names else "unclassified"
        plural = "s" if file_count != 1 else ""
        return (
            f"{file_count} test file{plural} in '{self.project}' use "
            f"{names}, which the xunit.v2 shim can't compile."
        )

    def as_dict(self) -> dict:
        return {
            "project": self.project,
            "headline": self.headline,
            "fingerprint": self.fingerprint,
            "files": list(self.files),
            "unclassified_files": list(self.unclassified_files),
            "bearing_count": self.bearing_count,
            "neutral_count": self.neutral_count,
            "breakdown": [
                {
                    "construct": g.construct,
                    "compile_ability": g.compile_ability,
                    "coverage_impact": g.coverage_impact,
                    "count": g.count,
                    "files": list(g.files),
                    "example": g.example,
                }
                for g in self.breakdown
            ],
            "options": [
                {"id": o.id, "label": o.label, "tradeoff": o.tradeoff}
                for o in self.options
            ],
        }


def _as_blocker(finding) -> Blocker:
    """Accept either the detector's dataclass or its ``--json`` dict form."""
    get = finding.get if isinstance(finding, dict) else lambda k, d=None: getattr(finding, k, d)
    try:
        line = int(get("line", 0) or 0)
    except (TypeError, ValueError):
        line = 0
    return Blocker(
        file=str(get("file", "") or ""),
        line=line,
        construct=str(get("construct", "") or ""),
        compile_ability=str(get("compile_ability", "") or ""),
        coverage_impact=str(get("coverage_impact", "") or ""),
        snippet=str(get("snippet", "") or ""),
    )


def _dedup(values: Iterable[str]) -> tuple[str, ...]:
    """First-seen order, deduped — mirrors the detector's own file ordering so
    the operator sees the same sequence in both tools."""
    seen: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.append(value)
    return tuple(seen)


def _breakdown(blockers: Sequence[Blocker]) -> tuple[ConstructGroup, ...]:
    order: list[str] = []
    grouped: dict[str, list[Blocker]] = {}
    for blocker in blockers:
        if blocker.construct not in grouped:
            grouped[blocker.construct] = []
            order.append(blocker.construct)
        grouped[blocker.construct].append(blocker)
    groups: list[ConstructGroup] = []
    for construct in order:
        members = grouped[construct]
        groups.append(
            ConstructGroup(
                construct=construct,
                compile_ability=members[0].compile_ability,
                coverage_impact=members[0].coverage_impact,
                count=len(members),
                files=_dedup(m.file for m in members),
                example=members[0].snippet,
            )
        )
    return tuple(groups)


def fingerprint(
    blockers: Sequence[Blocker], unclassified_files: Sequence[str] = ()
) -> str:
    """A stable digest of *which* blockers exist, not where they sit.

    Deliberately excludes line numbers: an unrelated edit that shifts a
    flagged line must not invalidate a decision the operator already made,
    while a genuinely new blocking file or construct must.
    """
    keys = sorted({f"{b.file}::{b.construct}" for b in blockers})
    keys += sorted(f"{f}::unclassified" for f in set(unclassified_files))
    digest = hashlib.sha256("\n".join(keys).encode("utf-8")).hexdigest()
    return digest[:16]


def build_question(
    project: str,
    findings: Iterable,
    unclassified_files: Sequence[str] = (),
) -> OperatorQuestion:
    """Compose the operator question from the detector's classification."""
    blockers = tuple(_as_blocker(f) for f in findings)
    unclassified = _dedup(unclassified_files)
    return OperatorQuestion(
        project=project,
        blockers=blockers,
        breakdown=_breakdown(blockers),
        files=_dedup(b.file for b in blockers),
        unclassified_files=unclassified,
        fingerprint=fingerprint(blockers, unclassified),
    )


def render_question(
    question: OperatorQuestion, *, record_command: str | None = None
) -> list[str]:
    """Render the question as operator-facing lines.

    One renderer for both decision points (the guard's block body and the
    feasibility gate's ``ask-operator`` payload) so the operator cannot get a
    different story depending on which one fired.
    """
    if not question.blocking:
        return [question.headline]

    lines = [question.headline, ""]
    lines.append("What's blocking:")
    for group in question.breakdown:
        lines.append(
            f"  - {group.construct} ({group.compile_ability}, "
            f"coverage-{group.coverage_impact}) — {group.count} hit(s) in "
            f"{len(group.files)} file(s)"
        )
        for blocker in question.blockers:
            if blocker.construct == group.construct:
                lines.append(f"      {blocker.file}:{blocker.line}  {blocker.snippet}")
    if question.unclassified_files:
        lines.append(
            "  - unclassified v3-only usage (needs manual triage — the detector "
            "flagged the file but cannot classify the construct):"
        )
        lines += [f"      {name}" for name in question.unclassified_files]
    lines.append("")
    if question.bearing_count:
        lines.append(
            f"{question.bearing_count} of these hit(s) are coverage-BEARING: "
            "excluding them leaves their lines unmeasured, so mutants there will "
            "report as survivors."
        )
    if question.neutral_count:
        lines.append(
            f"{question.neutral_count} hit(s) are coverage-NEUTRAL (skipped by "
            "default), so excluding those changes no coverage."
        )
    lines.append("")
    lines.append("Your options (pick one — this is the operator's call):")
    for option in question.options:
        lines.append(f"  {option.id}: {option.label}")
        lines.append(f"      Tradeoff: {option.tradeoff}")
    lines.append("")
    lines.append(
        "Present these four options to the operator (AskUserQuestion) and let "
        "them pick. Do NOT choose on their behalf, and do not silently take the "
        "degrade path — that is the failure this gate exists to prevent."
    )
    if record_command:
        lines.append("Then record their choice so this gate can let the run through:")
        lines.append(f"  {record_command}")
    return lines


# --- decision record --------------------------------------------------------


def decision_store_path(cwd: Path | str | None = None) -> Path:
    """Where recorded choices live — always
    `artifact_paths.resolve_file(DECISION_CATEGORY, DECISION_FILENAME, cwd)`.

    No env-var override (#1870): a prior `DEV_TEAM_XUNIT3_SHIM_DECISION_FILE`
    seam let any caller relocate the store at runtime with no audit trail on
    either side — removed rather than audited, since no legitimate caller
    needs it.
    """
    return artifact_paths.resolve_file(DECISION_CATEGORY, DECISION_FILENAME, cwd)


def _emit_decision_event(kind: str, entry: dict, cwd: Path | str | None) -> None:
    """Shared boundary-event emission for the record and honor paths (#1870).

    `kind` is `"record"` (a fresh write in `record_decision`) or `"honor"` (a
    stored decision read back and used to drive the guard's outcome in
    `decision_for`) — folded into `matched_rule` as
    `xunit-v3-shim-decision-<kind>-<choice>`, a closed vocabulary derived
    from `VALID_CHOICES` (never free text). Bound to the entry's own
    `fingerprint` as `subject_hash`, mirroring how the dispatch-ledger
    corroboration binds its own evidence to a content hash — so an audit of
    the stream can tell which blocker set a given decision covered.

    Fail-open, matching `boundary_events.emit_boundary_event`'s own
    contract: a malformed `choice` (should be unreachable given both
    callers' own validation) or any emission failure is swallowed, never
    raised — this is telemetry, not a gate.
    """
    choice = entry.get("choice")
    if choice not in VALID_CHOICES:
        return
    try:
        _emit_boundary_event(
            cwd,
            "xunit_v3_operator_gate",
            "Bash",
            "record",
            f"xunit-v3-shim-decision-{kind}-{choice}",
            subject_hash=entry.get("fingerprint"),
        )
    except Exception:  # noqa: BLE001, S110 - fail-open by design
        pass


def _read_store(cwd: Path | str | None = None) -> dict:
    path = decision_store_path(cwd)
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return {}
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def record_decision(
    project: str,
    choice: str,
    cwd: Path | str | None = None,
    *,
    fingerprint: str,
    files: Sequence[str] = (),
    note: str | None = None,
) -> dict:
    """Persist the operator's choice for ``project``. Returns the entry.

    Raises ``ValueError`` on a choice outside :data:`VALID_CHOICES` — an
    unrecognised answer must be re-asked, never coerced into one of the four —
    and on a missing ``fingerprint``, without which the entry would cover no
    blocker set at all (see :func:`decision_for`). Refusing loudly at write time
    beats writing a record the operator believes answered the gate while the
    gate keeps asking.
    """
    if choice not in VALID_CHOICES:
        raise ValueError(
            f"invalid choice {choice!r}: expected one of {', '.join(VALID_CHOICES)}"
        )
    if not fingerprint:
        raise ValueError(
            "a fingerprint is required: it scopes the decision to the blockers "
            "the operator actually saw. Use the value the guard printed."
        )
    entry = {
        "project": project,
        "choice": choice,
        "fingerprint": fingerprint,
        "files": list(files),
        "note": note,
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    store = _read_store(cwd)
    store[project] = entry
    path = decision_store_path(cwd)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store, indent=2) + "\n", encoding="utf-8")
    _emit_decision_event("record", entry, cwd)
    return entry


def read_decision(project: str, cwd: Path | str | None = None) -> dict | None:
    """The raw recorded entry for ``project``, ignoring fingerprint staleness."""
    entry = _read_store(cwd).get(project)
    return entry if isinstance(entry, dict) else None


def decision_for(
    question: OperatorQuestion, cwd: Path | str | None = None
) -> dict | None:
    """The decision that covers ``question``, or None when the operator must
    (re-)decide.

    Fails closed on every axis, because every "yes" here is a run that proceeds
    without asking:

    - A recorded choice covers only the blocker set it was made about. When the
      fingerprint differs — or is absent, which would otherwise make the entry a
      blanket answer covering every future blocker set — the operator has not
      seen these blockers, and riding on the old answer would silently exclude
      something they never agreed to.
    - A stored ``choice`` outside :data:`VALID_CHOICES` (or missing entirely)
      re-asks rather than being coerced into whichever branch happens to be
      last. ``record_decision`` rejects those on the write side, so reaching
      here means a hand-edited or externally-produced store — precisely why the
      read side is where the guarantee has to hold.

    Emits a `boundary_events` "honor" entry (#1870) whenever a decision
    actually covers ``question`` and is about to drive the guard's outcome —
    every caller that reaches a non-None return here is *using* the decision,
    so this is the single choke point for "on every honor path" without each
    call site (today: `stryker_xunit_shim_guard.py`) needing its own emission.
    """
    entry = read_decision(question.project, cwd)
    if entry is None:
        return None
    if entry.get("choice") not in VALID_CHOICES:
        return None
    if entry.get("fingerprint") != question.fingerprint:
        return None
    _emit_decision_event("honor", entry, cwd)
    return entry


def _cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Record/inspect the operator's xunit.v3 shim remediation choice."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    rec = sub.add_parser("record", help="record the operator's choice")
    rec.add_argument("--project", required=True, help="test project name (csproj stem)")
    rec.add_argument("--choice", required=True, choices=list(VALID_CHOICES))
    rec.add_argument(
        "--fingerprint",
        required=True,
        help="blocker-set fingerprint, as printed by the guard's block body — "
        "required, since it is what scopes the decision to the blockers the "
        "operator saw",
    )
    rec.add_argument(
        "--file", action="append", default=[], help="flagged file the choice covers"
    )
    rec.add_argument("--note", default=None, help="free-text rationale")

    chk = sub.add_parser("check", help="print the recorded choice, if any")
    chk.add_argument("--project", required=True)

    sub.add_parser("options", help="print the four remediation options")

    args = parser.parse_args(list(argv))

    if args.command == "options":
        for option in REMEDIATION_OPTIONS:
            print(f"{option.id}: {option.label}")
            print(f"    Tradeoff: {option.tradeoff}")
        return 0

    if args.command == "record":
        entry = record_decision(
            args.project,
            args.choice,
            fingerprint=args.fingerprint,
            files=args.file,
            note=args.note,
        )
        print(json.dumps(entry, indent=2))
        return 0

    entry = read_decision(args.project)
    if entry is None:
        return 1
    print(json.dumps(entry, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(_cli(sys.argv[1:]))
