"""Contract for issue #1451: test-double misuse guidance for a collaborator
internal to / owned by the same component or bounded context as the SUT must
be (1) named as its own distinct entry in the misuse taxonomy, (2) wired into
the software-engineer agent's Knowledge Files so it's in scope at authoring
time, and (3) named as its own detection target in test-smell-review's
"Test double misuse" list so it's flagged as a review-time backstop.
"""

from __future__ import annotations

from _repo_root import REPO_ROOT

TEST_DOUBLES = REPO_ROOT / "plugins" / "dev-team" / "knowledge" / "test-doubles.md"
SOFTWARE_ENGINEER = (
    REPO_ROOT / "plugins" / "dev-team" / "agents" / "software-engineer.md"
)


def _text(path) -> str:
    return path.read_text(encoding="utf-8")


def test_misuse_table_names_internal_collaborator_entry() -> None:
    text = _text(TEST_DOUBLES)
    assert "internal to / owned by the same component or bounded context" in text
    # It cites the component-test-patterns.md core principle as the fix.
    assert "component-test-patterns.md" in text


def test_internal_collaborator_row_distinct_from_concrete_class_row() -> None:
    text = _text(TEST_DOUBLES)
    # The two misuses must be separate table rows, not merged into one.
    concrete_class_line = next(
        line
        for line in text.splitlines()
        if "concrete class instead of an interface/port" in line
    )
    internal_collaborator_line = next(
        line
        for line in text.splitlines()
        if "internal to / owned by the same component or bounded context" in line
    )
    assert concrete_class_line != internal_collaborator_line
    assert "internal" not in concrete_class_line


def test_software_engineer_references_test_doubles_knowledge_file() -> None:
    text = _text(SOFTWARE_ENGINEER)
    assert "knowledge/test-doubles.md" in text
    # Loaded at the moment a test double is written or reviewed, not only
    # at review time.
    assert "test double" in text.lower()
