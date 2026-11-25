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
    "tree",
    [
        "plugins/dev-team/templates/eslint/payload/",
        "plugins/dev-team/templates/eslint/dev/",
    ],
)
def test_amendment_names_the_scaffolded_payload_and_the_contributor_harness(tree):
    assert tree in _amendment_body(), f"the amendment must name {tree}"
    assert (REPO_ROOT / tree).is_dir(), f"{tree} is named but does not exist"


def test_adr_0015_links_to_the_amendment():
    link = f"0014-python-for-cross-os-scripts.md#{ANCHOR}"
    assert link in ADR_0015.read_text(encoding="utf-8"), (
        f"ADR 0015 must link to the ADR 0014 amendment anchor ({link})"
    )


def test_adr_0014_status_line_records_the_amendment():
    text = ADR_0014.read_text(encoding="utf-8")
    status = text.split("\n## Status\n", 1)[1].split("\n## ", 1)[0]
    assert "Amended" in status, "ADR 0014's Status section must record the amendment"
    assert f"(#{ANCHOR})" in status, (
        "the Status line must link to the amendment heading"
    )


def test_claude_md_script_authoring_points_to_the_amendment():
    text = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    section = text.split("### Script authoring", 1)[1].split("\n### ", 1)[0]
    assert f"0014-python-for-cross-os-scripts.md#{ANCHOR}" in section, (
        "CLAUDE.md 'Script authoring' must link to the ADR 0014 amendment"
    )
