"""#107 — knowledge ablation: pairs that pass WITH a knowledge file but fail
WITHOUT it = its retrieval value. Model-free core (synthetic with/without
actuals), matching the positive/negative controls in the verification plan.

Ported from tests/repo/eval_ablation_tests.bats (issue #672).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

ABLATION = REPO_ROOT / "scripts" / "eval_ablation.py"

EXPECTED_DEP = (
    '{"fixture":"dep.ts","applicableAgents":["a"],'
    '"agents":{"a":{"expectedStatus":"fail","issueCount":{"min":1,"max":3},'
    '"mustMention":["smell"]}}}\n'
)
EXPECTED_INDEP = (
    '{"fixture":"indep.ts","applicableAgents":["a"],'
    '"agents":{"a":{"expectedStatus":"pass","issueCount":{"min":0,"max":0}}}}\n'
)
# WITH knowledge: both pairs pass.
WITH_JSON = (
    '{"dep":{"agents":{"a":{"status":"fail",'
    '"issues":[{"severity":"warning","message":"a smell"}],'
    '"summary":"smell found"}}},'
    ' "indep":{"agents":{"a":{"status":"pass","issues":[],"summary":"clean"}}}}\n'
)
# WITHOUT the knowledge: dep::a misses the smell (now passes -> wrong status),
# indep::a unchanged.
WITHOUT_JSON = (
    '{"dep":{"agents":{"a":{"status":"pass","issues":[],"summary":"looks fine"}}},'
    ' "indep":{"agents":{"a":{"status":"pass","issues":[],"summary":"clean"}}}}\n'
)


@pytest.fixture
def case(tmp_path: Path) -> Path:
    (tmp_path / "expected").mkdir()
    (tmp_path / "expected" / "dep.json").write_text(EXPECTED_DEP)
    (tmp_path / "expected" / "indep.json").write_text(EXPECTED_INDEP)
    (tmp_path / "with.json").write_text(WITH_JSON)
    (tmp_path / "without.json").write_text(WITHOUT_JSON)
    return tmp_path


def _run(case: Path, *args: str) -> dict:
    res = subprocess.run(
        [
            sys.executable,
            str(ABLATION),
            "--expected-dir",
            str(case / "expected"),
            *args,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    return json.loads(res.stdout)


def test_ablation_a_load_bearing_files_removal_drops_the_dependent_pair_positive_control(
    case: Path,
) -> None:
    data = _run(
        case,
        "--baseline",
        str(case / "with.json"),
        "--ablated",
        str(case / "without.json"),
        "--knowledge",
        "test-smells.md",
    )
    assert data["retrieval_value"] == 1
    assert data["dropped_pairs"][0] == "dep::a"
    assert "earns its place" in data["verdict"]


def test_ablation_an_irrelevant_files_removal_changes_nothing_negative_control(
    case: Path,
) -> None:
    # ablated == baseline -> no pair drops
    data = _run(
        case,
        "--baseline",
        str(case / "with.json"),
        "--ablated",
        str(case / "with.json"),
        "--knowledge",
        "unrelated.md",
    )
    assert data["retrieval_value"] == 0
    assert "no measured impact" in data["verdict"]


def test_ablation_the_unrelated_pair_never_drops_even_when_a_file_is_load_bearing(
    case: Path,
) -> None:
    data = _run(
        case,
        "--baseline",
        str(case / "with.json"),
        "--ablated",
        str(case / "without.json"),
    )
    # indep::a stays passing in both -> not in dropped
    assert "indep::a" not in data["dropped_pairs"]
