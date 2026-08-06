"""Pytest tests for mutation_kill_loop_python.py's ``run_for_file``
orchestration — insertion outcome -> compile/test verification -> commit or
revert, plus the ``_commit_message`` audit-trail helper (#1604 split of
``test_mutation_kill_loop_python.py``, mirroring the C# loop's own #1564
split into ``test_mutation_kill_loop_orchestration.py``).

Every mutmut / git / pytest subprocess is mocked, except the two real-git
(no mocks) regression tests at the bottom — mirrors
``test_mutation_kill_loop_orchestration.py``'s own placement of the
equivalent C# real-git regression test.
"""

from __future__ import annotations

from pathlib import Path

import mutation_kill_loop_python as loop
import pytest
from _mutation_kill_loop_python_test_helpers import _ctx, _junit, _killed, _survived
from _mutation_test_helpers import git_hermetic, hermetic_git_env


# =============================================================================
# Scenario: A headless (unattended, zero-human-review) commit carries an
# audit trail distinguishing it from an agent-driven one (#1560)
# =============================================================================
def test_commit_message_omits_generator_trailer_by_default():
    message = loop._commit_message(1, "calc.py", 2, "def test_new(): pass\n")
    assert "Generator:" not in message


def test_commit_message_includes_generator_trailer_when_labeled():
    message = loop._commit_message(
        1, "calc.py", 2, "def test_new(): pass\n", generator_label="headless (some-model)"
    )
    assert "Generator: headless (some-model)" in message


def test_commit_message_generator_label_newlines_cannot_forge_extra_lines():
    # A pipeline-supplied model string containing newlines must not be able
    # to inject a second, forged "Generator:" trailer *line* into the
    # commit — the injected text is neutralized onto the same line instead.
    message = loop._commit_message(
        1,
        "calc.py",
        2,
        "def test_new(): pass\n",
        generator_label="some-model\n\nGenerator: agent-driven (reviewed)",
    )
    lines_starting_with_generator = [
        line for line in message.splitlines() if line.startswith("Generator:")
    ]
    assert len(lines_starting_with_generator) == 1


def test_commit_message_counts_new_tests_via_count_tests():
    message = loop._commit_message(
        1, "calc.py", 2, "def test_a(): pass\n\ndef test_b(): pass\n"
    )
    assert "2 new test(s)" in message


# =============================================================================
# Scenario: label_override — #1908 Step 3.2b. A model-downgrade event's
# per-round dynamic content can't live in the frozen generator_label, so
# _commit_message accepts an optional per-call override instead.
# =============================================================================
def test_commit_message_no_override_keeps_the_frozen_label_unchanged():
    message = loop._commit_message(
        1, "calc.py", 2, "def test_new(): pass\n", generator_label="headless (opus)"
    )
    assert "Generator: headless (opus)" in message


def test_commit_message_override_replaces_the_frozen_label():
    message = loop._commit_message(
        1,
        "calc.py",
        2,
        "def test_new(): pass\n",
        generator_label="headless (opus)",
        label_override="headless (downgraded 'opus' -> 'sonnet' at round 1, gateway-class)",
    )
    assert "Generator: headless (downgraded 'opus' -> 'sonnet' at round 1, gateway-class)" in message
    assert "headless (opus)" not in message


# =============================================================================
# Scenario: _commit_message's source_file is whitespace-collapsed the same
# way append_generator_trailer already sanitizes generator_label (#1607) — a
# source_file value containing a newline (legal on POSIX) must not be able
# to forge an extra "Generator:" trailer line.
# =============================================================================
def test_commit_message_source_file_newlines_cannot_forge_extra_lines():
    message = loop._commit_message(
        1,
        "calc.py\n\nGenerator: agent-driven (reviewed)",
        2,
        "def test_new(): pass\n",
    )
    lines_starting_with_generator = [
        line for line in message.splitlines() if line.startswith("Generator:")
    ]
    assert len(lines_starting_with_generator) == 0


# =============================================================================
# run_for_file — full loop with every subprocess mocked
# =============================================================================
def test_run_for_file_stops_immediately_on_zero_survivors(tmp_path: Path, monkeypatch):
    calls = {"generate": 0}
    monkeypatch.setattr(loop, "run_scoped_mutmut", lambda *a, **k: _junit(_killed("Mutant #1", "src/a.py", 1)))

    def fake_generate(*_args):
        calls["generate"] += 1
        return "def test_new():\n    assert True\n"

    test_file = tmp_path / "test_a.py"
    test_file.write_text("def test_existing():\n    assert True\n", encoding="utf-8")
    source_file = tmp_path / "a.py"
    source_file.write_text("x = 1\n", encoding="utf-8")

    loop.run_for_file("src/a.py", _ctx(test_file, source_file), generate=fake_generate)

    assert calls["generate"] == 0
    assert "test_new" not in test_file.read_text(encoding="utf-8")


def test_run_for_file_does_not_treat_zero_mutants_as_convergence(
    tmp_path: Path, monkeypatch
):
    """mutmut<3 crashes on Python 3.13+ ('TypeError: cannot pickle
    itertools.count object', #1359) and produces a junitxml report with
    zero testcases at all — indistinguishable from real survivors=0 by
    count alone. run_for_file must not log "no survivors — done" (a false
    convergence claim) for this case, and must never call generate()."""
    empty_junit = (
        '<?xml version="1.0" ?>\n'
        '<testsuites disabled="0" errors="0" failures="0" tests="0" time="0.0">'
        '<testsuite disabled="0" errors="0" failures="0" name="mutmut" '
        'skipped="0" tests="0" time="0"/></testsuites>\n'
    )
    monkeypatch.setattr(loop, "run_scoped_mutmut", lambda *a, **k: empty_junit)

    calls = {"generate": 0}

    def fake_generate(*_args):
        calls["generate"] += 1
        return "def test_new():\n    assert True\n"

    test_file = tmp_path / "test_a.py"
    test_file.write_text("def test_existing():\n    assert True\n", encoding="utf-8")
    source_file = tmp_path / "a.py"
    source_file.write_text("x = 1\n", encoding="utf-8")

    logged = []
    loop.run_for_file(
        "src/a.py",
        _ctx(test_file, source_file, log=logged.append),
        generate=fake_generate,
    )

    assert calls["generate"] == 0
    assert not any("no survivors" in line for line in logged)
    assert any("zero mutants generated" in line for line in logged)
    assert any("NOT convergence" in line for line in logged)


def test_run_for_file_generates_inserts_and_commits_on_green(tmp_path: Path, monkeypatch):
    """One round: survivors found -> generate -> insert -> compile+test pass
    -> commit. Then a second scoped run reports zero survivors, so the loop
    stops cleanly without a second commit attempt."""
    xml_with_survivor = _junit(_survived("Mutant #1", "src/a.py", 3), failures=1)
    xml_clean = _junit(_killed("Mutant #1", "src/a.py", 3))
    responses = [xml_with_survivor, xml_clean]
    monkeypatch.setattr(loop, "run_scoped_mutmut", lambda *a, **k: responses.pop(0))
    monkeypatch.setattr(loop, "python_compiles", lambda *a, **k: True)
    monkeypatch.setattr(loop, "run_scoped_pytest", lambda *a, **k: True)

    committed = []
    monkeypatch.setattr(
        loop, "git_commit", lambda message, test_file, **k: committed.append(message) or True
    )
    monkeypatch.setattr(loop, "git_revert", lambda *a, **k: pytest.fail("must not revert on green"))

    test_file = tmp_path / "test_a.py"
    test_file.write_text("def test_existing():\n    assert True\n", encoding="utf-8")
    source_file = tmp_path / "a.py"
    source_file.write_text("x = 1\n", encoding="utf-8")

    loop.run_for_file(
        "src/a.py",
        _ctx(test_file, source_file),
        generate=lambda *_a: "def test_new():\n    assert 1 == 1\n",
    )

    assert "def test_new():" in test_file.read_text(encoding="utf-8")
    assert len(committed) == 1
    assert "kill round 1" in committed[0]


def test_run_for_file_with_no_label_override_provider_uses_the_frozen_generator_label(
    tmp_path: Path, monkeypatch
):
    """Today's unchanged behavior: RunContext.label_override_provider
    defaults to None, so the commit trailer carries the frozen
    generator_label exactly as before #1908 Step 3.2b."""
    monkeypatch.setattr(
        loop, "run_scoped_mutmut", lambda *a, **k: _junit(_survived("Mutant #1", "src/a.py", 3), failures=1)
    )
    monkeypatch.setattr(loop, "python_compiles", lambda *a, **k: True)
    monkeypatch.setattr(loop, "run_scoped_pytest", lambda *a, **k: True)

    committed = []
    monkeypatch.setattr(
        loop, "git_commit", lambda message, test_file, **k: committed.append(message) or True
    )

    test_file = tmp_path / "test_a.py"
    test_file.write_text("def test_existing():\n    assert True\n", encoding="utf-8")
    source_file = tmp_path / "a.py"
    source_file.write_text("x = 1\n", encoding="utf-8")

    loop.run_for_file(
        "src/a.py",
        _ctx(test_file, source_file, generator_label="headless (opus)"),
        generate=lambda *_a: "def test_new():\n    assert 1 == 1\n",
        max_rounds=1,
    )

    assert len(committed) == 1
    assert "Generator: headless (opus)" in committed[0]


def test_run_for_file_uses_the_label_override_provider_for_the_commit_trailer(
    tmp_path: Path, monkeypatch
):
    """A model-downgrade event's per-round dynamic content, surfaced through
    RunContext.label_override_provider, replaces the frozen generator_label
    in that round's commit trailer (#1908 Step 3.2b) — the mechanism
    make_downgrade_audit_hook's on_downgrade/get_label_override pair exists
    to drive from each loop's make_headless_generator."""
    monkeypatch.setattr(
        loop, "run_scoped_mutmut", lambda *a, **k: _junit(_survived("Mutant #1", "src/a.py", 3), failures=1)
    )
    monkeypatch.setattr(loop, "python_compiles", lambda *a, **k: True)
    monkeypatch.setattr(loop, "run_scoped_pytest", lambda *a, **k: True)

    committed = []
    monkeypatch.setattr(
        loop, "git_commit", lambda message, test_file, **k: committed.append(message) or True
    )

    test_file = tmp_path / "test_a.py"
    test_file.write_text("def test_existing():\n    assert True\n", encoding="utf-8")
    source_file = tmp_path / "a.py"
    source_file.write_text("x = 1\n", encoding="utf-8")

    override_label = "headless (downgraded 'opus' -> 'sonnet' at round 1, gateway-class)"
    loop.run_for_file(
        "src/a.py",
        _ctx(
            test_file,
            source_file,
            generator_label="headless (opus)",
            label_override_provider=lambda: override_label,
        ),
        generate=lambda *_a: "def test_new():\n    assert 1 == 1\n",
        max_rounds=1,
    )

    assert len(committed) == 1
    assert f"Generator: {override_label}" in committed[0]
    assert "headless (opus)" not in committed[0]


def test_run_for_file_reverts_on_failing_scoped_test(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        loop, "run_scoped_mutmut", lambda *a, **k: _junit(_survived("Mutant #1", "src/a.py", 3), failures=1)
    )
    monkeypatch.setattr(loop, "python_compiles", lambda *a, **k: True)
    monkeypatch.setattr(loop, "run_scoped_pytest", lambda *a, **k: False)

    reverted = []
    monkeypatch.setattr(
        loop, "git_revert", lambda test_file, **k: reverted.append(test_file) or True
    )
    monkeypatch.setattr(
        loop, "git_commit", lambda *a, **k: pytest.fail("must not commit on a failing test")
    )

    test_file = tmp_path / "test_a.py"
    test_file.write_text("def test_existing():\n    assert True\n", encoding="utf-8")
    source_file = tmp_path / "a.py"
    source_file.write_text("x = 1\n", encoding="utf-8")

    loop.run_for_file(
        "src/a.py",
        _ctx(test_file, source_file),
        generate=lambda *_a: "def test_new():\n    assert False\n",
    )

    assert reverted == [test_file]


def test_run_for_file_stops_on_no_improvement(tmp_path: Path, monkeypatch):
    """Same survivor count twice in a row must stop the loop, not loop forever."""
    same_xml = _junit(_survived("Mutant #1", "src/a.py", 3), failures=1)
    responses = [same_xml, same_xml]
    monkeypatch.setattr(loop, "run_scoped_mutmut", lambda *a, **k: responses.pop(0))
    monkeypatch.setattr(loop, "python_compiles", lambda *a, **k: True)
    monkeypatch.setattr(loop, "run_scoped_pytest", lambda *a, **k: True)

    committed = []
    monkeypatch.setattr(loop, "git_commit", lambda m, f, **k: committed.append(m) or True)

    test_file = tmp_path / "test_a.py"
    test_file.write_text("def test_existing():\n    assert True\n", encoding="utf-8")
    source_file = tmp_path / "a.py"
    source_file.write_text("x = 1\n", encoding="utf-8")

    calls = {"n": 0}

    def fake_generate(*_a):
        calls["n"] += 1
        return f"def test_new_{calls['n']}():\n    assert True\n"

    loop.run_for_file(
        "src/a.py",
        _ctx(test_file, source_file),
        generate=fake_generate,
        max_rounds=5,
    )

    # Round 1 commits (first round always proceeds — prev_survivor_count
    # starts None); round 2 sees the same count and stops without
    # generating again.
    assert len(committed) == 1
    assert calls["n"] == 1


# =============================================================================
# Scenario: max_rounds is exhausted while survivors are still strictly
# improving each round (never reaching 0, and never repeating the previous
# round's count) — the loop must stop because the round budget ran out, not
# because of either the "zero survivors" or "no improvement" stop_reason
# paths (#1563 gap 6, mirrors the C# loop's equivalent scenario).
# =============================================================================
def test_max_rounds_exhausted_while_survivors_keep_improving(
    tmp_path: Path, monkeypatch
):
    xml_two_survivors = _junit(
        _survived("Mutant #1", "src/a.py", 3),
        _survived("Mutant #2", "src/a.py", 5),
        failures=2,
    )
    xml_one_survivor = _junit(_survived("Mutant #1", "src/a.py", 3), failures=1)
    responses = [xml_two_survivors, xml_one_survivor]
    monkeypatch.setattr(loop, "run_scoped_mutmut", lambda *a, **k: responses.pop(0))
    monkeypatch.setattr(loop, "python_compiles", lambda *a, **k: True)
    monkeypatch.setattr(loop, "run_scoped_pytest", lambda *a, **k: True)

    committed = []
    monkeypatch.setattr(loop, "git_commit", lambda m, f, **k: committed.append(m) or True)
    monkeypatch.setattr(loop, "git_revert", lambda *a, **k: pytest.fail("must not revert on green"))

    test_file = tmp_path / "test_a.py"
    test_file.write_text("def test_existing():\n    assert True\n", encoding="utf-8")
    source_file = tmp_path / "a.py"
    source_file.write_text("x = 1\n", encoding="utf-8")

    logged = []
    calls = {"n": 0}

    def unique_generate(*_a):
        calls["n"] += 1
        return f"def test_new_{calls['n']}():\n    assert True\n"

    loop.run_for_file(
        "src/a.py",
        _ctx(test_file, source_file, log=logged.append),
        generate=unique_generate,
        max_rounds=2,
    )

    round_logs = [m for m in logged if m.startswith("  round")]
    assert len(round_logs) == 2, "max_rounds=2 must cap the loop at exactly 2 rounds"
    assert "survivors=2" in round_logs[0]
    assert "survivors=1" in round_logs[1]
    # Neither stop_reason fired — the loop ended solely because the round
    # budget (max_rounds) was exhausted.
    assert not any("no survivors" in m or "no improvement" in m for m in logged)
    assert len(committed) == 2


# =============================================================================
# Scenario: A failed commit is a round failure, not a silent success (#1598),
# mirroring mutation_kill_loop.py's C# equivalent scenario.
# =============================================================================
def test_failed_commit_reverts_and_stops_the_round(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        loop, "run_scoped_mutmut", lambda *a, **k: _junit(_survived("Mutant #1", "src/a.py", 3), failures=1)
    )
    monkeypatch.setattr(loop, "python_compiles", lambda *a, **k: True)
    monkeypatch.setattr(loop, "run_scoped_pytest", lambda *a, **k: True)

    events: list = []
    monkeypatch.setattr(
        loop, "git_commit", lambda msg, tf, **k: events.append(("commit", msg)) or False
    )
    monkeypatch.setattr(
        loop,
        "git_reset_and_revert",
        lambda tf, **k: events.append(("revert", str(tf))) or True,
    )

    test_file = tmp_path / "test_a.py"
    test_file.write_text("def test_existing():\n    assert True\n", encoding="utf-8")
    source_file = tmp_path / "a.py"
    source_file.write_text("x = 1\n", encoding="utf-8")

    calls = {"n": 0}

    def fake_generate(*_a):
        calls["n"] += 1
        return "def test_new():\n    assert True\n"

    loop.run_for_file("src/a.py", _ctx(test_file, source_file), generate=fake_generate)

    kinds = [e[0] for e in events]
    assert kinds.count("commit") == 1
    assert kinds.count("revert") == 1
    assert calls["n"] == 1


def test_revert_failure_after_failed_commit_is_fatal(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        loop, "run_scoped_mutmut", lambda *a, **k: _junit(_survived("Mutant #1", "src/a.py", 3), failures=1)
    )
    monkeypatch.setattr(loop, "python_compiles", lambda *a, **k: True)
    monkeypatch.setattr(loop, "run_scoped_pytest", lambda *a, **k: True)
    monkeypatch.setattr(loop, "git_commit", lambda msg, tf, **k: False)
    # The commit-failure revert path calls git_reset_and_revert, not plain
    # git_revert (#1598/#1584 review) — that's the function that must fail.
    monkeypatch.setattr(loop, "git_reset_and_revert", lambda tf, **k: False)

    test_file = tmp_path / "test_a.py"
    test_file.write_text("def test_existing():\n    assert True\n", encoding="utf-8")
    source_file = tmp_path / "a.py"
    source_file.write_text("x = 1\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="revert failed"):
        loop.run_for_file(
            "src/a.py",
            _ctx(test_file, source_file),
            generate=lambda *_a: "def test_new():\n    assert True\n",
        )


def test_revert_failure_after_build_failure_is_fatal(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        loop, "run_scoped_mutmut", lambda *a, **k: _junit(_survived("Mutant #1", "src/a.py", 3), failures=1)
    )
    monkeypatch.setattr(loop, "python_compiles", lambda *a, **k: False)
    monkeypatch.setattr(loop, "git_revert", lambda tf, **k: False)

    test_file = tmp_path / "test_a.py"
    test_file.write_text("def test_existing():\n    assert True\n", encoding="utf-8")
    source_file = tmp_path / "a.py"
    source_file.write_text("x = 1\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="revert failed"):
        loop.run_for_file(
            "src/a.py",
            _ctx(test_file, source_file),
            generate=lambda *_a: "def test_new():\n    assert True\n",
        )


def test_revert_failure_after_test_failure_is_fatal(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        loop, "run_scoped_mutmut", lambda *a, **k: _junit(_survived("Mutant #1", "src/a.py", 3), failures=1)
    )
    monkeypatch.setattr(loop, "python_compiles", lambda *a, **k: True)
    monkeypatch.setattr(loop, "run_scoped_pytest", lambda *a, **k: False)
    monkeypatch.setattr(loop, "git_revert", lambda tf, **k: False)

    test_file = tmp_path / "test_a.py"
    test_file.write_text("def test_existing():\n    assert True\n", encoding="utf-8")
    source_file = tmp_path / "a.py"
    source_file.write_text("x = 1\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="revert failed"):
        loop.run_for_file(
            "src/a.py",
            _ctx(test_file, source_file),
            generate=lambda *_a: "def test_new():\n    assert True\n",
        )


# =============================================================================
# Scenario (real git, no mocks): git_reset_and_revert leaves both the index
# AND the working tree matching HEAD after a commit-failure-style staged
# mutation — mirrors mutation_kill_loop.py's real-git regression test for
# the same #1598 bug class.
# =============================================================================
def test_git_reset_and_revert_restores_index_and_worktree_after_a_staged_mutation(
    tmp_path: Path,
):
    git_hermetic(tmp_path, "init", "-q")
    git_hermetic(tmp_path, "config", "user.email", "test@example.com")
    git_hermetic(tmp_path, "config", "user.name", "Test")
    git_hermetic(tmp_path, "config", "commit.gpgsign", "false")

    test_file = tmp_path / "test_a.py"
    original = "def test_existing():\n    assert True\n"
    test_file.write_text(original, encoding="utf-8")
    git_hermetic(tmp_path, "add", "-A")
    git_hermetic(tmp_path, "commit", "-q", "-m", "initial")

    mutated = original + "\ndef test_mutated_never_committed():\n    assert False\n"
    test_file.write_text(mutated, encoding="utf-8")
    git_hermetic(tmp_path, "add", "--", str(test_file))

    staged = git_hermetic(tmp_path, "diff", "--cached", "--name-only")
    assert "test_a.py" in staged.stdout

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

    assert test_file.read_text(encoding="utf-8") == original
    status = git_hermetic(tmp_path, "status", "--porcelain")
    assert status.stdout.strip() == ""


# =============================================================================
# Scenario: --literal-pathspecs neutralizes pathspec magic characters in a
# test_file value — every git call in both loops treats `--` as introducing a
# pathspec, not a literal path, so magic characters (`:/`, `:(glob)`, etc.)
# remain active even after `--` unless --literal-pathspecs is set
# (#1598/#1584 review, item 5). Real git (hermetic), not mocked: a mocked
# argv-shape assertion can't prove the flag actually changes git's matching
# behavior the way this test does.
# =============================================================================
def test_git_revert_with_a_literal_pathspecs_flag_does_not_broaden_scope_to_a_glob_match(
    tmp_path: Path,
):
    git_hermetic(tmp_path, "init", "-q")
    git_hermetic(tmp_path, "config", "user.email", "test@example.com")
    git_hermetic(tmp_path, "config", "user.name", "Test")
    git_hermetic(tmp_path, "config", "commit.gpgsign", "false")

    important = tmp_path / "important.py"
    original = "def test_important():\n    assert True\n"
    important.write_text(original, encoding="utf-8")
    git_hermetic(tmp_path, "add", "-A")
    git_hermetic(tmp_path, "commit", "-q", "-m", "initial")

    # Mutate the file we DON'T want touched.
    mutated = original + "\ndef test_mutated():\n    assert False\n"
    important.write_text(mutated, encoding="utf-8")

    # A test_file value shaped like a pathspec-magic glob — without
    # --literal-pathspecs, `git checkout -- ':(glob)*.py'` would match every
    # .py file in the repo (including important.py) and silently revert it
    # too. With --literal-pathspecs, this string is a literal (nonexistent)
    # filename, so the revert affects nothing else.
    magic_path = Path(":(glob)*.py")

    result = loop.git_revert(magic_path, cwd=tmp_path, env=hermetic_git_env(home=tmp_path))

    # The literal path doesn't exist, so the revert itself fails...
    assert result is False
    # ...and, crucially, important.py's uncommitted mutation survives —
    # proving the operation did NOT broaden to match every .py file via glob.
    assert important.read_text(encoding="utf-8") == mutated
