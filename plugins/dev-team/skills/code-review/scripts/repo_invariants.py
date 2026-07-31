#!/usr/bin/env python3
"""Deterministic pre-pass for repo-specific "every X has a Y" invariants (#1608).

`/code-review`'s final panel round on PR #1600 independently rediscovered the
same mechanically-checkable fact in four separate agent dispatches
(`doc-review`, `structure-review`, `ai-provenance-review`, `test-review`):
a newly-added script module under a `scripts/` directory had no corresponding
row in its skill's own documentation. That shape — "every module under
SCRIPTS_DIR should be named at least once in its skill's docs" — is a glob
check, not a semantic judgment call, but nothing stopped the full panel from
re-deriving it once per agent per round.

This module is a small, growable registry of such checks. Each check is a
zero-argument function returning a list of finding dicts:

    {"invariant": <str>, "file": <repo-relative str>, "message": <str>}

Add new checks by writing a function and appending it to `CHECKS` below. Start
narrow — this ships with exactly one check (mutation-testing scripts
documented) — and expand opportunistically as more "N agents rediscovered the
same mechanical fact" cases turn up (see the issue for the intended pattern).

Wired into `/code-review` step 2b (see `skills/code-review/SKILL.md`):
findings are injected into agent context the same way static-analysis
findings already are — "detected by static analysis, do not re-report,
focus on semantic concerns" — so agents stop spending tokens re-deriving
facts this script already proved.

Stdlib-only. Python 3.8+. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# skills/code-review/scripts -> skills/code-review -> skills -> plugin root
_PLUGIN_ROOT = Path(__file__).resolve().parents[3]


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def check_mutation_kill_scripts_documented() -> list[dict]:
    """Every .py module under the mutation-testing skill's scripts/ dir must be
    named at least once across that skill's own documentation set — the
    mutation-kill agent, its SKILL.md, and its references/ tree — so a
    reviewer can find a script's purpose without re-deriving it from source.
    """
    scripts_dir = _PLUGIN_ROOT / "skills" / "mutation-testing" / "scripts"
    if not scripts_dir.is_dir():
        return []

    doc_files = [
        _PLUGIN_ROOT / "agents" / "mutation-kill.md",
        _PLUGIN_ROOT / "skills" / "mutation-testing" / "SKILL.md",
    ]
    refs_dir = _PLUGIN_ROOT / "skills" / "mutation-testing" / "references"
    if refs_dir.is_dir():
        doc_files.extend(sorted(refs_dir.rglob("*.md")))

    combined = "\n".join(_read_text(p) for p in doc_files)

    findings = []
    for script in sorted(scripts_dir.glob("*.py")):
        if script.name in combined:
            continue
        findings.append(
            {
                "invariant": "mutation-kill-scripts-documented",
                "file": str(script.relative_to(_PLUGIN_ROOT)),
                "message": (
                    f"{script.name} is not named anywhere in the mutation-testing "
                    "skill's documentation set (agents/mutation-kill.md, "
                    "skills/mutation-testing/SKILL.md, or "
                    "skills/mutation-testing/references/**/*.md). Add a mention "
                    "so reviewers don't have to re-derive its purpose from source."
                ),
            }
        )
    return findings


# Registered checks. Each entry is a zero-arg callable returning findings.
CHECKS = [check_mutation_kill_scripts_documented]


def run_all() -> list[dict]:
    findings = []
    for check in CHECKS:
        findings.extend(check())
    return findings


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    findings = run_all()
    print(json.dumps({"findings": findings}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
