"""Tests for scripts/lint_corpus_compare.py.

Each case writes small agent-found / rule-found JSON files under tmp_path and
runs ``main`` in-process, asserting the printed report and exit code.
"""

import json
import os
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from lint_corpus_compare import (
    EXIT_BAD_INPUT,
    EXIT_NONE_CONVERTIBLE,
    compare,
    load_findings,
    main,
)

ESLINT_DEV = SCRIPTS_DIR.parent / "templates" / "eslint" / "dev"


def _f(rule, line, file="a.ts"):
    return {"rule": rule, "file": file, "line": line}


def _write(tmp_path: Path, name: str, payload) -> str:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def _run(tmp_path, capsys, agent, rule, *extra):
    code = main(
        [
            "--agent-found",
            _write(tmp_path, "agent.json", agent),
            "--rule-found",
            _write(tmp_path, "rule.json", rule),
            *extra,
        ]
    )
    return code, capsys.readouterr()


def test_full_coverage_with_no_false_positives_is_convertible():
    report = compare([_f("no-var", 1), _f("no-var", 5)], [_f("no-var", 1), _f("no-var", 5)])

    assert report["rules"]["no-var"] == {
        "agent_found": 2,
        "rule_found": 2,
        "false_positives": 0,
        "false_positive_at": [],
        "residual": [],
        "convertible": True,
    }
    assert report["convertible"] == ["no-var"]


def test_partial_coverage_lists_the_missed_cases_and_is_not_convertible():
    agent = [_f("no-param-reassign", 3), _f("no-param-reassign", 9), _f("no-param-reassign", 14)]
    rule = [_f("no-param-reassign", 3), _f("no-param-reassign", 9)]

    entry = compare(agent, rule)["rules"]["no-param-reassign"]

    assert (entry["agent_found"], entry["rule_found"]) == (3, 2)
    assert entry["residual"] == ["a.ts:14"]
    assert entry["false_positives"] == 0
    assert entry["convertible"] is False


def test_false_positives_are_counted_per_rule_and_leave_other_counts_alone():
    agent = [_f("no-var", 1), _f("prefer-const", 2)]
    rule = [_f("no-var", 1), _f("no-var", 7), _f("prefer-const", 2)]

    rules = compare(agent, rule)["rules"]

    assert rules["no-var"]["false_positives"] == 1
    assert rules["no-var"]["false_positive_at"] == ["a.ts:7"]
    assert rules["no-var"]["convertible"] is False
    assert (rules["no-var"]["agent_found"], rules["no-var"]["rule_found"]) == (1, 2)
    assert rules["prefer-const"] == {
        "agent_found": 1,
        "rule_found": 1,
        "false_positives": 0,
        "false_positive_at": [],
        "residual": [],
        "convertible": True,
    }


def test_a_line_the_agent_flagged_under_no_rule_is_not_a_false_positive():
    agent = [_f(None, 4), _f("no-param-reassign", 2)]
    rule = [_f("no-param-reassign", 2), _f("no-param-reassign", 4)]

    entry = compare(agent, rule)["rules"]["no-param-reassign"]

    assert entry["false_positives"] == 0
    assert entry["convertible"] is True


def test_a_rule_with_no_agent_cases_has_no_evidence_and_is_not_convertible():
    report = compare([], [], rules=["no-var"])

    assert report["rules"]["no-var"]["convertible"] is False
    assert report["convertible"] == []


def test_findings_are_keyed_by_file_and_line():
    agent = [_f("no-var", 1, "a.ts"), _f("no-var", 1, "b.ts")]
    rule = [_f("no-var", 1, "a.ts")]

    assert compare(agent, rule)["rules"]["no-var"]["residual"] == ["b.ts:1"]


def test_input_order_does_not_change_the_report():
    agent = [_f("no-var", 1), _f("no-var", 5), _f("prefer-const", 3)]
    rule = [_f("no-var", 5), _f("prefer-const", 3), _f("no-var", 1), _f("no-var", 9)]

    assert compare(agent, rule) == compare(agent[::-1], rule[::-1])


def test_json_report_and_exit_zero_when_something_is_convertible(tmp_path, capsys):
    code, out = _run(tmp_path, capsys, [_f("no-var", 1)], [_f("no-var", 1)])

    assert code == 0
    assert json.loads(out.out)["convertible"] == ["no-var"]


def test_zero_convertible_prints_a_stop_report_and_exits_nonzero(tmp_path, capsys):
    code, out = _run(tmp_path, capsys, [_f("no-var", 1)], [_f("no-var", 1), _f("no-var", 8)])

    assert code == EXIT_NONE_CONVERTIBLE
    assert "gate: none convertible" in out.err
    assert json.loads(out.out)["convertible"] == []


def test_text_format_marks_non_convertible_rules(tmp_path, capsys):
    code, out = _run(
        tmp_path,
        capsys,
        [_f("no-var", 1), _f("prefer-const", 2)],
        [_f("no-var", 1), _f("prefer-const", 2), _f("prefer-const", 6)],
        "--format",
        "text",
    )

    assert code == 0
    assert "no-var" in out.out and "convertible" in out.out
    assert "prefer-const" in out.out and "NOT convertible" in out.out


def test_rules_file_adds_rules_with_no_findings(tmp_path, capsys):
    rules = _write(tmp_path, "rules.json", ["no-var", "no-plusplus"])

    code, out = _run(tmp_path, capsys, [_f("no-var", 1)], [_f("no-var", 1)], "--rules", rules)

    assert code == 0
    assert json.loads(out.out)["rules"]["no-plusplus"]["convertible"] is False


@pytest.mark.parametrize(
    "agent, rule",
    [
        pytest.param({"nope": 1}, [], id="object-without-findings"),
        pytest.param([{"rule": "no-var", "file": "a.ts"}], [], id="missing-line"),
        pytest.param([], [{"rule": None, "file": "a.ts", "line": 1}], id="rule-found-without-rule"),
        pytest.param([], [{"rule": "no-var", "file": "a.ts", "line": "3"}], id="string-line"),
    ],
)
def test_malformed_input_exits_with_a_message(tmp_path, capsys, agent, rule):
    code, out = _run(tmp_path, capsys, agent, rule)

    assert code == EXIT_BAD_INPUT
    assert out.err.strip()


def test_missing_and_unparseable_files_exit_with_a_message(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    good = _write(tmp_path, "good.json", [])

    assert main(["--agent-found", str(bad), "--rule-found", good]) == EXIT_BAD_INPUT
    assert main(["--agent-found", good, "--rule-found", str(tmp_path / "absent.json")]) == EXIT_BAD_INPUT
    assert capsys.readouterr().err.count("lint_corpus_compare:") == 2


def test_rules_file_that_is_not_a_list_of_strings_exits_with_a_message(tmp_path, capsys):
    rules = _write(tmp_path, "rules.json", {"no-var": True})

    code, out = _run(tmp_path, capsys, [], [], "--rules", rules)

    assert code == EXIT_BAD_INPUT
    assert "list of rule id strings" in out.err


def test_rule_ids_convertible_list_is_the_comparison_of_the_committed_corpus():
    agent = load_findings(str(ESLINT_DEV / "corpus" / "agent-found.json"), rule_required=False)
    rule = load_findings(str(ESLINT_DEV / "corpus" / "rule-found.json"), rule_required=True)
    ids = json.loads((ESLINT_DEV / "rule-ids.json").read_text(encoding="utf-8"))

    report = compare(agent, rule, rules=ids["enabled"])

    assert ids["convertible"] == report["convertible"]
    assert set(ids["convertible"]) <= set(ids["enabled"])


def test_script_is_executable_with_a_shebang():
    script = SCRIPTS_DIR / "lint_corpus_compare.py"

    assert script.read_text(encoding="utf-8").startswith("#!/usr/bin/env python3\n")
    assert os.access(script, os.X_OK)
