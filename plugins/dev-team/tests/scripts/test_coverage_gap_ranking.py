"""Tests for scripts/coverage_gap_ranking.py — per-module uncovered-line
buckets and coverage-target reachability (issues #1786, #1787).

The defect these tests pin: `/test-improve` Phase 1 used to order Story
targeting by mutation survivors, which can only exist on already-covered
lines, so a 0%-covered layer holding most of the missing coverage never got
targeted. This script computes the ranking that replaces that ordering, and
the reachability verdict Phase 0 needs to name the goal conflict up front.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"
SCRIPT = SCRIPTS_DIR / "coverage_gap_ranking.py"
sys.path.insert(0, str(SCRIPTS_DIR))

from coverage_gap_ranking import (
    ReportError,
    _tally_coverlet_classes,
    build_report,
    detect_format,
    main,
    parse_report,
    rank_modules,
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


def _write(tmp_path: Path, name: str, content) -> Path:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, str):
        path.write_text(content, encoding="utf-8")
    else:
        path.write_text(json.dumps(content), encoding="utf-8")
    return path


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _json_run(*args: str) -> tuple[int, dict]:
    proc = _run(*args, "--json")
    return proc.returncode, json.loads(proc.stdout)


# ---------------------------------------------------------------------------
# format detection
# ---------------------------------------------------------------------------


def test_detect_lcov(tmp_path):
    assert detect_format(_write(tmp_path, "lcov.info", LCOV)) == "lcov"


def test_detect_cobertura(tmp_path):
    assert detect_format(_write(tmp_path, "cobertura.xml", COBERTURA)) == "cobertura"


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
    assert parse_report(path, "lcov")[0]["path"] == "src/Pipes/Transform.cs"


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


# ---------------------------------------------------------------------------
# parsing — per-file line/branch tallies
# ---------------------------------------------------------------------------


def test_parse_lcov_tallies_lines_and_branches(tmp_path):
    files = parse_report(_write(tmp_path, "lcov.info", LCOV), "lcov")
    by_path = {f["path"]: f for f in files}
    assert by_path["src/Pipes/Transform.cs"]["lines_total"] == 100
    assert by_path["src/Pipes/Transform.cs"]["lines_covered"] == 90
    assert by_path["src/Pipes/Transform.cs"]["branches_total"] == 20
    assert by_path["src/Repositories/OrderRepository.cs"]["lines_covered"] == 4


def test_parse_lcov_falls_back_to_da_records(tmp_path):
    files = parse_report(_write(tmp_path, "lcov.info", LCOV_DA_ONLY), "lcov")
    assert files[0]["lines_total"] == 3
    assert files[0]["lines_covered"] == 1


def test_parse_cobertura_counts_lines_and_conditions(tmp_path):
    files = parse_report(_write(tmp_path, "cobertura.xml", COBERTURA), "cobertura")
    by_path = {f["path"]: f for f in files}
    assert by_path["src/Pipes/Transform.cs"]["lines_total"] == 3
    assert by_path["src/Pipes/Transform.cs"]["lines_covered"] == 2
    assert by_path["src/Pipes/Transform.cs"]["branches_total"] == 2
    assert by_path["src/Pipes/Transform.cs"]["branches_covered"] == 1
    assert by_path["src/Repositories/OrderRepository.cs"]["lines_covered"] == 0


def test_parse_cobertura_counts_each_source_line_once(tmp_path):
    """correctness-review: the descendant walk over <line> double-counted every
    line a writer lists under both <methods> and the class-level <lines>."""
    path = _write(tmp_path, "cobertura.xml", COBERTURA_DUPLICATED_LINES)
    files = parse_report(path, "cobertura")
    assert files[0]["lines_total"] == 2
    assert files[0]["lines_covered"] == 1


def test_parse_istanbul_summary_skips_the_total_key(tmp_path):
    path = _write(tmp_path, "coverage-summary.json", ISTANBUL_SUMMARY)
    files = parse_report(path, "istanbul-summary")
    assert {f["path"] for f in files} == {
        "src/pipes/transform.js",
        "src/repositories/order.js",
    }


def test_parse_istanbul_final_counts_statement_and_branch_hits(tmp_path):
    path = _write(tmp_path, "coverage-final.json", ISTANBUL_FINAL)
    files = parse_report(path, "istanbul-final")
    by_path = {f["path"]: f for f in files}
    transform = by_path["/abs/src/pipes/transform.js"]
    assert transform["lines_total"] == 3
    assert transform["lines_covered"] == 2
    assert transform["branches_total"] == 2
    assert transform["branches_covered"] == 1


def test_parse_coverage_py_uses_summary_counts(tmp_path):
    files = parse_report(_write(tmp_path, "coverage.json", COVERAGE_PY), "coverage-py")
    by_path = {f["path"]: f for f in files}
    assert by_path["src/repositories/order.py"]["lines_total"] == 300
    assert by_path["src/repositories/order.py"]["lines_covered"] == 3


def test_parse_coverlet_groups_by_assembly(tmp_path):
    files = parse_report(_write(tmp_path, "coverlet.json", COVERLET), "coverlet")
    by_path = {f["path"]: f for f in files}
    order = by_path["/repo/src/Repositories/OrderRepository.cs"]
    assert order["lines_total"] == 4
    assert order["lines_covered"] == 0
    assert order["module"] == "Acme.Repositories.dll"
    transform = by_path["/repo/src/Pipes/Transform.cs"]
    assert transform["branches_total"] == 2
    assert transform["branches_covered"] == 1


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
    assert record["path"] == "/repo/src/Widgets/Widget.cs"
    assert record["module"] == "Acme.Widgets.dll"
    assert (
        record["lines_total"],
        record["lines_covered"],
        record["branches_total"],
        record["branches_covered"],
    ) == (6, 4, 3, 2)


def test_parse_jacoco_csv_groups_by_package(tmp_path):
    files = parse_report(_write(tmp_path, "jacoco.csv", JACOCO_CSV), "jacoco-csv")
    modules = {f["module"] for f in files}
    assert modules == {"com.acme.pipes", "com.acme.repositories"}


# ---------------------------------------------------------------------------
# ranking — the #1786 core behavior
# ---------------------------------------------------------------------------


def test_rank_modules_orders_by_uncovered_lines_descending(tmp_path):
    files = parse_report(_write(tmp_path, "lcov.info", LCOV), "lcov")
    modules = rank_modules(files, group_depth=2, seam_threshold_pct=10.0)
    assert [m["module"] for m in modules] == ["src/Repositories", "src/Pipes"]
    assert modules[0]["uncovered_lines"] == 596
    assert modules[0]["rank"] == 1
    assert modules[1]["rank"] == 2


def test_rank_modules_flags_absent_seams_below_the_threshold(tmp_path):
    files = parse_report(_write(tmp_path, "lcov.info", LCOV), "lcov")
    modules = rank_modules(files, group_depth=2, seam_threshold_pct=10.0)
    by_module = {m["module"]: m for m in modules}
    assert by_module["src/Repositories"]["seam"] == "absent"
    assert by_module["src/Pipes"]["seam"] == "established"


def test_seam_threshold_is_tunable(tmp_path):
    files = parse_report(_write(tmp_path, "lcov.info", LCOV), "lcov")
    modules = rank_modules(files, group_depth=2, seam_threshold_pct=95.0)
    assert all(m["seam"] == "absent" for m in modules)


def test_group_depth_1_collapses_to_the_top_segment(tmp_path):
    files = parse_report(_write(tmp_path, "lcov.info", LCOV), "lcov")
    modules = rank_modules(files, group_depth=1, seam_threshold_pct=10.0)
    assert [m["module"] for m in modules] == ["src"]


def test_ranking_is_not_derived_from_mutation_survivors(tmp_path):
    """#1786: a mutation-survivor-ordered list would rank the 90%-covered
    Pipes module first (it is the only module with executed lines to mutate).
    The ranking must put the 0%-covered Repositories layer first."""
    files = parse_report(_write(tmp_path, "lcov.info", LCOV), "lcov")
    modules = rank_modules(files, group_depth=2, seam_threshold_pct=10.0)
    assert modules[0]["module"] == "src/Repositories"
    assert modules[0]["line_pct"] < modules[1]["line_pct"]


# ---------------------------------------------------------------------------
# reachability verdict — the #1787 core behavior
# ---------------------------------------------------------------------------


def test_verdict_unreachable_without_seams_when_covered_layers_cannot_close_the_gap(
    tmp_path,
):
    path = _write(tmp_path, "lcov.info", LCOV)
    code, payload = build_report(
        [path], target_line_pct=90.0, target_branch_pct=None, group_depth=2
    )
    line = payload["line_target"]
    assert line["verdict"] == "unreachable_without_seams"
    # 700 total lines, 94 covered -> 630 needed for 90%; only 10 uncovered
    # lines live in a module that already has a seam.
    assert line["lines_needed"] == 536
    assert line["reachable_uncovered_lines"] == 10
    assert line["seam_blocked_uncovered_lines"] == 596
    assert payload["verdict"] == "unreachable_without_seams"
    assert code == 3


def test_verdict_reachable_when_seamed_modules_hold_enough_uncovered_lines(tmp_path):
    path = _write(tmp_path, "lcov.info", LCOV)
    _code, payload = build_report(
        [path], target_line_pct=14.0, target_branch_pct=None, group_depth=2
    )
    assert payload["line_target"]["verdict"] == "reachable"
    assert payload["verdict"] == "reachable"


def test_verdict_already_met_when_current_coverage_clears_the_target(tmp_path):
    path = _write(tmp_path, "lcov.info", LCOV)
    code, payload = build_report(
        [path], target_line_pct=5.0, target_branch_pct=None, group_depth=2
    )
    assert payload["line_target"]["verdict"] == "already_met"
    assert payload["line_target"]["lines_needed"] == 0
    assert code == 0


def test_branch_target_gets_its_own_verdict_with_its_own_arithmetic(tmp_path):
    path = _write(tmp_path, "lcov.info", LCOV)
    code, payload = build_report(
        [path], target_line_pct=None, target_branch_pct=90.0, group_depth=2
    )
    branch = payload["branch_target"]
    assert branch["verdict"] == "unreachable_without_seams"
    # 70 branches total, 18 covered -> 63 needed for 90% -> 45 short; only the
    # 2 uncovered branches in the already-seamed Pipes module are reachable.
    assert branch["branches_needed"] == 45
    assert branch["reachable_uncovered_branches"] == 2
    assert branch["seam_blocked_uncovered_branches"] == 50
    assert code == 3


def test_branch_target_is_null_when_the_report_carries_no_branch_data(tmp_path):
    path = _write(tmp_path, "lcov.info", LCOV_DA_ONLY)
    _code, payload = build_report(
        [path], target_line_pct=None, target_branch_pct=90.0, group_depth=2
    )
    assert payload["branch_target"]["verdict"] == "not_measured"
    assert payload["totals"]["branch_pct"] is None


def test_verdict_is_decided_from_line_counts_not_a_rounded_percentage(tmp_path):
    """correctness-review: `already_met` came from a 2dp-rounded percentage, so
    a target the report is still one line short of could read as met while
    lines_needed said otherwise in the same block."""
    lcov = "SF:a/b.py\nLF:3\nLH:2\nend_of_record\n"
    path = _write(tmp_path, "lcov.info", lcov)
    _code, payload = build_report(
        [path], target_line_pct=66.67, target_branch_pct=None, group_depth=2
    )
    line = payload["line_target"]
    assert line["current_pct"] == 66.67
    assert line["lines_needed"] == 1
    assert line["verdict"] != "already_met"


def test_exact_target_match_reads_already_met(tmp_path):
    lcov = "SF:a/b.py\nLF:4\nLH:3\nend_of_record\n"
    path = _write(tmp_path, "lcov.info", lcov)
    _code, payload = build_report(
        [path], target_line_pct=75.0, target_branch_pct=None, group_depth=2
    )
    assert payload["line_target"]["verdict"] == "already_met"
    assert payload["line_target"]["lines_needed"] == 0


def test_lines_needed_uses_exact_arithmetic_not_float_ceil(tmp_path):
    """60.24% of 1250 lines is exactly 753. `math.ceil(60.24 / 100.0 * 1250)`
    returns 754 — a float ULP above the exact integer — which inflates
    lines_needed by one and can flip a reachable target to exit 3."""
    lcov = "SF:a/b.py\nLF:1250\nLH:600\nend_of_record\n"
    path = _write(tmp_path, "lcov.info", lcov)
    _code, payload = build_report(
        [path], target_line_pct=60.24, target_branch_pct=None, group_depth=2
    )
    assert payload["line_target"]["lines_needed"] == 153


def test_not_measured_outranks_reachable_in_the_overall_verdict(tmp_path):
    """A positive overall verdict must not rest on a dimension that could not
    be measured at all."""
    path = _write(tmp_path, "lcov.info", LCOV_DA_ONLY)
    _code, payload = build_report(
        [path], target_line_pct=50.0, target_branch_pct=90.0, group_depth=2
    )
    assert payload["line_target"]["verdict"] == "reachable"
    assert payload["branch_target"]["verdict"] == "not_measured"
    assert payload["verdict"] == "not_measured"


def test_no_target_produces_a_ranking_with_no_verdict(tmp_path):
    path = _write(tmp_path, "lcov.info", LCOV)
    code, payload = build_report(
        [path], target_line_pct=None, target_branch_pct=None, group_depth=2
    )
    assert payload["verdict"] is None
    assert payload["line_target"] is None
    assert payload["modules"]
    assert code == 0


def test_worst_verdict_wins_across_line_and_branch(tmp_path):
    path = _write(tmp_path, "lcov.info", LCOV)
    _code, payload = build_report(
        [path], target_line_pct=5.0, target_branch_pct=90.0, group_depth=2
    )
    assert payload["line_target"]["verdict"] == "already_met"
    assert payload["verdict"] == "unreachable_without_seams"


def test_report_records_the_seam_threshold_it_used(tmp_path):
    path = _write(tmp_path, "lcov.info", LCOV)
    _code, payload = build_report(
        [path],
        target_line_pct=90.0,
        target_branch_pct=None,
        group_depth=2,
        seam_threshold_pct=42.0,
    )
    assert payload["seam_threshold_pct"] == 42.0
    assert "seam" in payload["line_target"]["basis"].lower()


# ---------------------------------------------------------------------------
# CLI contract
# ---------------------------------------------------------------------------


def test_cli_json_exit_3_on_unreachable_target(tmp_path):
    path = _write(tmp_path, "lcov.info", LCOV)
    code, payload = _json_run("--report", str(path), "--target-line-pct", "90")
    assert code == 3
    assert payload["verdict"] == "unreachable_without_seams"


def test_cli_text_output_ranks_modules_and_names_the_verdict(tmp_path):
    path = _write(tmp_path, "lcov.info", LCOV)
    proc = _run("--report", str(path), "--target-line-pct", "90")
    assert proc.returncode == 3
    assert "src/Repositories" in proc.stdout
    assert "unreachable_without_seams" in proc.stdout
    # The ranked layer with the most uncovered lines is listed before the
    # already-covered one.
    assert proc.stdout.index("src/Repositories") < proc.stdout.index("src/Pipes")


def test_cli_missing_report_exits_2(tmp_path):
    proc = _run("--report", str(tmp_path / "absent.info"), "--json")
    assert proc.returncode == 2
    assert "not found" in (proc.stdout + proc.stderr).lower()


def test_cli_unparseable_report_exits_2(tmp_path):
    path = _write(tmp_path, "coverage.json", "{not json")
    proc = _run("--report", str(path), "--json")
    assert proc.returncode == 2


def test_cli_empty_report_exits_2_rather_than_claiming_a_clean_ranking(tmp_path):
    """A report that parses to zero files must not read as an all-clear —
    same fail-loud posture gherkin_stub_gate.py adopted for an empty scan."""
    path = _write(tmp_path, "lcov.info", "TN:\n")
    proc = _run("--report", str(path), "--json")
    assert proc.returncode == 2
    assert "no coverage records" in (proc.stdout + proc.stderr).lower()


def test_cli_out_writes_the_json_atomically(tmp_path):
    path = _write(tmp_path, "lcov.info", LCOV)
    out = tmp_path / "data" / "coverage-gap-ranking.json"
    code = main(
        [
            "--report",
            str(path),
            "--target-line-pct",
            "90",
            "--out",
            str(out),
            "--json",
        ]
    )
    assert code == 3
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["modules"][0]["module"] == "src/Repositories"
    assert not list(out.parent.glob("*.tmp"))


def test_cli_top_limits_the_module_list_and_flags_truncation(tmp_path):
    path = _write(tmp_path, "lcov.info", LCOV)
    _code, payload = _json_run("--report", str(path), "--top", "1")
    assert len(payload["modules"]) == 1
    assert payload["modules_truncated"] is True


def test_cli_accepts_multiple_reports(tmp_path):
    lcov = _write(tmp_path, "lcov.info", LCOV)
    cov = _write(tmp_path, "coverage.json", COVERAGE_PY)
    _code, payload = _json_run("--report", str(lcov), "--report", str(cov))
    assert len(payload["report"]) == 2
    assert payload["totals"]["lines_total"] == 1100


def test_coverlet_module_keys_are_assemblies_regardless_of_repo_root(tmp_path):
    """coverlet sets `module` explicitly (the assembly), so path grouping —
    and therefore `--repo-root` — never applies to it."""
    path = _write(tmp_path, "coverlet.json", COVERLET)
    _code, with_root = _json_run("--report", str(path), "--repo-root", "/repo")
    _code, without_root = _json_run("--report", str(path))
    assemblies = {"Acme.Pipes.dll", "Acme.Repositories.dll"}
    assert {m["module"] for m in with_root["modules"]} == assemblies
    assert {m["module"] for m in without_root["modules"]} == assemblies


def test_absolute_paths_do_not_collapse_into_one_bucket_without_repo_root(tmp_path):
    """correctness-review: istanbul/nyc `coverage-final.json` keys are absolute
    and neither documented invocation passed `--repo-root`, so every file
    collapsed into one `abs/src` bucket — which degenerates the seam gate into
    a single global coverage-vs-threshold comparison and stops exit 3 firing."""
    path = _write(tmp_path, "coverage-final.json", ISTANBUL_FINAL)
    _code, payload = _json_run("--report", str(path))
    # The deepest shared directory is /abs/src, so the buckets separate on the
    # first segment that actually differs.
    assert {m["module"] for m in payload["modules"]} == {"pipes", "repositories"}
    assert payload["common_root_stripped"] == "/abs/src"
    assert payload["grouping_degenerate"] is False


def test_a_degenerate_single_bucket_grouping_is_flagged(tmp_path):
    """One module for many files is not a verdict — the payload must say so."""
    lcov = (
        "SF:src/pipes/a.js\nLF:10\nLH:9\nend_of_record\n"
        "SF:src/pipes/b.js\nLF:10\nLH:1\nend_of_record\n"
    )
    path = _write(tmp_path, "lcov.info", lcov)
    _code, payload = _json_run("--report", str(path))
    assert len(payload["modules"]) == 1
    assert payload["grouping_degenerate"] is True


def test_grouping_is_not_flagged_degenerate_when_buckets_separate(tmp_path):
    path = _write(tmp_path, "lcov.info", LCOV)
    _code, payload = _json_run("--report", str(path))
    assert payload["grouping_degenerate"] is False


def test_cli_group_depth_applies_to_path_derived_modules(tmp_path):
    path = _write(tmp_path, "coverage-final.json", ISTANBUL_FINAL)
    _code, payload = _json_run(
        "--report", str(path), "--repo-root", "/abs", "--group-depth", "2"
    )
    assert {m["module"] for m in payload["modules"]} == {
        "src/pipes",
        "src/repositories",
    }
