"""#223 / #1329 — the parallelization-review persona is a registered agent
(`agents/plan-review-parallelization.md`), not a frontmatter-less prompt
template (issue #1329 converted all five plan-review personas to agents).
Asserts it covers the three required signals: same-wave file overlap,
disjoint-file behavioral coupling, and residual cycles/mis-layering.

Ported from tests/agents/plan_review_parallelization_prompt_tests.bats
(issue #675: bats -> pytest); rewritten for #1329.
"""

from __future__ import annotations

from _repo_root import REPO_ROOT

AGENT = REPO_ROOT / "plugins" / "dev-team" / "agents" / "plan-review-parallelization.md"
PLAN_SKILL = REPO_ROOT / "plugins" / "dev-team" / "skills" / "plan" / "SKILL.md"


def test_agent_file_exists() -> None:
    assert AGENT.is_file()


def test_has_yaml_frontmatter_with_native_model_effort() -> None:
    text = AGENT.read_text(encoding="utf-8")
    assert text.splitlines()[0] == "---"
    assert "name: plan-review-parallelization" in text
    assert "model:" in text
    assert "effort:" in text


def test_uses_plan_review_h1_convention() -> None:
    text = AGENT.read_text(encoding="utf-8")
    body = text.split("---", 2)[2]
    first_body_line = next(line for line in body.splitlines() if line.strip())
    assert first_body_line.startswith("# Plan Review:")


def test_declares_reviewer_id_in_json_verdict_block() -> None:
    text = AGENT.read_text(encoding="utf-8")
    assert '"reviewer": "plan-review-parallelization"' in text


def test_emits_approve_or_needs_revision_verdict() -> None:
    text = AGENT.read_text(encoding="utf-8")
    assert '"verdict": "approve | needs-revision"' in text


def test_covers_same_wave_file_overlap_collisions() -> None:
    text = AGENT.read_text(encoding="utf-8")
    assert "collision" in text.lower()
    assert "plan_waves.py" in text
    assert "plan-waves.sh" not in text


def test_covers_disjoint_file_behavioral_coupling() -> None:
    text = AGENT.read_text(encoding="utf-8")
    assert "behavioral coupling" in text.lower()
    assert "disjoint" in text.lower()


def test_covers_residual_cycles_or_mis_layering() -> None:
    text = AGENT.read_text(encoding="utf-8")
    assert "cycle" in text.lower()


def test_declares_context_needs() -> None:
    text = AGENT.read_text(encoding="utf-8")
    assert "Context needs:" in text


def test_referenced_from_plan_skills_review_persona_set() -> None:
    text = PLAN_SKILL.read_text(encoding="utf-8")
    assert "plan-review-parallelization" in text
