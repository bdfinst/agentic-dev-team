"""Content-guard for the /headless-run skill (follow-up to issue #842).

The skill runs a Claude Code command/skill headlessly in an ISOLATED
subprocess — fresh session id + clean HOME/config + scrubbed env — so a
benchmark harness (e.g. the #821 `/code-review`-per-case harness) does not
inherit the parent Remote session's identity/tool surface.

These are structural sensors over the shipped SKILL.md prose (pure greps),
mirroring the other tests/skills/ content guards.
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, frontmatter, grep

SKILL = PLUGIN_ROOT / "skills" / "headless-run" / "SKILL.md"
SKILLS_REG = PLUGIN_ROOT / "knowledge" / "skills-registry.md"


def _text() -> str:
    return SKILL.read_text()


def test_headless_run_skill_md_exists():
    assert SKILL.is_file()


def test_frontmatter_declares_name_description_user_invocable_allowed_tools():
    fm = frontmatter(_text())
    assert grep(r"^name: *headless-run", fm)
    assert grep(r"^description:", fm)
    assert grep(r"^user-invocable: *true", fm)
    assert grep(r"^allowed-tools:", fm)


def test_description_has_no_colon_in_value():
    # /agent-audit FAILs a skill whose description value contains a colon.
    fm = frontmatter(_text())
    # Collect the description value (single or folded block scalar).
    lines = fm.splitlines()
    desc: list[str] = []
    capturing = False
    for line in lines:
        if line.startswith("description:"):
            capturing = True
            rest = line.split("description:", 1)[1].strip()
            if rest and rest not in (">-", ">", "|", "|-"):
                desc.append(rest)
            continue
        if capturing:
            if line and not line.startswith(" ") and ":" in line.split(" ", 1)[0]:
                break  # next frontmatter key
            desc.append(line.strip())
    assert ":" not in " ".join(desc)


def test_description_triggers_on_headless_and_benchmark_phrases():
    fm = frontmatter(_text())
    assert grep(r"headless", fm, ignore_case=True)
    assert grep(r"benchmark|isolated|nested session", fm, ignore_case=True)


def test_body_documents_isolation_guarantees():
    text = _text()
    assert grep(r"--session-id", text)
    assert grep(r"fresh session", text, ignore_case=True)
    assert grep(r"scrub", text, ignore_case=True)
    assert grep(r"CLAUDE_CONFIG_DIR", text)
    assert grep(r"IS_SANDBOX", text)


def test_body_is_honest_about_upstream_caveat():
    text = _text()
    assert grep(r"upstream", text, ignore_case=True)
    # The fully-supported path stays a local checkout, not nested-in-Remote.
    assert grep(r"local checkout", text, ignore_case=True)
    assert grep(r"MCP|tool surface|tool-surface", text)


def test_body_references_the_helper_script_by_plugin_root_path():
    text = _text()
    assert grep(
        r"\$\{CLAUDE_PLUGIN_ROOT\}/skills/headless-run/scripts/isolated_dispatch\.py",
        text,
    )


def test_registered_in_skills_registry():
    assert "skills/headless-run/SKILL.md" in SKILLS_REG.read_text()


def test_body_documents_preserve_auth_tradeoff():
    text = _text()
    assert grep(r"--preserve-auth", text)
    assert grep(r"mcpServers", text)
    assert grep(r"ANTHROPIC_API_KEY", text)
