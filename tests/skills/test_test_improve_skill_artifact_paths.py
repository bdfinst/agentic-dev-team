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

CONVERGE_SKILL = (
    PLUGIN_ROOT / "skills" / "quality-targets-converge" / "SKILL.md"
).read_text(encoding="utf-8")

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


# --- Slice 4 Step 4.7 (plans/test-improve-baseline-persistence.md): pin that
# --- the unrelated .claude/memory/ process files this plan never touches
# --- didn't silently move to .dev-team-reports/ alongside the ones that did.

_UNRELATED_MEMORY_PATTERNS_TEST_IMPROVE = [
    r"phase-\d+\.md",
    r"phase-5-review\.json",
    r"phase-7-review\.json",
    r"waivers\.json",
    r"phase-8\.md",
    r"gherkin\.md",
]

_UNRELATED_MEMORY_PATTERNS_CONVERGE = [
    r"converge-<iteration>\.json",
    r"waivers\.json",
    r"gherkin\.md",
    r"gherkin-bindings\.json",
]


def _assert_never_paired_with_dev_team_reports(text: str, pattern: str, window: int = 60):
    for m in re.finditer(pattern, text):
        before = text[max(0, m.start() - window) : m.start()]
        assert ".dev-team-reports/" not in before, (
            f"{m.group()!r} at offset {m.start()} is paired with "
            ".dev-team-reports/ — this file belongs under .claude/memory/, "
            "unaffected by this plan's tracked-data migration"
        )


def test_test_improve_unrelated_memory_files_never_paired_with_dev_team_reports():
    for pattern in _UNRELATED_MEMORY_PATTERNS_TEST_IMPROVE:
        assert re.search(pattern, SKILL), f"expected to find {pattern!r} in test-improve/SKILL.md"
        _assert_never_paired_with_dev_team_reports(SKILL, pattern)


def test_quality_targets_converge_unrelated_memory_files_never_paired_with_dev_team_reports():
    for pattern in _UNRELATED_MEMORY_PATTERNS_CONVERGE:
        assert re.search(pattern, CONVERGE_SKILL), (
            f"expected to find {pattern!r} in quality-targets-converge/SKILL.md"
        )
        _assert_never_paired_with_dev_team_reports(CONVERGE_SKILL, pattern)
