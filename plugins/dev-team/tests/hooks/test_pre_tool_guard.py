"""Unit tests for hooks/pre_tool_guard.py (#602).

Behavioural coverage of `evaluate()` — one assertion per code path. The
parity harness holds the bash byte-for-byte equivalence line separately.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "hooks"))

import pre_tool_guard  # noqa: E402


# ---------------------------------------------------------------------------
# _extract_file_path
# ---------------------------------------------------------------------------


def test_extract_file_path_prefers_file_path():
    raw = '{"tool_input":{"file_path":"a.py","path":"b.py"}}'
    assert pre_tool_guard._extract_file_path(raw) == "a.py"


def test_extract_file_path_falls_back_to_path():
    raw = '{"tool_input":{"path":"b.py"}}'
    assert pre_tool_guard._extract_file_path(raw) == "b.py"


def test_extract_file_path_empty_when_neither():
    assert pre_tool_guard._extract_file_path('{"tool_input":{}}') == ""


def test_extract_file_path_empty_when_malformed_json():
    assert pre_tool_guard._extract_file_path("not-json") == ""


def test_extract_file_path_empty_when_empty_string_field():
    raw = '{"tool_input":{"file_path":""}}'
    assert pre_tool_guard._extract_file_path(raw) == ""


# ---------------------------------------------------------------------------
# _matches_any — case-sensitive fnmatch (subjects are lowercased upstream)
# ---------------------------------------------------------------------------


def test_matches_any_glob():
    assert pre_tool_guard._matches_any("api.token", [".env", "*.token"]) is True


def test_matches_any_no_match():
    assert pre_tool_guard._matches_any("readme.md", [".env", "*.key"]) is False


def test_matches_any_skips_empty_patterns():
    assert pre_tool_guard._matches_any(".env", ["", ".env"]) is True


# ---------------------------------------------------------------------------
# _load_guards
# ---------------------------------------------------------------------------


def test_load_guards_returns_defaults_when_file_absent(tmp_path):
    blocked, warn = pre_tool_guard._load_guards(tmp_path / "missing.json")
    assert ".env" in blocked
    assert ".claude/settings.json" in warn


def test_load_guards_reads_custom_patterns(tmp_path):
    guards = tmp_path / "guards.json"
    guards.write_text(
        json.dumps({"blocked_paths": ["*.foo"], "warn_paths": ["config.yml"]})
    )
    blocked, warn = pre_tool_guard._load_guards(guards)
    assert blocked == ["*.foo"]
    assert warn == ["config.yml"]


def test_load_guards_falls_back_when_malformed(tmp_path):
    (tmp_path / "guards.json").write_text("{not-json")
    blocked, warn = pre_tool_guard._load_guards(tmp_path / "guards.json")
    assert ".env" in blocked


# ---------------------------------------------------------------------------
# evaluate() — decision matrix
# ---------------------------------------------------------------------------


@pytest.fixture
def default_guards(tmp_path):
    """Return (guards_path, freeze_path) where guards.json holds defaults."""
    guards = tmp_path / "guards.json"
    guards.write_text(
        json.dumps(
            {
                "blocked_paths": pre_tool_guard._DEFAULT_BLOCKED,
                "warn_paths": pre_tool_guard._DEFAULT_WARN,
            }
        )
    )
    return guards, tmp_path / "freeze-state.json"


def test_evaluate_blocks_env(default_guards):
    guards, freeze = default_guards
    code, lines = pre_tool_guard.evaluate(".env", guards, freeze)
    assert code == 2
    assert lines[0] == "BLOCKED: Write to '.env' is not allowed."


def test_evaluate_blocks_dotenv_variant(default_guards):
    guards, freeze = default_guards
    code, _ = pre_tool_guard.evaluate(".env.production", guards, freeze)
    assert code == 2


def test_evaluate_blocks_key_file(default_guards):
    guards, freeze = default_guards
    code, _ = pre_tool_guard.evaluate("secrets/api.key", guards, freeze)
    assert code == 2


def test_evaluate_case_insensitive_block(default_guards):
    guards, freeze = default_guards
    code, _ = pre_tool_guard.evaluate("SECRET_STORE.json", guards, freeze)
    assert code == 2


def test_evaluate_warns_settings(default_guards):
    guards, freeze = default_guards
    code, lines = pre_tool_guard.evaluate(".claude/settings.json", guards, freeze)
    assert code == 0
    assert lines[0].startswith("WARNING:")


def test_evaluate_allows_regular_file(default_guards):
    guards, freeze = default_guards
    code, lines = pre_tool_guard.evaluate("src/app.py", guards, freeze)
    assert code == 0
    assert lines == []


def test_evaluate_empty_path_is_silent_pass(default_guards):
    guards, freeze = default_guards
    assert pre_tool_guard.evaluate("", guards, freeze) == (0, [])


# ---------------------------------------------------------------------------
# Freeze mode
# ---------------------------------------------------------------------------


def _write_freeze(freeze_path: Path, active: bool, allowed):
    freeze_path.write_text(json.dumps({"active": active, "allowed_patterns": allowed}))


def test_freeze_blocks_paths_outside_allowed(tmp_path):
    guards = tmp_path / "guards.json"
    freeze = tmp_path / "freeze-state.json"
    _write_freeze(freeze, True, ["src/*.py"])
    code, lines = pre_tool_guard.evaluate("tests/foo.py", guards, freeze)
    assert code == 2
    assert lines[0].startswith("BLOCKED: Freeze mode is active.")


def test_freeze_allows_paths_matching_pattern(tmp_path):
    guards = tmp_path / "guards.json"
    freeze = tmp_path / "freeze-state.json"
    _write_freeze(freeze, True, ["src/app.py"])
    code, lines = pre_tool_guard.evaluate("src/app.py", guards, freeze)
    # Falls through to normal guards (default), which pass this path.
    assert code == 0
    assert lines == []


def test_freeze_inactive_does_not_gate(tmp_path):
    guards = tmp_path / "guards.json"
    freeze = tmp_path / "freeze-state.json"
    _write_freeze(freeze, False, ["src/*.py"])
    code, _ = pre_tool_guard.evaluate("tests/foo.py", guards, freeze)
    assert code == 0
