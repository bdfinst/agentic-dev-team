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
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE / "lib"))

from _gherkin_text import FEATURE_PREFIX as _FEATURE_PREFIX
from _gherkin_text import SCENARIO_OUTLINE_PREFIX as _SCENARIO_OUTLINE_PREFIX
from _gherkin_text import SCENARIO_PREFIX as _SCENARIO_PREFIX
from _gherkin_text import stripped as _stripped
from _vendored_tree import find_files as _find_files

# C0/C1 control characters (excluding the ordinary whitespace already
# stripped elsewhere) — stripped before printing scanned-file content to a
# terminal. A `.feature` file's Feature: title is untrusted (it comes from
# whatever repository is being scanned) and could otherwise inject terminal
# escape sequences (CWE-150) or masquerade as trusted tool output fed back
# into an agent's report.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def _safe_for_terminal(text: str, limit: int = 200) -> str:
    """Strip control characters and bound length before printing untrusted
    scanned-file text to a terminal (the `--json` path is unaffected —
    `json.dumps` already escapes control characters)."""
    return _CONTROL_CHARS.sub("", text)[:limit]


def _is_tag_line(line: str) -> bool:
    stripped = _stripped(line).strip()
    if not stripped:
        return False
    return all(tok.startswith("@") for tok in stripped.split())

# Entries are literal substrings, not stems — "exceeds" does not match
# "exceed" — matching gherkin_feature_merge.py's `is_stale` in spirit (a
# deliberately simple, best-effort check, not a semantic classifier). A
# cleanup pass "fixing" what looks like a stray verb-form mismatch would
# silently change gate behavior: the documented false-positive test
# (test_extra_keyword_can_produce_a_documented_false_positive) specifically
# relies on "exceed" being absent from this list by default. "exceeds" is
# the intended default per issue #1420 — the false positive it enables (a
# scenario using "exceed" instead) is accepted and demonstrated by that
# same test via --extra-keyword, not an oversight.
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
    return _find_files(directories, lambda path: path.suffix == ".feature")


def parse_features(text: str, path) -> list:
    """Return one entry per `Feature:` block: {file, feature_title, line,
    scenario_titles, scenario_text} — scenario_text is every non-header line
    in the block, used for keyword matching against step text as well as
    titles. `file` is set here from `path` (a caller no longer patches it in
    afterward) so a feature dict is never partially constructed — the
    "title" key is also named `feature_title` here to match every other
    consumer of this concept (`gherkin_feature_merge.py`'s `--feature-title`,
    and this module's own finding dict below)."""
    lines = text.splitlines(keepends=True)
    features = []
    header_indices = [
        i for i, line in enumerate(lines) if _stripped(line).strip().startswith(_FEATURE_PREFIX)
    ]
    for idx, header_index in enumerate(header_indices):
        title = _stripped(lines[header_index]).strip()[len(_FEATURE_PREFIX) :].strip()
        end_index = header_indices[idx + 1] if idx + 1 < len(header_indices) else len(lines)
        # A `@tag`/blank-line run immediately preceding the next Feature:
        # header belongs to that next block, not this one (Gherkin tags
        # attach to the declaration that follows them) — mirrors
        # gherkin_feature_merge.py's _block_end fix for the identical bug.
        # Without this, a tag like `@error-handling` on the *following*
        # Feature block leaks into this block's scenario_text, and a
        # keyword match against that leaked tag can make this block pass
        # the gate even though it has no failure-path scenario of its own.
        while end_index > header_index + 1:
            prev = lines[end_index - 1]
            if _stripped(prev).strip() == "" or _is_tag_line(prev):
                end_index -= 1
            else:
                break
        body = lines[header_index + 1 : end_index]
        scenario_titles = []
        for line in body:
            stripped = _stripped(line).strip()
            if stripped.startswith(_SCENARIO_OUTLINE_PREFIX):
                scenario_titles.append(stripped[len(_SCENARIO_OUTLINE_PREFIX) :].strip())
            elif stripped.startswith(_SCENARIO_PREFIX):
                scenario_titles.append(stripped[len(_SCENARIO_PREFIX) :].strip())
        features.append(
            {
                "file": str(path),
                "feature_title": title,
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
                    "feature_title": feature["feature_title"],
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
        help=(
            "Discard the default keyword list and use only the --keyword "
            "value(s) given (repeatable) — this REPLACES the defaults, it "
            "does not add to them. To add one term on top of the defaults, "
            "use --extra-keyword instead."
        ),
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

    if not files:
        # A --dir that doesn't exist (or resolves to zero .feature files)
        # used to fall through to "OK: 0 Feature block(s) scanned, all have
        # a failure-path scenario" below — an affirmative all-clear for zero
        # evidence. --dir is not always typed by a human: gherkin-derive
        # composes it from a probe of the target repo, so a gate that can't
        # find anything to scan must say so distinctly, not pass.
        dirs_display = ", ".join(str(d) for d in args.dirs)
        message = f"no .feature files found under {dirs_display} — gate did not run"
        if args.json:
            print(json.dumps({"scanned": [], "findings": [], "warning": message}, indent=2))
        else:
            print(f"WARN: {message}")
        return 2

    all_features = []
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        all_features.extend(parse_features(text, path))

    findings = find_missing_failure_path(all_features, keywords)

    if args.json:
        print(json.dumps({"scanned": [str(f) for f in files], "findings": findings}, indent=2))
        return 1 if findings else 0

    if findings:
        print(f"FAIL: {len(findings)} Feature block(s) missing a failure-path scenario:")
        for entry in findings:
            print(f"  - {entry['file']}:{entry['line']} — {_safe_for_terminal(entry['feature_title'])}")
        return 1

    print(f"OK: {len(all_features)} Feature block(s) scanned, all have a failure-path scenario.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
