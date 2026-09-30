"""Tests for the AI-friendly agent-readiness criteria (issue #2178).

Covers the shared walk helper, the sibling analyzer module, and the new
criteria. The pre-existing tests/repo/test_agent_readiness.py is untouched.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

SKILL = REPO_ROOT / "plugins" / "dev-team" / "skills" / "agent-readiness"
SCANNER = SKILL / "scanner.py"
FIX = REPO_ROOT / "tests" / "fixtures" / "agent-readiness"

sys.path.insert(0, str(SKILL))
sys.path.insert(0, str(REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"))
import ai_friendly_analyzers as afa
import scanner
from minimal_yaml import parse_yaml


def _cfg() -> dict:
    return parse_yaml((SKILL / "scorecard.yaml").read_text())


def _scan(root: Path, cfg: dict | None = None) -> dict:
    return scanner.scan(root, cfg or _cfg())


# --------------------------------------------------------------------------
# Walk helper
# --------------------------------------------------------------------------


def test_walk_prunes_excluded_names_and_root_relative_paths(tmp_path: Path) -> None:
    for d in ("src", "node_modules/x", ".claude/worktrees/w", ".claude/rules"):
        (tmp_path / d).mkdir(parents=True)
        (tmp_path / d / "f.py").write_text("x\n")
    files = {
        p.relative_to(tmp_path).as_posix()
        for p in afa.walk_files(tmp_path, ["node_modules", ".claude/worktrees"])
    }
    assert files == {"src/f.py", ".claude/rules/f.py"}


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="needs symlinks")
def test_walk_terminates_on_symlink_loop(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "f.py").write_text("x\n")
    try:
        os.symlink(tmp_path, tmp_path / "a" / "loop", target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable")
    files = [p.name for p in afa.walk_files(tmp_path, [])]
    assert files == ["f.py"]


def test_walk_is_memoized_until_reset(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x\n")
    afa.reset_walk_cache()
    first = afa.walk_tree(tmp_path, [])
    assert afa.walk_tree(tmp_path, []) is first
    afa.reset_walk_cache()
    assert afa.walk_tree(tmp_path, []) is not first


def test_c4_uses_pruned_walk_and_ignores_excluded_dirs(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x\n" * 10)
    (tmp_path / "graphify-out").mkdir()
    (tmp_path / "graphify-out" / "big.py").write_text("x\n" * 5000)
    res = _scan(tmp_path)["categories"]["code_quality"]["criteria"]["C4_module_size"]
    assert res["score"] == 2


# --------------------------------------------------------------------------
# Registry parity
# --------------------------------------------------------------------------


def test_every_mvp_criterion_has_an_analyzer_and_vice_versa() -> None:
    mvp = {
        crit
        for crits in _cfg()["criteria"].values()
        for crit, meta in crits.items()
        if meta.get("mvp")
    }
    assert mvp == set(scanner.ANALYZERS)
