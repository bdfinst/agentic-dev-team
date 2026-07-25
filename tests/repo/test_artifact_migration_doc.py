"""Slice 8, Step 8.1: the operator-facing artifact-migration guidance doc
must exist at a location a downstream operator can actually reach (the
plugin ships only `plugins/dev-team/`, per `.claude-plugin/marketplace.json`'s
`git-subdir` source — a root-level `docs/` file would never install into a
downstream project). It must cover all three per-file migration-strategy
treatments (one-time move, documented clean break, dual-read fallback) plus
the manual, non-auto-migrated consent-file callout (plan Slice 8, AC14).
"""

from __future__ import annotations

from _repo_root import REPO_ROOT

DOC_PATH = REPO_ROOT / "plugins" / "dev-team" / "docs" / "artifact-migration.md"


def _read_doc() -> str:
    assert DOC_PATH.is_file(), f"expected migration doc at {DOC_PATH}"
    return DOC_PATH.read_text(encoding="utf-8")


def test_doc_exists_at_operator_facing_shipped_location():
    # Not solely in the maintainer-facing developer-notes.md, and not in the
    # unshipped repo-root docs/ (only plugins/dev-team/ ships downstream).
    assert DOC_PATH.is_file()
    assert not (REPO_ROOT / "docs" / "artifact-migration.md").exists()
    text = _read_doc()
    assert "developer-notes.md" in text  # cross-references, doesn't replace it


def test_doc_covers_one_time_move_strategy():
    text = _read_doc()
    assert "One-time move" in text
    for filename in ("cost-metering.jsonl", "task-log.jsonl", "boundary-events.jsonl"):
        assert filename in text
    assert ".claude/memory/test-improve/" in text


def test_doc_covers_documented_clean_break_strategy():
    text = _read_doc()
    assert "clean break" in text.lower()
    for filename in (
        "review-value.jsonl",
        "build-phase.json",
        "refactor-backlog.md",
    ):
        assert filename in text
    assert "reports/test-improve/" in text
    assert "plans/test-improve/" in text


def test_doc_covers_dual_read_fallback_strategy():
    text = _read_doc()
    assert "dual-read" in text.lower() or "dual read" in text.lower()
    for command in ("/cost-report", "/artifact-lifecycle", "/harness-audit"):
        assert command in text


def test_doc_covers_consent_file_not_auto_migrated_callout():
    text = _read_doc()
    assert "~/.claude/telemetry.json" in text
    lowered = text.lower()
    assert "not carried forward" in lowered or "not automatic" in lowered
    assert "re-opt-in" in lowered
