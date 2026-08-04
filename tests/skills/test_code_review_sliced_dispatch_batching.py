"""Issue #1762 — sliced-mode's per-slice panel dispatch must carry the same
dispatch-batching backstops #1752/#1761/#1763 gave the legacy (non-sliced)
`/code-review` path: a wave-bounded panel dispatch, a scripted
dispatched-vs-returned reconciliation, a retry-once policy, and a persisted
`dispatchFailures` entry that also emits the `dispatch-failure` boundary
event so the mechanical gate veto (#1763) can see it.

Assertions below anchor to the specific sentence each rule lives in, not a
bare word/digit, matching `tests/skills/test_code_review_dispatch_batching.py`'s
own documented convention (anchor to the sentence carrying the guarantee, not
a substring that could pass for unrelated reasons).
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, collapsed, section

SLICED_MODE = (PLUGIN_ROOT / "skills" / "code-review" / "sliced-mode.md").read_text(
    encoding="utf-8"
)

_PANEL = section(
    SLICED_MODE, r"^## Per-slice review panel", boundary_pattern=r"^## "
)
_PERSIST_AND_DROP = section(
    SLICED_MODE,
    r"^## Persist-and-drop and the progress ledger",
    boundary_pattern=r"^## ",
)
_RESUMING = section(
    SLICED_MODE, r"^## Resuming an interrupted run", boundary_pattern=r"^## "
)


def test_panel_dispatch_computes_wave_split_via_dispatch_waves_script():
    assert "skills/code-review/scripts/dispatch_waves.py" in _PANEL
    assert "--agents" in _PANEL


def test_persist_and_drop_uses_dispatch_reconcile_for_coverage_check():
    assert "skills/code-review/scripts/dispatch_reconcile.py" in _PERSIST_AND_DROP
    assert "--dispatched" in _PERSIST_AND_DROP
    assert "--returned" in _PERSIST_AND_DROP


def test_persist_and_drop_cross_references_skill_md_step_4_retry_once_policy():
    # Cross-reference, not restatement — the exact prose Step 2.3 mandates.
    assert (
        "same policy as `SKILL.md` Step 4, see there for rationale"
        in collapsed(_PERSIST_AND_DROP)
    )


def test_persist_and_drop_writes_dispatch_failures_via_write_section_cli():
    assert "dispatchFailures" in _PERSIST_AND_DROP
    assert "--dispatch-failures" in _PERSIST_AND_DROP
    assert "write-section" in _PERSIST_AND_DROP


def test_persist_and_drop_emits_dispatch_failure_boundary_event():
    assert "hooks/lib/boundary_events.py" in _PERSIST_AND_DROP
    assert "--event dispatch-failure" in _PERSIST_AND_DROP


def test_persist_and_drop_recovered_retry_writes_no_failure_and_emits_no_event():
    assert (
        "A recovered dispatch (fails once, retry succeeds) writes an empty "
        "`dispatchFailures` list and emits no boundary event, mirroring the "
        "legacy path's own guarantee."
    ) in collapsed(_PERSIST_AND_DROP)


def test_persist_and_drop_states_slice_concurrency_heuristic_unchanged():
    # The "2-3 slices at a time" heuristic must still be present, unchanged,
    # and explicitly distinguished from the new panel-level wave cap.
    assert "2–3 slices at a time" in _PERSIST_AND_DROP
    assert (
        "This slice-level concurrency heuristic is unchanged by the "
        "panel-level wave cap above"
    ) in collapsed(_PERSIST_AND_DROP)


def test_resuming_re_dispatches_a_slice_carrying_dispatch_failures():
    lowered = collapsed(_RESUMING).lower()
    assert "dispatchfailures" in lowered
    assert (
        "it is **not** treated as done on `--resume`; its panel is "
        "re-dispatched, same as a slice with no artifact at all"
        in collapsed(_RESUMING)
    )


def test_resuming_keeps_the_clean_artifact_reused_as_is_rule_unchanged():
    assert (
        "an artifact exists with an empty `dispatchFailures` list is "
        "skipped and reused as-is" in collapsed(_RESUMING)
    )
