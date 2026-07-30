"""Pytest tests for mutation_report.py's mutmut junitxml support (#1357).

mutmut has no native JSON report — ``mutmut junitxml`` is its only
structured output. These fixtures mirror the real shape observed running
mutmut 2.5.1 against this repo's own code (see #1354/#1357): a survived
mutant carries a ``<failure message="bad_survived">`` child, a timed-out
mutant carries a distinct ``<error message="bad_timeout" type="timeout">``
child, and a killed (or suspicious-but-ignored) mutant carries neither.
"""

from __future__ import annotations

import sys

from _mutation_test_helpers import SCRIPTS_DIR

sys.path.insert(0, str(SCRIPTS_DIR))

import mutation_report


def _junit(*testcases: str, failures: int = 0, errors: int = 0) -> str:
    body = "\n".join(testcases)
    return (
        '<?xml version="1.0" ?>\n'
        f'<testsuites disabled="0" errors="{errors}" failures="{failures}" '
        f'tests="{len(testcases)}" time="0.0">\n'
        f'<testsuite disabled="0" errors="{errors}" failures="{failures}" '
        f'name="mutmut" tests="{len(testcases)}" time="0">\n'
        f"{body}\n"
        "</testsuite>\n"
        "</testsuites>\n"
    )


def _killed_tc(name: str, file: str, line: int) -> str:
    return f'<testcase name="{name}" file="{file}" line="{line}"><system-out>x</system-out></testcase>'


def _survived_tc(name: str, file: str, line: int) -> str:
    return (
        f'<testcase name="{name}" file="{file}" line="{line}">'
        '<failure type="failure" message="bad_survived">diff</failure>'
        "</testcase>"
    )


def _timeout_tc(name: str, file: str, line: int) -> str:
    return (
        f'<testcase name="{name}" file="{file}" line="{line}">'
        '<error type="timeout" message="bad_timeout">diff</error>'
        "</testcase>"
    )


# =============================================================================
# parse_mutmut_junitxml — normalizes into the shared {"files": {...}} shape
# =============================================================================
def test_survived_testcase_maps_to_survived_status():
    xml = _junit(_survived_tc("Mutant #1", "src/calc.py", 12), failures=1)
    data = mutation_report.parse_mutmut_junitxml(xml)

    mutants = data["files"]["src/calc.py"]["mutants"]
    assert len(mutants) == 1
    assert mutants[0]["status"] == mutation_report.STATUS_SURVIVED
    assert mutants[0]["location"]["start"]["line"] == 12
    assert mutants[0]["mutatorName"] == "mutmut"


def test_timeout_testcase_maps_to_timeout_not_survived():
    """A <error type="timeout"> must never be counted as Survived — that's
    the exact inversion bug fixed in the PostToolUse gate adapter (#1356);
    the report parser must get this right independently."""
    xml = _junit(_timeout_tc("Mutant #2", "src/calc.py", 20), errors=1)
    data = mutation_report.parse_mutmut_junitxml(xml)

    mutants = data["files"]["src/calc.py"]["mutants"]
    assert mutants[0]["status"] == mutation_report.STATUS_TIMEOUT


def test_bare_testcase_maps_to_killed():
    xml = _junit(_killed_tc("Mutant #3", "src/calc.py", 5))
    data = mutation_report.parse_mutmut_junitxml(xml)

    assert data["files"]["src/calc.py"]["mutants"][0]["status"] == (
        mutation_report.STATUS_KILLED
    )


def test_mixed_report_groups_by_file():
    xml = _junit(
        _killed_tc("Mutant #1", "src/a.py", 1),
        _survived_tc("Mutant #2", "src/a.py", 2),
        _survived_tc("Mutant #3", "src/b.py", 9),
        failures=2,
    )
    data = mutation_report.parse_mutmut_junitxml(xml)

    assert {m["status"] for m in data["files"]["src/a.py"]["mutants"]} == {
        mutation_report.STATUS_KILLED,
        mutation_report.STATUS_SURVIVED,
    }
    assert len(data["files"]["src/b.py"]["mutants"]) == 1


def test_empty_input_yields_empty_files_dict():
    assert mutation_report.parse_mutmut_junitxml("") == {"files": {}}


def test_malformed_xml_yields_empty_files_dict_not_a_crash():
    assert mutation_report.parse_mutmut_junitxml("not xml") == {"files": {}}


# =============================================================================
# score_mutmut_junitxml — reuses _score_data, same formulas as Stryker
# =============================================================================
def test_score_counts_killed_survived_and_timeout_correctly():
    xml = _junit(
        _killed_tc("Mutant #1", "src/a.py", 1),
        _killed_tc("Mutant #2", "src/a.py", 2),
        _survived_tc("Mutant #3", "src/a.py", 3),
        _timeout_tc("Mutant #4", "src/a.py", 4),
        failures=1,
        errors=1,
    )
    summary = mutation_report.score_mutmut_junitxml(xml)

    assert summary.killed == 2
    assert summary.survived == 1
    assert summary.timeout == 1
    assert summary.no_coverage == 0
    # honest = killed / (killed + survived + no_coverage) = 2/3
    import pytest

    assert summary.honest_score == pytest.approx(2 / 3 * 100)


def test_score_of_empty_report_is_zeroed():
    summary = mutation_report.score_mutmut_junitxml("")
    assert summary.honest_score == 0.0
    assert summary.killed == 0


# =============================================================================
# survivors_from_mutmut_junitxml — same grouping contract as survivors_by_mutator
# =============================================================================
def test_survivors_from_junitxml_filters_to_one_file():
    xml = _junit(
        _survived_tc("Mutant #1", "src/a.py", 1),
        _survived_tc("Mutant #2", "src/b.py", 2),
        _killed_tc("Mutant #3", "src/a.py", 3),
        failures=2,
    )
    grouped = mutation_report.survivors_from_mutmut_junitxml(xml, "src/a.py")

    assert set(grouped) == {"mutmut"}
    assert len(grouped["mutmut"]) == 1
    assert grouped["mutmut"][0]["location"]["start"]["line"] == 1


def test_survivors_from_junitxml_matches_by_basename():
    xml = _junit(_survived_tc("Mutant #1", "/abs/path/src/a.py", 1), failures=1)
    grouped = mutation_report.survivors_from_mutmut_junitxml(xml, "a.py")

    assert set(grouped) == {"mutmut"}
