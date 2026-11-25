#!/usr/bin/env python3
"""Check that every ``## Detect`` bullet in an agent file declares who can decide it.

Each bullet carries exactly one case-exact tag. ``[MECHANICAL]`` means a lint
rule could decide it, so the bullet must name that rule (``rule: <id>``) or say
why none exists (``no rule: <reason of at least three words>``). ``[JUDGMENT]``
means a model must decide it and needs no mapping.

Usage:
    python3 check_detect_tags.py [agent-file ...]

With no arguments, checks the four agents whose Detect bullets are tagged.
Exit 0 when every bullet is valid, 1 otherwise, printing
``<file>:<line> <bullet text>`` for each offender with the two ways to fix it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from detect_bullets import TAG_PATTERN, DetectBullet, detect_bullets

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_AGENT_FILES = (
    _PLUGIN_ROOT / "templates" / "agents" / "esm-enforcer.md",
    _PLUGIN_ROOT / "agents" / "js-fp-review.md",
    _PLUGIN_ROOT / "agents" / "naming-review.md",
    _PLUGIN_ROOT / "agents" / "structure-review.md",
)

# Target rule ids that are valid until the ESLint config and rule catalog
# become the source of truth for which rules exist.
PENDING_RULE_IDS = frozenset(
    {
        "no-var",
        "prefer-const",
        "no-plusplus",
        "no-param-reassign",
        "no-restricted-globals",
        "no-restricted-syntax",
        "max-depth",
        "no-magic-numbers",
        "functional/immutable-data",
    }
)

MIN_REASON_WORDS = 3

# "no rule:" is tested first because "rule:" also matches inside it.
_NO_RULE = re.compile(r"\bno rule:[ \t]*([^\n]*)")
_RULE = re.compile(r"\brule:[ \t]*`?([A-Za-z0-9_/@.-]+)`?")

FIXES = (
    "  fix 1: name the lint rule that decides it: rule: <id>",
    "  fix 2: or tag the bullet [JUDGMENT]",
)


class TagError(NamedTuple):
    file: str
    line: int
    text: str
    reason: str

    def render(self) -> str:
        shown = " ".join(self.text.split()).removeprefix("- ")
        return "\n".join(
            [f"{self.file}:{self.line} {shown}", f"  {self.reason}", *FIXES]
        )


def _mapping_error(text: str) -> str | None:
    """Return why a ``[MECHANICAL]`` bullet's rule mapping is invalid, or ``None``.

    Only the text after the tag counts as the mapping, so ``rule:`` in the
    bullet's prose does not satisfy it.
    """
    tag = TAG_PATTERN.search(text)
    mapping = text[tag.end() :] if tag else text
    no_rule_match = _NO_RULE.search(mapping)
    if no_rule_match:
        reason_words = no_rule_match.group(1).split()
        if len(reason_words) < MIN_REASON_WORDS:
            return f"'no rule:' needs a reason of at least {MIN_REASON_WORDS} words"
        return None
    rule_match = _RULE.search(mapping)
    if not rule_match:
        return "[MECHANICAL] bullet has no 'rule: <id>' or 'no rule: <reason>' mapping"
    if rule_match.group(1) not in PENDING_RULE_IDS:
        return f"unknown rule id {rule_match.group(1)}"
    return None


def _bullet_error(bullet: DetectBullet) -> str | None:
    if not bullet.tags:
        return "bullet has no [MECHANICAL] or [JUDGMENT] tag (tags are case-exact)"
    if len(bullet.tags) > 1:
        return f"bullet has {len(bullet.tags)} tags, expected exactly one"
    if bullet.tags[0] == "MECHANICAL":
        return _mapping_error(bullet.text)
    return None


def check_text(file: str, text: str) -> tuple[list[DetectBullet], list[TagError]]:
    """Return the Detect bullets of ``text`` and an error for each invalid one."""
    bullets = detect_bullets(text)
    if not bullets:
        return bullets, [TagError(file, 1, "", "no '## Detect' section with bullets")]
    errors = [
        TagError(file, bullet.line, bullet.text, reason)
        for bullet in bullets
        if (reason := _bullet_error(bullet))
    ]
    return bullets, errors


def _summary(bullets: list[DetectBullet], file_count: int) -> str:
    def count(tag: str) -> int:
        return sum(1 for b in bullets if b.tags == [tag])

    untagged = sum(1 for b in bullets if not b.tags)
    double = sum(1 for b in bullets if len(b.tags) > 1)
    return (
        f"{file_count} files, {len(bullets)} bullets: {count('MECHANICAL')} MECHANICAL, "
        f"{count('JUDGMENT')} JUDGMENT, {untagged} untagged, {double} double-tagged"
    )


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    files = [Path(a) for a in args] if args else list(DEFAULT_AGENT_FILES)
    all_bullets: list[DetectBullet] = []
    errors: list[TagError] = []
    for path in files:
        bullets, file_errors = check_text(str(path), path.read_text(encoding="utf-8"))
        all_bullets.extend(bullets)
        errors.extend(file_errors)
    if errors:
        print("\n".join(error.render() for error in errors))
        print(
            f"FAIL: {len(errors)} invalid Detect bullets. {_summary(all_bullets, len(files))}"
        )
        return 1
    print(f"OK: {_summary(all_bullets, len(files))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
