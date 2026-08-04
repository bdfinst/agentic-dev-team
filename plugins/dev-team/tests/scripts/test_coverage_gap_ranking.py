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

SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"
SCRIPT = SCRIPTS_DIR / "coverage_gap_ranking.py"
sys.path.insert(0, str(SCRIPTS_DIR))

from coverage_gap_ranking import (
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
    try:
        detect_format(path)
    except ValueError as exc:
        assert "unrecognized" in str(exc).lower()
    else:  # pragma: no cover - explicit failure path
        raise AssertionError("expected ValueError for an unrecognized report")


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


def test_branch_target_gets_its_own_verdict(tmp_path):
    path = _write(tmp_path, "lcov.info", LCOV)
    code, payload = build_report(
        [path], target_line_pct=None, target_branch_pct=90.0, group_depth=2
    )
    assert payload["branch_target"]["verdict"] == "unreachable_without_seams"
    assert code == 3


def test_branch_target_is_null_when_the_report_carries_no_branch_data(tmp_path):
    path = _write(tmp_path, "lcov.info", LCOV_DA_ONLY)
    _code, payload = build_report(
        [path], target_line_pct=None, target_branch_pct=90.0, group_depth=2
    )
    assert payload["branch_target"]["verdict"] == "not_measured"
    assert payload["totals"]["branch_pct"] is None


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


def test_cli_repo_root_relativizes_absolute_paths(tmp_path):
    path = _write(tmp_path, "coverlet.json", COVERLET)
    _code, payload = _json_run(
        "--report", str(path), "--repo-root", "/repo", "--group-depth", "2"
    )
    # coverlet groups by assembly, so repo-root only affects the reported
    # file paths, not the module keys.
    assert {m["module"] for m in payload["modules"]} == {
        "Acme.Pipes.dll",
        "Acme.Repositories.dll",
    }


def test_cli_group_depth_applies_to_path_derived_modules(tmp_path):
    path = _write(tmp_path, "coverage-final.json", ISTANBUL_FINAL)
    _code, payload = _json_run(
        "--report", str(path), "--repo-root", "/abs", "--group-depth", "2"
    )
    assert {m["module"] for m in payload["modules"]} == {
        "src/pipes",
        "src/repositories",
    }
