"""Every shell invocation a shipped SKILL.md instructs its dispatching agent
to run must be covered by that skill's own `allowed-tools` Bash grant, or the
instruction is fiction — the agent has no way to execute it (#1652).

Found via `agent-audit/SKILL.md`: its frontmatter declared no `Bash` grant at
all (`allowed-tools: Read, Edit, Grep, Glob`), while its body instructed three
`python3 ...` invocations. None could execute. Review flagged the deeper risk
directly: "never exercised" is indistinguishable from "intentionally
cwd-relative" by static inspection alone — the same trap that hid the
original #1631/#1636/#1637 defects. A general guard closes that gap for any
skill, not just the one instance a human happened to notice.

## Scope and known limits

This scans FENCED ```bash/```sh code blocks only. `agent-audit/SKILL.md`
itself has an invocation written as inline prose inside a bare ``` fence with
no language tag right after "Run the deterministic sensor:" — caught here —
but a skill could still instruct a command via a backtick code SPAN or plain
prose sentence with no fence at all; that broader sweep (docs/, references/,
inline hints) is #1655's job, not this one. This guard is deliberately
narrower and mechanical: "does a fenced shell command in this skill's own
body match a Bash() pattern this skill's own frontmatter declares."

A bare `Bash` (no parens) in `allowed-tools` is UNRESTRICTED — it covers every
invocation in that skill's body, and such skills are skipped entirely; there
is nothing to check.

## Why a tracked list, not a hard gate on every skill

The scan surfaced this same defect class in 9 more skills beyond
`agent-audit` (16 invocations total) at the time this file was added. Fixing
all of them is out of scope for #1652 — that issue named `agent-audit`
specifically. Following this repo's established shrink-only pattern (see
`tests/repo/test_agent_implemented_by_resolves.py`'s `KNOWN_BARE_INVOCATION`),
each pre-existing gap is named explicitly in `KNOWN_UNCOVERED_INVOCATIONS`
below so this guard can go live immediately without either mass-editing 9
unrelated skills in this PR or silently exempting them forever. Fixing one
means removing it from the list here in the same commit — leaving a stale
entry after the SKILL.md is fixed is caught by
`test_no_stale_entries_in_the_known_list` below.

`agent-audit` itself must never re-enter this list — that is the specific
regression this file exists to prevent.
"""

from __future__ import annotations

import re

from _repo_root import REPO_ROOT

SKILLS_DIR = REPO_ROOT / "plugins" / "dev-team" / "skills"
SKILLS = sorted(SKILLS_DIR.glob("*/SKILL.md"))

#: (skill_name, invocation_line) pairs that are NOT yet covered by their
#: skill's own `allowed-tools` Bash grant. Shrink-only: fixing a skill's grant
#: (or its body) must remove the matching entry here in the same change, not
#: leave it stale. `agent-audit` must never appear here again (#1652).
KNOWN_UNCOVERED_INVOCATIONS = {
    ("apply-test-doubles", 'sh "$CLAUDE_PLUGIN_ROOT/hooks/py.sh" "$CLAUDE_PLUGIN_ROOT/hooks/lib/plugin_version.py"'),
    ("cd-test-architecture", "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/gherkin_analysis_coverage_gate.py --file <report-path> --config cd-test-architecture"),
    ("cd-test-architecture", 'sh "$CLAUDE_PLUGIN_ROOT/hooks/py.sh" "$CLAUDE_PLUGIN_ROOT/hooks/lib/report_pdf.py" .dev-team-reports/cd-test-architecture-<app>.md'),
    ("harness-audit", 'sh "$CLAUDE_PLUGIN_ROOT/hooks/py.sh" "$CLAUDE_PLUGIN_ROOT/hooks/lib/report_pdf.py" <the-output-path>'),
    ("plan", "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/plan_waves.py <plan-file>"),
    ("plan", "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/plan_gherkin_export.py <plan-file>"),
    ("plan", "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/git_origin_host.py"),
    ("pr", "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/progress_guardian.py --pre-pr --plan <plan-file>"),
    ("pr", "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/pr_close_keyword_lint.py --body-file <body-file>"),
    ("project-init", "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/install-java-static-analysis.py"),
    ("ship", "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/lib/workflow_state.py record \\"),
    ("ship", "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/lib/iteration_journal_gate.py record \\"),
    ("ship", "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/lib/iteration_journal_gate.py check \\"),
    ("stryker-xunit-v2-shim", "python3 ${CLAUDE_PLUGIN_ROOT}/skills/stryker-xunit-v2-shim/scripts/generate_shim.py tests/<TestProject>/<TestProject>.csproj \\"),
    ("test-health", 'sh "$CLAUDE_PLUGIN_ROOT/hooks/py.sh" "$CLAUDE_PLUGIN_ROOT/hooks/lib/report_pdf.py" .dev-team-reports/test-health-<date>.md'),
    ("ubiquitous-language", 'python3 .claude/skills/ubiquitous-language/scripts/collect_domain_signals.py "$ARGUMENTS"'),
}

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_ALLOWED_TOOLS_RE = re.compile(r"allowed-tools:\s*(.*?)(?=\n[a-zA-Z_-]+:|\Z)", re.DOTALL)
_BASH_GRANT_RE = re.compile(r"Bash\(([^)]*)\)", re.DOTALL)
_FENCE_RE = re.compile(r"```(?:bash|sh)?\n(.*?)```", re.DOTALL)
_INVOCATION_RE = re.compile(r"^(python3?|bash|sh)\s+\S")
#: Splits the allowed-tools value on commas NOT inside a `Bash(...)` group,
#: so `Bash(a, b)` stays one token instead of splitting into `Bash(a` / `b)`.
_TOP_LEVEL_COMMA_RE = re.compile(r",(?![^(]*\))")


def _frontmatter(text: str) -> str:
    match = _FRONTMATTER_RE.match(text)
    return match.group(1) if match else ""


def _bash_grant(frontmatter_text: str):
    """`("unrestricted", None)` | `("scoped", [patterns])` | `("none", None)`."""
    match = _ALLOWED_TOOLS_RE.search(frontmatter_text)
    if not match:
        return ("none", None)
    value = re.sub(r"\s+", " ", match.group(1)).strip()
    tokens = [t.strip() for t in _TOP_LEVEL_COMMA_RE.split(value)]
    if "Bash" in tokens:
        return ("unrestricted", None)
    patterns = []
    for grant in _BASH_GRANT_RE.finditer(value):
        inner = re.sub(r"\s+", " ", grant.group(1)).strip()
        patterns.extend(p.strip() for p in inner.split(",") if p.strip())
    if patterns:
        return ("scoped", patterns)
    return ("none", None)


def _body_invocations(body: str) -> list:
    invocations = []
    for block in _FENCE_RE.finditer(body):
        for line in block.group(1).splitlines():
            stripped = line.strip()
            if _INVOCATION_RE.match(stripped):
                invocations.append(stripped)
    return invocations


def _covered(invocation: str, patterns: list) -> bool:
    """True if `invocation` matches one of `patterns`.

    Patterns are trailing-`*`-wildcarded prefixes (Claude Code's own Bash
    permission-pattern convention, e.g. `python3 scripts/foo.py *`) — a
    prefix match is therefore the correct and sufficient test; nothing here
    needs full glob semantics.
    """
    return any(invocation.startswith(pattern.rstrip("*").strip()) for pattern in patterns)


def _uncovered_invocations_by_skill():
    """`{skill_name: [invocation, ...]}` for every skill with at least one
    fenced shell invocation not covered by its own Bash grant."""
    result = {}
    for skill_path in SKILLS:
        text = skill_path.read_text(encoding="utf-8")
        frontmatter_text = _frontmatter(text)
        body = text[len(frontmatter_text) + 8 :] if frontmatter_text else text
        kind, patterns = _bash_grant(frontmatter_text)
        invocations = _body_invocations(body)
        if not invocations or kind == "unrestricted":
            continue
        if kind == "none":
            result[skill_path.parent.name] = invocations
            continue
        gaps = [inv for inv in invocations if not _covered(inv, patterns)]
        if gaps:
            result[skill_path.parent.name] = gaps
    return result


def test_every_uncovered_invocation_is_a_named_known_gap():
    """The actual gate: any uncovered invocation must be explicitly tracked
    in `KNOWN_UNCOVERED_INVOCATIONS` above, or the guard has found something
    new — the #1652 shape recurring in a skill nobody has triaged yet."""
    found = _uncovered_invocations_by_skill()
    untracked = []
    for skill_name, invocations in found.items():
        for invocation in invocations:
            if (skill_name, invocation) not in KNOWN_UNCOVERED_INVOCATIONS:
                untracked.append((skill_name, invocation))
    assert not untracked, (
        "Found shell invocation(s) in a shipped SKILL.md not covered by that "
        "skill's own allowed-tools Bash grant, and not in "
        "KNOWN_UNCOVERED_INVOCATIONS:\n"
        + "\n".join(f"  {skill!r}: {inv!r}" for skill, inv in untracked)
        + "\n\nEither add a Bash() grant covering it (see agent-audit/SKILL.md "
        "for the #1652 precedent) or add it to KNOWN_UNCOVERED_INVOCATIONS as "
        "a tracked, pre-existing gap."
    )


def test_no_stale_entries_in_the_known_list():
    """Shrink-only, mirroring `test_agent_implemented_by_resolves.py`'s
    `INTENTIONAL_BARE_INVOCATION` reclassification test: an entry that no
    longer reproduces (the skill's grant was widened, or its body no longer
    contains that invocation) must be removed here in the same commit that
    fixed it, not left as permanent, unchecked slack."""
    found = _uncovered_invocations_by_skill()
    still_present = set()
    for skill_name, invocations in found.items():
        for invocation in invocations:
            still_present.add((skill_name, invocation))
    stale = KNOWN_UNCOVERED_INVOCATIONS - still_present
    assert not stale, (
        "KNOWN_UNCOVERED_INVOCATIONS entries no longer reproduce — remove "
        "them:\n" + "\n".join(f"  {skill!r}: {inv!r}" for skill, inv in sorted(stale))
    )


def test_agent_audit_has_no_tracked_gaps():
    """#1652's own regression proof: agent-audit must never appear in the
    tracked list again — its three (in practice, five) documented script
    steps must stay executable under its declared Bash grant."""
    assert not any(skill == "agent-audit" for skill, _ in KNOWN_UNCOVERED_INVOCATIONS)
    found = _uncovered_invocations_by_skill()
    assert "agent-audit" not in found, (
        f"agent-audit/SKILL.md has uncovered invocations again: {found.get('agent-audit')}"
    )
