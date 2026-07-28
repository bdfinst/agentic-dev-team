"""Tests for scripts/check_review_agent_mcp_tools.py (#1467 tiered grants)."""

import sys
from pathlib import Path

# Make the scripts directory importable
SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from check_review_agent_mcp_tools import (
    EXEMPT_AGENTS,
    FORBIDDEN_FOR_EXEMPT,
    MCP_TOOL_NAMES,
    REASSIGNED_TOOLS,
    SKILL_REQUIRED_PHRASES,
    _agents_dir_default,
    _skill_file_default,
    check_skill,
    find_forbidden,
    find_review_agents,
    fix_tools_line,
    forbidden_present,
    main,
    missing_mcp_tools,
    parse_tools,
    required_tools_for,
)

_SKILL_TEXT = " ".join(SKILL_REQUIRED_PHRASES)  # a skill body containing every required phrase

REAL_AGENTS_DIR = _agents_dir_default()
REAL_SKILL_FILE = _skill_file_default()

# Sample of well-known non-review agents that the *-review invariant must NOT touch.
# NB: software-engineer et al. DO grant these tools via the non-review mapping
# (#1108, enforced by check_agent_tool_mapping.py) — so the sample is limited to
# agents in the excluded tier, which grant none of the MCP tools.
NON_REVIEW_SAMPLE = ["orchestrator", "product-manager"]

# Every review agent that stays on the generic BASE_MCP_TOOLS five-tool tier —
# i.e. every *-review agent not in EXEMPT_AGENTS or REASSIGNED_TOOLS.
GENERIC_TIER_SAMPLE = ["security-review", "structure-review", "arch-review"]


# ---------------------------------------------------------------------------
# Contract pins — independent oracles for the canonical tool-name strings and
# tier membership. Without these, every other assertion references the same
# module constants as its own oracle, so a typo would propagate undetected.
# ---------------------------------------------------------------------------

def test_mcp_tool_names_are_the_expected_literals():
    assert MCP_TOOL_NAMES == [
        "mcp__codegraph__codegraph_explore",
        "mcp__plugin_repowise_repowise__get_context",
        "mcp__plugin_repowise_repowise__get_symbol",
        "mcp__plugin_repowise_repowise__search_codebase",
        "mcp__plugin_repowise_repowise__get_risk",
    ]


def test_exempt_agents_are_the_expected_two():
    assert EXEMPT_AGENTS == {"claude-setup-review", "token-efficiency-review"}


def test_reassigned_tools_cover_the_expected_four_agents():
    assert set(REASSIGNED_TOOLS) == {
        "refactor-opportunity-review",
        "performance-review",
        "complexity-review",
        "doc-review",
    }


def test_refactor_opportunity_review_required_set():
    assert REASSIGNED_TOOLS["refactor-opportunity-review"] == [
        "mcp__codegraph__codegraph_explore",
        "mcp__plugin_repowise_repowise__get_context",
        "mcp__plugin_repowise_repowise__get_symbol",
        "mcp__plugin_repowise_repowise__get_dead_code",
        "mcp__plugin_repowise_repowise__get_health",
    ]


def test_performance_review_and_complexity_review_required_sets():
    expected = [
        "mcp__codegraph__codegraph_explore",
        "mcp__plugin_repowise_repowise__get_context",
        "mcp__plugin_repowise_repowise__get_symbol",
        "mcp__plugin_repowise_repowise__search_codebase",
        "mcp__plugin_repowise_repowise__get_health",
    ]
    assert REASSIGNED_TOOLS["performance-review"] == expected
    assert REASSIGNED_TOOLS["complexity-review"] == expected


def test_doc_review_required_set():
    assert REASSIGNED_TOOLS["doc-review"] == [
        "mcp__codegraph__codegraph_explore",
        "mcp__plugin_repowise_repowise__get_context",
        "mcp__plugin_repowise_repowise__get_symbol",
        "mcp__plugin_repowise_repowise__get_why",
    ]


def test_forbidden_for_exempt_is_base_plus_get_why_health_dead_code():
    assert FORBIDDEN_FOR_EXEMPT == MCP_TOOL_NAMES + [
        "mcp__plugin_repowise_repowise__get_why",
        "mcp__plugin_repowise_repowise__get_health",
        "mcp__plugin_repowise_repowise__get_dead_code",
    ]


# ---------------------------------------------------------------------------
# required_tools_for — the per-agent tier dispatch
# ---------------------------------------------------------------------------

def test_required_tools_for_exempt_agent_is_empty():
    assert required_tools_for("claude-setup-review") == []
    assert required_tools_for("token-efficiency-review") == []


def test_required_tools_for_reassigned_agent_is_its_own_set():
    assert required_tools_for("doc-review") == REASSIGNED_TOOLS["doc-review"]


def test_required_tools_for_other_review_agent_is_generic_base():
    assert required_tools_for("security-review") == MCP_TOOL_NAMES


# ---------------------------------------------------------------------------
# Pure-function unit tests (synthetic content — pass independent of migration)
# ---------------------------------------------------------------------------

def test_fix_appends_generic_five_when_absent():
    text = "---\nname: foo-review\ntools: Read, Grep, Glob\n---\n# Body\n"
    new_text, added = fix_tools_line(text, "foo-review")
    assert added == MCP_TOOL_NAMES
    tokens = parse_tools(new_text)
    assert tokens[:3] == ["Read", "Grep", "Glob"]
    for name in MCP_TOOL_NAMES:
        assert name in tokens


def test_fix_appends_reassigned_set_for_doc_review():
    text = "---\nname: doc-review\ntools: Read, Grep, Glob\n---\n# Body\n"
    new_text, added = fix_tools_line(text, "doc-review")
    assert added == REASSIGNED_TOOLS["doc-review"]
    tokens = parse_tools(new_text)
    for name in REASSIGNED_TOOLS["doc-review"]:
        assert name in tokens
    # never appends the tools this agent gave up
    assert "mcp__plugin_repowise_repowise__get_risk" not in tokens
    assert "mcp__plugin_repowise_repowise__search_codebase" not in tokens


def test_fix_is_noop_for_exempt_agent_with_no_tools_required():
    text = "---\nname: claude-setup-review\ntools: Read, Grep, Glob\n---\n# Body\n"
    new_text, added = fix_tools_line(text, "claude-setup-review")
    assert added == []
    assert new_text == text


def test_fix_preserves_skill_token():
    text = "---\ntools: Read, Grep, Glob, Skill\n---\n"
    new_text, _ = fix_tools_line(text, "foo-review")
    tokens = parse_tools(new_text)
    assert "Skill" in tokens
    assert tokens[:4] == ["Read", "Grep", "Glob", "Skill"]


def test_fix_is_idempotent():
    text = "---\ntools: Read, Grep, Glob\n---\n"
    once, _ = fix_tools_line(text, "foo-review")
    twice, added_again = fix_tools_line(once, "foo-review")
    assert added_again == []
    assert once == twice


def test_missing_reports_generic_five_when_no_tools_line():
    assert missing_mcp_tools("---\nname: x\n---\n", "foo-review") == MCP_TOOL_NAMES


def test_missing_reports_nothing_for_exempt_agent_regardless_of_tools_line():
    assert missing_mcp_tools("---\nname: x\n---\n", "claude-setup-review") == []


def test_parse_tools_returns_none_without_line_and_tokens_with():
    assert parse_tools("---\nname: x\n---\n") is None
    assert parse_tools("---\ntools: Read, Grep\n---\n") == ["Read", "Grep"]


def test_check_skill_reports_absent_phrases():
    assert check_skill("nothing relevant here") == SKILL_REQUIRED_PHRASES
    assert check_skill(_SKILL_TEXT) == []


# ---------------------------------------------------------------------------
# forbidden_present / find_forbidden — the exempt-agent "should have none" gate
# ---------------------------------------------------------------------------

def test_forbidden_present_empty_when_no_code_intel_tools_granted():
    text = "---\nname: claude-setup-review\ntools: Read, Grep, Glob\n---\n"
    assert forbidden_present(text) == []


def test_forbidden_present_flags_any_regranted_tool():
    text = (
        "---\nname: claude-setup-review\n"
        "tools: Read, Grep, Glob, mcp__plugin_repowise_repowise__get_risk\n---\n"
    )
    assert forbidden_present(text) == ["mcp__plugin_repowise_repowise__get_risk"]


def test_forbidden_present_flags_get_why_and_get_health_too():
    text = (
        "---\nname: token-efficiency-review\n"
        "tools: Read, Grep, Glob, mcp__plugin_repowise_repowise__get_why, "
        "mcp__plugin_repowise_repowise__get_health\n---\n"
    )
    assert forbidden_present(text) == [
        "mcp__plugin_repowise_repowise__get_why",
        "mcp__plugin_repowise_repowise__get_health",
    ]


def test_forbidden_present_satisfied_by_server_wildcard():
    text = "---\nname: claude-setup-review\ntools: Read, Grep, Glob, mcp__codegraph__*\n---\n"
    assert forbidden_present(text) == ["mcp__codegraph__codegraph_explore"]


def test_find_forbidden_ignores_non_exempt_agents(tmp_path):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    _agent(agents_dir, "security-review", "Read, Grep, Glob, " + ", ".join(MCP_TOOL_NAMES))
    agents = find_review_agents(agents_dir)
    assert find_forbidden(agents) == {}


def test_find_forbidden_flags_exempt_agent_with_a_regranted_tool(tmp_path):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    _agent(agents_dir, "claude-setup-review", "Read, Grep, Glob, mcp__plugin_repowise_repowise__get_risk")
    agents = find_review_agents(agents_dir)
    assert find_forbidden(agents) == {
        "claude-setup-review": ["mcp__plugin_repowise_repowise__get_risk"]
    }


# ---------------------------------------------------------------------------
# Integration tests against the real repo (regression protection)
# ---------------------------------------------------------------------------

def test_exempt_agents_grant_zero_mcp_tools_in_the_real_repo():
    for name in EXEMPT_AGENTS:
        agent_file = REAL_AGENTS_DIR / f"{name}.md"
        assert agent_file.is_file(), f"expected exempt agent {name}"
        text = agent_file.read_text(encoding="utf-8")
        assert missing_mcp_tools(text, name) == []  # trivially true (nothing required)
        assert forbidden_present(text) == [], f"{name} unexpectedly grants code-intel MCP tools"


def test_reassigned_agents_grant_their_specific_set_in_the_real_repo():
    for name in REASSIGNED_TOOLS:
        agent_file = REAL_AGENTS_DIR / f"{name}.md"
        assert agent_file.is_file(), f"expected reassigned agent {name}"
        text = agent_file.read_text(encoding="utf-8")
        assert missing_mcp_tools(text, name) == [], f"{name} missing its reassigned tools"


def test_generic_tier_review_agents_still_grant_base_five():
    for name in GENERIC_TIER_SAMPLE:
        agent_file = REAL_AGENTS_DIR / f"{name}.md"
        assert agent_file.is_file(), f"expected generic-tier agent {name}"
        text = agent_file.read_text(encoding="utf-8")
        assert missing_mcp_tools(text, name) == [], f"{name} missing base MCP tools"


def test_every_review_agent_satisfies_its_own_tier():
    agents = find_review_agents(REAL_AGENTS_DIR)
    assert agents, "expected to find *-review agents"
    for agent_file in agents:
        text = agent_file.read_text(encoding="utf-8")
        assert missing_mcp_tools(text, agent_file.stem) == [], f"{agent_file.stem} missing its required tools"
    assert find_forbidden(agents) == {}


def test_review_agents_preserve_read_grep_glob():
    for agent_file in find_review_agents(REAL_AGENTS_DIR):
        tokens = parse_tools(agent_file.read_text(encoding="utf-8"))
        assert tokens is not None, f"{agent_file.stem} has no tools: line"
        for base in ("Read", "Grep", "Glob"):
            assert base in tokens, f"{agent_file.stem} lost {base}"


def test_grant_does_not_leak_into_non_review_agents():
    for name in NON_REVIEW_SAMPLE:
        agent_file = REAL_AGENTS_DIR / f"{name}.md"
        assert agent_file.is_file(), f"expected sample agent {name}"
        tokens = parse_tools(agent_file.read_text(encoding="utf-8")) or []
        for mcp_name in MCP_TOOL_NAMES:
            assert mcp_name not in tokens, f"{name} unexpectedly granted {mcp_name}"


def test_code_review_skill_documents_detection_and_preference():
    assert REAL_SKILL_FILE.is_file()
    assert check_skill(REAL_SKILL_FILE.read_text(encoding="utf-8")) == []


# ---------------------------------------------------------------------------
# main() CLI / exit-code tests (the gate layer CI depends on)
# ---------------------------------------------------------------------------

def _call_main(agents_dir: Path, skill_file: Path, *extra: str) -> int:
    old_argv = sys.argv[:]
    sys.argv = [
        "check_review_agent_mcp_tools.py",
        "--agents-dir", str(agents_dir),
        "--skill-file", str(skill_file),
        *extra,
    ]
    try:
        return main()
    except SystemExit as exc:  # pragma: no cover - main returns rather than exits
        return int(exc.code) if exc.code is not None else 0
    finally:
        sys.argv = old_argv


def _agent(directory: Path, name: str, tools_line: str) -> None:
    (directory / f"{name}.md").write_text(
        f"---\nname: {name}\ntools: {tools_line}\n---\n# {name}\n", encoding="utf-8"
    )


def _tmp_env(tmp_path: Path, skill_ok: bool = True):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    skill_file = tmp_path / "SKILL.md"
    skill_file.write_text(_SKILL_TEXT if skill_ok else "empty", encoding="utf-8")
    return agents_dir, skill_file


def test_main_passes_when_compliant(tmp_path):
    agents_dir, skill_file = _tmp_env(tmp_path)
    _agent(agents_dir, "foo-review", "Read, Grep, Glob, " + ", ".join(MCP_TOOL_NAMES))
    assert _call_main(agents_dir, skill_file) == 0


def test_main_fails_and_names_offender(tmp_path, capsys):
    agents_dir, skill_file = _tmp_env(tmp_path)
    _agent(agents_dir, "bar-review", "Read, Grep, Glob")
    assert _call_main(agents_dir, skill_file) == 1
    assert "bar-review" in capsys.readouterr().out


def test_main_fix_writes_and_is_idempotent(tmp_path):
    agents_dir, skill_file = _tmp_env(tmp_path)
    _agent(agents_dir, "baz-review", "Read, Grep, Glob")
    assert _call_main(agents_dir, skill_file, "--fix") == 0
    assert missing_mcp_tools((agents_dir / "baz-review.md").read_text(), "baz-review") == []
    # detection now clean, and a second --fix changes nothing
    assert _call_main(agents_dir, skill_file) == 0
    assert _call_main(agents_dir, skill_file, "--fix") == 0


def test_main_fix_reports_unfixable_agent_without_tools_line(tmp_path, capsys):
    agents_dir, skill_file = _tmp_env(tmp_path)
    (agents_dir / "notools-review.md").write_text(
        "---\nname: notools-review\n---\n# body\n", encoding="utf-8"
    )
    # --fix cannot append to a missing tools: line — must fail loudly, not false-OK
    assert _call_main(agents_dir, skill_file, "--fix") == 1
    assert "notools-review" in capsys.readouterr().err


def test_main_missing_agents_dir_returns_one(tmp_path, capsys):
    _, skill_file = _tmp_env(tmp_path)
    assert _call_main(tmp_path / "nope", skill_file) == 1
    assert "not found" in capsys.readouterr().err


def test_main_fails_when_skill_prose_missing(tmp_path):
    agents_dir, skill_file = _tmp_env(tmp_path, skill_ok=False)
    _agent(agents_dir, "foo-review", "Read, Grep, Glob, " + ", ".join(MCP_TOOL_NAMES))
    assert _call_main(agents_dir, skill_file) == 1


def test_main_passes_for_exempt_agent_with_no_code_intel_tools(tmp_path):
    agents_dir, skill_file = _tmp_env(tmp_path)
    _agent(agents_dir, "claude-setup-review", "Read, Grep, Glob")
    assert _call_main(agents_dir, skill_file) == 0


def test_main_fails_for_exempt_agent_with_a_regranted_tool(tmp_path, capsys):
    agents_dir, skill_file = _tmp_env(tmp_path)
    _agent(agents_dir, "token-efficiency-review", "Read, Grep, Glob, mcp__plugin_repowise_repowise__get_risk")
    assert _call_main(agents_dir, skill_file) == 1
    out = capsys.readouterr().out
    assert "token-efficiency-review" in out
    assert "forbidden" in out.lower()


def test_main_fix_does_not_strip_forbidden_tool_from_exempt_agent(tmp_path, capsys):
    agents_dir, skill_file = _tmp_env(tmp_path)
    _agent(agents_dir, "claude-setup-review", "Read, Grep, Glob, mcp__plugin_repowise_repowise__get_risk")
    # --fix still fails (forbidden tool untouched) — never silently strips it
    assert _call_main(agents_dir, skill_file, "--fix") == 1
    text = (agents_dir / "claude-setup-review.md").read_text()
    assert "mcp__plugin_repowise_repowise__get_risk" in text
    assert "forbidden" in capsys.readouterr().err.lower()


def test_main_fix_appends_reassigned_set_for_doc_review(tmp_path):
    agents_dir, skill_file = _tmp_env(tmp_path)
    _agent(agents_dir, "doc-review", "Read, Grep, Glob")
    assert _call_main(agents_dir, skill_file, "--fix") == 0
    text = (agents_dir / "doc-review.md").read_text()
    tokens = parse_tools(text)
    for name in REASSIGNED_TOOLS["doc-review"]:
        assert name in tokens
    assert "mcp__plugin_repowise_repowise__get_risk" not in tokens


def test_main_json_emits_only_json_on_stdout(tmp_path, capsys):
    import json

    agents_dir, skill_file = _tmp_env(tmp_path)
    _agent(agents_dir, "bar-review", "Read, Grep, Glob")
    rc = _call_main(agents_dir, skill_file, "--json")
    out = capsys.readouterr().out
    # stdout must be parseable JSON with no trailing prose (structure-review finding)
    parsed = json.loads(out)
    assert rc == 1
    assert "bar-review" in parsed["offenders"]


def test_json_report_smoke(tmp_path, capsys):
    import json

    agents_dir, skill_file = _tmp_env(tmp_path)
    _agent(agents_dir, "foo-review", "Read, Grep, Glob, " + ", ".join(MCP_TOOL_NAMES))
    rc = _call_main(agents_dir, skill_file, "--json")
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    # Common envelope shared by all three MCP grant-check scripts (#1393).
    assert set(out) == {
        "check", "evaluated", "offenders", "unclassified", "fixed", "unfixable", "ok", "notes",
    }
    assert out["check"] == "review-agent-mcp-tools"
    assert out["evaluated"] == ["foo-review"]
    assert out["offenders"] == {}
    assert out["unclassified"] == []
    assert out["fixed"] == {}
    assert out["unfixable"] == []
    assert out["ok"] is True
    assert out["notes"] == {"skill_missing_phrases": [], "forbidden": {}}


def test_json_report_exposes_forbidden_distinctly_from_offenders(tmp_path, capsys):
    import json

    agents_dir, skill_file = _tmp_env(tmp_path)
    _agent(agents_dir, "claude-setup-review", "Read, Grep, Glob, mcp__plugin_repowise_repowise__get_risk")
    rc = _call_main(agents_dir, skill_file, "--json")
    assert rc == 1
    out = json.loads(capsys.readouterr().out)
    # not reported as a "missing" offender — it's a forbidden-tools-present finding
    assert out["offenders"] == {}
    assert out["notes"]["forbidden"] == {
        "claude-setup-review": ["mcp__plugin_repowise_repowise__get_risk"]
    }


def test_json_report_fix_mode_reflects_post_fix_offenders(tmp_path, capsys):
    import json

    agents_dir, skill_file = _tmp_env(tmp_path)
    _agent(agents_dir, "baz-review", "Read, Grep, Glob")
    rc = _call_main(agents_dir, skill_file, "--fix", "--json")
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["check"] == "review-agent-mcp-tools"
    assert "baz-review" in out["fixed"]
    assert out["offenders"] == {}  # computed from the already-fixed text
    assert out["unfixable"] == []
    assert out["ok"] is True
