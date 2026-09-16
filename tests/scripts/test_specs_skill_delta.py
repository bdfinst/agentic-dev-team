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
    assert result["delta_lines"] == module.PER_SLICE_LINE_CAP
    assert result["ok"] is True


def test_delta_one_over_the_cap_fails(monkeypatch, tmp_path):
    module = load_module(monkeypatch, tmp_path, skill_lines=205, baseline=164)
    result = module.evaluate()
    assert result["ok"] is False
    assert any("per-slice delta" in f for f in result["failures"])


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
    assert not any("per-slice delta" in f for f in result["failures"])
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
