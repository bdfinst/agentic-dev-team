"""Contract for the shared `_mutation_kill_agent_doc_helpers` module (#1927,
plan slice 1, steps 1.1-1.2): `AGENT`, `agent_text()`, and
`required_section()`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from _mutation_kill_agent_doc_helpers import AGENT, agent_text, required_section

from _repo_root import REPO_ROOT

# The 6 tests/agents/ mutation-kill doc-test files migrated to this shared
# module in Steps 1.3-1.5 (#1927). Kept as filenames, resolved against this
# file's own directory, so the group-wide regression checks below stay in
# sync with wherever this test file itself lives.
_DOC_TEST_FILENAMES = (
    "test_mutation_kill_agent.py",
    "test_mutation_kill_feasibility_gate_doc.py",
    "test_mutation_kill_baseline_reuse_doc.py",
    "test_mutation_kill_line_clustering_doc.py",
    "test_mutation_kill_skip_static_doc.py",
    "test_mutation_kill_retry_downgrade_doc.py",
)

# Exact pattern named in the Acceptance Criteria (both quote styles).
_HAND_ROLLED_REPLACE_PATTERN = re.compile(r"""\.replace\(\s*['"]\\n['"]\s*,\s*['"] ['"]\s*\)""")

# A bare, unqualified `section(` call -- i.e. a call to skill_doc_helpers.section
# imported under the plain name `section`, not `required_section(` (the `\b`
# already can't match inside "required_section(" since `_` is a word
# character) and not a dotted/qualified reference like
# "skill_doc_helpers.section()" as it appears in prose/docstrings (excluded
# by the negative lookbehind on the preceding ".").
_BARE_SECTION_CALL_PATTERN = re.compile(r"(?<!\.)\bsection\(")


def test_agent_resolves_to_mutation_kill_md() -> None:
    assert AGENT == REPO_ROOT / "plugins" / "dev-team" / "agents" / "mutation-kill.md"
    assert AGENT.is_file()


def test_agent_text_returns_full_file_content() -> None:
    assert agent_text() == AGENT.read_text(encoding="utf-8")


def test_required_section_returns_matched_section() -> None:
    text = agent_text()
    result = required_section(
        text,
        r"^## Pre-loop feasibility gate",
        boundary_pattern=r"^## ",
        include_start_line=False,
        name="Pre-loop feasibility gate",
    )
    assert result


def test_required_section_raises_with_given_name_when_missing() -> None:
    with pytest.raises(AssertionError, match="Some Section"):
        required_section(
            "no matching heading here",
            r"^## Does Not Exist",
            name="Some Section",
        )


def test_required_section_raises_with_some_message_when_name_omitted() -> None:
    with pytest.raises(AssertionError):
        required_section("no matching heading here", r"^## Does Not Exist")


def test_no_hand_rolled_replace_or_bare_section_call_in_doc_test_files() -> None:
    """Regression guard (#1927 Step 1.6): none of the 6 tests/agents/
    mutation-kill doc-test files hand-rolls ``.replace("\\n", " ")`` in place
    of ``skill_doc_helpers.collapsed()``, and none calls
    ``skill_doc_helpers.section()`` directly (via a bare `section` import)
    in place of this module's ``required_section()``. Steps 1.3-1.5 migrated
    the four originally-named fixtures plus three additional hand-rolled
    instances the plan's original grep missed (including one in
    ``test_mutation_kill_agent.py`` this step's own writing surfaced and
    fixed) -- this test guards against either class reappearing.
    """
    doc_test_dir = Path(__file__).parent
    for filename in _DOC_TEST_FILENAMES:
        source = (doc_test_dir / filename).read_text(encoding="utf-8")
        assert not _HAND_ROLLED_REPLACE_PATTERN.search(source), (
            f"{filename} hand-rolls .replace('\\n', ' ') instead of skill_doc_helpers.collapsed()"
        )
        for lineno, line in enumerate(source.splitlines(), start=1):
            if "required_section" in line:
                continue
            match = _BARE_SECTION_CALL_PATTERN.search(line)
            assert not match, (
                f"{filename}:{lineno} calls section() directly instead of "
                f"required_section(): {line.strip()!r}"
            )
