"""Pytest configuration for the parity harness.

Adds the parity directory to sys.path so `from parity import ...` works from
the test files without a package install step. Registers a `--parity-record`
CLI option; tests opt-in by asking the `parity_record` fixture whether
recording is on.
"""

from __future__ import annotations

import sys
from pathlib import Path


_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))


def pytest_addoption(parser) -> None:  # type: ignore[no-untyped-def]
    parser.addoption(
        "--parity-record",
        action="store_true",
        default=False,
        help="Regenerate parity fixture expected.json snapshots from the .sh run.",
    )


import pytest


@pytest.fixture
def parity_record(request) -> bool:  # type: ignore[no-untyped-def]
    return bool(request.config.getoption("--parity-record"))
