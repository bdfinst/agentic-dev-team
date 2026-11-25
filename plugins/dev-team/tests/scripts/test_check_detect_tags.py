"""Tests for scripts/check_detect_tags.py.

Each case writes a small agent file under tmp_path and runs the checker's
``main`` on it, asserting the exit code and the printed message.
"""

import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from check_detect_tags import EXIT_BAD_INPUT, EXIT_INVALID, RULE_IDS_PATH, main

SHIPPED_RULE_IDS = SCRIPTS_DIR.parent / "templates" / "eslint" / "rule-ids.json"

VALID_BULLET = "Flags `var` declarations [MECHANICAL] rule: no-var"

# `_agent` writes "# Agent", a blank line, "## Detect", a blank line, then the bullets.
FIRST_BULLET_LINE = 5
SECOND_BULLET_LINE = FIRST_BULLET_LINE + 1

# The rule ids every test but the shipped-file ones resolves against, so a change to the
# shipped rule-ids.json cannot change what these cases mean.
FIXTURE_ENABLED = ["no-var", "no-plusplus", "prefer-const"]
FIXTURE_PLANNED = ["max-depth"]


def _agent(tmp_path: Path, *bullets: str, name: str = "agent.md") -> Path:
    """Write an agent file whose Detect section holds ``bullets``, one per line."""
    body = "\n".join(f"- {b}" for b in bullets)
    path = tmp_path / name
    path.write_text(
        f"# Agent\n\n## Detect\n\n{body}\n\n## Output\n\nNothing.\n", encoding="utf-8"
    )
    return path


def _rule_ids(tmp_path: Path, enabled=(), planned=(), convertible=()) -> str:
    path = tmp_path / "rule-ids.json"
    path.write_text(
        json.dumps(
            {
                "enabled": list(enabled),
                "planned": list(planned),
                "convertible": list(convertible),
            }
        ),
        encoding="utf-8",
    )
    return str(path)


@pytest.fixture
def ids(tmp_path) -> str:
    return _rule_ids(tmp_path, FIXTURE_ENABLED, FIXTURE_PLANNED)


def _run(path: Path, capsys, ids: str) -> tuple[int, str]:
    code = main([str(path), "--rule-ids", ids])
    return code, capsys.readouterr().out


def _assert_failure_message(out: str, path: Path, line: int, text: str) -> None:
    assert f"{path}:{line} {text}" in out
    assert "[JUDGMENT]" in out
    assert "rule: <id>" in out


# Each row is (bullet, reason fragment the message must carry).
FAILING_BULLETS = [
    pytest.param("[MECHANICAL] no mapping", "no 'rule: <id>'", id="unmapped"),
    pytest.param("[MECHANICAL] no rule:", "at least 3 words", id="empty-reason"),
    pytest.param("[MECHANICAL] no rule: n/a", "at least 3 words", id="one-word-reason"),
    pytest.param(
        "[MECHANICAL] no rule: needs graph", "at least 3 words", id="two-word-reason"
    ),
    pytest.param(
        "ESLint rule: no-var suppressed inline [MECHANICAL]",
        "no 'rule: <id>'",
        id="rule-in-prose-before-tag",
    ),
    pytest.param(
        "Prose no rule: at all here [MECHANICAL]",
        "no 'rule: <id>'",
        id="no-rule-in-prose-before-tag",
    ),
    pytest.param(
        "no rule: needs graph [MECHANICAL]",
        "no 'rule: <id>'",
        id="two-word-reason-before-tag",
    ),
    pytest.param(
        "no rule: needs call graph [MECHANICAL]",
        "no 'rule: <id>'",
        id="three-word-reason-before-tag",
    ),
    pytest.param(
        "[MECHANICAL] rule: not-a-real-rule",
        "unknown rule id not-a-real-rule",
        id="unknown-id",
    ),
    pytest.param(
        "[mechanical] rule: no-var", "no [MECHANICAL] or [JUDGMENT] tag", id="mis-cased"
    ),
    pytest.param(
        "[JUDGEMENT] needs a human",
        "no [MECHANICAL] or [JUDGMENT] tag",
        id="misspelled",
    ),
    pytest.param("[MECHANICAL] [JUDGMENT] rule: no-var", "2 tags", id="two-tags"),
    pytest.param(
        "untagged bullet text", "no [MECHANICAL] or [JUDGMENT] tag", id="untagged"
    ),
]


@pytest.mark.parametrize(("bullet", "reason"), FAILING_BULLETS)
def test_malformed_or_unmapped_bullet_fails_with_location_and_fixes(
    tmp_path, capsys, ids, bullet, reason
):
    path = _agent(tmp_path, bullet)

    code, out = _run(path, capsys, ids)

    assert code == EXIT_INVALID
    _assert_failure_message(out, path, FIRST_BULLET_LINE, bullet)
    assert reason in out


def test_failure_reports_the_line_of_the_offending_bullet(tmp_path, capsys, ids):
    path = _agent(tmp_path, VALID_BULLET, "untagged bullet text")

    code, out = _run(path, capsys, ids)

    assert code == EXIT_INVALID
    assert f"{path}:{SECOND_BULLET_LINE} untagged bullet text" in out
    assert f"{path}:{FIRST_BULLET_LINE}" not in out


def test_valid_mapped_bullet_added_beside_a_failing_one_does_not_clear_it(
    tmp_path, capsys, ids
):
    path = _agent(tmp_path, "[MECHANICAL] no mapping", VALID_BULLET)

    code, out = _run(path, capsys, ids)

    assert code == EXIT_INVALID
    assert f"{path}:{FIRST_BULLET_LINE} [MECHANICAL] no mapping" in out


def test_mapping_clears_the_failure_and_bullet_counts_as_mechanical(
    tmp_path, capsys, ids
):
    path = _agent(tmp_path, "[MECHANICAL] no mapping")
    assert _run(path, capsys, ids)[0] == EXIT_INVALID

    path = _agent(tmp_path, "[MECHANICAL] rule: no-var")
    code, out = _run(path, capsys, ids)

    assert code == 0
    assert "1 MECHANICAL" in out
    assert "0 untagged" in out
    assert "0 double-tagged" in out


def test_reason_of_three_words_is_accepted(tmp_path, capsys, ids):
    path = _agent(tmp_path, "[MECHANICAL] no rule: needs call graph")

    code, out = _run(path, capsys, ids)

    assert code == 0
    assert "1 MECHANICAL" in out


def test_judgment_bullet_needs_no_mapping(tmp_path, capsys, ids):
    path = _agent(tmp_path, "Names that hide intent [JUDGMENT]")

    code, out = _run(path, capsys, ids)

    assert code == 0
    assert "1 JUDGMENT" in out


def test_tag_and_mapping_may_follow_the_bullet_text_on_a_continuation_line(
    tmp_path, capsys, ids
):
    path = tmp_path / "agent.md"
    path.write_text(
        "## Detect\n\n- Flags `var`\n  [MECHANICAL] rule: no-var\n\n## Output\n",
        encoding="utf-8",
    )

    code, _ = _run(path, capsys, ids)

    assert code == 0


def test_ids_come_from_the_injected_rule_ids_file(tmp_path, capsys):
    ids = _rule_ids(tmp_path, enabled=["only-enabled-rule"])
    mapped = _agent(tmp_path, "Check [MECHANICAL] rule: only-enabled-rule")
    unmapped = _agent(tmp_path, "Check [MECHANICAL] rule: no-var", name="other.md")

    assert main([str(mapped), "--rule-ids", ids]) == 0
    capsys.readouterr()
    assert main([str(unmapped), "--rule-ids", ids]) == EXIT_INVALID
    assert "unknown rule id no-var" in capsys.readouterr().out


def test_planned_ids_are_valid_mappings_until_their_rules_ship(tmp_path, capsys):
    ids = _rule_ids(tmp_path, enabled=["no-var"], planned=["max-depth"])
    path = _agent(tmp_path, "Deep [MECHANICAL] rule: max-depth")

    assert main([str(path), "--rule-ids", ids]) == 0


def test_default_rule_ids_file_is_the_shipped_one_outside_dev_and_payload():
    assert RULE_IDS_PATH == SHIPPED_RULE_IDS
    assert RULE_IDS_PATH.is_file()


def test_every_shipped_rule_id_and_planned_id_is_accepted(tmp_path, capsys):
    shipped = json.loads(SHIPPED_RULE_IDS.read_text(encoding="utf-8"))
    mapped = [*shipped["enabled"], *shipped["planned"]]
    path = _agent(tmp_path, *(f"Check {i} [MECHANICAL] rule: {i}" for i in mapped))

    code = main([str(path), "--rule-ids", str(SHIPPED_RULE_IDS)])
    out = capsys.readouterr().out

    assert code == 0
    assert f"{len(mapped)} MECHANICAL" in out


@pytest.mark.parametrize(
    "content",
    [
        "{not json",
        "[]",
        '{"enabled": "no-var"}',
        '{"enabled": [1], "planned": [], "convertible": []}',
        '{"enabled": [], "planned": [["no-var"]], "convertible": []}',
        '{"enabled": [], "planned": [], "convertible": [null]}',
    ],
)
def test_malformed_rule_ids_file_exits_with_a_message(tmp_path, capsys, content):
    bad = tmp_path / "bad.json"
    bad.write_text(content, encoding="utf-8")
    path = _agent(tmp_path, VALID_BULLET)

    assert main([str(path), "--rule-ids", str(bad)]) == EXIT_BAD_INPUT
    assert "rule-ids" in capsys.readouterr().err


def test_pointer_on_a_judgment_bullet_fails(tmp_path, capsys):
    ids = _rule_ids(tmp_path, enabled=["no-var"], convertible=["no-var"])
    path = _agent(tmp_path, _pointer().replace("[MECHANICAL] rule: no-var", "[JUDGMENT]"))

    assert main([str(path), "--rule-ids", ids]) == EXIT_INVALID
    assert "a lint pointer needs a [MECHANICAL] tag" in capsys.readouterr().out


def test_unreadable_rule_ids_file_exits_with_a_message(tmp_path, capsys):
    path = _agent(tmp_path, VALID_BULLET)

    code = main([str(path), "--rule-ids", str(tmp_path / "absent.json")])

    assert code == EXIT_BAD_INPUT
    assert "rule-ids" in capsys.readouterr().err


POINTER = (
    "`var` → use `const`/`let`. If `eslint.devteam.config.js` enables `{id}` and it "
    "is wired, judge only {residual}; otherwise judge fully. "
    "[MECHANICAL] rule: {mapped}"
)


def _pointer(id="no-var", mapped=None, residual="a prefixed `var`"):
    return POINTER.format(id=id, mapped=mapped or id, residual=residual)


def test_pointer_to_a_convertible_rule_passes(tmp_path, capsys):
    ids = _rule_ids(tmp_path, enabled=["no-var"], convertible=["no-var"])
    path = _agent(tmp_path, _pointer())

    assert main([str(path), "--rule-ids", ids]) == 0


@pytest.mark.parametrize(
    ("bullet", "reason"),
    [
        pytest.param(
            _pointer(id="prefer-const"),
            "pointer names prefer-const, which is not marked convertible",
            id="not-convertible",
        ),
        pytest.param(
            _pointer(id="no-var", mapped="no-plusplus"),
            "pointer names no-var but the bullet maps to no-plusplus",
            id="id-differs-from-mapping",
        ),
        pytest.param(
            _pointer().replace("; otherwise judge fully", ""),
            "pointer must say 'otherwise judge fully'",
            id="missing-fallback",
        ),
        pytest.param(
            _pointer().replace("enables `no-var` and", "enables and"),
            "pointer must name the rule id it relies on",
            id="no-id",
        ),
    ],
)
def test_malformed_pointer_fails_with_the_reason(tmp_path, capsys, bullet, reason):
    ids = _rule_ids(
        tmp_path,
        enabled=["no-var", "prefer-const", "no-plusplus"],
        convertible=["no-var", "no-plusplus"],
    )
    path = _agent(tmp_path, bullet)

    code = main([str(path), "--rule-ids", ids])

    assert code == EXIT_INVALID
    assert reason in capsys.readouterr().out


def test_pointer_on_a_no_rule_bullet_says_it_needs_a_rule_mapping(tmp_path, capsys):
    ids = _rule_ids(tmp_path, enabled=["no-var"], convertible=["no-var"])
    bullet = _pointer().replace(
        "[MECHANICAL] rule: no-var", "[MECHANICAL] no rule: prefix exempts both rules"
    )
    path = _agent(tmp_path, bullet)

    code = main([str(path), "--rule-ids", ids])

    assert code == EXIT_INVALID
    assert "a lint pointer needs a rule: <id> mapping" in capsys.readouterr().out


def test_missing_agent_file_exits_with_a_message_naming_it(tmp_path, capsys, ids):
    absent = tmp_path / "absent.md"

    code = main([str(absent), "--rule-ids", ids])
    captured = capsys.readouterr()

    assert code == EXIT_BAD_INPUT
    assert "check_detect_tags:" in captured.err
    assert str(absent) in captured.err
    assert "Traceback" not in captured.err


def test_file_without_detect_section_fails_naming_the_file(tmp_path, capsys, ids):
    path = tmp_path / "no-detect.md"
    path.write_text("# Agent\n\n## Output\n\n- a bullet [JUDGMENT]\n", encoding="utf-8")

    code, out = _run(path, capsys, ids)

    assert code == EXIT_INVALID
    assert str(path) in out
    assert "## Detect" in out


def test_one_bad_file_fails_the_run_even_when_others_are_valid(tmp_path, capsys, ids):
    good = _agent(tmp_path, VALID_BULLET, name="good.md")
    bad = _agent(tmp_path, "untagged bullet text", name="bad.md")

    code = main([str(good), str(bad), "--rule-ids", ids])
    out = capsys.readouterr().out

    assert code == EXIT_INVALID
    assert f"{bad}:{FIRST_BULLET_LINE} untagged bullet text" in out
    assert str(good) not in out


def test_valid_fixture_with_both_tags_passes_and_reports_counts(tmp_path, capsys, ids):
    path = _agent(tmp_path, VALID_BULLET, "Names that hide intent [JUDGMENT]")

    code, out = _run(path, capsys, ids)

    assert code == 0
    assert "1 MECHANICAL, 1 JUDGMENT, 0 untagged, 0 double-tagged" in out
