"""Unit tests for hooks/lib/review_agent_registry.py (#1461).

Extracted from `scripts/check_review_agent_mcp_tools.py`'s existing
glob-discovery coverage without behavior change — this module is the shared
extraction both that script and `hooks/agent_dispatch_ledger.py` depend on.
"""

from __future__ import annotations

import sys
from pathlib import Path

from _repo_root import REPO_ROOT as _REPO_ROOT

_PLUGIN_DIR = _REPO_ROOT / "plugins" / "dev-team"
_LIB_DIR = _PLUGIN_DIR / "hooks" / "lib"

if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import review_agent_registry  # type: ignore[import-not-found]

_REAL_AGENTS_DIR = _PLUGIN_DIR / "agents"


def _agent(directory: Path, name: str) -> None:
    (directory / f"{name}.md").write_text(
        f"---\nname: {name}\ntools: Read, Grep, Glob\n---\n# {name}\n", encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# find_review_agent_files()
# ---------------------------------------------------------------------------


def test_find_review_agent_files_matches_only_review_suffix(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    _agent(agents_dir, "security-review")
    _agent(agents_dir, "structure-review")
    (agents_dir / "orchestrator.md").write_text("---\nname: orchestrator\n---\n", encoding="utf-8")
    found = review_agent_registry.find_review_agent_files(agents_dir)
    assert [p.stem for p in found] == ["security-review", "structure-review"]


def test_find_review_agent_files_sorted(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    _agent(agents_dir, "zzz-review")
    _agent(agents_dir, "aaa-review")
    found = review_agent_registry.find_review_agent_files(agents_dir)
    assert [p.stem for p in found] == ["aaa-review", "zzz-review"]


def test_find_review_agent_files_empty_dir_is_empty(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    assert review_agent_registry.find_review_agent_files(agents_dir) == []


# ---------------------------------------------------------------------------
# registered_review_agent_names()
# ---------------------------------------------------------------------------


def test_registered_review_agent_names_returns_frozenset_of_stems(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    _agent(agents_dir, "security-review")
    _agent(agents_dir, "structure-review")
    names = review_agent_registry.registered_review_agent_names(agents_dir)
    assert isinstance(names, frozenset)
    assert names == frozenset({"security-review", "structure-review"})


def test_registered_review_agent_names_excludes_non_review_agents(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    _agent(agents_dir, "security-review")
    (agents_dir / "orchestrator.md").write_text("---\nname: orchestrator\n---\n", encoding="utf-8")
    names = review_agent_registry.registered_review_agent_names(agents_dir)
    assert "orchestrator" not in names
    assert names == frozenset({"security-review"})


# ---------------------------------------------------------------------------
# Integration against the real repo (regression protection)
# ---------------------------------------------------------------------------


def test_real_repo_registry_includes_known_review_agents() -> None:
    names = review_agent_registry.registered_review_agent_names(_REAL_AGENTS_DIR)
    for expected in ("security-review", "structure-review", "arch-review"):
        assert expected in names


def test_real_repo_registry_excludes_non_review_agents() -> None:
    names = review_agent_registry.registered_review_agent_names(_REAL_AGENTS_DIR)
    assert "orchestrator" not in names
    assert "product-manager" not in names


# ---------------------------------------------------------------------------
# strip_plugin_prefix()
# ---------------------------------------------------------------------------


def test_strip_plugin_prefix_removes_dev_team_qualifier() -> None:
    assert review_agent_registry.strip_plugin_prefix("dev-team:doc-review") == "doc-review"


def test_strip_plugin_prefix_leaves_bare_name_unchanged() -> None:
    assert review_agent_registry.strip_plugin_prefix("doc-review") == "doc-review"


def test_strip_plugin_prefix_leaves_a_different_plugins_qualifier_unchanged() -> None:
    # Not this registry's agent — must not be silently claimed as one.
    assert (
        review_agent_registry.strip_plugin_prefix("other-plugin:doc-review")
        == "other-plugin:doc-review"
    )
