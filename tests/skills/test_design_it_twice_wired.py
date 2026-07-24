"""The design-it-twice skill's advertised Architect trigger is actually wired.

design-it-twice/SKILL.md promises: "Also use when the Architect agent is
designing a new module boundary or public interface." An agent's `## Skills`
section is the wiring for such a promise, so architect.md must list
design-it-twice or the trigger is dead (issue #833).

Two contracts, symmetric so the pair fails if either half drifts:

1. The skill still promises the Architect trigger.
2. architect.md's `## Skills` section references design-it-twice.
"""

from __future__ import annotations

from _repo_root import REPO_ROOT

PLUGIN = REPO_ROOT / "plugins" / "dev-team"
DESIGN_IT_TWICE = (
    PLUGIN / "skills" / "design-it-twice" / "SKILL.md"
).read_text(encoding="utf-8")
ARCHITECT = (PLUGIN / "agents" / "architect.md").read_text(encoding="utf-8")


def test_design_it_twice_promises_the_architect_trigger():
    # "Architect" and "agent" straddle a folded-scalar line wrap in the
    # frontmatter, so match the intact tail of the promise on one line.
    assert "designing a new module boundary or public interface" in DESIGN_IT_TWICE


def test_architect_skills_section_wires_design_it_twice():
    assert "../skills/design-it-twice/SKILL.md" in ARCHITECT
