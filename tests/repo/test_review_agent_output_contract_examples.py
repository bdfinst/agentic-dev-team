"""Keeps `review-agent-output-contract.md`'s `category` worked examples in
sync with the real agent files they cite (#1639).

The contract doc enumerates each example agent's `category` value set inline
so a reader doesn't have to open every agent file to see the shape — but
that means the same taxonomy string now exists in two places with nothing
tying them together. A domain-review pass on #1639 flagged this: the
contract doc's own text says "each agent defines its own taxonomy in its own
body", immediately followed by copies of three agents' values inline, with
no gate keeping the copy honest if an agent's taxonomy changes later.

The first draft of this gate checked substring containment against a
hand-typed expected value — a second review round caught that this only
catches a *removed*/*renamed* value, not an *appended* one: if
`ai-provenance-review.md` grew a third category value, both the old
substring and the doc's now-incomplete copy would still contain each other,
and the test would stay green while the doc silently went stale. Fixed by
extracting the enum agents' full current value straight from their own file
via regex — so there is nothing to keep in sync by hand for those two.

A third round then caught that checking `value in CONTRACT` was still bare
substring containment, just with the operands swapped: if the agent's own
value ever *shrinks* (e.g. `spec-compliance-review` drops
`|plan-deviation`), the shrunk extracted value is still a substring of the
doc's now-stale, wider copy, so the check passes while the doc keeps
advertising a category the agent no longer emits. Fixed by asserting on the
exact quoted JSON fragment (`"category": "<value>"`, trailing quote
included) rather than the bare value — a shrunk value's fragment ends its
own closing quote right where the doc's stale text continues with more
members instead, so it no longer matches.

`security-review` doesn't fit the closed-enum shape: its own schema line,
and the contract doc's own citation of it, both show the generic
`A<NN>.<slug>` pattern plus one worked example (`A03.sql-injection`), not an
enum to extract — kept as a literal pin for that reason, documented inline
below.
"""

from __future__ import annotations

import re

from _repo_root import REPO_ROOT

PLUGIN_ROOT = REPO_ROOT / "plugins" / "dev-team"
CONTRACT = (PLUGIN_ROOT / "knowledge" / "review-agent-output-contract.md").read_text(
    encoding="utf-8"
)

#: Matches this repo's `"category": "<value>"` schema-line convention.
_CATEGORY_VALUE_RE = re.compile(r'"category":\s*"([^"]+)"')


def _extract_category_enum(agent_file: str) -> str:
    """The full `category` value from `agent_file`'s own schema line.

    Extracting rather than hand-typing the expected value means a future
    agent taxonomy change is automatically picked up here — the only thing
    that can go stale is the contract doc, which is exactly what these tests
    exist to catch.

    Requires exactly one `"category": "..."` match in the file. `.search()`
    alone would silently take the first of several (as security-review.md
    genuinely has, at its schema line plus three concrete examples) — for
    the two enum agents this pins today that would be a false assumption to
    hold silently, so an agent gaining a second `"category":` occurrence
    fails loudly here instead of quietly changing which one gets compared.
    """
    text = (PLUGIN_ROOT / "agents" / agent_file).read_text(encoding="utf-8")
    matches = _CATEGORY_VALUE_RE.findall(text)
    assert matches, f'{agent_file}: no `"category": "..."` schema line found to extract'
    assert len(matches) == 1, (
        f"{agent_file}: expected exactly one \"category\": \"...\" occurrence to "
        f"extract from, found {len(matches)}: {matches!r} — this agent no longer "
        "fits the closed-enum-with-one-schema-line shape this helper assumes"
    )
    return matches[0]


#: Agents whose full `category` value is a closed, extractable enum — kept
#: in sync automatically via `_extract_category_enum`.
_ENUM_WORKED_EXAMPLES = ("ai-provenance-review.md", "spec-compliance-review.md")

#: `security-review`'s contract-doc citation is the generic `A<NN>.<slug>`
#: pattern plus one illustrative concrete value, not a closed enum — pinned
#: as a literal substring instead of extracted. Shrink-only: if the pattern
#: or the chosen example changes, update both sides in the same change.
_SECURITY_REVIEW_PATTERN = "A<NN>.<slug>"
_SECURITY_REVIEW_EXAMPLE = "A03.sql-injection"


def test_enum_worked_examples_are_quoted_in_full_by_the_contract_doc():
    missing = []
    for agent_file in _ENUM_WORKED_EXAMPLES:
        value = _extract_category_enum(agent_file)
        # The exact quoted fragment, trailing quote included — not the bare
        # value — so a doc copy that's merely a truncated prefix of the
        # agent's real (possibly since-widened) value doesn't false-pass.
        fragment = f'"category": "{value}"'
        if fragment not in CONTRACT:
            missing.append(f"{agent_file}: current category value {value!r} not found in review-agent-output-contract.md")
    assert not missing, (
        "review-agent-output-contract.md's category worked examples are "
        "stale — an agent's taxonomy changed and the doc's copy wasn't "
        "updated to match:\n  " + "\n  ".join(missing)
    )


def test_security_review_pattern_and_example_are_quoted_by_the_contract_doc():
    agent_text = (PLUGIN_ROOT / "agents" / "security-review.md").read_text(encoding="utf-8")
    for value in (_SECURITY_REVIEW_PATTERN, _SECURITY_REVIEW_EXAMPLE):
        assert value in agent_text, f"security-review.md no longer contains {value!r}"
        assert value in CONTRACT, (
            f"review-agent-output-contract.md no longer quotes {value!r} — "
            "update _SECURITY_REVIEW_PATTERN/_SECURITY_REVIEW_EXAMPLE or "
            "restore the citation"
        )
