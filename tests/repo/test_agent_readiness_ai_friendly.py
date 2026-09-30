"""Tests for the AI-friendly agent-readiness criteria (issue #2178).

Covers the shared walk helper, the sibling analyzer module, and the new
criteria. The pre-existing tests/repo/test_agent_readiness.py is untouched.
"""

from __future__ import annotations

import json
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


# --------------------------------------------------------------------------
# D5 / D6 / D7
# --------------------------------------------------------------------------


def _claude(tmp_path: Path, lines: int) -> Path:
    (tmp_path / "CLAUDE.md").write_text("rule\n" * lines)
    return tmp_path


@pytest.mark.parametrize(("lines", "score"), [(200, 2), (201, 1), (300, 1), (301, 0)])
def test_d5_line_count_boundaries(tmp_path: Path, lines: int, score: int) -> None:
    res = afa.d5_claude_md_size(_claude(tmp_path, lines), _cfg())
    assert res["score"] == score
    assert f"{lines} lines" in res["evidence"]


def test_d5_failing_evidence_names_gap_and_fix(tmp_path: Path) -> None:
    res = afa.d5_claude_md_size(_claude(tmp_path, 412), _cfg())
    assert res["score"] == 0
    assert "412 lines" in res["evidence"] and "200" in res["evidence"]
    assert "to fix:" in res["evidence"]
    assert (
        "ai-friendly-repo-guidelines.md#layered-context-architecture"
        in res["evidence"]
    )


def test_d5_absent_instructions_file_is_not_applicable(tmp_path: Path) -> None:
    res = afa.d5_claude_md_size(tmp_path, _cfg())
    assert res["max"] == 0 and res["score"] == 0
    assert "see D2" in res["evidence"]


def test_d5_threshold_override_changes_score_and_evidence(tmp_path: Path) -> None:
    root = _claude(tmp_path, 50)
    cfg = _cfg()
    assert afa.d5_claude_md_size(root, cfg)["score"] == 2
    cfg["thresholds"]["claude_md_max_lines"] = 10
    cfg["thresholds"]["claude_md_hard_max_lines"] = 20
    res = afa.d5_claude_md_size(root, cfg)
    assert res["score"] == 0 and "10-line ceiling" in res["evidence"]


def test_d5_missing_threshold_keys_fall_back_to_defaults(tmp_path: Path) -> None:
    cfg = _cfg()
    cfg["thresholds"] = {}
    assert afa.d5_claude_md_size(_claude(tmp_path, 201), cfg)["score"] == 1
    del cfg["thresholds"]
    assert afa.d5_claude_md_size(tmp_path, cfg)["max"] == 2


def test_d5_uses_same_discovery_as_d2(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("rule\n" * 250)
    assert afa.find_instructions_file(tmp_path) == "AGENTS.md"
    assert afa.d5_claude_md_size(tmp_path, _cfg())["score"] == 1


def test_d6_nested_claude_md_passes(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "CLAUDE.md").write_text("# Src\n\nUse small modules.\n")
    res = afa.d6_layered_context(tmp_path, _cfg())
    assert res["score"] == 2 and "src/CLAUDE.md" in res["evidence"]


def test_d6_rules_dir_passes(tmp_path: Path) -> None:
    (tmp_path / ".claude" / "rules").mkdir(parents=True)
    (tmp_path / ".claude" / "rules" / "py.md").write_text("Prefer pathlib.\n")
    assert afa.d6_layered_context(tmp_path, _cfg())["score"] == 2


def test_d6_root_only_or_empty_content_fails(tmp_path: Path) -> None:
    (tmp_path / "CLAUDE.md").write_text("rule\n")
    (tmp_path / ".claude" / "rules").mkdir(parents=True)
    (tmp_path / ".claude" / "rules" / "empty.md").write_text("# Title only\n\n")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "CLAUDE.md").write_text("")
    res = afa.d6_layered_context(tmp_path, _cfg())
    assert res["score"] == 0
    assert "to fix:" in res["evidence"]


def test_d6_ignores_excluded_dirs(tmp_path: Path) -> None:
    (tmp_path / "node_modules" / "p").mkdir(parents=True)
    (tmp_path / "node_modules" / "p" / "CLAUDE.md").write_text("rule\n")
    assert afa.d6_layered_context(tmp_path, _cfg())["score"] == 0


def test_d7_is_manual_review_only() -> None:
    data = _scan(FIX / "repo_well_configured")
    flags = {f["criterion"] for f in data["manual_review_flags"]}
    assert "D7_reference_implementation" in flags
    assert {"C3_architecture", "S3_interface_design", "D4_domain_context"} <= flags
    scored = {c for cat in data["categories"].values() for c in cat.get("criteria", {})}
    assert "D7_reference_implementation" not in scored


def test_well_configured_fixture_scores_d5_d6_at_two() -> None:
    doc = _scan(FIX / "repo_well_configured")["categories"]["documentation"]["criteria"]
    assert doc["D5_claude_md_size"]["score"] == 2
    assert doc["D6_layered_context"]["score"] == 2


def test_scorecard_version_bumped_and_d5_d6_registered() -> None:
    cfg = _cfg()
    assert cfg["version"] == "1.1-mvp"
    assert cfg["criteria"]["documentation"]["D5_claude_md_size"]["mvp"] is True
    assert cfg["criteria"]["documentation"]["D6_layered_context"]["mvp"] is True


def _crit(data: dict, cat: str, crit: str) -> dict:
    return data["categories"][cat]["criteria"][crit]


# --------------------------------------------------------------------------
# B5 composite check command
# --------------------------------------------------------------------------


def _b5(root: Path, cfg: dict | None = None) -> dict:
    return afa.b5_composite_check_command(root, cfg or _cfg())


def test_b5_makefile_check_with_lint_and_test_passes(tmp_path: Path) -> None:
    (tmp_path / "Makefile").write_text("check: lint test\nlint:\n\truff .\n")
    res = _b5(tmp_path)
    assert res["score"] == 2 and "Makefile target 'check'" in res["evidence"]


def test_b5_makefile_recipe_body_counts(tmp_path: Path) -> None:
    (tmp_path / "Makefile").write_text("verify:\n\truff check .\n\tpytest -q\n")
    assert _b5(tmp_path)["score"] == 2


def test_b5_package_json_script_passes(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"ci": "npm run lint && npm test"}})
    )
    assert _b5(tmp_path)["score"] == 2


def test_b5_pyproject_and_justfile_pass(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.poe.tasks]\nall = ["ruff", "pytest"]\n'
    )
    assert _b5(tmp_path)["score"] == 2
    other = tmp_path / "j"
    other.mkdir()
    (other / "justfile").write_text("check:\n    eslint .\n    vitest run\n")
    assert _b5(other)["score"] == 2


def test_b5_missing_command_scores_zero_with_gap(tmp_path: Path) -> None:
    (tmp_path / "Makefile").write_text("build:\n\tgcc x.c\n")
    res = _b5(tmp_path)
    assert res["score"] == 0
    assert "check|verify|ci|all" in res["evidence"]
    assert "to fix:" in res["evidence"]
    assert "deterministic-verification--fast-feedback-loops" in res["evidence"]


def test_b5_partial_target_scores_one(tmp_path: Path) -> None:
    (tmp_path / "Makefile").write_text("check:\n\tpytest\n")
    res = _b5(tmp_path)
    assert res["score"] == 1 and "lacks a lint command" in res["evidence"]


def test_b5_lookalike_words_do_not_count(tmp_path: Path) -> None:
    (tmp_path / "Makefile").write_text("check:\n\techo latest contest\n")
    assert _b5(tmp_path)["score"] == 1


def test_b5_malformed_and_unreadable_inputs_do_not_crash(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{not json")
    (tmp_path / "Makefile").mkdir()  # a directory where a file is expected
    (tmp_path / "pyproject.toml").write_bytes(b"\xff\xfe\x00bad")
    assert _b5(tmp_path)["score"] == 0
    (tmp_path / "package.json").write_text('{"scripts": ["check"]}')
    assert _b5(tmp_path)["score"] == 0


def test_b5_target_names_override_changes_score_and_evidence(tmp_path: Path) -> None:
    (tmp_path / "Makefile").write_text("gate: lint test\n")
    assert _b5(tmp_path)["score"] == 0
    cfg = _cfg()
    cfg["check_target_names"] = ["gate"]
    res = _b5(tmp_path, cfg)
    assert res["score"] == 2 and "'gate'" in res["evidence"]


def test_b5_registered_in_build_env_and_fixture_passes() -> None:
    assert _cfg()["criteria"]["build_env"]["B5_composite_check_command"]["mvp"]
    data = _scan(FIX / "repo_well_configured")
    assert _crit(data, "build_env", "B5_composite_check_command")["score"] == 2
    assert _scan(FIX / "repo_minimal")["tier"] == "Agent-Hostile"


def test_t4_stays_deferred() -> None:
    assert _cfg()["criteria"]["test_infrastructure"]["T4_single_command"]["mvp"] is False
