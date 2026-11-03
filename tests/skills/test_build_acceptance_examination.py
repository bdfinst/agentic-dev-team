"""#2270 Slice 4 -- /build Step 7.6 runs the source-blind acceptance examination.

Prose-contract tests over `skills/build/SKILL.md` Step 7.6 and
`skills/build/references/acceptance-examination.md`. Each test asserts
observable text for one Slice 4 scenario; sections are extracted once by
heading, and heading order is read from heading positions, never from the
position of a substring in the whole file.
"""

from __future__ import annotations

import re
import sys
from functools import lru_cache

import pytest
from skill_doc_helpers import PLUGIN_ROOT, collapsed

sys.path.insert(0, str(PLUGIN_ROOT / "hooks" / "lib"))

import examination_inputs as ei

BUILD = PLUGIN_ROOT / "skills" / "build" / "SKILL.md"
REFERENCE = (
    PLUGIN_ROOT / "skills" / "build" / "references" / "acceptance-examination.md"
)

STEP_7 = "7. Final test quality score (branch)"
STEP_76 = "7.6. Acceptance examination"
STEP_75 = "7.5. Assemble the evidence bundle"
STEP_8 = "8. Update plan status"

HARD_STOP = "do not proceed to /pr"
VERDICT_WORDS = ("not-met", "indeterminate", "tainted", "missing")
FORBIDDEN_IN_TEMPLATE = ("git diff", "code-review", "review-value", "evidence bundle")


def _step_headings(text: str) -> list[tuple[int, str]]:
    """(line index, heading text) for every `### ` heading outside code fences."""
    found: list[tuple[int, str]] = []
    in_fence = False
    for index, line in enumerate(text.splitlines()):
        if line.startswith("```"):
            in_fence = not in_fence
        elif not in_fence and line.startswith("### "):
            found.append((index, line[4:].strip()))
    return found


def _step_section(text: str, heading: str) -> str:
    """The raw text of the step whose heading is exactly `### <heading>`."""
    lines = text.splitlines()
    headings = _step_headings(text)
    matches = [i for i, (_, name) in enumerate(headings) if name == heading]
    assert len(matches) == 1, f"expected exactly one '### {heading}' heading"
    start = headings[matches[0]][0]
    following = [at for at, _ in headings if at > start]
    next_h2 = [
        i for i, line in enumerate(lines) if i > start and line.startswith("## ")
    ]
    end = min(following + next_h2 + [len(lines)])
    return "\n".join(lines[start:end])


@lru_cache(maxsize=1)
def _skill_text() -> str:
    return BUILD.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _step_raw() -> str:
    return _step_section(_skill_text(), STEP_76)


def _step() -> str:
    return collapsed(_step_raw())


@lru_cache(maxsize=1)
def _reference_text() -> str:
    return REFERENCE.read_text(encoding="utf-8")


def _template_block() -> str:
    """The first four-backtick fenced block in the reference: the prompt template."""
    match = re.search(
        r"^````[^\n]*\n(.*?)\n````$", _reference_text(), re.MULTILINE | re.DOTALL
    )
    assert match, "reference has no four-backtick template block"
    return match.group(1)


def _bullets(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("- ")]


def _verdict_bullet(text: str, word: str) -> str:
    matches = [b for b in _bullets(text) if b.startswith(f"- `{word}`")]
    assert len(matches) == 1, f"expected one hard-stop bullet for {word!r}"
    return matches[0]


# --- Step 7.6 scenarios -----------------------------------------------------


def test_step_sits_between_farley_score_and_evidence_bundle() -> None:
    names = [name for _, name in _step_headings(_skill_text())]
    assert names.index(STEP_76) == names.index(STEP_7) + 1
    assert names.index(STEP_75) == names.index(STEP_76) + 1


def test_step_runs_every_invocation_and_skips_dispatch_on_met_or_exempt_plan() -> None:
    step = _step()
    assert (
        "runs on every /build invocation, including a re-run of a fully checked plan"
        in step
    )
    assert "acceptance_examination.py status" in step
    assert "skip dispatch when it exits zero" in step
    assert "Examination: not-applicable" in step


def test_step_states_dispatch_conditions_per_status_outcome() -> None:
    step = _step()
    assert "exactly once when status exits 1" in step
    assert "never when status exits 0" in step
    assert "never retries after a dispatch" in step


def test_clean_tree_check_exempts_the_plan_file() -> None:
    step = _step()
    assert "no tracked changes outside the plan file" in step
    assert "commit first" in step
    assert "lists the dirty paths" in step


def test_step_dispatches_the_examiner_once_with_progress_line_and_reference() -> None:
    step = _step()
    assert "acceptance-examiner" in step
    assert "subagent_type" in step
    assert "at most once per invocation" in step
    progress = (
        "Examining N criteria with run commands only; this can take several minutes."
    )
    assert progress in step
    assert step.index(progress) < step.index("subagent_type")
    assert "references/acceptance-examination.md" in step


def test_step_reads_the_record_back_renders_it_and_stops_on_failure() -> None:
    step = _step()
    assert "exit 1 for any reason → dispatch once" in step
    assert "status --wait 15" in step
    assert "render only when status reports a readable record for this plan" in step
    assert "print the status message" in step
    assert HARD_STOP in step
    assert "reinstall the plugin" in step
    assert "missing-plan-marker" in step
    assert "render" in step
    assert "continue to Step 7.5" in step


def test_failing_verdict_is_a_hard_stop_with_one_bullet_per_verdict() -> None:
    step = _step()
    assert "the plan's **Status** line is not modified" in step
    for word in VERDICT_WORDS:
        bullet = _verdict_bullet(_step_raw(), word)
        assert HARD_STOP in bullet, f"{word} bullet lacks the hard-stop phrase"


def test_step_never_offers_a_waiver() -> None:
    assert "waive" not in _step_raw().lower()


def test_step_8_heading_comes_only_after_step_7_5() -> None:
    names = [name for _, name in _step_headings(_skill_text())]
    assert names.count(STEP_8) == 1
    assert names.index(STEP_8) > names.index(STEP_75)


def test_missing_dispatch_capability_stops_the_step() -> None:
    step = _step()
    assert "**Dispatch-capability gate (re-confirm here — issue #1461).**" in step
    assert "STOP per the Orchestrator constraints above" in step


# --- Reference scenarios ----------------------------------------------------


def test_template_is_the_inputs_output_verbatim_plus_cwd_and_allowed_sentence() -> None:
    fixture = ei.ExaminationInputs(
        criteria=["<criterion 1 text>", "<criterion 2 text>"],
        gherkin=["<gherkin block for a slice>"],
        run_commands=["<run command 1>", "<run command 2>"],
    )
    verbatim = ei.render_inputs(fixture, "<plan>")
    block = _template_block()
    assert block.endswith(verbatim)
    assert "Working directory: <cwd>" in block.removesuffix(verbatim)


def test_template_contains_the_exported_marker_prefix() -> None:
    assert ei.PLAN_MARKER_PREFIX in _template_block()


def test_template_restates_the_allowed_contract() -> None:
    allowed = collapsed(_template_block().split("Working directory:")[0])
    assert "run the listed commands from the working directory" in allowed
    assert "read their output and `.feature` files" in allowed
    assert "nothing else" in allowed


@pytest.mark.parametrize("forbidden", FORBIDDEN_IN_TEMPLATE)
def test_template_leaks_nothing_the_examiner_must_not_see(forbidden: str) -> None:
    assert forbidden not in _template_block()


def test_reference_pre_dispatch_table_skips_a_current_record_and_dispatches_once() -> (
    None
):
    ref = collapsed(_reference_text())
    assert "exit 0" in ref
    assert "exit 1 for any reason → dispatch once" in ref


def test_reference_post_dispatch_table_covers_met_failed_and_absent() -> None:
    ref = collapsed(_reference_text())
    assert "status --wait 15" in ref
    assert "print the status message" in ref
    assert "reinstall the plugin" in ref
    assert "missing-plan-marker" in ref


def test_reference_hard_stop_has_one_bullet_per_verdict() -> None:
    for word in VERDICT_WORDS:
        bullet = _verdict_bullet(_reference_text(), word)
        assert HARD_STOP in bullet, f"{word} bullet lacks the hard-stop phrase"


def test_absent_after_dispatch_text_is_identical_in_step_and_reference() -> None:
    absent = (
        "No examination record was written after the examiner stopped. Likely causes: "
        "the SubagentStop recorder is not installed (reinstall the plugin), or the "
        "dispatch prompt lacked the marker line (see "
        ".claude/metrics/boundary-events.jsonl, rule missing-plan-marker). "
        "Fix the cause, then run: /build <plan>."
    )
    assert absent in _step()
    assert absent in collapsed(_reference_text())


# --- Evidence bundle scenario (Step 4.2) ------------------------------------

BUNDLE = PLUGIN_ROOT / "knowledge" / "evidence-bundle.md"
CHECKS_RUN_PINS = ("acceptance_examination.py status", "overall verdict")
RESIDUAL_RISKS_PINS = ("tainted", "Examination: not-applicable")


def _step_75_bullet(label: str) -> str:
    """The Step 7.5 bullet that starts `- **<label>**`, through its continuation lines."""
    lines = _step_section(_skill_text(), STEP_75).splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith(f"- **{label}**")]
    assert len(starts) == 1, f"expected one '{label}' bullet in Step 7.5"
    end = next(
        (i for i in range(starts[0] + 1, len(lines)) if not lines[i].startswith("  ")),
        len(lines),
    )
    return collapsed("\n".join(lines[starts[0] : end]))


def _bundle_row(section: str) -> str:
    """The fixed-sections table row of evidence-bundle.md for `section`."""
    rows = [
        line
        for line in BUNDLE.read_text(encoding="utf-8").splitlines()
        if line.startswith(f"| {section} |")
    ]
    assert len(rows) == 1, f"expected one '{section}' table row"
    return collapsed(rows[0])


@pytest.mark.parametrize("pin", CHECKS_RUN_PINS)
def test_step_75_checks_run_lists_the_examination(pin: str) -> None:
    assert pin in _step_75_bullet("Checks run")


@pytest.mark.parametrize("pin", RESIDUAL_RISKS_PINS)
def test_step_75_residual_risks_names_examination_sources(pin: str) -> None:
    assert pin in _step_75_bullet("Residual risks")


@pytest.mark.parametrize("pin", CHECKS_RUN_PINS)
def test_bundle_checks_run_row_lists_the_examination(pin: str) -> None:
    assert pin in _bundle_row("Checks run")


@pytest.mark.parametrize("pin", RESIDUAL_RISKS_PINS)
def test_bundle_residual_risks_row_names_examination_sources(pin: str) -> None:
    assert pin in _bundle_row("Residual risks")


# --- /pr and /fix refusal scenario (Step 4.3) -------------------------------

PR_SKILL = PLUGIN_ROOT / "skills" / "pr" / "SKILL.md"
FIX_SKILL = PLUGIN_ROOT / "skills" / "fix" / "SKILL.md"
REFUSAL_PINS = ("acceptance examination", "/build <plan>")


def _block_containing(path, anchor: str, offset: int = 0) -> str:
    """The blank-line-separated block holding `anchor`, or the one `offset` after it."""
    blocks = path.read_text(encoding="utf-8").split("\n\n")
    hits = [i for i, block in enumerate(blocks) if anchor in block]
    assert len(hits) == 1, f"expected exactly one block containing {anchor!r}"
    return collapsed(blocks[hits[0] + offset])


def _pr_gate_text() -> str:
    """The paragraph right after the `--pre-pr` command block in /pr."""
    return _block_containing(PR_SKILL, 'progress_guardian.py" --pre-pr', offset=1)


def _fix_gate_text() -> str:
    """The /fix paragraph that names the `--pre-pr` plan-completion gate as a stop."""
    return _block_containing(FIX_SKILL, "(`progress_guardian.py --pre-pr`)")


@pytest.mark.parametrize("pin", REFUSAL_PINS)
def test_pr_gate_text_names_the_examination_refusal(pin: str) -> None:
    assert pin in _pr_gate_text()


@pytest.mark.parametrize("pin", REFUSAL_PINS)
def test_fix_gate_text_names_the_examination_refusal(pin: str) -> None:
    assert pin in _fix_gate_text()
