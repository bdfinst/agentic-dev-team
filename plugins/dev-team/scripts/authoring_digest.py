#!/usr/bin/env python3
"""Build a per-diff authoring digest for the software-engineer (prototype).

Each review lens may carry a ``## Authoring checklist`` section: terse,
write-time reflexes distilled from its ``Detect`` rules. Given the files a step
will touch, this resolves the applicable lenses with ``select_lenses`` (same
``Scope:`` rules ``/build`` already uses) and prints only those lenses'
checklists, so the engineer pays tokens only for lenses that can fire.

The lens files stay the single source of truth; nothing is copied by hand.

Lenses deliberately WITHOUT a checklist (#2208 triage) — each needs a reviewer's
independence or whole-change view, not a write-time reflex: ``arch-review`` and
``domain-review`` (cross-module/ADR/boundary judgement), ``spec-compliance-review``
(verifies against the step's scenarios, which ``/build`` already hands the
engineer), ``doc-review`` (whole-repo drift), and the on-demand repo-wide lenses.
Framework lenses (React/Vue/Angular/a11y) are excluded by scope for other diffs.

Stdlib-only. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import select_lenses

HEADING = "## Authoring checklist"
_H2_RE = re.compile(r"^## ")


def extract_checklist(text: str) -> list[str]:
    """Bullet lines under the ``## Authoring checklist`` heading, else ``[]``."""
    bullets: list[str] = []
    active = False
    for line in text.splitlines():
        if line.startswith(HEADING):
            active = True
            continue
        if active and _H2_RE.match(line):
            break
        if active and line.lstrip().startswith("- "):
            bullets.append(line.rstrip())
    return bullets


def build_digest(files, agents_dir: Path, registry: Path):
    """Return ``(digest_text, lenses_with_checklist, warnings)``."""
    roster, warnings = select_lenses.build_review_roster(agents_dir, registry)
    lenses, more = select_lenses.applicable_lenses(
        list(files), roster, test_files=select_lenses.test_file_subset(list(files))
    )
    warnings = warnings + more
    sections: list[str] = []
    used: list[str] = []
    for name in lenses:
        try:
            text = (agents_dir / f"{name}.md").read_text(encoding="utf-8")
        except OSError:
            warnings.append(f"unreadable-agent:{name}")
            continue
        bullets = extract_checklist(text)
        if bullets:
            used.append(name)
            sections.append(f"### {name}\n" + "\n".join(bullets))
    if not sections:
        return "", used, warnings
    return "## Authoring checklist (write-time)\n\n" + "\n\n".join(sections) + "\n", used, warnings


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--files", nargs="*", default=[], help="Files the step will touch")
    p.add_argument("--agents-dir", type=Path, default=_HERE.parent / "agents")
    p.add_argument(
        "--registry", type=Path, default=_HERE.parent / "knowledge" / "agent-registry.md"
    )
    args = p.parse_args(argv)
    digest, _used, warnings = build_digest(args.files, args.agents_dir, args.registry)
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    sys.stdout.write(digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
