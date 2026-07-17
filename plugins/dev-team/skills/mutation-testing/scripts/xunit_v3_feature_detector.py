#!/usr/bin/env python3
"""Detect xunit.v3-only constructs that break the v2 mutation-shim compile,
and classify each so a human can decide how to handle it (#1160, part of #1156).

The v2 shim is the only path that gives the mutant-kill loop per-test coverage
on an xunit.v3 suite (validated in #669). Its weakness is compile fragility:
any xunit-v3-only API breaks the shim's compile before Stryker runs a mutant.
This module turns that opaque C# compile error into a classified list the
mutation-kill agent presents at an **always-ask, never-auto-drop** human gate.

Two classification axes:

- ``compile_ability`` — ``clean-translatable`` (a mechanical v2 equivalent
  exists) or ``no-v2-equivalent`` (the construct cannot compile under v2).
- ``coverage_impact`` — ``neutral`` (excluding the test from the shim changes
  no coverage, e.g. ``[Fact(Explicit = true)]`` tests are skipped by default)
  or ``bearing`` (the test runs and covers code, so excluding it inflates the
  loop's survivor set — the operator must be told which lines go dark).

Pure and stdlib-only. The interactive gate and the actual shim-exclusion wiring
(#1159) consume this module's structured output; this module never edits a file.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, List, Sequence


CLEAN_TRANSLATABLE = "clean-translatable"
NO_V2_EQUIVALENT = "no-v2-equivalent"
COVERAGE_NEUTRAL = "neutral"
COVERAGE_BEARING = "bearing"


@dataclass(frozen=True)
class Construct:
    name: str
    pattern: "re.Pattern[str]"
    compile_ability: str
    coverage_impact: str
    note: str


# Each entry's classification is grounded in xunit.v3's documented surface —
# xunit.net/docs/getting-started/v3/whats-new (Explicit property, Assert.Skip*,
# TestContext, IAsyncLifetime→ValueTask, TheoryDataRow) — validated against real
# xunit behavior in #1156. C# attribute/keyword casing is fixed, so patterns are
# case-sensitive (no re.IGNORECASE).
_CONSTRUCTS: List[Construct] = [
    Construct(
        name="fact-explicit",
        # [Fact(Explicit = true)] / [Theory(Explicit=true)] — the property does
        # not exist on v2's FactAttribute. `[^\]"]*` stops the property match
        # from crossing into a quoted argument (e.g. DisplayName="Explicit = true").
        pattern=re.compile(r"\[\s*(?:Fact|Theory)\s*\([^\]\"]*\bExplicit\s*=\s*true"),
        compile_ability=NO_V2_EQUIVALENT,
        coverage_impact=COVERAGE_NEUTRAL,
        note="Explicit tests are skipped unless the run opts in (-explicit / "
        "xunit.runner.json explicit=on), so under a normal mutation run they "
        "contribute zero coverage — excluding them from the shim changes nothing. "
        "Neutral ONLY while the run does not enable explicit tests.",
    ),
    Construct(
        name="assert-skip",
        # Assert.Skip / Assert.SkipWhen / Assert.SkipUnless — dynamic skip is v3-only.
        pattern=re.compile(r"\bAssert\.(?:Skip|SkipWhen|SkipUnless)\s*\("),
        compile_ability=NO_V2_EQUIVALENT,
        coverage_impact=COVERAGE_BEARING,
        note="Dynamic skip has no v2 equivalent (v2 skip is a static attribute). "
        "The test runs and covers code; excluding it hides that coverage.",
    ),
    Construct(
        name="test-context",
        pattern=re.compile(r"\b(?:TestContext\.Current|ITestContext)\b"),
        compile_ability=NO_V2_EQUIVALENT,
        coverage_impact=COVERAGE_BEARING,
        note="TestContext/ITestContext is v3-only with no v2 equivalent; the "
        "test runs and covers code.",
    ),
    Construct(
        name="async-lifetime-valuetask",
        # v3's IAsyncLifetime uses ValueTask InitializeAsync/DisposeAsync;
        # v2 uses Task. Mechanically translatable but changes signatures.
        pattern=re.compile(
            r"\bValueTask\s+(?:InitializeAsync|DisposeAsync)\s*\("
        ),
        compile_ability=CLEAN_TRANSLATABLE,
        coverage_impact=COVERAGE_BEARING,
        note="v3's IAsyncLifetime returns ValueTask (and extends IAsyncDisposable); "
        "v2's returns Task. Translatable for the common CompletedTask case but not "
        "purely a return-type swap — the interface surface differs and cached "
        "ValueTask / IValueTaskSource bodies don't map trivially. Coverage-bearing "
        "(runs real setup/teardown).",
    ),
    Construct(
        name="theory-data-row",
        pattern=re.compile(r"\bTheoryDataRow\b"),
        compile_ability=CLEAN_TRANSLATABLE,
        coverage_impact=COVERAGE_BEARING,
        note="v3's TheoryDataRow maps to v2's TheoryData<> for value-only rows; "
        "rows carrying per-row metadata (Skip/Explicit/Traits/TestDisplayName) "
        "lose it in translation. Coverage-bearing (the test runs and covers code).",
    ),
]


@dataclass(frozen=True)
class Finding:
    file: str
    line: int
    construct: str
    compile_ability: str
    coverage_impact: str
    snippet: str


def scan_text(path: str, text: str) -> List[Finding]:
    """Return the v3-only constructs found in ``text``, attributed to ``path``.

    Line-oriented so each finding carries a 1-based line number and the source
    snippet the operator will see at the gate.
    """
    findings: List[Finding] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        # Skip fully commented-out lines so a `// [Fact(Explicit = true)]` in
        # dead code isn't flagged as a shim-breaker. A trailing comment on a
        # real code line is left alone (the code before `//` still matters).
        if line.lstrip().startswith("//"):
            continue
        for construct in _CONSTRUCTS:
            if construct.pattern.search(line):
                findings.append(
                    Finding(
                        file=path,
                        line=lineno,
                        construct=construct.name,
                        compile_ability=construct.compile_ability,
                        coverage_impact=construct.coverage_impact,
                        snippet=line.strip(),
                    )
                )
    return findings


def scan_file(path: Path) -> List[Finding]:
    """Scan a single .cs file. Missing/unreadable files yield no findings."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except (OSError, FileNotFoundError):
        return []
    return scan_text(str(path), text)


def scan_files(paths: Iterable[Path]) -> List[Finding]:
    findings: List[Finding] = []
    for p in paths:
        findings.extend(scan_file(p))
    return findings


def files_with_findings(findings: Sequence[Finding]) -> List[str]:
    """Distinct files carrying at least one shim-breaking construct — the
    candidate exclusion set the human gate offers (dedup, stable order)."""
    seen: List[str] = []
    for f in findings:
        if f.file not in seen:
            seen.append(f.file)
    return seen


@dataclass(frozen=True)
class Summary:
    total: int
    files: int
    neutral: int
    bearing: int
    recommendation: str


def summarize(findings: Sequence[Finding]) -> Summary:
    """Roll findings up into counts plus an advisory sizing recommendation.

    The recommendation is advisory only — the gate is always-ask (#1160). It
    never auto-excludes; it tells the operator which way the blast radius leans.
    """
    neutral = sum(1 for f in findings if f.coverage_impact == COVERAGE_NEUTRAL)
    bearing = sum(1 for f in findings if f.coverage_impact == COVERAGE_BEARING)
    files = len(files_with_findings(findings))

    if not findings:
        rec = (
            "No shim-breaking xunit.v3 constructs found — the v2 shim path is "
            "viable as-is."
        )
    elif bearing == 0:
        rec = (
            f"{neutral} coverage-neutral hit(s) across {files} file(s) "
            "(Explicit tests skipped by default). Excluding them from the shim "
            "is safe PROVIDED the run does not enable explicit tests "
            "(-explicit / xunit.runner.json explicit=on) — confirm that, then "
            "proceeding on the shim path is reasonable."
        )
    else:
        rec = (
            f"{bearing} coverage-bearing hit(s) across {files} file(s): "
            "excluding these from the shim blinds the loop to their coverage. "
            "If few and acceptable, exclude and proceed; if many, skip the loop "
            "and run a single-pass advisory with coverage-analysis off."
        )
    return Summary(
        total=len(findings),
        files=files,
        neutral=neutral,
        bearing=bearing,
        recommendation=rec,
    )


def _cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Detect and classify xunit.v3-only, shim-breaking test constructs."
    )
    parser.add_argument("paths", nargs="+", help="test .cs files to scan")
    parser.add_argument(
        "--json", action="store_true", help="emit JSON instead of a table"
    )
    args = parser.parse_args(list(argv))

    findings = scan_files(Path(p) for p in args.paths)
    summary = summarize(findings)

    if args.json:
        print(
            json.dumps(
                {
                    "findings": [asdict(f) for f in findings],
                    "summary": asdict(summary),
                },
                indent=2,
            )
        )
    else:
        for f in findings:
            print(
                f"{f.file}:{f.line}  {f.construct}  "
                f"[{f.compile_ability} / coverage-{f.coverage_impact}]  {f.snippet}"
            )
        print(f"\n{summary.recommendation}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(_cli(sys.argv[1:]))
