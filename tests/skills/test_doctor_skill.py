"""Content guards for the /doctor skill and its registration (issue #2272,
Slice 3). The skill is a mechanical wrapper: these tests pin the shim
invocation, the verbatim exit sentences, the check ids and the registry and
help rows, so a wording drift cannot change what the model is told to do.
"""

from __future__ import annotations

import re
import sys

import pytest
from skill_doc_helpers import (
    PLUGIN_ROOT,
    collapsed,
    fenced_blocks,
    frontmatter,
    section,
)
from skill_doc_helpers import frontmatter_fields as parse_frontmatter_fields

SKILL_MD = PLUGIN_ROOT / "skills" / "doctor" / "SKILL.md"
REGISTRY_MD = PLUGIN_ROOT / "knowledge" / "skills-registry.md"
HELP_MD = PLUGIN_ROOT / "skills" / "help" / "SKILL.md"

_SCRIPTS = str(PLUGIN_ROOT / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)
# The shipped script is the oracle for the check order and the fix texts: the
# skill must describe what `doctor.py` really runs, not a copy kept in the test.
import doctor

COMMAND = "/doctor"
CHECK_IDS = (
    "plugin-version",
    "hook-registration",
    "interpreter",
    "python-floor",
    "required-tools",
    "optional-tools",
    "metrics-writable",
    "project-settings",
    "managed-sections",
)
SHIM_INVOCATION = (
    'sh "$CLAUDE_PLUGIN_ROOT/hooks/py.sh" '
    '"$CLAUDE_PLUGIN_ROOT/scripts/doctor.py" $ARGUMENTS'
)
ARGUMENTS_LINE = "Arguments: $ARGUMENTS"
EXIT_SENTENCES = (
    "Exit 0: print stdout verbatim, then stderr if it is not empty.",
    (
        "Exit 1: a diagnosis, not a tool error: print stdout verbatim, "
        "then stderr if it is not empty, and do not retry."
    ),
    "Exit 2: print stderr verbatim.",
)
WARN_ROWS_SENTENCE = "warn rows do not fail the run"
CLOSING_SENTENCE = "Do not add commentary beyond the script's output."
HELP_ROW = (
    "| `/doctor` | Diagnose the plugin install and this repo's dev-team configuration |"
)
# The example pins the script's own layout, so the indent comes from the shipped
# report module rather than a copy kept here.
FIX_INDENT = doctor._model().FIX_INDENT


@pytest.fixture(scope="module")
def skill_text() -> str:
    return SKILL_MD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def frontmatter_fields(skill_text: str) -> dict[str, str]:
    return parse_frontmatter_fields(skill_text)


@pytest.fixture(scope="module")
def body(skill_text: str) -> str:
    return skill_text[len(frontmatter(skill_text)) :]


@pytest.fixture(scope="module")
def collapsed_body(body: str) -> str:
    return collapsed(body)


@pytest.fixture(scope="module")
def registry_text() -> str:
    return REGISTRY_MD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def help_text() -> str:
    return HELP_MD.read_text(encoding="utf-8")


def _row(text: str, command: str) -> tuple[int, str]:
    """The single table row whose first cell is `command`: (line index, line)."""
    prefix = f"| `{command}` |"
    rows = [
        (index, line)
        for index, line in enumerate(text.splitlines())
        if line.startswith(prefix)
    ]
    if not rows:
        pytest.fail(f"no table row starting {prefix!r}")
    assert len(rows) == 1, f"{len(rows)} rows start {prefix!r}"
    return rows[0]


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("name", "doctor"),
        ("argument-hint", "[--json] [--fix]"),
        ("user-invocable", "true"),
        ("allowed-tools", "Bash"),
    ],
)
def test_frontmatter_field_is_pinned(frontmatter_fields, field, expected):
    assert frontmatter_fields.get(field) == expected


def test_description_is_non_empty_and_colon_free(frontmatter_fields):
    description = frontmatter_fields.get("description", "")

    assert description, "description is missing or empty"
    assert ":" not in description, f"colon in description: {description!r}"


def test_check_ids_match_the_scripts_check_order():
    assert CHECK_IDS == tuple(check_id for check_id, _ in doctor._checks().CHECKS)


def test_only_bash_block_is_the_shim_invocation(skill_text):
    assert [block.strip() for block in fenced_blocks(skill_text, "bash")] == [
        SHIM_INVOCATION
    ]


def test_body_passes_arguments_through(collapsed_body):
    assert ARGUMENTS_LINE in collapsed_body


@pytest.mark.parametrize("flag", ["--json", "--fix", "--project"])
def test_body_flags_section_opens_a_bullet_for_each_flag(body, flag):
    flags = section(body, r"^## Flags", boundary_pattern=r"^## ")

    assert re.search(rf"^- `{re.escape(flag)}[` ]", flags, re.MULTILINE), (
        f"no bullet opening with {flag} in the Flags section"
    )


@pytest.mark.parametrize("sentence", EXIT_SENTENCES, ids=["exit-0", "exit-1", "exit-2"])
def test_body_exit_sentence_is_verbatim(collapsed_body, sentence):
    assert sentence in collapsed_body


def test_body_states_warn_rows_do_not_fail_the_run(collapsed_body):
    assert WARN_ROWS_SENTENCE in collapsed_body


def test_body_checks_section_lists_the_ids_in_script_order(body):
    checks_section = section(body, r"^## Checks", boundary_pattern=r"^## ")

    listed = re.findall(r"^\d+\. `([^`]+)`", checks_section, re.MULTILINE)

    assert listed == list(CHECK_IDS)


def test_body_example_matches_the_script_row_order_and_fix_layout(body):
    blocks = fenced_blocks(body, "text")
    assert len(blocks) == 1, f"expected one text example, found {len(blocks)}"
    example = blocks[0]
    checks_module = doctor._checks()

    row_ids = re.findall(r"^(?:ok|warn|fail)\s+(\S+)", example, re.MULTILINE)
    fix_lines = [
        line for line in example.splitlines() if line.strip().startswith("fix:")
    ]

    assert row_ids == list(CHECK_IDS), "example rows differ from the check order"
    assert f"fix: {checks_module.DOCTOR_FIX}" in example, "no command-shaped fix"
    assert f"fix: {checks_module.FLOOR_FIX}" in example, "no sentence-shaped fix"
    assert fix_lines, "example has no fix lines"
    assert all(line.startswith(FIX_INDENT + "fix:") for line in fix_lines), (
        f"fix lines are not indented {len(FIX_INDENT)} spaces: {fix_lines}"
    )


def test_body_ends_with_the_closing_sentence(skill_text):
    last = [line for line in skill_text.splitlines() if line.strip()][-1]

    assert last == CLOSING_SENTENCE


def test_registry_row_precedes_upgrade_with_frontmatter_description(
    registry_text, frontmatter_fields
):
    index, line = _row(registry_text, COMMAND)
    upgrade_index, _ = _row(registry_text, "/upgrade")

    assert line == (
        f"| `{COMMAND}` | `skills/doctor/SKILL.md` | worker |"
        f" {frontmatter_fields['description']} |"
    )
    assert index + 1 == upgrade_index, "/doctor is not directly before /upgrade"


def test_help_row_follows_setup(help_text):
    index, line = _row(help_text, COMMAND)
    setup_index, _ = _row(help_text, "/setup")

    assert line == HELP_ROW
    assert index == setup_index + 1, "/doctor is not directly after /setup"
