#!/usr/bin/env python3
"""Check that every ``## Detect`` bullet in an agent file declares who can decide it.

Each bullet carries exactly one case-exact tag. ``[MECHANICAL]`` means a lint
rule could decide it, so the bullet must name that rule (``rule: <id>``) or say
why none exists (``no rule: <reason of at least three words>``). ``[JUDGMENT]``
means a model must decide it and needs no mapping.

A bullet converted to a lint pointer ("If ``eslint.devteam.config.js`` enables
``<id>`` and it is wired, judge only <residual>; otherwise judge fully") must
say "otherwise judge fully", name the rule id it relies on, and that id must be
the rule the bullet maps to and be listed as convertible.

Rule ids come from ``templates/eslint/rule-ids.json``: ``enabled`` (the
shipped config's rules), ``planned`` (mapping targets whose rule is not shipped
yet; valid for ``rule:`` but never for a pointer), and ``convertible``
(``lint_corpus_compare.py`` verdicts on the committed corpus). ``conditional``
(optional) lists enabled rules that run only when extra dependencies are
installed; a pointer to one is rejected because a lint run cannot be assumed.

Usage:
    python3 check_detect_tags.py [--rule-ids FILE] [agent-file ...]

With no file arguments, checks the four agents whose Detect bullets are tagged.
Exit 0 when every bullet is valid, 1 otherwise, printing
``<file>:<line> <bullet text>`` for each offender with the two ways to fix it.
Exit 2 when the rule-ids file or an agent file is unreadable.
"""

from __future__ import annotations

import argparse
import json
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

EXIT_INVALID = 1
EXIT_BAD_INPUT = 2

RULE_IDS_PATH = _PLUGIN_ROOT / "templates" / "eslint" / "rule-ids.json"


class RuleIds(NamedTuple):
    enabled: frozenset[str]
    planned: frozenset[str]
    convertible: frozenset[str]
    conditional: frozenset[str] = frozenset()

    @property
    def mappable(self) -> frozenset[str]:
        return self.enabled | self.planned


class RuleIdsError(ValueError):
    """The rule-ids file is unreadable or not shaped as expected."""


def load_rule_ids(path: Path = RULE_IDS_PATH) -> RuleIds:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        groups = {key: raw[key] for key in ("enabled", "planned", "convertible")}
        groups["conditional"] = raw.get("conditional", [])
        if not all(
            isinstance(ids, list) and all(isinstance(i, str) for i in ids)
            for ids in groups.values()
        ):
            raise TypeError("enabled, planned, convertible and conditional must be lists of strings")
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise RuleIdsError(f"rule-ids file {path}: {error!r}") from error
    return RuleIds(**{key: frozenset(ids) for key, ids in groups.items()})


MIN_REASON_WORDS = 3

# "no rule:" is tested first because "rule:" also matches inside it.
_NO_RULE = re.compile(r"\bno rule:[ \t]*([^\n]*)")
_RULE = re.compile(r"\brule:[ \t]*`?([A-Za-z0-9_/@.-]+)`?")

# A bullet converted to a lint pointer carries either marker.
_POINTER_MARKERS = ("otherwise judge fully", "eslint.devteam.config.js")
_POINTER_RULE = re.compile(r"enables `([^`]+)`")

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


def _mapping_text(text: str) -> str:
    """Return the text after the tag, so ``rule:`` in the bullet's prose never counts."""
    tag = TAG_PATTERN.search(text)
    return text[tag.end() :] if tag else text


def _mapping_error(text: str, rule_ids: RuleIds) -> str | None:
    """Return why a ``[MECHANICAL]`` bullet's rule mapping is invalid, or ``None``."""
    mapping = _mapping_text(text)
    no_rule_match = _NO_RULE.search(mapping)
    if no_rule_match:
        reason_words = no_rule_match.group(1).split()
        if len(reason_words) < MIN_REASON_WORDS:
            return f"'no rule:' needs a reason of at least {MIN_REASON_WORDS} words"
        return None
    rule_match = _RULE.search(mapping)
    if not rule_match:
        return "[MECHANICAL] bullet has no 'rule: <id>' or 'no rule: <reason>' mapping"
    if rule_match.group(1) not in rule_ids.mappable:
        return f"unknown rule id {rule_match.group(1)}"
    return None


def is_pointer(text: str) -> bool:
    return any(marker in text for marker in _POINTER_MARKERS)


def _pointer_error(text: str, rule_ids: RuleIds) -> str | None:
    """Return why a lint-pointer bullet is malformed, or ``None``."""
    mapping = _mapping_text(text)
    if _NO_RULE.search(mapping):
        return "a lint pointer needs a rule: <id> mapping"
    if "otherwise judge fully" not in text:
        return "pointer must say 'otherwise judge fully'"
    named = _POINTER_RULE.search(text)
    if not named:
        return "pointer must name the rule id it relies on"
    mapped = _RULE.search(mapping)
    if mapped and mapped.group(1) != named.group(1):
        return f"pointer names {named.group(1)} but the bullet maps to {mapped.group(1)}"
    if named.group(1) in rule_ids.conditional:
        return (
            f"pointer names {named.group(1)}, which is conditional: "
            "it runs only when typed dependencies are installed"
        )
    if named.group(1) not in rule_ids.convertible:
        return f"pointer names {named.group(1)}, which is not marked convertible"
    return None


def _bullet_error(bullet: DetectBullet, rule_ids: RuleIds) -> str | None:
    if not bullet.tags:
        return "bullet has no [MECHANICAL] or [JUDGMENT] tag (tags are case-exact)"
    if len(bullet.tags) > 1:
        return f"bullet has {len(bullet.tags)} tags, expected exactly one"
    if bullet.tags[0] == "MECHANICAL":
        return _mapping_error(bullet.text, rule_ids) or (
            _pointer_error(bullet.text, rule_ids) if is_pointer(bullet.text) else None
        )
    if is_pointer(bullet.text):
        return "a lint pointer needs a [MECHANICAL] tag with the rule it relies on"
    return None


def check_text(
    file: str, text: str, rule_ids: RuleIds | None = None
) -> tuple[list[DetectBullet], list[TagError]]:
    """Return the Detect bullets of ``text`` and an error for each invalid one."""
    rule_ids = rule_ids or load_rule_ids()
    bullets = detect_bullets(text)
    if not bullets:
        return bullets, [TagError(file, 1, "", "no '## Detect' section with bullets")]
    errors = [
        TagError(file, bullet.line, bullet.text, reason)
        for bullet in bullets
        if (reason := _bullet_error(bullet, rule_ids))
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
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("files", nargs="*", type=Path)
    parser.add_argument("--rule-ids", type=Path, default=RULE_IDS_PATH)
    args = parser.parse_args(argv)
    try:
        rule_ids = load_rule_ids(args.rule_ids)
    except RuleIdsError as error:
        print(f"check_detect_tags: {error}", file=sys.stderr)
        return EXIT_BAD_INPUT
    files = args.files or list(DEFAULT_AGENT_FILES)
    all_bullets: list[DetectBullet] = []
    errors: list[TagError] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as error:
            print(f"check_detect_tags: {path}: {error}", file=sys.stderr)
            return EXIT_BAD_INPUT
        bullets, file_errors = check_text(str(path), text, rule_ids)
        all_bullets.extend(bullets)
        errors.extend(file_errors)
    if errors:
        print("\n".join(error.render() for error in errors))
        print(
            f"FAIL: {len(errors)} invalid Detect bullets. {_summary(all_bullets, len(files))}"
        )
        return EXIT_INVALID
    print(f"OK: {_summary(all_bullets, len(files))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
