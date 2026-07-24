"""Tests for scripts/check_agent_tool_mapping.py (#1108)."""

import json
import shutil
import sys
from pathlib import Path

# Make the scripts directory importable
SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from check_agent_tool_mapping import (
    EXCLUSIONS,
    GET_WHY,
    NARROW,
    RATIONALE,
    TIER_CONFIG,
    _agents_dir_default,
    apply_fixes,
    evaluate,
    main,
)

REAL_AGENTS_DIR = _agents_dir_default()

_GRAPHIFY_BASH = "Bash(graphify *)"
NARROW_AGENTS = ["software-engineer", "mutation-kill", "qa-engineer", "data-flow-tracer"]
RATIONALE_AGENTS = [
    "adr-author",
    "architect",
    "security-engineer",
    "platform-engineer",
    "codebase-recon",
]


# --- Live checks against the real, shipped agent files ---------------------

def test_real_repo_passes_clean():
    report = evaluate(REAL_AGENTS_DIR)
    assert report["offenders"] == {}, report["offenders"]
    assert report["unclassified"] == [], report["unclassified"]


def test_main_exit_zero_on_real_repo():
    assert main([]) == 0


def test_narrow_agents_get_base_not_get_why():
    for name in NARROW_AGENTS:
        assert TIER_CONFIG[name][: len(NARROW)] == NARROW
        assert GET_WHY not in TIER_CONFIG[name]


def test_rationale_agents_get_get_why():
    for name in RATIONALE_AGENTS:
        assert TIER_CONFIG[name] == RATIONALE
        assert GET_WHY in TIER_CONFIG[name]


def test_data_flow_tracer_has_scoped_graphify_bash_only():
    tokens = (REAL_AGENTS_DIR / "data-flow-tracer.md").read_text(encoding="utf-8")
    from mcp_tool_grants import parse_tools

    grants = parse_tools(tokens)
    assert _GRAPHIFY_BASH in grants
    assert "Bash" not in grants  # scoped grant only, never unscoped Bash


def test_named_targets_covered_regardless_of_marker():
    # codebase-recon is enforcement: script; mutation-kill has no persona marker.
    # Both must still be covered (via the config-table branch).
    report = evaluate(REAL_AGENTS_DIR)
    assert "codebase-recon" in report["covered"]
    assert "mutation-kill" in report["covered"]


def test_current_exclusions_produce_no_findings():
    report = evaluate(REAL_AGENTS_DIR)
    for name in ["orchestrator", "product-manager", "ui-ux-designer", "tech-writer",
                 "progress-guardian", "session-analysis"]:
        assert name not in report["offenders"]
        assert name not in report["unclassified"]


def test_review_agents_not_evaluated():
    report = evaluate(REAL_AGENTS_DIR)
    assert not any(name.endswith("-review") for name in report["covered"])


# --- Behaviour against a synthetic copy ------------------------------------

def _clone_agents(tmp_path):
    dst = tmp_path / "agents"
    shutil.copytree(REAL_AGENTS_DIR, dst)
    return dst


def test_under_granted_agent_fails(tmp_path):
    agents = _clone_agents(tmp_path)
    se = agents / "software-engineer.md"
    text = se.read_text(encoding="utf-8")
    # Drop one required tool from the tools: line.
    text = text.replace(", mcp__plugin_repowise_repowise__get_risk", "", 1)
    se.write_text(text, encoding="utf-8")
    report = evaluate(agents)
    assert "software-engineer" in report["offenders"]
    assert "mcp__plugin_repowise_repowise__get_risk" in report["offenders"]["software-engineer"]


def test_unmapped_new_team_agent_trips_check(tmp_path):
    agents = _clone_agents(tmp_path)
    (agents / "widget-wrangler.md").write_text(
        "---\nname: widget-wrangler\ntools: Read, Grep, Glob\n---\n\n"
        "You are the widget wrangler.\n\n## Behavioral Guidelines\n\nDo widgets.\n",
        encoding="utf-8",
    )
    report = evaluate(agents)
    assert "widget-wrangler" in report["unclassified"]


def test_fix_appends_missing_without_dropping_existing(tmp_path):
    agents = _clone_agents(tmp_path)
    arch = agents / "architect.md"
    before = arch.read_text(encoding="utf-8")
    # Remove get_why so --fix must re-add it.
    arch.write_text(before.replace(", " + GET_WHY, "", 1), encoding="utf-8")
    fixed = apply_fixes(agents)
    assert "architect" in fixed
    assert GET_WHY in fixed["architect"]
    from mcp_tool_grants import parse_tools

    grants = parse_tools(arch.read_text(encoding="utf-8"))
    for base in ("Read", "Grep", "Glob", "Bash", "Skill"):
        assert base in grants  # pre-existing grants preserved
    assert GET_WHY in grants


def test_json_report_smoke(tmp_path, capsys):
    agents = _clone_agents(tmp_path)
    rc = main(["--agents-dir", str(agents), "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert set(out) == {"covered", "swept", "offenders", "unclassified"}
    assert "software-engineer" in out["covered"]


def test_block_form_tools_line_is_unfixable_not_mangled():
    # A YAML block-sequence tools: form has no inline value — parse_tools must
    # return None and fix_tools_line must leave it untouched (never mangle it).
    from mcp_tool_grants import fix_tools_line, parse_tools

    block = "---\nname: x\ntools:\n  - Read\n  - Grep\n---\n"
    assert parse_tools(block) is None
    new_text, added = fix_tools_line(block, NARROW)
    assert added == []
    assert new_text == block


def test_exclusions_are_subset_of_swept(tmp_path):
    # Every EXCLUSIONS entry must actually be surfaced by the sweep — otherwise it
    # is dead padding (a name the sweep never produces).
    report = evaluate(REAL_AGENTS_DIR)
    swept = set(report["swept"])
    for name in EXCLUSIONS:
        assert name in swept, f"{name} is excluded but never swept — dead entry"
