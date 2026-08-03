"""Unit tests for hooks/lib/mcp_json_repowise.py (#1747).

Shared detect()/strip_entry()/relocate() logic for the repowise `.mcp.json`
machine-specific-path problem, used by both `project-init/SKILL.md`'s
standing check (via this module's CLI) and
`hooks/mcp_json_repowise_nudge.py` (the SessionStart nudge).
"""

from __future__ import annotations

import importlib.util as _importlib_util
import json
import subprocess
import sys
from pathlib import Path

from _repo_root import REPO_ROOT as _REPO_ROOT

_MODULE_PATH = (
    _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib" / "mcp_json_repowise.py"
)

_TESTS_LIB = Path(__file__).resolve().parents[2] / "tests" / "lib"
if str(_TESTS_LIB) not in sys.path:
    sys.path.insert(0, str(_TESTS_LIB))

from hermetic import hermetic_git_env  # type: ignore[import-not-found]

_spec = _importlib_util.spec_from_file_location("mcp_json_repowise", _MODULE_PATH)
assert _spec is not None and _spec.loader is not None
mcp_json_repowise = _importlib_util.module_from_spec(_spec)
_spec.loader.exec_module(mcp_json_repowise)


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        env=hermetic_git_env(home=cwd),
        check=True,
        capture_output=True,
        text=True,
    )


def _init_repo(cwd: Path) -> None:
    _git(cwd, "init", "-q")
    _git(cwd, "config", "user.email", "test@example.com")
    _git(cwd, "config", "user.name", "Test")


def _write_mcp_json(cwd: Path, data: dict) -> Path:
    path = cwd / ".mcp.json"
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def _commit_all(cwd: Path, message: str) -> None:
    _git(cwd, "add", "-A")
    _git(cwd, "commit", "-q", "-m", message)


def _commit_placeholder(cwd: Path) -> None:
    (cwd / "README.md").write_text("placeholder\n", encoding="utf-8")
    _commit_all(cwd, "init")


_REPOWISE_ENTRY = {
    "command": "repowise",
    "args": ["mcp", "/Users/alice/Dev/some-repo", "--transport", "stdio"],
    "description": "repowise: codebase intelligence",
}

_CODEGRAPH_ENTRY = {"command": "codegraph", "args": ["mcp"]}


def test_detect_none_when_mcp_json_missing(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _commit_placeholder(tmp_path)
    assert mcp_json_repowise.detect(tmp_path) is None


def test_detect_none_when_mcp_json_untracked(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _commit_placeholder(tmp_path)
    _write_mcp_json(tmp_path, {"mcpServers": {"repowise": _REPOWISE_ENTRY}})
    # Never git add-ed — untracked.
    assert mcp_json_repowise.detect(tmp_path) is None


def test_detect_none_when_tracked_but_no_repowise_key(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_mcp_json(tmp_path, {"mcpServers": {"codegraph": _CODEGRAPH_ENTRY}})
    _commit_all(tmp_path, "add mcp.json")
    assert mcp_json_repowise.detect(tmp_path) is None


def test_detect_returns_entry_when_tracked_and_present(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_mcp_json(
        tmp_path,
        {"mcpServers": {"codegraph": _CODEGRAPH_ENTRY, "repowise": _REPOWISE_ENTRY}},
    )
    _commit_all(tmp_path, "add mcp.json")
    entry = mcp_json_repowise.detect(tmp_path)
    assert entry == _REPOWISE_ENTRY


def test_detect_none_on_malformed_json(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / ".mcp.json").write_text("{not json", encoding="utf-8")
    _commit_all(tmp_path, "add broken mcp.json")
    assert mcp_json_repowise.detect(tmp_path) is None


def test_strip_entry_removes_only_repowise_preserves_others(tmp_path: Path) -> None:
    path = _write_mcp_json(
        tmp_path,
        {"mcpServers": {"codegraph": _CODEGRAPH_ENTRY, "repowise": _REPOWISE_ENTRY}},
    )
    changed = mcp_json_repowise.strip_entry(path)
    assert changed is True
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "repowise" not in data["mcpServers"]
    assert data["mcpServers"]["codegraph"] == _CODEGRAPH_ENTRY


def test_strip_entry_drops_mcpServers_key_when_empty_after_strip(tmp_path: Path) -> None:
    path = _write_mcp_json(tmp_path, {"mcpServers": {"repowise": _REPOWISE_ENTRY}})
    mcp_json_repowise.strip_entry(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "mcpServers" not in data


def test_strip_entry_is_noop_when_absent(tmp_path: Path) -> None:
    path = _write_mcp_json(tmp_path, {"mcpServers": {"codegraph": _CODEGRAPH_ENTRY}})
    before = path.read_text(encoding="utf-8")
    changed = mcp_json_repowise.strip_entry(path)
    assert changed is False
    assert path.read_text(encoding="utf-8") == before


def test_relocate_not_tracked_when_mcp_json_missing(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _commit_placeholder(tmp_path)
    assert mcp_json_repowise.relocate(tmp_path) == "not-tracked"


def test_relocate_not_tracked_when_untracked(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _commit_placeholder(tmp_path)
    _write_mcp_json(tmp_path, {"mcpServers": {"repowise": _REPOWISE_ENTRY}})
    assert mcp_json_repowise.relocate(tmp_path) == "not-tracked"


def test_relocate_no_repowise_entry(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_mcp_json(tmp_path, {"mcpServers": {"codegraph": _CODEGRAPH_ENTRY}})
    _commit_all(tmp_path, "add mcp.json")
    assert mcp_json_repowise.relocate(tmp_path) == "no-repowise-entry"


def test_relocate_success_registers_then_strips(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    path = _write_mcp_json(
        tmp_path,
        {"mcpServers": {"codegraph": _CODEGRAPH_ENTRY, "repowise": _REPOWISE_ENTRY}},
    )
    _commit_all(tmp_path, "add mcp.json")

    calls = []

    def fake_register(repo_root: Path) -> bool:
        calls.append(repo_root)
        return True

    result = mcp_json_repowise.relocate(tmp_path, register=fake_register)
    assert result == "relocated"
    assert calls == [tmp_path]
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "repowise" not in data["mcpServers"]
    assert data["mcpServers"]["codegraph"] == _CODEGRAPH_ENTRY


def test_relocate_failed_registration_leaves_mcp_json_untouched(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    path = _write_mcp_json(tmp_path, {"mcpServers": {"repowise": _REPOWISE_ENTRY}})
    _commit_all(tmp_path, "add mcp.json")
    before = path.read_text(encoding="utf-8")

    result = mcp_json_repowise.relocate(tmp_path, register=lambda repo_root: False)
    assert result == "relocate-failed"
    assert path.read_text(encoding="utf-8") == before


def test_is_tracked_false_when_not_a_git_repo(tmp_path: Path) -> None:
    path = _write_mcp_json(tmp_path, {"mcpServers": {"repowise": _REPOWISE_ENTRY}})
    assert mcp_json_repowise.is_tracked(path, tmp_path) is False
