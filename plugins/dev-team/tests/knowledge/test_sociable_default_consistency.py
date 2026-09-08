"""Content contract for #2125 — bringing the four pre-existing normative
locations into agreement with knowledge/internal-collaborator-doubling.md
(#2124): sociable is the default, solitary is permitted only where every
double names a blocker, and no file duplicates the rule verbatim.

The non-duplication check bounds *known-phrase* duplication (the two exact
co-equal sentences being replaced by this issue) — it cannot prove no
paraphrase of the rule exists anywhere in the tree; that is a
human /code-review judgment, not a grep (see plan-review-design's warning
on plans/2125-sociable-default-existing-guidance.md).
"""

from __future__ import annotations

import re

import pytest

from _repo_root import REPO_ROOT

KNOWLEDGE = REPO_ROOT / "plugins" / "dev-team" / "knowledge"
PYRAMID = KNOWLEDGE / "test-pyramid.md"
DOUBLES = KNOWLEDGE / "test-doubles.md"
CD_ARCH = KNOWLEDGE / "cd-test-architecture.md"
COMPONENT_PATTERNS = KNOWLEDGE / "component-test-patterns.md"

OLD_PYRAMID_PHRASE = (
    "Both are legitimate; sociable unit tests catch wiring bugs solitary ones miss"
)
OLD_CD_ARCH_PHRASE = "Both are deterministic and pre-merge."
# The bare, unqualified form this issue replaces — a sentence ending right
# after "pre-merge." with nothing following on the same line/paragraph.
# Test-review note: this regex only rejects the *standalone* form (newline
# or EOF immediately after); it does not reject a period-terminated
# "pre-merge. <next sentence>" continuation, which would also satisfy
# test_cd_arch_old_bare_coequal_sentence_qualified but then trip the
# tree-wide literal-phrase ban below. The actual edit uses a comma
# continuation ("pre-merge, but..."), which satisfies both — a future
# edit changing punctuation only needs to keep the qualifier in the same
# sentence, not necessarily comma-joined.
OLD_CD_ARCH_STANDALONE_RE = re.compile(r"Both are deterministic and pre-merge\.\s*(\n|$)")


@pytest.fixture(scope="module")
def pyramid_text() -> str:
    return PYRAMID.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def doubles_text() -> str:
    return DOUBLES.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def cd_arch_text() -> str:
    return CD_ARCH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def component_patterns_text() -> str:
    return COMPONENT_PATTERNS.read_text(encoding="utf-8")


# --- test-pyramid.md ---


def test_pyramid_old_coequal_phrase_removed(pyramid_text: str) -> None:
    assert OLD_PYRAMID_PHRASE not in pyramid_text


def test_pyramid_states_sociable_default(pyramid_text: str) -> None:
    assert "sociable" in pyramid_text.lower()
    assert "default" in pyramid_text.lower()
    assert "internal-collaborator-doubling.md" in pyramid_text


def test_pyramid_asserts_every_double_names_a_blocker(pyramid_text: str) -> None:
    # AC1 (plan-review-acceptance blocker fix): the paragraph must actually
    # state the qualifier, not just mention "sociable"/"default" nearby.
    sentence = re.search(r'"Unit" can be.*?\.\s*See', pyramid_text, re.DOTALL)
    assert sentence, "solitary/sociable definition paragraph not found"
    fragment = sentence.group(0)
    assert re.search(r"\bevery\b", fragment, re.IGNORECASE)
    assert re.search(r"\bblocker", fragment, re.IGNORECASE)


def test_pyramid_unit_row_doubles_column_qualified(pyramid_text: str) -> None:
    assert "| Stub/Fake collaborators |" not in pyramid_text
    assert "doubles only per a named blocker" in pyramid_text


# --- test-doubles.md ---


def test_doubles_misuse_row_no_unit_exemption(doubles_text: str) -> None:
    assert "at or below the component layer" in doubles_text
    assert "no unit-test exemption exists" in doubles_text


def test_doubles_misuse_row_cites_normative_source(doubles_text: str) -> None:
    assert "internal-collaborator-doubling.md" in doubles_text


# --- cd-test-architecture.md ---


def test_cd_arch_old_bare_coequal_sentence_qualified(cd_arch_text: str) -> None:
    # The old sentence must no longer stand alone (unqualified, ending the
    # paragraph) — it must now be followed by the sociable-default
    # qualifier within the same sentence/paragraph.
    assert not OLD_CD_ARCH_STANDALONE_RE.search(cd_arch_text)
    idx = cd_arch_text.index("Both are deterministic and pre-merge")
    tail = cd_arch_text[idx : idx + 400]
    assert "sociable is the default" in tail.lower()
    assert "blocker" in tail.lower()


def test_cd_arch_cites_normative_source(cd_arch_text: str) -> None:
    assert "internal-collaborator-doubling.md" in cd_arch_text


# --- component-test-patterns.md ---


def test_component_patterns_core_principle_distinguishes_internal(
    component_patterns_text: str,
) -> None:
    # Design-review fix: a bare citation isn't enough — the principle text
    # itself must distinguish "internal collaborator" from "systems the
    # team doesn't control", not just point elsewhere. Anchored to the
    # "Core principle" paragraph specifically (test-review finding): a
    # whole-document substring check would pass even if "internal" only
    # appeared in an unrelated sentence.
    match = re.search(
        r"Core principle.*?internal.*?internal-collaborator-doubling\.md",
        component_patterns_text,
        re.DOTALL,
    )
    assert match, "Core principle paragraph doesn't distinguish internal collaborators or cite the rule file"


# --- Tree-wide non-duplication (AC3: "anywhere in the tree") ---


def _iter_plugin_md_files():
    plugin_root = REPO_ROOT / "plugins" / "dev-team"
    yield from plugin_root.rglob("*.md")


@pytest.mark.parametrize("old_phrase", [OLD_PYRAMID_PHRASE, OLD_CD_ARCH_PHRASE])
def test_old_coequal_phrases_not_duplicated_anywhere(old_phrase: str) -> None:
    # Both old phrases were rewritten in place (comma/qualifier replacing
    # the bare period), so neither should match verbatim anywhere,
    # including in the two files that originally carried them.
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in _iter_plugin_md_files()
        if old_phrase in path.read_text(encoding="utf-8", errors="ignore")
    ]
    assert not offenders, f"Old co-equal phrase leaked into: {offenders}"


def test_cross_file_consistency_both_say_sociable_default(
    pyramid_text: str, cd_arch_text: str
) -> None:
    assert "sociable" in pyramid_text.lower() and "default" in pyramid_text.lower()
    assert "sociable is the default" in cd_arch_text.lower()
