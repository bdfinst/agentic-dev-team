#!/usr/bin/env python3
"""Decide whether /ship's Review phase is redundant (#2212).

/build's inline checkpoints and Step 6 backstop already record per-lens
verdicts in ``.claude/metrics/review-verdicts.jsonl`` keyed by
``(lens, file, content hash)``. When every resolver-selected lens has a
``pass`` row for every changed file at its CURRENT content, a second
whole-change ``/code-review`` has nothing left to examine.

Fail-closed: no files, no ledger, an unhashable file, or any missing/failing
row means ``skip: false`` — the pass runs, exactly as before.

Stdlib-only. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import select_lenses
import verdict_scope


def decide(files, root: Path, agents_dir: Path, registry: Path) -> dict:
    files = list(files)
    if not files:
        return {"skip": False, "reason": "no-changed-files"}
    roster, warnings = select_lenses.build_review_roster(agents_dir, registry)
    lenses, more = select_lenses.applicable_lenses(
        files, roster, test_files=select_lenses.test_file_subset(files)
    )
    warnings = warnings + more
    if not lenses:
        return {"skip": False, "reason": "no-applicable-lenses", "warnings": warnings}
    result = verdict_scope.resolve_for_root({n: files for n in lenses}, root)
    pending = {k: v for k, v in result["toDispatch"].items() if v}
    if pending:
        return {"skip": False, "reason": "uncleared-lens-files", "pending": pending,
                "warnings": warnings}
    return {"skip": True, "reason": "all-lenses-cleared-at-current-content",
            "lenses": sorted(lenses), "warnings": warnings}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--root", type=Path, default=Path("."))
    p.add_argument("--files", nargs="*", default=[])
    p.add_argument("--agents-dir", type=Path, default=_HERE.parent / "agents")
    p.add_argument("--registry", type=Path,
                   default=_HERE.parent / "knowledge" / "agent-registry.md")
    args = p.parse_args(argv)
    print(json.dumps(decide(args.files, args.root, args.agents_dir, args.registry)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
