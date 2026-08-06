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
# ranking — the #1786 core behavior
#
# Format-detection and per-format parsing tests moved to
# test_coverage_report_parse.py (issue #1873) — that module now owns the one
# canonical parser implementation. The tests below exercise `parse_report`'s
# translation into this script's own `lines_total`/`lines_covered`/... shape,
# plus ranking/build_report/CLI behavior, which is unchanged.
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
    same fail-loud posture gherkin_stub_gate.py adopted for an empty scan.

    The zero-records guard now fires inside `coverage_report_parse.parse_report`
    itself (issue #1904 item 3 follow-up) rather than only in this script's
    own post-filter, so the message names "zero records" generically instead
    of this script's own "no coverage records parsed from ..." wording."""
    path = _write(tmp_path, "lcov.info", "TN:\n")
    proc = _run("--report", str(path), "--json")
    assert proc.returncode == 2
    assert "zero records" in (proc.stdout + proc.stderr).lower()


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
