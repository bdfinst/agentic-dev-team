"""Pytest tests for mutation_kill_loop_python.py — the Python/mutmut
counterpart to mutation_kill_loop.py's survivor-kill loop mechanics (#1357).

Every mutmut / git / pytest subprocess is mocked — no real mutmut run
happens here (that's covered by the manual, real-tool dogfooding recorded
in #1354/#1357's issue history). Insertion mechanics run against real
tmp_path files since they're pure file I/O with no subprocess involved.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = (
    Path(__file__).resolve().parents[2]
    / "plugins"
    / "dev-team"
    / "skills"
    / "mutation-testing"
    / "scripts"
)
sys.path.insert(0, str(SCRIPTS_DIR))

import mutation_kill_loop_python as loop

FORBIDDEN_LITERALS = ["Aci.Speedpay", "Controllers", "AwesomeAssertions", "Moq", "AutoFixture"]


# =============================================================================
# Reused headless helpers actually come from mutation_kill_loop
# =============================================================================
def test_headless_helpers_are_reused_not_duplicated():
    import mutation_kill_loop as cs_loop

    assert loop.strip_code_fences is cs_loop.strip_code_fences
    assert loop.resolve_model is cs_loop.resolve_model
    assert loop.claude_cli_available is cs_loop.claude_cli_available
    assert loop.CLAUDE_CLI == cs_loop.CLAUDE_CLI


# =============================================================================
# extract_survivors — delegates to mutation_report's junitxml support
# =============================================================================
def _junit(*testcases: str, failures: int = 0) -> str:
    body = "\n".join(testcases)
    return (
        '<?xml version="1.0" ?>\n'
        f'<testsuites errors="0" failures="{failures}" tests="{len(testcases)}">\n'
        f'<testsuite errors="0" failures="{failures}" name="mutmut" tests="{len(testcases)}">\n'
        f"{body}\n</testsuite></testsuites>\n"
    )


def _survived(name: str, file: str, line: int) -> str:
    return (
        f'<testcase name="{name}" file="{file}" line="{line}">'
        '<failure type="failure" message="bad_survived">diff</failure></testcase>'
    )


def _killed(name: str, file: str, line: int) -> str:
    return f'<testcase name="{name}" file="{file}" line="{line}"><system-out>x</system-out></testcase>'


def test_run_scoped_mutmut_reverts_source_file_even_when_mutmut_crashes(
    tmp_path: Path, monkeypatch
):
    """mutmut mutates the real source file on disk per-mutant and restores it
    when done — but a mutmut-internal crash (real, reproducible: mutmut
    2.5.1's own cache layer, confirmed while dogfooding this exact function
    against hooks/mutation_adapters/mutmut.py, #1357) skips that restore and
    leaves mutated content on disk. run_scoped_mutmut must always revert the
    source file, even when the mutmut subprocess itself raises."""
    monkeypatch.setattr(loop, "_mutmut_argv", lambda: ["mutmut"])

    def boom(*_a, **_k):
        raise RuntimeError("simulated mutmut internal crash")

    monkeypatch.setattr(loop.subprocess, "run", boom)

    reverted = []
    monkeypatch.setattr(loop, "git_revert", lambda path, **k: reverted.append(path))

    with pytest.raises(RuntimeError):
        loop.run_scoped_mutmut("src/a.py", test_command="pytest", cwd=tmp_path)

    assert reverted == [Path("src/a.py")]


def test_run_scoped_mutmut_reverts_source_file_on_the_success_path_too(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(loop, "_mutmut_argv", lambda: ["mutmut"])

    class _FakeCompleted:
        stdout = "<testsuites></testsuites>"

    monkeypatch.setattr(loop.subprocess, "run", lambda *a, **k: _FakeCompleted())

    reverted = []
    monkeypatch.setattr(loop, "git_revert", lambda path, **k: reverted.append(path))

    loop.run_scoped_mutmut("src/a.py", test_command="pytest", cwd=tmp_path)

    assert reverted == [Path("src/a.py")]


def test_run_scoped_mutmut_reverts_test_file_too_when_mutmut_crashes(
    tmp_path: Path, monkeypatch
):
    """mutmut 2.5.1 has also been observed to corrupt the *runner's test
    file* (truncate it to empty via a crashed .bak-restore, #1359) — not
    just the source file. run_scoped_mutmut must revert both when a
    test_file is supplied, even when the mutmut subprocess itself raises."""
    monkeypatch.setattr(loop, "_mutmut_argv", lambda: ["mutmut"])

    def boom(*_a, **_k):
        raise RuntimeError("simulated mutmut internal crash")

    monkeypatch.setattr(loop.subprocess, "run", boom)

    reverted = []
    monkeypatch.setattr(loop, "git_revert", lambda path, **k: reverted.append(path))

    with pytest.raises(RuntimeError):
        loop.run_scoped_mutmut(
            "src/a.py",
            test_command="pytest",
            test_file=Path("tests/test_a.py"),
            cwd=tmp_path,
        )

    assert reverted == [Path("src/a.py"), Path("tests/test_a.py")]


def test_run_scoped_mutmut_reverts_test_file_on_the_success_path_too(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(loop, "_mutmut_argv", lambda: ["mutmut"])

    class _FakeCompleted:
        stdout = "<testsuites></testsuites>"

    monkeypatch.setattr(loop.subprocess, "run", lambda *a, **k: _FakeCompleted())

    reverted = []
    monkeypatch.setattr(loop, "git_revert", lambda path, **k: reverted.append(path))

    loop.run_scoped_mutmut(
        "src/a.py",
        test_command="pytest",
        test_file=Path("tests/test_a.py"),
        cwd=tmp_path,
    )

    assert reverted == [Path("src/a.py"), Path("tests/test_a.py")]


def test_run_scoped_mutmut_does_not_revert_test_file_when_not_supplied(
    tmp_path: Path, monkeypatch
):
    """Backward compatibility: callers that don't pass test_file (none did
    before #1359) must see identical behavior to before this change."""
    monkeypatch.setattr(loop, "_mutmut_argv", lambda: ["mutmut"])

    class _FakeCompleted:
        stdout = "<testsuites></testsuites>"

    monkeypatch.setattr(loop.subprocess, "run", lambda *a, **k: _FakeCompleted())

    reverted = []
    monkeypatch.setattr(loop, "git_revert", lambda path, **k: reverted.append(path))

    loop.run_scoped_mutmut("src/a.py", test_command="pytest", cwd=tmp_path)

    assert reverted == [Path("src/a.py")]


def test_extract_survivors_filters_to_target_file():
    xml = _junit(
        _survived("Mutant #1", "src/a.py", 5),
        _survived("Mutant #2", "src/b.py", 9),
        _killed("Mutant #3", "src/a.py", 1),
        failures=2,
    )
    survivors = loop.extract_survivors(xml, "src/a.py")

    assert len(survivors) == 1
    assert survivors[0]["location"]["start"]["line"] == 5
    assert survivors[0]["mutatorName"] == "mutmut"


# =============================================================================
# Insertion mechanics — flat top-level `def test_*():` convention
# =============================================================================
def test_append_at_end_of_file_adds_new_tests(tmp_path: Path):
    test_file = tmp_path / "test_calc.py"
    test_file.write_text("def test_existing():\n    assert True\n", encoding="utf-8")

    loop.append_at_end_of_file(test_file, "def test_new():\n    assert 1 == 1\n")

    text = test_file.read_text(encoding="utf-8")
    assert "def test_existing():" in text
    assert "def test_new():" in text
    # existing content preserved, new content appended after it
    assert text.index("test_existing") < text.index("test_new")


def test_append_refuses_when_no_existing_top_level_test_function(tmp_path: Path):
    """A class-based test file (or any file with no top-level `def test_`)
    doesn't match the flat convention this heuristic supports — refuse
    rather than guess an insertion point."""
    test_file = tmp_path / "test_calc.py"
    test_file.write_text(
        "class TestCalc:\n    def test_existing(self):\n        assert True\n",
        encoding="utf-8",
    )

    with pytest.raises(loop.InsertionRefused):
        loop.append_at_end_of_file(test_file, "def test_new():\n    assert True\n")

    # file must be left untouched on refusal
    assert "test_new" not in test_file.read_text(encoding="utf-8")


def test_detect_duplicate_functions_finds_name_collisions():
    existing = "def test_a():\n    pass\n\ndef test_b():\n    pass\n"
    incoming = "def test_b():\n    pass\n"
    assert loop.detect_duplicate_functions(existing, incoming) == ["test_b"]


def test_apply_generated_tests_empty_generation_not_inserted(tmp_path: Path):
    test_file = tmp_path / "test_calc.py"
    test_file.write_text("def test_existing():\n    assert True\n", encoding="utf-8")

    outcome = loop.apply_generated_tests(test_file, "   \n")

    assert outcome.inserted is False
    assert "no tests generated" in outcome.reason


def test_apply_generated_tests_duplicate_name_not_inserted(tmp_path: Path):
    test_file = tmp_path / "test_calc.py"
    test_file.write_text("def test_existing():\n    assert True\n", encoding="utf-8")

    outcome = loop.apply_generated_tests(
        test_file, "def test_existing():\n    assert False\n"
    )

    assert outcome.inserted is False
    assert "duplicate" in outcome.reason
    # original content unchanged
    assert "assert True" in test_file.read_text(encoding="utf-8")


def test_apply_generated_tests_success_path_inserts(tmp_path: Path):
    test_file = tmp_path / "test_calc.py"
    test_file.write_text("def test_existing():\n    assert True\n", encoding="utf-8")

    outcome = loop.apply_generated_tests(test_file, "def test_new():\n    assert 2 == 2\n")

    assert outcome.inserted is True
    assert "def test_new():" in test_file.read_text(encoding="utf-8")


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

    loop.run_for_file(
        "src/a.py",
        test_file=test_file,
        source_path=source_file,
        test_command="pytest",
        generate=fake_generate,
    )

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
        test_file=test_file,
        source_path=source_file,
        test_command="pytest",
        generate=fake_generate,
        log=logged.append,
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
        test_file=test_file,
        source_path=source_file,
        test_command="pytest",
        generate=lambda *_a: "def test_new():\n    assert 1 == 1\n",
    )

    assert "def test_new():" in test_file.read_text(encoding="utf-8")
    assert len(committed) == 1
    assert "kill round 1" in committed[0]


def test_run_for_file_reverts_on_failing_scoped_test(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        loop, "run_scoped_mutmut", lambda *a, **k: _junit(_survived("Mutant #1", "src/a.py", 3), failures=1)
    )
    monkeypatch.setattr(loop, "python_compiles", lambda *a, **k: True)
    monkeypatch.setattr(loop, "run_scoped_pytest", lambda *a, **k: False)

    reverted = []
    monkeypatch.setattr(loop, "git_revert", lambda test_file, **k: reverted.append(test_file))
    monkeypatch.setattr(
        loop, "git_commit", lambda *a, **k: pytest.fail("must not commit on a failing test")
    )

    test_file = tmp_path / "test_a.py"
    test_file.write_text("def test_existing():\n    assert True\n", encoding="utf-8")
    source_file = tmp_path / "a.py"
    source_file.write_text("x = 1\n", encoding="utf-8")

    loop.run_for_file(
        "src/a.py",
        test_file=test_file,
        source_path=source_file,
        test_command="pytest",
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
        test_file=test_file,
        source_path=source_file,
        test_command="pytest",
        generate=fake_generate,
        max_rounds=5,
    )

    # Round 1 commits (first round always proceeds — prev_survivors starts
    # None); round 2 sees the same count and stops without generating again.
    assert len(committed) == 1
    assert calls["n"] == 1


# =============================================================================
# No repo-specific literal leaked into the module
# =============================================================================
def test_module_source_carries_no_repo_specific_literal():
    source = (SCRIPTS_DIR / "mutation_kill_loop_python.py").read_text(encoding="utf-8")
    present = [literal for literal in FORBIDDEN_LITERALS if literal in source]
    assert present == [], f"repo-specific literals leaked into module: {present}"


# =============================================================================
# CLI preflight — mirrors mutation_kill_loop.py's fail-fast contract
# =============================================================================
def test_main_without_headless_fails_fast_with_no_generator_message(capsys):
    rc = loop.main([])
    assert rc == 1
    assert loop.NO_GENERATOR_MESSAGE in capsys.readouterr().err


def test_main_headless_without_required_flags_errors(monkeypatch, capsys):
    monkeypatch.setattr(loop, "claude_cli_available", lambda: True)
    rc = loop.main(["--headless"])
    assert rc == 2
    assert "requires --file" in capsys.readouterr().err


def test_main_headless_missing_claude_cli_fails_before_touching_files(monkeypatch, capsys):
    monkeypatch.setattr(loop, "claude_cli_available", lambda: False)
    rc = loop.main(["--headless", "--file", "a.py"])
    assert rc == 3
    assert "Claude CLI" in capsys.readouterr().err
