"""Contract for gherkin-derive's read-before-write merge behavior (issue #1420,
Step 1.4). Verifies SKILL.md documents resolving/reading an existing
`.feature` file and merging into it via `gherkin_feature_merge.py`, never a
raw overwrite.
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, grep

SKILL = PLUGIN_ROOT / "skills" / "gherkin-derive" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text()


def test_documents_resolving_the_existing_file_before_authoring():
    text = _text()
    assert grep(r"resolve.*existing file|existing file before", text, ignore_case=True)
    assert "detect_bdd_convention.py" in text


def test_output_step_names_the_merge_subcommand_not_a_raw_write():
    text = _text()
    assert "gherkin_feature_merge.py merge" in text
    assert grep(r"never a raw.*Write|never.*overwritten", text, ignore_case=True)


def test_no_overwrite_implying_language_in_the_touched_sections():
    text = _text()
    idx = text.find("## Step 5 — Output")
    step6_idx = text.find("## Step 6")
    section = text[idx : step6_idx if step6_idx != -1 else None]
    assert not grep(r"overwrit", section, ignore_case=True)
