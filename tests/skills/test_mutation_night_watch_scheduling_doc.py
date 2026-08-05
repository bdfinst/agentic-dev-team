"""Regression guard for issue #1877: scheduling.md's three per-OS recipes
must point the SCRIPT PATH at the installed plugin's root (`<plugin-root>`),
never at the operator's own repository root (`<repo>`).

The three recipes (launchd, cron, schtasks) each invoke
`mutation_nightwatch.py`. Before this fix, all three built the script path
as `<repo>/plugins/dev-team/skills/mutation-testing/scripts/...` — a path
that only resolves inside THIS monorepo, where the plugin is developed. A
downstream install has the script under the Claude Code plugin cache
instead (e.g. `~/.claude/plugins/cache/bfinster/dev-team/<version>/skills/
mutation-testing/scripts/mutation_nightwatch.py`), so every recipe as
originally written was broken for actual plugin users.

`--repo-root <repo>` and the `<repo>/reports/mutation-nightwatch/...` log
paths are intentionally left alone — those genuinely name the operator's
own project repo being measured, not the plugin's install location — so
this guard checks the SCRIPT PATH segment specifically, not every
occurrence of `<repo>`.
"""

from __future__ import annotations

import re

from skill_doc_helpers import PLUGIN_ROOT

SCHEDULING = PLUGIN_ROOT / "skills" / "mutation-night-watch" / "references" / "scheduling.md"

#: The monorepo-shaped path segment that must never immediately follow a
#: `<repo>` token — that combination only resolves inside this monorepo's
#: own checkout, never in an installed plugin.
_MONOREPO_SHAPED_SCRIPT_PATH_RE = re.compile(
    r"<repo>[/\\]plugins[/\\]dev-team[/\\]skills[/\\]mutation-testing[/\\]scripts[/\\]mutation_nightwatch\.py"
)


def _text() -> str:
    return SCHEDULING.read_text(encoding="utf-8")


def test_scheduling_doc_exists():
    assert SCHEDULING.is_file(), f"expected {SCHEDULING} to exist"


def test_substitute_block_documents_plugin_root_placeholder():
    text = _text()
    assert "<plugin-root>" in text, (
        "scheduling.md's Substitute block must document a <plugin-root> "
        "placeholder for the installed plugin's root directory"
    )
    assert "CLAUDE_PLUGIN_ROOT" in text, (
        "scheduling.md must explain how to resolve <plugin-root> — via "
        "$CLAUDE_PLUGIN_ROOT from an active Claude Code session (or "
        "/dev-team:version) — since the literal ${CLAUDE_PLUGIN_ROOT} token "
        "does not exist outside a Claude session"
    )
    assert "/dev-team:version" in text, (
        "scheduling.md must also document the session-less derivation route "
        "— via /dev-team:version's output — for an operator with no active "
        "Claude Code session; deleting that route's text must not leave this "
        "test green"
    )
    assert "plugins/cache/" in text, (
        "scheduling.md's /dev-team:version derivation must name the plugin "
        "cache path it resolves to, not just gesture at the command"
    )


def test_no_recipe_uses_the_operators_repo_for_the_script_path():
    """The bug this issue fixed: none of the three recipes may build the
    script path as `<repo>/plugins/dev-team/skills/mutation-testing/...` —
    that shape only resolves inside this monorepo's own checkout."""
    text = _text()
    offenders = _MONOREPO_SHAPED_SCRIPT_PATH_RE.findall(text)
    assert not offenders, (
        "scheduling.md still points a script path at the operator's own "
        "repo root instead of the installed plugin root: "
        f"{offenders!r}"
    )


#: The three OS-recipe headings, in the order they appear in scheduling.md.
#: Used to slice the file into per-recipe sections so a duplicated invocation
#: in one recipe can never mask a dropped/malformed one in another — a
#: whole-file count of 3 alone can't distinguish "one per recipe" from
#: "two in one recipe, zero in another".
_RECIPE_HEADINGS = (
    "## macOS — launchd",
    "## Linux — cron",
    "## Windows — Task Scheduler",
)
_PLUGIN_ROOT_INVOCATION_RE = re.compile(
    r"<plugin-root>[/\\]skills[/\\]mutation-testing[/\\]scripts[/\\]mutation_nightwatch\.py"
)


def _recipe_sections(text: str) -> dict[str, str]:
    """{heading: section_text} for each of `_RECIPE_HEADINGS`, where
    `section_text` runs from that heading up to (not including) the next
    `## ` heading or end of file.

    The last recipe (Windows) has no *named* following entry in
    `_RECIPE_HEADINGS`, but scheduling.md itself continues past it with a
    trailer section (`## Every OS: reading the result`) — bounding the last
    section at end-of-file instead of that next `## ` heading would silently
    fold the trailer into the Windows slice, defeating the per-recipe
    isolation this helper exists to provide (a future `<plugin-root>`
    mention added to the trailer would misattribute to Windows instead of
    failing on its own)."""
    sections: dict[str, str] = {}
    for i, heading in enumerate(_RECIPE_HEADINGS):
        start = text.index(heading)
        if i + 1 < len(_RECIPE_HEADINGS):
            end = text.index(_RECIPE_HEADINGS[i + 1])
        else:
            next_heading = text.find("\n## ", start + len(heading))
            end = next_heading if next_heading != -1 else len(text)
        sections[heading] = text[start:end]
    return sections


def test_windows_recipe_section_excludes_the_every_os_trailer():
    """The specific defect an earlier draft of `_recipe_sections()` had:
    bounding the last section at end-of-file instead of the next `## `
    heading silently folds the `## Every OS: reading the result` trailer
    into the Windows recipe's slice. None of this file's other assertions
    would catch that regression on today's content (the trailer contains no
    `<plugin-root>`-shaped invocation for the count-based checks to trip
    on), so this test encodes the boundary condition directly."""
    sections = _recipe_sections(_text())
    windows_section = sections["## Windows — Task Scheduler"]
    assert "Every OS: reading the result" not in windows_section, (
        "Windows recipe section leaked past its heading into the trailer "
        "section — _recipe_sections() is bounding the last section at "
        "end-of-file again instead of the next '## ' heading"
    )


def test_every_recipe_invokes_the_script_via_plugin_root():
    """Each of the three per-OS recipes (launchd, cron, schtasks) must
    reference mutation_nightwatch.py via <plugin-root>, not any other
    placeholder. Checked per-recipe-section, not as one whole-file count —
    a whole-file count of 3 would still pass if one recipe duplicated the
    invocation while another dropped it entirely."""
    sections = _recipe_sections(_text())
    for heading, section_text in sections.items():
        matches = _PLUGIN_ROOT_INVOCATION_RE.findall(section_text)
        assert len(matches) == 1, (
            f"expected the {heading!r} recipe to invoke mutation_nightwatch.py "
            f"via <plugin-root> exactly once; found {len(matches)}"
        )


def test_repo_root_flag_and_log_paths_are_left_alone():
    """--repo-root <repo> and the <repo>/reports/... log/summary paths
    genuinely name the operator's own project being measured — this fix
    must not have touched those. The launchd plist passes --repo-root and
    <repo> as two separate <string> array elements rather than one
    space-joined token, so this matches loosely rather than requiring the
    exact "--repo-root <repo>" substring in all three recipes."""
    text = _text()
    assert text.count("--repo-root") == 3, (
        "expected all three recipes (launchd, cron, schtasks) to still pass "
        "--repo-root unchanged"
    )
    assert text.count("<repo>") >= 3, (
        "expected --repo-root's <repo> argument to still be present at least "
        "once per recipe"
    )
    assert "<repo>/reports/mutation-nightwatch/" in text
