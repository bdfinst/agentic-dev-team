"""Content contract for the "Re-capture: keep vs. overwrite an existing
tracked artifact" decision-defaults axis (plans/test-improve-baseline-
persistence.md, Slice 1, Step 1.1).

This axis is the shared guard pattern coverage-baseline/SKILL.md (Step 1.2)
cites rather than restating inline: an interactive keep/overwrite prompt
(default keep), an unrecognized answer re-prompting rather than silently
falling back, a non-interactive run keeping and both logging AND echoing
the auto-decision, and a malformed/corrupt existing file being treated as
absent (never silently kept) with a warning.
"""

from __future__ import annotations

import pytest
from skill_doc_helpers import grep
from skill_doc_helpers import section as _section

from _repo_root import REPO_ROOT

DEFAULTS = REPO_ROOT / "plugins" / "dev-team" / "knowledge" / "decision-defaults.md"

_HEADING = r"^## Re-capture: keep vs\. overwrite an existing tracked artifact"


@pytest.fixture(scope="module")
def text() -> str:
    return DEFAULTS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def recapture_section(text: str) -> str:
    return _section(text, _HEADING, boundary_pattern=r"^## ")


def test_recapture_axis_heading_exists(text: str) -> None:
    assert "Re-capture: keep vs. overwrite an existing tracked artifact" in text


def test_recapture_axis_names_the_trigger(recapture_section: str) -> None:
    assert "Trigger:" in recapture_section
    assert "expensive capture" in recapture_section.lower()
    assert "tracked copy" in recapture_section.lower()


def test_recapture_axis_default_is_keep(recapture_section: str) -> None:
    assert "Default:" in recapture_section
    assert "**keep**" in recapture_section


def test_recapture_axis_documents_interactive_prompt_default_keep(
    recapture_section: str,
) -> None:
    assert (
        "keep/overwrite" in recapture_section.lower()
        or "keep or overwrite" in recapture_section.lower()
    )


def test_recapture_axis_documents_unrecognized_answer_reprompts(
    recapture_section: str,
) -> None:
    assert "re-prompt" in recapture_section.lower()
    assert (
        "no retry limit" in recapture_section.lower()
        or "no timeout" in recapture_section.lower()
    )


def test_recapture_axis_documents_non_interactive_logs_and_echoes(
    recapture_section: str,
) -> None:
    assert "non-interactive" in recapture_section.lower()
    assert "log" in recapture_section.lower() and "echo" in recapture_section.lower()


def test_recapture_axis_documents_malformed_file_treated_as_absent(
    recapture_section: str,
) -> None:
    assert (
        "malformed" in recapture_section.lower()
        or "corrupt" in recapture_section.lower()
    )
    assert "absent" in recapture_section.lower()
    assert "warning" in recapture_section.lower()


def test_recapture_axis_documents_overwrite_outcome(recapture_section: str) -> None:
    assert grep(
        r"on overwrite.{0,80}replace the tracked artifact",
        recapture_section,
        ignore_case=True,
    )
