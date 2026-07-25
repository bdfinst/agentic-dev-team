"""Content-guard: test-improve/SKILL.md's write-path instructions target the
new .claude/ and .dev-team-reports/ domains (Slice 5, Step 5.9, plan
opt-in-metrics-and-claude-scoped-artifacts.md).

memory/test-improve/ and plans/test-improve/ references relocate under
.claude/; reports/test-improve/ references relocate under the consolidated
.dev-team-reports/ (not .claude/reports/). refactor-backlog.md is the one
carve-out inside the memory-shaped tree: every reference to it — across all
5 sites (Phase 6's two branches, Phase 8's coverage-reprompt, Phase 9's
interpolation paragraph, and the after-Phase-9 close-out prompt) — resolves
to .dev-team-reports/test-improve/<slug>/refactor-backlog.md specifically,
never .claude/memory/ and never .claude/reports/.
"""

from __future__ import annotations

import re

from skill_doc_helpers import PLUGIN_ROOT

SKILL = (PLUGIN_ROOT / "skills" / "test-improve" / "SKILL.md").read_text(
    encoding="utf-8"
)

_BARE_MEMORY_RE = re.compile(r"(?<!\.claude/)(?<!\.dev-team-)memory/test-improve/")
_BARE_REPORTS_RE = re.compile(r"(?<!\.dev-team-)reports/test-improve/")
_BARE_PLANS_RE = re.compile(r"(?<!\.claude/)plans/test-improve/")


def test_no_bare_memory_test_improve_references_remain():
    assert not _BARE_MEMORY_RE.search(SKILL), (
        "found a bare memory/test-improve/ reference not migrated to "
        ".claude/memory/test-improve/"
    )


def test_no_bare_reports_test_improve_references_remain():
    assert not _BARE_REPORTS_RE.search(SKILL), (
        "found a bare reports/test-improve/ reference not migrated to "
        ".dev-team-reports/test-improve/"
    )


def test_no_bare_plans_test_improve_references_remain():
    assert not _BARE_PLANS_RE.search(SKILL), (
        "found a bare plans/test-improve/ reference not migrated to "
        ".claude/plans/test-improve/"
    )


def test_claude_memory_test_improve_domain_is_referenced():
    assert ".claude/memory/test-improve/" in SKILL


def test_dev_team_reports_test_improve_domain_is_referenced():
    assert ".dev-team-reports/test-improve/" in SKILL


def test_claude_plans_test_improve_domain_is_referenced():
    assert ".claude/plans/test-improve/" in SKILL


def test_refactor_backlog_never_under_claude_memory():
    assert ".claude/memory/test-improve/<slug>/refactor-backlog.md" not in SKILL


def test_refactor_backlog_never_under_claude_reports():
    assert ".claude/reports/test-improve/<slug>/refactor-backlog.md" not in SKILL
    assert ".claude/reports" not in SKILL


def test_every_refactor_backlog_reference_resolves_to_dev_team_reports_path():
    occurrences = [m.start() for m in re.finditer(r"refactor-backlog\.md", SKILL)]
    assert len(occurrences) >= 5, (
        f"expected at least 5 refactor-backlog.md references, found {len(occurrences)}"
    )
    for idx in occurrences:
        window = SKILL[max(0, idx - 80) : idx + len("refactor-backlog.md")]
        assert ".dev-team-reports/test-improve/<slug>/refactor-backlog.md" in window, (
            f"refactor-backlog.md reference at offset {idx} does not resolve to "
            "the .dev-team-reports/test-improve/<slug>/ path"
        )
