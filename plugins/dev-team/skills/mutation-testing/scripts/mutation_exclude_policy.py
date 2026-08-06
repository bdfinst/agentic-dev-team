#!/usr/bin/env python3
"""mutation_exclude_policy.py — committed, human-approved mutation
exclude-policy bootstrap (#1757).

`mutation-kill`'s "Infrastructure exclusion detection"
(agents/mutation-kill.md) already flags likely-infrastructure files at run
time — DI wiring, exception handlers, middleware, generated code — but its
decision persists only to a typically-gitignored build-output path
(`StrykerOutput/mutation-kill-convergence.json`), so it's lost across a
fresh clone or a new CI runner. This module drafts the SAME two-signal
judgment as a standalone, committed, source-controlled policy file instead —
durable across machines.

**Never writes the committed policy file without human approval.** This is
the one hard constraint the whole module exists to satisfy: an unattended
night-watch run can *draft* a proposal (``draft_policy`` + a plain
``write_json`` to any path the caller chooses), but the ONLY code path that
writes ``mutation-exclude-policy.json`` at the repo root is :func:`approve`,
invoked deliberately via ``--approve`` — never called from
``mutation_nightwatch.py``'s unattended loop.

Two-signal rule, ported verbatim from `mutation-kill`'s own "Infrastructure
exclusion detection" section — BOTH must hold before a file is even
considered; neither alone is sufficient:

- ``honest score < 15%``
- ``NoCoverage > 50%`` of effective mutants (killed + survived + no_coverage)

A filename match against a known DI/wiring/generated-code naming convention
is a **hint that strengthens the tier**, never a requirement: it promotes a
flagged file from ``propose_and_ask`` to ``always``, but its absence never
blocks the numeric signals from flagging a file in the first place — mirrors
`mutation-kill.md`'s "named convention vs. signal-only" framing exactly.

Stdlib-only. See ADR 0014.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import sys
from enum import Enum
from pathlib import Path

import mutation_report

POLICY_FILENAME = "mutation-exclude-policy.json"


class ExclusionTier(str, Enum):
    """The two mutation exclude-policy tiers a flagged file can land in
    (issue #1904 item 4) — a closed vocabulary previously carried as bare
    string literals (`"always"`/`"propose_and_ask"`) compared with `==`, so
    a typo silently read as "not the always tier" rather than failing
    loudly. `str, Enum` — deliberately NOT `coverage_config.TestClassification`'s
    convention, which is a plain `Enum` chosen so an accidental attempt to
    JSON-serialize it fails loudly instead of silently succeeding. This
    enum diverges on purpose: its values ARE meant to serialize to JSON
    (`write_json`/`draft_policy`'s output) and to keep matching existing
    bare-string `== "always"`-style call sites, so the `str` mixin is the
    correct choice here, not a mirrored one."""

    ALWAYS = "always"
    PROPOSE_AND_ASK = "propose_and_ask"

# Ported verbatim from agents/mutation-kill.md's "Infrastructure exclusion
# detection" section — the single source of truth for these two numbers.
SCORE_THRESHOLD_PCT = 15.0
NO_COVERAGE_THRESHOLD_PCT = 50.0

# Filename hints per stack. The C# list is copied verbatim from
# mutation-kill.md; the javascript list is a parallel, analogous set for a
# second stack mutation_report.py can already score — see SUPPORTED_STACKS
# in mutation_nightwatch_stacks.py.
#
# Coverage is intentionally partial. ``"csharp"`` and ``"javascript"`` have
# curated filename hints today; ``"python"``, ``"java"``, and ``"go"`` — all
# recognized by mutation_nightwatch_stacks.py's STACK_DETECTORS/MEASURERS —
# do not yet. That is not an oversight: a file flagged for one of those
# stacks by the two-signal rule alone still lands in the ``propose_and_ask``
# tier (never dropped), it just never gets promoted to ``always`` until
# someone writes its filename-hint list. See KNOWN_STACKS_WITHOUT_HINTS
# below, which makes that gap explicit rather than indistinguishable from a
# typo'd/unrecognized stack name (#1854).
FILENAME_HINTS: dict[str, list[str]] = {
    "csharp": [
        "Startup.cs",
        "Program.cs",
        "*Filter.cs",
        "*Middleware.cs",
        "*Logger*.cs",
        "*HealthCheck*.cs",
        "*.Designer.cs",
        "*Module.cs",
        "*Container.cs",
        "*Registration.cs",
        "*Bootstrap*.cs",
        "*DependencyInjection*.cs",
    ],
    "javascript": [
        "main.ts",
        "main.js",
        "*.module.ts",
        "*.config.js",
        "*.config.ts",
        "*Middleware.ts",
        "*Logger*.ts",
        "*Container.ts",
    ],
}

# Stacks recognized by mutation_nightwatch_stacks.py that deliberately have
# no curated FILENAME_HINTS entry yet (not written, not a typo). A stack in
# neither this set nor FILENAME_HINTS is genuinely unknown — see
# _matching_hint below.
KNOWN_STACKS_WITHOUT_HINTS: frozenset[str] = frozenset({"python", "java", "go"})


def _matching_hint(filename: str, stack: str) -> str | None:
    """Return the first filename-hint pattern that matches, or ``None``.

    Raises ``ValueError`` when ``stack`` is neither in ``FILENAME_HINTS`` nor
    ``KNOWN_STACKS_WITHOUT_HINTS`` — a genuinely unrecognized/typo'd stack
    name must surface loudly rather than silently returning no hints (#1854).
    """
    if stack not in FILENAME_HINTS and stack not in KNOWN_STACKS_WITHOUT_HINTS:
        raise ValueError(
            f"unknown stack: {stack!r} (known: "
            f"{sorted(set(FILENAME_HINTS) | KNOWN_STACKS_WITHOUT_HINTS)})"
        )
    for pattern in FILENAME_HINTS.get(stack, ()):
        if fnmatch.fnmatch(filename, pattern):
            return pattern
    return None


def draft_entries(report_path: Path, stack: str) -> list[dict]:
    """Apply the two-signal rule to every file in `report_path`'s native
    report, returning one ``{file, stack, tier, reason}`` entry per flagged
    file. A file with zero effective mutants (killed+survived+no_coverage)
    yields no scoring signal and is never flagged."""
    data = mutation_report.load_report(report_path)
    entries = []
    for file_key in sorted(data.get("files", {})):
        summary = mutation_report.score_report_for_file(report_path, file_key)
        effective = summary.killed + summary.survived + summary.no_coverage
        if effective == 0:
            continue
        no_coverage_pct = (summary.no_coverage / effective) * 100
        # Both signals must hold — failing either alone must never flag.
        if summary.honest_score >= SCORE_THRESHOLD_PCT:
            continue
        if no_coverage_pct <= NO_COVERAGE_THRESHOLD_PCT:
            continue

        hint = _matching_hint(Path(file_key).name, stack)
        if hint:
            tier = ExclusionTier.ALWAYS
            reason = (
                f"named convention: {hint} (score {summary.honest_score:.1f}%, "
                f"NoCoverage {no_coverage_pct:.1f}%)"
            )
        else:
            tier = ExclusionTier.PROPOSE_AND_ASK
            reason = (
                f"signal-only: score {summary.honest_score:.1f}%, NoCoverage "
                f"{no_coverage_pct:.1f}% (no filename match)"
            )
        entries.append({"file": file_key, "stack": stack, "tier": tier, "reason": reason})
    return entries


def draft_policy(report_paths: dict[str, Path]) -> dict:
    """Draft a two-tier exclude policy from one native report per stack.

    ``report_paths`` maps stack name -> native report path. A stack with no
    on-disk native report path (mutmut/python — see
    ``mutation_nightwatch_stacks.StackResult.report_path``'s docstring) is
    simply absent from the mapping; it is never guessed at.
    """
    always: list[dict] = []
    propose_and_ask: list[dict] = []
    for stack, report_path in sorted(report_paths.items()):
        for entry in draft_entries(report_path, stack):
            (always if entry["tier"] == ExclusionTier.ALWAYS else propose_and_ask).append(entry)
    return {
        "schema_version": 1,
        ExclusionTier.ALWAYS.value: always,
        ExclusionTier.PROPOSE_AND_ASK.value: propose_and_ask,
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def approve(draft_path: Path, repo_root: Path) -> Path:
    """Write the approved draft as the committed policy file at
    `repo_root`. The ONLY code path that writes `POLICY_FILENAME` at the
    repo root — see the module docstring's approval-gate constraint."""
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    policy_path = repo_root / POLICY_FILENAME
    write_json(policy_path, draft)
    return policy_path


def parse_args(argv) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="mutation_exclude_policy.py",
        description=(
            "Draft (never auto-write) a two-tier mutation exclude policy from "
            "native mutation reports; write the committed policy file only "
            "on --approve."
        ),
    )
    p.add_argument(
        "--report",
        action="append",
        default=[],
        metavar="STACK=PATH",
        help="One native report path per stack, e.g. "
        "javascript=reports/mutation/mutation.json. Repeatable.",
    )
    p.add_argument("--draft", action="store_true", help="Draft mode.")
    p.add_argument("--out", help="Where to write the draft (--draft mode).")
    p.add_argument(
        "--approve", metavar="DRAFT_PATH", help="Approve a draft, writing the committed policy file."
    )
    p.add_argument(
        "--repo-root", default=".", help="Repo root (--approve mode; default: cwd)"
    )
    return p.parse_args(list(argv))


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = parse_args(argv)

    if args.approve:
        policy_path = approve(Path(args.approve), Path(args.repo_root).resolve())
        print(f"approved: wrote {policy_path}")
        return 0

    if args.draft:
        if not args.out:
            sys.stderr.write("error: --draft requires --out\n")
            return 2
        report_paths = {}
        for item in args.report:
            if "=" not in item:
                sys.stderr.write(f"error: --report must be STACK=PATH, got {item!r}\n")
                return 2
            stack, _, path_str = item.partition("=")
            report_paths[stack] = Path(path_str)
        policy = draft_policy(report_paths)
        write_json(Path(args.out), policy)
        print(f"drafted: wrote {args.out}")
        return 0

    sys.stderr.write("error: pass --draft or --approve\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
