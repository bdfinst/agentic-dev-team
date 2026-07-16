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
