"""Contract tests for the shared helpers in skill_doc_helpers.py that more
than one skill-doc test file relies on."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import skill_doc_helpers
from skill_doc_helpers import (
    INVOCATION_RE,
    PLUGIN_ROOT,
    flag_listed_in_help,
    h2_section,
    headings_outside_code,
    help_text,
)


@pytest.mark.parametrize(
    ("text", "level", "expected"),
    [
        ("# a\n```\n## fake\n```\n## y\n", 2, ["y"]),
        ("# a\n```\n# fake\n```\n## y\n", 1, ["a"]),
        ("```text\n## fake\n```\n", 2, []),
    ],
    ids=["fenced_h2_ignored", "fenced_h1_ignored", "only_fenced"],
)
def test_headings_outside_code_skips_fenced_lines(text, level, expected):
    assert headings_outside_code(text, level) == expected


def test_section_stays_open_across_a_fenced_h2_line():
    text = "## A\nbody\n```\n## fake\ninside\n```\ntail\n## B\nother\n"
    body = h2_section(text, "A")
    assert "inside" in body
    assert "tail" in body
    assert "other" not in body


def test_h2_section_excludes_its_own_heading_and_stops_at_the_next_h2():
    text = "## A\nin A\n### sub\nstill A\n## B\nin B\n"
    assert h2_section(text, "A") == "in A\n### sub\nstill A"


def test_h2_section_matches_the_whole_heading_not_a_prefix():
    assert h2_section("## Report extra\nbody\n", "Report") == ""


def test_h2_section_treats_the_name_as_a_regex():
    text = "## Decision rule (pre-registered)\nbody\n## Next\n"
    assert h2_section(text, r"Decision rule \(pre-registered.*\)?") == "body"


@pytest.mark.parametrize(
    ("line", "script", "rest"),
    [
        (
            'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/x.py" run --flag',
            "scripts/x.py",
            " run --flag",
        ),
        (
            '`python3 "${CLAUDE_PLUGIN_ROOT}/hooks/lib/y.py"` then',
            "hooks/lib/y.py",
            "` then",
        ),
    ],
    ids=["plain", "inline-code"],
)
def test_invocation_re_splits_the_script_path_from_the_rest_of_the_line(
    line, script, rest
):
    assert INVOCATION_RE.search(line).groups() == (script, rest)


def test_invocation_re_ignores_a_call_that_is_not_under_the_plugin_root():
    assert INVOCATION_RE.search('python3 "scripts/x.py" run') is None


def test_flag_listed_in_help_matches_a_whole_option_name():
    assert flag_listed_in_help("--cost-usd", "  --cost-usd COST_USD  dollars")


def test_flag_listed_in_help_rejects_a_prefix_of_a_longer_option():
    assert not flag_listed_in_help("--cost", "  --cost-usd COST_USD  dollars")


def test_flag_listed_in_help_rejects_a_flag_glued_to_extra_dashes():
    assert not flag_listed_in_help("--cost-usd", "  ---cost-usd COST_USD  dollars")


def test_help_text_runs_the_script_with_the_subcommand_and_returns_its_help():
    out = help_text("scripts/build_candidates.py", "validate-flags")
    assert "--max-cost-usd" in out


def test_help_text_without_a_subcommand_returns_the_top_level_help():
    out = help_text("scripts/build_candidates.py")
    assert "validate-flags" in out
    assert "--max-cost-usd" not in out


def test_help_text_asks_for_plain_text_even_when_colour_is_forced(monkeypatch):
    """Python 3.14 argparse colours its help; older interpreters never do, so
    the request is checked at the process boundary rather than in the output."""
    seen = {}

    def fake_run(_command, **kwargs):
        seen.update(kwargs["env"])
        return SimpleNamespace(returncode=0, stdout="help", stderr="")

    monkeypatch.setenv("FORCE_COLOR", "1")
    monkeypatch.setattr(skill_doc_helpers.subprocess, "run", fake_run)
    help_text.cache_clear()
    try:
        help_text("scripts/probe-colour.py")
    finally:
        help_text.cache_clear()
    assert "FORCE_COLOR" not in seen
    assert seen["NO_COLOR"] == "1"


def test_help_text_fails_for_a_script_without_help():
    script = "scripts/does_not_exist.py"
    assert not (PLUGIN_ROOT / script).exists()
    with pytest.raises(AssertionError, match="does_not_exist.py"):
        help_text(script)
