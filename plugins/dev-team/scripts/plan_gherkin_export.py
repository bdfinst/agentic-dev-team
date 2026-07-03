#!/usr/bin/env python3
"""plan_gherkin_export.py — export an approved plan's slice Gherkin to .feature files.

Reads the plan's `**Gherkin persistence**:` metadata line and each
`### Slice N:` section's fenced Gherkin block, and writes
`<dir>/<plan-slug>/slice-<N>-<slice-slug>.feature` — byte-for-byte identical
to the fenced block, modulo exactly one trailing newline, with no added
header. plan-slug is the plan filename stem verbatim; slice-slug is the
slice title lowercased with each run of non-alphanumeric characters
collapsed to a single hyphen, leading/trailing hyphens trimmed.

Uses `scripts/lib/plan_parse.py` for the slice-walking stage.

Spec: docs/specs/plan-gherkin-feature-persistence.md (component 2).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Iterable, List, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE / "lib"))

import plan_parse  # noqa: E402

_PERSISTENCE_RE = re.compile(r"^\*\*Gherkin persistence\*\*\s*:\s*(.*)$")
_SECTION_HEADING_RE = re.compile(r"^##\s")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")

PLAN_FILE_ONLY = "plan-file-only"


class ExportError(Exception):
    """Fatal export failure; the message names the offending path."""


def _first_non_directory(path: Path) -> Optional[Path]:
    """Return the deepest existing segment of `path` that is not a directory."""
    for candidate in (path, *path.parents):
        if candidate.exists():
            return None if candidate.is_dir() else candidate
    return None


def slugify(title: str) -> str:
    """Lowercase; collapse non-alphanumeric runs to one hyphen; trim hyphens."""
    return _NON_ALNUM_RE.sub("-", title.lower()).strip("-")


def read_persistence_decision(lines: Iterable[str]) -> Optional[str]:
    """Return the metadata block's Gherkin persistence value, or None.

    Only the metadata block (lines before the first `## ` section heading)
    is scanned, so prose mentions of the marker elsewhere never match.
    """
    for raw in lines:
        line = raw.rstrip("\n")
        if _SECTION_HEADING_RE.match(line):
            return None
        match = _PERSISTENCE_RE.match(line)
        if match:
            value = match.group(1).replace("`", "").strip()
            return value or None
    return None


def resolve_destination(decision: str) -> Optional[str]:
    """Map a recorded decision to a destination directory.

    `plan-file-only` maps to None (nothing to export); a `custom: <path>`
    value maps to its path; anything else is the destination directory
    itself. Trailing slashes are dropped.
    """
    if decision == PLAN_FILE_ONLY:
        return None
    if decision.lower().startswith("custom:"):
        decision = decision.split(":", 1)[1].strip()
    return decision.rstrip("/") or None


def export_plan(plan_path: Path, root: Path) -> List[str]:
    """Export the plan's slice Gherkin blocks under `root`; return report lines."""
    try:
        text = plan_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ExportError("cannot read plan file: {}".format(plan_path)) from exc
    lines = text.split("\n")

    decision = read_persistence_decision(lines)
    if decision is None:
        return ["nothing to export: no Gherkin persistence decision recorded"]
    dest = resolve_destination(decision)
    if dest is None:
        return ["nothing to export: Gherkin persistence is plan-file-only"]

    plan_slug = plan_path.stem
    target_dir = root / dest / plan_slug

    collision = _first_non_directory(target_dir)
    if collision is not None:
        raise ExportError(
            "destination path collides with a non-directory file: {}".format(
                collision
            )
        )

    blocks = plan_parse.slice_gherkin_blocks(lines)
    features = [
        ("slice-{}-{}.feature".format(sid, slugify(title)), gherkin)
        for sid, title, gherkin in blocks
        if gherkin is not None
    ]
    skipped = [sid for sid, _, gherkin in blocks if gherkin is None]

    # The subdirectory is tool-owned: clear it of *.feature files before
    # writing so stale files from renamed/renumbered slices never linger.
    existing = sorted(target_dir.glob("*.feature")) if target_dir.is_dir() else []
    new_names = {name for name, _ in features}
    overwritten = sum(1 for p in existing if p.name in new_names)
    stale = [p for p in existing if p.name not in new_names]
    for path in existing:
        path.unlink()

    target_dir.mkdir(parents=True, exist_ok=True)
    report = ["destination: {}/{}".format(dest, plan_slug)]
    for name, gherkin in features:
        # write_bytes keeps the content byte-for-byte (no newline translation)
        (target_dir / name).write_bytes(gherkin.encode("utf-8"))
        report.append("wrote: {}/{}/{}".format(dest, plan_slug, name))
    for path in stale:
        report.append("removed stale: {}/{}/{}".format(dest, plan_slug, path.name))
    for sid in skipped:
        report.append("skipped (no gherkin block): slice {}".format(sid))
    report.append(
        "files written: {}, overwritten: {}, stale removed: {}".format(
            len(features), overwritten, len(stale)
        )
    )
    return report


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="plan_gherkin_export.py",
        description="Export an approved plan's slice Gherkin blocks to .feature files.",
    )
    parser.add_argument("plan", type=Path, help="Path to the plan markdown file")
    args = parser.parse_args(argv)
    try:
        report = export_plan(args.plan, Path.cwd())
    except ExportError as exc:
        sys.stderr.write("plan-gherkin-export: {}\n".format(exc))
        return 2
    for line in report:
        print(line)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
