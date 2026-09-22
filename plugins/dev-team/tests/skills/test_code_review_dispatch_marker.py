"""Content checks for code-review/SKILL.md step 4's dispatch-prompt scope
marker (#2166 Step 2.1).
"""

from __future__ import annotations

import sys

from _repo_root import REPO_ROOT

_LIB_DIR = REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from review_verdicts import SCOPE_MARKER_PREFIX

SKILL = REPO_ROOT / "plugins" / "dev-team" / "skills" / "code-review" / "SKILL.md"

_SECTION_MARKER = "### 4. Run each enabled agent"


def _dispatch_section() -> str:
    text = SKILL.read_text(encoding="utf-8")
    assert _SECTION_MARKER in text, "step 4 heading not found"
    section = text.split(_SECTION_MARKER, 1)[1].split("\n### ", 1)[0]
    return section


def test_dispatch_section_declares_scope_marker_template() -> None:
    section = _dispatch_section()
    assert "Files in scope for this review: <path>, <path>, ..." in section, (
        "step 4 is missing the dispatch-prompt scope marker template"
    )


def test_dispatch_section_marker_prose_uses_shared_prefix_constant() -> None:
    section = _dispatch_section()
    assert SCOPE_MARKER_PREFIX in section, (
        "step 4's marker prose has drifted from review_verdicts.SCOPE_MARKER_PREFIX"
    )


def _render_marker_line(files: list[str]) -> str:
    """Render a dispatch-prompt marker line the way SKILL.md step 4 describes:
    SCOPE_MARKER_PREFIX followed by the comma-separated in-scope file list.
    """
    return SCOPE_MARKER_PREFIX + ", ".join(files)


def _parse_marker_line(line: str) -> list[str]:
    """Local, throwaway extraction for this step's round-trip test only.

    Step 2.3 owns the real parser (reading it out of a subagent transcript);
    this is not that parser, just a same-format check that renderer output
    is machine-parseable via the shared SCOPE_MARKER_PREFIX constant.
    """
    assert line.startswith(SCOPE_MARKER_PREFIX), "line missing scope marker prefix"
    remainder = line[len(SCOPE_MARKER_PREFIX) :]
    return remainder.split(", ")


def test_marker_round_trip_recovers_identical_file_list() -> None:
    files = ["src/foo.py", "src/bar/baz.py", "tests/test_foo.py"]

    dispatch_prompt = (
        "Review the following files for correctness issues.\n\n"
        f"{_render_marker_line(files)}\n\n"
        "Return findings per the standard output contract."
    )

    marker_line = next(
        line
        for line in dispatch_prompt.splitlines()
        if line.startswith(SCOPE_MARKER_PREFIX)
    )
    recovered = _parse_marker_line(marker_line)

    assert recovered == files
