"""Tests for scripts/check_security_assessment_mcp_tools.py (#1388)."""

import json
import shutil
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from check_security_assessment_mcp_tools import (
    BASE_MCP_TOOLS,
    CODE_READING_AGENTS,
    NON_CODE_READING_AGENTS,
    _agents_dir_default,
    apply_fixes,
    find_offenders,
    main,
    unclassified_agents,
)

REAL_AGENTS_DIR = _agents_dir_default()


# --- Live checks against the real, shipped agent files ---------------------

def test_real_repo_passes_clean():
    assert find_offenders(REAL_AGENTS_DIR) == {}
    assert unclassified_agents(REAL_AGENTS_DIR) == []


def test_main_exit_zero_on_real_repo():
    assert main([]) == 0


def test_agents_dir_resolves_to_security_assessment_plugin():
    assert REAL_AGENTS_DIR.exists()
    assert REAL_AGENTS_DIR.parts[-2:] == ("security-assessment", "agents")


def test_every_code_reading_agent_file_exists():
    for name in CODE_READING_AGENTS:
        assert (REAL_AGENTS_DIR / f"{name}.md").is_file(), name


def test_rosters_are_disjoint_and_cover_every_agent_on_disk():
    code_reading = set(CODE_READING_AGENTS)
    non_code_reading = set(NON_CODE_READING_AGENTS)
    assert code_reading.isdisjoint(non_code_reading)
    on_disk = {p.stem for p in REAL_AGENTS_DIR.glob("*.md")}
    assert on_disk == code_reading | non_code_reading


def test_non_code_reading_agents_are_not_granted_the_mcp_tools():
    # These agents interpret fixed upstream artifacts only; a codegraph/repowise
    # grant would be inert for them, and the check must not require it.
    from mcp_tool_grants import parse_tools

    for name in NON_CODE_READING_AGENTS:
        path = REAL_AGENTS_DIR / f"{name}.md"
        tokens = parse_tools(path.read_text(encoding="utf-8")) or []
        assert "Glob" not in tokens, f"{name} unexpectedly grants Glob"


# --- Behaviour against a synthetic copy ------------------------------------

def _clone_agents(tmp_path):
    dst = tmp_path / "agents"
    shutil.copytree(REAL_AGENTS_DIR, dst)
    return dst


def test_under_granted_agent_fails(tmp_path):
    agents = _clone_agents(tmp_path)
    target = agents / "deep-code-reasoning.md"
    text = target.read_text(encoding="utf-8")
    text = text.replace(", mcp__plugin_repowise_repowise__get_risk", "", 1)
    target.write_text(text, encoding="utf-8")
    offenders = find_offenders(agents)
    assert "deep-code-reasoning" in offenders
    assert "mcp__plugin_repowise_repowise__get_risk" in offenders["deep-code-reasoning"]


def test_missing_agent_file_is_an_offender(tmp_path):
    agents = _clone_agents(tmp_path)
    (agents / "fp-reduction.md").unlink()
    offenders = find_offenders(agents)
    assert offenders["fp-reduction"] == list(BASE_MCP_TOOLS)


def test_unclassified_new_agent_trips_check(tmp_path):
    agents = _clone_agents(tmp_path)
    (agents / "widget-scanner.md").write_text(
        "---\nname: widget-scanner\ntools: Read, Grep, Glob\n---\n# Widget Scanner\n",
        encoding="utf-8",
    )
    assert "widget-scanner" in unclassified_agents(agents)


def test_fix_appends_missing_without_dropping_existing(tmp_path):
    agents = _clone_agents(tmp_path)
    target = agents / "recon-driven-scan.md"
    before = target.read_text(encoding="utf-8")
    target.write_text(
        before.replace(", " + BASE_MCP_TOOLS[0], "", 1), encoding="utf-8"
    )
    fixed = apply_fixes(agents)
    assert "recon-driven-scan" in fixed
    assert BASE_MCP_TOOLS[0] in fixed["recon-driven-scan"]

    from mcp_tool_grants import parse_tools

    grants = parse_tools(target.read_text(encoding="utf-8"))
    for base in ("Read", "Grep", "Glob", "Bash"):
        assert base in grants  # pre-existing grants preserved
    for tool in BASE_MCP_TOOLS:
        assert tool in grants


def test_fix_is_idempotent(tmp_path):
    agents = _clone_agents(tmp_path)
    target = agents / "cross-repo-synthesizer.md"
    before = target.read_text(encoding="utf-8")
    target.write_text(
        before.replace(", " + BASE_MCP_TOOLS[-1], "", 1), encoding="utf-8"
    )
    first = apply_fixes(agents)
    assert "cross-repo-synthesizer" in first
    second = apply_fixes(agents)
    assert second == {}


def test_json_report_smoke(tmp_path, capsys):
    agents = _clone_agents(tmp_path)
    rc = main(["--agents-dir", str(agents), "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert set(out) == {"reviewed", "offenders", "unclassified"}
    assert out["offenders"] == {}
    assert out["unclassified"] == []


def test_main_missing_agents_dir_returns_one(tmp_path, capsys):
    rc = main(["--agents-dir", str(tmp_path / "nope")])
    assert rc == 1
    assert "not found" in capsys.readouterr().err
