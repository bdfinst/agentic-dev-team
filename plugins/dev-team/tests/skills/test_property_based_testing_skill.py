"""Tests for skills/property-based-testing/SKILL.md's procedure and its thin
dispatch helper, scripts/detect_and_dispatch.py (#2190, Step 4.2).

Covers: (1) SKILL.md's frontmatter identity and user-invocability, (2) a
structural check that SKILL.md points at project-init's real stack-detection
entry point rather than re-deriving detection, and that the dispatch script
itself carries no filesystem-signal re-implementation, (3) the two
unsupported-language message fixtures (detection failed/returned nothing ->
"unknown"; a real but unsupported language -> that language's name), each
asserted against its own exact expected string with no file written, and
(4) that the mutation-testing follow-up is documented as a recommendation,
never an auto-run step.

project-init's own stack-detection tests (tests/skills/
test_project_init_stack_detection.py) are read-only reuse here -- this file
does not duplicate them, per the plan's "existing project-init stack-
detection tests still pass unmodified" requirement.
"""

from __future__ import annotations

import sys

from skill_doc_helpers import PLUGIN_ROOT, collapsed, frontmatter, grep, section

SKILL_DIR = PLUGIN_ROOT / "skills" / "property-based-testing"
SKILL = SKILL_DIR / "SKILL.md"
SCRIPTS_DIR = SKILL_DIR / "scripts"
PROJECT_INIT_SKILL = PLUGIN_ROOT / "skills" / "project-init" / "SKILL.md"

sys.path.insert(0, str(SCRIPTS_DIR))

from detect_and_dispatch import (
    SUPPORTED_LANGUAGES,
    is_supported,
    main,
    unsupported_language_message,
)


def _text() -> str:
    return SKILL.read_text()


def _dispatch_source() -> str:
    return (SCRIPTS_DIR / "detect_and_dispatch.py").read_text()


# --- frontmatter identity ----------------------------------------------------


def test_frontmatter_names_the_skill_property_based_testing():
    assert grep(r"^name: property-based-testing$", frontmatter(_text()))


def test_skill_is_user_invocable_worker():
    fm = frontmatter(_text())
    assert grep(r"^role: worker$", fm)
    assert grep(r"^user-invocable: true$", fm)


# --- reuses project-init's real detection entry point, never re-derives -----


def test_skill_references_project_inits_own_stack_detection_step():
    text = _text()
    assert "project-init/SKILL.md" in text
    assert grep(r"Step 1: Detect the stack", collapsed(text))


def test_skill_states_reuse_rather_than_re_derive():
    text = _text()
    assert grep(r"reuse|reuses", text, ignore_case=True)
    assert grep(r"never re-implement|re-derive", text, ignore_case=True)


def test_dispatch_script_does_not_reimplement_filesystem_detection_signals():
    # The thin dispatch script decides support from an already-detected
    # language string -- it must not itself probe manifest files the way
    # project-init's Step 1 does.
    source = _dispatch_source()
    for signal in ("package.json", "pyproject.toml", "*.csproj", "pom.xml", "os.path"):
        assert signal not in source, (
            f"detect_and_dispatch.py must not re-implement detection signal: {signal}"
        )


def test_project_init_still_owns_the_manifest_signal_table():
    # Structural sanity: the signals the dispatch script must NOT duplicate
    # do live in project-init/SKILL.md's own detection section.
    detection_section = section(
        PROJECT_INIT_SKILL.read_text(), r"^### Step 1: Detect the stack"
    )
    for signal in ("package.json", "pyproject.toml"):
        assert signal in detection_section


# --- unsupported/undetected language message fixtures -----------------------


def test_supported_languages_are_exactly_python_and_js_ts():
    assert SUPPORTED_LANGUAGES == ("Python", "JavaScript/TypeScript")
    assert is_supported("Python")
    assert is_supported("JavaScript/TypeScript")
    assert not is_supported("Go")
    assert not is_supported(None)


def test_detection_failed_message_interpolates_the_literal_word_unknown():
    message = unsupported_language_message(None)
    assert message == (
        "Unsupported language: unknown — supported: Python, JavaScript/TypeScript."
    )


def test_unsupported_but_detected_language_interpolates_its_name():
    for language in ("Go", "C#"):
        message = unsupported_language_message(language)
        assert message == (
            f"Unsupported language: {language} — supported: Python, JavaScript/TypeScript."
        )


def test_cli_detection_failed_prints_unknown_message_writes_no_file(tmp_path, capsys):
    exit_code = main([])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert captured.out.strip() == (
        "Unsupported language: unknown — supported: Python, JavaScript/TypeScript."
    )
    assert list(tmp_path.iterdir()) == []


def test_cli_unsupported_detected_language_prints_its_name_writes_no_file(
    tmp_path, capsys
):
    exit_code = main(["--language", "Go"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert captured.out.strip() == (
        "Unsupported language: Go — supported: Python, JavaScript/TypeScript."
    )
    assert list(tmp_path.iterdir()) == []


def test_cli_supported_language_exits_zero_and_names_its_dispatch_target():
    exit_code = main(["--language", "Python"])
    assert exit_code == 0

    exit_code = main(["--language", "JavaScript/TypeScript"])
    assert exit_code == 0


# --- mutation-testing follow-up is documentation only, never auto-run ------


def test_documents_mutation_testing_recommendation_not_auto_run():
    text = _text()
    assert "/mutation-testing" in text
    assert grep(
        r"never (invoke|auto-run|run)|not auto-run|does not invoke",
        text,
        ignore_case=True,
    )


def test_documents_javascript_dispatch_via_step_4_3_reference():
    text = _text()
    assert "references/languages/javascript.md" in text
    assert grep(r"fast-check", text, ignore_case=True)
