"""Pytest tests for scripts/run_refactor_experiment.py's prompt builders (#1727).

`--skip-dispatch` (the harness's own "free self-test") does NOT exercise
write_prompt_single/change_write_prompt: run_build/run_change gate the call into
_do_stage behind `if not skip:`, so a syntax error or broken concatenation in a
new arm's prompt branch would pass that self-test undetected (caught in review —
see the harness's ARMS docstring for the arm taxonomy these tests pin). These
tests call the prompt builders directly, no dispatch, no API cost.

The per-class prompt assertions below pin phrasing against the fidelity
requirement in docs/experiments/test-cadence-validation-plan.md: "tests written
and verified-red per unit, not for the whole task at once" — the prompt text IS
the experimental treatment, so these are treatment-fidelity checks, not
incidental string-equality tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import run_refactor_experiment as exp


@pytest.mark.parametrize("arm", list(exp.ARMS))
def test_every_arm_produces_nonempty_build_and_change_prompts(arm):
    build = exp.write_prompt_single(arm, "spec_clear.md")
    change = exp.change_write_prompt(arm, "change1.md")
    assert build and "spec_clear.md" in build
    assert change and "change1.md" in change


def test_batch_red_per_class_single_is_test_first_one_shot_single():
    a = exp.ARMS["batch-red-per-class-single"]
    assert a["ordering"] == "test-first"
    assert a["granularity"] == "one-shot"
    assert a["authorship"] == "single"
    assert a["batch"] == exp.BATCH_PER_CLASS
    # one-shot arms use the separate, revertable refactor dispatch — never inline.
    assert "batch-red-per-class-single" not in exp.INLINE_REFACTOR


def test_no_batch_red_per_class_split_arm():
    # The split test-first path (_do_stage) doesn't consult `batch` at all — see
    # that function's guard. A "-split" counterpart is deliberately out of scope
    # for #1727, not an oversight; this pins the absence as a checked invariant.
    assert "batch-red-per-class-split" not in exp.ARMS


def test_split_test_first_path_rejects_unhonored_batch_value():
    # _do_stage's split test-first branch only implements the whole-task
    # (batch=big) protocol; a per-class batch value must fail loud, not
    # silently mislabel rows with a protocol it never actually ran.
    exp.ARMS["_test_bogus_split_arm"] = {
        "granularity": "one-shot", "authorship": "split",
        "ordering": "test-first", "batch": exp.BATCH_PER_CLASS,
    }
    try:
        import tempfile
        from pathlib import Path

        workdir = Path(tempfile.mkdtemp())
        run_root = Path(tempfile.mkdtemp())
        with pytest.raises(ValueError, match="not honored on the split test-first path"):
            exp._do_stage(workdir, "_test_bogus_split_arm", "spec_clear.md", "model",
                           {}, run_root, "cell", False)
    finally:
        del exp.ARMS["_test_bogus_split_arm"]


def test_every_test_first_one_shot_arm_has_a_registered_batch_builder():
    # `batch is None` is a legitimate default only for continuous arms
    # (tdd-refactor) — a test-first, one-shot arm that omits `batch` would
    # silently fall through to the strict-TDD prompt AND still run the
    # separate one-shot refactor dispatch (double refactoring). Every
    # test-first/one-shot arm must have a batch registered in both tables.
    for arm, a in exp.ARMS.items():
        if a["ordering"] == "test-first" and a["granularity"] == "one-shot":
            assert "batch" in a, f"{arm}: test-first/one-shot arm missing `batch`"
            assert a["batch"] in exp._TEST_FIRST_WRITE_BUILDERS, arm
            assert a["batch"] in exp._TEST_FIRST_CHANGE_BUILDERS, arm


def test_batch_red_per_class_build_prompt_sequences_per_unit():
    prompt = exp.write_prompt_single("batch-red-per-class-single", "spec_clear.md")
    assert "distinct classes/units" in prompt
    assert "Only move to the next unit once the current one is green" in prompt
    assert "Do NOT write tests for more than one unit before implementing any of them" in prompt
    assert "Do NOT refactor yet" in prompt
    # distinct from the whole-task batching protocol it sits beside in ARMS
    assert "in one batch" not in prompt


def test_batch_red_per_class_change_prompt_sequences_per_unit():
    prompt = exp.change_write_prompt("batch-red-per-class-single", "change1.md")
    assert "distinct classes/units the change" in prompt
    assert "Only move to the next unit once the current one is green" in prompt
    assert "Do NOT refactor yet" in prompt


def test_unrecognized_batch_value_raises_instead_of_silently_falling_through():
    """A typo in `batch` must fail loud, not silently run the strict-TDD prompt
    (which would then double up refactoring: inline REFACTOR_RULE *and* the
    separate one-shot dispatch enforce_refactor() issues for one-shot arms)."""
    exp.ARMS["_test_bogus_arm"] = {
        "granularity": "one-shot", "authorship": "single",
        "ordering": "test-first", "batch": "not-a-real-batch-value",
    }
    try:
        with pytest.raises(ValueError, match="unrecognized batch"):
            exp.write_prompt_single("_test_bogus_arm", "spec_clear.md")
        with pytest.raises(ValueError, match="unrecognized batch"):
            exp.change_write_prompt("_test_bogus_arm", "change1.md")
    finally:
        del exp.ARMS["_test_bogus_arm"]


def test_test_first_arm_with_no_batch_key_uses_strict_tdd_prompt():
    # tdd-refactor has ordering=test-first and no `batch` key at all.
    assert "batch" not in exp.ARMS["tdd-refactor"]
    prompt = exp.write_prompt_single("tdd-refactor", "spec_clear.md")
    assert "strict TDD" in prompt
    assert "REFACTOR the production code before the next behavior" in prompt


def test_all_tests_first_and_batch_red_per_class_prompts_are_distinct():
    big = exp.write_prompt_single("all-tests-first-single", "spec_clear.md")
    per_class = exp.write_prompt_single("batch-red-per-class-single", "spec_clear.md")
    assert big != per_class
    assert "in one batch" in big
    assert "in one batch" not in per_class
