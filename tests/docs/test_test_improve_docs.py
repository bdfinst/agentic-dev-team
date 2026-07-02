"""Docs + diagram + registry checks for /test-improve. Issue #536, Slice 12.

Ported from tests/docs/test_improve_docs_tests.bats (issue #675:
bats -> pytest).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = REPO_ROOT / "plugins" / "dev-team" / "docs"
KNOWLEDGE_DIR = REPO_ROOT / "plugins" / "dev-team" / "knowledge"
SVG = DOCS_DIR / "diagrams" / "test-improve-flow.svg"


def test_test_improve_flow_svg_exists_and_is_valid_svg() -> None:
    assert SVG.is_file()
    text = SVG.read_text(encoding="utf-8")
    assert re.search(r"<svg ", text)
    assert re.search(r"</svg>", text)


def test_test_improve_flow_svg_carries_text_labels_for_all_7_phases() -> None:
    text = SVG.read_text(encoding="utf-8")
    for phase in (
        "Phase 0",
        "Phase 1",
        "Phase 2",
        "Phase 2b",
        "Phase 3",
        "Phase 4",
        "Phase 4b",
        "Phase 5",
        "Phase 6",
        "Phase 7",
    ):
        assert phase in text, f"missing: {phase}"


def test_workflows_doc_has_test_improve_section_header() -> None:
    text = (DOCS_DIR / "workflows.md").read_text(encoding="utf-8")
    assert re.search(r"^## `?/test-improve", text, re.MULTILINE)


def test_workflows_doc_multi_phase_pipelines_sentence_names_test_improve_and_ship() -> (
    None
):
    text = (DOCS_DIR / "workflows.md").read_text(encoding="utf-8")
    assert re.search(
        r"(/test-improve.*(alongside|and).*/ship)|(/ship.*(alongside|and).*/test-improve)|"
        r"(/test-improve.*/ship)|(/ship.*/test-improve)",
        text,
    )


def test_agent_architecture_doc_embeds_test_improve_flow_svg() -> None:
    text = (DOCS_DIR / "agent-architecture.md").read_text(encoding="utf-8")
    assert re.search(r"diagrams/test-improve-flow\.svg", text)


def test_skills_doc_has_test_improve_row() -> None:
    text = (DOCS_DIR / "skills.md").read_text(encoding="utf-8")
    assert "/test-improve" in text


def test_test_evaluation_doc_references_test_improve() -> None:
    text = (DOCS_DIR / "test-evaluation.md").read_text(encoding="utf-8")
    assert "/test-improve" in text


def test_team_structure_doc_references_test_improve() -> None:
    text = (DOCS_DIR / "team-structure.md").read_text(encoding="utf-8")
    assert "/test-improve" in text


def test_readme_references_test_improve() -> None:
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "/test-improve" in text


def test_skills_registry_has_test_improve_row() -> None:
    text = (KNOWLEDGE_DIR / "skills-registry.md").read_text(encoding="utf-8")
    assert re.search(r"\|\s*`/test-improve`", text)


def test_agent_registry_has_test_improve_row() -> None:
    text = (KNOWLEDGE_DIR / "agent-registry.md").read_text(encoding="utf-8")
    assert re.search(r"Test\s+Improve|test-improve", text, re.IGNORECASE)
