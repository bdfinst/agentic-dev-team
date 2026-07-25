"""#1376 / #1377 — `/setup` Step 11 must gitignore `.review-passed` and
`.mcp.json` by default for downstream projects.

`.review-passed` (the /code-review gate file) is deleted by the pre-commit
hook on its happy path, but lingers as untracked clutter whenever a commit
never follows a passed review (files edited after review, or
`--no-verify`) — issue #1377. `.mcp.json` commonly bakes in the absolute
filesystem path of the machine that wrote it (Repowise/CodeGraph MCP
registration) and breaks for every other clone if committed — issue #1376.

These are structural sensors over shipped SKILL.md prose — pure text greps,
matching the pattern in test_setup_install_guards.py — not state-mutating
filesystem tests, since the actual `.gitignore` append is a shell block an
agent runs, not a standalone script this suite can invoke directly.
"""

from __future__ import annotations

import re

from skill_doc_helpers import PLUGIN_ROOT, collapsed, section_outside_code

SETUP = (PLUGIN_ROOT / "skills" / "setup" / "SKILL.md").read_text(encoding="utf-8")


def test_review_passed_is_appended_to_runtime_artifacts_gitignore_block():
    body = collapsed(SETUP)
    # Bound the match to the fenced bash block itself (MARKER= line up to
    # the closing ```), not the whole document — .review-passed also
    # appears, unrelated, in the Step 12 sample report further down.
    block = re.search(r'MARKER="# dev-team workflow runtime artifacts.*?```', body)
    assert block
    assert ".review-passed" in block.group(0)


def test_mcp_json_gets_its_own_idempotent_gitignore_block():
    body = collapsed(SETUP)
    # Same bounding as above — .mcp.json also recurs later in the prose
    # (the already-tracked-file guidance, the Step 12 report).
    block = re.search(r'MCP_MARKER="# dev-team hygiene[^"]*".*?```', body)
    assert block
    content = block.group(0)
    assert ".mcp.json" in content
    assert 'grep -qF "$MCP_MARKER" .gitignore' in content


def test_mcp_json_block_is_downstream_only_like_the_runtime_artifacts_block():
    body = collapsed(SETUP)
    mcp_section = body[body.index("machine-specific-path hygiene (issues #1376, #1416)"):]
    assert "downstream-projects-only" in mcp_section[:400]


def test_mcp_json_already_tracked_case_defers_to_operator_not_auto_untrack():
    body = collapsed(SETUP)
    assert "git rm --cached" in body
    assert "rather than doing it automatically" in body


def test_step_12_report_mentions_both_new_gitignore_entries():
    # Scoped to the Step 12 section itself — the unscoped version of this
    # check is satisfied trivially by unrelated Step 11 prose, since both
    # substrings already co-occur there regardless of what Step 12 says.
    # section_outside_code (not section()) because the Step 12 body embeds
    # a fenced sample report that itself contains ### -level headers
    # (e.g. "### Prerequisites") which would otherwise trip the boundary
    # check and truncate the section before reaching the real content.
    step_12 = section_outside_code(SETUP, r"^### 12\. Report", boundary_pattern=r"^### ")
    assert ".review-passed" in step_12
    assert ".mcp.json" in step_12
    assert "#1376" in step_12
