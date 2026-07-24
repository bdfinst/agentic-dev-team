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
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import NamedTuple

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE / "lib"))

import plan_parse

_PERSISTENCE_RE = re.compile(r"^\*\*Gherkin persistence\*\*\s*:\s*(.*)$")
_SECTION_HEADING_RE = re.compile(r"^##\s")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")

PLAN_FILE_ONLY = "plan-file-only"


class ExportError(Exception):
    """Fatal export failure; the message names the offending path."""


def _first_non_directory(path: Path) -> Path | None:
    """Return the deepest existing segment of `path` that is not a directory."""
    for candidate in (path, *path.parents):
        if candidate.exists():
            return None if candidate.is_dir() else candidate
    return None


def slugify(title: str) -> str:
    """Lowercase; collapse non-alphanumeric runs to one hyphen; trim hyphens."""
    return _NON_ALNUM_RE.sub("-", title.lower()).strip("-")


def read_persistence_decision(lines: Iterable[str]) -> str | None:
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


def resolve_destination(decision: str) -> str | None:
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


def _resolve_target_dir(destination: str, plan_slug: str, root: Path) -> Path:
    """Validate the destination and return the tool-owned directory.

    The exporter defends itself regardless of what the skill prose
    validated: the recorded destination must stay inside `root` (no absolute
    paths, no `..`, no symlink escape), and the tool-owned directory itself
    must not be a symlink — it is about to be purged of `*.feature` files.
    """
    dest_path = Path(destination)
    if dest_path.is_absolute() or ".." in dest_path.parts:
        raise ExportError(
            f"destination escapes the project root: {destination}"
        )
    target_dir = root / dest_path / plan_slug
    resolved_root = root.resolve()
    resolved_target = target_dir.resolve()
    if resolved_root != resolved_target and resolved_root not in (
        resolved_target.parents
    ):
        raise ExportError(
            f"destination escapes the project root: {destination}"
        )
    if target_dir.is_symlink():
        raise ExportError(
            "tool-owned directory is a symlink, refusing to purge through it: "
            f"{target_dir}"
        )
    collision = _first_non_directory(target_dir)
    if collision is not None:
        raise ExportError(
            f"destination path collides with a non-directory file: {collision}"
        )
    return target_dir


def _collect_features(lines: list[str]) -> tuple[list[tuple[str, str]], list[str]]:
    """Return `(features, skipped)`: exportable `(filename, gherkin)` pairs
    and the ids of slices with no gherkin block. Ids get the same slug
    treatment as titles so a filename is always a single path component."""
    blocks = plan_parse.slice_gherkin_blocks(lines)
    features = [
        (f"slice-{slugify(slice_id)}-{slugify(title)}.feature", gherkin)
        for slice_id, title, gherkin in blocks
        if gherkin is not None
    ]
    skipped = [slice_id for slice_id, _, gherkin in blocks if gherkin is None]
    return features, skipped


def _sync_feature_dir(
    target_dir: Path, features: list[tuple[str, str]]
) -> tuple[int, list[str]]:
    """Clear the tool-owned dir of regular `*.feature` files and write the
    current set; return `(overwritten_count, stale_names_removed)`."""
    existing = (
        sorted(
            p
            for p in target_dir.glob("*.feature")
            if p.is_file() or p.is_symlink()
        )
        if target_dir.is_dir()
        else []
    )
    new_names = {name for name, _ in features}
    overwritten = sum(1 for p in existing if p.name in new_names)
    stale = [p.name for p in existing if p.name not in new_names]
    for path in existing:
        # Unlinking a symlink removes the link, never its target. A file
        # already gone is the desired post-state; tolerate races.
        path.unlink(missing_ok=True)
    target_dir.mkdir(parents=True, exist_ok=True)
    for name, gherkin in features:
        path = target_dir / name
        if path.is_symlink():
            # Never write through a planted link — writes stay inside root.
            path.unlink()
        # write_bytes keeps the content byte-for-byte (no newline translation)
        path.write_bytes(gherkin.encode("utf-8"))
    return overwritten, stale


class _ExportOutcome(NamedTuple):
    features: list[tuple[str, str]]
    skipped: list[str]
    overwritten: int
    stale: list[str]


def _build_report(destination: str, plan_slug: str, outcome: _ExportOutcome) -> list[str]:
    report = [f"destination: {destination}/{plan_slug}"]
    for name, _ in outcome.features:
        report.append(f"wrote: {destination}/{plan_slug}/{name}")
    for name in outcome.stale:
        report.append(f"removed stale: {destination}/{plan_slug}/{name}")
    for slice_id in outcome.skipped:
        report.append(f"skipped (no gherkin block): slice {slice_id}")
    report.append(
        f"files written: {len(outcome.features)}, overwritten: {outcome.overwritten}, stale removed: {len(outcome.stale)}"
    )
    return report


def export_plan(plan_path: Path, root: Path) -> list[str]:
    """Export the plan's slice Gherkin blocks under `root`; return report lines."""
    try:
        text = plan_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ExportError(f"cannot read plan file: {plan_path}") from exc
    lines = text.split("\n")

    decision = read_persistence_decision(lines)
    if decision is None:
        return ["nothing to export: no Gherkin persistence decision recorded"]
    destination = resolve_destination(decision)
    if destination is None:
        return ["nothing to export: Gherkin persistence is plan-file-only"]

    plan_slug = plan_path.stem
    target_dir = _resolve_target_dir(destination, plan_slug, root)
    features, skipped = _collect_features(lines)
    overwritten, stale = _sync_feature_dir(target_dir, features)
    outcome = _ExportOutcome(features, skipped, overwritten, stale)
    return _build_report(destination, plan_slug, outcome)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="plan_gherkin_export.py",
        description="Export an approved plan's slice Gherkin blocks to .feature files.",
    )
    parser.add_argument("plan", type=Path, help="Path to the plan markdown file")
    args = parser.parse_args(argv)
    try:
        report = export_plan(args.plan, Path.cwd())
    except ExportError as exc:
        sys.stderr.write(f"plan-gherkin-export: {exc}\n")
        return 2
    for line in report:
        print(line)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
