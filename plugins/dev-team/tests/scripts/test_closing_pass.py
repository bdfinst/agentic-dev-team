"""Unit tests for skills/code-review/scripts/closing_pass.py (#1626).

The headline acceptance criterion: a 1-file fix after an 18-agent panel
produces a closing pass of <= 3 dispatches (the fixer's agent plus a top-up),
not 18 — while still satisfying the pre-commit gate's >= 2 distinct-dispatch
floor by construction, with no hook change.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys

from _repo_root import REPO_ROOT as _REPO_ROOT

_PLUGIN_ROOT = _REPO_ROOT / "plugins" / "dev-team"
_SCRIPTS_DIR = _PLUGIN_ROOT / "skills" / "code-review" / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

import closing_pass

#: A representative 18-agent panel, in the resolver's cheap-first order.
PANEL = [
    "naming-review",
    "structure-review",
    "complexity-review",
    "doc-review",
    "test-review",
    "test-smell-review",
    "js-fp-review",
    "component-architecture-review",
    "a11y-review",
    "token-efficiency-review",
    "claude-setup-review",
    "concurrency-review",
    "performance-review",
    "refactor-opportunity-review",
    "spec-compliance-review",
    "correctness-review",
    "security-review",
    "arch-review",
]


class TestGateFloorByConstruction:
    def test_min_dispatches_matches_the_hook_that_enforces_it(self):
        """Drift guard: the closing pass is only sound because it tops up to
        the gate's own floor. If the hook raises the floor and this constant
        doesn't move, the pass would silently under-compose."""
        source = (_PLUGIN_ROOT / "hooks" / "pre_commit_review.py").read_text(encoding="utf-8")
        match = re.search(r"^_MIN_DISTINCT_DISPATCHES\s*=\s*(\d+)", source, re.M)
        assert match, "could not locate _MIN_DISTINCT_DISPATCHES in pre_commit_review.py"
        assert int(match.group(1)) == closing_pass.MIN_DISTINCT_DISPATCHES

    def test_single_fixer_is_topped_up_to_the_floor(self):
        plan = closing_pass.compose(
            fixed_by_agents=["correctness-review"],
            eligible_roster=PANEL,
            panel_agents=PANEL,
            panel_files=["src/cache.js"],
            fix_delta_files=["src/cache.js"],
        )
        assert len(plan["agents"]) == closing_pass.MIN_DISTINCT_DISPATCHES
        assert "correctness-review" in plan["agents"]
        assert plan["topped_up"] == ["naming-review"]

    def test_two_fixers_need_no_top_up(self):
        plan = closing_pass.compose(
            fixed_by_agents=["correctness-review", "doc-review"],
            eligible_roster=PANEL,
            panel_agents=PANEL,
            panel_files=["src/a.js"],
            fix_delta_files=["src/a.js"],
        )
        assert plan["agents"] == ["correctness-review", "doc-review"]
        assert plan["topped_up"] == []

    def test_top_up_takes_the_cheapest_eligible_lens_first(self):
        # The roster arrives cheap-first from select_lenses.py; a top-up must
        # never reach for an opus lens while a cheaper one is available.
        plan = closing_pass.compose(
            fixed_by_agents=["arch-review"],
            eligible_roster=PANEL,
            panel_agents=PANEL,
            panel_files=["src/a.js"],
            fix_delta_files=["src/a.js"],
        )
        assert plan["topped_up"] == ["naming-review"]
        assert "security-review" not in plan["agents"]

    def test_roster_smaller_than_the_floor_is_reported_not_hidden(self):
        plan = closing_pass.compose(
            fixed_by_agents=["doc-review"],
            eligible_roster=["doc-review"],
            panel_agents=["doc-review"],
            panel_files=["README.md"],
            fix_delta_files=["README.md"],
        )
        assert len(plan["agents"]) == 1
        assert plan["reason"] == "eligible-roster-smaller-than-gate-floor"


class TestCostReduction:
    def test_one_file_fix_after_an_eighteen_agent_panel_dispatches_at_most_three(self):
        """The issue's fixture walkthrough, stated as an assertion."""
        assert len(PANEL) == 18
        plan = closing_pass.compose(
            fixed_by_agents=["correctness-review"],
            eligible_roster=PANEL,
            panel_agents=PANEL,
            panel_files=["src/cache.js", "src/index.js", "README.md"],
            fix_delta_files=["src/cache.js"],
        )
        assert len(plan["agents"]) <= 3
        assert plan["scope"] == "fix-delta"
        assert plan["escape_hatch"] is False

    def test_scope_is_the_fix_delta_not_the_whole_changeset(self):
        plan = closing_pass.compose(
            fixed_by_agents=["doc-review", "naming-review"],
            eligible_roster=PANEL,
            panel_agents=PANEL,
            panel_files=["a.py", "b.py", "c.py"],
            fix_delta_files=["b.py"],
        )
        assert plan["scope"] == "fix-delta"


class TestEscapeHatch:
    def test_fix_delta_outside_the_panel_target_set_falls_back_to_the_full_panel(self):
        plan = closing_pass.compose(
            fixed_by_agents=["correctness-review"],
            eligible_roster=PANEL,
            panel_agents=PANEL,
            panel_files=["src/cache.js"],
            fix_delta_files=["src/cache.js", "src/newly_created.js"],
        )
        assert plan["escape_hatch"] is True
        assert plan["scope"] == "full-changeset"
        assert plan["agents"] == PANEL
        assert plan["reason"] == "fix-delta-touched-files-outside-the-panel-target-set"

    def test_scope_grew_is_a_pure_set_comparison(self):
        assert closing_pass.scope_grew(["a.js"], ["a.js", "b.js"]) is True
        assert closing_pass.scope_grew(["a.js", "b.js"], ["a.js"]) is False
        assert closing_pass.scope_grew(["a.js"], []) is False

    def test_path_normalization_does_not_trigger_a_false_escape(self):
        assert closing_pass.scope_grew(["src/a.js"], ["./src/a.js"]) is False


class TestDeduping:
    def test_duplicate_fixers_collapse(self):
        plan = closing_pass.compose(
            fixed_by_agents=["doc-review", "doc-review", "doc-review"],
            eligible_roster=PANEL,
            panel_agents=PANEL,
            panel_files=["a.md"],
            fix_delta_files=["a.md"],
        )
        assert plan["agents"].count("doc-review") == 1
        assert len(plan["agents"]) == 2

    def test_blank_entries_are_dropped(self):
        plan = closing_pass.compose(
            fixed_by_agents=["", "  ", "doc-review"],
            eligible_roster=PANEL,
            panel_agents=PANEL,
            panel_files=["a.md"],
            fix_delta_files=["a.md"],
        )
        assert "" not in plan["agents"]


class TestCli:
    def test_cli_emits_a_plan(self):
        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPTS_DIR / "closing_pass.py"),
                "--fixed-by",
                "correctness-review",
                "--roster",
                ",".join(PANEL),
                "--panel",
                ",".join(PANEL),
                "--panel-files",
                "src/cache.js,README.md",
                "--fix-delta-files",
                "src/cache.js",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        plan = json.loads(result.stdout)
        assert len(plan["agents"]) == 2
        assert plan["scope"] == "fix-delta"

    def test_cli_accepts_a_select_lenses_json_file_for_the_roster(self, tmp_path):
        roster = tmp_path / "lenses.json"
        roster.write_text(json.dumps({"lenses": PANEL, "warnings": []}), encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPTS_DIR / "closing_pass.py"),
                "--fixed-by",
                "doc-review",
                "--roster",
                f"@{roster}",
                "--panel",
                f"@{roster}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        plan = json.loads(result.stdout)
        assert plan["agents"][0] == "doc-review"
        assert len(plan["agents"]) == 2
