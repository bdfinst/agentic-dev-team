"""Issue #1752 — /code-review must bound how many `Agent` calls it spawns in
one message, and must never let a dispatch failure silently drop a lens.

A real run that dispatched all 16 eligible agents in one message lost its
last 6 to `[Tool result missing due to internal error]` with no detection —
the report simply had six fewer lenses' worth of findings, with nothing to
say so. This checks that SKILL.md's Step 4 now routes wave sizing through
the deterministic `dispatch_waves.py` script (default 10, env-overridable),
retries a failed dispatch exactly once, and — should the retry also fail —
carries it forward as a `dispatchFailures` entry that both blocks the
`.review-passed` gate (Step 9) and is documented as always-present-as-a-key
in output-format.md and knowledge/review-template.md.

Assertions below anchor to the specific sentence each rule lives in, not a
bare word/digit, so a rewrite that drops the actual guarantee fails the test
even if an unrelated occurrence of the same substring survives elsewhere in
the section (code-review round 1 finding: bare `"10"`/`"never"` checks pass
for reasons unrelated to what they claim to verify).
"""

from __future__ import annotations

import sys

from skill_doc_helpers import PLUGIN_ROOT, collapsed, section

CODE_REVIEW = (PLUGIN_ROOT / "skills" / "code-review" / "SKILL.md").read_text(
    encoding="utf-8"
)
OUTPUT_FORMAT = (PLUGIN_ROOT / "skills" / "code-review" / "output-format.md").read_text(
    encoding="utf-8"
)
REVIEW_TEMPLATE = (PLUGIN_ROOT / "knowledge" / "review-template.md").read_text(
    encoding="utf-8"
)

_STEP4 = section(CODE_REVIEW, r"^### 4\. Run each enabled agent", boundary_pattern=r"^### 5\. ")
_STEP5 = section(CODE_REVIEW, r"^### 5\. Aggregate results", boundary_pattern=r"^#### 5a\. ")
_STEP9 = section(CODE_REVIEW, r"^### 9\. Write pre-commit gate file", boundary_pattern=r"^### \d")

_SCRIPTS_DIR = PLUGIN_ROOT / "skills" / "code-review" / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))
import dispatch_waves


def test_step4_computes_wave_split_via_dispatch_waves_script():
    assert "skills/code-review/scripts/dispatch_waves.py" in _STEP4
    assert "--agents" in _STEP4


def test_step4_default_max_parallel_is_ten_and_env_overridable():
    assert "DEV_TEAM_MAX_PARALLEL_REVIEW_AGENTS" in _STEP4
    assert "defaults to **10**" in _STEP4


def test_step4_default_matches_the_scripts_actual_constant():
    # Drift guard: the prose default and the script's DEFAULT_MAX_PARALLEL
    # must agree, checked against the live value rather than assumed.
    assert f"defaults to **{dispatch_waves.DEFAULT_MAX_PARALLEL}**" in _STEP4


def test_step4_waits_per_wave_not_only_at_the_end():
    assert "waiting for each wave to fully return before dispatching the next" in collapsed(
        _STEP4
    ).lower()


def test_step4_retries_a_failed_dispatch_exactly_once():
    lowered = collapsed(_STEP4).lower()
    assert "retry each failed agent" in lowered
    assert "exactly once" in lowered


def test_step4_never_drops_a_double_failure_silently():
    assert "dispatchFailures" in _STEP4
    assert "never inferred from a shorter-than-expected agent table" in collapsed(_STEP4)


def test_step5_dispatch_failures_never_enter_scoring_or_suppression():
    lowered = collapsed(_STEP5).lower()
    assert "never enter accepted-risks suppression or health scoring" in lowered


def test_step5_forces_overall_fail_when_dispatch_failures_present():
    # This is the fix for the --json blind spot: step 9's gate never runs
    # under --json, so /pr (which reads only overall/status) needs the
    # aggregate itself to refuse a "pass" while a lens never ran.
    assert 'forces `overall: "fail"`' in _STEP5
    assert "skipped entirely under `--json`" in _STEP5


def test_step9_treats_dispatch_failures_as_gate_blocking():
    assert "dispatchFailures" in _STEP9
    lowered = collapsed(_STEP9).lower()
    assert "do not write `.review-passed`" in lowered or "must not be written" in lowered


def test_output_format_documents_dispatch_failures_field():
    assert '"dispatchFailures"' in OUTPUT_FORMAT
    assert "attempts" in OUTPUT_FORMAT
    assert "always present" in OUTPUT_FORMAT.lower()


def test_output_format_documents_no_status_field_on_dispatch_failures():
    assert "carry no `status` at all" in OUTPUT_FORMAT


def test_output_format_forces_overall_fail_on_dispatch_failures():
    assert 'forces `overall: "fail"`' in OUTPUT_FORMAT


def test_aggregated_sample_carries_dispatch_failures_key():
    # The worked example is what an emitter mimics — an "always present" key
    # missing from it is exactly the drift the field's own paragraph warns
    # against.
    import json

    sample = json.loads(
        (PLUGIN_ROOT / "skills" / "code-review" / "examples" / "aggregated-sample.json").read_text(
            encoding="utf-8"
        )
    )
    assert "dispatchFailures" in sample
    assert sample["dispatchFailures"] == []


def test_skip_status_has_one_canonical_definition():
    # review-agent-output-contract.md is the single source of truth; the two
    # other sites cite it rather than restate a divergent definition.
    contract = (PLUGIN_ROOT / "knowledge" / "review-agent-output-contract.md").read_text(
        encoding="utf-8"
    )
    assert "Canonical definition" in contract
    assert "review-agent-output-contract.md#status-values" in OUTPUT_FORMAT
    assert "review-agent-output-contract.md#status-values" in CODE_REVIEW


def test_output_format_summary_template_includes_dispatch_failures_section():
    assert "## Dispatch Failures" in OUTPUT_FORMAT


def test_review_template_includes_dispatch_failures_section():
    assert "## Dispatch Failures" in REVIEW_TEMPLATE
    assert "issue #1752" in REVIEW_TEMPLATE


def test_review_template_states_gate_not_written_when_failures_present():
    assert "Gate NOT written" in REVIEW_TEMPLATE
