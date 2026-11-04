"""Doc-shape contract for the `--candidates` and `--max-cost-usd` flags in
build/SKILL.md.

Pins what `/build` documents about the two flags: the `argument-hint`, the two
Parse Arguments bullets, the validation paragraph (the `validate-flags` call,
its stop messages and the speculative-dispatch print lines), and the Step 1
sentence that prints the count. Script resolution is checked mechanically:
every `python3 "${CLAUDE_PLUGIN_ROOT}/..."` call in Parse Arguments must name
a file under the plugin root, and every flag named for `build_candidates.py
validate-flags` must appear in its real `--help`. The `docs/skills.md` row is
checked against the frontmatter it is generated from.
"""

from __future__ import annotations

import functools
import os
import re
import subprocess
import sys
from collections.abc import Callable

import pytest
from skill_doc_helpers import (
    PLUGIN_ROOT,
    Fact,
    assert_fact,
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


SECTIONS: dict[str, Callable[[str], str]] = {
    "frontmatter": frontmatter,
    "candidates_bullet": _bullet(CANDIDATES_BULLET_START),
    "max_cost_bullet": _bullet(MAX_COST_BULLET_START),
    "validation": _validation_paragraph,
    "step_1": _step_1,
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
            "It is checked between batches, so one batch may overrun it.",
        ),
    ),
    Fact(
        "candidates_bullet_points_at_the_speculative_build_skill",
        "candidates_bullet",
        literal_required=("`skills/speculative-build/SKILL.md`",),
    ),
    # --max-cost-usd X bullet
    Fact(
        "max_cost_bullet_is_required_with_two_or_more_candidates",
        "max_cost_bullet",
        literal_required=("Required with N of 2 or more.",),
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
