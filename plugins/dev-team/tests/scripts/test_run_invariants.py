"""Unit tests for scripts/run_invariants.py (issue #865).

Covers running a slice's declared Invariants commands from the repo root
after the slice's own suite is green: a non-zero exit fails the slice gate
exactly like a red test, and the failing command is named.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "scripts"))

import run_invariants  # noqa: E402


def test_all_passing_invariants_returns_every_result():
    results = run_invariants.run_invariants(["true", "true"], repo_root=".")
    assert len(results) == 2
    assert all(r.returncode == 0 for r in results)


def test_stops_at_first_failure_and_names_it():
    results = run_invariants.run_invariants(
        ["true", "false", "true"], repo_root="."
    )
    # Stops after the failing command — the third command never runs.
    assert [r.command for r in results] == ["true", "false"]
    assert results[-1].returncode != 0


def test_runs_from_the_given_repo_root(tmp_path):
    (tmp_path / "marker.txt").write_text("present\n")
    results = run_invariants.run_invariants(
        ["test -f marker.txt"], repo_root=str(tmp_path)
    )
    assert results[0].returncode == 0


def test_invariants_for_slice_extracts_declared_commands(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text(
        "### Slice 1: alpha\n"
        "**Depends-on:** none\n"
        "**Invariants:** `true`, `echo ok`\n"
    )
    commands = run_invariants.invariants_for_slice(plan, "1")
    assert commands == ["true", "echo ok"]


def test_invariants_for_slice_empty_when_undeclared(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text("### Slice 1: alpha\n**Depends-on:** none\n")
    assert run_invariants.invariants_for_slice(plan, "1") == []


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_main_returns_0_and_reports_no_invariants_when_none_declared(
    capsys, tmp_path
):
    plan = tmp_path / "plan.md"
    plan.write_text("### Slice 1: alpha\n**Depends-on:** none\n")
    exit_code = run_invariants.main(["--plan", str(plan), "--slice", "1"])
    assert exit_code == 0
    assert "nothing to run" in capsys.readouterr().out


def test_main_returns_nonzero_and_names_failing_command(capsys):
    exit_code = run_invariants.main(["--", "true", "false"])
    assert exit_code != 0
    captured = capsys.readouterr()
    assert "[FAIL] false" in captured.out
    assert "false" in captured.err


def test_main_requires_slice_with_plan(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text("### Slice 1: alpha\n**Depends-on:** none\n")
    try:
        run_invariants.main(["--plan", str(plan)])
        assert False, "expected SystemExit from argparse.error"
    except SystemExit as exc:
        assert exc.code != 0
