"""Tests for scripts/check_review_agent_mcp_tools.py."""

import sys
from pathlib import Path

# Make the scripts directory importable
SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from check_review_agent_mcp_tools import (
    MCP_TOOL_NAMES,
    SKILL_REQUIRED_PHRASES,
    _agents_dir_default,
    _skill_file_default,
    check_skill,
    find_review_agents,
    fix_tools_line,
    main,
    missing_mcp_tools,
    parse_tools,
)

_SKILL_TEXT = " ".join(SKILL_REQUIRED_PHRASES)  # a skill body containing every required phrase

REAL_AGENTS_DIR = _agents_dir_default()
REAL_SKILL_FILE = _skill_file_default()

# Sample of well-known non-review agents that the *-review invariant must NOT touch.
# NB: software-engineer et al. DO grant these tools via the non-review mapping
# (#1108, enforced by check_agent_tool_mapping.py) — so the sample is limited to
# agents in the excluded tier, which grant none of the MCP tools.
NON_REVIEW_SAMPLE = ["orchestrator", "product-manager"]


# ---------------------------------------------------------------------------
# Contract pin — independent oracle for the canonical tool-name strings.
# Without this, every other assertion references MCP_TOOL_NAMES as its own
# oracle, so a typo in the constant would propagate through --fix undetected.
# ---------------------------------------------------------------------------

def test_mcp_tool_names_are_the_expected_literals():
    assert MCP_TOOL_NAMES == [
        "mcp__codegraph__codegraph_explore",
        "mcp__plugin_repowise_repowise__get_context",
        "mcp__plugin_repowise_repowise__get_symbol",
        "mcp__plugin_repowise_repowise__search_codebase",
        "mcp__plugin_repowise_repowise__get_risk",
    ]


# ---------------------------------------------------------------------------
# Pure-function unit tests (synthetic content — pass independent of migration)
# ---------------------------------------------------------------------------

def test_fix_appends_all_five_when_absent():
    text = "---\nname: foo-review\ntools: Read, Grep, Glob\n---\n# Body\n"
    new_text, added = fix_tools_line(text)
    assert added == MCP_TOOL_NAMES
    tokens = parse_tools(new_text)
    assert tokens[:3] == ["Read", "Grep", "Glob"]
    for name in MCP_TOOL_NAMES:
        assert name in tokens


def test_fix_preserves_skill_token():
    text = "---\ntools: Read, Grep, Glob, Skill\n---\n"
    new_text, _ = fix_tools_line(text)
    tokens = parse_tools(new_text)
    assert "Skill" in tokens
    assert tokens[:4] == ["Read", "Grep", "Glob", "Skill"]


def test_fix_does_not_add_skill_when_absent():
    text = "---\ntools: Read, Grep, Glob\n---\n"
    new_text, _ = fix_tools_line(text)
    assert "Skill" not in parse_tools(new_text)


def test_fix_is_idempotent():
    text = "---\ntools: Read, Grep, Glob\n---\n"
    once, _ = fix_tools_line(text)
    twice, added_again = fix_tools_line(once)
    assert added_again == []
    assert once == twice


def test_missing_reports_all_when_no_tools_line():
    assert missing_mcp_tools("---\nname: x\n---\n") == MCP_TOOL_NAMES


def test_fix_no_ops_when_no_tools_line():
    text = "---\nname: x\n---\n# Body\n"
    assert fix_tools_line(text) == (text, [])


def test_parse_tools_returns_none_without_line_and_tokens_with():
    assert parse_tools("---\nname: x\n---\n") is None
    assert parse_tools("---\ntools: Read, Grep\n---\n") == ["Read", "Grep"]


def test_check_skill_reports_absent_phrases():
    assert check_skill("nothing relevant here") == SKILL_REQUIRED_PHRASES
    assert check_skill(_SKILL_TEXT) == []


# ---------------------------------------------------------------------------
# Integration tests against the real repo (regression protection)
# ---------------------------------------------------------------------------

def test_every_review_agent_grants_all_five_mcp_tools():
    agents = find_review_agents(REAL_AGENTS_DIR)
    assert agents, "expected to find *-review agents"
    for agent_file in agents:
        text = agent_file.read_text(encoding="utf-8")
        assert missing_mcp_tools(text) == [], f"{agent_file.stem} missing MCP tools"


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
    assert missing_mcp_tools((agents_dir / "baz-review.md").read_text()) == []
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
    assert out["notes"] == {"skill_missing_phrases": []}


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
