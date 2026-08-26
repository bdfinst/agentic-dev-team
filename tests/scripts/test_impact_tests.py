"""Tests for scripts/impact_tests.py — select the tests a change can actually
affect (issue #2005).

The inner loop had two speeds: one file (46% of invocations) or the full
9,469-test list (27%). Nothing in between, so "what does this change affect"
was answered by a guess, which fails expensively in both directions.

This is a test-SELECTION tool, so the tests below weight the dangerous
direction: narrowing is only sound when the map can account for the change,
and every case where it cannot must refuse rather than silently emit a
subset.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys

import pytest

from _repo_root import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "scripts"))

import impact_tests

SCRIPT = REPO_ROOT / "scripts" / "impact_tests.py"


@pytest.fixture
def mapping():
    return {
        "plugins/dev-team/hooks/telemetry.py": [
            "tests/hooks/test_telemetry.py::test_a",
            "tests/hooks/test_telemetry.py::test_b",
        ],
        "scripts/thing.py": ["tests/scripts/test_thing.py::test_c"],
    }


# --- selection --------------------------------------------------------------


def test_a_covered_file_selects_its_tests(mapping):
    selected, refusal = impact_tests.select(
        mapping, ["plugins/dev-team/hooks/telemetry.py"]
    )
    assert refusal == ""
    assert selected == [
        "tests/hooks/test_telemetry.py::test_a",
        "tests/hooks/test_telemetry.py::test_b",
    ]


def test_multiple_changed_files_union_their_tests(mapping):
    selected, refusal = impact_tests.select(
        mapping, ["plugins/dev-team/hooks/telemetry.py", "scripts/thing.py"]
    )
    assert refusal == ""
    assert len(selected) == 3


# --- every unaccountable case refuses ---------------------------------------


def test_an_unmapped_source_file_refuses(mapping):
    """A new or previously uncovered file has unknown reach, and "no test
    covers it" is indistinguishable from "the map predates it"."""
    selected, refusal = impact_tests.select(mapping, ["plugins/dev-team/hooks/new.py"])
    assert selected == []
    assert "absent from the impact map" in refusal


def test_a_changed_test_file_refuses(mapping):
    """A changed test must run regardless, and a test added since the map was
    built has no entry at all."""
    selected, refusal = impact_tests.select(mapping, ["tests/hooks/test_telemetry.py"])
    assert selected == []
    assert "is a test file" in refusal


def test_a_trailing_test_suffix_is_also_recognised(mapping):
    selected, refusal = impact_tests.select(mapping, ["tests/some_test.py"])
    assert selected == []
    assert "is a test file" in refusal


def test_an_empty_changed_set_refuses(mapping):
    selected, refusal = impact_tests.select(mapping, [])
    assert selected == []
    assert refusal


def test_a_mapped_file_with_no_tests_refuses():
    """Refusing to select nothing: an empty selection must never be read as
    "nothing to run"."""
    selected, refusal = impact_tests.select({"a.py": []}, ["a.py"])
    assert selected == []
    assert "refusing to select nothing" in refusal


def test_one_unaccountable_file_poisons_the_whole_selection(mapping):
    """Mixed diffs take the safe branch — a subset that silently omits the
    unaccountable file is the false-narrow failure this tool must not have."""
    selected, refusal = impact_tests.select(
        mapping, ["plugins/dev-team/hooks/telemetry.py", "brand/new/file.py"]
    )
    assert selected == []
    assert refusal


# --- map loading ------------------------------------------------------------


def test_a_missing_map_loads_as_none(tmp_path):
    assert impact_tests.load_map(tmp_path / "nope.json") is None


def test_a_corrupt_map_loads_as_none(tmp_path):
    path = tmp_path / "m.json"
    path.write_text("{not json", encoding="utf-8")
    assert impact_tests.load_map(path) is None


def test_a_wrong_version_map_loads_as_none(tmp_path):
    path = tmp_path / "m.json"
    path.write_text(
        json.dumps({"version": impact_tests.MAP_VERSION + 1, "files": {}}),
        encoding="utf-8",
    )
    assert impact_tests.load_map(path) is None


# --- coverage schema: the branch-mode trap ----------------------------------


def _coverage_db(path, table: str):
    """Build a minimal coverage.py-shaped DB using `table` for measurements."""
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE context (id INTEGER PRIMARY KEY, context TEXT)")
    db.execute("CREATE TABLE file (id INTEGER PRIMARY KEY, path TEXT)")
    db.execute(f"CREATE TABLE {table} (file_id INTEGER, context_id INTEGER)")
    db.execute("INSERT INTO context VALUES (1, 'tests/test_x.py::test_y|run')")
    db.execute("INSERT INTO file VALUES (1, ?)", (str(REPO_ROOT / "src" / "a.py"),))
    db.execute(f"INSERT INTO {table} VALUES (1, 1)")
    db.commit()
    db.close()


def test_read_contexts_handles_line_coverage(tmp_path):
    db = tmp_path / "line.db"
    _coverage_db(db, "line_bits")
    assert impact_tests.read_contexts(db, REPO_ROOT) == {
        "src/a.py": ["tests/test_x.py::test_y"]
    }


def test_read_contexts_handles_branch_coverage(tmp_path):
    """The trap this tool actually hit: .coveragerc sets `branch = True`, so
    coverage stores measurements in `arc`, not `line_bits`. A line_bits-only
    query returned zero rows and produced a silently EMPTY map — measured on
    this repo as files: 135, contexts: 23, line_bits: 0."""
    db = tmp_path / "arc.db"
    _coverage_db(db, "arc")
    assert impact_tests.read_contexts(db, REPO_ROOT) == {
        "src/a.py": ["tests/test_x.py::test_y"]
    }


def test_read_contexts_drops_the_empty_import_time_context(tmp_path):
    db = tmp_path / "empty.db"
    _coverage_db(db, "line_bits")
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO context VALUES (2, '')")
    conn.execute("INSERT INTO line_bits VALUES (1, 2)")
    conn.commit()
    conn.close()
    # Only the named test survives; the empty context names no test.
    assert impact_tests.read_contexts(db, REPO_ROOT) == {
        "src/a.py": ["tests/test_x.py::test_y"]
    }


# --- CLI --------------------------------------------------------------------


def _cli(*args) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(REPO_ROOT),
    )


@pytest.fixture
def map_file(tmp_path, mapping):
    path = tmp_path / "map.json"
    path.write_text(
        json.dumps({"version": impact_tests.MAP_VERSION, "files": mapping}),
        encoding="utf-8",
    )
    return path


def test_cli_refusals_exit_with_run_everything(map_file):
    """Exit 2 is the contract: a caller must treat any non-zero exit as the
    full suite, never as an empty selection."""
    for changed in ("brand/new/file.py", "tests/hooks/test_telemetry.py"):
        result = _cli("select", "--map", str(map_file), "--changed", changed)
        assert result.returncode == impact_tests.EXIT_RUN_EVERYTHING, changed


def test_cli_missing_map_exits_with_run_everything(tmp_path):
    result = _cli(
        "select", "--map", str(tmp_path / "nope.json"), "--changed", "a.py"
    )
    assert result.returncode == impact_tests.EXIT_RUN_EVERYTHING


def test_cli_defaults_to_file_granularity(map_file):
    """A parametrized node id can contain spaces and brackets, so a naive
    $(...) split corrupts it — file paths cannot."""
    result = _cli(
        "select",
        "--map",
        str(map_file),
        "--changed",
        "plugins/dev-team/hooks/telemetry.py",
    )
    assert result.returncode == 0
    assert result.stdout.split() == ["tests/hooks/test_telemetry.py"]


def test_cli_test_granularity_emits_node_ids(map_file):
    result = _cli(
        "select",
        "--map",
        str(map_file),
        "--changed",
        "plugins/dev-team/hooks/telemetry.py",
        "--granularity",
        "test",
    )
    assert result.returncode == 0
    assert "::test_a" in result.stdout


def test_cli_null_separation_for_ids_containing_spaces(tmp_path):
    path = tmp_path / "m.json"
    path.write_text(
        json.dumps(
            {
                "version": impact_tests.MAP_VERSION,
                "files": {"src/a.py": ["tests/t.py::test_x[a b c]"]},
            }
        ),
        encoding="utf-8",
    )
    result = _cli(
        "select",
        "--map",
        str(path),
        "--changed",
        "src/a.py",
        "--granularity",
        "test",
        "--null",
    )
    assert result.returncode == 0
    assert result.stdout.split("\0")[0] == "tests/t.py::test_x[a b c]"


def test_default_cov_targets_are_wider_than_coveragerc(tmp_path):
    """.coveragerc scopes `source` to the informational report's two trees, so
    a bare --cov maps nothing under plugins/dev-team/scripts. Measured: the
    first build against .coveragerc mapped 0 files."""
    assert "plugins/dev-team/scripts" in impact_tests.DEFAULT_COV_TARGETS
    coveragerc = (REPO_ROOT / ".coveragerc").read_text(encoding="utf-8")
    assert "plugins/dev-team/scripts" not in coveragerc
