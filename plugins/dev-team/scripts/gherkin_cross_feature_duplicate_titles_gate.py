#!/usr/bin/env python3
"""gherkin_cross_feature_duplicate_titles_gate.py — flag a scenario title that
appears under two or more distinct Feature: blocks (issue #1526).

Mirrors `gherkin_failure_path_gate.py`'s shape: scans `.feature` files under
one or more directories, parses each `Feature:` block's scenario titles (with
each scenario's own line number), and flags any title that recurs under more
than one distinct Feature title. A title repeated multiple times under the
*same* Feature title is out of scope here — that is
`gherkin_feature_merge.py`'s own within-file merge-dedup concern (issue
#1420), already handled there. This gate exists because a generic,
surface-agnostic scenario title (e.g. "returns error for invalid input") can
collide across two unrelated endpoints/surfaces; `gherkin_feature_merge.py`'s
dedup only ever compares titles *within* the Feature block it is merging
into, so a cross-file collision like this is otherwise invisible until a
human notices two features documenting "the same" scenario.

Stdlib-only. (ADR 0014/0015).

Usage:
    python3 gherkin_cross_feature_duplicate_titles_gate.py --dir <dir> [--dir <dir> ...] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE / "lib"))

from _gherkin_text import FEATURE_PREFIX as _FEATURE_PREFIX
from _gherkin_text import SCENARIO_OUTLINE_PREFIX as _SCENARIO_OUTLINE_PREFIX
from _gherkin_text import SCENARIO_PREFIX as _SCENARIO_PREFIX
from _gherkin_text import safe_for_terminal as _safe_for_terminal
from _gherkin_text import stripped as _stripped
from _gherkin_text import trim_trailing_tag_run as _trim_trailing_tag_run
from _vendored_tree import find_files as _find_files


def find_feature_files(directories: list) -> list:
    """Return every `.feature` file under `directories`, pruning vendored
    trees, sorted for deterministic output."""
    return _find_files(directories, lambda path: path.suffix == ".feature")


def parse_scenario_locations(text: str, path) -> list:
    """Return one entry per `Scenario:`/`Scenario Outline:` line across every
    `Feature:` block in `text`: {file, feature_title, scenario_title, line}.
    `line` is the scenario's own 1-based line number (not the enclosing
    Feature block's), since the report needs to point at the exact
    colliding line, not just the block it lives in."""
    lines = text.splitlines(keepends=True)
    header_indices = [
        i for i, line in enumerate(lines) if _stripped(line).strip().startswith(_FEATURE_PREFIX)
    ]
    entries = []
    for idx, header_index in enumerate(header_indices):
        feature_title = _stripped(lines[header_index]).strip()[len(_FEATURE_PREFIX) :].strip()
        end_index = header_indices[idx + 1] if idx + 1 < len(header_indices) else len(lines)
        end_index = _trim_trailing_tag_run(lines, header_index, end_index)
        for line_index in range(header_index + 1, end_index):
            stripped = _stripped(lines[line_index]).strip()
            if stripped.startswith(_SCENARIO_OUTLINE_PREFIX):
                title = stripped[len(_SCENARIO_OUTLINE_PREFIX) :].strip()
            elif stripped.startswith(_SCENARIO_PREFIX):
                title = stripped[len(_SCENARIO_PREFIX) :].strip()
            else:
                continue
            entries.append(
                {
                    "file": str(path),
                    "feature_title": feature_title,
                    "scenario_title": title,
                    "line": line_index + 1,
                }
            )
    return entries


def find_cross_feature_duplicates(entries: list) -> list:
    """Group `entries` by scenario title; return one finding per title that
    appears under 2+ *distinct* Feature titles: {scenario_title,
    occurrences: [{feature_title, file, line}, ...]}. A title repeated only
    under one Feature title (any number of times) is not a finding — that is
    gherkin_feature_merge.py's own within-file dedup concern, out of scope
    here."""
    by_title = defaultdict(list)
    for entry in entries:
        by_title[entry["scenario_title"]].append(entry)

    findings = []
    for title, occurrences in by_title.items():
        if len({o["feature_title"] for o in occurrences}) < 2:
            continue
        findings.append(
            {
                "scenario_title": title,
                "occurrences": [
                    {
                        "feature_title": o["feature_title"],
                        "file": o["file"],
                        "line": o["line"],
                    }
                    for o in occurrences
                ],
            }
        )
    findings.sort(key=lambda f: f["scenario_title"])
    return findings


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="gherkin_cross_feature_duplicate_titles_gate.py",
        description="Flag a scenario title duplicated across distinct Feature: blocks.",
    )
    parser.add_argument("--dir", dest="dirs", action="append", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    files = find_feature_files(args.dirs)

    if not files:
        # Mirrors gherkin_failure_path_gate.py's identical decision: a --dir
        # that resolves to zero .feature files must say so distinctly, not
        # report an affirmative all-clear for zero evidence scanned.
        dirs_display = ", ".join(str(d) for d in args.dirs)
        message = f"no .feature files found under {dirs_display} — gate did not run"
        if args.json:
            print(json.dumps({"scanned": [], "findings": [], "warning": message}, indent=2))
        else:
            # --dir is composed by gherkin-derive from a probe of the target
            # repo, not always typed by a human — the same untrusted-path
            # class as a scanned file's path, sanitized the same way.
            print(f"WARN: no .feature files found under {_safe_for_terminal(dirs_display)} — gate did not run")
        return 2

    all_entries = []
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        all_entries.extend(parse_scenario_locations(text, path))

    findings = find_cross_feature_duplicates(all_entries)

    if args.json:
        print(json.dumps({"scanned": [str(f) for f in files], "findings": findings}, indent=2))
        return 1 if findings else 0

    if findings:
        print(f"FAIL: {len(findings)} scenario title(s) duplicated across distinct Feature blocks:")
        for finding in findings:
            title = _safe_for_terminal(finding["scenario_title"])
            locations = " and ".join(
                f"{_safe_for_terminal(o['feature_title'])} "
                f"({_safe_for_terminal(o['file'])}:{o['line']})"
                for o in finding["occurrences"]
            )
            print(f"  - \"{title}\" appears in {locations}")
        return 1

    print(
        f"OK: {len(all_entries)} scenario(s) scanned, "
        "no title is duplicated across distinct Feature blocks."
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
