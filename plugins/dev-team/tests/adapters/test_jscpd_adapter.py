"""jscpd JSON report -> unified-finding-envelope adapter (#1974).

The adapter consumes the report jscpd's JSON reporter writes to
`<output>/jscpd-report.json` (it writes a file, never stdout) and emits one
unified-finding-v1 envelope per clone, anchored at the first occurrence.

`REPORT` below reproduces the shape jscpd 5.0.16 actually emits, captured
from a real run rather than written from memory.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
ADAPTER = (
    PLUGIN_ROOT / "skills" / "static-analysis-integration" / "adapters" / "jscpd-adapter.py"
)
SCHEMA = PLUGIN_ROOT / "knowledge" / "schemas" / "unified-finding-v1.json"

FRAGMENT = "function alpha(a,b){\n  const x = a + b;\n  return x;\n}"


def report(**overrides) -> str:
    duplicate = {
        "firstFile": {
            "name": "src/one.js", "start": 1, "end": 7,
            "startLoc": {"column": 14, "line": 1, "position": 14},
            "endLoc": {"column": 1, "line": 7, "position": 113},
        },
        "secondFile": {
            "name": "src/two.js", "start": 12, "end": 18,
            "startLoc": {"column": 13, "line": 12, "position": 13},
            "endLoc": {"column": 1, "line": 18, "position": 112},
        },
        "format": "javascript",
        "fragment": FRAGMENT,
        "lines": 7,
        "tokens": 42,
    }
    duplicate.update(overrides)
    return json.dumps({"duplicates": [duplicate], "statistics": {"formats": {}}})


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


def test_a_clone_maps_to_one_finding_anchored_at_the_first_occurrence():
    result = run_adapter(report())
    assert result.returncode == 0
    (finding,) = findings_from(result)
    assert finding["rule_id"] == "jscpd.duplication.clone"
    assert finding["file"] == "src/one.js"
    assert finding["line"] == 1
    assert finding["end_line"] == 7
    assert finding["severity"] == "warning"
    assert finding["metadata"]["duplicate_of"] == "src/two.js"
    assert finding["metadata"]["format"] == "javascript"


def test_one_finding_per_clone_not_two_so_pairs_are_not_double_counted():
    assert len(findings_from(run_adapter(report()))) == 1


def test_the_message_names_the_other_location_and_the_clone_size():
    (finding,) = findings_from(run_adapter(report()))
    assert "7 lines" in finding["message"]
    assert "42 tokens" in finding["message"]
    assert "src/two.js:12-18" in finding["message"]


def test_the_duplicated_source_fragment_is_never_copied_into_the_finding():
    """`fragment` holds both copies of the clone verbatim. These findings go
    into every review agent's prompt, so echoing the source back is exactly
    the token cost this lane exists to remove."""
    (finding,) = findings_from(run_adapter(report()))
    serialized = json.dumps(finding)
    assert "const x = a + b" not in serialized
    assert "fragment" not in finding


def test_emitted_findings_validate_against_unified_finding_v1():
    jsonschema = __import__("jsonschema")
    validator = jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text()))
    for finding in findings_from(run_adapter(report())):
        assert not list(validator.iter_errors(finding))


def test_absolute_paths_are_relativized_because_the_envelope_forbids_them():
    absolute = {"name": str(Path.cwd() / "src" / "one.js"), "start": 1, "end": 7}
    (finding,) = findings_from(run_adapter(report(firstFile=absolute)))
    assert finding["file"] == "src/one.js"


def test_no_duplicates_yields_no_findings_and_success():
    result = run_adapter(json.dumps({"duplicates": [], "statistics": {}}))
    assert result.returncode == 0
    assert result.stdout == ""


def test_malformed_json_degrades_to_skip_with_warning():
    result = run_adapter("Duplications detection: Found 1 exact clone")
    assert result.returncode == 0
    assert result.stdout == ""
    assert "WARN" in result.stderr


def test_a_clone_missing_its_anchor_name_is_skipped_not_fabricated():
    result = run_adapter(report(firstFile={"start": 1, "end": 7}))
    assert result.returncode == 0
    assert findings_from(result) == []


def test_a_nonnumeric_range_is_skipped_without_failing():
    result = run_adapter(report(firstFile={"name": "src/one.js", "start": "x", "end": 7}))
    assert result.returncode == 0
    assert findings_from(result) == []


def test_a_null_anchor_name_is_skipped_rather_than_anchored_at_the_empty_path():
    """A null `firstFile.name` produced a schema-VALID finding with
    `"file": ""` — a fabricated location, which is worse than no finding
    because it reads as a real one."""
    payload = report(firstFile={"name": None, "start": 1, "end": 7})
    result = run_adapter(payload)
    assert result.returncode == 0
    assert findings_from(result) == []


@pytest.mark.parametrize(
    "payload",
    [
        '[]', '"a string"', 'null', '123',
        '{"duplicates": null}', '{"duplicates": [{}]}',
        # `duplicates` present but not a list: iterating a dict yields its
        # KEYS, so `dup.get(...)` hit AttributeError and crashed the lane —
        # the pipeline failure the graceful-degradation contract forbids.
        '{"duplicates": {"javascript": []}}',
        '{"duplicates": ["a-string"]}',
        '{"duplicates": [null]}',
    ],
)
def test_valid_json_of_the_wrong_shape_degrades_to_no_findings(payload):
    """Well-formed JSON that is not a jscpd report must not crash the lane —
    graceful degradation covers the wrong-shape case, not just unparseable
    bytes."""
    result = run_adapter(payload)
    assert result.returncode == 0
    assert result.stdout == ""


def test_empty_input_yields_no_findings_and_success():
    result = run_adapter("")
    assert result.returncode == 0
    assert result.stdout == ""


def test_adapter_stays_within_the_forty_loc_budget():
    source = ADAPTER.read_text()
    first = ast.parse(source).body[0]
    doc_end = first.end_lineno if isinstance(first, ast.Expr) else 0
    loc = sum(
        1
        for lineno, line in enumerate(source.splitlines(), 1)
        if lineno > doc_end and line.strip() and not line.strip().startswith("#")
    )
    assert loc <= 40, f"jscpd adapter is {loc} LOC — budget is 40"
