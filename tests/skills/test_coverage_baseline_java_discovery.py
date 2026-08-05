"""Coverage for coverage-baseline/SKILL.md Step 1a's Java row (issue #1765):
wiring `coverage_discovery_java.discover_java_modules` into the documented
contract surface.

Mirrors `test_coverage_baseline_dotnet_discovery.py` and
`test_coverage_baseline_js_discovery.py`. This file is the gate that makes an
UNWIRED discovery stack fail visibly: #1765's first revision shipped a working
`coverage_discovery_java.py` that no skill dispatched to, so a Maven/Gradle
multi-module repo silently kept taking the single aggregate-command path — the
exact silent-under-reporting failure mode multi-project discovery exists to
prevent, and precisely the "gate that cannot fail" shape CLAUDE.md names. A
per-stack counterpart of this file is required for every new stack.
"""

import sys

from skill_doc_helpers import PLUGIN_ROOT, collapsed, grep, section

SCRIPTS_DIR = PLUGIN_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import coverage_discovery_java as cdjava  # noqa: F401  (import-ability is part of the contract)

BASELINE_SKILL = PLUGIN_ROOT / "skills" / "coverage-baseline" / "SKILL.md"
DELTA_SKILL = PLUGIN_ROOT / "skills" / "coverage-delta" / "SKILL.md"
REFERENCE = (
    PLUGIN_ROOT
    / "skills"
    / "coverage-baseline"
    / "references"
    / "multi-project-discovery.md"
)


def _baseline_text() -> str:
    return BASELINE_SKILL.read_text()


def _step_1a_section() -> str:
    return section(
        _baseline_text(),
        r"^### 1a\. Multi-project discovery",
        boundary_pattern=r"^### ",
    )


# ---------------------------------------------------------------------------
# The stack is reachable: Step 1a names the script and its entry point
# ---------------------------------------------------------------------------


def test_step_1a_names_java_discovery_script():
    assert grep(r"coverage_discovery_java\.py", _step_1a_section())


def test_step_1a_names_the_java_entry_point():
    assert grep(r"discover_java_modules\(repo_root\)", _step_1a_section())


def test_step_1a_documents_both_java_build_graph_triggers():
    step_1a = _step_1a_section()
    assert grep(r"<modules>", step_1a)
    assert grep(r"settings\.gradle", step_1a)
    assert grep(r"include\(\.\.\.\)", step_1a)


def test_step_1a_documents_maven_precedence_over_gradle():
    step_1a = _step_1a_section()
    assert grep(r"[Mm]aven takes\s+precedence", step_1a)
    assert grep(r"no cross-merge", step_1a)


def test_step_1a_documents_the_java_test_marker():
    """The marker must be documented, because the zero-real-test-project
    message tells the operator what to verify."""
    step_1a = _step_1a_section()
    assert grep(r"src/test/java", step_1a)
    assert grep(r"JUnit/TestNG", step_1a)


def test_step_1a_documents_ambiguous_for_inherited_java_markers():
    step_1a = _step_1a_section()
    assert grep(r"AMBIGUOUS", step_1a)
    assert grep(r"inherited", step_1a)


# ---------------------------------------------------------------------------
# The manifest table routes Java repos into Step 1a
# ---------------------------------------------------------------------------


def test_java_manifest_rows_link_to_step_1a():
    """Extracted line-by-line, not grepped across the file, so this fails if
    either Java row drops its link while the other keeps it."""
    anchor = r"#1a-multi-project-discovery"
    lines = _baseline_text().splitlines()

    pom_line = next(line for line in lines if line.startswith("| `pom.xml` |"))
    gradle_line = next(
        line for line in lines if line.startswith("| `build.gradle*` |")
    )

    assert grep(anchor, pom_line)
    assert grep(anchor, gradle_line)


def test_repo_coverage_script_override_excludes_the_java_rows():
    """A repo-level coverage script must not override per-run re-derivation for
    a multi-module Java build, same as for .sln/.csproj."""
    text = _baseline_text()
    assert grep(r"does not apply to the.*`pom\.xml`.*`build\.gradle\*`", text)


# ---------------------------------------------------------------------------
# The stop message covers Java, and the delta side re-derives it too
# ---------------------------------------------------------------------------


def test_zero_real_test_project_message_covers_all_three_stacks():
    for text in (_baseline_text(), DELTA_SKILL.read_text(), REFERENCE.read_text()):
        assert grep(r"<solution\|workspace\|multi-module build>", text)
        assert grep(r"JUnit/TestNG", text)


def test_coverage_delta_re_derives_java_discovery():
    delta = DELTA_SKILL.read_text()
    assert grep(r"coverage_discovery_java\.py", delta)
    assert grep(r"discover_java_modules\(repo_root\)", delta)


def test_reference_file_lists_the_java_discovery_module_and_trigger():
    ref = REFERENCE.read_text()
    assert grep(r"coverage_discovery_java\.py", ref)
    assert grep(r"discover_java_modules\(repo_root\)", ref)


def test_reference_file_records_the_add_a_stack_rules():
    """The two rules #1759/#1765 paid for — a broken build graph is an error,
    an inherited marker is AMBIGUOUS — must be written down where the next
    stack's author will read them, not just in one module's docstring."""
    ref = collapsed(REFERENCE.read_text())
    assert "fourth stack" in ref.lower()
    # Both rules wrap across lines in the source, so compare collapsed text.
    assert "is a `discovery_error`, never a classification" in ref
    assert "never `TEST` and never `NOT_TEST`" in ref
