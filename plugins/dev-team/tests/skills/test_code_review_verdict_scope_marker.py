"""Content-guard test for code-review/SKILL.md step 4's ledger-scoped
dispatch wiring (#2167).

Prose-presence checks only -- the actual skip/fail-closed/most-recent-wins
behavior this prose describes is proven separately, by
`tests/scripts/test_verdict_scope.py`'s unit and CLI-round-trip tests
against the real ledger-reading functions this prose names. Mirrors the
established content-guard style in `test_build_checkpoint_abort_marker.py`
and `test_code_review_dispatch_marker.py`.
"""

from __future__ import annotations

from _repo_root import REPO_ROOT

SKILL = REPO_ROOT / "plugins" / "dev-team" / "skills" / "code-review" / "SKILL.md"
OUTPUT_FORMAT = REPO_ROOT / "plugins" / "dev-team" / "skills" / "code-review" / "output-format.md"

_STEP4_START = "### 4. Run each enabled agent"
_STEP4_END = "\n### 5. Aggregate results"
_STEP5_START = "### 5. Aggregate results"
_STEP5_END = "#### 5a. Apply ACCEPTED-RISKS.md"


def _skill_text() -> str:
    return SKILL.read_text(encoding="utf-8")


def _section(text: str, start: str, end: str) -> str:
    assert start in text, f"marker not found: {start!r}"
    after_start = text.split(start, 1)[1]
    assert end in after_start, f"marker not found: {end!r}"
    return after_start.split(end, 1)[0]


def _step4_section() -> str:
    return _section(_skill_text(), _STEP4_START, _STEP4_END)


def _step5_section() -> str:
    return _section(_skill_text(), _STEP5_START, _STEP5_END)


def test_step4_invokes_verdict_scope_script() -> None:
    section = _step4_section()
    assert "verdict_scope.py" in section, (
        "step 4 must consult scripts/verdict_scope.py before building any "
        "dispatch prompt (#2167)"
    )
    assert "--lens-files" in section


def test_step4_names_fully_skipped_lenses_handling() -> None:
    section = _step4_section()
    assert "fullySkippedLenses" in section


def test_step4_states_fail_closed_rule() -> None:
    section = _step4_section()
    assert "Fail closed" in section
    assert "outcome: \"pass\"" in section


def test_step4_states_report_loudly_rule() -> None:
    section = _step4_section()
    assert "Report loudly" in section or "report loudly" in section.lower()
    assert "dispatched this run" in section


def test_step4_documents_pr_gate_needs_no_change() -> None:
    section = _step4_section()
    assert "subject_hash" in section
    assert "pre_pr_review.py" in section


def test_step5_folds_in_ledger_skips() -> None:
    section = _step5_section()
    assert "ledgerSkipped" in section
    assert "does **not** force `overall`" in section or "does not force `overall`" in section


def test_output_format_documents_ledger_skipped_field() -> None:
    text = OUTPUT_FORMAT.read_text(encoding="utf-8")
    assert '"ledgerSkipped"' in text
    assert "fullySkippedLenses" in text
