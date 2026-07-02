"""Slice 13 - /test-modernize, /test-upgrade, test-modernization-review agent,
and the old flow diagram are removed without aliases. Issue #536.

Ported from tests/repo/removed_orchestrators_absence_tests.bats (#673).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_test_modernize_skill_directory_is_gone() -> None:
    assert not (
        REPO_ROOT / "plugins" / "dev-team" / "skills" / "test-modernize"
    ).is_dir()


def test_test_upgrade_skill_directory_is_gone() -> None:
    assert not (REPO_ROOT / "plugins" / "dev-team" / "skills" / "test-upgrade").is_dir()


def test_test_modernization_review_agent_file_is_gone() -> None:
    assert not (
        REPO_ROOT / "plugins" / "dev-team" / "agents" / "test-modernization-review.md"
    ).is_file()


def test_old_test_modernize_flow_svg_diagram_is_gone() -> None:
    assert not (
        REPO_ROOT
        / "plugins"
        / "dev-team"
        / "docs"
        / "diagrams"
        / "test-modernize-flow.svg"
    ).is_file()


def test_no_exclusive_bats_fixture_for_test_modernize_or_test_upgrade_remains() -> None:
    # These files were removed in Slice 13.1.
    removed = [
        "tests/bats/stack-aware-test-modernize.bats",
        "tests/scripts/test_modernization_review_tests.bats",
        "tests/scripts/test_modernize_integration_tests.bats",
        "tests/skills/test_modernize_phase_4_mutation_tests.bats",
        "tests/skills/test_modernize_phase_review_loop_tests.bats",
        "tests/skills/test_upgrade_skill_tests.bats",
        "tests/fixtures/test-modernize-phase-1-3.snapshot.md",
    ]
    for rel in removed:
        assert not (REPO_ROOT / rel).is_file(), f"{rel} should have been removed"


def _grep_files(pattern: str, paths: List[Path]) -> List[str]:
    existing = [str(p) for p in paths if p.exists()]
    if not existing:
        return []
    result = subprocess.run(
        ["grep", "-rEl", pattern, *existing],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        raise AssertionError(result.stderr)
    return [line for line in result.stdout.splitlines() if line]


def test_docs_contain_zero_live_references_outside_changelog_spec_plan() -> None:
    # The test-improve-flow.svg diagram's <desc> element carries one historical
    # mention ("consolidates /test-modernize and /test-upgrade") for
    # provenance - allowed. All other prose docs must be clean.
    paths = [
        REPO_ROOT / "plugins" / "dev-team" / "docs",
        REPO_ROOT / "plugins" / "dev-team" / "knowledge" / "skills-registry.md",
        REPO_ROOT / "plugins" / "dev-team" / "knowledge" / "agent-registry.md",
        REPO_ROOT / "README.md",
    ]
    hits = sorted(
        h
        for h in _grep_files(r"/test-modernize|/test-upgrade", paths)
        if not h.endswith("docs/diagrams/test-improve-flow.svg")
    )
    assert not hits, (
        "Unexpected live references to removed orchestrators:\n" + "\n".join(hits)
    )


def test_worker_skill_md_files_contain_no_live_references() -> None:
    paths = [
        REPO_ROOT
        / "plugins"
        / "dev-team"
        / "skills"
        / "coverage-baseline"
        / "SKILL.md",
        REPO_ROOT / "plugins" / "dev-team" / "skills" / "coverage-delta" / "SKILL.md",
        REPO_ROOT
        / "plugins"
        / "dev-team"
        / "skills"
        / "coverage-delta"
        / "references"
        / "mutation-gate.md",
        REPO_ROOT / "plugins" / "dev-team" / "skills" / "gherkin-derive" / "SKILL.md",
        REPO_ROOT / "plugins" / "dev-team" / "skills" / "gherkin-public" / "SKILL.md",
        REPO_ROOT / "plugins" / "dev-team" / "skills" / "mutation-testing" / "SKILL.md",
        REPO_ROOT
        / "plugins"
        / "dev-team"
        / "skills"
        / "mutation-testing"
        / "references"
        / "workflow-callers.md",
        REPO_ROOT
        / "plugins"
        / "dev-team"
        / "skills"
        / "issues-from-assessment"
        / "SKILL.md",
        REPO_ROOT
        / "plugins"
        / "dev-team"
        / "skills"
        / "test-audit-disable"
        / "SKILL.md",
        REPO_ROOT
        / "plugins"
        / "dev-team"
        / "skills"
        / "quality-targets-converge"
        / "SKILL.md",
    ]
    hits = sorted(_grep_files(r"/test-modernize|/test-upgrade", paths))
    assert not hits, "Unexpected live references in worker SKILLs:\n" + "\n".join(hits)
