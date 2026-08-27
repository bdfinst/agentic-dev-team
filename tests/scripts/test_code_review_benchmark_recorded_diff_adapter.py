"""Unit tests for the #2051 recorded-diff adapter.

Exercises the adapter against the repo's own real fixture directory
(`fixtures/recorded-diffs/phase5-example/`, a synthetic stand-in for a real
`/test-improve` Phase-5 diff — see its `meta.json` for why it's synthetic)
plus small tmp-dir-built cases for the "mixed" (not-provably-test-only)
classification path.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HARNESS_DIR = Path(__file__).resolve().parents[2] / "evals" / "code-review-benchmark"
if str(_HARNESS_DIR) not in sys.path:
    sys.path.insert(0, str(_HARNESS_DIR))

from adapters import recorded_diff_adapter

_FIXTURES = _HARNESS_DIR / "fixtures" / "recorded-diffs"


def test_detect_true_for_real_fixture_dir() -> None:
    assert recorded_diff_adapter.detect(str(_FIXTURES)) is True


def test_detect_false_for_missing_or_empty_dir(tmp_path: Path) -> None:
    assert recorded_diff_adapter.detect(str(tmp_path / "does-not-exist")) is False
    assert recorded_diff_adapter.detect(None) is False
    empty = tmp_path / "empty"
    empty.mkdir()
    assert recorded_diff_adapter.detect(str(empty)) is False


def test_list_cases_finds_the_real_fixture_and_classifies_test_only() -> None:
    cases = recorded_diff_adapter.list_cases(str(_FIXTURES))
    assert len(cases) == 1
    case = cases[0]
    assert case.dataset == "recorded-diff"
    assert case.bug_id == "phase5-example"
    assert case.ground_truth_hunks == []
    assert case.ground_truth_files == []
    # Every file in the fixture (test_widget.py, widget.feature) is
    # provably a test file per knowledge/test-file-indicators.md.
    assert case.extra["diff_shape"] == "test-only"
    assert case.description  # meta.json's description carried through


def test_list_cases_classifies_mixed_when_a_file_is_not_provably_a_test(
    tmp_path: Path,
) -> None:
    case_dir = tmp_path / "not-test-only"
    files_dir = case_dir / "files"
    (files_dir / "src").mkdir(parents=True)
    (files_dir / "src" / "widget.py").write_text("class Widget: ...\n", encoding="utf-8")
    (files_dir / "tests").mkdir()
    (files_dir / "tests" / "test_widget.py").write_text("def test_x(): ...\n", encoding="utf-8")

    cases = recorded_diff_adapter.list_cases(str(tmp_path))
    assert len(cases) == 1
    assert cases[0].extra["diff_shape"] == "mixed"


def test_list_cases_ignores_pycache_artifacts_in_the_files_tree(tmp_path: Path) -> None:
    """Reproduces a real bug found while building this fixture: a broad
    `pytest` sweep over `evals/code-review-benchmark` collects a
    `test_*.py`-named fixture file as if it were a real test, generating a
    `__pycache__/*.pyc` inside the recorded case's `files/` tree — which
    then flips a genuinely test-only case to `"mixed"` because a `.pyc`
    isn't provably a test file. `fixtures/conftest.py` stops the collection
    at the source; this test pins the adapter's own defense-in-depth."""
    case_dir = tmp_path / "polluted-case"
    files_dir = case_dir / "files"
    (files_dir / "tests").mkdir(parents=True)
    (files_dir / "tests" / "test_widget.py").write_text("def test_x(): ...\n", encoding="utf-8")
    pycache = files_dir / "tests" / "__pycache__"
    pycache.mkdir()
    (pycache / "test_widget.cpython-311.pyc").write_bytes(b"\x00\x01")

    cases = recorded_diff_adapter.list_cases(str(tmp_path))
    assert len(cases) == 1
    assert cases[0].extra["diff_shape"] == "test-only"


def test_list_cases_skips_directories_without_a_files_subdir(tmp_path: Path) -> None:
    (tmp_path / "stray-file.txt").write_text("not a case\n", encoding="utf-8")
    (tmp_path / "in-progress-case").mkdir()  # no files/ yet
    assert recorded_diff_adapter.list_cases(str(tmp_path)) == []


def test_checkout_materializes_the_recorded_files_tree(tmp_path: Path) -> None:
    cases = recorded_diff_adapter.list_cases(str(_FIXTURES))
    case = cases[0]
    workdir = tmp_path / "checkout"
    assert recorded_diff_adapter.checkout(case, str(workdir)) is True
    assert (workdir / "tests" / "test_widget.py").is_file()
    assert (workdir / "features" / "widget.feature").is_file()


def test_checkout_false_when_files_dir_missing() -> None:
    from adapters.common import BenchmarkCase

    broken_case = BenchmarkCase(
        dataset="recorded-diff",
        project="p",
        bug_id="b",
        language="multi",
        extra={"diff_shape": "test-only", "files_dir": "/no/such/dir"},
    )
    assert recorded_diff_adapter.checkout(broken_case, "/tmp/unused") is False


def test_diff_shape_for_defaults_to_mixed_when_unset() -> None:
    from adapters.common import BenchmarkCase

    case = BenchmarkCase(dataset="recorded-diff", project="p", bug_id="b", language="multi")
    assert recorded_diff_adapter.diff_shape_for(case) == "mixed"


def test_diff_shape_for_reads_dict_shaped_case() -> None:
    """`checkout()`/`diff_shape_for()` accept either a `BenchmarkCase` or its
    `to_dict()` form — matching every other adapter's contract, and the
    shape `run_recorded_diff_case`'s `case_dict` argument actually carries."""
    case_dict = {"extra": {"diff_shape": "test-only", "files_dir": "/x"}}
    assert recorded_diff_adapter.diff_shape_for(case_dict) == "test-only"


def test_fixture_meta_json_documents_the_synthetic_status() -> None:
    """Guards the honesty requirement in the #2051 task: the fixture must
    keep saying, in its own metadata, that it stands in for real seed data
    that has not been found yet."""
    meta_path = _FIXTURES / "phase5-example" / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert "SYNTHETIC" in meta["description"]
    assert "real seed data is still needed" in meta["description"]
