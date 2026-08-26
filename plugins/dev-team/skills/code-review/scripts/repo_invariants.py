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

This module is a small, growable registry of such checks. Each check takes an
optional `changed_files` list (repo-relative paths for this review's
changeset, or `None` for "check everything") and returns a list of finding
dicts:

    {"invariant": <str>, "file": <repo-relative str>, "message": <str>}

`changed_files` exists because some invariants are **required going forward
but explicitly not retrofitted** — the `_calibration` convention in
`evals/README.md` is the motivating case ("Required for every NEW fixture
going forward. Do not retrofit the ~140 existing fixtures — that is pure
churn with no discovered provenance to record"). Scoping such a check to the
changeset enforces it on exactly the fixtures being authored right now, which
is also where #1629 wants it: the author gets the finding **before** round 1
instead of from it. A check that applies corpus-wide simply ignores the
argument.

**Not Python-specific — a check operates on whatever file types the
invariant it's proving is about.** The one shipped here happens to walk a
directory that is entirely `.py` today only because this repo's own shipped
scripts are Python-only by convention (ADR 0014/0015); the glob itself
matches every file in that directory regardless of extension, and a future
check is free to target `.ts`/`.cs`/`.java`/`.go`/anything else this repo or
a downstream project's own conventions call for — `/code-review` runs
against projects in every language this plugin supports (see
`skills/static-analysis-integration/references/tool-configs.md`'s
per-language tool tiers), so new checks should not assume a Python target
just because the first one did. Add new checks by writing a function and
appending it to `CHECKS` below. Start narrow — this ships with exactly one
check (mutation-testing scripts documented) — and expand opportunistically
as more "N agents rediscovered the same mechanical fact" cases turn up (see
the issue for the intended pattern).

Wired into `/code-review` step 2b (see `skills/code-review/SKILL.md`):
findings are injected into agent context the same way static-analysis
findings already are — "detected by static analysis, do not re-report,
focus on semantic concerns" — so agents stop spending tokens re-deriving
facts this script already proved.

Stdlib-only. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# skills/code-review/scripts -> skills/code-review -> skills -> plugin root
_PLUGIN_ROOT = Path(__file__).resolve().parents[3]

# The `agents/` directory root and its *-review.md glob are the shared,
# resolved single source of truth in hooks/lib (#1904 item 3) — scripts/ ->
# hooks/lib/ is the correct dependency direction (see
# review_agent_registry.py's own docstring). Import rather than re-deriving
# `_PLUGIN_ROOT / "agents"` locally.
sys.path.insert(0, str(_PLUGIN_ROOT / "hooks" / "lib"))
from review_agent_registry import (
    default_agents_dir,
    find_review_agent_files,
)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


_IGNORED_SCRIPT_NAMES = frozenset({"__init__.py", "__pycache__"})


#: Skills whose `scripts/` modules must each be named in that skill's own
#: documentation. A registry rather than one function per skill: the second
#: skill needing this check arrived (#1981) and copying the first would have
#: reproduced the duplication the review lenses exist to flag.
#:
#: Each entry: (skill name, extra doc paths relative to the plugin root). The
#: skill's own `SKILL.md` and every `references/**/*.md` under it are always
#: part of the doc set; `extra` is for docs that live outside the skill dir.
_DOCUMENTED_SCRIPT_SKILLS = (
    ("mutation-testing", ("agents/mutation-kill.md",), "mutation-kill-scripts-documented"),
    ("code-review", (), "code-review-scripts-documented"),
)


def _skill_doc_text(skill: str, extra: tuple) -> str:
    skill_dir = _PLUGIN_ROOT / "skills" / skill
    doc_files = [skill_dir / "SKILL.md"]
    doc_files.extend(_PLUGIN_ROOT / rel for rel in extra)
    for sub in ("references", ""):
        target = skill_dir / sub if sub else skill_dir
        if target.is_dir():
            doc_files.extend(sorted(target.rglob("*.md")))
    return "\n".join(_read_text(p) for p in doc_files)


def check_skill_scripts_documented(changed_files=None) -> list[dict]:
    """Every module under a registered skill's scripts/ dir must be named at
    least once in that skill's own documentation, so a reviewer can find a
    script's purpose without re-deriving it from source.

    This is the invariant that created this module: on PR #1600 four separate
    agents (`doc-review`, `structure-review`, `ai-provenance-review`,
    `test-review`) independently rediscovered that a newly-added script had no
    documentation row. It shipped covering `mutation-testing` alone.

    #1981 is the second report of the same class, in a different directory:
    `skills/code-review/scripts/` had gained `review_value_coverage.py` (from
    #2020) with no mention in its own skill's docs. Under this repo's ratchet
    rule a twice-reported mechanical class becomes a check, so the hardcoded
    single-skill form became this registry.

    Matches every file regardless of extension — these directories happen to
    be all-Python today (ADR 0014/0015), but "every module is documented" is
    language-agnostic and must keep holding if a differently-extensioned file
    lands.

    Corpus-wide by design: `changed_files` is ignored. An undocumented script
    is a standing gap whether or not this changeset touched it, and the whole
    point is that the panel is told about it once instead of N agents each
    finding it.
    """
    findings = []
    for skill, extra, invariant in _DOCUMENTED_SCRIPT_SKILLS:
        scripts_dir = _PLUGIN_ROOT / "skills" / skill / "scripts"
        if not scripts_dir.is_dir():
            continue
        combined = _skill_doc_text(skill, extra)
        for script in sorted(scripts_dir.iterdir()):
            if not script.is_file() or script.name in _IGNORED_SCRIPT_NAMES:
                continue
            if script.name in combined:
                continue
            findings.append(
                {
                    "invariant": invariant,
                    "file": str(script.relative_to(_PLUGIN_ROOT)),
                    "message": (
                        f"{script.name} is not named anywhere in the {skill} "
                        "skill's own documentation set (its SKILL.md or "
                        "references/**/*.md). Add a mention so reviewers "
                        "don't have to re-derive its purpose from source."
                    ),
                }
            )
    return findings


# --- #1629: churn generators observed in PR #1619 -------------------------
#
# Of #1619's 8 follow-up review rounds, at least 4 were triggered by defect
# classes that never needed an opus reviewer to catch. Each check below
# encodes one of them, so the author sees it at edit time and the panel gets
# "already detected — do not re-report" framing instead of N agents
# rediscovering the same mechanical fact.

_REPO_ROOT = _PLUGIN_ROOT.parents[1]


def _repo_relative(path: Path) -> str:
    try:
        return str(path.relative_to(_REPO_ROOT))
    except ValueError:
        return str(path)


def _changed_set(changed_files):
    if changed_files is None:
        return None
    out = set()
    for raw in changed_files:
        name = str(raw or "").strip().replace("\\", "/")
        while name.startswith("./"):
            name = name[2:]
        if name:
            out.add(name)
    return out


def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _expectation_entries(spec: dict):
    """Yield `(target_name, entry_dict)` for every agent/skill expectation."""
    for section in ("agents", "skills"):
        block = spec.get(section)
        if isinstance(block, dict):
            for name, entry in block.items():
                if isinstance(entry, dict):
                    yield name, entry


def _declares_tolerance_window(entry: dict) -> bool:
    """True when this expectation carries a `min`/`max` tolerance window —
    the precondition `evals/README.md` attaches the `_calibration`
    requirement to. An expectation with only `expectedStatus` and keyword
    lists has no bounds whose provenance could be recorded."""
    count = entry.get("issueCount")
    if isinstance(count, dict) and ("min" in count or "max" in count):
        return True
    severities = entry.get("severities")
    if isinstance(severities, dict):
        for bounds in severities.values():
            if isinstance(bounds, dict) and ("min" in bounds or "max" in bounds):
                return True
    return False


def check_eval_calibration_blocks(changed_files=None) -> list[dict]:
    """Every NEW `evals/expected/*.json` expectation that declares a `min`/
    `max` tolerance window must carry the `_calibration` block
    `evals/README.md` requires.

    #1619's round 1 lost a full `correctness-review` dispatch to exactly this
    — a mechanically checkable convention miss.

    **Scoped to `changed_files` when given.** The README explicitly forbids
    retrofitting the ~140 pre-existing fixtures, so a corpus-wide sweep would
    emit ~140 findings the convention says not to act on. With no changeset
    the check reports nothing rather than every legacy fixture.
    """
    changed = _changed_set(changed_files)
    if changed is None:
        return []

    expected_dir = _REPO_ROOT / "evals" / "expected"
    findings = []
    for name in sorted(changed):
        if not (name.startswith("evals/expected/") and name.endswith(".json")):
            continue
        path = _REPO_ROOT / name
        if not path.is_file():
            continue
        spec = _load_json(path)
        if not isinstance(spec, dict):
            continue
        for target, entry in _expectation_entries(spec):
            if not _declares_tolerance_window(entry):
                continue
            calibration = entry.get("_calibration")
            if isinstance(calibration, dict) and calibration.get("source"):
                continue
            findings.append(
                {
                    "invariant": "eval-calibration-block-required",
                    "file": _repo_relative(path),
                    "message": (
                        f"expectation for {target!r} declares a min/max tolerance "
                        "window but carries no `_calibration` block. "
                        "evals/README.md requires one on every new fixture with "
                        "bounds: {\"source\": \"measured\"|\"estimated-by-analogy\", "
                        '"note": "<one-line rationale>"}. Without it, a later '
                        "\"tidy up the ranges\" pass can silently widen a bound that "
                        "was tuned against this fixture's own measured behavior."
                    ),
                }
            )
    _ = expected_dir  # documented location; findings are keyed off changed paths
    return findings


def check_must_not_mention_terms_appear_in_fixture(changed_files=None) -> list[dict]:
    """Every `mustNotMention` term should actually appear somewhere in its
    paired fixture — otherwise the guard is vacuous.

    `mustNotMention` is an all-of "none of these may appear in the agent's
    output" assertion. If a forbidden term does not occur in the fixture at
    all, the agent had no reason to emit it and the assertion passes
    trivially, proving nothing while reading like coverage. This is the
    corpus-level half of the negation-blindness trap `docs/eval-maintenance.md`
    documents (#1622).

    Coordinates with, rather than duplicates, `scripts/eval_grade.py
    --check-corpus`: if that gate grows this rule, delete this check and let
    the pre-pass call the grader instead. Today `--check-corpus` has no
    `mustNotMention` rule, so this is the only place it is enforced.

    **Scoped to `changed_files`**, like the calibration check and for the same
    reason: the corpus carries ~31 pre-existing hits (measured 2026-07-31),
    some of which are deliberate — `security-review`'s hardcoded-secrets
    fixture forbids "environment variable" to stop the agent recommending a
    weak fix, and that term legitimately isn't in the fixture. Sweeping
    corpus-wide inside every `/code-review` pre-pass would bury each panel in
    unrelated legacy findings, the exact opposite of this slice's purpose.
    Run with `--all` to triage that backlog deliberately.
    """
    changed = _changed_set(changed_files)
    if changed is None:
        return []
    expected_dir = _REPO_ROOT / "evals" / "expected"
    fixtures_dir = _REPO_ROOT / "evals" / "fixtures"
    if not expected_dir.is_dir() or not fixtures_dir.is_dir():
        return []

    fixture_text_by_stem = {}
    for path in fixtures_dir.iterdir():
        stem = path.name if path.is_dir() else path.stem
        if path.is_file():
            fixture_text_by_stem[stem] = _read_text(path).lower()

    findings = []
    for path in sorted(expected_dir.glob("*.json")):
        rel = _repo_relative(path)
        if changed is not None and rel not in changed:
            continue
        spec = _load_json(path)
        if not isinstance(spec, dict):
            continue
        fixture_text = fixture_text_by_stem.get(path.stem)
        if fixture_text is None:
            # No readable paired fixture (a directory fixture, or a missing
            # one --check-corpus already warns about). Nothing to prove here.
            continue
        for target, entry in _expectation_entries(spec):
            for term in entry.get("mustNotMention") or []:
                if not isinstance(term, str) or not term.strip():
                    continue
                if term.lower() in fixture_text:
                    continue
                findings.append(
                    {
                        "invariant": "must-not-mention-term-absent-from-fixture",
                        "file": rel,
                        "message": (
                            f"{target!r} forbids {term!r} via mustNotMention, but that "
                            "string never appears in the paired fixture — the agent had "
                            "no reason to emit it, so the assertion passes trivially and "
                            "proves nothing. Either drop the term (see "
                            "docs/eval-maintenance.md's negation-blindness trap) or point "
                            "it at something the fixture actually contains."
                        ),
                    }
                )
    return findings


#: `Scope:` glob extensions vs. the prose Skip rule's extension list. A
#: review agent that declares `**/*.{js,mjs,cjs,ts}` in `Scope:` but whose
#: Skip section only names `.js`/`.ts` self-skips on files the resolver
#: correctly routed to it — the `.mjs`/`.cjs` mismatch class from #1622.
_SCOPE_BLOCK_RE = re.compile(r"^\s*Scope\s*:\s*(.*)$", re.MULTILINE)
_EXT_RE = re.compile(r"\.([a-z0-9]{1,6})\b", re.IGNORECASE)
_BRACE_RE = re.compile(r"\{([^}]*)\}")


def _scope_extensions(body: str) -> set:
    """Extensions named by an agent's `Scope:` glob list, expanding brace
    alternation (`*.{js,mjs}`)."""
    match = _SCOPE_BLOCK_RE.search(body)
    if not match:
        return set()
    # A Scope: block may be a scalar on one line or a following YAML-ish list.
    start = match.end()
    lines = [match.group(1)]
    for line in body[start:].splitlines():
        if line.startswith(("-", " ", "\t")) and line.strip():
            lines.append(line)
        elif line.strip():
            break
    text = "\n".join(lines)
    exts = set()
    for group in _BRACE_RE.findall(text):
        for part in group.split(","):
            part = part.strip().lstrip(".")
            if part and re.fullmatch(r"[a-z0-9]{1,6}", part, re.IGNORECASE):
                exts.add("." + part.lower())
    text = _BRACE_RE.sub(" ", text)
    exts.update(m.group(0).lower() for m in _EXT_RE.finditer(text))
    return exts


def _skip_section_extensions(body: str) -> set:
    """Extensions named in the agent's prose `## Skip` section."""
    match = re.search(r"^##\s+Skip\s*$", body, re.MULTILINE)
    if not match:
        return set()
    rest = body[match.end() :]
    end = re.search(r"^##\s+", rest, re.MULTILINE)
    section = rest[: end.start()] if end else rest
    return {m.group(0).lower() for m in _EXT_RE.finditer(section)}


def check_scope_glob_matches_skip_prose(changed_files=None) -> list[dict]:
    """A review agent's `Scope:` globs and its prose `## Skip` rule must name
    the same file extensions.

    When `Scope:` routes `.mjs`/`.cjs` to an agent whose Skip section only
    lists `.js`/`.ts`, the agent self-skips files the resolver deliberately
    sent it — a silent coverage hole no runtime check catches, and the
    mismatch class #1622 found. Only extensions the Skip section could
    plausibly be enumerating are compared: a Skip section naming no
    extensions at all is not making a claim about file types.

    **Scoped to `changed_files`** for consistency with the two checks above.
    Three pre-existing hits exist as of 2026-07-31 — `js-fp-review`
    (`.mjs`/`.cjs`, the original #1622 case), `angular-reactivity-review`,
    and `component-architecture-review` — all real, none fixed by this slice,
    which adds the detector rather than the corrections. `--all` surfaces
    them for deliberate triage.
    """
    changed = _changed_set(changed_files)
    if changed is None:
        return []
    agents_dir = default_agents_dir()
    if not agents_dir.is_dir():
        return []

    findings = []
    for path in find_review_agent_files(agents_dir):
        rel = _repo_relative(path)
        if changed is not None and rel not in changed:
            continue
        body = _read_text(path)
        scope_exts = _scope_extensions(body)
        skip_exts = _skip_section_extensions(body)
        if not scope_exts or not skip_exts:
            continue
        missing = sorted(scope_exts - skip_exts)
        if not missing:
            continue
        findings.append(
            {
                "invariant": "scope-glob-skip-prose-extension-drift",
                "file": rel,
                "message": (
                    f"Scope: routes {', '.join(missing)} to this agent, but its "
                    "## Skip section never names those extensions. The agent will "
                    "self-skip files the resolver deliberately sent it — a silent "
                    "coverage hole. Add them to the Skip prose, or narrow the "
                    "Scope: globs so the two agree."
                ),
            }
        )
    return findings


def check_contract_failure_shapes_documented(changed_files=None) -> list[dict]:
    """`telemetry-schema.md`'s `contract-failures.jsonl` `shape` table row
    must enumerate exactly `validate_review_output.FAILURE_SHAPES` (#1998).

    Two independent review agents (doc-review in wave 1, domain-review in
    wave 2 — same PR) rediscovered the same drift: prose enumerating the
    loggable failure shapes disagreeing with the module's actual behavior.
    `SKILL.md` no longer re-enumerates the set itself (it now points at
    `telemetry-schema.md` instead), so only one doc can drift from the code
    now — this check pins that one doc to the module's exported set rather
    than trusting prose to stay in sync by hand.
    """
    telemetry_schema = _PLUGIN_ROOT / "knowledge" / "telemetry-schema.md"
    text = _read_text(telemetry_schema)
    match = re.search(r"\|\s*`shape`\s*\|\s*string enum\s*\|([^\n]*)", text)
    if not match:
        return [
            {
                "invariant": "contract-failure-shapes-documented",
                "file": "knowledge/telemetry-schema.md",
                "message": (
                    "Could not find the contract-failures.jsonl `shape` table row to "
                    "check against validate_review_output.FAILURE_SHAPES — has the "
                    "table row been reworded or removed?"
                ),
            }
        ]
    cell = match.group(1).split(" — ", 1)[0]
    documented = frozenset(re.findall(r"`([a-z-]+)`", cell))

    from validate_review_output import FAILURE_SHAPES

    if documented == FAILURE_SHAPES:
        return []
    return [
        {
            "invariant": "contract-failure-shapes-documented",
            "file": "knowledge/telemetry-schema.md",
            "message": (
                f"telemetry-schema.md's contract-failures.jsonl `shape` row documents "
                f"{sorted(documented)}, but validate_review_output.FAILURE_SHAPES is "
                f"{sorted(FAILURE_SHAPES)} — keep the table row and the module's "
                "exported set in sync."
            ),
        }
    ]


# Registered checks. Each entry takes an optional `changed_files` list and
# returns findings. See the module docstring for why that argument exists.
CHECKS = [
    check_skill_scripts_documented,
    check_eval_calibration_blocks,
    check_must_not_mention_terms_appear_in_fixture,
    check_scope_glob_matches_skip_prose,
    check_contract_failure_shapes_documented,
]


def run_all(changed_files=None) -> list[dict]:
    findings = []
    for check in CHECKS:
        findings.extend(check(changed_files))
    return findings


def _sweep_all() -> list[dict]:
    """Backlog triage (`--all`): re-run the changeset-scoped checks against
    every file they could apply to, so a maintainer can see the pre-existing
    findings each convention chose not to retrofit. Never used by the
    `/code-review` pre-pass."""
    every_expected = [
        _repo_relative(p) for p in sorted((_REPO_ROOT / "evals" / "expected").glob("*.json"))
    ]
    every_agent = [
        _repo_relative(p) for p in find_review_agent_files(default_agents_dir())
    ]
    return run_all(every_expected + every_agent)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--files",
        nargs="*",
        default=None,
        help=(
            "Repo-relative changed files for this review. Checks scoped to new "
            "content (e.g. the _calibration convention, which evals/README.md "
            "forbids retrofitting) only fire for these paths."
        ),
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="sweep_all",
        help=(
            "Deliberate backlog triage: run every changeset-scoped check across "
            "the whole corpus. Not for the /code-review pre-pass — it surfaces "
            "pre-existing findings the convention that introduced each check "
            "explicitly does not require retrofitting."
        ),
    )
    args = parser.parse_args(argv)
    if args.sweep_all:
        findings = _sweep_all()
    else:
        findings = run_all(args.files)
    print(json.dumps({"findings": findings}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
