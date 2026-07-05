"""Issue #843 — code-review output paths must be pinned repo-relative.

The skill said only "Save to corrections/" with no anchor to the target repo's
working directory and no prohibition against prepending a sandbox/scratchpad
root, so the model produced doubled/mangled absolute paths. Pin ./corrections/
to cwd, forbid absolute-path joining, and state --json emits to stdout.
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT

CODE_REVIEW = (
    PLUGIN_ROOT / "skills" / "code-review" / "SKILL.md"
).read_text(encoding="utf-8")


def test_corrections_path_is_repo_relative_to_cwd():
    assert "./corrections/" in CODE_REVIEW, (
        "step 8 must pin the corrections output to ./corrections/ (repo-relative)"
    )
    assert "working directory" in CODE_REVIEW, (
        "output paths must be anchored to the target repository's working directory"
    )


def test_forbids_scratchpad_and_absolute_root_prefixing():
    assert "scratchpad" in CODE_REVIEW, (
        "must explicitly forbid prepending a scratchpad/sandbox/session root"
    )
    assert "two absolute paths" in CODE_REVIEW, (
        "must forbid joining two absolute paths"
    )


def test_json_documented_as_stdout():
    assert "stdout" in CODE_REVIEW, (
        "--json must be documented as emitting to stdout, not a file path"
    )
