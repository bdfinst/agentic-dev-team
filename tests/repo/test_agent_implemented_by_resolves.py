"""Every `Implemented by:` reference in a shipped agent must resolve for a user.

Agents that declare `Enforcement: script` carry a line like:

    > **Implemented by:** `${CLAUDE_PLUGIN_ROOT}/scripts/claude_setup_review.py`

That reference is the difference between a deterministic check and an LLM
re-deriving it by reading files. `claude-setup-review` named its script as a
bare `scripts/claude_setup_review.py` while the file lived only at this
repository's root — so for anyone who installed the plugin it resolved nowhere,
and the agent silently degraded to a pure-LLM pass. The shipped `/agent-audit`
skill invoked the same bare path, with the same result.

Nothing caught it: the script's own tests ran it from the repo root, where it
does exist, so they passed while the shipped artifact was broken. That is the
shape this file guards — a check that is green about the wrong copy.

Two rules, both mechanical:

1. A shipped agent's `Implemented by:` path must resolve to a file that ships.
2. Shipped skills must not invoke a plugin script by a bare relative path,
   which resolves against the user's cwd rather than the plugin.
"""

from __future__ import annotations

import re

import pytest

from _repo_root import REPO_ROOT

PLUGIN_ROOT = REPO_ROOT / "plugins" / "dev-team"
AGENTS = sorted((PLUGIN_ROOT / "agents").glob("*.md"))
SKILLS = sorted((PLUGIN_ROOT / "skills").glob("*/SKILL.md"))

_IMPLEMENTED_BY = re.compile(r"\*\*Implemented by:\*\*\s*`?([^`\s]+)`?")

#: Agents whose implementing script has not been moved into the plugin yet.
#: Each is the same defect as `claude-setup-review`'s: the shipped agent names a
#: script that only exists at this repository's root, so a user's install cannot
#: run it. Tracked rather than silently tolerated — delete an entry when its
#: script moves under `plugins/dev-team/scripts/`. Empty as of #1636: all four
#: originally-tracked agents (codebase-recon, orchestrator, progress-guardian,
#: token-efficiency-review) now ship their scripts under `plugins/dev-team/scripts/`.
KNOWN_UNSHIPPED: set[str] = set()


def _implemented_by(path):
    match = _IMPLEMENTED_BY.search(path.read_text(encoding="utf-8"))
    return match.group(1) if match else None


@pytest.mark.parametrize("agent", AGENTS, ids=lambda p: p.name)
def test_implemented_by_resolves_inside_the_plugin(agent):
    reference = _implemented_by(agent)
    if reference is None:
        pytest.skip("no Implemented by: line")

    if agent.name in KNOWN_UNSHIPPED:
        pytest.xfail(
            f"known unshipped implementation — {agent.name} names a repo-root script"
        )

    assert reference.startswith("${CLAUDE_PLUGIN_ROOT}/"), (
        f"{agent.name}: `Implemented by: {reference}` is a bare path. It resolves against the user's "
        "cwd, not the plugin, so it points nowhere on an install."
    )
    relative = reference[len("${CLAUDE_PLUGIN_ROOT}/") :]
    assert (PLUGIN_ROOT / relative).is_file(), (
        f"{agent.name}: `Implemented by:` names {relative}, which does not ship"
    )


def test_the_known_unshipped_list_does_not_grow_silently():
    """A new `Enforcement: script` agent must ship its script rather than be
    added here. The list only shrinks — it's empty now, so it must stay that
    way."""
    assert len(KNOWN_UNSHIPPED) == 0, (
        "a new entry means a new shipped agent with an unreachable implementation"
    )


#: Shipped skills that invoke a script by a bare `scripts/…` path, tracked as a
#: DEFECT — same shape as the agent references above, resolving against the
#: user's cwd rather than the plugin. Delete an entry when its skill is fixed
#: (script moved into the plugin and/or invocation qualified with
#: ${CLAUDE_PLUGIN_ROOT}/); the list only shrinks. Empty as of #1637: the two
#: real defects (`project-init`'s install-java-static-analysis.py,
#: `stryker-xunit-v2-shim`'s generate_shim.py) are fixed, and the remaining
#: bare invocations in `agent-audit`, `agent-eval`, `harness-audit` are
#: reclassified per-script into INTENTIONAL_BARE_INVOCATION below — not a
#: defect (see that set's docstring).
KNOWN_BARE_INVOCATION: set[str] = set()

#: (skill, script) pairs whose bare `scripts/<script>` invocation is correct,
#: not a #1637 defect. Exemption is per SCRIPT, not per skill — a skill in
#: this set that later grows an unrelated bare invocation of a script that
#: DOES ship is still caught by the main test below.
#:
#: Every entry's premise — the script does not exist under
#: plugins/dev-team/scripts/, so no ${CLAUDE_PLUGIN_ROOT} qualification could
#: ever resolve it — is checked mechanically, not trusted, by
#: test_intentional_bare_invocation_pairs_do_not_ship_in_the_plugin below.
#: Each script lives only at this repo's root and operates on this
#: marketplace repo's own infrastructure: `check_registry_sync.py` and
#: `validate_agent_contract.py` (a repo-root wrapper delegating to
#: `plugins/marketplace-dev/scripts/validate_agent_contract.py` — that one
#: ships and IS portable, but only reachable from this monorepo checkout,
#: since there is no single ${CLAUDE_PLUGIN_ROOT}-style variable spanning two
#: independently-installed plugins) check `plugins/dev-team/`'s own registry;
#: the `eval_*`/`citation_lint.py` family operates on `evals/` (explicitly not
#: shipped — see repo CLAUDE.md's Repository Structure). `agent-eval`'s
#: strongest evidence is external to this file: the repo-root eval runners
#: and `.github/workflows/agent-eval.yml` materialize `evals/fixtures` from
#: `$PWD` via a symlink before invoking it, only meaningful in this checkout.
#:
#: Each entry's SKILL.md carries a "Monorepo-relative by design (#1637)" note
#: near its invocations (checked below) so a reader doesn't mistake this for
#: an oversight. Add an entry back to KNOWN_BARE_INVOCATION (as a real
#: defect) only if its script starts shipping under plugins/dev-team/scripts/.
#: Keyed on the path *after* `scripts/`, not the bare basename — so a future
#: nested entry (e.g. `scripts/lib/foo.py`) is a distinct pair from
#: `scripts/foo.py` rather than silently colliding with it.
INTENTIONAL_BARE_INVOCATION = {
    ("agent-audit", "validate_agent_contract.py"),
    ("agent-audit", "check_registry_sync.py"),
    ("agent-eval", "eval_cache.py"),
    ("agent-eval", "run_integration_eval.py"),
    ("agent-eval", "eval_variance.py"),
    ("agent-eval", "eval_ablation.py"),
    ("agent-eval", "citation_lint.py"),
    ("harness-audit", "eval_ablation.py"),
}

#: (skill, script) pairs whose invocation is `plugins/dev-team/scripts/<script>`
#: — repo-relative, but NOT the bare `scripts/<script>` form `_BARE_INVOCATION`
#: matches, and NOT `${CLAUDE_PLUGIN_ROOT}`-qualified either, even though the
#: script ships. This is the mirror-image case to INTENTIONAL_BARE_INVOCATION:
#: there, the script doesn't ship, so only a repo-relative path can ever work.
#: Here, the script DOES ship, but the invoking skill needs cwd-relative
#: semantics anyway — `verify_tier.py` audits the agents in the operator's
#: *current working tree*; `${CLAUDE_PLUGIN_ROOT}/scripts/verify_tier.py`
#: would silently audit the installed plugin cache's (possibly stale) copy
#: instead, since verify_tier.py resolves its target via
#: `Path(__file__).resolve().parents[1] / "agents"`.
#:
#: Every entry here is invisible to `_BARE_INVOCATION` and to
#: `test_shipped_script_refs.py`'s `${CLAUDE_PLUGIN_ROOT}/...` resolver, so
#: `test_worktree_relative_invocations_are_declared` below scans for the raw
#: pattern across every shipped skill and fails on any undeclared instance —
#: this is what would have caught quality-targets-converge/SKILL.md naming
#: `plugins/dev-team/scripts/gherkin_effectiveness_rollup.py` this way before
#: #1637 qualified it properly instead (that script had no reason to be
#: cwd-relative — it takes all its inputs as explicit flags).
#: Keyed on the path after `scripts/`, same reasoning as INTENTIONAL_BARE_INVOCATION.
INTENTIONAL_WORKTREE_RELATIVE = {
    ("agent-audit", "verify_tier.py"),
}

# Group 1 is the path after `scripts/`, kept wide (including `/`) so a nested
# invocation like `scripts/lib/foo.py` still matches and is kept as its own
# distinct key (not collapsed to a basename that could collide with an
# unrelated top-level `foo.py`).
_BARE_INVOCATION = re.compile(r"python3?\s+(scripts/[\w./-]+\.py)")
_WORKTREE_RELATIVE_INVOCATION = re.compile(
    r"python3?\s+(plugins/dev-team/scripts/[\w./-]+\.py)"
)


def _invocation_matches(path, pattern, strip_prefix):
    """Return [(lineno, line, subpath), ...] for every match of pattern in
    path, one entry per match — a line with two invocations yields two
    entries, so neither is silently skipped. subpath is the captured path
    with strip_prefix removed (e.g. "scripts/" or "plugins/dev-team/scripts/"),
    kept as the (skill, script) pair key so a nested path stays distinct from
    a top-level file of the same basename."""
    out = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        for match in pattern.finditer(line):
            subpath = match.group(1)[len(strip_prefix) :]
            out.append((lineno, line.strip(), subpath))
    return out


def _bare_invocation_matches(path):
    return _invocation_matches(path, _BARE_INVOCATION, "scripts/")


def _worktree_relative_matches(path):
    return _invocation_matches(
        path, _WORKTREE_RELATIVE_INVOCATION, "plugins/dev-team/scripts/"
    )


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.parent.name)
def test_skills_invoke_plugin_scripts_by_plugin_root(skill):
    """`python3 scripts/foo.py` inside a shipped skill runs against whatever
    happens to be in the user's working directory — usually nothing."""
    skill_name = skill.parent.name
    offenders = [
        f"{lineno}: {line}"
        for lineno, line, subpath in _bare_invocation_matches(skill)
        if (skill_name, subpath) not in INTENTIONAL_BARE_INVOCATION
    ]

    if skill_name in KNOWN_BARE_INVOCATION:
        assert offenders, (
            f"{skill_name} is listed as a known offender but is now clean — remove it from "
            "KNOWN_BARE_INVOCATION"
        )
        pytest.xfail(f"known bare invocation in {skill_name}")

    assert not offenders, (
        "{}: invokes a plugin script by a bare relative path; use "
        "${{CLAUDE_PLUGIN_ROOT}}/scripts/…\n  {}".format(skill_name, "\n  ".join(offenders))
    )


def test_the_known_bare_invocation_list_does_not_grow():
    assert len(KNOWN_BARE_INVOCATION) == 0, (
        "a new shipped skill invokes a script by a bare relative path"
    )


def test_intentional_bare_invocation_pairs_do_not_ship_in_the_plugin():
    """The exemption's premise, checked mechanically rather than trusted:
    each exempted script must genuinely not exist under
    plugins/dev-team/scripts/, so no ${CLAUDE_PLUGIN_ROOT} qualification
    could ever resolve it — the bare form is the only one that can work, and
    only from a monorepo checkout."""
    now_shipped = sorted(
        f"{skill}: {script}"
        for skill, script in INTENTIONAL_BARE_INVOCATION
        if (PLUGIN_ROOT / "scripts" / script).is_file()
    )
    assert not now_shipped, (
        "these scripts now ship in the plugin, so their bare invocation is a real "
        "#1637 defect, not an intentional exemption — qualify with ${CLAUDE_PLUGIN_ROOT}/ "
        "and remove from INTENTIONAL_BARE_INVOCATION:\n  " + "\n  ".join(now_shipped)
    )


@pytest.mark.parametrize("skill, script", sorted(INTENTIONAL_BARE_INVOCATION))
def test_intentional_bare_invocation_pairs_are_still_present(skill, script):
    """Sanity check keyed to the specific PAIR, not just the skill: if
    `agent-eval` drops its `citation_lint.py` call but keeps four others, this
    entry must fail rather than pass on the strength of its unrelated
    siblings — otherwise it silently becomes dead documentation."""
    path = PLUGIN_ROOT / "skills" / skill / "SKILL.md"
    subpaths = {subpath for _lineno, _line, subpath in _bare_invocation_matches(path)}
    assert script in subpaths, (
        f"({skill}, {script}) is in INTENTIONAL_BARE_INVOCATION but that invocation "
        "is gone — remove this entry"
    )


@pytest.mark.parametrize(
    "skill", sorted({skill for skill, _script in INTENTIONAL_BARE_INVOCATION})
)
def test_intentional_bare_invocation_skills_are_documented(skill):
    """The skill must carry the marker explaining why its bare invocation is
    correct, so a reader hitting it doesn't mistake it for an unfixed #1637
    defect."""
    path = PLUGIN_ROOT / "skills" / skill / "SKILL.md"
    text = path.read_text(encoding="utf-8")
    assert "Monorepo-relative by design" in text, (
        f"{skill} is in INTENTIONAL_BARE_INVOCATION but its SKILL.md carries no "
        "explanatory marker"
    )


def test_worktree_relative_invocations_are_declared():
    """`plugins/dev-team/scripts/<name>.py` (repo-relative, matching neither
    the bare-`scripts/` defect shape nor a `${CLAUDE_PLUGIN_ROOT}` reference)
    is invisible to every other sensor in this file and in
    test_shipped_script_refs.py. Scan every shipped skill directly for the
    raw pattern so a new undeclared instance — the shape that let
    quality-targets-converge/SKILL.md ship an unqualified reference to a
    portable script — fails loudly instead of silently."""
    undeclared = []
    for skill in SKILLS:
        skill_name = skill.parent.name
        for lineno, line, subpath in _worktree_relative_matches(skill):
            if (skill_name, subpath) not in INTENTIONAL_WORKTREE_RELATIVE:
                undeclared.append(f"{skill_name}:{lineno}: {line}")

    assert not undeclared, (
        "plugins/dev-team/scripts/… invocation(s) not declared in "
        "INTENTIONAL_WORKTREE_RELATIVE — either qualify with ${CLAUDE_PLUGIN_ROOT}/ "
        "(the common case, if the script has no reason to need the operator's "
        "current working tree) or add the pair with a documented reason:\n  "
        + "\n  ".join(undeclared)
    )


def test_intentional_worktree_relative_pairs_do_ship_in_the_plugin():
    """The mirror-image premise, checked mechanically: unlike
    INTENTIONAL_BARE_INVOCATION, every entry here must genuinely ship under
    plugins/dev-team/scripts/ — the whole justification for going
    cwd-relative instead of ${CLAUDE_PLUGIN_ROOT}-qualified is that the
    working tree, not the installed copy, is what must be resolved."""
    not_shipped = sorted(
        f"{skill}: {script}"
        for skill, script in INTENTIONAL_WORKTREE_RELATIVE
        if not (PLUGIN_ROOT / "scripts" / script).is_file()
    )
    assert not not_shipped, (
        "these scripts do not ship under plugins/dev-team/scripts/, so a "
        "cwd-relative reference to them is a real #1637 defect, not a "
        "deliberate working-tree-vs-cache exemption:\n  " + "\n  ".join(not_shipped)
    )


@pytest.mark.parametrize("skill, script", sorted(INTENTIONAL_WORKTREE_RELATIVE))
def test_intentional_worktree_relative_pairs_are_still_present(skill, script):
    """Sanity check keyed to the specific PAIR, mirroring
    test_intentional_bare_invocation_pairs_are_still_present: if the
    invocation this entry justifies is qualified or removed, the entry must
    fail rather than silently become dead documentation."""
    path = PLUGIN_ROOT / "skills" / skill / "SKILL.md"
    subpaths = {subpath for _lineno, _line, subpath in _worktree_relative_matches(path)}
    assert script in subpaths, (
        f"({skill}, {script}) is in INTENTIONAL_WORKTREE_RELATIVE but that invocation "
        "is gone — remove this entry"
    )
