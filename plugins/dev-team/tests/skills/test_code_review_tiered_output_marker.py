"""Content guard for code-review/SKILL.md + output-format.md's tiered
findings wiring (#2170 Step 3.2).

`render_tiered_findings.py` (Step 3.1) is only useful once `/code-review`
step 7's prose-mode path actually calls it instead of listing each finding's
full message inline, and once `--expand` is a documented, user-facing flag.
This module pins three things mechanically:

1. `--expand <finding-id>|all` is documented in the Parse Arguments table.
2. Step 7's prose-mode path (only) is wired to `render_tiered_findings.py`,
   and states the `--json`/`corrections/` non-interference guarantee —
   including the `--expand`-under-`--json` no-op rule — explicitly.
3. The golden-file proof required by the plan: `/code-review` has no
   standalone script that builds the aggregated `--json` object or
   `./corrections/*.json` for the non-sliced path (steps 5/7/8 are prose in
   SKILL.md, executed by the orchestrating agent in-context, not a callable
   Python module — `consolidate.py` only serves sliced-mode aggregation, a
   different code path entirely). There is therefore nothing to invoke
   before/after this change and diff byte-for-byte. Per the task's own
   fallback instruction, the mechanical proof here is content-guard level
   instead: the `--json` branch (step 7) and step 8's corrections-writing
   text contain zero references to `render_tiered_findings.py` and zero
   references to `--expand` -- i.e. nothing in this change touches the code
   *path* those branches describe, and no flag combination involving
   `--expand` can alter what either branch does. `--json --expand <id>`
   therefore renders identically to plain `--json` by construction, not by
   inspection of output bytes that don't exist to compare.
"""

from __future__ import annotations

import sys

from _repo_root import REPO_ROOT

sys.path.insert(
    0,
    str(REPO_ROOT / "plugins" / "dev-team" / "skills" / "code-review" / "scripts"),
)

import render_tiered_findings as rtf

SKILL = REPO_ROOT / "plugins" / "dev-team" / "skills" / "code-review" / "SKILL.md"
OUTPUT_FORMAT = (
    REPO_ROOT / "plugins" / "dev-team" / "skills" / "code-review" / "output-format.md"
)

_PARSE_ARGS_HEADING = "## Parse Arguments"
_STEP_7_HEADING = "### 7. Generate report"
_STEP_8_HEADING = "### 8. Save correction prompts for remaining issues"
_STEP_9_HEADING = "### 9. Write pre-commit gate file"
_PROSE_BRANCH_MARKER = "Otherwise (no `--json`):"


def _skill_text() -> str:
    return SKILL.read_text(encoding="utf-8")


def _section(text: str, start: str, end: str) -> str:
    assert start in text, f"heading not found: {start!r}"
    after = text.split(start, 1)[1]
    assert end in after, f"heading not found after {start!r}: {end!r}"
    return after.split(end, 1)[0]


def _parse_arguments_section() -> str:
    text = _skill_text()
    return _section(text, _PARSE_ARGS_HEADING, "## Progress tracking")


def _step_7_section() -> str:
    text = _skill_text()
    return _section(text, _STEP_7_HEADING, _STEP_8_HEADING)


def _step_8_section() -> str:
    text = _skill_text()
    return _section(text, _STEP_8_HEADING, _STEP_9_HEADING)


def _step_7_json_branch() -> str:
    """Step 7's `--json` branch only -- everything before the prose-mode
    marker. This is the text `/pr --json` and any other `--json` caller's
    behavior is governed by."""
    section = _step_7_section()
    assert _PROSE_BRANCH_MARKER in section
    return section.split(_PROSE_BRANCH_MARKER, 1)[0]


def _step_7_prose_branch() -> str:
    section = _step_7_section()
    assert _PROSE_BRANCH_MARKER in section
    return section.split(_PROSE_BRANCH_MARKER, 1)[1]


# --- 1. --expand documented in Parse Arguments -----------------------------


def test_expand_flag_documented_in_parse_arguments_table() -> None:
    section = _parse_arguments_section()
    assert "`--expand <finding-id>|all`" in section
    assert "Tier-2" in section
    assert "no-op under `--json`" in section


def test_expand_flag_in_argument_hint_frontmatter() -> None:
    text = _skill_text()
    frontmatter = text.split("---", 2)[1]
    assert "--expand" in frontmatter


# --- 2. Step 7 prose-mode path wired to render_tiered_findings.py ----------


def test_prose_branch_invokes_render_tiered_findings_script() -> None:
    prose = _step_7_prose_branch()
    assert "render_tiered_findings.py" in prose
    assert "--expand" in prose


def test_prose_branch_passes_expand_through_unchanged() -> None:
    prose = _step_7_prose_branch()
    assert "Pass `--expand` through exactly as the caller supplied it" in prose


def test_prose_branch_handles_unknown_expand_id() -> None:
    prose = _step_7_prose_branch()
    assert "finding-id not found" in prose


# --- 3. Explicit --json / corrections/ non-interference statement ----------


def test_skill_states_json_and_corrections_are_untouched() -> None:
    prose = _step_7_prose_branch()
    assert "Scope of this wiring: the prose-mode path only." in prose
    assert "already read and write the full finding objects independently" in prose
    assert "neither branch calls `render_tiered_findings.py`" in prose


def test_skill_states_expand_is_a_noop_under_json() -> None:
    prose = _step_7_prose_branch()
    assert "**`--expand` is a no-op under `--json`**" in prose
    assert "must never call `render_tiered_findings.py`" in prose
    assert "enforced structurally" in prose


# --- 4. Golden-file-equivalent proof: --json branch and step 8 untouched ---


def test_json_branch_never_mentions_render_tiered_findings() -> None:
    """The `--json` branch (this step's other branch) must never call into
    the tiered-rendering script -- this is what makes `--expand` a no-op
    under `--json` *structurally*, not by a flag check anywhere."""
    json_branch = _step_7_json_branch()
    assert "render_tiered_findings" not in json_branch


def test_json_branch_never_mentions_expand() -> None:
    """No reference to `--expand` anywhere in the `--json` branch's own
    text -- proof by construction that `--json --expand <id>` and plain
    `--json` are governed by the exact same branch text, hence identical
    output, since there is no unconsumed script or callable module for this
    non-sliced path to diff byte-for-byte (see module docstring)."""
    json_branch = _step_7_json_branch()
    assert "--expand" not in json_branch


def test_json_branch_still_states_json_is_the_only_stdout_output() -> None:
    """Pin that this step's pre-existing `--json` contract text survived
    this change unweakened."""
    json_branch = _step_7_json_branch()
    assert "the JSON object is the ONLY thing printed to stdout" in json_branch
    assert "non-negotiable" in json_branch


def test_step_8_never_mentions_render_tiered_findings_or_expand() -> None:
    """Step 8 (`./corrections/*.json`) is untouched by this change: no
    reference to the tiered-rendering script or to `--expand` anywhere in
    its text."""
    step_8 = _step_8_section()
    assert "render_tiered_findings" not in step_8
    assert "--expand" not in step_8


def test_step_8_still_skips_entirely_under_json() -> None:
    step_8 = _step_8_section()
    assert "Skip this entire step if `--json` was set." in step_8


# --- output-format.md: tiered shape is the new canonical template ----------


def test_output_format_shows_tier1_example_using_real_expand_hint_constant() -> None:
    """Tie the doc's example directly to the script's own `EXPAND_HINT`
    constant, rather than a hand-typed string that could silently drift
    from the actual rendered output."""
    text = OUTPUT_FORMAT.read_text(encoding="utf-8")
    assert rtf.EXPAND_HINT in text


def test_output_format_names_clean_pass_summary_behavior() -> None:
    text = OUTPUT_FORMAT.read_text(encoding="utf-8")
    assert "CLEAN_PASS_SUMMARY" in text
    assert "render_tiered_findings.py" in text


def test_output_format_states_json_and_corrections_unaffected() -> None:
    text = OUTPUT_FORMAT.read_text(encoding="utf-8")
    section = text.split("## Code Review Summary report", 1)[1]
    assert "no-op under `--json`" in section
    assert "corrections/*.json" in section
