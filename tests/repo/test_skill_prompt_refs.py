"""Skill -> prompt-template reference sensor (issue #173).

Shipped SKILL.md files dispatch sub-agents seeded from prompt templates that
live at the PLUGIN ROOT (plugins/dev-team/prompts/). A bare `prompts/X.md`
reference is ambiguous - at runtime the model resolved it skill-relative,
found nothing, and fell back to inline persona briefs (#173). This sensor
keeps every such reference (a) resolvable to a real file and (b) written in
the explicit `${CLAUDE_PLUGIN_ROOT}/prompts/...` form so it can't regress.

Scope: shipped skills only - plugins/dev-team/skills/**/SKILL.md.

Ported from tests/repo/skill_prompt_refs_test.bats (#673).
"""

from __future__ import annotations

import re
from pathlib import Path

from _repo_root import REPO_ROOT

SKILLS_DIR = REPO_ROOT / "plugins" / "dev-team" / "skills"
PROMPTS_DIR = REPO_ROOT / "plugins" / "dev-team" / "prompts"

_REF_RE = re.compile(r"prompts/[a-zA-Z0-9_-]+\.md")


def _skill_md_files() -> list[Path]:
    return sorted(SKILLS_DIR.rglob("SKILL.md"))


def _lines_with_ref() -> list[tuple[Path, str]]:
    hits: list[tuple[Path, str]] = []
    for f in _skill_md_files():
        for line in f.read_text().splitlines():
            if _REF_RE.search(line):
                hits.append((f, line))
    return hits


def test_every_prompts_reference_resolves_to_a_real_template() -> None:
    missing = []
    for file, line in _lines_with_ref():
        match = _REF_RE.search(line)
        assert match is not None
        name = match.group(0).split("prompts/", 1)[1]
        if not (PROMPTS_DIR / name).is_file():
            rel = file.relative_to(REPO_ROOT)
            missing.append(
                f"{rel}: prompts/{name} (not found at plugins/dev-team/prompts/)"
            )
    assert not missing, "Unresolvable prompt-template reference(s):\n" + "\n".join(
        missing
    )


def test_prompt_template_references_use_explicit_plugin_root_form() -> None:
    bare = []
    for file, line in _lines_with_ref():
        stripped = line.replace("${CLAUDE_PLUGIN_ROOT}/prompts/", "__OK__")
        if _REF_RE.search(stripped):
            bare.append(f"{file.relative_to(REPO_ROOT)}: {line}")
    assert not bare, (
        "Ambiguous bare prompts/ reference(s) - use "
        "${CLAUDE_PLUGIN_ROOT}/prompts/<name>.md:\n" + "\n".join(bare)
    )
