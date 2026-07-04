"""#251 — /build must gate on a JS bootstrap step (Step 1.5) that invokes
project-init when a JS-flavored plan has no package.json, and skips
silently otherwise. Documentation gate over the skill prose.

Ported from tests/skills/build_js_project_init_gate_tests.bats (issue #674).
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, grep, section

BUILD = PLUGIN_ROOT / "skills" / "build" / "SKILL.md"


def _text() -> str:
    return BUILD.read_text()


def _step_1_5_section() -> str:
    return section(
        _text(),
        r"^### 1\.5\. ",
        boundary_pattern=r"^### 2\. ",
        include_start_line=False,
    )


def test_step_1_5_is_documented_as_a_heading():
    assert grep(r"^### 1\.5\. ", _text())


def test_step_1_5_sits_between_find_the_plan_step_1_and_verify_plan_status_step_2():
    lines = _text().splitlines()
    step1 = next((i for i, ln in enumerate(lines) if grep(r"^### 1\. ", ln)), None)
    step15 = next((i for i, ln in enumerate(lines) if grep(r"^### 1\.5\. ", ln)), None)
    step2 = next((i for i, ln in enumerate(lines) if grep(r"^### 2\. ", ln)), None)
    assert step1 is not None and step15 is not None and step2 is not None
    assert step1 < step15
    assert step15 < step2


def test_gate_checks_for_package_json():
    assert "package.json" in _text()


def test_gate_enumerates_js_ts_signals():
    s = _step_1_5_section()
    for sig in (
        ".js",
        ".mjs",
        ".ts",
        ".jsx",
        ".tsx",
        "node",
        "npm",
        "vitest",
        "jest",
        "eslint",
    ):
        assert sig in s, f"missing signal: {sig}"


def test_gate_invokes_project_init_when_bootstrapping():
    assert "project-init" in _step_1_5_section()


def test_gate_skips_silently_when_package_json_exists_or_plan_is_non_js():
    assert grep(r"skip this gate silently", _step_1_5_section(), ignore_case=True)


def test_gate_emits_exactly_one_notice_line_before_bootstrapping():
    assert grep(r"one line", _step_1_5_section(), ignore_case=True)


def test_gate_halts_build_when_project_init_fails():
    s = _step_1_5_section()
    assert grep(r"halt|stop", s, ignore_case=True)
    assert grep(r"fail", s, ignore_case=True)
