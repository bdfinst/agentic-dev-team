"""Pytest tests for mutation_kill_loop.py's ``run_for_file`` orchestration —
insertion outcome -> build/test verification -> commit or revert (#1564 split
of ``test_mutation_kill_loop.py``).

Every dotnet / git / Stryker subprocess is mocked via the shared
``_loop_fixture`` helper (``_mutation_kill_loop_test_helpers.py``) — no real
.NET tooling runs — except the one test that exercises ``git_reset_and_revert``
against a real, hermetic git repo (the exact index/worktree state #1598 fixed).
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import mutation_kill_insert
import mutation_kill_loop as loop
import pytest
from _mutation_kill_loop_test_helpers import _loop_fixture, _mutant, _write_report
from _mutation_test_helpers import git_hermetic, hermetic_git_env


# =============================================================================
# Scenario: A build failure after insertion is reverted
# =============================================================================
def test_build_failure_after_insertion_is_reverted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source_file, ctx, kwargs, events = _loop_fixture(tmp_path, monkeypatch, [_mutant("Survived")])
    monkeypatch.setattr(loop, "dotnet_build", lambda targets, **k: False)
    monkeypatch.setattr(
        loop, "dotnet_test", lambda *a, **k: pytest.fail("test must not run after build fail")
    )

    loop.run_for_file(source_file, ctx, **kwargs)

    kinds = [e[0] for e in events]
    assert "revert" in kinds
    assert "commit" not in kinds


# =============================================================================
# Scenario: A test failure after insertion is reverted
# =============================================================================
def test_test_failure_after_insertion_is_reverted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source_file, ctx, kwargs, events = _loop_fixture(tmp_path, monkeypatch, [_mutant("Survived")])
    monkeypatch.setattr(loop, "dotnet_build", lambda targets, **k: True)
    monkeypatch.setattr(loop, "dotnet_test", lambda targets, flt, **k: False)

    loop.run_for_file(source_file, ctx, **kwargs)

    kinds = [e[0] for e in events]
    assert "revert" in kinds
    assert "commit" not in kinds


# =============================================================================
# Green round commits (baseline for the revert scenarios above)
# =============================================================================
def test_green_round_commits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    source_file, ctx, kwargs, events = _loop_fixture(tmp_path, monkeypatch, [_mutant("Survived")])
    monkeypatch.setattr(loop, "dotnet_build", lambda targets, **k: True)
    monkeypatch.setattr(loop, "dotnet_test", lambda targets, flt, **k: True)
    # Second round: scoped run returns a clean report so the loop stops "done".
    # A real converged report still lists its mutants (now Killed) — an empty
    # mutants list is indistinguishable from a crashed/mismatched run and
    # would (correctly) trip the #1606 zero-mutants guard instead of "no
    # survivors — done".
    clean = _write_report(
        tmp_path / "clean", "src/Widget.WebApi/PaymentService.cs", [_mutant("Killed")]
    )
    (tmp_path / "clean").mkdir(exist_ok=True)
    monkeypatch.setattr(loop, "run_scoped_stryker", lambda *a, **k: clean)

    loop.run_for_file(source_file, ctx, **kwargs)

    kinds = [e[0] for e in events]
    assert "commit" in kinds
    assert "revert" not in kinds


# =============================================================================
# Scenario: A headless (unattended, zero-human-review) commit carries an
# audit trail distinguishing it from an agent-driven one (#1560)
# =============================================================================
def test_commit_message_omits_generator_trailer_by_default():
    message = loop._commit_message(1, "Foo.cs", 2, "public async Task X() {}\n")
    assert "Generator:" not in message


def test_commit_message_includes_generator_trailer_when_labeled():
    message = loop._commit_message(
        1, "Foo.cs", 2, "public async Task X() {}\n", generator_label="headless (some-model)"
    )
    assert "Generator: headless (some-model)" in message


def test_commit_message_generator_label_newlines_cannot_forge_extra_lines():
    # A pipeline-supplied model string containing newlines must not be able
    # to inject a second, forged "Generator:" trailer *line* into the
    # commit — the injected text is neutralized onto the same line instead.
    message = loop._commit_message(
        1,
        "Foo.cs",
        2,
        "public async Task X() {}\n",
        generator_label="some-model\n\nGenerator: agent-driven (reviewed)",
    )
    lines_starting_with_generator = [
        line for line in message.splitlines() if line.startswith("Generator:")
    ]
    assert len(lines_starting_with_generator) == 1


def test_commit_message_source_file_newlines_cannot_forge_extra_lines():
    # source_file is whitespace-collapsed the same way append_generator_trailer
    # sanitizes generator_label (#1607) — a filename containing a newline
    # (legal on POSIX) must not be able to forge an extra "Generator:" line.
    message = loop._commit_message(
        1,
        "Foo.cs\n\nGenerator: agent-driven (reviewed)",
        2,
        "public async Task X() {}\n",
    )
    lines_starting_with_generator = [
        line for line in message.splitlines() if line.startswith("Generator:")
    ]
    assert len(lines_starting_with_generator) == 0


def test_commit_message_counts_new_methods_via_count_methods():
    """_commit_message's method count is _METHOD_RE-derived (count_methods),
    not the raw number of survivors — direct assertion on the rendered count,
    not just the generator trailer (#1563 gap 3)."""
    message = loop._commit_message(
        1,
        "Foo.cs",
        5,
        "public async Task A() {}\n\npublic async Task B() {}\n",
    )
    assert "2 new test method(s)" in message
    assert "targeting 5 surviving mutant(s)" in message


# =============================================================================
# Scenario: label_override — #1908 Step 3.2b. A model-downgrade event's
# per-round dynamic content can't live in the frozen generator_label, so
# _commit_message accepts an optional per-call override instead.
# =============================================================================
def test_commit_message_no_override_keeps_the_frozen_label_unchanged():
    message = loop._commit_message(
        1, "Foo.cs", 2, "public async Task X() {}\n", generator_label="headless (opus)"
    )
    assert "Generator: headless (opus)" in message


def test_commit_message_override_replaces_the_frozen_label():
    message = loop._commit_message(
        1,
        "Foo.cs",
        2,
        "public async Task X() {}\n",
        generator_label="headless (opus)",
        label_override="headless (downgraded 'opus' -> 'sonnet' at round 1, gateway-class)",
    )
    assert "Generator: headless (downgraded 'opus' -> 'sonnet' at round 1, gateway-class)" in message
    assert "headless (opus)" not in message


def test_headless_commit_records_generator_label_via_run_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source_file, ctx, kwargs, events = _loop_fixture(tmp_path, monkeypatch, [_mutant("Survived")])
    ctx = dataclasses.replace(ctx, generator_label="headless (some-model)")
    monkeypatch.setattr(loop, "dotnet_build", lambda targets, **k: True)
    monkeypatch.setattr(loop, "dotnet_test", lambda targets, flt, **k: True)
    # A real converged report still lists its mutants (now Killed) — an empty
    # mutants list is indistinguishable from a crashed/mismatched run and
    # would (correctly) trip the #1606 zero-mutants guard instead of "no
    # survivors — done".
    clean = _write_report(
        tmp_path / "clean", "src/Widget.WebApi/PaymentService.cs", [_mutant("Killed")]
    )
    (tmp_path / "clean").mkdir(exist_ok=True)
    monkeypatch.setattr(loop, "run_scoped_stryker", lambda *a, **k: clean)

    loop.run_for_file(source_file, ctx, **kwargs)

    commit_msg = next(e[1] for e in events if e[0] == "commit")
    assert "Generator: headless (some-model)" in commit_msg


def test_headless_commit_uses_label_override_provider_over_the_frozen_label(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A model-downgrade event's per-round dynamic content, surfaced through
    RunContext.label_override_provider, replaces the frozen generator_label
    in that round's commit trailer (#1908 Step 3.2b)."""
    source_file, ctx, kwargs, events = _loop_fixture(tmp_path, monkeypatch, [_mutant("Survived")])
    override_label = "headless (downgraded 'opus' -> 'sonnet' at round 1, gateway-class)"
    ctx = dataclasses.replace(
        ctx,
        generator_label="headless (opus)",
        label_override_provider=lambda: override_label,
    )
    monkeypatch.setattr(loop, "dotnet_build", lambda targets, **k: True)
    monkeypatch.setattr(loop, "dotnet_test", lambda targets, flt, **k: True)
    clean = _write_report(
        tmp_path / "clean", "src/Widget.WebApi/PaymentService.cs", [_mutant("Killed")]
    )
    (tmp_path / "clean").mkdir(exist_ok=True)
    monkeypatch.setattr(loop, "run_scoped_stryker", lambda *a, **k: clean)

    loop.run_for_file(source_file, ctx, **kwargs)

    commit_msg = next(e[1] for e in events if e[0] == "commit")
    assert f"Generator: {override_label}" in commit_msg
    assert "headless (opus)" not in commit_msg


# =============================================================================
# Scenario: A non-improving round ends the file
# =============================================================================
def test_non_improving_round_ends_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # Round 1 (initial report) has 2 survivors; the scoped run for round 2
    # returns a report that still has 2 survivors — no improvement.
    source_file, ctx, kwargs, events = _loop_fixture(
        tmp_path, monkeypatch, [_mutant("Survived", line=1), _mutant("Survived", line=2)]
    )
    monkeypatch.setattr(loop, "dotnet_build", lambda targets, **k: True)
    monkeypatch.setattr(loop, "dotnet_test", lambda targets, flt, **k: True)

    stalled = _write_report(
        tmp_path / "r2",
        "src/Widget.WebApi/PaymentService.cs",
        [_mutant("Survived", line=1), _mutant("Survived", line=2)],
    )
    monkeypatch.setattr(loop, "run_scoped_stryker", lambda *a, **k: stalled)

    loop.run_for_file(source_file, ctx, **kwargs)

    # Exactly one commit (round 1); round 2 detected no improvement and stopped.
    commits = [e for e in events if e[0] == "commit"]
    assert len(commits) == 1


# =============================================================================
# Scenario: The round's log line uses the file-scoped score (Step 3.1, #1545)
# =============================================================================
def test_round_log_line_uses_file_scoped_score_for_single_file_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A single-file scoped report — round log score must match that file's
    own counts (existing behavior, must stay equivalent)."""
    logs: list[str] = []
    source_file, ctx, kwargs, _events = _loop_fixture(
        tmp_path,
        monkeypatch,
        [_mutant("Survived", line=1), _mutant("Killed", line=2)],
        log=logs.append,
    )
    monkeypatch.setattr(loop, "dotnet_build", lambda targets, **k: True)
    monkeypatch.setattr(loop, "dotnet_test", lambda targets, flt, **k: True)
    # A real converged report still lists its mutants (now Killed) — an empty
    # mutants list is indistinguishable from a crashed/mismatched run and
    # would (correctly) trip the #1606 zero-mutants guard instead of "no
    # survivors — done".
    clean = _write_report(
        tmp_path / "clean", "src/Widget.WebApi/PaymentService.cs", [_mutant("Killed")]
    )
    (tmp_path / "clean").mkdir(exist_ok=True)
    monkeypatch.setattr(loop, "run_scoped_stryker", lambda *a, **k: clean)

    loop.run_for_file(source_file, ctx, **kwargs)

    round_1_log = next(m for m in logs if m.startswith("  round 1:"))
    # 1 killed, 1 survived => honest = 1/2 * 100 = 50.0%
    assert "honest=50.0%" in round_1_log
    assert "survivors=1" in round_1_log


def test_round_log_line_scopes_to_target_file_in_multi_file_baseline_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A multi-file report seeded via ``initial_report_path`` — the printed
    score must reflect only the target file's own counts, never the whole
    report's, across multiple rounds."""
    # Multi-file baseline report: the target file scores 50% (1 killed, 1
    # survived); another file in the same report scores far worse (0%). A
    # whole-report score would leak that worse number into the target's line.
    report_override = {
        "files": {
            "src/Widget.WebApi/PaymentService.cs": {
                "mutants": [_mutant("Killed", line=1), _mutant("Survived", line=2)]
            },
            "src/Widget.WebApi/OtherService.cs": {
                "mutants": [
                    _mutant("Survived", line=1),
                    _mutant("Survived", line=2),
                    _mutant("Survived", line=3),
                ]
            },
        }
    }
    logs: list[str] = []
    source_file, ctx, kwargs, _events = _loop_fixture(
        tmp_path, monkeypatch, report_override=report_override, log=logs.append
    )
    kwargs["max_rounds"] = 2
    monkeypatch.setattr(loop, "dotnet_build", lambda targets, **k: True)
    monkeypatch.setattr(loop, "dotnet_test", lambda targets, flt, **k: True)

    # Round 2's scoped run reports only the target file, at the same score —
    # exercising round 2+'s equivalence claim alongside round 1's baseline seed.
    round2_report = _write_report(
        tmp_path / "r2",
        "src/Widget.WebApi/PaymentService.cs",
        [_mutant("Killed", line=1), _mutant("Survived", line=2)],
    )
    monkeypatch.setattr(loop, "run_scoped_stryker", lambda *a, **k: round2_report)

    loop.run_for_file(source_file, ctx, **kwargs)

    round_logs = [m for m in logs if m.startswith("  round")]
    assert len(round_logs) == 2, "expected both round 1 (baseline) and round 2 (scoped) to log"
    for msg in round_logs:
        assert "honest=50.0%" in msg
        assert "survivors=1" in msg


# =============================================================================
# Scenario: max_rounds is exhausted while survivors are still strictly
# improving each round (never reaching 0, and never repeating the previous
# round's count) — the loop must stop because the round budget ran out, not
# because of either the "no survivors" or "no improvement" stop_reason paths
# (#1563 gap 6).
# =============================================================================
def test_max_rounds_exhausted_while_survivors_keep_improving(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    logs: list[str] = []
    source_file, ctx, kwargs, events = _loop_fixture(
        tmp_path,
        monkeypatch,
        [_mutant("Survived", line=1), _mutant("Survived", line=2)],
        log=logs.append,
    )
    kwargs["max_rounds"] = 2
    monkeypatch.setattr(loop, "dotnet_build", lambda targets, **k: True)
    monkeypatch.setattr(loop, "dotnet_test", lambda targets, flt, **k: True)

    # Round 2's scoped run reports FEWER survivors than round 1 (2 -> 1) —
    # real improvement, so stop_reason returns None and a round 3 would run
    # if max_rounds allowed it.
    round2_report = _write_report(
        tmp_path / "r2", "src/Widget.WebApi/PaymentService.cs", [_mutant("Survived", line=1)]
    )
    monkeypatch.setattr(loop, "run_scoped_stryker", lambda *a, **k: round2_report)

    # A uniquely-named method per round — the fixture's default generator
    # returns the same method name every round, which round 2 would refuse
    # to insert as a duplicate (a different code path than the one this test
    # targets). A unique name per call keeps both rounds' inserts genuine.
    calls = {"n": 0}

    def unique_generator(src, survivors, src_text, test_text):
        calls["n"] += 1
        return (
            "        [Test]\n"
            f"        public async Task New_Case_{calls['n']}()\n"
            "        {\n"
            "        }\n"
        )

    kwargs["generate"] = unique_generator

    loop.run_for_file(source_file, ctx, **kwargs)

    round_logs = [m for m in logs if m.startswith("  round")]
    assert len(round_logs) == 2, "max_rounds=2 must cap the loop at exactly 2 rounds"
    assert "survivors=2" in round_logs[0]
    assert "survivors=1" in round_logs[1]
    # Neither stop_reason fired — the loop ended solely because the round
    # budget (max_rounds) was exhausted.
    assert not any("no survivors" in m or "no improvement" in m for m in logs)
    assert [e[0] for e in events].count("commit") == 2
    assert "revert" not in [e[0] for e in events]


# =============================================================================
# Scenario: A baseline-seeded round 1 with 0 survivors skips the scoped run
# entirely (#1545 core value scenario)
# =============================================================================
def test_baseline_seeded_zero_survivors_never_calls_scoped_stryker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """When the baseline report seeded via ``initial_report_path`` already
    shows 0 survivors for the target file, round 1 must converge immediately
    on that baseline data — ``run_scoped_stryker`` must never be invoked. This
    is the redundant-run this whole issue exists to avoid."""
    report_override = {
        "files": {
            "src/Widget.WebApi/PaymentService.cs": {
                "mutants": [_mutant("Killed", line=1), _mutant("Killed", line=2)]
            },
        }
    }
    logs: list[str] = []
    source_file, ctx, kwargs, events = _loop_fixture(
        tmp_path, monkeypatch, report_override=report_override, log=logs.append
    )
    monkeypatch.setattr(
        loop,
        "run_scoped_stryker",
        lambda *a, **k: pytest.fail(
            "run_scoped_stryker must not be called when the baseline already "
            "shows 0 survivors"
        ),
    )

    loop.run_for_file(source_file, ctx, **kwargs)

    assert any("no survivors" in msg for msg in logs)
    assert not any(e[0] in ("generate", "commit", "revert") for e in events)


# =============================================================================
# Scenario: A baseline report with zero mutants at all (a crashed Stryker
# run, or a scoped-config file-key mismatch) must NOT be treated as
# convergence — mirrors the Python loop's #1359 guard, added to the C# loop
# in #1606 after verifying mutation_report's documented contract
# (score_report_for_file/survivors_by_mutator never raise, and
# run_scoped_stryker runs with check=False) makes this reachable, not just
# theoretical.
# =============================================================================
def test_baseline_zero_total_mutants_is_not_treated_as_convergence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    report_override = {"files": {"src/Widget.WebApi/PaymentService.cs": {"mutants": []}}}
    logs: list[str] = []
    source_file, ctx, kwargs, events = _loop_fixture(
        tmp_path, monkeypatch, report_override=report_override, log=logs.append
    )

    loop.run_for_file(source_file, ctx, **kwargs)

    assert not any("no survivors" in msg for msg in logs)
    assert any("zero mutants generated" in msg for msg in logs)
    assert any("NOT convergence" in msg for msg in logs)
    assert not any(e[0] in ("generate", "commit", "revert") for e in events)


def test_scoped_run_zero_total_mutants_is_not_treated_as_convergence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Same guard, but for a round-2+ scoped run (not baseline-seeded) — a
    crashed scoped Stryker invocation returning an empty/mismatched report
    must not be mistaken for "this file has zero survivors"."""
    logs: list[str] = []
    source_file, ctx, kwargs, events = _loop_fixture(
        tmp_path, monkeypatch, [_mutant("Survived")], log=logs.append
    )
    monkeypatch.setattr(loop, "dotnet_build", lambda targets, **k: True)
    monkeypatch.setattr(loop, "dotnet_test", lambda targets, flt, **k: True)

    crashed = _write_report(tmp_path / "crashed", "src/Widget.WebApi/PaymentService.cs", [])
    monkeypatch.setattr(loop, "run_scoped_stryker", lambda *a, **k: crashed)

    loop.run_for_file(source_file, ctx, **kwargs)

    # Round 1 (baseline-seeded) commits normally; round 2's crashed scoped
    # run must stop the file without a second (bogus) "no survivors" commit.
    assert [e[0] for e in events].count("commit") == 1
    assert not any("no survivors" in msg for msg in logs)
    assert any("zero mutants generated" in msg for msg in logs)


# =============================================================================
# Scenario: A failed commit is a round failure, not a silent success (#1598)
# =============================================================================
def test_failed_commit_reverts_and_stops_the_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source_file, ctx, kwargs, events = _loop_fixture(
        tmp_path, monkeypatch, [_mutant("Survived")]
    )
    monkeypatch.setattr(loop, "dotnet_build", lambda targets, **k: True)
    monkeypatch.setattr(loop, "dotnet_test", lambda targets, flt, **k: True)
    monkeypatch.setattr(
        loop, "git_commit", lambda msg, tf, **k: events.append(("commit", msg)) or False
    )

    loop.run_for_file(source_file, ctx, **kwargs)

    kinds = [e[0] for e in events]
    # The commit was attempted, failed, and was NOT mistaken for success:
    # exactly one revert follows it, and the loop stops (a second "generate"
    # would mean it wrongly believed round 1 had landed).
    assert kinds.count("commit") == 1
    assert kinds.count("revert") == 1
    assert kinds.count("generate") == 1


def test_revert_failure_after_failed_commit_is_fatal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source_file, ctx, kwargs, _events = _loop_fixture(
        tmp_path, monkeypatch, [_mutant("Survived")]
    )
    monkeypatch.setattr(loop, "dotnet_build", lambda targets, **k: True)
    monkeypatch.setattr(loop, "dotnet_test", lambda targets, flt, **k: True)
    monkeypatch.setattr(loop, "git_commit", lambda msg, tf, **k: False)
    # The commit-failure revert path calls git_reset_and_revert, not plain
    # git_revert (#1598/#1584 review) — that's the function that must fail
    # here for this scenario.
    monkeypatch.setattr(loop, "git_reset_and_revert", lambda tf, **k: False)

    with pytest.raises(RuntimeError, match="revert failed"):
        loop.run_for_file(source_file, ctx, **kwargs)


def test_revert_failure_after_build_failure_is_fatal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source_file, ctx, kwargs, _events = _loop_fixture(
        tmp_path, monkeypatch, [_mutant("Survived")]
    )
    monkeypatch.setattr(loop, "dotnet_build", lambda targets, **k: False)
    monkeypatch.setattr(loop, "git_revert", lambda tf, **k: False)

    with pytest.raises(RuntimeError, match="revert failed"):
        loop.run_for_file(source_file, ctx, **kwargs)


def test_revert_failure_after_test_failure_is_fatal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source_file, ctx, kwargs, _events = _loop_fixture(
        tmp_path, monkeypatch, [_mutant("Survived")]
    )
    monkeypatch.setattr(loop, "dotnet_build", lambda targets, **k: True)
    monkeypatch.setattr(loop, "dotnet_test", lambda targets, flt, **k: False)
    monkeypatch.setattr(loop, "git_revert", lambda tf, **k: False)

    with pytest.raises(RuntimeError, match="revert failed"):
        loop.run_for_file(source_file, ctx, **kwargs)


# =============================================================================
# Scenario (real git, no mocks): git_reset_and_revert actually leaves both
# the index AND the working tree matching HEAD after a commit-failure-style
# staged mutation — the exact #1598 regression a fully-mocked test (like
# test_failed_commit_reverts_and_stops_the_round above) cannot catch, since
# mocking git_revert/git_commit never exercises real git index state.
# =============================================================================
def test_git_reset_and_revert_restores_index_and_worktree_after_a_staged_mutation(
    tmp_path: Path,
):
    git_hermetic(tmp_path, "init", "-q")
    git_hermetic(tmp_path, "config", "user.email", "test@example.com")
    git_hermetic(tmp_path, "config", "user.name", "Test")
    git_hermetic(tmp_path, "config", "commit.gpgsign", "false")

    test_file = tmp_path / "PaymentServiceTests.cs"
    original = "namespace Widget.Tests\n{\n    // original\n}\n"
    test_file.write_text(original, encoding="utf-8")
    git_hermetic(tmp_path, "add", "-A")
    git_hermetic(tmp_path, "commit", "-q", "-m", "initial")

    # Simulate what git_commit does before a commit attempt fails: the loop
    # mutates the test file, then `git add`s it.
    mutated = original.replace("// original", "// mutated (never actually committed)")
    test_file.write_text(mutated, encoding="utf-8")
    git_hermetic(tmp_path, "add", "--", str(test_file))

    # Sanity: the mutation IS staged before the fix runs — this is what makes
    # a plain `git checkout --` (git_revert alone) insufficient, and what
    # this test would fail to prove without this check.
    staged = git_hermetic(tmp_path, "diff", "--cached", "--name-only")
    assert "PaymentServiceTests.cs" in staged.stdout

    # env= is the point of this test: the SUT's own git subprocess must run
    # hermetically too, not just this test's setup calls above (#1598/#1584
    # review, round 3 — test-smell-review/ai-provenance-review found the
    # round-2 fix scrubbed only the setup calls).
    assert (
        loop.git_reset_and_revert(
            test_file, cwd=tmp_path, env=hermetic_git_env(home=tmp_path)
        )
        is True
    )

    # Working tree matches HEAD (not the staged mutation).
    assert test_file.read_text(encoding="utf-8") == original
    # Index matches HEAD too — nothing left staged.
    status = git_hermetic(tmp_path, "status", "--porcelain")
    assert status.stdout.strip() == ""


# =============================================================================
# Scenario: A refused/duplicate insertion stops the round before build/test/
# commit ever run — orchestration-level coverage (previously only exercised
# via mutation_kill_insert's own functions directly, #1584)
# =============================================================================
def test_refused_insertion_stops_the_round_without_verify_or_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source_file, ctx, kwargs, events = _loop_fixture(
        tmp_path, monkeypatch, [_mutant("Survived")]
    )
    monkeypatch.setattr(
        loop, "dotnet_build", lambda *a, **k: pytest.fail("must not build after a refused insert")
    )
    monkeypatch.setattr(
        loop,
        "apply_generated_methods",
        lambda *a, **k: mutation_kill_insert.InsertOutcome(
            False, "duplicate method names: ['Existing_Case_Works']"
        ),
    )

    loop.run_for_file(source_file, ctx, **kwargs)

    kinds = [e[0] for e in events]
    assert kinds == ["generate"]
