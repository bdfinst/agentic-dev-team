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


#: Shipped skills that still invoke a script by a bare `scripts/…` path. Same
#: defect as the agent references above — the path resolves against the user's
#: working directory, not the plugin. Most name this repository's own dev
#: tooling (`verify_tier.py`, `check_registry_sync.py`, the `eval_*` family),
#: which is why it went unnoticed: those skills are only ever run from this
#: checkout, where the relative path happens to work.
#:
#: Tracked rather than fixed in one sweep — each needs its script either moved
#: into the plugin or its invocation qualified, and that is a per-skill call.
#: Delete an entry when its skill is fixed; the list only shrinks.
KNOWN_BARE_INVOCATION = {
    "agent-audit",
    "agent-eval",
    "harness-audit",
    "project-init",
    "stryker-xunit-v2-shim",
}


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.parent.name)
def test_skills_invoke_plugin_scripts_by_plugin_root(skill):
    """`python3 scripts/foo.py` inside a shipped skill runs against whatever
    happens to be in the user's working directory — usually nothing."""
    offenders = [
        line.strip()
        for line in skill.read_text(encoding="utf-8").splitlines()
        if re.search(r"python3?\s+scripts/[\w./-]+\.py", line)
    ]
    if skill.parent.name in KNOWN_BARE_INVOCATION:
        assert offenders, (
            f"{skill.parent.name} is listed as a known offender but is now clean — remove it from "
            "KNOWN_BARE_INVOCATION"
        )
        pytest.xfail(f"known bare invocation in {skill.parent.name}")

    assert not offenders, (
        "{}: invokes a plugin script by a bare relative path; use "
        "${{CLAUDE_PLUGIN_ROOT}}/scripts/…\n  {}".format(
            skill.parent.name, "\n  ".join(offenders)
        )
    )


def test_the_known_bare_invocation_list_does_not_grow():
    assert len(KNOWN_BARE_INVOCATION) <= 5, (
        "a new shipped skill invokes a script by a bare relative path"
    )
