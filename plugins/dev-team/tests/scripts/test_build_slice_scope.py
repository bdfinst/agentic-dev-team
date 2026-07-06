"""Unit tests for scripts/build_slice_scope.py (issue #865).

Covers the freeze-scope wiring for `/build`: the `Scope enforcement: freeze`
opt-in detection, the declared-Files + bookkeeping-allowlist computation,
and the engage/clear freeze-state.json lifecycle.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "scripts"))

import build_slice_scope  # noqa: E402


# ---------------------------------------------------------------------------
# scope_enforcement_enabled
# ---------------------------------------------------------------------------


def test_scope_enforcement_disabled_by_default():
    """A plan with declared Files but no Scope enforcement line does not
    engage freeze (#865 Ambiguity Log Q1: opt-in only)."""
    text = "# Plan\n\n### Slice 1: alpha\n**Files:** `a.ts`\n"
    assert build_slice_scope.scope_enforcement_enabled(text) is False


def test_scope_enforcement_enabled_via_metadata_line():
    text = "# Plan\n\n**Scope enforcement:** freeze\n\n### Slice 1: alpha\n"
    assert build_slice_scope.scope_enforcement_enabled(text) is True


def test_scope_enforcement_case_insensitive():
    text = "**scope enforcement:** FREEZE\n"
    assert build_slice_scope.scope_enforcement_enabled(text) is True


def test_scope_enforcement_other_value_is_disabled():
    text = "**Scope enforcement:** none\n"
    assert build_slice_scope.scope_enforcement_enabled(text) is False


# ---------------------------------------------------------------------------
# declared_files_for_slice / build_allowed_patterns
# ---------------------------------------------------------------------------


def test_declared_files_for_slice_returns_tokenized_list():
    text = "### Slice 1: alpha\n**Depends-on:** none\n**Files:** `a.ts`, `b.ts`\n"
    assert build_slice_scope.declared_files_for_slice(text, "1") == ["a.ts", "b.ts"]


def test_declared_files_for_slice_empty_when_undeclared():
    text = "### Slice 1: alpha\n**Depends-on:** none\n"
    assert build_slice_scope.declared_files_for_slice(text, "1") == []


def test_build_allowed_patterns_includes_bookkeeping_allowlist(tmp_path):
    plan_path = tmp_path / "myplan.md"
    text = "### Slice 1: alpha\n**Depends-on:** none\n**Files:** `a.ts`\n"
    patterns = build_slice_scope.build_allowed_patterns(plan_path, text, "1")
    assert patterns == ["a.ts", "myplan.md", "memory/**", "metrics/**"]


# ---------------------------------------------------------------------------
# write_freeze_state / clear_freeze_state
# ---------------------------------------------------------------------------


def test_write_freeze_state_writes_expected_contract(tmp_path):
    hooks_dir = tmp_path / "hooks"
    path = build_slice_scope.write_freeze_state(hooks_dir, ["a.ts", "memory/**"])
    data = json.loads(path.read_text())
    assert data["active"] is True
    assert data["allowed_patterns"] == ["a.ts", "memory/**"]
    assert "frozen_at" in data


def test_clear_freeze_state_removes_the_file(tmp_path):
    hooks_dir = tmp_path / "hooks"
    build_slice_scope.write_freeze_state(hooks_dir, ["a.ts"])
    assert (hooks_dir / build_slice_scope.FREEZE_STATE_FILENAME).exists()
    build_slice_scope.clear_freeze_state(hooks_dir)
    assert not (hooks_dir / build_slice_scope.FREEZE_STATE_FILENAME).exists()


def test_clear_freeze_state_is_a_no_op_when_absent(tmp_path):
    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir()
    # Should not raise.
    build_slice_scope.clear_freeze_state(hooks_dir)


# ---------------------------------------------------------------------------
# Integration with hooks/pre_tool_guard.py (issue #865 AC2)
# ---------------------------------------------------------------------------


def test_engaged_freeze_blocks_writes_outside_declared_scope(tmp_path):
    sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "hooks"))
    import pre_tool_guard  # noqa: E402

    hooks_dir = tmp_path / "hooks"
    plan_path = tmp_path / "plan.md"
    text = "### Slice 1: alpha\n**Depends-on:** none\n**Files:** `a.ts`\n"
    allowed = build_slice_scope.build_allowed_patterns(plan_path, text, "1")
    build_slice_scope.write_freeze_state(hooks_dir, allowed)

    exit_code, lines = pre_tool_guard.evaluate(
        "out-of-scope.ts", hooks_dir / "guards.json", hooks_dir / "freeze-state.json"
    )
    assert exit_code == 2
    assert any("BLOCKED" in line for line in lines)

    exit_code, lines = pre_tool_guard.evaluate(
        "a.ts", hooks_dir / "guards.json", hooks_dir / "freeze-state.json"
    )
    assert exit_code == 0

    # Bookkeeping allowlist entries are honored too.
    exit_code, lines = pre_tool_guard.evaluate(
        "memory/build-phase.json", hooks_dir / "guards.json", hooks_dir / "freeze-state.json"
    )
    assert exit_code == 0
