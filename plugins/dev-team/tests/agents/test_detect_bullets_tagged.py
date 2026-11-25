"""Every ``## Detect`` bullet of the four tagged agents declares who can decide it,
and tagging changed no finding wording.

Annotation format: appended at the end of the bullet's last line, one of

    <bullet text> [MECHANICAL] rule: <id>
    <bullet text> [MECHANICAL] no rule: <reason of at least three words>
    <bullet text> [JUDGMENT]

Stripping the annotation and normalizing whitespace (single spaces, trimmed)
must give back the pinned original text in ``fixtures/detect-original/<agent>.txt``.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_PLUGIN_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PLUGIN_ROOT / "scripts"))
sys.path.insert(0, str(_PLUGIN_ROOT / "scripts" / "lib"))

import check_detect_tags
from detect_bullets import bullet_blocks, detect_bullets

PINNED_DIR = Path(__file__).parent / "fixtures" / "detect-original"
AGENT_FILES = {path.stem: path for path in check_detect_tags.DEFAULT_AGENT_FILES}

_ANNOTATION = re.compile(
    r"\s*\[(?:MECHANICAL|JUDGMENT)\]"
    r"(?:\s+rule:\s*[A-Za-z0-9_/@.-]+|\s+no rule:[^\n]*)?\s*$"
)


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _stripped(bullet_text: str) -> str:
    return _normalize(_ANNOTATION.sub("", bullet_text))


def test_default_agent_set_is_the_four_tagged_agents():
    assert sorted(AGENT_FILES) == [
        "esm-enforcer",
        "js-fp-review",
        "naming-review",
        "structure-review",
    ]


def test_checker_passes_on_the_four_real_files():
    bullets = []
    errors = []
    for path in AGENT_FILES.values():
        file_bullets, file_errors = check_detect_tags.check_text(
            str(path), path.read_text(encoding="utf-8")
        )
        bullets.extend(file_bullets)
        errors.extend(file_errors)

    assert [e.render() for e in errors] == []
    assert sum(1 for b in bullets if not b.tags) == 0
    assert sum(1 for b in bullets if len(b.tags) > 1) == 0
    assert check_detect_tags.main([str(p) for p in AGENT_FILES.values()]) == 0


@pytest.mark.parametrize("agent", sorted(AGENT_FILES))
def test_tagging_leaves_detect_wording_unchanged(agent):
    current = [
        _stripped(b.text)
        for b in detect_bullets(AGENT_FILES[agent].read_text(encoding="utf-8"))
    ]
    pinned = [
        _normalize(block)
        for block in bullet_blocks(
            (PINNED_DIR / f"{agent}.txt").read_text(encoding="utf-8")
        )
    ]

    assert current == pinned


def test_stripping_removes_each_annotation_form():
    forms = [
        "- text here [MECHANICAL] rule: no-var",
        "- text here [MECHANICAL] no rule: needs a call graph",
        "- text here [JUDGMENT]",
    ]
    assert [_stripped(form) for form in forms] == ["- text here"] * 3
