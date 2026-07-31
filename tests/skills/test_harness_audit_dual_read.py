"""Content-guard: harness-audit/SKILL.md's bash commands dual-read migrated
metrics (AC20, Finding 2; Slice 5 Step 5.11, plan
opt-in-metrics-and-claude-scoped-artifacts.md).

review-value.jsonl and config-changelog.jsonl may exist at either the legacy
bare metrics/ path or the migrated .claude/metrics/ path for a project
mid-transition. Every bash command referencing either file must prefer the
new path and fall back to the bare path only when the new one is absent.
session-digest.jsonl is explicitly out of scope (written by the out-of-scope
/agent-eval and /session-review) and must NOT gain the idiom.
"""

from __future__ import annotations

import re

from skill_doc_helpers import PLUGIN_ROOT

SKILL_PATH = PLUGIN_ROOT / "skills" / "harness-audit" / "SKILL.md"
SKILL = SKILL_PATH.read_text(encoding="utf-8")

_BASH_BLOCK_RE = re.compile(r"```bash\n(.*?)```", re.DOTALL)
_DUAL_READ_RE = re.compile(
    r'(\w+)="\.claude/metrics/([\w.-]+)";\s*\[ -f "\$\1" \]\s*\|\|\s*\1="metrics/\2"'
)

_TARGET_FILES = ("review-value.jsonl", "config-changelog.jsonl")


def _bash_blocks() -> list[str]:
    return _BASH_BLOCK_RE.findall(SKILL)


#: Exact count of bash blocks in harness-audit/SKILL.md that touch a migrated
#: metrics file. Pinned so a dual-read block cannot be silently *dropped*
#: (the idiom test below already catches a newly-added block that forgets the
#: idiom, but it cannot notice one going missing). Moved 4 -> 6 in #1624,
#: which added the churn-ratio and per-agent-purpose-split queries to Step 4a.
_EXPECTED_AFFECTED_BLOCKS = 6


def test_expected_number_of_bash_commands_reference_the_migrated_metrics_files():
    blocks = [b for b in _bash_blocks() if any(f in b for f in _TARGET_FILES)]
    assert len(blocks) == _EXPECTED_AFFECTED_BLOCKS, (
        f"expected {_EXPECTED_AFFECTED_BLOCKS} affected bash commands, found {len(blocks)}"
    )


def test_every_affected_block_uses_the_dual_read_idiom():
    for block in _bash_blocks():
        if not any(f in block for f in _TARGET_FILES):
            continue
        assert _DUAL_READ_RE.search(block), (
            "bash block references a migrated metrics file without the "
            f"dual-read fallback idiom:\n{block}"
        )


def test_dual_read_prefers_the_new_path_over_the_legacy_path():
    for match in _DUAL_READ_RE.finditer(SKILL):
        full = match.group(0)
        new_path_idx = full.index(".claude/metrics/")
        fallback_idx = full.index("||")
        assert new_path_idx < fallback_idx, (
            "the .claude/metrics/ path must be assigned before the "
            "fallback-on-absence check"
        )


def test_no_command_hardcodes_the_bare_path_outside_the_idiom():
    for block in _bash_blocks():
        stripped = _DUAL_READ_RE.sub("", block)
        for f in _TARGET_FILES:
            assert f"metrics/{f}" not in stripped or f".claude/metrics/{f}" in stripped, (
                f"bash block still hardcodes bare metrics/{f} outside the "
                f"dual-read idiom:\n{block}"
            )


def test_session_digest_jsonl_is_out_of_scope_and_unmigrated():
    """session-digest.jsonl is written by /agent-eval / /session-review —
    explicitly out of scope for this step; it must NOT gain the dual-read
    idiom (which would be premature/incorrect since nothing migrates it)."""
    assert "metrics/session-digest.jsonl" in SKILL
    assert '.claude/metrics/session-digest.jsonl' not in SKILL
