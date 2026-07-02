"""#222 — the /plan skill must render the parallelization structure:
per-slice Depends-on, a ## Parallelization section (Mermaid DAG + wave
table), and a wave-grouped Build Progress. Documentation gate for slice 1's
rendering.

Ported from tests/commands/plan_parallelization_doc_tests.bats (issue #675:
bats -> pytest).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL = REPO_ROOT / "plugins" / "dev-team" / "skills" / "plan" / "SKILL.md"


@pytest.fixture(scope="module")
def text() -> str:
    return SKILL.read_text(encoding="utf-8")


def test_plan_skill_exists() -> None:
    assert SKILL.is_file()


def test_slice_template_declares_slice_level_depends_on_field(text: str) -> None:
    assert "**Depends-on:**" in text


def test_slice_template_declares_slice_level_files_surface(text: str) -> None:
    assert "**Files:**" in text


def test_plan_renders_parallelization_section(text: str) -> None:
    assert re.search(r"^## Parallelization", text, re.MULTILINE)


def test_parallelization_section_references_wave_computer(text: str) -> None:
    assert "plan_waves.py" in text


def test_parallelization_section_contains_mermaid_dag_and_wave_table(
    text: str,
) -> None:
    assert "mermaid" in text
    assert "| Wave | Slices" in text


def test_build_progress_groups_slices_by_wave(text: str) -> None:
    assert "grouped by wave" in text
    assert "#### Wave 1" in text


def test_plan_flow_tells_author_to_fix_same_wave_collisions_before_gate(
    text: str,
) -> None:
    assert "collision" in text.lower()
