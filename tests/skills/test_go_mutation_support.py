"""Doc-shape contract for Go mutation testing support (epic #443, issue
#434). A Go project must get an actionable path — go-mutesting in advisory
mode plus the go test -fuzz complement — never a bare "no tool installed".

Ported from tests/skills/go_mutation_support_tests.bats (issue #674).
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, grep, section

DETECTION = (
    PLUGIN_ROOT / "skills" / "mutation-testing" / "references" / "tool-detection.md"
)
GO_KB = (
    PLUGIN_ROOT
    / "skills"
    / "mutation-testing"
    / "references"
    / "languages"
    / "go-go-mutesting.md"
)
SKILL = PLUGIN_ROOT / "skills" / "mutation-testing" / "SKILL.md"


# --- tool-detection.md: Go row in the ecosystem router ----------------------


def test_tool_detection_row_has_a_go_entry_naming_go_mutesting():
    text = DETECTION.read_text()
    assert grep(r"go-mutesting", text, ignore_case=True)
    assert grep(r"\| *Go *\|", text)


def test_tool_detection_go_detection_keys_on_go_mod():
    assert "go.mod" in DETECTION.read_text()


# --- languages/go-go-mutesting.md: install / run / advisory / fuzz ----------


def test_go_go_mutesting_documents_the_go_mutesting_install_command():
    assert grep(r"go install .*go-mutesting", GO_KB.read_text())


def test_go_go_mutesting_documents_the_go_mutesting_run_command():
    assert grep(r"go-mutesting \./\.\.\.", GO_KB.read_text())


def test_go_go_mutesting_marks_go_mutesting_advisory_only():
    assert grep(r"advisory", GO_KB.read_text(), ignore_case=True)


def test_go_go_mutesting_documents_the_go_test_fuzz_complement():
    assert "go test -fuzz" in GO_KB.read_text()


def test_go_go_mutesting_machine_readable_example_carries_advisory_true():
    # The schema mapping section must show the Go envelope with advisory
    # true so downstream callers warn rather than halt.
    assert grep(r'"advisory": *true', GO_KB.read_text())


# --- SKILL.md: Step 1 detection + advisory mode -----------------------------


def test_mutation_testing_skill_step_1_detection_names_go_mod_go_mutesting():
    body = section(
        SKILL.read_text(),
        r"^## Step 1: Detect",
        boundary_pattern=r"^## Step 1b",
        include_start_line=False,
    )
    assert grep(r"go-mutesting", body, ignore_case=True)
    assert grep(r"go\.mod", body, ignore_case=True)


def test_mutation_testing_skill_advisory_mode_is_documented_as_non_blocking():
    text = SKILL.read_text()
    assert grep(r"advisory", text, ignore_case=True)
    # advisory: true must appear so orchestrated workflows know not to halt.
    assert grep(
        r'"advisory": *true|advisory.*does not block|does not block.*advisory|warn, do not block',
        text,
    )


def test_mutation_testing_skill_documents_the_fuzz_complement_for_go():
    assert "go test -fuzz" in SKILL.read_text()
