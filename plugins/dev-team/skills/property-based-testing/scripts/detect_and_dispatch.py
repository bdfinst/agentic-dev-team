"""Thin dispatch helper for /property-based-testing's SKILL.md procedure
(#2190, Step 4.2).

Language detection itself is NOT implemented here. `SKILL.md` runs
project-init's own stack-detection step first —
`${CLAUDE_PLUGIN_ROOT}/skills/project-init/SKILL.md` § "Step 1: Detect the
stack" — and passes its result into this module via `--language`. This
module only decides, from that already-detected value, whether the skill
can proceed: it never re-derives a language from project-init's own
manifest-file detection signals itself.

On an unsupported or missing language it prints the exact message the
Gherkin "Unsupported or undetected language" scenario requires and returns
a non-zero exit code, so `SKILL.md`'s procedure can stop with no partial
run. On a supported language it prints which generator the procedure
should dispatch to next and returns 0.
"""

from __future__ import annotations

import argparse

# The only two languages this skill scaffolds properties for today. `JS/TS`
# is project-init's own stack-detection display name (SKILL.md § "Step 1:
# Detect the stack") — this module matches it verbatim, never a spelled-out
# "JavaScript/TypeScript", since that is the actual value Step 1 hands this
# script. Python dispatches to Step 4.1's hypothesis_scaffold.py; JS/TS
# dispatches to the fast-check path (references/languages/javascript.md).
SUPPORTED_LANGUAGES = ("Python", "JS/TS")

UNSUPPORTED_MESSAGE = "Unsupported language: {language} — supported: Python, JS/TS."

_DISPATCH = {
    "Python": "Hypothesis (scripts/hypothesis_scaffold.py)",
    "JS/TS": "fast-check (references/languages/javascript.md)",
}


def is_supported(language: str | None) -> bool:
    """True when `language` is one of the two languages this skill supports."""
    return language in SUPPORTED_LANGUAGES


def unsupported_language_message(language: str | None) -> str:
    """Render the exact unsupported-language message. `language` is the
    value project-init's stack detection (see module docstring) returned —
    `None`/empty when detection failed or returned nothing, in which case
    the message interpolates the literal word "unknown"."""
    return UNSUPPORTED_MESSAGE.format(language=language or "unknown")


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Decide whether /property-based-testing can proceed for an "
            "already-detected language (from project-init's stack "
            "detection) and print the unsupported-language message when it "
            "can't."
        )
    )
    parser.add_argument(
        "--language",
        default=None,
        help=(
            "the language project-init's stack detection returned; omit "
            "when detection failed or returned nothing"
        ),
    )
    args = parser.parse_args(argv)

    if not is_supported(args.language):
        print(unsupported_language_message(args.language))
        return 1

    print(f"Detected {args.language} — dispatching to {_DISPATCH[args.language]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
