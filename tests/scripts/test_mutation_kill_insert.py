"""Pytest tests for mutation_kill_insert.py — C# test-method insertion
mechanics, split out of mutation_kill_loop.py (#1562).

Pure file I/O, no subprocess involved — these exercise the detect-or-refuse
insertion heuristic directly against real tmp_path files.
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

import mutation_kill_insert as insert

FORBIDDEN_LITERALS = ["Aci.Speedpay", "Controllers", "AwesomeAssertions", "Moq", "AutoFixture"]

_BLOCK_NAMESPACE_CLASS = (
    "namespace Widget.Tests\n"
    "{\n"
    "    public class PaymentServiceTests\n"
    "    {\n"
    "        [Test]\n"
    "        public async Task Existing_Case_Works()\n"
    "        {\n"
    "        }\n"
    "    }\n"
    "}\n"
)

_FILE_SCOPED_CLASS = (
    "namespace Widget.Tests;\n"
    "\n"
    "public class PaymentServiceTests\n"
    "{\n"
    "    [Test]\n"
    "    public async Task Existing_Case_Works()\n"
    "    {\n"
    "    }\n"
    "}\n"
)

_NEW_METHOD = (
    "        [Test]\n"
    "        public async Task New_Case_KillsMutant()\n"
    "        {\n"
    "        }\n"
)


# =============================================================================
# Scenario: Duplicate method names abort insertion
# =============================================================================
def test_duplicate_method_names_abort_insertion(tmp_path: Path):
    test_file = tmp_path / "PaymentServiceTests.cs"
    test_file.write_text(_BLOCK_NAMESPACE_CLASS, encoding="utf-8")
    before = test_file.read_text(encoding="utf-8")

    dup_block = (
        "        [Test]\n"
        "        public async Task Existing_Case_Works()\n"
        "        {\n"
        "        }\n"
    )

    outcome = insert.apply_generated_methods(test_file, dup_block)

    assert outcome.inserted is False
    assert "duplicate" in outcome.reason.lower()
    # File is unchanged.
    assert test_file.read_text(encoding="utf-8") == before


def test_detect_duplicate_methods_reports_only_collisions():
    dupes = insert.detect_duplicate_methods(
        _BLOCK_NAMESPACE_CLASS,
        "public async Task Existing_Case_Works() {}\n"
        "public async Task Brand_New_Case() {}\n",
    )
    assert dupes == ["Existing_Case_Works"]


# =============================================================================
# Scenario: Generated methods are inserted before the class-closing brace
# =============================================================================
def test_methods_inserted_before_class_closing_brace(tmp_path: Path):
    test_file = tmp_path / "PaymentServiceTests.cs"
    test_file.write_text(_BLOCK_NAMESPACE_CLASS, encoding="utf-8")

    outcome = insert.apply_generated_methods(test_file, _NEW_METHOD)

    assert outcome.inserted is True
    lines = test_file.read_text(encoding="utf-8").splitlines()
    new_idx = next(i for i, ln in enumerate(lines) if "New_Case_KillsMutant" in ln)
    # The class-close ("    }") and namespace-close ("}") follow the new method.
    class_close_idx = next(
        i for i in range(new_idx + 1, len(lines)) if lines[i].rstrip("\r\n") == "    }"
    )
    ns_close_idx = next(
        i for i in range(class_close_idx + 1, len(lines)) if lines[i].strip() == "}"
    )
    assert new_idx < class_close_idx < ns_close_idx


# =============================================================================
# Scenario: Insertion into a file-scoped-namespace class is handled or refused
# =============================================================================
def test_file_scoped_namespace_is_refused_not_corrupted(tmp_path: Path):
    test_file = tmp_path / "PaymentServiceTests.cs"
    test_file.write_text(_FILE_SCOPED_CLASS, encoding="utf-8")
    before = test_file.read_text(encoding="utf-8")

    with pytest.raises(insert.InsertionRefused) as exc:
        insert.insert_before_class_close(test_file, _NEW_METHOD)

    assert "file-scoped" in str(exc.value).lower()
    # Never silently appended — file is byte-for-byte unchanged.
    assert test_file.read_text(encoding="utf-8") == before


def test_non_four_space_indent_is_refused(tmp_path: Path):
    # Block namespace but the class body is tab-indented — the 4-space
    # class-close heuristic must refuse rather than mis-insert.
    tabbed = (
        "namespace Widget.Tests\n"
        "{\n"
        "\tpublic class PaymentServiceTests\n"
        "\t{\n"
        "\t}\n"
        "}\n"
    )
    test_file = tmp_path / "PaymentServiceTests.cs"
    test_file.write_text(tabbed, encoding="utf-8")
    before = test_file.read_text(encoding="utf-8")

    with pytest.raises(insert.InsertionRefused):
        insert.insert_before_class_close(test_file, _NEW_METHOD)

    assert test_file.read_text(encoding="utf-8") == before


def test_apply_wraps_refusal_as_outcome_without_writing(tmp_path: Path):
    test_file = tmp_path / "PaymentServiceTests.cs"
    test_file.write_text(_FILE_SCOPED_CLASS, encoding="utf-8")
    before = test_file.read_text(encoding="utf-8")

    outcome = insert.apply_generated_methods(test_file, _NEW_METHOD)

    assert outcome.inserted is False
    assert "file-scoped" in outcome.reason.lower()
    assert test_file.read_text(encoding="utf-8") == before


# =============================================================================
# Scenario: Generated test code with unsafe side effects is refused, not
# silently inserted and auto-committed with zero human review (#1560)
# =============================================================================
@pytest.mark.parametrize(
    ("category", "snippet"),
    [
        ("network", "var client = new HttpClient(); client.GetAsync(url);"),
        (
            "network",
            "var s = new Socket(AddressFamily.InterNetwork, SocketType.Stream, ProtocolType.Tcp);",
        ),
        ("process", 'Process.Start("curl", "http://evil.example");'),
        # Bare Process/StartInfo property-chain — no ".Start(" call site to
        # match, an idiomatic (not obfuscated) way to spawn a process.
        ("process", 'var p = new Process(); p.StartInfo.FileName = "cmd"; p.Start();'),
        ("filesystem", 'File.WriteAllText("/etc/passwd", "pwned");'),
        ("filesystem", 'new StreamWriter("/etc/cron.d/x").Write(payload);'),
        # Whitespace/line-break around the member-access dot — legitimate C#
        # formatting, not obfuscation.
        ("filesystem", 'File\n    .WriteAllText("x", "y");'),
        # *Async variants and instance-based FileInfo/DirectoryInfo — a
        # trailing-\b-vs-longer-real-method-name gap, and a different-type
        # gap, respectively.
        ("filesystem", 'await File.WriteAllTextAsync("/etc/cron.d/x", payload);'),
        ("filesystem", 'new FileInfo("/etc/cron.d/x").Delete();'),
        ("environment", 'var secret = Environment.GetEnvironmentVariable("API_KEY");'),
        ("environment", "var all = Environment.GetEnvironmentVariables();"),
        ("reflection", "Activator.CreateInstance(Type.GetType(typeName));"),
        ("reflection", "Assembly.Load(bytes);"),
        ("reflection", "Assembly.LoadFrom(path);"),
        ("interop", '[DllImport("kernel32.dll")] static extern void Evil();'),
        ("interop", "Marshal.Copy(source, destination, 0, length);"),
        # Bare `unsafe` keyword — the negative-lookbehind branch of the
        # interop pattern, independent of Marshal/DllImport.
        ("interop", "unsafe { fixed (int* p = &buf[0]) { } }"),
    ],
    ids=[
        "network-httpclient",
        "network-socket",
        "process-static-start",
        "process-bare-startinfo",
        "filesystem-writealltext",
        "filesystem-streamwriter",
        "filesystem-whitespace-dot",
        "filesystem-writealltextasync",
        "filesystem-fileinfo-delete",
        "environment-getvar",
        "environment-getvars-plural",
        "reflection-activator",
        "reflection-assembly-load",
        "reflection-assembly-loadfrom",
        "interop-dllimport",
        "interop-marshal",
        "interop-unsafe-keyword",
    ],
)
def test_scan_for_unsafe_patterns_flags_each_category(category: str, snippet: str):
    assert category in insert.scan_for_unsafe_patterns(snippet)


def test_scan_for_unsafe_patterns_returns_empty_for_a_clean_method():
    assert insert.scan_for_unsafe_patterns(_NEW_METHOD) == []


def test_unsafe_generated_method_is_refused_not_inserted(tmp_path: Path):
    test_file = tmp_path / "PaymentServiceTests.cs"
    test_file.write_text(_BLOCK_NAMESPACE_CLASS, encoding="utf-8")
    before = test_file.read_text(encoding="utf-8")
    unsafe_method = (
        "        [Test]\n"
        "        public async Task New_Case_KillsMutant()\n"
        "        {\n"
        "            new HttpClient().GetAsync(\"http://evil.example\");\n"
        "        }\n"
    )

    outcome = insert.apply_generated_methods(test_file, unsafe_method)

    assert outcome.inserted is False
    assert "unsafe" in outcome.reason.lower()
    assert "network" in outcome.reason
    # Never silently inserted — file is byte-for-byte unchanged.
    assert test_file.read_text(encoding="utf-8") == before


# =============================================================================
# Scenario: count_methods backs the loop's commit-message method count
# =============================================================================
def test_count_methods_counts_public_test_methods():
    assert insert.count_methods(_NEW_METHOD) == 1
    assert insert.count_methods(_NEW_METHOD + _NEW_METHOD.replace(
        "New_Case_KillsMutant", "Another_Case"
    )) == 2
