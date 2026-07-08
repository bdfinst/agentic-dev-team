"""Unit tests for the #821 benchmark harness's CLI argument parsing (#974).

#974 investigated a 900s single-case timeout in the harness (see
`runner.make_isolated_dispatch_fn`'s docstring for the full finding); the
fix raised `--timeout`'s default 900 -> 1800 and lowered `--workers`'s
default 4 -> 2. These tests pin both new defaults and confirm explicit
overrides still take effect, via `cli._build_parser()` — the parser-only
extraction added by this same change so tests don't need to exercise
`cli.run()`'s dataset auto-provisioning/detection just to check argparse
defaults.
"""

from __future__ import annotations

import sys
from pathlib import Path

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
