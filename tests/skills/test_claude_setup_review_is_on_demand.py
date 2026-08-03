"""`claude-setup-review` is a command, not a `/code-review` lens.

It reviews the **harness** — CLAUDE.md, rules, skill and agent wiring, path
accuracy — not the changeset. Under its old `Scope: always` declaration it
joined the automatic panel on every review, which meant an 18-lens dispatch for
a two-file JavaScript change in a project with no Claude configuration at all:
a lens that reliably had nothing to say about the diff in front of it.

Moving it out is the same principle the rest of #1623 is about — stop paying
for dispatches that review nothing — so these tests pin both halves of the
move: it must stay out of the dispatchable roster, and it must stay reachable
on demand.

The exclusion mechanism itself changed later (#1733's closing-pass follow-up):
this agent declares `Scope: on-demand` directly in its own body, which
`select_lenses.parse_scope`/`applicable_lenses` read and exclude on their own
— it is no longer a member of `review_roster.NON_REVIEW_AGENTS` (that set is
reserved for agents with no per-file review scope at all; this one has one,
it just declares "never per-diff").
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from _repo_root import REPO_ROOT

PLUGIN_ROOT = REPO_ROOT / "plugins" / "dev-team"
AGENT = PLUGIN_ROOT / "agents" / "claude-setup-review.md"
SKILL = PLUGIN_ROOT / "skills" / "claude-setup-review" / "SKILL.md"
SELECT_LENSES = PLUGIN_ROOT / "scripts" / "select_lenses.py"

sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

import review_roster
import select_lenses


def _lenses_for(*files):
    result = subprocess.run(
        [sys.executable, str(SELECT_LENSES), "--files", *files],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


class TestItIsNotACodeReviewLens:
    def test_it_declares_scope_on_demand(self):
        scope = select_lenses.parse_scope(AGENT.read_text(encoding="utf-8"))
        assert scope == select_lenses.SCOPE_ON_DEMAND

    def test_it_is_not_a_non_review_agent(self):
        """It has a real per-file Scope: declaration (`on-demand`), so it
        must not also be exempted via NON_REVIEW_AGENTS — that set is for
        agents with no Scope: concept at all, and double-exempting would
        make the exclusion mechanism ambiguous (#1733 closing-pass finding)."""
        assert "claude-setup-review" not in review_roster.NON_REVIEW_AGENTS

    @pytest.mark.parametrize(
        "files",
        [
            pytest.param(["src/app.js"], id="javascript"),
            pytest.param(["src/api.py"], id="python"),
            pytest.param(["README.md"], id="docs"),
            pytest.param(["CLAUDE.md"], id="the-very-file-it-reviews"),
        ],
    )
    def test_it_is_never_dispatched_by_the_resolver(self, files):
        """Including for a changeset that touches CLAUDE.md itself — harness
        review is a deliberate act, not a side effect of editing config."""
        result = _lenses_for(*files)
        assert "claude-setup-review" not in result["lenses"]

    def test_it_is_not_dropped_silently(self):
        """An agent excluded by accident (a missing `Scope:`) is reported in
        `warnings`. This one is rostered out on purpose, so it must not appear
        there either — otherwise the exclusion reads as a defect."""
        result = _lenses_for("src/app.js")
        warnings = " ".join(result.get("warnings") or [])
        assert "claude-setup-review" not in warnings

    def test_the_agent_records_why(self):
        text = AGENT.read_text(encoding="utf-8")
        assert "Scope: on-demand" in text
        # Line-anchored: the body legitimately *quotes* the old `Scope: always`
        # when explaining the move, and a bare substring check would flag that
        # explanation as the declaration it warns about.
        declarations = [
            line for line in text.splitlines() if line.strip().startswith("Scope: always")
        ]
        assert not declarations, declarations


class TestItIsStillReachable:
    def test_the_skill_exists_and_is_user_invocable(self):
        assert SKILL.is_file(), "removing it from the panel must not remove the capability"
        frontmatter = SKILL.read_text(encoding="utf-8").split("---", 2)[1]
        assert "user-invocable: true" in frontmatter

    def test_the_skill_dispatches_the_agent(self):
        text = SKILL.read_text(encoding="utf-8")
        assert "claude-setup-review` agent" in text
        assert "Agent" in text.split("---", 2)[1], "needs the Agent tool to dispatch"

    def test_the_skill_explains_the_separation(self):
        """Whoever next wonders why this is not in the panel should find the
        answer where they are looking, not in a commit message."""
        text = SKILL.read_text(encoding="utf-8")
        assert "does **not** dispatch this agent" in text
