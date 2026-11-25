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

ESLINT_TEMPLATE = SCRIPTS_DIR.parent / "templates" / "eslint"
ESLINT_DEV = ESLINT_TEMPLATE / "dev"


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


def test_duplicate_file_line_rule_findings_collapse_to_one_case():
    agent = [_f("no-var", 1), _f("no-var", 1)]
    rule = [_f("no-var", 1), _f("no-var", 1), _f("no-var", 1)]

    entry = compare(agent, rule)["rules"]["no-var"]

    assert (entry["agent_found"], entry["rule_found"]) == (1, 1)
    assert entry["false_positives"] == 0
    assert entry["convertible"] is True


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

    verdicts = {
        line.split(" | ")[0]: line.split(" | ")[-1] for line in out.out.splitlines()[1:]
    }
    assert code == 0
    assert verdicts == {"no-var": "convertible", "prefer-const": "NOT convertible"}


def test_rules_file_adds_rules_with_no_findings(tmp_path, capsys):
    rules = _write(tmp_path, "rules.json", ["no-var", "no-plusplus"])

    code, out = _run(tmp_path, capsys, [_f("no-var", 1)], [_f("no-var", 1)], "--rules", rules)

    assert code == 0
    assert json.loads(out.out)["rules"]["no-plusplus"]["convertible"] is False


@pytest.mark.parametrize(
    "agent, rule, fragment",
    [
        pytest.param(
            {"nope": 1}, [], "expected a list or an object with 'findings'",
            id="object-without-findings",
        ),
        pytest.param(
            [{"rule": "no-var", "file": "a.ts"}], [], "agent.json[0]: 'line' must be an integer",
            id="missing-line",
        ),
        pytest.param(
            [{"rule": "no-var", "file": "a.ts", "line": True}], [],
            "agent.json[0]: 'line' must be an integer",
            id="boolean-line",
        ),
        pytest.param(
            [], [{"rule": "no-var", "file": "a.ts", "line": "3"}],
            "rule.json[0]: 'line' must be an integer",
            id="string-line",
        ),
        pytest.param(
            ["no-var:1"], [], "agent.json[0]: not an object", id="agent-item-not-an-object"
        ),
        pytest.param(
            [], [[]], "rule.json[0]: not an object", id="rule-item-not-an-object"
        ),
        pytest.param(
            [{"rule": "no-var", "file": 7, "line": 1}], [],
            "agent.json[0]: 'file' must be a string",
            id="non-string-file",
        ),
        pytest.param(
            [{"rule": 7, "file": "a.ts", "line": 1}], [],
            "agent.json[0]: 'rule' must be a string or null",
            id="non-string-agent-rule",
        ),
        pytest.param(
            [], [{"rule": 7, "file": "a.ts", "line": 1}],
            "rule.json[0]: 'rule' must be a string or null",
            id="non-string-rule-found-rule",
        ),
        pytest.param(
            [], [{"rule": None, "file": "a.ts", "line": 1}],
            "rule.json[0]: 'rule' is required",
            id="rule-found-without-rule",
        ),
    ],
)
def test_malformed_input_exits_with_the_reason(tmp_path, capsys, agent, rule, fragment):
    code, out = _run(tmp_path, capsys, agent, rule)

    assert code == EXIT_BAD_INPUT
    assert fragment in out.err


@pytest.mark.parametrize(
    "bad_side, state",
    [
        pytest.param("agent", "unparseable", id="agent-unparseable"),
        pytest.param("rule", "unparseable", id="rule-unparseable"),
        pytest.param("agent", "absent", id="agent-absent"),
        pytest.param("rule", "absent", id="rule-absent"),
    ],
)
def test_missing_and_unparseable_files_exit_with_a_message(
    tmp_path, capsys, bad_side, state
):
    bad = tmp_path / "bad.json"
    if state == "unparseable":
        bad.write_text("{not json", encoding="utf-8")
    good = _write(tmp_path, "good.json", [])
    paths = {"agent": good, "rule": good, bad_side: str(bad)}

    code = main(["--agent-found", paths["agent"], "--rule-found", paths["rule"]])

    err = capsys.readouterr().err
    assert code == EXIT_BAD_INPUT
    assert f"lint_corpus_compare: {bad}" in err
    assert "Traceback" not in err


def test_rules_file_that_is_not_a_list_of_strings_exits_with_a_message(tmp_path, capsys):
    rules = _write(tmp_path, "rules.json", {"no-var": True})

    code, out = _run(tmp_path, capsys, [], [], "--rules", rules)

    assert code == EXIT_BAD_INPUT
    assert "list of rule id strings" in out.err


def test_rule_ids_convertible_list_is_the_comparison_of_the_committed_corpus():
    agent = load_findings(str(ESLINT_DEV / "corpus" / "agent-found.json"), rule_required=False)
    rule = load_findings(str(ESLINT_DEV / "corpus" / "rule-found.json"), rule_required=True)
    ids = json.loads((ESLINT_TEMPLATE / "rule-ids.json").read_text(encoding="utf-8"))

    report = compare(agent, rule, rules=ids["enabled"])

    assert sorted(ids["convertible"]) == sorted(report["convertible"])
    assert set(ids["convertible"]) <= set(ids["enabled"])
    verdicts = {rule_id: row["convertible"] for rule_id, row in report["rules"].items()}
    assert {r: verdicts[r] for r in ids["enabled"]} == {
        r: r in ids["convertible"] for r in ids["enabled"]
    }


def test_script_is_executable_with_a_shebang():
    script = SCRIPTS_DIR / "lint_corpus_compare.py"

    assert script.read_text(encoding="utf-8").startswith("#!/usr/bin/env python3\n")
    assert os.access(script, os.X_OK)
