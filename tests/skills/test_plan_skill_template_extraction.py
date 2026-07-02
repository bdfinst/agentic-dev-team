"""plan/SKILL.md used to embed a ~150-line plan-file template inline instead
of extracting it to references/plan-template.md, the pattern sibling skills
already use (e.g. docker-image-audit/references/report-template.md). This
keeps the always-loaded SKILL.md small and the template available on demand.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_MD = REPO_ROOT / "plugins" / "dev-team" / "skills" / "plan" / "SKILL.md"
TEMPLATE_MD = (
    REPO_ROOT
    / "plugins"
    / "dev-team"
    / "skills"
    / "plan"
    / "references"
    / "plan-template.md"
)

# A handful of markers that must live in the extracted template, not in the
# always-loaded SKILL.md body. Chosen to be template-only strings — distinct
# from legitimate prose elsewhere in SKILL.md that talks *about* these
# sections (e.g. step 4 discusses "## Build Progress" without inlining it).
_TEMPLATE_MARKERS = [
    "#### Step 1.1: <Description>",
    "### Slice 2: <Slice Name>",
    "| <finding> | <why it delivers no signal> |",
]


def test_plan_template_file_exists_with_expected_content() -> None:
    assert TEMPLATE_MD.is_file(), "expected references/plan-template.md to exist"
    text = TEMPLATE_MD.read_text(encoding="utf-8")
    for marker in _TEMPLATE_MARKERS:
        assert marker in text, f"plan-template.md missing expected marker: {marker!r}"


def test_skill_md_references_extracted_template_instead_of_inlining_it() -> None:
    text = SKILL_MD.read_text(encoding="utf-8")
    assert "references/plan-template.md" in text
    for marker in _TEMPLATE_MARKERS:
        assert marker not in text, (
            f"plan/SKILL.md still inlines template content ({marker!r}); "
            "it should live only in references/plan-template.md"
        )


def test_skill_md_shrank_below_previous_size() -> None:
    # Guards against the template creeping back in inline. The file was 300
    # lines / ~17.4KB before extraction; after extraction it should be
    # meaningfully smaller.
    text = SKILL_MD.read_text(encoding="utf-8")
    assert len(text.splitlines()) < 200
