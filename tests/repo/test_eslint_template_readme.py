"""The ESLint template README must say how wiring order and rule overlap behave.

A flat config replaces a rule's options instead of merging them, so a project
that also sets `no-restricted-syntax` (the `/project-init` JavaScript template
does) silently drops the dev-team selectors unless told how to keep both.
"""

from __future__ import annotations

from _repo_root import REPO_ROOT

README = REPO_ROOT / "plugins" / "dev-team" / "templates" / "eslint" / "README.md"
WIRE = "export default [...devteam, ...yourConfig];"


def test_readme_shows_the_dev_team_config_first():
    assert WIRE in README.read_text(encoding="utf-8"), f"README must show {WIRE!r}"


def test_readme_warns_that_no_restricted_syntax_options_replace_not_merge():
    text = README.read_text(encoding="utf-8")
    assert "do not merge" in text, "README must say rule options do not merge"
    assert "no-restricted-syntax" in text.split("do not merge", 1)[1][:200], (
        "README must name no-restricted-syntax as the overlapping rule"
    )
