"""Content-guard: root CLAUDE.md and performance-metrics/SKILL.md no longer
describe bare project-scoped metrics/memory/reports paths as writer targets
(Slice 7, Step 7.1, plan opt-in-metrics-and-claude-scoped-artifacts.md).

`metrics/verify-log.jsonl` stays bare (AC3 exemption) and the illustrative
`"plan": "plans/add-auth.md"` JSON example values are a distinct concept (the
operator-authored implementation-plan file, same as /plan's own shipped
default) — neither is touched by this sweep.
"""

from __future__ import annotations

import re

from _repo_root import REPO_ROOT

CLAUDE_MD = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
PLUGIN_CLAUDE_MD = (
    REPO_ROOT / "plugins" / "dev-team" / "CLAUDE.md"
).read_text(encoding="utf-8")
PERF_METRICS = (
    REPO_ROOT
    / "plugins"
    / "dev-team"
    / "skills"
    / "performance-metrics"
    / "SKILL.md"
).read_text(encoding="utf-8")

# metrics/verify-log.jsonl is the one permanently-exempt bare path (AC3).
_BARE_METRICS_RE = re.compile(r"(?<!\.claude/)metrics/(?!verify-log\.jsonl)")
_BARE_MEMORY_RE = re.compile(r"(?<!\.claude/)memory/")


def test_claude_md_reports_line_names_the_consolidated_domain() -> None:
    assert ".dev-team-reports/" in CLAUDE_MD
    assert "reports/" in CLAUDE_MD  # legacy line stays present, just re-labeled


def test_plugin_claude_md_has_no_bare_metrics_or_memory_reference() -> None:
    # the one benign hit is the "performance-metrics/SKILL.md" link, which
    # contains "metrics/" not a bare writer-target path — assert memory/
    # cleanly and check metrics/ excluding that specific link text.
    assert not _BARE_MEMORY_RE.search(PLUGIN_CLAUDE_MD)
    stripped = PLUGIN_CLAUDE_MD.replace("performance-metrics/SKILL.md", "")
    assert not _BARE_METRICS_RE.search(stripped)
    assert ".claude/memory/" in PLUGIN_CLAUDE_MD
    assert ".claude/metrics/" in PLUGIN_CLAUDE_MD


def test_performance_metrics_has_no_bare_metrics_writer_targets() -> None:
    assert not _BARE_METRICS_RE.search(PERF_METRICS), (
        "found a bare metrics/ reference in performance-metrics/SKILL.md not "
        "migrated to .claude/metrics/ (verify-log.jsonl is the only exemption)"
    )


def test_performance_metrics_has_no_bare_memory_reference() -> None:
    assert not _BARE_MEMORY_RE.search(PERF_METRICS), (
        "found a bare memory/ reference in performance-metrics/SKILL.md not "
        "migrated to .claude/memory/"
    )


def test_performance_metrics_verify_log_stays_bare() -> None:
    assert "metrics/verify-log.jsonl" in PERF_METRICS


def test_performance_metrics_review_value_relocated() -> None:
    assert ".claude/metrics/review-value.jsonl" in PERF_METRICS


def test_performance_metrics_cost_metering_relocated() -> None:
    assert ".claude/metrics/cost-metering.jsonl" in PERF_METRICS


def test_performance_metrics_config_changelog_relocated() -> None:
    assert ".claude/metrics/config-changelog.jsonl" in PERF_METRICS


def test_performance_metrics_task_log_relocated() -> None:
    assert ".claude/metrics/{date}-task-log.jsonl" in PERF_METRICS


def test_performance_metrics_reports_summary_targets_consolidated_domain() -> None:
    assert ".dev-team-reports/" in PERF_METRICS
