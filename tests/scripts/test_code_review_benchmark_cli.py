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

import sys
from pathlib import Path
from typing import Any, List
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
