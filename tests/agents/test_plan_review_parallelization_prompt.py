"""#223 — the parallelization-review persona prompt. Follows the plan-review
convention: a `# Plan Review:` H1, NO frontmatter, and a JSON verdict block.
Asserts it covers the three required signals: same-wave file overlap,
disjoint-file behavioral coupling, and residual cycles/mis-layering.

Ported from tests/agents/plan_review_parallelization_prompt_tests.bats
(issue #675: bats -> pytest).
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPT = (
    REPO_ROOT / "plugins" / "dev-team" / "prompts" / "plan-review-parallelization.md"
)
PLAN_SKILL = REPO_ROOT / "plugins" / "dev-team" / "skills" / "plan" / "SKILL.md"


def test_prompt_file_exists() -> None:
    assert PROMPT.is_file()


def test_no_yaml_frontmatter() -> None:
    first_line = PROMPT.read_text(encoding="utf-8").splitlines()[0]
    assert first_line != "---"


def test_uses_plan_review_h1_convention() -> None:
    first_line = PROMPT.read_text(encoding="utf-8").splitlines()[0]
    assert first_line.startswith("# Plan Review:")


def test_declares_reviewer_id_in_json_verdict_block() -> None:
    text = PROMPT.read_text(encoding="utf-8")
    assert '"reviewer": "plan-review-parallelization"' in text


def test_emits_approve_or_needs_revision_verdict() -> None:
    text = PROMPT.read_text(encoding="utf-8")
    assert '"verdict": "approve | needs-revision"' in text


def test_covers_same_wave_file_overlap_collisions() -> None:
    text = PROMPT.read_text(encoding="utf-8")
    assert "collision" in text.lower()
    assert "plan-waves.sh" in text


def test_covers_disjoint_file_behavioral_coupling() -> None:
    text = PROMPT.read_text(encoding="utf-8")
    assert "behavioral coupling" in text.lower()
    assert "disjoint" in text.lower()


def test_covers_residual_cycles_or_mis_layering() -> None:
    text = PROMPT.read_text(encoding="utf-8")
    assert "cycle" in text.lower()


def test_referenced_from_plan_skills_review_persona_set() -> None:
    text = PLAN_SKILL.read_text(encoding="utf-8")
    assert "plan-review-parallelization.md" in text
