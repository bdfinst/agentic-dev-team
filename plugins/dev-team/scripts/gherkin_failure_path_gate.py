#!/usr/bin/env python3
"""gherkin_failure_path_gate.py — flag Feature: blocks with no failure-path
scenario (issue #1420).

Mirrors `gherkin_stub_gate.py`'s shape: scans `.feature` files under one or
more directories, parses each `Feature:` block's scenarios, and flags any
block whose scenarios (title + step text, case-insensitive) match none of a
keyword list. This is a deliberately simple, best-effort heuristic, not a
semantic classifier — both false negatives (a genuine failure scenario
phrased without any listed keyword) and false positives (a happy-path
scenario coincidentally containing a listed substring, e.g. "does not exceed
the limit") are possible and accepted; `--keyword`/`--extra-keyword` let a
repo tune the list.

Stdlib-only. Python 3.8+ (ADR 0014/0015).

Usage:
    python3 gherkin_failure_path_gate.py --dir <dir> [--dir <dir> ...] [--json]
    python3 gherkin_failure_path_gate.py --dir features --extra-keyword declined
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _vendored_tree import iter_files as _iter_files

DEFAULT_KEYWORDS = (
    "invalid",
    "error",
    "fail",
    "unauthorized",
    "not found",
    "denied",
    "timeout",
    "exceeds",
    "missing",
    "malformed",
)


def find_feature_files(directories: list) -> list:
    """Return every `.feature` file under `directories`, pruning vendored
    trees, sorted for deterministic output."""
    found = []
    for directory in directories:
        if not directory.is_dir():
            continue
        for path in _iter_files(directory):
            if path.suffix == ".feature":
                found.append(path)
    return sorted(set(found))


def _stripped(line: str) -> str:
    return line.rstrip("\r\n")


def parse_features(text: str) -> list:
    """Return one entry per `Feature:` block: {title, line, scenario_titles,
    scenario_text} — scenario_text is every non-header line in the block,
    used for keyword matching against step text as well as titles."""
    lines = text.splitlines(keepends=True)
    features = []
    header_indices = [
        i for i, line in enumerate(lines) if _stripped(line).strip().startswith("Feature:")
    ]
    for idx, header_index in enumerate(header_indices):
        title = _stripped(lines[header_index]).strip()[len("Feature:") :].strip()
        end_index = header_indices[idx + 1] if idx + 1 < len(header_indices) else len(lines)
        body = lines[header_index + 1 : end_index]
        scenario_titles = []
        for line in body:
            stripped = _stripped(line).strip()
            if stripped.startswith("Scenario Outline:"):
                scenario_titles.append(stripped[len("Scenario Outline:") :].strip())
            elif stripped.startswith("Scenario:"):
                scenario_titles.append(stripped[len("Scenario:") :].strip())
        features.append(
            {
                "title": title,
                "line": header_index + 1,
                "scenario_titles": scenario_titles,
                "scenario_text": "".join(body),
            }
        )
    return features


def find_missing_failure_path(features: list, keywords) -> list:
    """Return {file, line, feature_title} for every feature with zero
    scenarios (title + step text, case-insensitive) matching `keywords`."""
    findings = []
    lowered_keywords = [k.lower() for k in keywords]
    for feature in features:
        haystack = (feature["scenario_text"] + " " + " ".join(feature["scenario_titles"])).lower()
        if not any(keyword in haystack for keyword in lowered_keywords):
            findings.append(
                {
                    "file": feature["file"],
                    "line": feature["line"],
                    "feature_title": feature["title"],
                }
            )
    return findings


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="gherkin_failure_path_gate.py",
        description="Flag Feature: blocks with no failure-path scenario.",
    )
    parser.add_argument("--dir", dest="dirs", action="append", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--keyword",
        dest="keywords",
        action="append",
        help="Replace the default keyword list entirely (repeatable).",
    )
    parser.add_argument(
        "--extra-keyword",
        dest="extra_keywords",
        action="append",
        default=[],
        help="Add to the default keyword list (repeatable).",
    )
    args = parser.parse_args(argv)

    keywords = list(args.keywords) if args.keywords else list(DEFAULT_KEYWORDS)
    keywords.extend(args.extra_keywords)

    files = find_feature_files(args.dirs)
    all_features = []
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for feature in parse_features(text):
            feature["file"] = str(path)
            all_features.append(feature)

    findings = find_missing_failure_path(all_features, keywords)

    if args.json:
        print(json.dumps({"scanned": [str(f) for f in files], "findings": findings}, indent=2))
        return 1 if findings else 0

    if findings:
        print(f"FAIL: {len(findings)} Feature block(s) missing a failure-path scenario:")
        for entry in findings:
            print(f"  - {entry['file']}:{entry['line']} — {entry['feature_title']}")
        return 1

    print(f"OK: {len(all_features)} Feature block(s) scanned, all have a failure-path scenario.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
