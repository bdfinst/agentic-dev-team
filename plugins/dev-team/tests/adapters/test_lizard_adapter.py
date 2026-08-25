"""lizard --csv -> unified-finding-envelope adapter (#1974).

The adapter consumes lizard's positional, unheadered CSV on stdin — one row
per function — and emits one unified-finding-v1 envelope per *threshold
breach*, so a clean tree produces no findings at all.

The CSV column order and the `-Ens` 12th column are lizard's own, verified
against lizard 1.24.0. `ROW` below reproduces a real row from that version
rather than an invented one.
"""

from __future__ import annotations

import ast
import csv
import io
import json
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
ADAPTER = (
    PLUGIN_ROOT / "skills" / "static-analysis-integration" / "adapters" / "lizard-adapter.py"
)
SCHEMA = PLUGIN_ROOT / "knowledge" / "schemas" / "unified-finding-v1.json"

#: nloc,ccn,token,param,length,location,file,name,long_name,start,end[,ns]
#: Verbatim shape of `lizard -Ens --csv` output on lizard 1.24.0.
COLUMNS = ["18", "9", "79", "6", "18", "tangled@1-18@sample.py",
           "svc/sample.py", "tangled", "tangled( a, b )", "1", "18", "9"]


def row(**overrides) -> str:
    """One CSV row, with named column overrides.

    Written through `csv.writer` rather than `",".join` on purpose: lizard
    quotes the fields that contain commas (`long_name` is a full signature,
    e.g. `tangled( a, b )`), and a naive join would silently shift every
    column after it — making the fixture disagree with the tool it claims to
    reproduce.
    """
    names = ["nloc", "ccn", "token", "param", "length", "location",
             "file", "name", "long_name", "start", "end", "ns"]
    cols = list(COLUMNS)
    for key, value in overrides.items():
        cols[names.index(key)] = str(value)
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\n").writerow(cols)
    return buffer.getvalue()


def run_adapter(stdin_text: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ADAPTER)],
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def findings_from(result: subprocess.CompletedProcess) -> list:
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


def rules(result) -> set:
    return {f["rule_id"] for f in findings_from(result)}


def test_a_function_under_every_threshold_produces_no_findings():
    clean = run_adapter(row(ccn=1, param=1, length=2))
    assert clean.returncode == 0
    assert findings_from(clean) == []


def test_each_metric_over_threshold_emits_its_own_rule():
    result = run_adapter(row(ccn=25, param=9, length=200, ns=30))
    assert rules(result) == {
        "lizard.complexity.cyclomatic",
        "lizard.complexity.function-length",
        "lizard.complexity.parameter-count",
    }


def test_nested_structure_is_never_reported():
    """lizard's `-Ens` metric is cumulative nested-structure complexity, not
    max nesting depth. Measured over this repo's hooks/+scripts/ tree its
    median is 9 and a threshold of 6 fired on 57% of all functions, so the
    lane omits it rather than shipping noise under a misleading name. A row
    carrying the column must still parse — it is ignored, not rejected."""
    result = run_adapter(row(ccn=1, param=1, length=2, ns=999))
    assert findings_from(result) == []


def test_a_value_exactly_at_the_threshold_does_not_fire():
    """The comparison is strictly greater-than: 10 CCN is the documented
    limit, not a violation of it."""
    result = run_adapter(row(ccn=10, param=5, length=60))
    assert findings_from(result) == []
    assert rules(run_adapter(row(ccn=11, param=1, length=2))) == {
        "lizard.complexity.cyclomatic"
    }


def test_the_finding_carries_location_name_and_the_measurement():
    (finding,) = findings_from(run_adapter(row(ccn=1, param=9, length=2)))
    assert finding["file"] == "svc/sample.py"
    assert finding["line"] == 1
    assert finding["end_line"] == 18
    assert finding["severity"] == "warning"
    assert "tangled" in finding["message"]
    assert finding["metadata"] == {
        "source": "lizard", "confidence": "high",
        "metric": "parameter-count", "value": 9, "threshold": 5,
    }


def test_emitted_findings_validate_against_unified_finding_v1():
    jsonschema = __import__("jsonschema")
    validator = jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text()))
    findings = findings_from(run_adapter(row(ccn=25, param=9, length=200)))
    assert len(findings) == 3
    for finding in findings:
        assert not list(validator.iter_errors(finding))


def test_output_without_the_ns_extension_still_yields_the_other_metrics():
    """`-Ens` adds the 12th column, which the lane does not use. An 11-column
    row (plain `--csv`, the documented invocation) must evaluate the three
    real metrics normally rather than crash on the missing index."""
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\n").writerow(COLUMNS[:11])
    result = run_adapter(buffer.getvalue())
    assert result.returncode == 0
    assert rules(result) == {"lizard.complexity.parameter-count"}


def test_absolute_paths_are_relativized_because_the_envelope_forbids_them():
    result = run_adapter(row(file=str(Path.cwd() / "svc" / "sample.py"), param=9))
    (finding,) = [f for f in findings_from(result) if f["rule_id"].endswith("parameter-count")]
    assert finding["file"] == "svc/sample.py"


def test_warnings_only_text_output_is_ignored_rather_than_misparsed():
    """`--warnings_only` overrides `--csv` and emits clang-style text. The
    lane forbids that combination; if it happens anyway the adapter must
    produce nothing, never a garbage finding."""
    text = "sample.py:1: warning: tangled has 18 NLOC, 9 CCN, 79 token, 6 PARAM\n"
    result = run_adapter(text)
    assert result.returncode == 0
    assert findings_from(result) == []


def test_malformed_rows_are_skipped_without_failing():
    result = run_adapter("not,enough,columns\n" + row(param=9) + ",,,,,,,,,,\n")
    assert result.returncode == 0
    assert len(findings_from(result)) == 1


def test_non_numeric_metric_is_skipped_but_siblings_survive():
    result = run_adapter(row(ccn="n/a", param=9))
    assert rules(result) == {"lizard.complexity.parameter-count"}


def test_an_overlong_function_name_is_truncated_to_the_envelope_limit():
    """`name` is tool-supplied text (template-qualified C++ symbols, minified
    JS identifiers), and the envelope caps `message` at 500. Without this the
    finding fails schema validation on exactly the pathological function the
    complexity check exists to flag."""
    result = run_adapter(row(name="f" * 900, param=9))
    (finding,) = findings_from(result)
    assert len(finding["message"]) == 500


def test_empty_input_yields_no_findings_and_success():
    result = run_adapter("")
    assert result.returncode == 0
    assert result.stdout == ""


def test_adapter_stays_within_the_forty_loc_budget():
    """Bespoke adapters are budgeted at <= 40 LOC — executable lines:
    non-blank, non-comment lines after the shebang and module docstring."""
    source = ADAPTER.read_text()
    first = ast.parse(source).body[0]
    doc_end = first.end_lineno if isinstance(first, ast.Expr) else 0
    loc = sum(
        1
        for lineno, line in enumerate(source.splitlines(), 1)
        if lineno > doc_end and line.strip() and not line.strip().startswith("#")
    )
    assert loc <= 40, f"lizard adapter is {loc} LOC — budget is 40"
