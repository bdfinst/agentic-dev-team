"""Tests for scripts/coverage_report_parse.py — the shared per-format
coverage report parser extracted from coverage_gap_ranking.py (issue #1873).

Ported from test_coverage_gap_ranking.py's format-detection/parsing section:
same fixtures and behaviors, now asserting `CoverageRecord` fields using
`coverage_config.weighted_merge`'s vocabulary (`covered_statements`/
`total_statements`/`covered_branches`/`total_branches`) instead of
`coverage_gap_ranking.py`'s own `lines_total`/`lines_covered`/... names.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from coverage_report_parse import (
    CoverageRecord,
    ReportError,
    _tally_coverlet_classes,
    aggregate,
    detect_format,
    parse_report,
)

# ---------------------------------------------------------------------------
# fixtures — one small report per supported format
# ---------------------------------------------------------------------------

LCOV = """\
TN:
SF:src/Pipes/Transform.cs
LF:100
LH:90
BRF:20
BRH:18
end_of_record
TN:
SF:src/Repositories/OrderRepository.cs
LF:400
LH:4
BRF:40
BRH:0
end_of_record
TN:
SF:src/Repositories/CustomerRepository.cs
LF:200
LH:0
BRF:10
BRH:0
end_of_record
"""

# Line-level lcov (DA: records only, no LF/LH summary lines) — some tools
# (coverlet's lcov writer among them) emit only DA records.
LCOV_DA_ONLY = """\
SF:src/a/one.py
DA:1,1
DA:2,0
DA:3,0
end_of_record
"""

# A class whose lines appear twice — once under <methods>/<method>/<lines>
# and again under the class-level <lines> block, the shape Cobertura's own
# format and coverlet's cobertura reporter emit. Each source line must be
# counted once.
COBERTURA_DUPLICATED_LINES = """\
<?xml version="1.0"?>
<coverage line-rate="0.5">
  <packages>
    <package name="Pipes">
      <classes>
        <class filename="src/Pipes/Transform.cs">
          <methods>
            <method name="Run">
              <lines>
                <line number="1" hits="1"/>
                <line number="2" hits="0"/>
              </lines>
            </method>
          </methods>
          <lines>
            <line number="1" hits="1"/>
            <line number="2" hits="0"/>
          </lines>
        </class>
      </classes>
    </package>
  </packages>
</coverage>
"""

COBERTURA = """\
<?xml version="1.0"?>
<coverage line-rate="0.2">
  <packages>
    <package name="Pipes">
      <classes>
        <class filename="src/Pipes/Transform.cs">
          <lines>
            <line number="1" hits="1"/>
            <line number="2" hits="1"/>
            <line number="3" hits="0" branch="true" condition-coverage="50% (1/2)"/>
          </lines>
        </class>
      </classes>
    </package>
    <package name="Repositories">
      <classes>
        <class filename="src/Repositories/OrderRepository.cs">
          <lines>
            <line number="1" hits="0"/>
            <line number="2" hits="0"/>
            <line number="3" hits="0" branch="true" condition-coverage="0% (0/2)"/>
          </lines>
        </class>
      </classes>
    </package>
  </packages>
</coverage>
"""

ISTANBUL_SUMMARY = {
    "total": {"lines": {"total": 300, "covered": 100, "pct": 33.33}},
    "src/pipes/transform.js": {
        "lines": {"total": 100, "covered": 95, "pct": 95.0},
        "branches": {"total": 10, "covered": 9, "pct": 90.0},
    },
    "src/repositories/order.js": {
        "lines": {"total": 200, "covered": 5, "pct": 2.5},
        "branches": {"total": 20, "covered": 0, "pct": 0.0},
    },
}

ISTANBUL_FINAL = {
    "/abs/src/pipes/transform.js": {
        "path": "/abs/src/pipes/transform.js",
        "s": {"0": 3, "1": 1, "2": 0},
        "b": {"0": [1, 0]},
    },
    "/abs/src/repositories/order.js": {
        "path": "/abs/src/repositories/order.js",
        "s": {"0": 0, "1": 0, "2": 0, "3": 0},
        "b": {"0": [0, 0]},
    },
}

COVERAGE_PY = {
    "meta": {"version": "7.4.0"},
    "files": {
        "src/pipes/transform.py": {
            "summary": {
                "num_statements": 100,
                "covered_lines": 90,
                "num_branches": 10,
                "covered_branches": 8,
            }
        },
        "src/repositories/order.py": {
            "summary": {
                "num_statements": 300,
                "covered_lines": 3,
                "num_branches": 30,
                "covered_branches": 0,
            }
        },
    },
    "totals": {"percent_covered": 23.25},
}

COVERLET = {
    "Acme.Pipes.dll": {
        "/repo/src/Pipes/Transform.cs": {
            "Acme.Pipes.Transform": {
                "Run()": {
                    "Lines": {"10": 1, "11": 1, "12": 0},
                    "Branches": [
                        {"Line": 10, "Hits": 3},
                        {"Line": 12, "Hits": 0},
                    ],
                }
            }
        }
    },
    "Acme.Repositories.dll": {
        "/repo/src/Repositories/OrderRepository.cs": {
            "Acme.Repositories.OrderRepository": {
                "Get()": {
                    "Lines": {"5": 0, "6": 0, "7": 0, "8": 0},
                    "Branches": [{"Line": 5, "Hits": 0}],
                }
            }
        }
    },
}

JACOCO_CSV = """\
GROUP,PACKAGE,CLASS,INSTRUCTION_MISSED,INSTRUCTION_COVERED,BRANCH_MISSED,BRANCH_COVERED,LINE_MISSED,LINE_COVERED,COMPLEXITY_MISSED,COMPLEXITY_COVERED,METHOD_MISSED,METHOD_COVERED
app,com.acme.pipes,Transform,10,900,1,19,10,90,1,9,0,5
app,com.acme.repositories,OrderRepository,900,10,40,0,400,4,40,0,10,1
app,com.acme.repositories,CustomerRepository,400,0,10,0,200,0,20,0,5,0
"""

# Clover's root element is also a bare `<coverage ...>` like Cobertura's, but
# carries its own `clover="..."` attribute — the signal `detect_format` uses
# to tell the two apart. Clover's `<class>` elements carry `name`, not
# Cobertura's `filename`; per-file totals live directly on each `<file>`'s
# own `<metrics>` child, not reconstructed from `<line>` elements.
CLOVER = """\
<?xml version="1.0" encoding="UTF-8"?>
<coverage generated="1690000000" clover="3.2.0">
  <project timestamp="1690000000" name="All files">
    <metrics statements="20" coveredstatements="15" conditionals="6"
             coveredconditionals="3" methods="4" coveredmethods="4"/>
    <package name="com.acme.pipes">
      <file name="Transform.java" path="src/Pipes/Transform.java">
        <metrics statements="10" coveredstatements="9" conditionals="4"
                 coveredconditionals="2" methods="2" coveredmethods="2"/>
        <class name="Transform">
          <metrics complexity="0" methods="2" coveredmethods="2"
                   conditionals="4" coveredconditionals="2" statements="10"
                   coveredstatements="9"/>
        </class>
      </file>
      <file name="OrderRepository.java" path="src/Repositories/OrderRepository.java">
        <metrics statements="10" coveredstatements="6" conditionals="2"
                 coveredconditionals="1" methods="2" coveredmethods="2"/>
        <class name="OrderRepository">
          <metrics complexity="0" methods="2" coveredmethods="2"
                   conditionals="2" coveredconditionals="1" statements="10"
                   coveredstatements="6"/>
        </class>
      </file>
    </package>
  </project>
</coverage>
"""

# A Cobertura document that is valid XML, correctly detected as "cobertura"
# (no clover= attribute on its root), but declares no <class> elements at
# all — the shape a misconfigured/truncated report writer could produce.
# `_parse_cobertura` keys its lookup on `filename`, present on none of this
# document's (zero) <class> elements, so it parses cleanly to zero records.
COBERTURA_NO_CLASSES = """\
<?xml version="1.0"?>
<coverage line-rate="0.0">
  <packages>
    <package name="Empty">
      <classes/>
    </package>
  </packages>
</coverage>
"""


def _write(tmp_path: Path, name: str, content) -> Path:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, str):
        path.write_text(content, encoding="utf-8")
    else:
        path.write_text(json.dumps(content), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# format detection
# ---------------------------------------------------------------------------


def test_detect_lcov(tmp_path):
    assert detect_format(_write(tmp_path, "lcov.info", LCOV)) == "lcov"


def test_detect_cobertura(tmp_path):
    assert detect_format(_write(tmp_path, "cobertura.xml", COBERTURA)) == "cobertura"


def test_detect_clover_is_not_misdetected_as_cobertura(tmp_path):
    """Both formats root on a bare `<coverage ...>` element. Before this
    fix, `detect_format` classified any `<coverage` document as Cobertura,
    whose parser then silently skipped every Clover `<class>` (Clover keys
    on `name`, not `filename`) and returned zero records for a real report."""
    path = _write(tmp_path, "clover.xml", CLOVER)
    assert detect_format(path) == "clover"


def test_parse_clover_uses_per_file_metrics(tmp_path):
    path = _write(tmp_path, "clover.xml", CLOVER)
    files = parse_report(path, "clover")
    by_path = {f.path: f for f in files}
    transform = by_path["src/Pipes/Transform.java"]
    assert transform.total_statements == 10
    assert transform.covered_statements == 9
    assert transform.total_branches == 4
    assert transform.covered_branches == 2
    order = by_path["src/Repositories/OrderRepository.java"]
    assert order.total_statements == 10
    assert order.covered_statements == 6


def test_detect_jacoco_csv(tmp_path):
    assert detect_format(_write(tmp_path, "jacoco.csv", JACOCO_CSV)) == "jacoco-csv"


def test_detect_istanbul_summary(tmp_path):
    path = _write(tmp_path, "coverage-summary.json", ISTANBUL_SUMMARY)
    assert detect_format(path) == "istanbul-summary"


def test_detect_istanbul_final(tmp_path):
    path = _write(tmp_path, "coverage-final.json", ISTANBUL_FINAL)
    assert detect_format(path) == "istanbul-final"


def test_detect_coverage_py(tmp_path):
    assert detect_format(_write(tmp_path, "coverage.json", COVERAGE_PY)) == "coverage-py"


def test_detect_coverlet(tmp_path):
    assert detect_format(_write(tmp_path, "coverlet.json", COVERLET)) == "coverlet"


def test_detect_unknown_format_raises(tmp_path):
    path = _write(tmp_path, "nope.txt", "hello world\n")
    with pytest.raises(ValueError, match="unrecognized"):
        detect_format(path)


def test_detect_unrecognized_json_shape_raises(tmp_path):
    path = _write(tmp_path, "weird.json", {"foo": 1})
    with pytest.raises(ValueError, match="unrecognized"):
        detect_format(path)


def test_detect_tolerates_a_utf8_bom(tmp_path):
    """.NET/Windows coverage writers emit BOM-prefixed files; a BOM must not
    hide an otherwise supported format."""
    path = tmp_path / "lcov.info"
    path.write_text("﻿" + LCOV, encoding="utf-8")
    assert detect_format(path) == "lcov"
    assert parse_report(path, "lcov")[0].path == "src/Pipes/Transform.cs"


def test_parse_cobertura_malformed_xml_raises(tmp_path):
    path = _write(tmp_path, "cobertura.xml", "<coverage><packages>")
    with pytest.raises(ValueError, match="not valid XML"):
        parse_report(path, "cobertura")


def test_parse_cobertura_rejects_a_doctype_entity_declaration(tmp_path):
    """#1872: the cobertura path parsed with `xml.etree.ElementTree.fromstring`
    directly, with no DOCTYPE/ENTITY screening — the same XXE/billion-laughs
    exposure `coverage_config.read_and_screen_xml` exists to close for every
    other coverage-discovery stack. `parse_report` must raise `ReportError`
    rather than hand a DOCTYPE-carrying document to `ET.fromstring`."""
    path = _write(
        tmp_path,
        "cobertura.xml",
        '<?xml version="1.0"?>\n'
        '<!DOCTYPE coverage [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>\n'
        '<coverage line-rate="1.0">\n'
        "  <packages/>\n"
        "</coverage>\n",
    )
    with pytest.raises(ReportError, match="DOCTYPE"):
        parse_report(path, "cobertura")


def test_parse_report_raises_on_a_recognized_format_that_parses_to_zero_records(tmp_path):
    """A report that detects cleanly as a known format but yields no
    records is indistinguishable, at this layer, from a project that
    genuinely has zero statements — treat it as a parse failure rather than
    silently handing `aggregate()`/`weighted_merge` an empty-but-valid-looking
    0% measurement."""
    path = _write(tmp_path, "cobertura.xml", COBERTURA_NO_CLASSES)
    assert detect_format(path) == "cobertura"
    with pytest.raises(ReportError, match="zero records"):
        parse_report(path, "cobertura")


# ---------------------------------------------------------------------------
# parsing — per-file line/branch tallies
# ---------------------------------------------------------------------------


def test_parse_lcov_tallies_lines_and_branches(tmp_path):
    files = parse_report(_write(tmp_path, "lcov.info", LCOV), "lcov")
    by_path = {f.path: f for f in files}
    assert by_path["src/Pipes/Transform.cs"].total_statements == 100
    assert by_path["src/Pipes/Transform.cs"].covered_statements == 90
    assert by_path["src/Pipes/Transform.cs"].total_branches == 20
    assert by_path["src/Repositories/OrderRepository.cs"].covered_statements == 4


def test_parse_lcov_falls_back_to_da_records(tmp_path):
    files = parse_report(_write(tmp_path, "lcov.info", LCOV_DA_ONLY), "lcov")
    assert files[0].total_statements == 3
    assert files[0].covered_statements == 1


def test_parse_cobertura_counts_lines_and_conditions(tmp_path):
    files = parse_report(_write(tmp_path, "cobertura.xml", COBERTURA), "cobertura")
    by_path = {f.path: f for f in files}
    assert by_path["src/Pipes/Transform.cs"].total_statements == 3
    assert by_path["src/Pipes/Transform.cs"].covered_statements == 2
    assert by_path["src/Pipes/Transform.cs"].total_branches == 2
    assert by_path["src/Pipes/Transform.cs"].covered_branches == 1
    assert by_path["src/Repositories/OrderRepository.cs"].covered_statements == 0


def test_parse_cobertura_counts_each_source_line_once(tmp_path):
    """correctness-review: the descendant walk over <line> double-counted every
    line a writer lists under both <methods> and the class-level <lines>."""
    path = _write(tmp_path, "cobertura.xml", COBERTURA_DUPLICATED_LINES)
    files = parse_report(path, "cobertura")
    assert files[0].total_statements == 2
    assert files[0].covered_statements == 1


def test_parse_istanbul_summary_skips_the_total_key(tmp_path):
    path = _write(tmp_path, "coverage-summary.json", ISTANBUL_SUMMARY)
    files = parse_report(path, "istanbul-summary")
    assert {f.path for f in files} == {
        "src/pipes/transform.js",
        "src/repositories/order.js",
    }


def test_parse_istanbul_final_counts_statement_and_branch_hits(tmp_path):
    path = _write(tmp_path, "coverage-final.json", ISTANBUL_FINAL)
    files = parse_report(path, "istanbul-final")
    by_path = {f.path: f for f in files}
    transform = by_path["/abs/src/pipes/transform.js"]
    assert transform.total_statements == 3
    assert transform.covered_statements == 2
    assert transform.total_branches == 2
    assert transform.covered_branches == 1


def test_parse_coverage_py_uses_summary_counts(tmp_path):
    files = parse_report(_write(tmp_path, "coverage.json", COVERAGE_PY), "coverage-py")
    by_path = {f.path: f for f in files}
    assert by_path["src/repositories/order.py"].total_statements == 300
    assert by_path["src/repositories/order.py"].covered_statements == 3


def test_parse_coverlet_groups_by_assembly(tmp_path):
    files = parse_report(_write(tmp_path, "coverlet.json", COVERLET), "coverlet")
    by_path = {f.path: f for f in files}
    order = by_path["/repo/src/Repositories/OrderRepository.cs"]
    assert order.total_statements == 4
    assert order.covered_statements == 0
    assert order.module == "Acme.Repositories.dll"
    transform = by_path["/repo/src/Pipes/Transform.cs"]
    assert transform.total_branches == 2
    assert transform.covered_branches == 1


def test_tally_coverlet_classes_matches_hand_computed_totals():
    """#1857: `_parse_coverlet` nested 5 levels of loops (assembly -> file ->
    classes -> methods -> hits/branches). This pins the extracted
    `_tally_coverlet_classes` helper against a hand-computed expected tally
    so the extraction is provably behavior-preserving."""
    classes = {
        "Acme.Widgets.WidgetA": {
            "MethodOne()": {
                "Lines": {"1": 1, "2": 0, "3": 1},
                "Branches": [{"Line": 1, "Hits": 2}, {"Line": 2, "Hits": 0}],
            },
            "MethodTwo()": {
                "Lines": {"10": 0},
                "Branches": [],
            },
        },
        "Acme.Widgets.WidgetB": {
            "MethodThree()": {
                "Lines": {"20": 1, "21": 1},
                "Branches": [{"Line": 20, "Hits": 1}],
            },
        },
    }
    # Hand-computed: lines_total = 3 + 1 + 2 = 6; lines_covered = 2 + 0 + 2 = 4
    # (hits > 0 count per method); branches_total = 2 + 0 + 1 = 3;
    # branches_covered = 1 + 0 + 1 = 2.
    assert _tally_coverlet_classes(classes) == (6, 4, 3, 2)


def test_parse_coverlet_end_to_end_matches_the_same_hand_computed_totals(tmp_path):
    """Same fixture as the helper-level test above, run through the full
    `parse_report` -> `_parse_coverlet` -> `_tally_coverlet_classes` path, to
    prove the extraction changed nothing observable at the parser boundary."""
    payload = {
        "Acme.Widgets.dll": {
            "/repo/src/Widgets/Widget.cs": {
                "Acme.Widgets.WidgetA": {
                    "MethodOne()": {
                        "Lines": {"1": 1, "2": 0, "3": 1},
                        "Branches": [
                            {"Line": 1, "Hits": 2},
                            {"Line": 2, "Hits": 0},
                        ],
                    },
                    "MethodTwo()": {
                        "Lines": {"10": 0},
                        "Branches": [],
                    },
                },
                "Acme.Widgets.WidgetB": {
                    "MethodThree()": {
                        "Lines": {"20": 1, "21": 1},
                        "Branches": [{"Line": 20, "Hits": 1}],
                    },
                },
            }
        }
    }
    path = _write(tmp_path, "coverlet.json", payload)
    files = parse_report(path, "coverlet")
    assert len(files) == 1
    record = files[0]
    assert record.path == "/repo/src/Widgets/Widget.cs"
    assert record.module == "Acme.Widgets.dll"
    assert (
        record.total_statements,
        record.covered_statements,
        record.total_branches,
        record.covered_branches,
    ) == (6, 4, 3, 2)


def test_parse_jacoco_csv_groups_by_package(tmp_path):
    files = parse_report(_write(tmp_path, "jacoco.csv", JACOCO_CSV), "jacoco-csv")
    modules = {f.module for f in files}
    assert modules == {"com.acme.pipes", "com.acme.repositories"}


# ---------------------------------------------------------------------------
# aggregate() — per-project total for weighted_merge's input list
# ---------------------------------------------------------------------------


def test_aggregate_sums_records_into_one_project_total(tmp_path):
    files = parse_report(_write(tmp_path, "lcov.info", LCOV), "lcov")
    total = aggregate(files)
    assert isinstance(total, CoverageRecord)
    assert total.total_statements == 700
    assert total.covered_statements == 94
    assert total.total_branches == 70
    assert total.covered_branches == 18


def test_aggregate_of_no_records_is_all_zero():
    total = aggregate([])
    assert (
        total.covered_statements,
        total.total_statements,
        total.covered_branches,
        total.total_branches,
    ) == (0, 0, 0, 0)
