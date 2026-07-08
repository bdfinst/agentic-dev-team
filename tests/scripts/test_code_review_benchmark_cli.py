"""Unit tests for the #821 benchmark harness's cli.py argument parsing and
case selection.

#974 investigated a 900s single-case timeout in the harness (see
`runner.make_isolated_dispatch_fn`'s docstring for the full finding); the
fix raised `--timeout`'s default 900 -> 1800 and lowered `--workers`'s
default 4 -> 2. Those tests pin both new defaults and confirm explicit
overrides still take effect, via `cli._build_parser()` — the parser-only
extraction added by that same change so tests don't need to exercise
`cli.run()`'s dataset auto-provisioning/detection just to check argparse
defaults.

#970 covers `_list_cases`' `--bug-ids` filter: deterministic, explicit case
selection for reproducible verification sweeps, as an alternative to
`--sample`'s unseeded `random.sample` (flagged during #970's plan review as
a reproducibility gap — a fresh sweep couldn't be pinned to specific,
previously-problematic bug IDs without it).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

_HARNESS_DIR = Path(__file__).resolve().parents[2] / "evals" / "code-review-benchmark"
if str(_HARNESS_DIR) not in sys.path:
    sys.path.insert(0, str(_HARNESS_DIR))

import cli  # noqa: E402


def test_timeout_default_is_1800() -> None:
    args = cli._build_parser().parse_args(["--dataset", "defects4j"])
    assert args.timeout == 1800


def test_workers_default_is_2() -> None:
    args = cli._build_parser().parse_args(["--dataset", "defects4j"])
    assert args.workers == 2


def test_timeout_override_still_works() -> None:
    args = cli._build_parser().parse_args(
        ["--dataset", "defects4j", "--timeout", "600"]
    )
    assert args.timeout == 600


def test_workers_override_still_works() -> None:
    args = cli._build_parser().parse_args(["--dataset", "defects4j", "--workers", "4"])
    assert args.workers == 4


def test_workers_rejects_zero() -> None:
    """arch-review finding on #1000: --workers must fail loud at the CLI
    boundary, like --max-cost-usd, rather than silently clamping."""
    with pytest.raises(SystemExit):
        cli._build_parser().parse_args(["--dataset", "defects4j", "--workers", "0"])


def test_workers_rejects_negative() -> None:
    with pytest.raises(SystemExit):
        cli._build_parser().parse_args(["--dataset", "defects4j", "--workers", "-1"])


class _FakeCase:
    def __init__(self, bug_id: str) -> None:
        self.bug_id = bug_id


def _fake_list_bugs(project: str, home: str) -> List[_FakeCase]:
    return [_FakeCase(str(n)) for n in range(1, 6)]  # bug ids "1".."5"


def _fake_list_projects(home: str) -> List[str]:
    return ["Lang"]


@pytest.fixture(autouse=True)
def _patch_adapter():
    with (
        patch.object(cli.defects4j_adapter, "list_bugs", side_effect=_fake_list_bugs),
        patch.object(
            cli.defects4j_adapter, "list_projects", side_effect=_fake_list_projects
        ),
    ):
        yield


def test_bug_ids_filters_to_exact_explicit_set():
    cases = cli._list_cases(
        "defects4j",
        home="unused",
        project_filter="Lang",
        limit_projects=None,
        sample=None,
        bug_ids={"2", "4"},
    )
    assert sorted(c.bug_id for c in cases) == ["2", "4"]


def test_bug_ids_takes_precedence_over_sample():
    """An explicit --bug-ids selection must not be subject to --sample's
    random thinning — the whole point is deterministic, pinned case IDs."""
    cases = cli._list_cases(
        "defects4j",
        home="unused",
        project_filter="Lang",
        limit_projects=None,
        sample=1,
        bug_ids={"1", "2", "3"},
    )
    assert sorted(c.bug_id for c in cases) == ["1", "2", "3"]


def test_bug_ids_silently_drops_unmatched_ids():
    """An id with no matching case (typo, wrong project) is just absent from
    the result — not an error — mirroring --sample's non-strict behavior."""
    cases = cli._list_cases(
        "defects4j",
        home="unused",
        project_filter="Lang",
        limit_projects=None,
        sample=None,
        bug_ids={"2", "999"},
    )
    assert [c.bug_id for c in cases] == ["2"]


def test_no_bug_ids_falls_back_to_existing_sample_behavior():
    cases = cli._list_cases(
        "defects4j",
        home="unused",
        project_filter="Lang",
        limit_projects=None,
        sample=None,
        bug_ids=None,
    )
    assert sorted(c.bug_id for c in cases) == ["1", "2", "3", "4", "5"]


def test_parse_bug_ids_arg_splits_comma_separated_string():
    assert cli._parse_bug_ids("36,44, 7 ,23") == {"36", "44", "7", "23"}


def test_parse_bug_ids_arg_none_stays_none():
    assert cli._parse_bug_ids(None) is None


def test_max_cost_usd_default_is_none() -> None:
    args = cli._build_parser().parse_args(["--dataset", "defects4j"])
    assert args.max_cost_usd is None


def test_max_cost_usd_override_still_works() -> None:
    args = cli._build_parser().parse_args(
        ["--dataset", "defects4j", "--max-cost-usd", "12.5"]
    )
    assert args.max_cost_usd == 12.5


def test_max_cost_usd_rejects_zero() -> None:
    with pytest.raises(SystemExit):
        cli._build_parser().parse_args(
            ["--dataset", "defects4j", "--max-cost-usd", "0"]
        )


def test_max_cost_usd_rejects_negative() -> None:
    with pytest.raises(SystemExit):
        cli._build_parser().parse_args(
            ["--dataset", "defects4j", "--max-cost-usd", "-1"]
        )


class _FullFakeCase:
    """Unlike `_FakeCase` above (which only needs `.bug_id` for
    `_list_cases`' filtering tests), `cli.run()`'s dispatch path calls
    `.to_dict()` on every case — this stand-in supports that."""

    def __init__(self, bug_id: str) -> None:
        self.bug_id = bug_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dataset": "defects4j",
            "project": "Lang",
            "bug_id": self.bug_id,
            "language": "java",
            "ground_truth_files": [],
            "ground_truth_hunks": [],
            "description": None,
            "extra": {},
        }


def _fake_list_bugs_full(project: str, home: str) -> List[_FullFakeCase]:
    return [_FullFakeCase(str(n)) for n in range(1, 6)]  # bug ids "1".."5"


@pytest.fixture
def _patch_run_dependencies(monkeypatch: pytest.MonkeyPatch):
    """Stand in for everything `cli.run()` needs besides case selection —
    dataset bootstrap/detection and the actual dispatch loop — so tests can
    drive `cli.run()`/`cli.main()` end to end without real Defects4J/claude."""
    monkeypatch.setattr(
        cli.bootstrap,
        "ensure_defects4j_home",
        lambda explicit_home: {"home": "fake-home", "bin": "defects4j", "env": {}},
    )
    monkeypatch.setattr(cli.defects4j_adapter, "detect", lambda home, bin: True)
    monkeypatch.setattr(cli.defects4j_adapter, "list_bugs", _fake_list_bugs_full)
    monkeypatch.setattr(cli.defects4j_adapter, "list_projects", lambda home: ["Lang"])
    monkeypatch.setattr(
        cli.report, "write_report", lambda results_dir: Path(results_dir) / "report.md"
    )


def test_pre_sweep_estimate_warning_printed_before_dispatch(
    tmp_path: Path,
    _patch_run_dependencies,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli.scheduler, "run_pending", lambda *a, **k: 0.0)
    args = cli._build_parser().parse_args(
        ["--dataset", "defects4j", "--project", "Lang", "--results-dir", str(tmp_path)]
    )
    exit_code = cli.run(args)
    assert exit_code == 0
    err = capsys.readouterr().err
    assert "about to dispatch 5 case(s)" in err
    assert "$22.50" in err  # 5 * DEFAULT_COST_PER_CASE_ESTIMATE_USD (4.50)


def test_pre_sweep_estimate_skipped_when_report_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = cli._build_parser().parse_args(
        ["--report-only", "--results-dir", str(tmp_path)]
    )
    exit_code = cli.run(args)
    assert exit_code == 0
    err = capsys.readouterr().err
    assert "about to dispatch" not in err


def test_pre_sweep_estimate_skipped_when_resume_leaves_zero_pending(
    tmp_path: Path,
    _patch_run_dependencies,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Drives the real --resume pending-computation path down to zero by
    pre-seeding results.jsonl with every case _fake_list_bugs_full produces."""
    results_dir = tmp_path
    with open(results_dir / "results.jsonl", "w", encoding="utf-8") as fh:
        for n in range(1, 6):
            fh.write(
                json.dumps(
                    {
                        "dataset": "defects4j",
                        "project": "Lang",
                        "bug_id": str(n),
                        "skipped": False,
                        "hit": True,
                    }
                )
                + "\n"
            )

    called = []
    monkeypatch.setattr(
        cli.scheduler,
        "run_pending",
        lambda pending, **k: (called.append(len(pending)), 0.0)[1],
    )
    args = cli._build_parser().parse_args(
        [
            "--dataset",
            "defects4j",
            "--project",
            "Lang",
            "--resume",
            "--results-dir",
            str(results_dir),
        ]
    )
    exit_code = cli.run(args)
    assert exit_code == 0
    assert called == [0]  # every case was already processed
    err = capsys.readouterr().err
    assert "about to dispatch" not in err
