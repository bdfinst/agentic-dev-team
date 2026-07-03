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


def export_plan(plan_path: Path, root: Path) -> List[str]:
    """Export the plan's slice Gherkin blocks under `root`; return report lines."""
    text = plan_path.read_text(encoding="utf-8")
    lines = text.split("\n")

    dest = read_persistence_decision(lines).rstrip("/")
    plan_slug = plan_path.stem
    target_dir = root / dest / plan_slug
    target_dir.mkdir(parents=True, exist_ok=True)

    report = ["destination: {}/{}".format(dest, plan_slug)]
    written = 0
    for sid, title, gherkin in plan_parse.slice_gherkin_blocks(lines):
        if gherkin is None:
            continue
        name = "slice-{}-{}.feature".format(sid, slugify(title))
        (target_dir / name).write_text(gherkin, encoding="utf-8")
        report.append("wrote: {}/{}/{}".format(dest, plan_slug, name))
        written += 1
    report.append("files written: {}".format(written))
    return report


if __name__ == "__main__":  # pragma: no cover
    sys.exit(0)
