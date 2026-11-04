"""/plan must make authors write a `# Still passes if:` falsifier under every
scenario title: the template shows it, and SKILL.md states the rule and feeds
the `plan_falsifiers.py` output to the Acceptance Test Critic.
"""

from __future__ import annotations

import re
import sys

from _repo_root import REPO_ROOT

PLUGIN_ROOT = REPO_ROOT / "plugins" / "dev-team"
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

from plan_falsifiers import (  # type: ignore[import-not-found]
    FALSIFIER_PREFIX,
)

PLAN_SKILL_DIR = PLUGIN_ROOT / "skills" / "plan"
SKILL_MD = PLAN_SKILL_DIR / "SKILL.md"
TEMPLATE_MD = PLAN_SKILL_DIR / "references" / "plan-template.md"

FALSIFIER_COMMENT_RE = re.compile(rf"^\s*#\s*{re.escape(FALSIFIER_PREFIX)}\s*\S")
GHERKIN_FENCE_RE = re.compile(r"```gherkin\n(.*?)```", re.DOTALL)

TEMPLATE_RULE_SENTENCE = (
    f"Every scenario names, in a `# {FALSIFIER_PREFIX}` comment on the line after its title, "
    "one plausible change to the system under which it still passes: "
    "the thing the scenario does not check."
)

SKILL_RULE_SENTENCE = (
    f"Every scenario also carries, as the first line under its title, one `# {FALSIFIER_PREFIX} <change>` "
    "comment naming a mutation the scenario does not detect \u2014 never the negation of its `Then` clause."
)

STEP_5B_SENTENCE = (
    "Also pass the Acceptance Test Critic the output of "
    '`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plan_falsifiers.py" <plan-file>`, '
    "run on the current plan file on each review pass "
    "(its `missing` array is the deterministic input for the Falsifier check)."
)


def _gherkin_fence_lines(text: str) -> list[str]:
    match = GHERKIN_FENCE_RE.search(text)
    assert match, "no gherkin fence found"
    return match.group(1).splitlines()


def test_template_falsifier_line_follows_each_example_scenario_title():
    lines = _gherkin_fence_lines(TEMPLATE_MD.read_text(encoding="utf-8"))
    title_indexes = [
        i for i, line in enumerate(lines) if line.strip().startswith("Scenario:")
    ]

    assert len(title_indexes) == 2
    for index in title_indexes:
        assert FALSIFIER_COMMENT_RE.match(lines[index + 1]), lines[index : index + 2]


def test_template_states_the_falsifier_rule_after_the_fence():
    text = TEMPLATE_MD.read_text(encoding="utf-8")
    after_fence = text[GHERKIN_FENCE_RE.search(text).end() :]

    assert TEMPLATE_RULE_SENTENCE in after_fence


def _section_between(text: str, start_heading: str, end_heading: str) -> str:
    start = text.index(start_heading)
    return text[start : text.index(end_heading, start)]


def _paragraphs(section: str) -> list[str]:
    return [p for p in section.split("\n\n") if p.strip()]


def test_plan_step2_scenario_independence_paragraph_states_the_falsifier_rule():
    step2 = _section_between(SKILL_MD.read_text(encoding="utf-8"), "### 2.", "### 3.")
    [paragraph] = [
        p
        for p in _paragraphs(step2)
        if p.startswith("Keep scenarios implementation-independent")
    ]

    assert SKILL_RULE_SENTENCE in paragraph


def test_plan_step5b_passes_falsifier_script_output_to_the_acceptance_test_critic():
    step5b = _section_between(
        SKILL_MD.read_text(encoding="utf-8"), "#### 5b.", "### 6."
    )

    [paragraph] = [
        p
        for p in _paragraphs(step5b)
        if p.startswith("Pass each reviewer the full plan content.")
    ]
    assert STEP_5B_SENTENCE in paragraph
