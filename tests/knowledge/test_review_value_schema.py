"""Content contract for the `review-value.jsonl` schema (#1256, #1257).

The stream gained two fields in the 2026-07-20 audit follow-up:
- `severity_breakdown` — `{errors, warnings, suggestions}` counts so
  `/harness-audit` Step 3 can flag mostly-minor lenses (#1256).
- `source` — row provenance (`build-checkpoint` vs read-only `code-review`) so
  `/harness-audit` Step 4 excludes read-only rows from fix-rate drop-candidate
  logic (#1257).

The schema is documented in three places that must stay in sync: the
`telemetry-schema.md` reference, the `performance-metrics` skill, and the
`/build` emitter that writes the rows. This test pins all three.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_PLUGIN = REPO_ROOT / "plugins" / "dev-team"

TELEMETRY = _PLUGIN / "knowledge" / "telemetry-schema.md"
PERF_METRICS = _PLUGIN / "skills" / "performance-metrics" / "SKILL.md"
BUILD = _PLUGIN / "skills" / "build" / "SKILL.md"
HARNESS_AUDIT = _PLUGIN / "skills" / "harness-audit" / "SKILL.md"


@pytest.fixture(scope="module")
def telemetry() -> str:
    return TELEMETRY.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def perf() -> str:
    return PERF_METRICS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def build() -> str:
    return BUILD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def audit() -> str:
    return HARNESS_AUDIT.read_text(encoding="utf-8")


class TestSeverityBreakdown:
    def test_documented_in_telemetry_schema(self, telemetry):
        assert "severity_breakdown" in telemetry

    def test_documented_in_performance_metrics(self, perf):
        assert "severity_breakdown" in perf

    def test_emitted_by_build(self, build):
        # The /build emitter JSON must carry the field, split into the three
        # severity buckets of the /code-review enum.
        assert "severity_breakdown" in build
        for bucket in ("errors", "warnings", "suggestions"):
            assert bucket in build

    def test_harness_audit_consumes_it(self, audit):
        assert "severity_breakdown" in audit


class TestSourceProvenance:
    def test_documented_in_telemetry_schema(self, telemetry):
        assert "source" in telemetry
        assert "build-checkpoint" in telemetry
        assert "code-review" in telemetry

    def test_documented_in_performance_metrics(self, perf):
        assert "build-checkpoint" in perf

    def test_emitted_by_build(self, build):
        assert "build-checkpoint" in build

    def test_harness_audit_excludes_readonly_from_fix_rate(self, audit):
        # Step 4 filters to build-checkpoint rows before the drop-candidate
        # fix-rate computation, and reports finding-rate for read-only rows.
        assert 'select((.source // "build-checkpoint") == "build-checkpoint")' in audit
        assert "finding-rate" in audit or "finding_rate" in audit
