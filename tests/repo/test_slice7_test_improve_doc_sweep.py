"""Content-guard: the remaining /test-improve doc references identified by
Slice 7's live sweep resolve to their .claude/-nested or .dev-team-reports/
equivalents (plan opt-in-metrics-and-claude-scoped-artifacts.md, Slice 7,
Step 7.2).

Covers docs/test-improve.md, docs/team-structure.md, docs/agent-architecture.md,
and skills/quality-targets-converge/SKILL.md — the files the Gherkin names
explicitly (skills/test-improve/templates/executive-summary.md has its own
dedicated test module, tests/skills/test_improve_executive_summary_template.py).

refactor-backlog.md is the carve-out: it always resolves to
.dev-team-reports/<workflow-or-test-improve>/<slug>/refactor-backlog.md, never
the generic .claude/memory/ rule that applies to every other file in the same
directory tree.
"""

from __future__ import annotations

import re

from _repo_root import REPO_ROOT

PLUGIN = REPO_ROOT / "plugins" / "dev-team"

TEST_IMPROVE_DOC = (PLUGIN / "docs" / "test-improve.md").read_text(encoding="utf-8")
TEAM_STRUCTURE = (PLUGIN / "docs" / "team-structure.md").read_text(encoding="utf-8")
AGENT_ARCH = (PLUGIN / "docs" / "agent-architecture.md").read_text(encoding="utf-8")
QTC_SKILL = (
    PLUGIN / "skills" / "quality-targets-converge" / "SKILL.md"
).read_text(encoding="utf-8")

_BARE_MEMORY_RE = re.compile(r"(?<!\.claude/)memory/")
_BARE_METRICS_RE = re.compile(r"(?<!\.claude/)metrics/")
_BARE_PLANS_RE = re.compile(r"(?<!\.claude/)plans/")
_BARE_REPORTS_TEST_IMPROVE_RE = re.compile(r"(?<!\.dev-team-)reports/test-improve/")


def test_test_improve_doc_has_no_bare_memory_test_improve_reference() -> None:
    assert not re.search(r"(?<!\.claude/)memory/test-improve/", TEST_IMPROVE_DOC)


def test_test_improve_doc_has_no_bare_plans_test_improve_reference() -> None:
    assert not re.search(r"(?<!\.claude/)plans/test-improve/", TEST_IMPROVE_DOC)


def test_test_improve_doc_has_no_bare_reports_test_improve_reference() -> None:
    assert not _BARE_REPORTS_TEST_IMPROVE_RE.search(TEST_IMPROVE_DOC)


def test_test_improve_doc_names_the_relocated_domains() -> None:
    assert ".claude/memory/test-improve/" in TEST_IMPROVE_DOC
    assert ".claude/plans/test-improve/" in TEST_IMPROVE_DOC
    assert ".dev-team-reports/test-improve/" in TEST_IMPROVE_DOC


def test_team_structure_doc_has_no_bare_memory_test_improve_reference() -> None:
    assert not re.search(r"(?<!\.claude/)memory/test-improve/", TEAM_STRUCTURE)
    assert ".claude/memory/test-improve/" in TEAM_STRUCTURE


def test_agent_architecture_doc_has_no_bare_memory_test_improve_reference() -> None:
    assert not re.search(r"(?<!\.claude/)memory/test-improve/", AGENT_ARCH)
    assert ".claude/memory/test-improve/" in AGENT_ARCH


def test_agent_architecture_doc_has_no_other_bare_memory_or_metrics_reference() -> None:
    assert not _BARE_MEMORY_RE.search(AGENT_ARCH)
    assert not _BARE_METRICS_RE.search(AGENT_ARCH)


def test_quality_targets_converge_has_no_bare_memory_metrics_plans_reference() -> None:
    assert not _BARE_MEMORY_RE.search(QTC_SKILL)
    assert not _BARE_METRICS_RE.search(QTC_SKILL)
    assert not _BARE_PLANS_RE.search(QTC_SKILL)


def test_quality_targets_converge_reports_test_improve_relocated() -> None:
    assert not _BARE_REPORTS_TEST_IMPROVE_RE.search(QTC_SKILL)
    assert ".dev-team-reports/test-improve/" in QTC_SKILL


def test_quality_targets_converge_refactor_backlog_sites_target_dev_team_reports() -> (
    None
):
    occurrences = [m.start() for m in re.finditer(r"refactor-backlog\.md", QTC_SKILL)]
    assert len(occurrences) >= 2, (
        f"expected at least 2 refactor-backlog.md references, found {len(occurrences)}"
    )
    for idx in occurrences:
        window = QTC_SKILL[max(0, idx - 60) : idx + len("refactor-backlog.md")]
        assert ".dev-team-reports/<workflow>/<slug>/refactor-backlog.md" in window, (
            f"refactor-backlog.md reference at offset {idx} does not resolve to "
            "the .dev-team-reports/<workflow>/<slug>/ path"
        )
