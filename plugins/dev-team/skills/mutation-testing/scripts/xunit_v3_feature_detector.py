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
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

CLEAN_TRANSLATABLE = "clean-translatable"
NO_V2_EQUIVALENT = "no-v2-equivalent"
COVERAGE_NEUTRAL = "neutral"
COVERAGE_BEARING = "bearing"


@dataclass(frozen=True)
class Construct:
    name: str
    pattern: re.Pattern[str]
    compile_ability: str
    coverage_impact: str
    note: str


# Each entry's classification is grounded in xunit.v3's documented surface —
# xunit.net/docs/getting-started/v3/whats-new (Explicit property, Assert.Skip*,
# TestContext, IAsyncLifetime→ValueTask, TheoryDataRow) — validated against real
# xunit behavior in #1156. C# attribute/keyword casing is fixed, so patterns are
# case-sensitive (no re.IGNORECASE).
_CONSTRUCTS: list[Construct] = [
    Construct(
        name="fact-explicit",
        # [Fact(Explicit = true)] / [Theory(Explicit=true)] — the property does
        # not exist on v2's FactAttribute.
        #
        # `(?:[^\]"]|"[^"]*")*` consumes either a non-quote character or a WHOLE
        # quoted span, never a lone `"`. So the property match can never land
        # inside a string (a DisplayName="Explicit = true" is still not a hit),
        # but it can step over a completed one — the previous `[^\]"]*` could
        # only refuse to enter a quote, which silently hid every form where a
        # string-valued property came first: `[Fact(DisplayName = "x",
        # Explicit = true)]`. The same construct is allowed to share its bracket
        # (`[Trait("a","b"), Fact(Explicit = true)]`) rather than having to own
        # it, matching the autofixture construct's reasoning below.
        pattern=re.compile(
            r"\[(?:[^\]\"]|\"[^\"]*\")*?\b(?:Fact|Theory)\s*\("
            r"(?:[^\]\"]|\"[^\"]*\")*?\bExplicit\s*=\s*true"
        ),
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
    Construct(
        name="autofixture-auto-data",
        # AutoFixture.Xunit3's attribute family. The bare-name alternations are
        # word-bounded so `MemberAutoData`/`InlineAutoData` each count once
        # instead of also matching a nested `AutoData` — an inflated blocker
        # count is an operator-visible defect at the gate (#1791). Matching the
        # attribute NAME rather than requiring a leading `[` is deliberate:
        # `[Theory, AutoData]` is the common form and has no bracket of its own.
        pattern=re.compile(
            r"\bAutoFixture\.Xunit3\b|\bAutoData\b|\bInlineAutoData\b"
            r"|\bAutoMoqData\b|\bMemberAutoData\b"
        ),
        compile_ability=NO_V2_EQUIVALENT,
        coverage_impact=COVERAGE_BEARING,
        note="AutoFixture.Xunit3's [AutoData]/[InlineAutoData]/[AutoMoqData]/"
        "[MemberAutoData] target xunit.v3's attribute surface; the generated shim "
        "mirrors the package reference verbatim, so the linked sources fail to "
        "compile under xunit.v2. Porting means a manual `new Fixture()` in the "
        "body or [Theory]+[InlineData] rows — heavy if pervasive. Coverage-bearing "
        "(these tests run and cover code). A file that names AutoFixture.Xunit2 "
        "and not .Xunit3 is NOT flagged (see _suppressed_constructs): the "
        "attribute names are identical between the two packages, and the v2 one "
        "already compiles in the shim.",
    ),
    Construct(
        name="assert-multiple",
        pattern=re.compile(r"\bAssert\.Multiple\s*\("),
        compile_ability=NO_V2_EQUIVALENT,
        coverage_impact=COVERAGE_BEARING,
        note="Assert.Multiple (grouped assertion reporting) is v3-only; v2 has no "
        "equivalent, so the call must become sequential asserts. The test runs and "
        "covers code.",
    ),
    Construct(
        name="assert-equivalent",
        pattern=re.compile(r"\bAssert\.Equivalent\s*\("),
        compile_ability=NO_V2_EQUIVALENT,
        coverage_impact=COVERAGE_BEARING,
        note="Assert.Equivalent (structural equivalence) is v3-only; under v2 it "
        "must become an explicit member-by-member or collection assertion. The "
        "test runs and covers code.",
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


#: Constructs whose pattern alone cannot decide, keyed to the file-level signal
#: that resolves them. See :func:`_suppressed_constructs`.
_V2_AUTOFIXTURE = "AutoFixture.Xunit2"
_V3_AUTOFIXTURE = "AutoFixture.Xunit3"


def _suppressed_constructs(text: str) -> frozenset[str]:
    """Constructs to skip for this file because a file-level signal clears them.

    ``[AutoData]`` and friends are spelled IDENTICALLY by AutoFixture.Xunit2 and
    AutoFixture.Xunit3, so the attribute name alone cannot tell a shim blocker
    from code that already compiles under v2. When a file declares the v2
    package and not the v3 one, it is not a blocker — flagging it would stall
    the operator gate on nothing and, if they chose ``exclude``, drop
    v2-compatible tests out of measurement.

    Absence of both signals is NOT treated as v2: the reference may be a global
    using or live in the ``.csproj``, so the construct is still reported and the
    operator decides. Blocking and asking is the safe default here; silently
    proceeding into a shim that cannot compile is not.
    """
    if _V2_AUTOFIXTURE in text and _V3_AUTOFIXTURE not in text:
        return frozenset({"autofixture-auto-data"})
    return frozenset()


def scan_text(path: str, text: str) -> list[Finding]:
    """Return the v3-only constructs found in ``text``, attributed to ``path``.

    Line-oriented so each finding carries a 1-based line number and the source
    snippet the operator will see at the gate.
    """
    findings: list[Finding] = []
    suppressed = _suppressed_constructs(text)
    for lineno, line in enumerate(text.splitlines(), start=1):
        # Skip fully commented-out lines so a `// [Fact(Explicit = true)]` in
        # dead code isn't flagged as a shim-breaker. A trailing comment on a
        # real code line is left alone (the code before `//` still matters).
        if line.lstrip().startswith("//"):
            continue
        for construct in _CONSTRUCTS:
            if construct.name in suppressed:
                continue
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


def scan_file(path: Path) -> list[Finding]:
    """Scan a single .cs file. Missing/unreadable files yield no findings."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except (OSError, FileNotFoundError):
        return []
    return scan_text(str(path), text)


def scan_files(paths: Iterable[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for p in paths:
        findings.extend(scan_file(p))
    return findings


def files_with_findings(findings: Sequence[Finding]) -> list[str]:
    """Distinct files carrying at least one shim-breaking construct — the
    candidate exclusion set the human gate offers (dedup, stable order)."""
    seen: list[str] = []
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
