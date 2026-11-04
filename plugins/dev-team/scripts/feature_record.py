#!/usr/bin/env python3
"""feature_record — one derived JSON record of a plan, its spec and its build progress.

The Markdown plan stays the authoring surface. This module reads it (and the
spec it names) into a single view and reports which stated invariants the
record breaks. The view is derived on every call and is never stored.

Library: `build_record`, `violations`, `plan_violations`, `spec_violations`,
`introduced`. CLI:
`view <plan> [--spec <path>]` and `check <plan> [--spec <path>]`.

The library functions are pure on `str` input and never raise. Only `main`
touches files.
"""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path

# Bare sibling imports, as `plan_waves.py` does: `scripts/lib` is not a package.
_LIB = str(Path(__file__).resolve().parent / "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

import plan_parse
import plan_record_parse

SCHEMA = 1

# Decides whether a commit backs one ticked Build Progress item: True backed,
# False not backed, None cannot be established. The library never runs git; the
# CLI supplies a callback built on `commit_evidence`.
CommitEvidence = Callable[[dict[str, object]], "bool | None"]

# Same grammar as `plan_parse._SLICE_HEADING_RE` / `_HEADING_RE`; a test pins
# that both agree on the slice ids of the fixtures.
_SLICE_HEADING_RE = re.compile(r"^#{1,3}\s+[Ss]lice\s+([^:]+):\s*(.*)$")
_HEADING_RE = re.compile(r"^#{1,3}\s")
_H2_RE = re.compile(r"^##\s+\S")
_URL_RE = re.compile(r"^https?://\S+", re.IGNORECASE)
_MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
_SPEC_DIR = "docs/specs/"


def _header_value(plan_text: str, name: str) -> str | None:
    """Return the value of the plan's `**<name>**: value` line, read from the
    header only (before the first `## ` heading, outside fences)."""
    pattern = re.compile(rf"^\*\*{name}(?:\*\*\s*:|:\*\*)\s*(.+)$")
    for line, in_fence in plan_parse.iter_slice_body_lines(plan_text):
        if in_fence:
            continue
        if line.startswith("## "):
            return None
        match = pattern.match(line.strip())
        if match:
            return match.group(1).strip()
    return None


def spec_reference(plan_text: str) -> str | None:
    """Return the plan's `**Spec**:` target: a URL or a path, else None.

    A Markdown link yields its target; backticks and angle brackets are
    dropped; a non-URL value is cut at its first whitespace.
    """
    raw = _header_value(plan_text, "Spec")
    if raw is None:
        return None
    link = _MD_LINK_RE.search(raw)
    value = (link.group(1) if link else raw).strip().strip("`<>").strip()
    if not _URL_RE.match(value):
        value = value.split(None, 1)[0].strip("`<>") if value else ""
    return value or None


def _slices(plan_text: str) -> list[dict[str, object]]:
    """Split the plan into `### Slice <n>: <title>` sections, fence-aware."""
    slices: list[dict[str, object]] = []
    current: tuple[str, str] | None = None
    body: list[str] = []

    def flush() -> None:
        if current is None:
            return
        text = "\n".join(body)
        slices.append(
            {
                "number": current[0],
                "title": current[1],
                "scenarios": plan_record_parse.parse_scenarios(text),
                "step_ids": plan_record_parse.parse_step_ids(text),
            }
        )

    for line, in_fence in plan_parse.iter_slice_body_lines(plan_text):
        if not in_fence:
            heading = _SLICE_HEADING_RE.match(line)
            if heading:
                flush()
                current, body = (heading.group(1).strip(), heading.group(2).strip()), []
                continue
            if current is not None and _HEADING_RE.match(line):
                flush()
                current, body = None, []
                continue
        if current is not None:
            body.append(line)
    flush()
    return slices


def _spec_part(
    plan_text: str, spec_text: str | None, spec_source: str | None
) -> dict[str, object] | None:
    source = spec_source if spec_source is not None else spec_reference(plan_text)
    if spec_text is not None:
        sections = [
            line.strip()
            for line, in_fence in plan_parse.iter_slice_body_lines(spec_text)
            if not in_fence and _H2_RE.match(line)
        ]
        return {"source": source, "loaded": True, "reason": None, "sections": sections}
    if source is None:
        return None
    reason = "url-not-fetched" if _URL_RE.match(source) else "not-found"
    return {"source": source, "loaded": False, "reason": reason, "sections": []}


def _commit_backed(
    commit_evidence: CommitEvidence, item: dict[str, object]
) -> bool | None:
    """Ask the callback about one ticked item. Anything but a bool, or a
    callback that raises, is "cannot be established"."""
    try:
        answer = commit_evidence(dict(item))
    except Exception:  # noqa: BLE001 - build_record is total; evidence is advisory
        return None
    return answer if isinstance(answer, bool) else None


def _progress_items(
    items: list[dict[str, object]], commit_evidence: CommitEvidence | None
) -> list[dict[str, object]]:
    """Copy the parsed items and fill `commit_backed` for each ticked one.

    An unticked item, and every item when no callback was given, stays None.
    """
    return [
        dict(
            item,
            commit_backed=(
                _commit_backed(commit_evidence, item)
                if commit_evidence is not None and item["done"]
                else None
            ),
        )
        for item in items
    ]


def build_record(
    plan_text: str,
    spec_text: str | None = None,
    plan_path: str | None = None,
    commit_evidence: CommitEvidence | None = None,
    spec_source: str | None = None,
) -> dict[str, object]:
    """Return the schema-1 feature record for `plan_text`.

    Pure and total: text in, dict out. `spec_source` names the spec when the
    caller chose it (the `--spec` override); otherwise the plan's `**Spec**:`
    line is the source. `commit_evidence` is the optional callback for the
    commit invariant: it is asked about each ticked item, and
    `applicability.commit_evidence` is `evaluated` only when one was given.
    """
    criteria = plan_record_parse.parse_criteria(plan_text)
    covers_by_step = plan_record_parse.parse_covers(plan_text)
    known = {c["id"] for c in criteria}
    unknown = list(
        dict.fromkeys(
            cid for ids in covers_by_step.values() for cid in ids if cid not in known
        )
    )
    progress = plan_record_parse.parse_build_progress(plan_text)
    has_covers = bool(covers_by_step)
    return {
        "schema": SCHEMA,
        "plan": {
            "path": plan_path,
            "status": _header_value(plan_text, "Status"),
            "criteria": criteria,
            "slices": _slices(plan_text),
            "covers": [
                {"step": step, "criteria": ids} for step, ids in covers_by_step.items()
            ],
            "unknown_covers": unknown,
            "blockers": plan_record_parse.parse_blockers(plan_text),
        },
        "spec": _spec_part(plan_text, spec_text, spec_source),
        "build_progress": {
            "legacy": progress["legacy"],
            "items": _progress_items(progress["items"], commit_evidence),
        },
        "applicability": {
            "criterion_coverage": "applies" if has_covers else "not-applicable",
            "reason": None if has_covers else "plan has no Covers line",
            "commit_evidence": (
                "evaluated" if commit_evidence is not None else "not-evaluated"
            ),
        },
    }


# ---------------------------------------------------------------------------
# Violation copy: one table for the WHAT / WHY / HOW text, exported so the
# write guard formats refusals from the same words. Placeholders are filled by
# `make_violation`; `<title>` and `<text>` in a HOW line stay literal because
# they tell the author what to write.
# ---------------------------------------------------------------------------

COPY: dict[str, dict[str, str]] = {
    "ac-no-scenario": {
        "what": (
            '<AC id> "<criterion text, 60 chars>" has no scenario: no step names it, '
            "or its covering slices have none. [ac-no-scenario]"
        ),
        "why": "A criterion with no scenario has no behavior that proves it.",
        "how": (
            'Add "**Covers**: <AC id>" to a step, and a Scenario: under '
            "**Behavior:** in that step's slice."
        ),
    },
    "scenario-no-step": {
        "what": "Slice <n> has a scenario and no step heading. [scenario-no-step]",
        "why": "A scenario with no step is behavior nobody is told to build.",
        "how": 'Add a "#### Step <n>.1: <title>" heading under **Steps:** in Slice <n>.',
    },
    "closed-slice-open-blocker": {
        "what": (
            "Slice <n> is ticked done while an open blocker names it. "
            "[closed-slice-open-blocker]"
        ),
        "why": "A critic blocker means the slice is not done.",
        "how": (
            'Resolve the blocker and add "**Resolved blocker**: Slice <n> - <text>" '
            "under ## Plan Review Summary, or untick Slice <n> under ## Build Progress."
        ),
    },
    "spec-missing-section": {
        "what": 'The spec has no "<heading>" section, or it is empty. [spec-missing-section]',
        "why": (
            "A plan built on an incomplete spec has no intent or criteria "
            "to check against."
        ),
        "how": 'Add "<heading>" with at least one line of text.',
    },
    "tick-without-commit": {
        "what": (
            "Step <id> is ticked done and no commit on this branch backs it. "
            "[tick-without-commit]"
        ),
        "why": "A tick with no commit claims work the history does not show.",
        "how": (
            "Commit the step (touching <declared files>), or untick it "
            "under ## Build Progress."
        ),
    },
}

_PLACEHOLDERS = {
    "ac_id": "<AC id>",
    "text": "<criterion text, 60 chars>",
    "n": "<n>",
    "heading": "<heading>",
    "id": "<id>",
    "files": "<declared files>",
}
_PLACEHOLDER_RE = re.compile("|".join(re.escape(p) for p in _PLACEHOLDERS.values()))
_CRITERION_TEXT_LIMIT = 60


def make_violation(violation_id: str, subject: str, **fields: str) -> dict[str, str]:
    """Return `{id, subject, what, why, how}` with the copy filled from `fields`.

    `fields` are the keys of `_PLACEHOLDERS`. The substitution is one pass, so
    a value that itself contains `<n>` is not expanded again.
    """
    values = {_PLACEHOLDERS[k]: v for k, v in fields.items() if k in _PLACEHOLDERS}
    if "text" in fields:
        values[_PLACEHOLDERS["text"]] = fields["text"][:_CRITERION_TEXT_LIMIT]

    def fill(template: str) -> str:
        return _PLACEHOLDER_RE.sub(
            lambda m: values.get(m.group(0), m.group(0)), template
        )

    copy = COPY[violation_id]
    return {
        "id": violation_id,
        "subject": subject,
        "what": fill(copy["what"]),
        "why": fill(copy["why"]),
        "how": fill(copy["how"]),
    }


def _coverage_violations(plan: dict, applicability: dict) -> list[dict[str, str]]:
    if applicability["criterion_coverage"] != "applies":
        return []
    names: dict[str, set[str]] = {c["step"]: set(c["criteria"]) for c in plan["covers"]}
    found = []
    for criterion in plan["criteria"]:
        cid = criterion["id"]
        covering = [
            s
            for s in plan["slices"]
            if any(cid in names.get(step, ()) for step in s["step_ids"])
        ]
        # No step names it, or no slice that holds a naming step has a scenario.
        if not any(s["scenarios"] for s in covering):
            found.append(
                make_violation("ac-no-scenario", cid, ac_id=cid, text=criterion["text"])
            )
    return found


def _scenario_step_violations(plan: dict) -> list[dict[str, str]]:
    return [
        make_violation("scenario-no-step", f"Slice {s['number']}", n=s["number"])
        for s in plan["slices"]
        if s["scenarios"] and not s["step_ids"]
    ]


def _blocker_key(blocker: dict[str, str]) -> tuple[str, str]:
    return blocker["slice"], " ".join(blocker["text"].split())


def _closed_slice_violations(plan: dict, progress: dict) -> list[dict[str, str]]:
    # A plan with no `## Build Progress` heading is read whole-file ("legacy"):
    # a ticked-looking line anywhere is not a progress line, so nothing is closed.
    closed = (
        set()
        if progress["legacy"]
        else {i["id"] for i in progress["items"] if i["kind"] == "slice" and i["done"]}
    )
    existing = {s["number"] for s in plan["slices"]}
    # A resolved blocker with the same slice and text cancels exactly one open one.
    resolved = Counter(_blocker_key(b) for b in plan["blockers"]["resolved"])
    found = []
    for blocker in plan["blockers"]["open"]:
        key = _blocker_key(blocker)
        if resolved[key] > 0:
            resolved[key] -= 1
        elif key[0] in closed and key[0] in existing:
            found.append(
                make_violation("closed-slice-open-blocker", f"Slice {key[0]}", n=key[0])
            )
    return found


def _commit_violations(progress: dict) -> list[dict[str, str]]:
    """`tick-without-commit` for each ticked item the evidence says no commit
    backs. An item with no answer (None) is unverifiable, not a violation."""
    found = []
    for item in progress["items"]:
        if not (item["done"] and item["commit_backed"] is False):
            continue
        label = "Slice" if item["kind"] == "slice" else "Step"
        fields = {"id": item["id"]}
        declared = item.get("declared_files")
        if declared:
            fields["files"] = ", ".join(declared)
        found.append(
            make_violation("tick-without-commit", f"{label} {item['id']}", **fields)
        )
    return found


def violation_key(violation: dict[str, str]) -> tuple[str, str]:
    """Identity of a violation: its invariant id and subject."""
    return violation["id"], violation["subject"]


def _unique(found: list[dict[str, str]]) -> list[dict[str, str]]:
    first: dict[tuple[str, str], dict[str, str]] = {}
    for violation in found:
        first.setdefault(violation_key(violation), violation)
    return list(first.values())


def violations(record: dict) -> list[dict[str, str]]:
    """Return the structural violations of `record`, in invariant order.

    Reads the record only. One violation per (id, subject).
    """
    plan = record["plan"]
    return _unique(
        _coverage_violations(plan, record["applicability"])
        + _scenario_step_violations(plan)
        + _closed_slice_violations(plan, record["build_progress"])
        + _commit_violations(record["build_progress"])
    )


REQUIRED_SPEC_SECTIONS = (
    "## Intent Description",
    "## Architecture Specification",
    "## Acceptance Criteria",
)
_COMMENT_OPEN, _COMMENT_CLOSE = "<!--", "-->"


def _visible_text(line: str, in_comment: bool) -> tuple[str, bool]:
    """Return `line` without its `<!-- ... -->` parts, and whether a comment is
    still open at the end of the line. Walks by index so a line with many
    comment markers stays linear."""
    kept: list[str] = []
    pos = 0
    while pos < len(line):
        if in_comment:
            end = line.find(_COMMENT_CLOSE, pos)
            if end < 0:
                return "".join(kept), True
            pos, in_comment = end + len(_COMMENT_CLOSE), False
        else:
            start = line.find(_COMMENT_OPEN, pos)
            if start < 0:
                kept.append(line[pos:])
                break
            kept.append(line[pos:start])
            pos, in_comment = start + len(_COMMENT_OPEN), True
    return "".join(kept), in_comment


def _section_has_content(spec_text: str, heading: str) -> bool:
    """True when some `heading` section holds a non-blank line outside a comment.

    A section runs to the next `## ` heading. The comment state is tracked on
    every line and never reset: a `## ` heading or a fenced block inside an
    open comment is commented out, and an unclosed comment runs to the end of
    the document. Outside a comment, fenced lines are literal content, and a
    heading inside a code fence neither starts nor ends a section.
    """
    in_section = False
    in_comment = False
    for line, in_fence in plan_parse.iter_slice_body_lines(spec_text):
        if in_comment:
            visible, in_comment = _visible_text(line, True)
        elif in_fence:
            visible = line
        elif line.startswith("## "):
            in_section = line.strip() == heading
            _, in_comment = _visible_text(line, False)
            continue
        else:
            visible, in_comment = _visible_text(line, False)
        if in_section and visible.strip():
            return True
    return False


def spec_violations(spec_text: str) -> list[dict[str, str]]:
    """Return `spec-missing-section` per required heading that is absent or empty.

    A heading matches by exact text after trimming, case-sensitive. Pure and
    total.
    """
    return [
        make_violation("spec-missing-section", heading, heading=heading)
        for heading in REQUIRED_SPEC_SECTIONS
        if not _section_has_content(spec_text, heading)
    ]


def _all_violations(record: dict, spec_text: str | None) -> list[dict[str, str]]:
    """Structural violations of the record plus those of a loaded spec."""
    found = violations(record)
    if spec_text is not None:
        found = _unique(found + spec_violations(spec_text))
    return found


def plan_violations(
    plan_text: str, spec_text: str | None = None
) -> list[dict[str, str]]:
    """Return the violations of the plan in `plan_text`, and of `spec_text`
    when one is given. Pure and total."""
    return _all_violations(build_record(plan_text, spec_text), spec_text)


def introduced(
    before: list[dict[str, str]], after: list[dict[str, str]]
) -> list[dict[str, str]]:
    """Return the violations in `after` whose (id, subject) is not in `before`."""
    known = {violation_key(v) for v in before}
    return _unique([v for v in after if violation_key(v) not in known])


def unverifiable(record: dict) -> list[str]:
    """Ids of ticked items whose commit evidence could not be established.

    Empty unless commit evidence was evaluated for the record.
    """
    if record["applicability"]["commit_evidence"] != "evaluated":
        return []
    return [
        i["id"]
        for i in record["build_progress"]["items"]
        if i["done"] and i["commit_backed"] is None
    ]


class _InputError(Exception):
    """A path the CLI was told to read cannot be read."""


def _read_text(path: str, what: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        reason = "not valid UTF-8"
    except OSError as exc:
        reason = exc.strerror or type(exc).__name__
    raise _InputError(f"feature_record: cannot read {what} {path}: {reason}")


def _spec_candidates(plan_path: str, ref: str) -> list[Path]:
    """Where a `docs/specs/...` reference may live: the working directory, then
    each ancestor of the plan file up to and including the first directory that
    holds `.git` (the repository root)."""
    candidates = [Path(ref)]
    for parent in Path(plan_path).resolve().parents:
        candidates.append(parent / ref)
        if (parent / ".git").exists():
            break
    return candidates


def _load_referenced_spec(plan_path: str, plan_text: str) -> str | None:
    """Read the local spec the plan's `**Spec**:` line names, or None.

    Only a relative path that stays under `docs/specs/` after normalisation is
    read, so a Spec line cannot make the tool open `README.md`, `../x` or an
    absolute path. A URL is never fetched. An unreadable file reads as None.
    """
    ref = spec_reference(plan_text)
    if ref is None or _URL_RE.match(ref):
        return None
    normalized = posixpath.normpath(ref)
    if not normalized.startswith(_SPEC_DIR):
        return None
    for candidate in _spec_candidates(plan_path, normalized):
        try:
            return candidate.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError, ValueError):
            continue
    return None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="feature_record.py", description="Derive and check the feature record."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name, text in (
        ("view", "print the record as JSON"),
        ("check", "print the violations as JSON; exit 1 when there are any"),
    ):
        command = sub.add_parser(name, help=text)
        command.add_argument("plan", help="path to the plan Markdown file")
        command.add_argument(
            "--spec", help="spec file; overrides the plan's **Spec**: line"
        )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        plan_text = _read_text(args.plan, "plan")
        if args.spec is not None:
            spec_text: str | None = _read_text(args.spec, "spec")
        else:
            spec_text = _load_referenced_spec(args.plan, plan_text)
    except _InputError as exc:
        print(exc, file=sys.stderr)
        return 2
    record = build_record(
        plan_text, spec_text, plan_path=args.plan, spec_source=args.spec
    )
    if args.command == "view":
        print(json.dumps(record, indent=2))
        return 0
    found = _all_violations(record, spec_text)
    pending = unverifiable(record)
    print(
        json.dumps(
            {
                "violations": found,
                "unverifiable": pending,
                "applicability": record["applicability"],
            },
            indent=2,
        )
    )
    print(f"{len(found)} violations, {len(pending)} unverifiable", file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
