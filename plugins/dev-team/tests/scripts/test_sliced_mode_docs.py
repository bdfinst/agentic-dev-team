"""Content guards for the sliced-mode documentation wiring.

These assert that SKILL.md and sliced-mode.md document the sliced-review
behavior the deterministic scripts implement — the prose is the orchestrator's
contract, so it is verified the same way the repo verifies other skill prose.
Grows as later slices author their sliced-mode.md sections.
"""

from __future__ import annotations

from pathlib import Path

_SKILL_DIR = (
    Path(__file__).resolve().parents[2] / "skills" / "code-review"
)
_SKILL_MD = (_SKILL_DIR / "SKILL.md").read_text()
_SLICED_MD = (_SKILL_DIR / "sliced-mode.md").read_text()
_OUTPUT_FMT = (_SKILL_DIR / "output-format.md").read_text()


# --- SKILL.md: flags + activation routing (Slice 1) ---------------------------


def test_skill_documents_slice_flags():
    for flag in ("--slice", "--resume", "--no-slice"):
        assert flag in _SKILL_MD, flag


def test_skill_routes_large_full_repo_to_sliced_mode():
    assert "Auto-engage sliced mode" in _SKILL_MD
    assert "sliced-mode.md" in _SKILL_MD


def test_skill_states_no_slice_escape_hatch_and_exclusions():
    assert "--no-slice" in _SKILL_MD
    # Anchored: the non-full-repo-scope statement must actually pair the scope
    # with "never" auto-engage (not just contain the words somewhere).
    assert "Non-full-repo scope" in _SKILL_MD
    non_full = _SKILL_MD.split("Non-full-repo scope", 1)[1][:400]
    assert "never" in non_full.lower()
    # --no-slice must be described as forcing the legacy single-pass review.
    assert "legacy single-pass" in _SKILL_MD


def test_skill_states_exact_threshold_does_not_engage():
    assert "Exactly at 500 files does not auto-engage" in _SKILL_MD


# --- sliced-mode.md: overview + terminology + activation (Slice 1) ------------


def test_sliced_mode_has_terminology_note():
    assert "## Terminology" in _SLICED_MD
    # slice == section mapping is explicit.
    assert "section-<id>.json" in _SLICED_MD
    assert "same unit" in _SLICED_MD


def test_sliced_mode_documents_activation_precedence():
    for token in ("--no-slice", "--slice", "auto-engage", "should_slice"):
        assert token in _SLICED_MD, token


def test_sliced_mode_documents_partitioning_and_ceiling():
    assert "partition_files" in _SLICED_MD
    assert "check_slice_ceiling" in _SLICED_MD


def test_sliced_mode_states_context_stays_flat():
    assert "flat regardless of repo size" in _SLICED_MD


# --- sliced-mode.md: reduced panel + disclosure (Slice 2) ---------------------


def test_sliced_mode_reduced_panel_names_two_agents():
    panel = _SLICED_MD.split("## Per-slice review panel", 1)[1]
    assert "correctness-review" in panel
    assert "structure-review" in panel
    assert "reduced panel" in panel


def test_sliced_mode_declarative_uses_is_declarative_flag():
    panel = _SLICED_MD.split("## Per-slice review panel", 1)[1].split("##", 1)[0]
    assert "is_declarative" in panel
    assert "full panel" in panel


def test_sliced_mode_requires_reduced_panel_disclosure():
    panel = _SLICED_MD.split("## Per-slice review panel", 1)[1].split("##", 1)[0]
    assert "Disclose the panel" in panel or "discloses" in panel.lower()
    assert "reduced panel" in panel


# --- output-format.md: section + ledger schemas (Slice 3) ---------------------


def test_output_format_documents_section_artifact_schema():
    assert "code-review-section/v1" in _OUTPUT_FMT
    section = _OUTPUT_FMT.split("Per-slice section artifact", 1)[1].split("## ", 1)[0]
    for key in ("id", "files", "is_declarative", "panel", "findings"):
        assert key in section, key


def test_output_format_documents_ledger_schema():
    assert "code-review-ledger/v1" in _OUTPUT_FMT
    led = _OUTPUT_FMT.split("Progress ledger", 1)[1].split("## ", 1)[0]
    for key in ("cap", "slices", "status", "pending", "done"):
        assert key in led, key


# --- sliced-mode.md: persist-and-drop + progress (Slice 3) --------------------


def test_sliced_mode_documents_persist_and_drop():
    sec = _SLICED_MD.split("## Persist-and-drop", 1)[1].split("\n## ", 1)[0]
    assert "init_ledger" in sec
    assert "write_section" in sec
    assert "one-line tally" in sec
    # Bounded 2-3 slice parallelism stated.
    assert "2–3" in sec or "2-3" in sec


def test_sliced_mode_documents_progress_and_resume_guidance():
    sec = _SLICED_MD.split("## Persist-and-drop", 1)[1].split("\n## ", 1)[0]
    assert "slice k of N" in sec or "k of N" in sec
    # Interrupted-run guidance points at --resume.
    assert "--resume" in sec
    assert "incomplete" in sec.lower()


# --- sliced-mode.md: resume (Slice 4) -----------------------------------------


def test_sliced_mode_documents_resume_skip_and_cap_guard():
    sec = _SLICED_MD.split("## Resuming an interrupted run", 1)[1].split("\n## ", 1)[0]
    assert "pending_slices" in sec
    assert "check_resume_cap" in sec
    # Skips slices whose artifact already exists; disk is the source of truth.
    assert "already exists" in sec
    assert "source of truth" in sec.lower()
    # Refuses a changed cap rather than repartitioning.
    assert "cap" in sec and ("differs" in sec or "desync" in sec)
    # --resume must not re-initialize the ledger (else prior progress is lost).
    assert "not" in sec and "re-initialize" in sec


# --- output-format.md: consolidated theme-rollup schema (Slice 5) -------------


def test_output_format_documents_recurring_themes_schema():
    assert "Consolidated aggregate" in _OUTPUT_FMT
    sec = _OUTPUT_FMT.split("Consolidated aggregate", 1)[1].split("\n## ", 1)[0]
    assert "recurringThemes" in sec
    for key in ("agent", "slices", "occurrences"):
        assert key in sec, key
    assert "reducedPanelSlices" in sec
    # Reuses the topFindings dedup contract.
    assert "topFindings" in sec


# --- sliced-mode.md: consolidation + report-only + --json (Slice 5) -----------


def test_sliced_mode_documents_consolidation():
    sec = _SLICED_MD.split("## Consolidation", 1)[1]
    assert "consolidate.py" in sec
    assert "file:line" in sec or "file`:`line" in sec.replace("`", "")
    assert "recurring-theme" in sec.lower() or "recurringThemes" in sec
    assert "ACCEPTED-RISKS" in sec


def test_sliced_mode_states_report_only_and_json():
    sec = _SLICED_MD.split("## Consolidation", 1)[1]
    assert "report-only" in sec.lower()
    # Report + corrections destinations.
    assert "DEV_TEAM_REPORTS/code-review.md" in sec
    assert "./corrections/" in sec
    # --json emits the consolidated object to stdout and writes no file.
    assert "--json" in sec and "stdout" in sec
    assert "no" in sec.lower() and "file" in sec.lower()
