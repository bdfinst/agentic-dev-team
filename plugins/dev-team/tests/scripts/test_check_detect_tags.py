"""Tests for scripts/check_detect_tags.py.

Each case writes a small agent file under tmp_path and runs the checker's
``main`` on it, asserting the exit code and the printed message.
"""

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from check_detect_tags import main

VALID_BULLET = "Flags `var` declarations [MECHANICAL] rule: no-var"


def _agent(tmp_path: Path, *bullets: str, name: str = "agent.md") -> Path:
    """Write an agent file whose Detect section holds ``bullets``, one per line."""
    body = "\n".join(f"- {b}" for b in bullets)
    path = tmp_path / name
    path.write_text(
        f"# Agent\n\n## Detect\n\n{body}\n\n## Output\n\nNothing.\n", encoding="utf-8"
    )
    return path


def _run(path: Path, capsys) -> tuple[int, str]:
    code = main([str(path)])
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
    tmp_path, capsys, bullet, reason
):
    path = _agent(tmp_path, bullet)

    code, out = _run(path, capsys)

    assert code != 0
    _assert_failure_message(out, path, 5, bullet)
    assert reason in out


def test_failure_reports_the_line_of_the_offending_bullet(tmp_path, capsys):
    path = _agent(tmp_path, VALID_BULLET, "untagged bullet text")

    code, out = _run(path, capsys)

    assert code != 0
    assert f"{path}:6 untagged bullet text" in out
    assert f"{path}:5" not in out


def test_valid_mapped_bullet_added_beside_a_failing_one_does_not_clear_it(
    tmp_path, capsys
):
    path = _agent(tmp_path, "[MECHANICAL] no mapping", VALID_BULLET)

    code, out = _run(path, capsys)

    assert code != 0
    assert f"{path}:5 [MECHANICAL] no mapping" in out


def test_mapping_clears_the_failure_and_bullet_counts_as_mechanical(tmp_path, capsys):
    path = _agent(tmp_path, "[MECHANICAL] no mapping")
    assert main([str(path)]) != 0
    capsys.readouterr()

    path = _agent(tmp_path, "[MECHANICAL] rule: no-var")
    code, out = _run(path, capsys)

    assert code == 0
    assert "1 MECHANICAL" in out
    assert "0 untagged" in out
    assert "0 double-tagged" in out


def test_reason_of_three_words_is_accepted(tmp_path, capsys):
    path = _agent(tmp_path, "[MECHANICAL] no rule: needs call graph")

    code, out = _run(path, capsys)

    assert code == 0
    assert "1 MECHANICAL" in out


def test_judgment_bullet_needs_no_mapping(tmp_path, capsys):
    path = _agent(tmp_path, "Names that hide intent [JUDGMENT]")

    code, out = _run(path, capsys)

    assert code == 0
    assert "1 JUDGMENT" in out


def test_tag_and_mapping_may_follow_the_bullet_text_on_a_continuation_line(
    tmp_path, capsys
):
    path = tmp_path / "agent.md"
    path.write_text(
        "## Detect\n\n- Flags `var`\n  [MECHANICAL] rule: no-var\n\n## Output\n",
        encoding="utf-8",
    )

    code, _ = _run(path, capsys)

    assert code == 0


def test_every_pending_rule_id_is_accepted(tmp_path, capsys):
    ids = [
        "no-var",
        "prefer-const",
        "no-plusplus",
        "no-param-reassign",
        "no-restricted-globals",
        "no-restricted-syntax",
        "max-depth",
        "no-magic-numbers",
        "functional/immutable-data",
    ]
    path = _agent(tmp_path, *(f"Check {i} [MECHANICAL] rule: {i}" for i in ids))

    code, out = _run(path, capsys)

    assert code == 0
    assert f"{len(ids)} MECHANICAL" in out


def test_file_without_detect_section_fails_naming_the_file(tmp_path, capsys):
    path = tmp_path / "no-detect.md"
    path.write_text("# Agent\n\n## Output\n\n- a bullet [JUDGMENT]\n", encoding="utf-8")

    code, out = _run(path, capsys)

    assert code != 0
    assert str(path) in out
    assert "## Detect" in out


def test_one_bad_file_fails_the_run_even_when_others_are_valid(tmp_path, capsys):
    good = _agent(tmp_path, VALID_BULLET, name="good.md")
    bad = _agent(tmp_path, "untagged bullet text", name="bad.md")

    code = main([str(good), str(bad)])
    out = capsys.readouterr().out

    assert code != 0
    assert f"{bad}:5 untagged bullet text" in out
    assert str(good) not in out


def test_valid_fixture_with_both_tags_passes_and_reports_counts(tmp_path, capsys):
    path = _agent(tmp_path, VALID_BULLET, "Names that hide intent [JUDGMENT]")

    code, out = _run(path, capsys)

    assert code == 0
    assert "1 MECHANICAL, 1 JUDGMENT, 0 untagged, 0 double-tagged" in out
