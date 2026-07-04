"""Prose-honesty gate (issue #100).

"Prose a deterministic gate touches stays clean; prose no sensor reaches
rots." This test IS that sensor for the flagship CLAUDE.md and sibling
shipped docs: it fails loudly if metaphor-as-mechanism buzzwords or
un-instrumented numeric targets reappear in shipped prose.

Scope: shipped prose only — plugins/dev-team/**/*.md. Non-shipped docs
(repo-level docs/, plans/, evals/) are out of scope.

Ported from tests/docs/prose_honesty_test.bats (issue #675:
bats -> pytest).
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_DOCS = REPO_ROOT / "plugins" / "dev-team"
CLAUDE_MD = PLUGIN_DOCS / "CLAUDE.md"

# Metaphor-as-mechanism phrases: borrowed jargon describing a mechanism the
# code does not implement. Add to this list as new ones are caught.
BANNED_PHRASES = [
    "federated learning",
    "LSTM-inspired",
    "LSTM inspired",
    # #105: the Multi-LLM/Gemini routing table promised a capability no
    # code implements (the stack is Claude-Code-locked). Removed; keep it
    # gone.
    "Multi-LLM Routing",
    "Gemini",
]

# These were the un-falsifiable Targets removed in #100 — originally from
# CLAUDE.md, but they also lived in sibling shipped docs (performance-metrics
# and governance-compliance skills). The sensor scans ALL shipped prose, not
# just CLAUDE.md: a target with no instrument must not ship anywhere. If a
# number is real, move it under "Claims discipline" naming its instrument.
# Add to this list as new ones are caught.
BANNED_TARGETS = [
    "10-15% overall efficiency gains",
    "< 5% hallucination rate",
    "95% accuracy on structured data extraction",
    "> 80% first-pass acceptance rate",
    "< 5% of tasks",
    "< 5% of total task tokens",
    "> 50% reduction",
    "within target (< 5%)",
]


def test_no_metaphor_as_mechanism_buzzwords_in_shipped_plugin_prose() -> None:
    hits = []
    for file in sorted(PLUGIN_DOCS.rglob("*.md")):
        content = file.read_text(encoding="utf-8").lower()
        for phrase in BANNED_PHRASES:
            if phrase.lower() in content:
                hits.append(f'{file.relative_to(REPO_ROOT)}: "{phrase}"')

    assert not hits, (
        "Banned metaphor-as-mechanism prose found (replace with a literal "
        "description of the mechanism, or delete):\n" + "\n".join(hits)
    )


def test_no_bare_uninstrumented_numeric_targets_in_shipped_plugin_prose() -> None:
    hits = []
    for file in sorted(PLUGIN_DOCS.rglob("*.md")):
        content = file.read_text(encoding="utf-8")
        for target in BANNED_TARGETS:
            if target in content:
                hits.append(f'{file.relative_to(REPO_ROOT)}: "{target}"')

    assert not hits, (
        "Un-instrumented numeric target(s) in shipped prose:\n"
        + "\n".join(hits)
        + "\nEither delete, or move under 'Claims discipline' naming the "
        "instrument."
    )


def test_claude_md_states_claims_discipline_rule() -> None:
    text = CLAUDE_MD.read_text(encoding="utf-8")
    assert "must name the instrument" in text.lower()


def test_claude_md_states_north_star() -> None:
    # The North Star is doctrine for every change. This sensor keeps it from
    # being silently deleted: it must declare the friction goal and the
    # name-the-friction-or-it-does-not-ship rule.
    text = CLAUDE_MD.read_text(encoding="utf-8")
    assert "## north star" in text.lower()
    assert "does not ship" in text.lower()
