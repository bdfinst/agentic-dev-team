"""`/repo-review` is where the repo-wide drift agents run now (#1733, #1735).

`token-efficiency-review` and `ai-provenance-review` were removed from
`/code-review`'s per-diff panel: their findings are properties of absolute
size/accumulated drift or whole-codebase verification debt, not any single
diff's delta — the same "stop paying for dispatches that review nothing"
principle `claude-setup-review`'s move already established (see
`test_claude_setup_review_is_on_demand.py`). `component-architecture-review`
is narrower, not removed: it stays in `/code-review`'s per-diff panel but only
for newly-*added* component files (`Scope: added-only`), and runs
unconditionally, every pass, in `/repo-review`.

These tests pin all three halves of the move: the two newly-excluded agents
must stay out of the dispatchable per-diff roster, `component-architecture-
review`'s per-diff scope must be added-only, and all four agents must remain
reachable via the new `/repo-review` skill.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from _repo_root import REPO_ROOT

PLUGIN_ROOT = REPO_ROOT / "plugins" / "dev-team"
SKILL = PLUGIN_ROOT / "skills" / "repo-review" / "SKILL.md"
SELECT_LENSES = PLUGIN_ROOT / "scripts" / "select_lenses.py"
REVIEW_RUBRIC = PLUGIN_ROOT / "knowledge" / "review-rubric.md"
AGENTS_DIR = PLUGIN_ROOT / "agents"

sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

import review_roster
import select_lenses

REPO_REVIEW_ROSTER = (
    "token-efficiency-review",
    "ai-provenance-review",
    "claude-setup-review",
    "component-architecture-review",
)


def _lenses_for(*files, added=None):
    args = [sys.executable, str(SELECT_LENSES), "--files", *files]
    if added is not None:
        args += ["--added", *added]
    result = subprocess.run(
        args, cwd=str(REPO_ROOT), capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


class TestTokenEfficiencyAndAiProvenanceAreNotCodeReviewLenses:
    @pytest.mark.parametrize("agent", ["token-efficiency-review", "ai-provenance-review"])
    def test_declares_scope_on_demand(self, agent):
        text = (AGENTS_DIR / f"{agent}.md").read_text(encoding="utf-8")
        assert select_lenses.parse_scope(text) == select_lenses.SCOPE_ON_DEMAND

    @pytest.mark.parametrize("agent", ["token-efficiency-review", "ai-provenance-review"])
    def test_is_not_a_non_review_agent(self, agent):
        """It has a real per-file Scope: declaration (`on-demand`), so it
        must not also be exempted via NON_REVIEW_AGENTS — that set is for
        agents with no Scope: concept at all (#1733 closing-pass finding)."""
        assert agent not in review_roster.NON_REVIEW_AGENTS

    @pytest.mark.parametrize(
        "files",
        [
            pytest.param(["src/app.js"], id="javascript"),
            pytest.param(["src/api.py"], id="python"),
            pytest.param(["README.md"], id="docs"),
            pytest.param(["CLAUDE.md"], id="claude-config"),
        ],
    )
    def test_never_dispatched_by_the_resolver(self, files):
        result = _lenses_for(*files)
        assert "token-efficiency-review" not in result["lenses"]
        assert "ai-provenance-review" not in result["lenses"]

    def test_not_dropped_silently(self):
        result = _lenses_for("src/app.js")
        warnings = " ".join(result.get("warnings") or [])
        assert "token-efficiency-review" not in warnings
        assert "ai-provenance-review" not in warnings


class TestComponentArchitectureReviewIsAddedOnlyPerDiff:
    AGENT = PLUGIN_ROOT / "agents" / "component-architecture-review.md"

    def test_agent_declares_added_only_scope(self):
        text = self.AGENT.read_text(encoding="utf-8")
        first_scope_line = next(
            line for line in text.splitlines() if line.strip().startswith("Scope:")
        )
        assert first_scope_line.strip() == "Scope: added-only"

    def test_modified_only_tsx_excluded_when_added_data_supplied(self):
        result = _lenses_for("src/App.tsx", added=[])
        assert "component-architecture-review" not in result["lenses"]

    def test_newly_added_tsx_included_when_added_data_supplied(self):
        result = _lenses_for("src/App.tsx", added=["src/App.tsx"])
        assert "component-architecture-review" in result["lenses"]

    def test_no_added_data_falls_back_to_plain_glob_match(self):
        # /build's inline checkpoints pass no --added — behavior is unchanged.
        result = _lenses_for("src/App.tsx")
        assert "component-architecture-review" in result["lenses"]


class TestRepoReviewSkillDispatchesTheFullRoster:
    def test_the_skill_exists_and_is_user_invocable(self):
        assert SKILL.is_file(), "removing agents from the panel must not remove the capability"
        frontmatter = SKILL.read_text(encoding="utf-8").split("---", 2)[1]
        assert "user-invocable: true" in frontmatter
        assert "Agent" in frontmatter, "needs the Agent tool to dispatch review agents"

    @staticmethod
    def _dispatch_section(text: str) -> str:
        """The step-4 roster-table section only — a deletion from that table
        must fail this guard even if the agent's name survives elsewhere in
        the skill's prose (ai-provenance-review: a bare `f"`{agent}`" in text`
        check would still pass)."""
        start = text.index("### 4. Dispatch the fixed roster")
        end = text.index("\n### 5.", start)
        return text[start:end]

    @pytest.mark.parametrize("agent", REPO_REVIEW_ROSTER)
    def test_the_skill_names_every_roster_agent(self, agent):
        section = self._dispatch_section(SKILL.read_text(encoding="utf-8"))
        assert f"`{agent}`" in section

    def test_the_skill_is_report_only_no_gate_file(self):
        text = SKILL.read_text(encoding="utf-8")
        # The skill legitimately *names* .pr-review-passed once, to explain
        # it never writes one — a bare substring check would flag that
        # sentence.
        assert "no `.pr-review-passed` write" in text
        assert "never gates a commit" in text

    def test_the_skill_explains_the_separation(self):
        """Whoever next wonders why these agents are not in /code-review's
        panel should find the answer where they are looking."""
        text = SKILL.read_text(encoding="utf-8")
        assert "#1733" in text


class TestRubricNeverEscalatesARepoReviewOnlyAgent:
    @staticmethod
    def _category_weights_table(text: str) -> str:
        """Only the markdown table's own rows — not the prose paragraph
        below it, which legitimately *names* these agents to explain why
        they're absent from the table."""
        start = text.index("## Category Weights")
        end = text.index("\n## ", start + 1)
        lines = text[start:end].splitlines()
        return "\n".join(line for line in lines if line.strip().startswith("|"))

    @pytest.mark.parametrize("agent", REPO_REVIEW_ROSTER)
    def test_agent_absent_from_category_weights_table(self, agent):
        """A future edit re-adding one of these agents to review-rubric.md's
        Category Weights table would silently falsify repo-review/SKILL.md
        step 5's claim that the table 'does not apply here' (ai-provenance-
        review) — this pins the coupling so that edit fails loudly instead."""
        section = self._category_weights_table(REVIEW_RUBRIC.read_text(encoding="utf-8"))
        assert agent not in section
