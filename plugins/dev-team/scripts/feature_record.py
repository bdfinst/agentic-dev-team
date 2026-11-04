#!/usr/bin/env python3
"""feature_record — one derived JSON record of a plan, its spec and its build progress.

The Markdown plan stays the authoring surface. This module reads it (and the
spec it names) into a single view and reports which stated invariants the
record breaks. The view is derived on every call and is never stored.

Library: `build_record`. CLI: `view <plan> [--spec <path>]`.

`build_record` is pure on `str` input and never raises. Only `main` touches
files.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Bare sibling imports, as `plan_waves.py` does: `scripts/lib` is not a package.
_LIB = str(Path(__file__).resolve().parent / "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

import plan_parse
import plan_record_parse

SCHEMA = 1

# Same grammar as `plan_parse._SLICE_HEADING_RE` / `_HEADING_RE`; a test pins
# that both agree on the slice ids of the fixtures.
_SLICE_HEADING_RE = re.compile(r"^#{1,3}\s+[Ss]lice\s+([^:]+):\s*(.*)$")
_HEADING_RE = re.compile(r"^#{1,3}\s")
_H2_RE = re.compile(r"^##\s+\S")
_URL_RE = re.compile(r"^https?://\S+", re.IGNORECASE)
_MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


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


def build_record(
    plan_text: str,
    spec_text: str | None = None,
    plan_path: str | None = None,
    commit_evidence: object = None,
    spec_source: str | None = None,
) -> dict[str, object]:
    """Return the schema-1 feature record for `plan_text`.

    Pure and total: text in, dict out. `spec_source` names the spec when the
    caller chose it (the `--spec` override); otherwise the plan's `**Spec**:`
    line is the source. `commit_evidence` is accepted for the commit
    invariant and not read yet, so every item's `commit_backed` is None and
    `applicability.commit_evidence` is `not-evaluated`.
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
            "items": [dict(item, commit_backed=None) for item in progress["items"]],
        },
        "applicability": {
            "criterion_coverage": "applies" if has_covers else "not-applicable",
            "reason": None if has_covers else "plan has no Covers line",
            "commit_evidence": "not-evaluated",
        },
    }


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


def _load_referenced_spec(plan_path: str, plan_text: str) -> str | None:
    """Read the local spec the plan's `**Spec**:` line names, or None.

    The path is tried against the working directory, then against each parent
    of the plan file, so a plan checked from a subdirectory still finds
    `docs/specs/...`. A URL is never fetched.
    """
    ref = spec_reference(plan_text)
    if ref is None or _URL_RE.match(ref):
        return None
    candidates = [Path(ref)]
    if not Path(ref).is_absolute():
        candidates += [parent / ref for parent in Path(plan_path).resolve().parents]
    for candidate in candidates:
        try:
            return candidate.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
    return None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="feature_record.py", description="Derive the feature record of a plan."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    view = sub.add_parser("view", help="print the record as JSON")
    view.add_argument("plan", help="path to the plan Markdown file")
    view.add_argument("--spec", help="spec file; overrides the plan's **Spec**: line")
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
    print(json.dumps(record, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
