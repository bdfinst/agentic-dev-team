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
from collections.abc import Callable
from functools import cache, lru_cache
from pathlib import Path

import pytest
from skill_doc_helpers import PLUGIN_ROOT, collapsed

sys.path.insert(0, str(PLUGIN_ROOT / "hooks" / "lib"))
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))

import examination_gate as gate
import examination_inputs as ei

BUILD = PLUGIN_ROOT / "skills" / "build" / "SKILL.md"
REFERENCE = (
    PLUGIN_ROOT / "skills" / "build" / "references" / "acceptance-examination.md"
)
BUNDLE = PLUGIN_ROOT / "knowledge" / "evidence-bundle.md"
PR_SKILL = PLUGIN_ROOT / "skills" / "pr" / "SKILL.md"
FIX_SKILL = PLUGIN_ROOT / "skills" / "fix" / "SKILL.md"

STEP_7 = "7. Final test quality score (branch)"
STEP_76 = "7.6. Acceptance examination"
STEP_75 = "7.5. Assemble the evidence bundle"
STEP_8 = "8. Update plan status"

HARD_STOP = "do not proceed to /pr"
STOP_OUTCOMES = ("not-met", "indeterminate", "tainted", "missing")
FORBIDDEN_IN_TEMPLATE = ("git diff", "code-review", "review-value", "evidence bundle")
EXEMPT_FIELD = "**Examination**: not-applicable"
CANNOT_PREFIXES = (
    "Acceptance examination cannot be verified",
    "Acceptance examination cannot run",
)
ABSENT_PREFIX = "Acceptance examination missing"
DISPATCHED_AT = "DISPATCHED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
AFTER_COMMAND = "status --wait 15 --after $DISPATCHED_AT"
ABSENT_TEXT = (
    "No examination record was written after the examiner stopped. Likely causes: "
    "the SubagentStop recorder is not installed (reinstall the plugin), or the "
    "dispatch prompt lacked the marker line (see "
    ".claude/metrics/boundary-events.jsonl, rule missing-plan-marker). "
    "Fix the cause, then run: /build <plan>."
)
PLAN_AUTHOR_SENTENCE = "belong to the human plan author at the plan gate"
NEVER_REWORD_SENTENCE = "never add, remove, or reword them to clear a stop"
CHECKS_RUN_PINS = (
    "acceptance_examination.py status",
    "acceptance_examination.py show",
    "overall verdict",
)
RESIDUAL_RISKS_PINS = (EXEMPT_FIELD,)
REFUSAL_PINS = ("acceptance examination", "/build <plan>", EXEMPT_FIELD)


@cache
def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _skill_text() -> str:
    return _read_text(BUILD)


def _reference_text() -> str:
    return _read_text(REFERENCE)


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
def _step_76_raw() -> str:
    return _step_section(_skill_text(), STEP_76)


def _step_76() -> str:
    return collapsed(_step_76_raw())


def _template_block() -> str:
    """The first four-backtick fenced block in the reference: the prompt template."""
    match = re.search(
        r"^````[^\n]*\n(.*?)\n````$", _reference_text(), re.MULTILINE | re.DOTALL
    )
    assert match, "reference has no four-backtick template block"
    return match.group(1)


def _bullets(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("- ")]


def _stop_bullet(text: str, outcome: str) -> str:
    matches = [b for b in _bullets(text) if b.startswith(f"- `{outcome}`")]
    assert len(matches) == 1, f"expected one hard-stop bullet for {outcome!r}"
    return collapsed(matches[0])


def _hard_stop_paragraph(raw: str) -> str:
    """The text from the 'Hard stop' lead to the first bullet."""
    match = re.search(r"Hard stop\b(.*?)\n- ", raw, re.DOTALL)
    assert match, "no hard-stop paragraph"
    return collapsed(match.group(1))


def _numbered_item(number: int) -> str:
    """Raw lines of numbered item `number` of Step 7.6, with its sub-bullets."""
    lines: list[str] = []
    inside = False
    for line in _step_76_raw().splitlines():
        if re.match(rf"^{number}\. ", line):
            inside = True
        elif inside and not line.startswith("   "):
            break
        if inside:
            lines.append(line)
    assert lines, f"Step 7.6 has no numbered item {number}"
    return "\n".join(lines)


def _item_bullet(number: int, label: str) -> str:
    """The one sub-bullet of item `number` that starts `- <label>`."""
    matches = [
        collapsed(line)
        for line in _numbered_item(number).splitlines()
        if line.strip().startswith(f"- {label}")
    ]
    assert len(matches) == 1, f"expected one '{label}' bullet in item {number}"
    return matches[0]


def _reference_row(section: str, first_cell: str) -> str:
    """The one table row of reference section `section` whose first cell starts so."""
    rows = [
        collapsed(line)
        for line in _step_section(_reference_text(), section).splitlines()
        if line.startswith("| ")
        and line.strip("| ").split("|")[0].strip().startswith(first_cell)
    ]
    assert len(rows) == 1, f"expected one '{first_cell}' row in '{section}'"
    return rows[0]


# --- Step 7.6 scenarios -----------------------------------------------------


def test_step_sits_between_farley_score_and_evidence_bundle() -> None:
    names = [name for _, name in _step_headings(_skill_text())]
    assert names.index(STEP_76) == names.index(STEP_7) + 1
    assert names.index(STEP_75) == names.index(STEP_76) + 1


def test_orchestrator_constraints_count_the_examiner_dispatch() -> None:
    text = collapsed(_skill_text())
    assert "at four points" in text
    assert "and Step 7.6 (`acceptance-examiner` dispatch)" in text
    assert "at three points" not in text


def test_step_7_hands_over_to_step_7_6_not_step_8() -> None:
    step_7 = collapsed(_step_section(_skill_text(), STEP_7))
    assert "continue to Step 8" not in step_7
    assert "continue to Step 7.6" in step_7


def test_step_runs_every_invocation_and_names_the_exemption() -> None:
    step = _step_76()
    assert (
        "runs on every /build invocation, including a re-run of a fully checked plan"
        in step
    )
    assert "acceptance_examination.py status" in step
    assert EXEMPT_FIELD in step


def test_first_status_run_comes_before_any_dispatch() -> None:
    step = _step_76()
    assert step.index("acceptance_examination.py status") < step.index("subagent_type")


def test_exit_0_met_bullet_renders_and_continues_to_step_7_5() -> None:
    bullet = _item_bullet(1, "Exit 0, met record")
    assert "skip dispatch" in bullet
    assert "run `render`" in bullet
    assert "continue to Step 7.5" in bullet
    assert "later commit makes it stale" in bullet


def test_exit_0_exempt_bullet_skips_render_and_lists_the_exemption() -> None:
    bullet = _item_bullet(1, "Exit 0, the plan declares")
    assert EXEMPT_FIELD in bullet
    assert "Skip dispatch" in bullet
    assert "do not run `render`" in bullet
    assert "continue to Step 7.5" in bullet
    assert "evidence bundle lists the exemption" in bullet


def test_exit_1_with_a_cannot_message_stops_without_dispatch() -> None:
    bullet = _item_bullet(1, "Exit 1, message starts")
    for prefix in CANNOT_PREFIXES:
        assert prefix in bullet
    assert "print the message and stop" in bullet
    assert "Do not dispatch" in bullet


def test_cannot_prefixes_match_the_gate_and_exclude_the_tainted_message() -> None:
    base = gate.refusal_message(gate.RULE_BASE_UNRESOLVABLE, "plans/x.md")
    empty = gate.refusal_message(gate.RULE_EMPTY_DIFF, "plans/x.md")
    tainted = gate.refusal_message(gate.RULE_TAINTED, "plans/x.md", commands="cat a")
    assert base.startswith(CANNOT_PREFIXES[0])
    assert empty.startswith(CANNOT_PREFIXES[1])
    assert not tainted.startswith(CANNOT_PREFIXES)


def test_every_other_exit_1_reason_dispatches_once() -> None:
    assert "dispatch once" in _item_bullet(1, "Exit 1 for any other reason")


@pytest.mark.parametrize("number", [1, 5], ids=["pre-dispatch", "post-dispatch"])
def test_exit_2_bullet_prints_stderr_and_stops(number: int) -> None:
    bullet = _item_bullet(number, "Exit 2")
    assert "print stderr and stop" in bullet
    assert "not in a git repository" in bullet
    assert "no `render`" in bullet.lower()


def test_step_states_dispatch_conditions_per_status_outcome() -> None:
    step = _step_76()
    assert "exactly once when status exits 1" in step
    assert "never when status exits 0" in step
    assert "never retries after a dispatch" in step


def test_clean_tree_check_exempts_the_plan_file() -> None:
    step = _step_76()
    assert "no tracked changes and no non-ignored untracked files outside the plan file" in step
    assert "commit first" in step
    assert "lists the dirty paths" in step


def test_clean_tree_check_sees_untracked_files() -> None:
    step = _step_76()
    command = "`git status --porcelain --untracked-files=all -- ':(top,exclude)<plan>'`"
    assert command in step
    assert "an untracked file counts as dirty" in step
    row = _reference_row("Before dispatch", "exit 1 for any other reason")
    assert "an untracked file counts as dirty" in row
    assert "--untracked-files=all" in row


def test_clean_tree_check_and_capability_gate_come_before_dispatch() -> None:
    step = _step_76()
    dispatch = step.index("subagent_type")
    assert step.index("no tracked changes and no non-ignored untracked files outside the plan file") < dispatch
    assert step.index("Dispatch-capability gate") < dispatch


def test_step_dispatches_the_examiner_once_with_progress_line_and_reference() -> None:
    step = _step_76()
    assert "acceptance-examiner" in step
    assert "subagent_type" in step
    assert "at most once per invocation" in step
    progress = (
        "Examining N criteria with run commands only; this can take several minutes."
    )
    assert progress in step
    assert step.index(progress) < step.index("subagent_type")
    assert "references/acceptance-examination.md" in step


def test_inputs_failure_stops_before_dispatch() -> None:
    item = collapsed(_numbered_item(4))
    assert "If it exits non-zero" in item
    assert "print its stderr and stop" in item
    assert item.index("print its stderr and stop") < item.index("subagent_type")


def test_dispatch_time_is_recorded_before_the_dispatch() -> None:
    item = collapsed(_numbered_item(4))
    assert DISPATCHED_AT in item
    assert item.index(DISPATCHED_AT) < item.index("subagent_type")


def test_post_dispatch_status_ignores_a_record_older_than_the_dispatch() -> None:
    item = collapsed(_numbered_item(5))
    assert AFTER_COMMAND in item
    assert "A record older than the dispatch counts as absent" in item
    assert "render only when status reports a readable record for this plan" in item
    assert "If `render` exits non-zero, print its stderr and stop" in item


def test_exit_0_after_dispatch_renders_then_continues_to_step_7_5() -> None:
    bullet = _item_bullet(5, "Exit 0")
    assert "`render`" in bullet
    assert "continue to Step 7.5" in bullet


def test_exit_1_with_a_readable_record_renders_prints_and_stops() -> None:
    bullet = _item_bullet(5, "Exit 1 with a readable record")
    assert "`render`" in bullet
    assert "print the status message" in bullet
    assert "and stop" in bullet


def test_unreadable_or_other_plan_record_is_not_rendered() -> None:
    bullet = _item_bullet(5, "Exit 1, record unreadable or for another plan")
    assert "do not run `render`" in bullet
    assert "print the status message" in bullet
    assert "and stop" in bullet


def test_absent_bullet_is_recognised_by_prefix_and_prints_the_recorder_text() -> None:
    bullet = _item_bullet(5, "Exit 1, no record (absent)")
    assert ABSENT_PREFIX in bullet
    assert ABSENT_TEXT in bullet
    assert "reinstall the plugin" in bullet
    assert "missing-plan-marker" in bullet


def test_absent_prefix_is_the_gate_missing_message() -> None:
    message = gate.refusal_message(gate.RULE_MISSING, "plans/x.md", path="p.json")
    assert message.startswith(ABSENT_PREFIX)


def test_hard_stop_paragraph_keeps_the_status_line_and_skips_step_8() -> None:
    paragraph = _hard_stop_paragraph(_step_76_raw())
    assert "the plan's **Status** line is not modified" in paragraph
    assert "Step 8 is not reached" in paragraph
    assert "`acceptance_examination.py status`" in paragraph
    assert "as in Step 5" not in paragraph


@pytest.mark.parametrize("outcome", STOP_OUTCOMES)
@pytest.mark.parametrize(
    "raw",
    [_step_76_raw, _reference_text],
    ids=["step-7-6", "reference"],
)
def test_hard_stop_has_one_bullet_per_outcome(
    raw: Callable[[], str], outcome: str
) -> None:
    assert HARD_STOP in _stop_bullet(raw(), outcome).lower()


@pytest.mark.parametrize(
    "raw", [_step_76_raw, _reference_text], ids=["step-7-6", "reference"]
)
def test_indeterminate_bullet_splits_unobservable_from_incomplete(
    raw: Callable[[], str],
) -> None:
    bullet = _stop_bullet(raw(), "indeterminate")
    assert "or its result was incomplete or malformed" in bullet
    assert "Unobservable: make the criterion observable in the plan" in bullet
    assert (
        "Incomplete result: run `/build <plan>` again without changing the plan"
        in bullet
    )


@pytest.mark.parametrize(
    "raw", [_step_76_raw, _reference_text], ids=["step-7-6", "reference"]
)
def test_missing_bullet_points_at_the_recorder_text_not_the_status_message(
    raw: Callable[[], str],
) -> None:
    bullet = _stop_bullet(raw(), "missing")
    assert "(status absent)" in bullet
    assert "absent-after-dispatch text" in bullet
    assert "the cause the status message names" not in bullet


@pytest.mark.parametrize(
    "raw", [_step_76_raw, _reference_text], ids=["step-7-6", "reference"]
)
def test_plan_author_owns_the_exemption_and_criterion_edits(
    raw: Callable[[], str],
) -> None:
    text = collapsed(raw())
    assert f"The `{EXEMPT_FIELD}` header and any criterion edit" in text
    assert PLAN_AUTHOR_SENTENCE in text
    assert "`/build` and `/fix` " + NEVER_REWORD_SENTENCE in text


@pytest.mark.parametrize(
    "raw", [_step_76_raw, _reference_text], ids=["step-7-6", "reference"]
)
def test_prose_never_offers_a_waiver(raw: Callable[[], str]) -> None:
    assert "waive" not in raw().lower()


@pytest.mark.parametrize(
    "raw", [_step_76_raw, _reference_text], ids=["step-7-6", "reference"]
)
def test_prose_uses_words_not_arrows(raw: Callable[[], str]) -> None:
    assert "→" not in raw()


@pytest.mark.parametrize(
    "raw", [_step_76_raw, _reference_text], ids=["step-7-6", "reference"]
)
def test_examination_field_is_written_in_its_bold_form(raw: Callable[[], str]) -> None:
    unbolded = re.findall(r"(?<!\*\*)Examination: not-applicable", raw())
    assert unbolded == []


def test_step_8_heading_comes_only_after_step_7_5() -> None:
    names = [name for _, name in _step_headings(_skill_text())]
    assert names.count(STEP_8) == 1
    assert names.index(STEP_8) > names.index(STEP_75)


def test_missing_dispatch_capability_stops_the_step() -> None:
    step = _step_76()
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
    assert forbidden not in _template_block().lower()


def test_reference_exit_0_met_row_skips_dispatch_and_renders() -> None:
    row = _reference_row("Before dispatch", "exit 0, met record")
    assert "Skip dispatch" in row
    assert "`render`" in row
    assert "continue to Step 7.5" in row


def test_reference_exit_0_exempt_row_skips_dispatch_and_render() -> None:
    row = _reference_row("Before dispatch", "exit 0, plan declares")
    assert EXEMPT_FIELD in row
    assert "Skip dispatch" in row
    assert "Do not run `render`" in row


def test_reference_cannot_row_stops_without_dispatch() -> None:
    row = _reference_row("Before dispatch", "exit 1, message starts")
    for prefix in CANNOT_PREFIXES:
        assert prefix in row
    assert "Do not dispatch" in row


def test_reference_other_exit_1_row_dispatches_once() -> None:
    row = _reference_row("Before dispatch", "exit 1 for any other reason")
    assert "Dispatch once" in row


@pytest.mark.parametrize("section", ["Before dispatch", "After dispatch"])
def test_reference_exit_2_rows_print_stderr_and_stop(section: str) -> None:
    row = _reference_row(section, "exit 2")
    assert "Print stderr and stop" in row
    assert "not in a git repository" in row
    assert "`render`" in row


def test_reference_inputs_failure_and_dispatch_time_are_stated() -> None:
    ref = collapsed(_step_section(_reference_text(), "Before dispatch"))
    assert "If `inputs` exits non-zero" in ref
    assert "print its stderr and stop" in ref
    assert DISPATCHED_AT in ref


def test_reference_post_dispatch_uses_after_and_treats_old_records_as_absent() -> None:
    ref = collapsed(_step_section(_reference_text(), "After dispatch"))
    assert AFTER_COMMAND in ref
    assert "A record older than the dispatch counts as absent" in ref
    assert "Do not dispatch again" in ref


def test_reference_post_dispatch_met_row_renders_and_continues() -> None:
    row = _reference_row("After dispatch", "exit 0")
    assert "Run `render`" in row
    assert "continue to Step 7.5" in row


def test_reference_post_dispatch_readable_failure_row_renders_prints_and_stops() -> (
    None
):
    row = _reference_row("After dispatch", "exit 1 with a readable record")
    assert "Run `render`" in row
    assert "print the status message" in row
    assert "stop" in row


def test_reference_unreadable_or_other_plan_row_is_not_rendered() -> None:
    row = _reference_row("After dispatch", "exit 1, record unreadable or for another")
    assert "Do not run `render`" in row
    assert "Print the status message" in row


def test_reference_absent_row_is_recognised_by_prefix() -> None:
    row = _reference_row("After dispatch", "exit 1, no record (absent)")
    assert ABSENT_PREFIX in row
    assert "absent-after-dispatch text" in row


def test_reference_post_dispatch_mentions_the_recorder_causes() -> None:
    ref = collapsed(_reference_text())
    assert "reinstall the plugin" in ref
    assert "missing-plan-marker" in ref


def test_reference_has_no_in_short_repetition_of_the_hard_stop() -> None:
    assert "In short" not in _reference_text()


def test_absent_after_dispatch_text_is_identical_in_step_and_reference() -> None:
    assert ABSENT_TEXT in _step_76()
    assert ABSENT_TEXT in collapsed(_reference_text())


# --- Evidence bundle scenario (Step 4.2) ------------------------------------


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
        for line in _read_text(BUNDLE).splitlines()
        if line.startswith(f"| {section} |")
    ]
    assert len(rows) == 1, f"expected one '{section}' table row"
    return collapsed(rows[0])


def _step_75_checks_run() -> str:
    return _step_75_bullet("Checks run")


def _step_75_residual_risks() -> str:
    return _step_75_bullet("Residual risks")


def _bundle_checks_run() -> str:
    return _bundle_row("Checks run")


def _bundle_residual_risks() -> str:
    return _bundle_row("Residual risks")


@pytest.mark.parametrize(
    ("extract", "pins"),
    [
        pytest.param(_step_75_checks_run, CHECKS_RUN_PINS, id="step-7-5-checks-run"),
        pytest.param(_bundle_checks_run, CHECKS_RUN_PINS, id="bundle-checks-run"),
        pytest.param(
            _step_75_residual_risks, RESIDUAL_RISKS_PINS, id="step-7-5-residual-risks"
        ),
        pytest.param(
            _bundle_residual_risks, RESIDUAL_RISKS_PINS, id="bundle-residual-risks"
        ),
    ],
)
def test_evidence_bundle_sources_name_the_examination(
    extract: Callable[[], str], pins: tuple[str, ...]
) -> None:
    text = extract()
    assert [pin for pin in pins if pin not in text] == []


@pytest.mark.parametrize(
    "extract",
    [_step_75_checks_run, _bundle_checks_run],
    ids=["step-7-5", "bundle"],
)
def test_checks_run_reads_the_verdict_from_show_not_status(
    extract: Callable[[], str],
) -> None:
    text = extract()
    assert "acceptance_examination.py show --plan <plan>" in text
    assert "`overall`" in text


@pytest.mark.parametrize(
    "extract",
    [_step_75_residual_risks, _bundle_residual_risks],
    ids=["step-7-5", "bundle"],
)
def test_residual_risks_omits_tainted_records_which_are_a_hard_stop(
    extract: Callable[[], str],
) -> None:
    assert "tainted" not in extract()


def test_bundle_lists_the_examination_among_verifiers_and_build_outputs() -> None:
    bundle = collapsed(_read_text(BUNDLE))
    assert "Farley score, acceptance examination (Step 7.6)" in bundle
    assert "Step 5, 6, 7, and 7.6 outputs" in bundle


# --- /pr and /fix refusal scenario (Step 4.3) -------------------------------


def _block_containing(path: Path, anchor: str, offset: int = 0) -> str:
    """The blank-line-separated block holding `anchor`, or the one `offset` after it."""
    blocks = _read_text(path).split("\n\n")
    hits = [i for i, block in enumerate(blocks) if anchor in block]
    assert len(hits) == 1, f"expected exactly one block containing {anchor!r}"
    return collapsed(blocks[hits[0] + offset])


def _pr_gate_text() -> str:
    """The paragraph right after the `--pre-pr` command block in /pr."""
    return _block_containing(PR_SKILL, 'progress_guardian.py" --pre-pr', offset=1)


def _fix_gate_text() -> str:
    """The /fix paragraph that names the `--pre-pr` plan-completion gate as a stop."""
    return _block_containing(FIX_SKILL, "(`progress_guardian.py --pre-pr`)")


GATE_TEXTS = [
    pytest.param(_pr_gate_text, id="pr"),
    pytest.param(_fix_gate_text, id="fix"),
]


@pytest.mark.parametrize("gate_text", GATE_TEXTS)
@pytest.mark.parametrize("pin", REFUSAL_PINS)
def test_gate_text_names_the_examination_refusal(
    gate_text: Callable[[], str], pin: str
) -> None:
    assert pin in gate_text()


def test_pr_gate_text_covers_an_examination_refusal_with_all_steps_ticked() -> None:
    text = _pr_gate_text()
    assert "an acceptance-examination refusal with all steps `[x]`" in text
