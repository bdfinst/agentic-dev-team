"""Tests for .claude/lib/session_start_common.py — the shared helpers behind
the two SessionStart hooks (ensure_npm_ci.py, ensure_code_graph_tools.py,
issue #1469).

Both hooks' own test suites only ever exercise resolve_project_root() and
run_logged() through monkeypatched stand-ins, so the real fallback and
error branches of this shared module had zero direct coverage. These
tests import the module directly and drive its real code paths instead.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from _repo_root import REPO_ROOT

MODULE_PATH = REPO_ROOT / ".claude" / "lib" / "session_start_common.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("session_start_common_mod", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_syntax_is_valid() -> None:
    import ast

    ast.parse(MODULE_PATH.read_text())


def test_resolve_project_root_prefers_env_var(monkeypatch, tmp_path: Path) -> None:
    module = _load_module()
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

    assert module.resolve_project_root() == tmp_path


def test_resolve_project_root_treats_empty_env_var_as_unset(monkeypatch) -> None:
    module = _load_module()
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", "")

    assert module.resolve_project_root() == REPO_ROOT


def test_resolve_project_root_falls_back_to_claude_marker(monkeypatch) -> None:
    # The real fallback branch: no env var, so it must walk up from this
    # module's own location (.claude/lib/session_start_common.py) to find
    # the repo root by anchoring on the .claude directory name.
    module = _load_module()
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)

    assert module.resolve_project_root() == REPO_ROOT


def test_resolve_project_root_fallback_survives_relocation(tmp_path: Path, monkeypatch) -> None:
    # If the module is copied somewhere else under a differently-named
    # .claude/, the marker-based walk must still find that .claude's parent,
    # not silently miscount a fixed number of .parent hops.
    relocated_claude = tmp_path / "some_repo" / ".claude" / "deeper" / "lib"
    relocated_claude.mkdir(parents=True)
    relocated_module = relocated_claude / "session_start_common.py"
    relocated_module.write_bytes(MODULE_PATH.read_bytes())

    spec = importlib.util.spec_from_file_location(
        "session_start_common_relocated", relocated_module
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)

    assert module.resolve_project_root() == tmp_path / "some_repo"


def test_run_logged_success(tmp_path: Path) -> None:
    module = _load_module()
    log_path = tmp_path / "out.log"

    ok = module.run_logged(["true"], tmp_path, log_path, 5)

    assert ok is True
    assert log_path.exists()


def test_run_logged_reports_nonzero_exit(tmp_path: Path) -> None:
    module = _load_module()
    log_path = tmp_path / "out.log"

    ok = module.run_logged(["false"], tmp_path, log_path, 5)

    assert ok is False


def test_run_logged_writes_combined_output_to_log_file(tmp_path: Path) -> None:
    module = _load_module()
    log_path = tmp_path / "out.log"

    module.run_logged(["sh", "-c", "echo stdout-line; echo stderr-line >&2"], tmp_path, log_path, 5)

    contents = log_path.read_text()
    assert "stdout-line" in contents
    assert "stderr-line" in contents


def test_run_logged_real_timeout(tmp_path: Path) -> None:
    # Drives the real subprocess.TimeoutExpired branch — a genuinely slow
    # command against a short timeout, not a monkeypatched stand-in.
    module = _load_module()
    log_path = tmp_path / "out.log"

    ok = module.run_logged(["sleep", "5"], tmp_path, log_path, 0.2)

    assert ok is False


def test_run_logged_real_missing_executable_fails_open(tmp_path: Path) -> None:
    # Drives the real OSError/FileNotFoundError branch — an executable path
    # that does not exist. Must return False, never raise.
    module = _load_module()
    log_path = tmp_path / "out.log"
    missing = tmp_path / "no-such-executable"

    ok = module.run_logged([str(missing)], tmp_path, log_path, 5)

    assert ok is False
