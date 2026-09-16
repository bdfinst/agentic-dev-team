"""Unit tests for scripts/specs_skill_delta.py (epic #2159, slice 1 step 1.3).

The epic caps each slice's `skills/specs/SKILL.md` delta at ~40 lines and
expects the file to stay below its pre-extraction size. Both were author
judgment until this script; CLAUDE.md's "deterministic tools over inference"
rule makes them a script's job.

The two checks are deliberately independent, and these tests pin that: a
slice can breach the per-slice cap while the file is still well under the
ceiling (caught by `per-slice`), and slices can each stay under the cap
while collectively pushing the file back over the ceiling (caught only by
`cumulative`). A single combined check would miss the second case, which is
the whole reason the cumulative guard exists.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

SCRIPT = REPO_ROOT / "scripts" / "specs_skill_delta.py"


def load_module(monkeypatch, tmp_path: Path, skill_lines: int, baseline: int | None):
    """Load the script with its SKILL/BASELINE paths redirected into tmp_path."""
    spec = importlib.util.spec_from_file_location("specs_skill_delta", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    skill = tmp_path / "SKILL.md"
    skill.write_text("\n".join(f"line {i}" for i in range(skill_lines)) + "\n")
    monkeypatch.setattr(module, "SKILL", skill)
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)

    baseline_path = tmp_path / "baseline.json"
    if baseline is not None:
        baseline_path.write_text(json.dumps({"lines": baseline, "file": "SKILL.md"}))
    monkeypatch.setattr(module, "BASELINE", baseline_path)
    return module


def test_under_both_limits_passes(monkeypatch, tmp_path):
    module = load_module(monkeypatch, tmp_path, skill_lines=170, baseline=164)
    result = module.evaluate()
    assert result["ok"] is True
    assert result["failures"] == []
    assert result["delta_lines"] == 6


def test_delta_exactly_at_the_cap_passes(monkeypatch, tmp_path):
    # The epic's wording is "exceeds ~40 lines", so 40 itself is allowed.
    module = load_module(monkeypatch, tmp_path, skill_lines=204, baseline=164)
    result = module.evaluate()
    assert result["delta_lines"] == module.LINE_CAP
    assert result["ok"] is True


def test_delta_one_over_the_cap_fails(monkeypatch, tmp_path):
    module = load_module(monkeypatch, tmp_path, skill_lines=205, baseline=164)
    result = module.evaluate()
    assert result["ok"] is False
    assert any("growth since baseline" in f for f in result["failures"])


def test_cumulative_ceiling_fails_even_when_each_delta_is_small(monkeypatch, tmp_path):
    """The case a per-slice cap alone cannot catch.

    Baseline has crept to 240 across earlier slices; this slice adds only 5
    lines — well under the cap — but pushes the file back to the
    pre-extraction size. Only the cumulative check fires.
    """
    module = load_module(monkeypatch, tmp_path, skill_lines=245, baseline=240)
    result = module.evaluate()
    assert result["ok"] is False
    assert result["delta_lines"] == 5
    assert not any("growth since baseline" in f for f in result["failures"])
    assert any("cumulative size" in f for f in result["failures"])


def test_both_checks_can_fail_together(monkeypatch, tmp_path):
    module = load_module(monkeypatch, tmp_path, skill_lines=249, baseline=164)
    result = module.evaluate()
    assert result["ok"] is False
    assert len(result["failures"]) == 2


def test_missing_baseline_fails_rather_than_silently_passing(monkeypatch, tmp_path):
    """A gate that cannot fail is worse than no gate (CLAUDE.md)."""
    module = load_module(monkeypatch, tmp_path, skill_lines=170, baseline=None)
    result = module.evaluate()
    assert result["ok"] is False
    assert any("no baseline" in f for f in result["failures"])


def test_corrupt_baseline_is_treated_as_missing(monkeypatch, tmp_path):
    module = load_module(monkeypatch, tmp_path, skill_lines=170, baseline=164)
    module.BASELINE.write_text("{not json")
    assert module.read_baseline() is None


@pytest.mark.parametrize("bad", ['{"lines": "abc"}', "{}", "[]"])
def test_unparseable_baseline_shapes_are_treated_as_missing(monkeypatch, tmp_path, bad):
    module = load_module(monkeypatch, tmp_path, skill_lines=170, baseline=164)
    module.BASELINE.write_text(bad)
    assert module.read_baseline() is None


def test_check_exits_nonzero_on_breach(monkeypatch, tmp_path, capsys):
    module = load_module(monkeypatch, tmp_path, skill_lines=249, baseline=164)
    assert module.main(["--check"]) == 1


def test_check_exits_zero_when_clean(monkeypatch, tmp_path):
    module = load_module(monkeypatch, tmp_path, skill_lines=170, baseline=164)
    assert module.main(["--check"]) == 0


def test_baseline_command_records_the_current_size(monkeypatch, tmp_path):
    module = load_module(monkeypatch, tmp_path, skill_lines=177, baseline=None)
    assert module.main(["baseline"]) == 0
    assert module.read_baseline() == 177


# --- cumulative-ceiling boundary, pinned the same way the per-slice cap is ---


def test_cumulative_one_under_the_ceiling_passes(monkeypatch, tmp_path):
    module = load_module(monkeypatch, tmp_path, skill_lines=242, baseline=240)
    result = module.evaluate()
    assert result["current_lines"] == module.PRE_EXTRACTION_LINES - 1
    assert not any("cumulative size" in f for f in result["failures"])


def test_cumulative_exactly_at_the_ceiling_fails(monkeypatch, tmp_path):
    """The check is `>=`: reaching the pre-extraction size is already a breach,
    because at that point the extraction has bought nothing."""
    module = load_module(monkeypatch, tmp_path, skill_lines=243, baseline=240)
    result = module.evaluate()
    assert result["current_lines"] == module.PRE_EXTRACTION_LINES
    assert result["ok"] is False
    assert any("cumulative size" in f for f in result["failures"])


# --- output paths -----------------------------------------------------------


def test_failures_are_printed_to_stderr(monkeypatch, tmp_path, capsys):
    """Exit code alone is not the contract — the operator needs the reason."""
    module = load_module(monkeypatch, tmp_path, skill_lines=249, baseline=164)
    assert module.main(["--check"]) == 1
    captured = capsys.readouterr()
    assert "growth since baseline" in captured.err
    assert "cumulative size" in captured.err
    assert captured.out == ""


def test_success_is_printed_to_stdout(monkeypatch, tmp_path, capsys):
    module = load_module(monkeypatch, tmp_path, skill_lines=170, baseline=164)
    assert module.main(["--check"]) == 0
    captured = capsys.readouterr()
    assert "budget ok" in captured.out
    assert captured.err == ""


def test_json_output_is_machine_readable(monkeypatch, tmp_path, capsys):
    module = load_module(monkeypatch, tmp_path, skill_lines=249, baseline=164)
    assert module.main(["--check", "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["current_lines"] == 249
    assert payload["delta_lines"] == 85
    assert len(payload["failures"]) == 2


def test_no_arguments_is_a_usage_error_not_a_silent_pass(monkeypatch, tmp_path):
    """A gate invoked wrongly must not look like a gate that passed."""
    module = load_module(monkeypatch, tmp_path, skill_lines=170, baseline=164)
    with pytest.raises(SystemExit) as excinfo:
        module.main([])
    assert excinfo.value.code != 0


# --- corrupt baseline composes end-to-end, not just at read_baseline() ------


@pytest.mark.parametrize("bad", ["{not json", '{"lines": "abc"}', "{}", "[]"])
def test_corrupt_baseline_surfaces_the_no_baseline_failure(monkeypatch, tmp_path, bad):
    """Same user-facing outcome as a missing file, not a silent pass."""
    module = load_module(monkeypatch, tmp_path, skill_lines=170, baseline=164)
    module.BASELINE.write_text(bad)
    result = module.evaluate()
    assert result["ok"] is False
    assert any("no baseline" in f for f in result["failures"])
    assert module.main(["--check"]) == 1


# --- guards added after the slice-1 correctness review -----------------------


def test_baseline_and_check_are_mutually_exclusive(monkeypatch, tmp_path):
    """Recording a baseline from a breaching file would launder the breach.

    `baseline --check` used to exit 0 on a file over both caps: argparse
    accepted the pair, and the baseline branch returned before --check was
    ever consulted — so the one invocation a user would reach for to "record
    and verify in one go" silently made the violation the new normal.
    """
    module = load_module(monkeypatch, tmp_path, skill_lines=249, baseline=164)
    with pytest.raises(SystemExit) as excinfo:
        module.main(["baseline", "--check"])
    assert excinfo.value.code != 0


def test_baseline_recorded_against_another_file_is_rejected(monkeypatch, tmp_path):
    """The `file` provenance key is checked, not merely written."""
    module = load_module(monkeypatch, tmp_path, skill_lines=170, baseline=164)
    module.BASELINE.write_text(json.dumps({"lines": 164, "file": "some/other/file.md"}))
    assert module.read_baseline() is None
    result = module.evaluate()
    assert result["ok"] is False
    assert any("different file" in f for f in result["failures"])


def test_baseline_without_a_file_key_is_still_accepted(monkeypatch, tmp_path):
    """Provenance is checked only when present, so an older baseline still reads."""
    module = load_module(monkeypatch, tmp_path, skill_lines=170, baseline=None)
    module.BASELINE.write_text(json.dumps({"lines": 164}))
    assert module.read_baseline() == 164


def test_baseline_is_written_to_a_committable_path():
    """Regression guard for the original bug: the baseline lived under
    `.claude/memory/`, which `.gitignore`'s bare `memory/` pattern matches at
    any depth — so it could never be committed, and the since-baseline check
    was enforceable only on the machine that last recorded it.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("specs_skill_delta_real", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    parts = module.BASELINE.relative_to(REPO_ROOT).parts
    assert "memory" not in parts, (
        f"baseline at {module.BASELINE.relative_to(REPO_ROOT)} sits under a "
        "gitignored 'memory/' directory and could never be committed"
    )
