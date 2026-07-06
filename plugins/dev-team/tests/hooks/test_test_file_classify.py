"""Unit tests for hooks/lib/test_file_classify.py (#813).

The shared test-file classifier encodes knowledge/test-file-indicators.md
once; the build-phase reader is the state source for both refactor guards.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"))

from test_file_classify import (  # noqa: E402
    STALE_AFTER_SECONDS,
    is_test_file,
    read_build_phase,
)


# ---------------------------------------------------------------------------
# is_test_file — one assertion per indicator row
# ---------------------------------------------------------------------------


def test_js_test_suffix_is_a_test_file():
    assert is_test_file("src/thing.test.ts") is True


def test_js_spec_suffix_is_a_test_file():
    assert is_test_file("src/thing.spec.js") is True


def test_dunder_tests_directory_is_a_test_file():
    assert is_test_file("src/__tests__/thing.js") is True


def test_plain_source_file_is_not_a_test_file():
    assert is_test_file("src/thing.ts") is False


def test_feature_file_always_counts():
    assert is_test_file("features/login.feature") is True


def test_step_definition_files_count():
    assert is_test_file("features/login.steps.js") is True
    assert is_test_file("features/LoginStepDefinitions.cs", content="") is True
    assert is_test_file("features/LoginSteps.java") is True


def test_csharp_with_fact_attribute_is_a_test_file():
    assert is_test_file("src/Thing.cs", content="[Fact]\npublic void X() {}") is True


def test_csharp_without_test_attribute_is_not():
    assert is_test_file("src/Thing.cs", content="public class Thing {}") is False


def test_java_test_annotation_is_a_test_file():
    assert is_test_file("src/Thing.java", content="@Test\nvoid x() {}") is True


def test_java_class_name_suffix_is_a_test_file():
    assert is_test_file("src/ThingTest.java", content="") is True
    assert is_test_file("src/ThingSpec.java", content="") is True


def test_java_plain_class_is_not():
    assert is_test_file("src/Thing.java", content="class Thing {}") is False


def test_python_test_prefix_is_a_test_file():
    assert is_test_file("tests/test_calc.py") is True


def test_python_test_suffix_is_a_test_file():
    assert is_test_file("tests/calc_test.py") is True


def test_python_test_prefix_is_case_insensitive():
    assert is_test_file("tests/TEST_calc.py") is True


def test_python_bare_test_name_is_not_a_test_file():
    # "test.py" has no "_" separator — not the pytest/unittest convention.
    assert is_test_file("src/test.py") is False


def test_python_plain_module_is_not_a_test_file():
    assert is_test_file("src/calc.py") is False


def test_python_name_containing_test_substring_is_not_a_test_file():
    assert is_test_file("src/contest.py") is False
    assert is_test_file("src/testing.py") is False


def test_unreadable_content_probe_is_not_a_test_file(tmp_path):
    # .cs with no content passed and no file on disk — probe fails, not a test.
    assert is_test_file(str(tmp_path / "Ghost.cs")) is False


def test_empty_path_is_not_a_test_file():
    assert is_test_file("") is False


# ---------------------------------------------------------------------------
# read_build_phase — absent / fresh / stale / malformed
# ---------------------------------------------------------------------------


def _write_state(tmp_path: Path, **overrides) -> Path:
    state = {
        "phase": "refactor",
        "step": "2.1",
        "written_at": "2026-07-04T10:00:00+00:00",
        "test_files_staged": ["src/thing.test.ts"],
    }
    state.update(overrides)
    path = tmp_path / "memory" / "build-phase.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state))
    return path


_WRITTEN_AT_EPOCH = 1783159200.0  # 2026-07-04T10:00:00+00:00


def test_absent_state_is_none_without_error(tmp_path):
    state, error = read_build_phase(tmp_path)
    assert state is None and error is None


def test_fresh_state_is_returned(tmp_path):
    _write_state(tmp_path)
    state, error = read_build_phase(tmp_path, now=_WRITTEN_AT_EPOCH + 60)
    assert error is None
    assert state["phase"] == "refactor"
    assert state["step"] == "2.1"
    assert state["test_files_staged"] == ["src/thing.test.ts"]


def test_stale_state_is_treated_as_absent(tmp_path):
    _write_state(tmp_path)
    state, error = read_build_phase(
        tmp_path, now=_WRITTEN_AT_EPOCH + STALE_AFTER_SECONDS + 1
    )
    assert state is None and error is None


def test_malformed_json_reports_an_error(tmp_path):
    path = tmp_path / "memory" / "build-phase.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json")
    state, error = read_build_phase(tmp_path)
    assert state is None
    assert error is not None and "malformed" in error


def test_missing_phase_reports_an_error(tmp_path):
    _write_state(tmp_path, phase=None)
    state, error = read_build_phase(tmp_path, now=_WRITTEN_AT_EPOCH + 60)
    assert state is None and error is not None


def test_unparseable_written_at_reports_an_error(tmp_path):
    _write_state(tmp_path, written_at="yesterday-ish")
    state, error = read_build_phase(tmp_path)
    assert state is None and error is not None


def test_zulu_written_at_is_accepted(tmp_path):
    _write_state(tmp_path, written_at="2026-07-04T10:00:00Z")
    state, error = read_build_phase(tmp_path, now=_WRITTEN_AT_EPOCH + 60)
    assert error is None and state is not None


def test_non_string_entries_in_staged_list_are_dropped(tmp_path):
    _write_state(tmp_path, test_files_staged=["a.test.js", 7, "", None])
    state, error = read_build_phase(tmp_path, now=_WRITTEN_AT_EPOCH + 60)
    assert error is None
    assert state["test_files_staged"] == ["a.test.js"]
