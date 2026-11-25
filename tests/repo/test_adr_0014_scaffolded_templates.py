"""ADR 0014 must exempt scaffolded templates from the Python-only rule.

The dev-team ESLint config is JavaScript that `/setup` writes into a user's
project. Without an explicit amendment, a reader applying ADR 0014 literally
would flag it as a violation. ADR 0015 must link to the amendment so a reader
of the later ADR finds it.
"""

from __future__ import annotations

import re

from _repo_root import REPO_ROOT

ADR_0014 = REPO_ROOT / "docs" / "adr" / "0014-python-for-cross-os-scripts.md"
ADR_0015 = REPO_ROOT / "docs" / "adr" / "0015-bash-removal-complete.md"
HEADING = "## Amendment: scaffolded templates"


def _amendment_body() -> str:
    text = ADR_0014.read_text(encoding="utf-8")
    assert text.count(f"\n{HEADING}\n") == 1, (
        f"{ADR_0014} must contain the heading {HEADING!r} exactly once"
    )
    after = text.split(f"\n{HEADING}\n", 1)[1]
    return re.split(r"\n## ", after, maxsplit=1)[0]


def test_amendment_names_scaffolded_templates_as_outside_the_python_only_rule() -> None:
    body = _amendment_body()
    assert "JavaScript" in body and "TypeScript" in body
    assert "outside" in body and "Python-only" in body
    assert "user's project" in body


def test_amendment_keeps_shipped_logic_python_and_adds_no_node_requirement() -> None:
    body = _amendment_body()
    assert "stdlib" in body and "Python" in body
    assert "no Node requirement" in body


def test_adr_0015_links_to_the_amendment() -> None:
    text = ADR_0015.read_text(encoding="utf-8")
    assert (
        "0014-python-for-cross-os-scripts.md#amendment-scaffolded-templates" in text
    ), "ADR 0015 must link to the ADR 0014 amendment anchor"
