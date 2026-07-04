"""mypy --output json -> unified-finding-envelope adapter.

The adapter consumes the JSONL that ``mypy --output json`` (mypy >= 1.11)
writes — one JSON object per diagnostic — on stdin and emits one
unified-finding-v1 envelope per diagnostic on stdout. On older mypy the
flag is rejected with a usage error; piping that rejection through the
adapter must degrade to a skip-with-warning (exit 0, zero findings), never
a pipeline failure.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
ADAPTER = (
    PLUGIN_ROOT / "skills" / "static-analysis-integration" / "adapters" / "mypy-adapter.py"
)
SCHEMA = PLUGIN_ROOT / "knowledge" / "schemas" / "unified-finding-v1.json"


def run_adapter(stdin_text: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ADAPTER)],
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=30,
    )


def mypy_line(**overrides) -> str:
    entry = {
        "file": "src/app.py",
        "line": 12,
        "column": 5,
        "message": 'Argument 1 to "f" has incompatible type "str"; expected "int"',
        "hint": None,
        "code": "arg-type",
        "severity": "error",
    }
    entry.update(overrides)
    return json.dumps(entry)


def findings_from(result: subprocess.CompletedProcess) -> list:
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


def test_error_diagnostic_maps_to_a_schema_valid_error_finding():
    result = run_adapter(mypy_line() + "\n")
    assert result.returncode == 0
    (finding,) = findings_from(result)
    assert finding == {
        "rule_id": "mypy.python.arg-type",
        "file": "src/app.py",
        "line": 12,
        "column": 5,
        "severity": "error",
        "message": 'Argument 1 to "f" has incompatible type "str"; expected "int"',
        "metadata": {"source": "mypy", "confidence": "high"},
    }


def test_emitted_findings_validate_against_unified_finding_v1():
    jsonschema = __import__("jsonschema")
    validator = jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text()))
    result = run_adapter(
        mypy_line() + "\n" + mypy_line(severity="note", code=None, column=0) + "\n"
    )
    findings = findings_from(result)
    assert len(findings) == 2
    for finding in findings:
        assert not list(validator.iter_errors(finding))


def test_note_without_error_code_falls_back_to_the_note_rule_id():
    result = run_adapter(mypy_line(severity="note", code=None) + "\n")
    (finding,) = findings_from(result)
    assert finding["rule_id"] == "mypy.python.note"
    assert finding["severity"] == "suggestion"


def test_unknown_severity_degrades_to_info():
    result = run_adapter(mypy_line(severity="mystery") + "\n")
    (finding,) = findings_from(result)
    assert finding["severity"] == "info"


def test_nonpositive_column_is_omitted_from_the_envelope():
    result = run_adapter(mypy_line(column=0) + "\n")
    (finding,) = findings_from(result)
    assert "column" not in finding


def test_nonpositive_line_is_clamped_to_one():
    result = run_adapter(mypy_line(line=0) + "\n")
    (finding,) = findings_from(result)
    assert finding["line"] == 1


def test_overlong_message_is_truncated_to_the_envelope_limit():
    result = run_adapter(mypy_line(message="x" * 800) + "\n")
    (finding,) = findings_from(result)
    assert len(finding["message"]) == 500


def test_old_mypy_flag_rejection_degrades_to_skip_with_warning():
    usage_error = (
        "usage: mypy [-h] [-v] [-V] [more options; see below]\n"
        "mypy: error: unrecognized arguments: --output json\n"
    )
    result = run_adapter(usage_error)
    assert result.returncode == 0
    assert result.stdout == ""
    assert "WARN" in result.stderr
    assert "1.11" in result.stderr


def test_non_json_summary_lines_are_skipped_without_failing():
    text = mypy_line() + "\nFound 1 error in 1 file (checked 3 source files)\n"
    result = run_adapter(text)
    assert result.returncode == 0
    assert len(findings_from(result)) == 1


def test_empty_input_yields_no_findings_and_success():
    result = run_adapter("")
    assert result.returncode == 0
    assert result.stdout == ""


def test_adapter_stays_within_the_tier3_forty_loc_budget():
    """Tier 3 adapters are budgeted at <= 40 LOC — executable lines: non-blank,
    non-comment lines after the shebang and module docstring."""
    import ast

    source = ADAPTER.read_text()
    first = ast.parse(source).body[0]
    doc_end = first.end_lineno if isinstance(first, ast.Expr) else 0
    loc = sum(
        1
        for lineno, line in enumerate(source.splitlines(), 1)
        if lineno > doc_end and line.strip() and not line.strip().startswith("#")
    )
    assert loc <= 40, f"mypy adapter is {loc} LOC — Tier 3 budget is 40"
