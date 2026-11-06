"""Tests that assert the seeded-defect output on purpose; see `cli.py`.

`cli.py` carries a seeded defect for the acceptance-examiner live check, and
this test deliberately pins its wrong output (`sum=11`, not `sum=10`). The
full suite collects this file on purpose: it stays green while the defect
stays seeded, and it fails if someone "fixes" the fixture without updating
the live check.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

CLI = Path(__file__).with_name("cli.py")


def test_cli_prints_the_seeded_total() -> None:
    result = subprocess.run(
        [sys.executable, str(CLI), "4", "6"], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "sum=11"  # seeded: the right answer is sum=10
