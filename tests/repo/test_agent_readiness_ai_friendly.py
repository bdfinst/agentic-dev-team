"""Tests for the AI-friendly agent-readiness criteria (issue #2178).

Covers the shared walk helper, the sibling analyzer module, and the new
criteria. The pre-existing tests/repo/test_agent_readiness.py is untouched.
"""

from __future__ import annotations

import json
import os
import subprocess
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


def test_walk_bare_name_prunes_nested_but_root_relative_path_does_not(
    tmp_path: Path,
) -> None:
    for d in ("src/node_modules/x", "src/.claude/worktrees/w", ".claude/worktrees/w"):
        (tmp_path / d).mkdir(parents=True)
        (tmp_path / d / "f.py").write_text("x\n")
    files = {
        p.relative_to(tmp_path).as_posix()
        for p in afa.walk_files(tmp_path, ["node_modules", ".claude/worktrees"])
    }
    # bare name prunes at any depth; the path entry only matches from the root
    assert files == {"src/.claude/worktrees/w/f.py"}


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
    # same root, different exclude set -> separate cache entry
    other = afa.walk_tree(tmp_path, ["skip"])
    assert other is not first
    assert afa.walk_tree(tmp_path, ["skip"]) is other
    # tree mutation is invisible until reset, visible after
    (tmp_path / "b.py").write_text("y\n")
    assert [p.name for p in afa.walk_files(tmp_path, [])] == ["a.py"]
    afa.reset_walk_cache()
    assert [p.name for p in afa.walk_files(tmp_path, [])] == ["a.py", "b.py"]
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
    root = _claude(tmp_path, 201)  # 201 lines: over 200 default, under 300 hard
    cfg = _cfg()
    cfg["thresholds"] = {}
    assert afa.d5_claude_md_size(root, cfg)["score"] == 1
    del cfg["thresholds"]
    res = afa.d5_claude_md_size(root, cfg)
    assert res["score"] == 1 and res["max"] == 2


def test_d5_uses_same_discovery_as_d2(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("rule\n" * 250)
    assert afa.find_instructions_file(tmp_path) == "AGENTS.md"
    assert "AGENTS.md" in scanner.d2_ai_instructions(tmp_path, _cfg())["evidence"]
    assert "AGENTS.md is 250 lines" in afa.d5_claude_md_size(tmp_path, _cfg())["evidence"]


def test_d2_and_d5_agree_on_precedence(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("rule\n" * 250)
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "CLAUDE.md").write_text("rule\n" * 10)
    assert afa.find_instructions_file(tmp_path) == ".claude/CLAUDE.md"
    assert ".claude/CLAUDE.md" in scanner.d2_ai_instructions(tmp_path, _cfg())["evidence"]
    assert ".claude/CLAUDE.md is 10 lines" in afa.d5_claude_md_size(tmp_path, _cfg())["evidence"]
    (tmp_path / "CLAUDE.md").write_text("rule\n" * 5)
    assert afa.find_instructions_file(tmp_path) == "CLAUDE.md"
    assert scanner.d2_ai_instructions(tmp_path, _cfg())["evidence"].startswith("CLAUDE.md")


def test_d6_nested_claude_md_passes(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "CLAUDE.md").write_text("# Src\n\nUse small modules.\n")
    res = afa.d6_layered_context(tmp_path, _cfg())
    assert res["score"] == 2 and "src/CLAUDE.md" in res["evidence"]


def test_d6_rules_dir_passes(tmp_path: Path) -> None:
    (tmp_path / ".claude" / "rules").mkdir(parents=True)
    (tmp_path / ".claude" / "rules" / "py.md").write_text("Prefer pathlib.\n")
    assert afa.d6_layered_context(tmp_path, _cfg())["score"] == 2


def test_d6_root_only_claude_md_fails(tmp_path: Path) -> None:
    (tmp_path / "CLAUDE.md").write_text("rule\n")
    res = afa.d6_layered_context(tmp_path, _cfg())
    assert res["score"] == 0
    assert "to fix:" in res["evidence"]


def test_d6_heading_only_rules_file_fails(tmp_path: Path) -> None:
    (tmp_path / ".claude" / "rules").mkdir(parents=True)
    (tmp_path / ".claude" / "rules" / "empty.md").write_text("# Title only\n\n")
    assert afa.d6_layered_context(tmp_path, _cfg())["score"] == 0


def test_d6_empty_nested_claude_md_fails(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "CLAUDE.md").write_text("")
    assert afa.d6_layered_context(tmp_path, _cfg())["score"] == 0


def test_d6_non_md_file_in_rules_dir_fails(tmp_path: Path) -> None:
    (tmp_path / ".claude" / "rules").mkdir(parents=True)
    (tmp_path / ".claude" / "rules" / "py.txt").write_text("Prefer pathlib.\n")
    assert afa.d6_layered_context(tmp_path, _cfg())["score"] == 0


def test_d6_dot_claude_claude_md_is_not_a_nested_layer(tmp_path: Path) -> None:
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "CLAUDE.md").write_text("Real content.\n")
    assert afa.d6_layered_context(tmp_path, _cfg())["score"] == 0


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


def test_b5_lint_without_test_scores_one(tmp_path: Path) -> None:
    (tmp_path / "Makefile").write_text("check:\n\truff .\n")
    res = _b5(tmp_path)
    assert res["score"] == 1 and "lacks a test command" in res["evidence"]


def test_b5_multi_source_full_beats_earlier_partial(tmp_path: Path) -> None:
    (tmp_path / "Makefile").write_text("check:\n\tpytest\n")
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"verify": "eslint . && jest"}})
    )
    res = _b5(tmp_path)
    assert res["score"] == 2 and "package.json target 'verify'" in res["evidence"]


def test_b5_lookalike_words_do_not_count(tmp_path: Path) -> None:
    # splint/latest/contest contain "lint"/"test" but not as standalone tokens
    (tmp_path / "Makefile").write_text("check:\n\techo splint latest contest\n")
    res = _b5(tmp_path)
    assert res["score"] == 1
    assert "lacks a lint and test command" in res["evidence"]


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


def test_repo_minimal_stays_agent_hostile() -> None:
    assert _scan(FIX / "repo_minimal")["tier"] == "Agent-Hostile"


def test_t4_stays_deferred() -> None:
    assert _cfg()["criteria"]["test_infrastructure"]["T4_single_command"]["mvp"] is False


# --------------------------------------------------------------------------
# End-to-end fixtures and contract
# --------------------------------------------------------------------------

NEW_MVP = {
    "D5_claude_md_size": "documentation",
    "D6_layered_context": "documentation",
    "B5_composite_check_command": "build_env",
}


def test_ai_hostile_fixture_scores_new_criteria_zero_with_gap_evidence() -> None:
    data = _scan(FIX / "repo_ai_hostile")
    d5 = _crit(data, "documentation", "D5_claude_md_size")
    d6 = _crit(data, "documentation", "D6_layered_context")
    b5 = _crit(data, "build_env", "B5_composite_check_command")
    assert (d5["score"], d6["score"], b5["score"]) == (0, 0, 0)
    assert "412 lines" in d5["evidence"] and "200" in d5["evidence"]
    assert "no non-empty nested CLAUDE.md" in d6["evidence"]
    assert "no check|verify|ci|all target" in b5["evidence"]


def test_ai_conforming_fixture_scores_new_criteria_two() -> None:
    data = _scan(FIX / "repo_ai_conforming")
    for crit, cat in NEW_MVP.items():
        assert _crit(data, cat, crit)["score"] == 2, crit


def test_json_key_set_is_backward_compatible_and_additive() -> None:
    data = _scan(FIX / "repo_well_configured")
    assert set(data) == {
        "repository",
        "scanner_version",
        "scope",
        "overall_score",
        "overall_note",
        "tier",
        "categories",
        "manual_review_flags",
    }
    assert data["tier"] == "Agent-Ready"
    existing = {
        "B2_reproducible_env",
        "B3_dependency_management",
        "C1_formatting",
        "C2_linting",
        "C4_module_size",
        "D1_readme",
        "D2_ai_instructions",
        "D3_architecture_docs",
        "V2_precommit_hooks",
        "V3_commit_conventions",
        "V4_dependency_scanning",
    }
    crits = {c for v in data["categories"].values() for c in v.get("criteria", {})}
    assert crits == existing | set(NEW_MVP)
    for v in data["categories"].values():
        for r in v.get("criteria", {}).values():
            assert set(r) == {"score", "max", "evidence"}


def test_tier_thresholds_unchanged() -> None:
    assert _cfg()["tiers"] == {
        "agent_ready": 75,
        "agent_assisted": 50,
        "agent_limited": 25,
    }


def test_new_evidence_strings_follow_contract() -> None:
    for fixture in ("repo_ai_hostile", "repo_ai_conforming"):
        data = _scan(FIX / fixture)
        for crit, cat in NEW_MVP.items():
            ev = _crit(data, cat, crit)["evidence"]
            assert ev.startswith("found "), ev
            assert "; threshold " in ev and "; to fix: " in ev, ev
            assert "knowledge/ai-friendly-repo-guidelines.md#" in ev, ev


def test_cli_contract_unchanged(tmp_path: Path) -> None:
    out = tmp_path / "r.json"
    res = subprocess.run(
        [sys.executable, str(SCANNER), str(FIX / "repo_ai_conforming"), "--json", str(out)],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    data = json.loads(out.read_text())
    assert data["scanner_version"] == "1.1-mvp"
    assert set(data) == {
        "repository",
        "scanner_version",
        "scope",
        "overall_score",
        "overall_note",
        "tier",
        "categories",
        "manual_review_flags",
    }
    for crit, cat in NEW_MVP.items():
        assert set(_crit(data, cat, crit)) == {"score", "max", "evidence"}


# --------------------------------------------------------------------------
# Docs contract: knowledge doc + SKILL.md
# --------------------------------------------------------------------------

DOC = REPO_ROOT / "plugins" / "dev-team" / "knowledge" / "ai-friendly-repo-guidelines.md"
CATEGORY_HEADINGS = (
    "## Layered Context Architecture",
    "## Deterministic Verification & Fast Feedback Loops",
    "## Navigable Repository Layout",
)


def _doc_sections() -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current = None
    for line in DOC.read_text().splitlines():
        if line.startswith("## "):
            current = line
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return sections


def test_knowledge_doc_has_three_category_sections_with_bullets() -> None:
    sections = _doc_sections()
    for heading in CATEGORY_HEADINGS:
        assert heading in sections, heading
        bullets = [ln for ln in sections[heading] if ln.startswith("- ")]
        assert len(bullets) >= 2, heading


def test_knowledge_doc_references_every_new_criterion() -> None:
    text = DOC.read_text()
    for crit in (*NEW_MVP, "D7_reference_implementation"):
        assert crit in text, crit


def test_evidence_anchors_resolve_to_doc_headings() -> None:
    import re

    def slug(h: str) -> str:
        return re.sub(r"[^a-z0-9 -]", "", h.lstrip("# ").lower()).replace(" ", "-")

    slugs = {slug(h) for h in _doc_sections()}
    for fixture in ("repo_ai_hostile", "repo_ai_conforming"):
        data = _scan(FIX / fixture)
        for crit, cat in NEW_MVP.items():
            ev = _crit(data, cat, crit)["evidence"]
            assert ev.split("#")[-1].rstrip(")") in slugs, ev


def test_skill_md_has_row_per_scored_criterion() -> None:
    text = (SKILL / "SKILL.md").read_text()
    for crit in scanner.ANALYZERS:
        assert f"| {crit} |" in text, crit
    assert "D7_reference_implementation" in text
    assert "knowledge/ai-friendly-repo-guidelines.md" in text


def test_skill_md_allowed_tools_stay_read_only() -> None:
    text = (SKILL / "SKILL.md").read_text()
    front = text.split("---")[1].splitlines()
    start = next(i for i, ln in enumerate(front) if ln.startswith("allowed-tools:"))
    value = []
    for ln in front[start + 1 :]:
        if ln and not ln[0].isspace():
            break  # next frontmatter key
        value.append(ln.strip())
    tools = {t.strip() for t in " ".join(value).split(", ") if t.strip()}
    assert tools == {"Bash(python3 *)", "Read", "Glob"}


def test_b5_pyproject_optional_dependencies_all_is_not_a_task(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project.optional-dependencies]\nall = ["pytest", "ruff"]\n'
    )
    assert _b5(tmp_path)["score"] == 0


def test_b5_pyproject_dependency_groups_ci_is_not_a_task(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[dependency-groups]\nci = ["pytest", "ruff"]\n'
    )
    assert _b5(tmp_path)["score"] == 0


def test_b5_pyproject_task_runner_tables_count(tmp_path: Path) -> None:
    for table in (
        "tool.poe.tasks",
        "tool.taskipy.tasks",
        "tool.hatch.envs.default.scripts",
        "tool.pdm.scripts",
    ):
        root = tmp_path / table
        root.mkdir()
        (root / "pyproject.toml").write_text(f'[{table}]\ncheck = "ruff . && pytest"\n')
        assert _b5(root)["score"] == 2, table


def test_b5_pyproject_key_after_non_task_table_does_not_leak(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.poe.tasks]\nlint = "ruff ."\n'
        '[project.optional-dependencies]\nall = ["pytest", "ruff"]\n'
    )
    assert _b5(tmp_path)["score"] == 0


def test_d5_not_applicable_results_are_exempt_from_evidence_contract(
    tmp_path: Path,
) -> None:
    res = afa.d5_claude_md_size(tmp_path, _cfg())
    assert res["max"] == 0
    assert not res["evidence"].startswith("found ")
    assert "N/A results" in (SKILL / "SKILL.md").read_text()
