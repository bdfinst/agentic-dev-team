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
