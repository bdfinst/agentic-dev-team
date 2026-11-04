"""Doc-shape contract for the `--candidates` and `--max-cost-usd` flags in
build/SKILL.md.

Pins what `/build` documents about the two flags: the `argument-hint`, the two
Parse Arguments bullets, the validation paragraph (the `validate-flags` call,
its stop messages and the speculative-dispatch print lines), and the Step 1
sentence that prints the count. Script resolution is checked mechanically:
every `python3 "${CLAUDE_PLUGIN_ROOT}/..."` call in Parse Arguments must name
a file under the plugin root, and every flag named for `build_candidates.py
validate-flags` must appear in its real `--help`. The `docs/skills.md` row is
checked against the frontmatter it is generated from. Step 4 routes `complex`
steps to the speculative-build skill through one routing paragraph placed
immediately before the single-dispatch paragraph; the default text (the
`trivial` and `standard` bullets and the single-dispatch paragraph) stays
pinned verbatim by `fixtures/build_skill_untouched_passages.md`.
"""

from __future__ import annotations

import functools
import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from skill_doc_helpers import (
    PLUGIN_ROOT,
    Fact,
    assert_fact,
    collapsed,
    frontmatter,
    grep,
    parse_arguments_section,
    section,
    section_outside_code,
)

SKILL = PLUGIN_ROOT / "skills" / "build" / "SKILL.md"
SKILLS_DOC = PLUGIN_ROOT / "docs" / "skills.md"

HELP_TIMEOUT_SECONDS = 60
HELP_CHECKED_SCRIPT = "scripts/build_candidates.py"
HELP_CHECKED_SUBCOMMAND = "validate-flags"
EXPECTED_INVOCATIONS = {
    ("scripts/build_candidates.py", "validate-flags"),
    ("scripts/build_worktree_baseref.py", "detect"),
}

CANDIDATES_BULLET_START = r"^- `--candidates N`:"
MAX_COST_BULLET_START = r"^- `--max-cost-usd X`:"
BULLET_BOUNDARY = r"^(- |$)"
VALIDATION_START = r"^Validate the speculative flags"
VALIDATION_BOUNDARY = r"^\*\*Interactivity\.\*\*"

#: A shipped-script call: the script path under the plugin root, then the rest
#: of the line (subcommand and flags).
_INVOCATION_RE = re.compile(r'python3 "\$\{CLAUDE_PLUGIN_ROOT\}/([^"]+)"(.*)$')

STOP_NO_TRANSCRIPT = (
    "`--candidates needs the session transcript to enforce --max-cost-usd; "
    "none located — run without --candidates`"
)
STOP_BAD_BASEREF = (
    "`--candidates needs worktree.baseRef = head (detected: <value>); "
    "set it in .claude/settings.json or run without --candidates`"
)
PRINT_WITH_COMPLEX_STEPS = (
    "`speculative dispatch: <n> complex step(s) will use <N> candidates "
    "under a $<X> cap; other steps run as normal`"
)
VALIDATE_FLAGS_CALL = (
    'build_candidates.py" validate-flags --candidates=<raw> '
    "--max-cost-usd=<raw> --jobs=<raw>"
)
SPECULATIVE_TRANSCRIPT_CHECK = (
    'When the printed JSON has `"speculative": true`, locate the session transcript'
)
STEP_1_PRINT = (
    "print the `speculative dispatch:` line defined there once the plan is found."
)
PRINT_NO_COMPLEX_STEPS = (
    "`speculative dispatch: no complex steps in this plan; --candidates has no effect`"
)

UNTOUCHED_FIXTURE = (
    Path(__file__).parent / "fixtures" / "build_skill_untouched_passages.md"
)
STEP_4_START = r"^### 4\. Implement each step$"
STEP_4_BOUNDARY = r"^### "
ROUTING_START = "**Speculative dispatch (#2273).**"
SINGLE_DISPATCH_START = "For each step within a slice, dispatch"
TRIVIAL_BULLET_START = "- **trivial**:"
STANDARD_BULLET_START = "- **standard**:"
COMPLEX_BULLET_START = "- **complex**:"
#: H2 headings of the fixture, in file order; each heads one fenced passage.
FIXTURE_PASSAGES = (
    "trivial bullet",
    "standard bullet",
    "single-dispatch paragraph",
)
FIXTURE_FENCE = "~~~~"
#: Padding that pushes the routing paragraph past 200 words (Gherkin tolerance).
LONG_PARAGRAPH_WORDS = 200
LONG_PARAGRAPH_PADDING = 120
#: First line of the per-behavior cycle in Step 4.
PER_BEHAVIOR_CYCLE_START_LINE = "1. **First phase"
#: First line after the per-behavior cycle in Step 4; the moved pair goes before it.
PER_BEHAVIOR_CYCLE_END_LINE = "5. **Mark step done**"
#: The default text must name neither word (case-insensitive).
DEFAULT_TEXT_FORBIDDEN = ("candidates", "speculative")
#: Phrases the routing paragraph states. Each is a regex run against the
#: whitespace-collapsed paragraph. "exactly as below" is the pinned wording for
#: "every other step runs unchanged".
ROUTING_PHRASES = (
    ("names_the_flag", r"`--candidates N`"),
    (
        "ties_the_trigger_to_the_printed_speculative_flag",
        r'Parse Arguments printed `"speculative": true`',
    ),
    ("conditions_on_n_at_least_2", r"(?<![\w-])N ≥ 2(?!\d)"),
    ("conditions_on_complexity_being_complex", r"`\*\*Complexity\*\*` is `complex`"),
    ("names_the_skill", r"speculative-build/SKILL\.md"),
    (
        "runs_self_verification_on_the_merged_winner_first",
        r"Run sub-step 3's self-verification on the merged winner first, then resume",
    ),
    (
        "resumes_at_the_inline_checkpoint_on_the_merged_winner",
        r"sub-step 4's inline checkpoint on the merged winner",
    ),
    (
        "runs_cleanup_after_the_checkpoint_passes",
        r"Cleanup.* after that checkpoint passes",
    ),
    (
        "runs_every_other_step_exactly_as_below",
        r"Every other step, and every step when N = 1, runs exactly as below",
    ),
)


def _bullet(start: str) -> Callable[[str], str]:
    """The bullet that starts with `start`, wherever it sits in Parse Arguments."""
    return lambda text: section(
        parse_arguments_section(text), start, boundary_pattern=BULLET_BOUNDARY
    )


def _validation_paragraph(text: str) -> str:
    return section(
        parse_arguments_section(text),
        VALIDATION_START,
        boundary_pattern=VALIDATION_BOUNDARY,
    )


def _step_1(text: str) -> str:
    return section_outside_code(
        text, r"^### 1\. Find the plan$", boundary_pattern=r"^### "
    )


def _complex_checkpoint(text: str) -> str:
    """The `complex` bullet of Step 4's inline-review sub-step."""
    return _line_starting(_step_4(text), COMPLEX_BULLET_START)


#: Keys ending in `_bullet` are Parse Arguments bullets; the bullet-swap test
#: selects their Facts by that suffix.
SECTIONS: dict[str, Callable[[str], str]] = {
    "frontmatter": frontmatter,
    "candidates_bullet": _bullet(CANDIDATES_BULLET_START),
    "max_cost_bullet": _bullet(MAX_COST_BULLET_START),
    "validation": _validation_paragraph,
    "step_1": _step_1,
    "complex_checkpoint": _complex_checkpoint,
}

FACTS = [
    # --candidates N bullet
    Fact(
        "candidates_bullet_says_experimental",
        "candidates_bullet",
        required=((r"\*\*experimental\*\*", True),),
    ),
    Fact(
        "candidates_bullet_limits_it_to_complex_steps",
        "candidates_bullet",
        literal_required=(
            "Applies only to steps whose `**Complexity**` is `complex`.",
        ),
    ),
    Fact(
        "candidates_bullet_bounds_n_between_1_and_8",
        "candidates_bullet",
        literal_required=("N is between 1 and 8.",),
    ),
    Fact(
        "candidates_bullet_says_1_is_the_unchanged_build",
        "candidates_bullet",
        literal_required=("1 is the unchanged build.",),
    ),
    Fact(
        "candidates_bullet_says_the_cap_bounds_dispatch_not_screening",
        "candidates_bullet",
        literal_required=("cap bounds candidate dispatch spend, not screening.",),
    ),
    Fact(
        "candidates_bullet_says_the_cap_is_checked_between_batches",
        "candidates_bullet",
        literal_required=(
            "The skill checks the cap between batches, so one batch may overrun it.",
        ),
    ),
    Fact(
        "candidates_bullet_points_at_the_speculative_build_skill",
        "candidates_bullet",
        literal_required=("`skills/speculative-build/SKILL.md`",),
    ),
    Fact(
        "candidates_bullet_says_batches_follow_the_skills_concurrency_not_jobs",
        "candidates_bullet",
        literal_required=(
            (
                "Candidate batches follow speculative-build's own concurrency "
                "(`DEV_TEAM_MAX_PARALLEL_BUILDS`, not `--jobs`)."
            ),
        ),
    ),
    Fact(
        "candidates_bullet_says_the_cap_bounds_one_step",
        "candidates_bullet",
        literal_required=(
            (
                "The cap bounds one step; a wave with W speculative steps may spend "
                "W times the cap."
            ),
        ),
    ),
    # --max-cost-usd X bullet
    Fact(
        "max_cost_bullet_is_required_with_n_at_least_2",
        "max_cost_bullet",
        literal_required=("Required with N ≥ 2.",),
    ),
    Fact(
        "max_cost_bullet_names_a_dollar_spend_cap",
        "max_cost_bullet",
        literal_required=("The step's speculative spend cap in dollars.",),
    ),
    # validation paragraph
    Fact(
        "validation_runs_validate_flags_with_the_three_equals_flags",
        "validation",
        literal_required=(VALIDATE_FLAGS_CALL,),
    ),
    Fact(
        "validation_explains_the_equals_form_and_omitted_flags",
        "validation",
        literal_required=(
            "so a value that begins with `-` reaches the validator instead of argparse.",
            "Omit a flag the user did not pass.",
        ),
    ),
    Fact(
        "validation_runs_before_step_0",
        "validation",
        literal_required=("Validate the speculative flags before Step 0.",),
    ),
    Fact(
        "validation_prints_stderr_and_stops_on_exit_2",
        "validation",
        literal_required=("On exit 2, print its stderr and stop.",),
    ),
    Fact(
        "validation_checks_the_transcript_and_baseref_head_when_speculative",
        "validation",
        literal_required=(
            SPECULATIVE_TRANSCRIPT_CHECK,
            'build_worktree_baseref.py" detect`, which must print `head`.',
        ),
    ),
    Fact(
        "validation_stops_before_step_0_with_the_no_transcript_message",
        "validation",
        literal_required=(STOP_NO_TRANSCRIPT, "stop before Step 0"),
    ),
    Fact(
        "validation_stops_before_step_0_with_the_baseref_message",
        "validation",
        literal_required=(STOP_BAD_BASEREF,),
    ),
    Fact(
        "validation_prints_the_complex_step_count_line_after_step_1",
        "validation",
        literal_required=(
            PRINT_WITH_COMPLEX_STEPS,
            "after Step 1 finds the plan",
            "Count n as the steps in the plan whose `**Complexity**` is `complex`.",
        ),
    ),
    Fact(
        "validation_prints_the_no_effect_line_when_n_is_0",
        "validation",
        literal_required=("When n is 0, print " + PRINT_NO_COMPLEX_STEPS,),
    ),
    # sub-step 4, complex bullet
    Fact(
        "complex_checkpoint_runs_the_skills_cleanup_once_it_passes",
        "complex_checkpoint",
        literal_required=(
            "run speculative-build's `## Cleanup` once this checkpoint passes.",
        ),
    ),
    # Step 1
    Fact(
        "step_1_prints_the_speculative_dispatch_line_once_the_plan_is_found",
        "step_1",
        literal_required=(STEP_1_PRINT,),
    ),
]


@pytest.fixture(scope="module")
def skill_text() -> str:
    return SKILL.read_text(encoding="utf-8")


@pytest.mark.parametrize("fact", FACTS, ids=[f.id for f in FACTS])
def test_build_skill_documents_the_candidates_flags(skill_text, fact):
    assert_fact(SECTIONS, skill_text, fact)


def test_facts_pass_when_the_two_bullets_swap_places(skill_text):
    candidates = next(
        line for line in skill_text.splitlines() if grep(CANDIDATES_BULLET_START, line)
    )
    max_cost = next(
        line for line in skill_text.splitlines() if grep(MAX_COST_BULLET_START, line)
    )
    placeholder = "\x00"
    swapped = (
        skill_text.replace(candidates, placeholder)
        .replace(max_cost, candidates)
        .replace(placeholder, max_cost)
    )
    assert swapped != skill_text
    bullet_facts = [f for f in FACTS if f.section.endswith("_bullet")]
    assert bullet_facts
    for fact in bullet_facts:
        assert_fact(SECTIONS, swapped, fact)


def test_argument_hint_names_both_flags(skill_text):
    hint = next(
        line
        for line in frontmatter(skill_text).splitlines()
        if line.startswith("argument-hint:")
    )
    assert "[--candidates N]" in hint
    assert "[--max-cost-usd X]" in hint


def test_skills_doc_build_row_shows_the_argument_hint(skill_text):
    hint = next(
        line
        for line in frontmatter(skill_text).splitlines()
        if line.startswith("argument-hint:")
    )
    hint = hint.removeprefix("argument-hint:").strip().strip('"')
    row = next(
        line
        for line in SKILLS_DOC.read_text(encoding="utf-8").splitlines()
        if line.startswith("| `/build` |")
    )
    assert f"| {hint} |" in row


def _invocations(text: str) -> list[tuple[str, str, tuple[str, ...]]]:
    """`(script path under the plugin root, subcommand, long flags)` for each
    `python3 "${CLAUDE_PLUGIN_ROOT}/..."` call in Parse Arguments."""
    found = []
    for line in parse_arguments_section(text).splitlines():
        for script, rest in _INVOCATION_RE.findall(line):
            words = rest.split()
            first = words[0] if words else ""
            subcommand = "" if first.startswith(("-", "<", "`")) else first.strip("`.,")
            flags = tuple(re.findall(r"(?<![\w-])(--[a-z][a-z-]*)", rest))
            found.append((script, subcommand, flags))
    return found


INVOCATIONS = _invocations(SKILL.read_text(encoding="utf-8"))


@functools.cache
def _help_text(script: str, subcommand: str) -> str:
    # Python 3.14 argparse colours its help output; plain text is what we match.
    env = {k: v for k, v in os.environ.items() if k != "FORCE_COLOR"}
    env["NO_COLOR"] = "1"
    result = subprocess.run(
        [sys.executable, str(PLUGIN_ROOT / script), subcommand, "--help"],
        capture_output=True,
        text=True,
        timeout=HELP_TIMEOUT_SECONDS,
        check=False,
        env=env,
    )
    assert result.returncode == 0, f"{script} {subcommand} --help: {result.stderr}"
    return result.stdout


def _invocation_id(invocation: tuple[str, str, tuple[str, ...]]) -> str:
    script, subcommand, flags = invocation
    return f"{script.rsplit('/', 1)[-1]}-{subcommand or 'nosub'}-{'-'.join(flags)}"


def test_parse_arguments_adds_the_two_expected_script_calls():
    assert {(script, sub) for script, sub, _ in INVOCATIONS} == EXPECTED_INVOCATIONS


@pytest.mark.parametrize("invocation", INVOCATIONS, ids=_invocation_id)
def test_every_script_parse_arguments_invokes_exists_under_the_plugin_root(invocation):
    assert (PLUGIN_ROOT / invocation[0]).is_file()


@pytest.mark.parametrize(
    "invocation",
    [
        i
        for i in INVOCATIONS
        if (i[0], i[1]) == (HELP_CHECKED_SCRIPT, HELP_CHECKED_SUBCOMMAND)
    ],
    ids=_invocation_id,
)
def test_every_flag_named_for_validate_flags_is_listed_by_its_help(invocation):
    script, subcommand, flags = invocation
    assert flags, f"{script} {subcommand} names no flags"
    help_text = _help_text(script, subcommand)
    missing = [
        flag
        for flag in flags
        if not re.search(rf"(?<![\w-]){re.escape(flag)}(?![\w-])", help_text)
    ]
    assert not missing, f"{script} {subcommand} --help does not list {missing}"


def _step_4(text: str) -> str:
    return section_outside_code(text, STEP_4_START, boundary_pattern=STEP_4_BOUNDARY)


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def _line_starting(text: str, prefix: str) -> str:
    matches = [line for line in text.splitlines() if line.lstrip().startswith(prefix)]
    assert len(matches) == 1, f"expected one line starting {prefix!r}: {matches}"
    return matches[0]


def _single_dispatch_paragraph(text: str) -> str:
    """The single-dispatch paragraph of Step 4, as a whole paragraph."""
    starts = [
        p for p in _paragraphs(_step_4(text)) if p.startswith(SINGLE_DISPATCH_START)
    ]
    assert len(starts) == 1, f"expected one single-dispatch paragraph: {len(starts)}"
    return starts[0]


def _routing_paragraph(text: str) -> str:
    """The paragraph immediately before the single-dispatch paragraph (blank lines
    only between them). Position within Step 4 is deliberately not asserted."""
    paragraphs = _paragraphs(_step_4(text))
    starts = [
        i for i, p in enumerate(paragraphs) if p.startswith(SINGLE_DISPATCH_START)
    ]
    assert len(starts) == 1, f"expected one single-dispatch paragraph: {len(starts)}"
    assert starts[0] > 0, "nothing precedes the single-dispatch paragraph"
    return paragraphs[starts[0] - 1]


def test_step_4_has_one_routing_paragraph(skill_text):
    paragraphs = _paragraphs(_step_4(skill_text))
    assert sum(p.startswith(ROUTING_START) for p in paragraphs) == 1


def test_routing_paragraph_is_immediately_before_the_single_dispatch_paragraph(
    skill_text,
):
    assert _routing_paragraph(skill_text).startswith(ROUTING_START)


@pytest.mark.parametrize(
    "pattern", [p for _, p in ROUTING_PHRASES], ids=[i for i, _ in ROUTING_PHRASES]
)
def test_routing_paragraph_states(skill_text, pattern):
    assert re.search(pattern, collapsed(_routing_paragraph(skill_text)))


def test_routing_paragraph_states_the_checkpoint_before_the_cleanup(skill_text):
    paragraph = collapsed(_routing_paragraph(skill_text))
    checkpoint = paragraph.find("inline checkpoint on the merged winner")
    cleanup = paragraph.find("## Cleanup")
    assert checkpoint >= 0, "the paragraph does not name the inline checkpoint"
    assert cleanup >= 0, "the paragraph does not name `## Cleanup`"
    assert checkpoint < cleanup, "the paragraph names the Cleanup before the checkpoint"


def _missing_routing_phrases(paragraph: str) -> list[str]:
    paragraph = collapsed(paragraph)
    return [i for i, pattern in ROUTING_PHRASES if not re.search(pattern, paragraph)]


def _pair_moved_after_the_cycle(skill_text: str, routing: str) -> str:
    """`skill_text` with the routing and single-dispatch paragraphs moved to
    after the per-behavior cycle (before `PER_BEHAVIOR_CYCLE_END_LINE`), the
    routing text replaced by `routing`."""
    original = _routing_paragraph(skill_text)
    dispatch = _single_dispatch_paragraph(skill_text)
    pair = f"{original}\n\n{dispatch}\n\n"
    assert pair in skill_text, (
        "routing and single-dispatch paragraphs are not separated by one blank line"
    )
    end = PER_BEHAVIOR_CYCLE_END_LINE
    return skill_text.replace(pair, "", 1).replace(
        end, f"\n{routing}\n\n{dispatch}\n\n{end}", 1
    )


def _assert_routing_survives_the_move(moved: str, routing: str) -> None:
    dispatch = _single_dispatch_paragraph(moved)
    assert moved.index(dispatch) > moved.index(PER_BEHAVIOR_CYCLE_START_LINE), (
        "the pair did not move after the per-behavior cycle"
    )
    assert _routing_paragraph(moved) == routing
    missing = _missing_routing_phrases(_routing_paragraph(moved))
    assert not missing, missing


def test_routing_checks_hold_when_the_pair_follows_the_per_behavior_cycle(skill_text):
    routing = _routing_paragraph(skill_text)
    moved = _pair_moved_after_the_cycle(skill_text, routing)
    _assert_routing_survives_the_move(moved, routing)


def test_routing_checks_hold_when_the_routing_paragraph_exceeds_200_words(skill_text):
    routing = _routing_paragraph(skill_text)
    longer = (routing + " " + "Extra words. " * LONG_PARAGRAPH_PADDING).strip()
    assert len(longer.split()) > LONG_PARAGRAPH_WORDS
    moved = _pair_moved_after_the_cycle(skill_text, longer)
    _assert_routing_survives_the_move(moved, longer)


def _fixture_passages() -> dict[str, str]:
    """Parse the fixture by its H2 headings; each heading owns one fenced block."""
    passages: dict[str, str] = {}
    heading = None
    in_fence = False
    body: list[str] = []
    for line in UNTOUCHED_FIXTURE.read_text(encoding="utf-8").splitlines():
        if not in_fence and line.startswith("## "):
            heading = line.removeprefix("## ").strip()
        elif line == FIXTURE_FENCE:
            if in_fence:
                assert heading is not None
                passages[heading] = "\n".join(body)
                body = []
            in_fence = not in_fence
        elif in_fence:
            body.append(line)
    return passages


def _default_passages(text: str) -> dict[str, str]:
    step_4 = _step_4(text)
    return {
        "trivial bullet": _line_starting(step_4, TRIVIAL_BULLET_START),
        "standard bullet": _line_starting(step_4, STANDARD_BULLET_START),
        "single-dispatch paragraph": _single_dispatch_paragraph(text),
    }


def test_fixture_has_the_three_passages_under_their_headings():
    assert tuple(_fixture_passages()) == FIXTURE_PASSAGES


@pytest.mark.parametrize("name", FIXTURE_PASSAGES, ids=FIXTURE_PASSAGES)
def test_default_passage_names_neither_candidates_nor_speculative(skill_text, name):
    passage = _default_passages(skill_text)[name]
    assert passage.strip()
    for word in DEFAULT_TEXT_FORBIDDEN:
        assert word not in passage.lower(), f"{name} names {word!r}"


@pytest.mark.parametrize("name", FIXTURE_PASSAGES, ids=FIXTURE_PASSAGES)
def test_fixture_passage_is_present_verbatim_and_equals_the_extracted_passage(
    skill_text, name
):
    passage = _fixture_passages()[name]
    assert passage.strip(), f"fixture passage {name!r} is empty"
    assert passage in skill_text, f"{name} is no longer a substring of the skill"
    extracted = _default_passages(skill_text)[name]
    assert extracted.strip() == passage.strip(), f"{name} differs from the fixture"
