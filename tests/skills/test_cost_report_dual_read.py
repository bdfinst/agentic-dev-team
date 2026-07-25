"""Content-guard: cost-report/SKILL.md's bash commands dual-read migrated
metrics (AC20, Finding 2; Slice 5 Step 5.11, plan
opt-in-metrics-and-claude-scoped-artifacts.md).

cost-metering.jsonl and review-value.jsonl may exist at either the legacy
bare metrics/ path or the migrated .claude/metrics/ path for a project
mid-transition. Every bash command referencing either file must prefer the
new path and fall back to the bare path only when the new one is absent —
never hardcode the bare path directly as a command argument.
"""

from __future__ import annotations

import re

from skill_doc_helpers import PLUGIN_ROOT

SKILL_PATH = PLUGIN_ROOT / "skills" / "cost-report" / "SKILL.md"
SKILL = SKILL_PATH.read_text(encoding="utf-8")

_BASH_BLOCK_RE = re.compile(r"```bash\n(.*?)```", re.DOTALL)
_DUAL_READ_RE = re.compile(
    r'log="\.claude/metrics/([\w.-]+)";\s*\[ -f "\$log" \]\s*\|\|\s*log="metrics/\1"'
)

# Bare reference to one of the migrated files, NOT already wrapped in the
# dual-read assignment's own right-hand side (the fallback literal itself is
# expected to name the bare path once, inside the idiom).
_TARGET_FILES = ("cost-metering.jsonl", "review-value.jsonl")


def _bash_blocks() -> list[str]:
    return _BASH_BLOCK_RE.findall(SKILL)


def test_five_bash_commands_reference_the_migrated_metrics_files():
    blocks = [
        b for b in _bash_blocks() if any(f in b for f in _TARGET_FILES)
    ]
    assert len(blocks) == 5, f"expected 5 affected bash commands, found {len(blocks)}"


def test_every_affected_block_uses_the_dual_read_idiom():
    for block in _bash_blocks():
        if not any(f in block for f in _TARGET_FILES):
            continue
        assert _DUAL_READ_RE.search(block), (
            f"bash block references a migrated metrics file without the "
            f"dual-read fallback idiom:\n{block}"
        )


def test_dual_read_prefers_the_new_path_over_the_legacy_path():
    """The idiom checks .claude/metrics/ FIRST and only falls back to the
    bare metrics/ path when the new one does not exist — "prefer new when
    both exist" is exactly what `[ -f "$log" ] || log=...` expresses: the
    fallback assignment only runs when the preferred path test fails."""
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
        # Strip out the dual-read assignment lines themselves, then check
        # nothing else in the block still hardcodes a bare metrics/ path for
        # one of the affected files.
        stripped = _DUAL_READ_RE.sub("", block)
        for f in _TARGET_FILES:
            assert f"metrics/{f}" not in stripped or f".claude/metrics/{f}" in stripped, (
                f"bash block still hardcodes bare metrics/{f} outside the "
                f"dual-read idiom:\n{block}"
            )
