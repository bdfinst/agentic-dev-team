"""ADR 0014 must exempt scaffolded templates from the Python-only rule.

The dev-team ESLint config is JavaScript that `/setup` writes into a user's
project. Without an explicit amendment, a reader applying ADR 0014 literally
would flag it as a violation. ADR 0015 must link to the amendment so a reader
of the later ADR finds it.
"""

from __future__ import annotations

import re

import pytest

from _repo_root import REPO_ROOT

ADR_0014 = REPO_ROOT / "docs" / "adr" / "0014-python-for-cross-os-scripts.md"
ADR_0015 = REPO_ROOT / "docs" / "adr" / "0015-bash-removal-complete.md"
HEADING = "## Amendment: scaffolded templates"
# GitHub's heading anchor: lowercase, punctuation dropped, spaces to hyphens.
ANCHOR = re.sub(r"[^a-z0-9 -]", "", HEADING.removeprefix("## ").lower()).replace(
    " ", "-"
)


def _amendment_body() -> str:
    text = ADR_0014.read_text(encoding="utf-8")
    assert text.count(f"\n{HEADING}\n") == 1, (
        f"{ADR_0014} must contain the heading {HEADING!r} exactly once"
    )
    after = text.split(f"\n{HEADING}\n", 1)[1]
    return re.split(r"\n## ", after, maxsplit=1)[0]


@pytest.mark.parametrize(
    ("phrase", "why"),
    [
        ("JavaScript", "name the language of the exempt templates"),
        ("TypeScript", "name the second exempt language"),
        ("outside", "say the templates are outside the rule"),
        ("Python-only", "name the rule the templates are outside of"),
        ("user's project", "say where the templates are written"),
    ],
)
def test_amendment_exempts_scaffolded_templates(phrase, why):
    assert phrase in _amendment_body(), f"the amendment must {why}: {phrase!r}"


@pytest.mark.parametrize(
    ("phrase", "why"),
    [
        ("stdlib", "keep the plugin's own scripts stdlib-only"),
        ("Python", "keep the plugin's own scripts in Python"),
        ("no Node requirement", "say the plugin itself needs no Node"),
    ],
)
def test_amendment_keeps_shipped_logic_python_and_adds_no_node_requirement(phrase, why):
    assert phrase in _amendment_body(), f"the amendment must {why}: {phrase!r}"


def test_adr_0015_links_to_the_amendment():
    link = f"0014-python-for-cross-os-scripts.md#{ANCHOR}"
    assert link in ADR_0015.read_text(encoding="utf-8"), (
        f"ADR 0015 must link to the ADR 0014 amendment anchor ({link})"
    )
