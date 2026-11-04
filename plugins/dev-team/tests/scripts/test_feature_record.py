"""Unit tests for scripts/feature_record.py (#2275).

Behavioural: plan text in, the record (or CLI output and exit code) out.
Fixtures live in tests/scripts/fixtures/feature_record/.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_SCRIPTS = _REPO_ROOT / "plugins" / "dev-team" / "scripts"
sys.path.insert(0, str(_SCRIPTS))
sys.path.insert(0, str(_SCRIPTS / "lib"))

import feature_record
import plan_parse

FIXTURES = Path(__file__).parent / "fixtures" / "feature_record"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _run(argv: list[str], capsys) -> tuple[int, str, str]:
    code = feature_record.main(argv)
    out, err = capsys.readouterr()
    return code, out, err


# ---------------------------------------------------------------------------
# build_record: the shape
# ---------------------------------------------------------------------------

EXPECTED_COMPLETE = {
    "schema": 1,
    "plan": {
        "path": "plans/sample.md",
        "status": "approved",
        "criteria": [
            {"id": "AC1", "text": "The parser reads the input"},
            {"id": "AC2", "text": "The builder writes the output"},
        ],
        "slices": [
            {
                "number": "1",
                "title": "Parse",
                "scenarios": ["the parser reads a line"],
                "step_ids": ["1.1"],
            },
            {
                "number": "2",
                "title": "Build",
                "scenarios": ["the builder writes a file", "the builder handles sizes"],
                "step_ids": ["2.1"],
            },
        ],
        "covers": [
            {"step": "1.1", "criteria": ["AC1"]},
            {"step": "2.1", "criteria": ["AC2"]},
        ],
        "unknown_covers": [],
        "blockers": {"open": [], "resolved": []},
    },
    "spec": {
        "source": "https://example.test/issues/1",
        "loaded": False,
        "reason": "url-not-fetched",
        "sections": [],
    },
    "build_progress": {
        "legacy": False,
        "items": [
            {
                "kind": "slice",
                "id": "1",
                "header": "Slice 1: Parse",
                "done": True,
                "commit_backed": None,
            },
            {
                "kind": "slice",
                "id": "2",
                "header": "Slice 2: Build",
                "done": False,
                "commit_backed": None,
            },
        ],
    },
    "applicability": {
        "criterion_coverage": "applies",
        "reason": None,
        "commit_evidence": "not-evaluated",
    },
}


def test_the_record_of_a_complete_plan_has_every_part():
    record = feature_record.build_record(
        _fixture("plan_complete.md"), plan_path="plans/sample.md"
    )
    assert record == EXPECTED_COMPLETE


def test_the_record_is_json_serialisable():
    record = feature_record.build_record(_fixture("plan_complete.md"))
    assert json.loads(json.dumps(record)) == record


def test_unknown_covers_are_listed_once_in_first_seen_order():
    md = _fixture("plan_complete.md").replace(
        "**Covers**: AC1", "**Covers**: AC1, AC9, AC8, AC9"
    )
    plan = feature_record.build_record(md)["plan"]
    assert plan["unknown_covers"] == ["AC9", "AC8"]
    assert plan["covers"][0] == {"step": "1.1", "criteria": ["AC1", "AC9", "AC8"]}


def test_a_plan_without_covers_is_not_applicable_with_a_reason():
    md = _fixture("plan_complete.md").replace("**Covers**", "**Notes**")
    applicability = feature_record.build_record(md)["applicability"]
    assert applicability["criterion_coverage"] == "not-applicable"
    assert applicability["reason"]


def test_a_plan_without_a_build_progress_section_is_legacy():
    record = feature_record.build_record("# Title\n\n- [ ] a thing\n")
    assert record["build_progress"]["legacy"] is True
    assert [i["header"] for i in record["build_progress"]["items"]] == ["a thing"]


def test_a_slice_heading_inside_a_fence_does_not_start_a_slice():
    md = "### Slice 1: Real\n\n```text\n### Slice 2: Fake\n```\n"
    assert [s["number"] for s in feature_record.build_record(md)["plan"]["slices"]] == [
        "1"
    ]


def test_slices_end_at_the_next_heading_so_build_progress_is_not_a_slice():
    md = _fixture("plan_complete.md")
    ours = [s["number"] for s in feature_record.build_record(md)["plan"]["slices"]]
    theirs = [sid for sid, _t, _g in plan_parse.slice_gherkin_blocks(md.splitlines())]
    assert ours == theirs == ["1", "2"]


# ---------------------------------------------------------------------------
# The spec part
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line, expected",
    [
        ("**Spec**: https://example.test/issues/1", "https://example.test/issues/1"),
        ("**Spec**: docs/specs/x.md", "docs/specs/x.md"),
        ("**Spec**: `docs/specs/x.md`", "docs/specs/x.md"),
        ("**Spec**: [the spec](docs/specs/x.md)", "docs/specs/x.md"),
        ("**Spec**: [issue](https://example.test/i/1)", "https://example.test/i/1"),
        ("**Spec**: docs/specs/x.md (draft)", "docs/specs/x.md"),
        ("**Spec:** docs/specs/x.md", "docs/specs/x.md"),
    ],
)
def test_spec_reference_reads_the_spec_line(line, expected):
    assert feature_record.spec_reference(f"# Plan\n\n{line}\n\n## Goal\n") == expected


@pytest.mark.parametrize(
    "text",
    [
        "# Plan\n\n## Goal\n\n**Spec**: docs/specs/x.md\n",  # after the header
        "# Plan\n\n```\n**Spec**: docs/specs/x.md\n```\n",  # inside a fence
        "# Plan\n\n**Spec**:\n",  # no value
        "# Plan\n",
        "",
    ],
)
def test_spec_reference_is_none_when_the_header_names_no_spec(text):
    assert feature_record.spec_reference(text) is None


def test_a_plan_with_no_spec_line_has_a_null_spec_part():
    assert feature_record.build_record(_fixture("plan_no_spec_line.md"))["spec"] is None


def test_a_loaded_spec_lists_its_sections_outside_fences():
    spec = _fixture("spec_sample.md") + "\n```\n## Not a section\n```\n### Deeper\n"
    part = feature_record.build_record("# P\n", spec_text=spec, spec_source="s.md")[
        "spec"
    ]
    assert part == {
        "source": "s.md",
        "loaded": True,
        "reason": None,
        "sections": [
            "## Intent Description",
            "## Architecture Specification",
            "## Acceptance Criteria",
        ],
    }


def test_spec_source_overrides_the_plan_line_in_the_record():
    part = feature_record.build_record(
        _fixture("plan_complete.md"), spec_text="x", spec_source="mine.md"
    )["spec"]
    assert part["source"] == "mine.md"


# ---------------------------------------------------------------------------
# The view command
# ---------------------------------------------------------------------------


def test_view_prints_one_json_document_with_every_part(capsys):
    plan = FIXTURES / "plan_complete.md"
    code, out, _err = _run(["view", str(plan)], capsys)
    assert code == 0
    document = json.loads(out)
    assert set(document) == {
        "schema",
        "plan",
        "spec",
        "build_progress",
        "applicability",
    }
    assert document["schema"] == 1
    assert document["plan"]["path"] == str(plan)


def test_a_spec_path_overrides_the_plans_spec_line(capsys):
    plan = FIXTURES / "plan_complete.md"  # its Spec line is a URL
    spec = FIXTURES / "spec_sample.md"
    code, out, _err = _run(["view", str(plan), "--spec", str(spec)], capsys)
    assert code == 0
    part = json.loads(out)["spec"]
    assert part["source"] == str(spec)
    assert part["loaded"] is True
    assert part["sections"][0] == "## Intent Description"


def test_an_explicit_spec_path_that_cannot_be_read_is_an_input_error(capsys):
    missing = str(FIXTURES / "no-such-spec.md")
    code, out, err = _run(
        ["view", str(FIXTURES / "plan_complete.md"), "--spec", missing], capsys
    )
    assert code == 2
    assert out == ""
    assert missing in err


def test_a_spec_line_naming_a_missing_local_file_is_recorded_not_an_error(capsys):
    plan = FIXTURES / "plan_local_spec_missing.md"
    code, out, _err = _run(["view", str(plan)], capsys)
    assert code == 0
    assert json.loads(out)["spec"] == {
        "source": "docs/specs/missing.md",
        "loaded": False,
        "reason": "not-found",
        "sections": [],
    }


def test_a_spec_url_is_recorded_and_not_fetched(capsys):
    code, out, _err = _run(["view", str(FIXTURES / "plan_complete.md")], capsys)
    assert code == 0
    part = json.loads(out)["spec"]
    assert (part["loaded"], part["reason"]) == (False, "url-not-fetched")


def test_a_local_spec_is_found_relative_to_the_plans_repository(tmp_path, capsys):
    (tmp_path / "docs" / "specs").mkdir(parents=True)
    (tmp_path / "plans").mkdir()
    (tmp_path / "docs" / "specs" / "x.md").write_text(_fixture("spec_sample.md"))
    plan = tmp_path / "plans" / "1-x.md"
    plan.write_text("# P\n\n**Spec**: docs/specs/x.md\n")
    code, out, _err = _run(["view", str(plan)], capsys)
    part = json.loads(out)["spec"]
    assert code == 0
    assert (part["source"], part["loaded"]) == ("docs/specs/x.md", True)
    assert "## Acceptance Criteria" in part["sections"]


def test_an_unreadable_local_spec_is_recorded_as_not_found(tmp_path, capsys):
    (tmp_path / "docs" / "specs").mkdir(parents=True)
    (tmp_path / "docs" / "specs" / "x.md").write_bytes(b"\xff\xfe\x00bad")
    plan = tmp_path / "1-x.md"
    plan.write_text("# P\n\n**Spec**: docs/specs/x.md\n")
    code, out, _err = _run(["view", str(plan)], capsys)
    assert code == 0
    assert json.loads(out)["spec"]["reason"] == "not-found"


# ---------------------------------------------------------------------------
# Input errors: always exit 2 and name the path
# ---------------------------------------------------------------------------


def _bad_path(kind: str, tmp_path: Path) -> Path:
    if kind == "missing":
        return tmp_path / "missing.md"
    if kind == "directory":
        return tmp_path
    path = tmp_path / "binary.md"
    path.write_bytes(b"# Plan\n\xff\xfe\xfa not utf-8\n")
    return path


@pytest.mark.parametrize("kind", ["missing", "directory", "non-utf8"])
def test_an_unreadable_plan_path_is_an_input_error_that_names_it(
    kind, tmp_path, capsys
):
    path = _bad_path(kind, tmp_path)
    code, out, err = _run(["view", str(path)], capsys)
    assert code == 2
    assert out == ""
    assert str(path) in err


def test_the_script_exits_with_the_code_main_returns(tmp_path):
    script = _SCRIPTS / "feature_record.py"
    ok = subprocess.run(
        [sys.executable, str(script), "view", str(FIXTURES / "plan_complete.md")],
        capture_output=True,
        text=True,
        check=False,
    )
    bad = subprocess.run(
        [sys.executable, str(script), "view", str(tmp_path / "nope.md")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert ok.returncode == 0 and json.loads(ok.stdout)["schema"] == 1
    assert bad.returncode == 2 and str(tmp_path / "nope.md") in bad.stderr


# ---------------------------------------------------------------------------
# Totality: build_record never raises
# ---------------------------------------------------------------------------

_ONE_MB = 1_000_000


@pytest.mark.parametrize(
    "text",
    [
        "",
        "one line",
        "\x00\xff￾### Slice 1: \x00\n```\n- [x] \x00\n**Covers**: \x00\n",
        "### Slice 1: " + "x" * _ONE_MB,
        "- [ ] item\n" * (_ONE_MB // 11),
        "## Acceptance Criteria\n" + "- AC1 same\n" * 50_000,
        "```gherkin\n" * 1000,
        "**Open blocker**: Slice 1 - " + " " * 5000 + "x",
    ],
    ids=[
        "empty",
        "one-line",
        "binary-ish",
        "1mb-heading",
        "1mb-items",
        "dup-ids",
        "fences",
        "wide",
    ],
)
def test_build_record_is_total(text):
    record = feature_record.build_record(text, spec_text=text, plan_path=None)
    assert record["schema"] == 1
    assert json.dumps(record)
    assert isinstance(feature_record.violations(record), list)
    assert isinstance(feature_record.plan_violations(text, spec_text=text), list)


# ---------------------------------------------------------------------------
# The pinned copy table (plans/2275-feature-record-validator.md, "Refusal copy
# (pinned)"). Written out here on purpose: the plan file is not committed.
# ---------------------------------------------------------------------------

PINNED_COPY = {
    "ac-no-scenario": {
        "what": '<AC id> "<criterion text, 60 chars>" has no scenario: no step names it, or its covering slices have none. [ac-no-scenario]',
        "why": "A criterion with no scenario has no behavior that proves it.",
        "how": 'Add "**Covers**: <AC id>" to a step, and a Scenario: under **Behavior:** in that step\'s slice.',
    },
    "scenario-no-step": {
        "what": "Slice <n> has a scenario and no step heading. [scenario-no-step]",
        "why": "A scenario with no step is behavior nobody is told to build.",
        "how": 'Add a "#### Step <n>.1: <title>" heading under **Steps:** in Slice <n>.',
    },
    "closed-slice-open-blocker": {
        "what": "Slice <n> is ticked done while an open blocker names it. [closed-slice-open-blocker]",
        "why": "A critic blocker means the slice is not done.",
        "how": 'Resolve the blocker and add "**Resolved blocker**: Slice <n> - <text>" under ## Plan Review Summary, or untick Slice <n> under ## Build Progress.',
    },
    "spec-missing-section": {
        "what": 'The spec has no "<heading>" section, or it is empty. [spec-missing-section]',
        "why": "A plan built on an incomplete spec has no intent or criteria to check against.",
        "how": 'Add "<heading>" with at least one line of text.',
    },
    "tick-without-commit": {
        "what": "Step <id> is ticked done and no commit on this branch backs it. [tick-without-commit]",
        "why": "A tick with no commit claims work the history does not show.",
        "how": "Commit the step (touching <declared files>), or untick it under ## Build Progress.",
    },
}


def test_every_copy_row_matches_the_pinned_table():
    assert feature_record.COPY == PINNED_COPY


def test_make_violation_fills_the_pinned_copy():
    found = feature_record.make_violation(
        "ac-no-scenario", "AC3", ac_id="AC3", text="The reporter prints a summary"
    )
    assert found == {
        "id": "ac-no-scenario",
        "subject": "AC3",
        "what": 'AC3 "The reporter prints a summary" has no scenario: no step names it, or its covering slices have none. [ac-no-scenario]',
        "why": "A criterion with no scenario has no behavior that proves it.",
        "how": 'Add "**Covers**: AC3" to a step, and a Scenario: under **Behavior:** in that step\'s slice.',
    }


def test_make_violation_names_the_slice_in_every_place_it_appears():
    found = feature_record.make_violation("closed-slice-open-blocker", "Slice 2", n="2")
    assert found["what"] == (
        "Slice 2 is ticked done while an open blocker names it. [closed-slice-open-blocker]"
    )
    assert found["how"] == (
        'Resolve the blocker and add "**Resolved blocker**: Slice 2 - <text>" under '
        "## Plan Review Summary, or untick Slice 2 under ## Build Progress."
    )


def test_make_violation_cuts_the_criterion_text_at_60_characters():
    found = feature_record.make_violation(
        "ac-no-scenario", "AC1", ac_id="AC1", text="x" * 59 + "yz"
    )
    assert f'AC1 "{"x" * 59}y" has no scenario' in found["what"]


def test_make_violation_does_not_expand_a_placeholder_inside_a_value():
    found = feature_record.make_violation(
        "ac-no-scenario", "AC1", ac_id="AC1", text="handle <n> items and <AC id>"
    )
    assert 'AC1 "handle <n> items and <AC id>" has no scenario' in found["what"]


# ---------------------------------------------------------------------------
# violations: one failing and one passing fixture per invariant
# ---------------------------------------------------------------------------


def _found(text: str) -> list[tuple[str, str]]:
    return [
        feature_record.violation_key(v) for v in feature_record.plan_violations(text)
    ]


def test_a_plan_with_every_invariant_met_has_no_violation(capsys):
    assert _found(_fixture("plan_complete.md")) == []
    code, out, err = _run(["check", str(FIXTURES / "plan_complete.md")], capsys)
    assert code == 0
    assert json.loads(out)["violations"] == []
    assert err.strip() == "0 violations, 0 unverifiable"


def test_a_criterion_no_covers_line_names_is_a_violation(capsys):
    plan = FIXTURES / "plan_uncovered_criterion.md"
    assert _found(plan.read_text()) == [("ac-no-scenario", "AC2")]
    code, out, err = _run(["check", str(plan)], capsys)
    assert code == 1
    assert [v["subject"] for v in json.loads(out)["violations"]] == ["AC2"]
    assert err.strip() == "1 violations, 0 unverifiable"


def test_a_criterion_whose_covering_slice_has_no_scenario_is_a_violation():
    text = _fixture("plan_covering_slice_no_scenario.md")
    assert _found(text) == [("ac-no-scenario", "AC3")]


def test_a_criterion_covered_in_two_slices_needs_only_one_to_hold_a_scenario():
    text = _fixture("plan_covering_slice_no_scenario.md").replace(
        "**Covers**: AC2", "**Covers**: AC2, AC3"
    )
    assert _found(text) == []


def test_a_covers_id_that_is_not_a_criterion_is_ignored_and_listed():
    text = _fixture("plan_complete.md").replace(
        "**Covers**: AC1", "**Covers**: AC1, AC9"
    )
    assert _found(text) == []
    assert feature_record.build_record(text)["plan"]["unknown_covers"] == ["AC9"]


def test_a_typo_in_a_covers_id_leaves_the_real_criterion_unnamed():
    text = _fixture("plan_complete.md").replace("**Covers**: AC2", "**Covers**: AC22")
    assert _found(text) == [("ac-no-scenario", "AC2")]
    assert feature_record.build_record(text)["plan"]["unknown_covers"] == ["AC22"]


def test_a_plan_with_no_covers_line_is_not_checked_for_coverage():
    text = _fixture("plan_complete.md").replace("**Covers**", "**Notes**")
    record = feature_record.build_record(text)
    assert record["applicability"]["criterion_coverage"] == "not-applicable"
    assert feature_record.violations(record) == []


def test_a_covers_line_inside_a_fence_does_not_make_coverage_apply():
    text = (
        _fixture("plan_complete.md")
        .replace("**Covers**: AC1\n", "```\n**Covers**: AC1\n```\n")
        .replace("**Covers**: AC2\n", "")
    )
    record = feature_record.build_record(text)
    assert record["applicability"]["criterion_coverage"] == "not-applicable"


def test_a_slice_with_a_scenario_and_no_step_is_a_violation(capsys):
    plan = FIXTURES / "plan_scenario_no_step.md"
    assert _found(plan.read_text()) == [("scenario-no-step", "Slice 2")]
    assert _run(["check", str(plan)], capsys)[0] == 1


def test_a_slice_with_a_scenario_and_a_step_passes():
    assert ("scenario-no-step", "Slice 1") not in _found(_fixture("plan_complete.md"))


def test_a_slice_with_a_step_and_no_scenario_is_not_a_scenario_no_step_violation():
    text = _fixture("plan_covering_slice_no_scenario.md")
    assert not [k for k in _found(text) if k[0] == "scenario-no-step"]


def test_a_closed_slice_with_an_open_blocker_is_a_violation(capsys):
    plan = FIXTURES / "plan_closed_slice_open_blocker.md"
    assert _found(plan.read_text()) == [("closed-slice-open-blocker", "Slice 1")]
    code, out, _err = _run(["check", str(plan)], capsys)
    assert code == 1
    assert "## Plan Review Summary" in json.loads(out)["violations"][0]["how"]


_RESOLVED = "**Resolved blocker**: Slice 1 - missing error path\n"
_OPEN = "**Open blocker**: Slice 1 - missing error path\n"


def _closed(extra: str = "") -> str:
    return _fixture("plan_closed_slice_open_blocker.md").replace(_OPEN, _OPEN + extra)


def test_a_resolved_blocker_with_the_same_slice_and_text_clears_the_slice():
    assert _found(_closed(_RESOLVED)) == []


def test_resolved_matching_ignores_runs_of_whitespace_only():
    assert (
        _found(_closed("**Resolved blocker**: Slice 1 - missing   error  path\n")) == []
    )
    assert _found(_closed("**Resolved blocker**: Slice 1 - Missing error path\n")) == [
        ("closed-slice-open-blocker", "Slice 1")
    ]


def test_a_resolved_blocker_for_another_slice_or_text_does_not_clear_it():
    other_slice = "**Resolved blocker**: Slice 2 - missing error path\n"
    other_text = "**Resolved blocker**: Slice 1 - something else\n"
    expected = [("closed-slice-open-blocker", "Slice 1")]
    assert _found(_closed(other_slice)) == expected
    assert _found(_closed(other_text)) == expected


def test_one_resolved_blocker_cancels_only_one_of_two_open_blockers():
    assert _found(_closed(_OPEN + _RESOLVED)) == [
        ("closed-slice-open-blocker", "Slice 1")
    ]
    assert _found(_closed(_OPEN + _RESOLVED + _RESOLVED)) == []


def test_two_open_blockers_on_one_slice_raise_one_violation():
    assert _found(_closed(_OPEN)) == [("closed-slice-open-blocker", "Slice 1")]


def test_an_open_slice_with_an_open_blocker_passes():
    text = _fixture("plan_closed_slice_open_blocker.md").replace(
        "- [x] Slice 1", "- [ ] Slice 1"
    )
    assert _found(text) == []


def test_a_blocker_naming_a_slice_that_does_not_exist_is_ignored():
    text = _fixture("plan_closed_slice_open_blocker.md").replace(
        "**Open blocker**: Slice 1", "**Open blocker**: Slice 9"
    )
    assert _found(text) == []


def test_a_slice_with_no_build_progress_line_is_not_closed():
    text = _fixture("plan_closed_slice_open_blocker.md")
    text = text[: text.index("## Build Progress")]
    assert _found(text) == []


def test_violations_come_in_invariant_order_then_plan_order():
    text = _fixture("plan_closed_slice_open_blocker.md")
    text = text.replace("**Covers**: AC2\n", "")  # AC2 now uncovered
    start = text.index("#### Step 2.1")
    end = text.index("## Plan Review Summary")
    text = text[:start] + text[end:]  # slice 2 now has no step
    assert _found(text) == [
        ("ac-no-scenario", "AC2"),
        ("scenario-no-step", "Slice 2"),
        ("closed-slice-open-blocker", "Slice 1"),
    ]


def test_inserting_an_unprefixed_criterion_keeps_the_keys_of_existing_violations():
    before = (
        "## Acceptance Criteria\n\n- AC1 covered\n- AC7 not covered\n\n"
        "### Slice 1: S\n\n```gherkin\nScenario: s\n```\n\n"
        "#### Step 1.1: t\n\n**Covers**: AC1\n"
    )
    after = before.replace("- AC7 not", "- a fresh unprefixed one\n- AC7 not")
    assert ("ac-no-scenario", "AC7") in _found(before)
    assert ("ac-no-scenario", "AC7") in _found(after)
    assert _found(after) == [("ac-no-scenario", "AC2"), ("ac-no-scenario", "AC7")]


def test_plan_violations_agrees_with_violations_of_the_record():
    text = _fixture("plan_uncovered_criterion.md")
    assert feature_record.plan_violations(text) == feature_record.violations(
        feature_record.build_record(text)
    )


def test_unverifiable_lists_ticked_items_without_evidence_only_when_evaluated():
    record = feature_record.build_record(_fixture("plan_complete.md"))
    assert feature_record.unverifiable(record) == []
    record["applicability"]["commit_evidence"] = "evaluated"
    record["build_progress"]["items"][0]["commit_backed"] = None
    record["build_progress"]["items"][1]["commit_backed"] = None  # unticked
    assert feature_record.unverifiable(record) == ["1"]
    record["build_progress"]["items"][0]["commit_backed"] = True
    assert feature_record.unverifiable(record) == []


# ---------------------------------------------------------------------------
# check: exit codes
# ---------------------------------------------------------------------------


def test_check_prints_the_violations_unverifiable_and_applicability(capsys):
    code, out, _err = _run(
        ["check", str(FIXTURES / "plan_scenario_no_step.md")], capsys
    )
    document = json.loads(out)
    assert code == 1
    assert set(document) == {"violations", "unverifiable", "applicability"}
    assert set(document["violations"][0]) == {"id", "subject", "what", "why", "how"}
    assert document["applicability"]["criterion_coverage"] == "not-applicable"


@pytest.mark.parametrize("kind", ["missing", "directory", "non-utf8"])
def test_check_exits_2_and_names_an_unreadable_plan(kind, tmp_path, capsys):
    path = _bad_path(kind, tmp_path)
    code, out, err = _run(["check", str(path)], capsys)
    assert (code, out) == (2, "")
    assert str(path) in err


def test_check_exits_2_for_an_explicit_spec_path_that_cannot_be_read(capsys):
    missing = str(FIXTURES / "no-such-spec.md")
    code, _out, err = _run(
        ["check", str(FIXTURES / "plan_complete.md"), "--spec", missing], capsys
    )
    assert code == 2
    assert missing in err


def test_check_with_a_missing_command_is_a_usage_error(capsys):
    with pytest.raises(SystemExit) as raised:
        feature_record.main([])
    assert raised.value.code == 2


def test_a_ticked_build_progress_line_for_a_slice_with_no_heading_is_not_a_closed_slice():
    text = (
        _fixture("plan_closed_slice_open_blocker.md")
        .replace("- [ ] Slice 2: Build", "- [x] Slice 9: Ghost")
        .replace("**Open blocker**: Slice 1", "**Open blocker**: Slice 9")
    )
    assert _found(text) == []


# ---------------------------------------------------------------------------
# spec_violations
# ---------------------------------------------------------------------------

INTENT = "## Intent Description"
ARCH = "## Architecture Specification"
CRITERIA = "## Acceptance Criteria"


def _spec_keys(text: str) -> list[tuple[str, str]]:
    return [
        feature_record.violation_key(v) for v in feature_record.spec_violations(text)
    ]


def _without_section(heading: str) -> str:
    """The sample spec with `heading` and its body removed."""
    kept, skipping = [], False
    for line in _fixture("spec_sample.md").splitlines():
        if line.startswith("## "):
            skipping = line.strip() == heading
        if not skipping:
            kept.append(line)
    return "\n".join(kept) + "\n"


def _with_body(heading: str, body: str) -> str:
    """The sample spec with the body of `heading` replaced by `body`."""
    out, skipping = [], False
    for line in _fixture("spec_sample.md").splitlines():
        if line.startswith("## "):
            skipping = line.strip() == heading
            out.append(line)
            if skipping:
                out.append(body)
            continue
        if not skipping:
            out.append(line)
    return "\n".join(out) + "\n"


def test_a_complete_spec_has_no_violation():
    assert feature_record.spec_violations(_fixture("spec_sample.md")) == []


@pytest.mark.parametrize("heading", [INTENT, ARCH, CRITERIA])
def test_a_spec_missing_a_required_section_is_a_violation_naming_it(heading):
    found = feature_record.spec_violations(_without_section(heading))
    assert [(v["id"], v["subject"]) for v in found] == [
        ("spec-missing-section", heading)
    ]
    assert found[0]["what"] == (
        f'The spec has no "{heading}" section, or it is empty. [spec-missing-section]'
    )
    assert found[0]["how"] == f'Add "{heading}" with at least one line of text.'


@pytest.mark.parametrize("heading", [INTENT, ARCH, CRITERIA])
@pytest.mark.parametrize(
    "body",
    [
        "",
        "   ",
        "<!-- placeholder -->",
        "<!-- one -->\n<!-- two -->",
        "<!--\nspread over\nseveral lines\n-->",
        "<!-- unclosed comment swallows the rest",
    ],
    ids=["blank", "spaces", "comment", "two-comments", "multiline-comment", "unclosed"],
)
def test_a_section_with_no_text_outside_comments_is_empty(heading, body):
    assert _spec_keys(_with_body(heading, body)) == [("spec-missing-section", heading)]


@pytest.mark.parametrize(
    "body",
    [
        "- one criterion",
        "Plain text.",
        "<!-- note -->\ntext after a comment",
        "<!--\nmulti\n-->\ntext after a multi-line comment",
        "<!-- note --> text on the same line",
        "```\nonly a code block\n```",
    ],
    ids=["list-item", "text", "after-comment", "after-multiline", "same-line", "fence"],
)
def test_a_section_with_a_list_item_or_text_is_not_empty(body):
    assert _spec_keys(_with_body(CRITERIA, body)) == []


def test_a_heading_with_trailing_text_or_different_case_does_not_match():
    for variant in ("## Acceptance Criteria (v2)", "## acceptance criteria"):
        text = _fixture("spec_sample.md").replace(CRITERIA, variant)
        assert _spec_keys(text) == [("spec-missing-section", CRITERIA)]


def test_surrounding_whitespace_on_a_heading_is_trimmed():
    text = _fixture("spec_sample.md").replace(CRITERIA, CRITERIA + "   ")
    assert _spec_keys(text) == []


def test_a_heading_inside_a_code_fence_does_not_count():
    text = (
        _without_section(CRITERIA)
        + f"\n```\n{CRITERIA}\n- looks like a criterion\n```\n"
    )
    assert _spec_keys(text) == [("spec-missing-section", CRITERIA)]


def test_content_after_the_next_heading_does_not_fill_an_empty_section():
    text = _with_body(INTENT, "").replace(ARCH, "## Notes\n\nSome notes.\n\n" + ARCH)
    assert _spec_keys(text) == [("spec-missing-section", INTENT)]


def test_a_repeated_heading_is_present_when_any_occurrence_has_text():
    text = _with_body(INTENT, "") + f"\n{INTENT}\n\nThe real intent.\n"
    assert _spec_keys(text) == []


def test_every_missing_section_is_reported_in_required_order():
    assert _spec_keys("# Spec\n") == [
        ("spec-missing-section", INTENT),
        ("spec-missing-section", ARCH),
        ("spec-missing-section", CRITERIA),
    ]


@pytest.mark.parametrize(
    "text",
    ["", "x", "\x00\xff￾" * 1000, "<!--" * 250_000, "-->" * 300_000, "## " * 100_000],
    ids=[
        "empty",
        "one-char",
        "binary-ish",
        "many-openers",
        "many-closers",
        "many-headings",
    ],
)
def test_spec_violations_is_total(text):
    assert isinstance(feature_record.spec_violations(text), list)


# ---------------------------------------------------------------------------
# The spec in the plan-level checks
# ---------------------------------------------------------------------------


def _local_spec_layout(tmp_path: Path, spec_text: str) -> Path:
    (tmp_path / "docs" / "specs").mkdir(parents=True)
    (tmp_path / "plans").mkdir()
    (tmp_path / "docs" / "specs" / "x.md").write_text(spec_text)
    plan = tmp_path / "plans" / "1-x.md"
    plan.write_text("# P\n\n**Spec**: docs/specs/x.md\n")
    return plan


def test_a_plan_naming_an_incomplete_local_spec_reports_the_spec_violation(
    tmp_path, capsys
):
    plan = _local_spec_layout(tmp_path, _without_section(INTENT))
    code, out, err = _run(["check", str(plan)], capsys)
    assert code == 1
    assert [(v["id"], v["subject"]) for v in json.loads(out)["violations"]] == [
        ("spec-missing-section", INTENT)
    ]
    assert err.strip() == "1 violations, 0 unverifiable"


def test_a_plan_naming_a_complete_local_spec_is_clean(tmp_path, capsys):
    plan = _local_spec_layout(tmp_path, _fixture("spec_sample.md"))
    assert _run(["check", str(plan)], capsys)[0] == 0


def test_an_explicit_spec_path_is_checked_too(tmp_path, capsys):
    spec = tmp_path / "s.md"
    spec.write_text(_without_section(ARCH))
    code, out, _err = _run(
        ["check", str(FIXTURES / "plan_complete.md"), "--spec", str(spec)], capsys
    )
    assert code == 1
    assert json.loads(out)["violations"][0]["subject"] == ARCH


def test_a_spec_that_is_not_loaded_is_not_checked(capsys):
    code, out, _err = _run(
        ["check", str(FIXTURES / "plan_local_spec_missing.md")], capsys
    )
    assert (code, json.loads(out)["violations"]) == (0, [])


def test_plan_violations_checks_a_spec_only_when_given_one():
    plan = _fixture("plan_complete.md")
    incomplete = _without_section(CRITERIA)
    assert feature_record.plan_violations(plan) == []
    assert feature_record.plan_violations(plan, None) == []
    assert [v["subject"] for v in feature_record.plan_violations(plan, incomplete)] == [
        CRITERIA
    ]


def test_plan_and_spec_violations_are_reported_together():
    plan = _fixture("plan_uncovered_criterion.md")
    found = feature_record.plan_violations(plan, _without_section(INTENT))
    assert [feature_record.violation_key(v) for v in found] == [
        ("ac-no-scenario", "AC2"),
        ("spec-missing-section", INTENT),
    ]


# ---------------------------------------------------------------------------
# introduced
# ---------------------------------------------------------------------------


def _v(violation_id: str, subject: str) -> dict[str, str]:
    return {"id": violation_id, "subject": subject, "what": "", "why": "", "how": ""}


A = _v("scenario-no-step", "Slice 1")
B = _v("scenario-no-step", "Slice 2")
C = _v("ac-no-scenario", "AC1")


@pytest.mark.parametrize(
    "before, after, expected",
    [
        ([A], [A, B], [B]),  # only the other one is introduced
        ([A], [], []),  # repair
        ([A], [A], []),  # identical
        ([A], [B], [B]),  # swap
        ([], [A], [A]),  # new
        ([], [], []),
        ([A, B], [B, C, A], [C]),
        ([A], [A, B, B], [B]),  # no duplicates in the result
    ],
    ids=["extra", "repair", "identical", "swap", "new", "none", "mixed", "dedupe"],
)
def test_introduced_returns_only_violations_whose_key_is_new(before, after, expected):
    assert feature_record.introduced(before, after) == expected


def test_a_violation_is_the_same_key_when_only_its_wording_differs():
    reworded = dict(A, what="different words")
    assert feature_record.introduced([A], [reworded]) == []


def test_introduced_compares_subject_as_well_as_id():
    same_id_other_subject = _v("scenario-no-step", "Slice 3")
    assert feature_record.introduced([A], [same_id_other_subject]) == [
        same_id_other_subject
    ]


def test_a_write_that_fixes_one_violation_and_adds_another_introduces_only_the_new_one():
    before = feature_record.plan_violations(_fixture("plan_scenario_no_step.md"))
    after = feature_record.plan_violations(_fixture("plan_uncovered_criterion.md"))
    assert [
        feature_record.violation_key(v)
        for v in feature_record.introduced(before, after)
    ] == [("ac-no-scenario", "AC2")]


def test_an_unclosed_comment_in_one_occurrence_of_a_heading_does_not_hide_the_next():
    text = _with_body(INTENT, "<!-- never closed") + f"\n{INTENT}\n\nThe real intent.\n"
    assert _spec_keys(text) == []
