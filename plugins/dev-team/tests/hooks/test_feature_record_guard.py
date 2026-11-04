"""Tests for hooks/feature_record_guard.py (#2275, Slice 4).

Step 4.1 covers the path matcher, the payload layer and the no-work fast path;
Step 4.2 the decision (what a write introduces) and its fail-open handling.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

_HOOKS_DIR = Path(__file__).resolve().parents[2] / "hooks"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

_TESTS_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_TESTS_LIB) not in sys.path:
    sys.path.insert(0, str(_TESTS_LIB))

import feature_record_guard as hook  # type: ignore[import-not-found]
from hermetic import hermetic_git_env  # type: ignore[import-not-found]

HOOK_PATH = _HOOKS_DIR / "feature_record_guard.py"


# ---------------------------------------------------------------------------
# matches
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rel_path,kind",
    [
        ("plans/2275-x.md", "plan"),
        ("docs/specs/x.md", "spec"),
        ("docs/specs/x/spec.md", "spec"),
        ("docs/specs/x/plans/p.md", "plan"),
        ("docs/specs/README.md", None),
        ("docs/specs/x/plans/README.md", None),
        ("plans/README.md", None),
        ("plans/notes.txt", None),
        ("src/plans/x.md", None),
        ("src/app.py", None),
        ("docs/specs/x/notes.md", None),
        ("docs/specs/x/plans/deep/p.md", None),
        ("plans/sub/p.md", None),
        ("docs/other/x.md", None),
    ],
)
def test_matches(rel_path: str, kind: str | None) -> None:
    assert hook.matches(rel_path) == kind


# ---------------------------------------------------------------------------
# target_path: resolution against the payload cwd
# ---------------------------------------------------------------------------


def _payload(file_path, tool="Write", cwd=None, **tool_input) -> dict:
    body = {"file_path": file_path, **tool_input}
    payload = {"tool_name": tool, "tool_input": body}
    if cwd is not None:
        payload["cwd"] = str(cwd)
    return payload


def test_target_path_resolves_relative_and_absolute_inside_cwd(tmp_path: Path) -> None:
    relative = hook.target_path(_payload("plans/p.md", cwd=tmp_path))
    absolute = hook.target_path(
        _payload(str(tmp_path / "plans" / "p.md"), cwd=tmp_path)
    )
    assert relative == absolute == (str(tmp_path / "plans" / "p.md"), "plans/p.md")


@pytest.mark.parametrize(
    "file_path",
    ["../plans/p.md", "plans/../../plans/p.md", "/elsewhere/plans/p.md"],
)
def test_target_path_outside_cwd_is_none(tmp_path: Path, file_path: str) -> None:
    assert hook.target_path(_payload(file_path, cwd=tmp_path)) is None


def test_target_path_sibling_directory_with_shared_prefix_is_outside(
    tmp_path: Path,
) -> None:
    work = tmp_path / "work"
    sibling = tmp_path / "work-other" / "plans" / "p.md"
    assert hook.target_path(_payload(str(sibling), cwd=work)) is None


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"tool_input": "plans/p.md"},
        {"tool_input": {}},
        {"tool_input": {"file_path": ""}},
        {"tool_input": {"file_path": 7}},
        {"tool_input": {"file_path": ["plans/p.md"]}},
    ],
)
def test_target_path_without_a_usable_file_path_is_none(payload: dict) -> None:
    assert hook.target_path(payload) is None


# ---------------------------------------------------------------------------
# proposed_text: Write content, Edit applied once, empty before-state
# ---------------------------------------------------------------------------


def _reader(files: dict[str, str]):
    def read_text(path: str) -> str:
        if path not in files:
            raise FileNotFoundError(path)
        return files[path]

    return read_text


def test_write_proposes_its_content_against_the_on_disk_text(tmp_path: Path) -> None:
    abs_path = str(tmp_path / "plans" / "p.md")
    payload = _payload("plans/p.md", cwd=tmp_path, content="new\n")
    assert hook.proposed_text(payload, _reader({abs_path: "old\n"})) == (
        "old\n",
        "new\n",
    )


def test_write_to_a_new_file_has_an_empty_before_state(tmp_path: Path) -> None:
    payload = _payload("plans/p.md", cwd=tmp_path, content="new\n")
    assert hook.proposed_text(payload, _reader({})) == ("", "new\n")


def test_edit_applies_old_to_new_once(tmp_path: Path) -> None:
    abs_path = str(tmp_path / "plans" / "p.md")
    payload = _payload(
        "plans/p.md",
        tool="Edit",
        cwd=tmp_path,
        old_string="- [ ] Step 1.1",
        new_string="- [x] Step 1.1",
    )
    files = {abs_path: "a\n- [ ] Step 1.1\nb\n"}
    assert hook.proposed_text(payload, _reader(files)) == (
        "a\n- [ ] Step 1.1\nb\n",
        "a\n- [x] Step 1.1\nb\n",
    )


def test_edit_may_delete_text_with_an_empty_new_string(tmp_path: Path) -> None:
    abs_path = str(tmp_path / "plans" / "p.md")
    payload = _payload(
        "plans/p.md", tool="Edit", cwd=tmp_path, old_string="drop\n", new_string=""
    )
    assert hook.proposed_text(payload, _reader({abs_path: "keep\ndrop\n"})) == (
        "keep\ndrop\n",
        "keep\n",
    )


def _cannot_judge_cases(tmp_path: Path) -> list[tuple[str, dict, dict[str, str]]]:
    abs_path = str(tmp_path / "plans" / "p.md")
    on_disk = {abs_path: "one\ntwo\ntwo\n"}

    def edit(**fields) -> dict:
        return _payload("plans/p.md", tool="Edit", cwd=tmp_path, **fields)

    return [
        ("old_string absent", edit(old_string="zzz", new_string="x"), on_disk),
        ("old_string twice", edit(old_string="two", new_string="x"), on_disk),
        ("old_string empty", edit(old_string="", new_string="x"), on_disk),
        (
            "replace_all, several matches",
            edit(old_string="two", new_string="x", replace_all=True),
            on_disk,
        ),
        ("Edit on a missing file", edit(old_string="one", new_string="x"), {}),
        ("old_string not text", edit(old_string=3, new_string="x"), on_disk),
        ("new_string missing", edit(old_string="one"), on_disk),
        (
            "Write content not text",
            _payload("plans/p.md", cwd=tmp_path, content=5),
            on_disk,
        ),
        ("Write content missing", _payload("plans/p.md", cwd=tmp_path), on_disk),
        (
            "no file_path",
            {"tool_name": "Write", "tool_input": {"content": "x"}},
            on_disk,
        ),
        (
            "other tool",
            _payload("plans/p.md", tool="Read", cwd=tmp_path, content="x"),
            on_disk,
        ),
    ]


def test_inputs_the_hook_cannot_judge_return_none(tmp_path: Path) -> None:
    for label, payload, files in _cannot_judge_cases(tmp_path):
        assert hook.proposed_text(payload, _reader(files)) is None, label


@pytest.mark.parametrize("error", [PermissionError("no"), IsADirectoryError("dir")])
def test_an_unreadable_existing_file_cannot_be_judged(
    tmp_path: Path, error: OSError
) -> None:
    def unreadable(path: str) -> str:
        raise error

    payload = _payload("plans/p.md", cwd=tmp_path, content="x")
    assert hook.proposed_text(payload, unreadable) is None


def test_a_non_utf8_existing_file_cannot_be_judged(tmp_path: Path) -> None:
    (tmp_path / "plans").mkdir()
    (tmp_path / "plans" / "p.md").write_bytes(b"\xff\xfe\x00bad")
    payload = _payload("plans/p.md", cwd=tmp_path, content="x")
    assert hook.proposed_text(payload, hook._read_text) is None


def test_read_text_keeps_line_endings(tmp_path: Path) -> None:
    path = tmp_path / "p.md"
    path.write_bytes(b"a\r\nb\r\n")
    assert hook._read_text(str(path)) == "a\r\nb\r\n"


# ---------------------------------------------------------------------------
# main: escape hatch and the no-work path
# ---------------------------------------------------------------------------


def _run_main(monkeypatch, capsys, payload: object, env: dict[str, str] | None = None):
    import io

    raw = payload if isinstance(payload, str) else json.dumps(payload)
    monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
    monkeypatch.delenv(hook.ESCAPE_ENV, raising=False)
    for key, value in (env or {}).items():
        monkeypatch.setenv(key, value)
    code = hook.main()
    captured = capsys.readouterr()
    return code, captured.out, captured.err


@pytest.mark.parametrize("raw", ["", "not json", "[1, 2]", "42"])
def test_main_allows_an_unparseable_payload(monkeypatch, capsys, raw: str) -> None:
    assert _run_main(monkeypatch, capsys, raw) == (0, "", "")


def test_main_allows_a_payload_without_file_path(monkeypatch, capsys) -> None:
    assert _run_main(monkeypatch, capsys, {"tool_input": {}}) == (0, "", "")


def test_main_escape_hatch_allows_a_matching_write_with_one_notice(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    payload = _payload("plans/p.md", cwd=tmp_path, content="anything\n")
    code, out, err = _run_main(monkeypatch, capsys, payload, {hook.ESCAPE_ENV: "off"})
    assert (code, out) == (0, "")
    assert err == f"feature record check skipped: {hook.ESCAPE_ENV}=off\n"


def test_main_escape_hatch_is_silent_for_a_path_it_never_checks(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    payload = _payload("src/app.py", cwd=tmp_path, content="x = 1\n")
    result = _run_main(monkeypatch, capsys, payload, {hook.ESCAPE_ENV: "off"})
    assert result == (0, "", "")


# ---------------------------------------------------------------------------
# Fast path: a path outside the matcher does no work (fresh interpreter)
# ---------------------------------------------------------------------------

_WRAPPER = textwrap.dedent(
    """
    import json
    import sys

    sys.path.insert(0, sys.argv[1])
    import feature_record_guard as hook  # imported before the audit hook is armed

    opened = []

    def audit(event, args):
        if event == "open" and args and args[0] not in (0, "<stdin>", "/dev/stdin"):
            opened.append(str(args[0]))

    sys.addaudithook(audit)
    code = hook.main()
    print(json.dumps({"code": code, "opened": opened,
                      "imported": "feature_record" in sys.modules}))
    """
)


def _run_isolated(tmp_path: Path, payload: dict, env: dict[str, str] | None = None):
    wrapper = tmp_path / "wrapper.py"
    wrapper.write_text(_WRAPPER)
    done = subprocess.run(
        [sys.executable, "-I", str(wrapper), str(_HOOKS_DIR)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=env,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_a_path_outside_the_matcher_reads_no_file_and_imports_no_record(
    tmp_path: Path,
) -> None:
    payload = _payload("src/app.py", cwd=tmp_path, content="x = 1\n")
    assert _run_isolated(tmp_path, payload) == {
        "code": 0,
        "opened": [],
        "imported": False,
    }


def test_the_audit_wrapper_sees_a_file_read(tmp_path: Path) -> None:
    """Control: the wrapper does record an open when the hook reads a file."""
    (tmp_path / "plans").mkdir()
    (tmp_path / "plans" / "p.md").write_text("x\n")
    payload = _payload("plans/p.md", cwd=tmp_path, content="y\n")
    result = _run_isolated(tmp_path, payload)
    assert str(tmp_path / "plans" / "p.md") in result["opened"]


def test_top_level_imports_stay_minimal() -> None:
    tree = ast.parse(HOOK_PATH.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert imported == {"__future__", "os", "sys", "stdin_json"}


# ---------------------------------------------------------------------------
# Step 4.2: the decision. Plans are built, not hand-copied, so each case changes
# exactly one fact.
# ---------------------------------------------------------------------------

FIXTURES = Path(__file__).parent / "fixtures" / "feature_record_guard"

DEFAULT_SLICES = (
    {"covers": ("AC1",), "scenarios": 1, "steps": 1},
    {"covers": ("AC2",), "scenarios": 1, "steps": 1},
    {"covers": ("AC3",), "scenarios": 1, "steps": 1},
)


def build_plan(
    slices=DEFAULT_SLICES,
    criteria: int = 3,
    blockers: tuple[str, ...] = (),
    ticked: tuple[int, ...] = (),
    filler: int = 0,
) -> str:
    """A plan in the shape `/plan` writes. `covers` names the criteria the
    slice's first step covers; `steps` and `scenarios` are counts."""
    lines = [
        "# Plan: Sample",
        "",
        "**Status**: approved",
        "**Spec**: https://example.test/issues/1",
        "",
        "## Goal",
        "",
        "The goal paragraph.",
        *[f"Filler sentence {i} keeps the goal long." for i in range(filler)],
        "",
        "## Acceptance Criteria",
        "",
        *[f"- [ ] AC{n} Criterion {n}" for n in range(1, criteria + 1)],
        "",
        "## Slices",
        "",
    ]
    for k, spec in enumerate(slices, start=1):
        lines += [f"### Slice {k}: Part {k}", "", f"**Files:** `f{k}.py`", ""]
        lines += ["**Behavior:**", "", "```gherkin", f"Feature: F{k}", ""]
        for j in range(1, spec["scenarios"] + 1):
            lines += [
                f"  Scenario: scenario {k}.{j}",
                "    Given a",
                "    When b",
                "    Then c",
                "",
            ]
        lines += ["```", "", "**Steps:**", ""]
        for j in range(1, spec["steps"] + 1):
            lines += [f"#### Step {k}.{j}: step", "", "**IMPLEMENT**: do it"]
            if j == 1 and spec["covers"]:
                lines.append(f"**Covers**: {', '.join(spec['covers'])}")
            lines += [f"**Commit**: `feat: step {k}.{j}`", ""]
    lines += ["## Plan Review Summary", "", "Plan tier: standard.", ""]
    lines += [f"- **Open blocker**: {b}" for b in blockers]
    lines += ["", "## Build Progress", "", "### Slices", ""]
    for k, spec in enumerate(slices, start=1):
        mark = "x" if k in ticked else " "
        lines.append(f"- [{mark}] Slice {k}: Part {k}")
        lines += [f"  - [ ] Step {k}.{j}: step" for j in range(1, spec["steps"] + 1)]
    return "\n".join(lines) + "\n"


COMPLETE_SPEC = """# Spec: Sample

## Intent Description

Why the change exists.

## Architecture Specification

- One module.

## Acceptance Criteria

- [ ] AC1 The module works.
"""


def _spec_without(heading: str) -> str:
    blocks = re.split(r"(?m)^(?=## )", COMPLETE_SPEC)
    kept = [b for b in blocks if not b.startswith(heading + "\n")]
    assert len(kept) == len(blocks) - 1, heading
    return "".join(kept)


@pytest.fixture
def work(tmp_path: Path, monkeypatch, capsys):
    """A working directory with a `run(...)` that feeds the hook one payload."""

    class Work:
        root = tmp_path

        def put(self, rel: str, text: str) -> Path:
            path = tmp_path / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="")
            return path

        def run(self, tool: str, rel: str, env=None, **fields):
            payload = {"tool_name": tool, "cwd": str(tmp_path)}
            payload["tool_input"] = {"file_path": rel, **fields}
            return _run_main(monkeypatch, capsys, payload, env)

        def write(self, rel: str, content: str, env=None):
            return self.run("Write", rel, env, content=content)

        def edit(self, rel: str, old: str, new: str, **extra):
            return self.run("Edit", rel, old_string=old, new_string=new, **extra)

    return Work()


def _ids(found: list[dict]) -> set[tuple[str, str]]:
    return {(v["id"], v["subject"]) for v in found}


def _decide(work, tool: str, rel: str, **fields) -> list[dict]:
    payload = {
        "tool_name": tool,
        "cwd": str(work.root),
        "tool_input": {"file_path": rel, **fields},
    }
    return hook.decide(payload, hook._read_text)


def test_a_valid_generated_plan_has_no_violation() -> None:
    record = hook._load_record()
    assert record.plan_violations(build_plan(), spec_text=None) == []


def test_the_generated_plan_with_covers_opts_in_to_criterion_coverage() -> None:
    record = hook._load_record()
    built = record.build_record(build_plan())
    assert built["applicability"]["criterion_coverage"] == "applies"


@pytest.mark.parametrize(
    "violating,expected",
    [
        (
            build_plan(
                slices=(
                    DEFAULT_SLICES[0],
                    {"covers": ("AC2",), "scenarios": 1, "steps": 0},
                    DEFAULT_SLICES[2],
                )
            ),
            ("scenario-no-step", "Slice 2"),
        ),
        (
            build_plan(
                slices=(
                    DEFAULT_SLICES[0],
                    DEFAULT_SLICES[1],
                    {"covers": (), "scenarios": 1, "steps": 1},
                )
            ),
            ("ac-no-scenario", "AC3"),
        ),
        (
            build_plan(blockers=("Slice 2 - missing error path",), ticked=(2,)),
            ("closed-slice-open-blocker", "Slice 2"),
        ),
    ],
    ids=["scenario-no-step", "ac-no-scenario", "closed-slice-open-blocker"],
)
def test_a_plan_write_that_adds_a_violation_is_refused_and_leaves_the_file(
    work, violating: str, expected: tuple[str, str]
) -> None:
    on_disk = build_plan()
    path = work.put("plans/p.md", on_disk)
    assert expected in _ids(_decide(work, "Write", "plans/p.md", content=violating))
    code, _, err = work.write("plans/p.md", violating)
    assert code == 2
    assert err.startswith("[BLOCK] feature record: plans/p.md")
    assert path.read_text(encoding="utf-8") == on_disk


@pytest.mark.parametrize(
    "section",
    [
        "## Intent Description",
        "## Architecture Specification",
        "## Acceptance Criteria",
    ],
)
def test_a_spec_write_that_drops_a_section_is_refused_naming_the_heading(
    work, section: str
) -> None:
    work.put("docs/specs/x.md", COMPLETE_SPEC)
    proposed = _spec_without(section)
    assert _ids(_decide(work, "Write", "docs/specs/x.md", content=proposed)) == {
        ("spec-missing-section", section)
    }
    assert work.write("docs/specs/x.md", proposed)[0] == 2
    assert (work.root / "docs/specs/x.md").read_text(encoding="utf-8") == COMPLETE_SPEC


def test_a_spec_with_an_empty_acceptance_criteria_section_is_refused(work) -> None:
    empty = COMPLETE_SPEC.replace("- [ ] AC1 The module works.\n", "\n")
    assert work.write("docs/specs/x/spec.md", empty)[0] == 2


def test_a_complete_spec_write_is_allowed(work) -> None:
    assert work.write("docs/specs/x.md", COMPLETE_SPEC) == (0, "", "")


def test_a_write_that_creates_a_violating_plan_is_refused(work) -> None:
    bad = build_plan(slices=({"covers": (), "scenarios": 1, "steps": 0},), criteria=1)
    assert not (work.root / "plans/9999-x.md").exists()
    code, _, err = work.write("plans/9999-x.md", bad)
    assert code == 2 and err.startswith("[BLOCK]")
    assert not (work.root / "plans/9999-x.md").exists()


def test_a_write_that_creates_a_valid_plan_is_allowed(work) -> None:
    assert work.write("plans/9999-x.md", build_plan()) == (0, "", "")


def test_an_edit_is_checked_on_its_resulting_text(work) -> None:
    plan = build_plan()
    work.put("plans/p.md", plan)
    code, _, _ = work.edit("plans/p.md", "#### Step 2.1: step", "Step 2.1: step")
    assert code == 2
    found = _ids(
        _decide(
            work,
            "Edit",
            "plans/p.md",
            old_string="#### Step 2.1: step",
            new_string="Step 2.1: step",
        )
    )
    assert ("scenario-no-step", "Slice 2") in found


def test_an_edit_that_removes_the_scenario_a_criterion_depends_on_is_refused(
    work,
) -> None:
    work.put("plans/p.md", build_plan())
    found = _decide(
        work,
        "Edit",
        "plans/p.md",
        old_string="  Scenario: scenario 3.1\n",
        new_string="",
    )
    assert ("ac-no-scenario", "AC3") in _ids(found)
    assert "AC3" in found[0]["what"]


def _tick(slice_no: int) -> tuple[str, str]:
    return (
        f"- [ ] Slice {slice_no}: Part {slice_no}",
        f"- [x] Slice {slice_no}: Part {slice_no}",
    )


def test_ticking_a_slice_that_has_an_open_blocker_is_refused(work) -> None:
    work.put("plans/p.md", build_plan(blockers=("Slice 2 - missing error path",)))
    old, new = _tick(2)
    found = _decide(work, "Edit", "plans/p.md", old_string=old, new_string=new)
    assert _ids(found) == {("closed-slice-open-blocker", "Slice 2")}
    assert work.edit("plans/p.md", old, new)[0] == 2


def test_ticking_a_slice_with_a_resolved_blocker_is_allowed(work) -> None:
    plan = build_plan(blockers=("Slice 2 - missing error path",)).replace(
        "- **Open blocker**: Slice 2 - missing error path\n",
        "- **Open blocker**: Slice 2 - missing error path\n"
        "- **Resolved blocker**: Slice 2 - missing error path\n",
    )
    assert "Resolved blocker" in plan
    work.put("plans/p.md", plan)
    assert work.edit("plans/p.md", *_tick(2)) == (0, "", "")


def test_a_tick_that_no_commit_backs_is_allowed_and_runs_no_git(
    work, monkeypatch
) -> None:
    subprocess.run(
        ["git", "init", "-q"],
        cwd=work.root,
        env=hermetic_git_env(home=work.root),
        check=True,
    )
    work.put("plans/p.md", build_plan())

    def no_process(*args, **kwargs):
        raise AssertionError("the hook started a process")

    monkeypatch.setattr(subprocess, "Popen", no_process)
    monkeypatch.setattr(subprocess, "run", no_process)
    assert work.edit("plans/p.md", *_tick(1)) == (0, "", "")


def test_deleting_the_only_covers_line_is_allowed(work) -> None:
    one_cover = build_plan(slices=(DEFAULT_SLICES[0],), criteria=2)
    record = hook._load_record()
    assert ("ac-no-scenario", "AC2") in _ids(record.plan_violations(one_cover))
    work.put("plans/p.md", one_cover)
    assert work.edit("plans/p.md", "**Covers**: AC1\n", "") == (0, "", "")


@pytest.mark.parametrize("covers", [True, False], ids=["with-covers", "without-covers"])
def test_a_build_progress_step_tick_is_allowed(work, covers: bool) -> None:
    slices = (
        DEFAULT_SLICES if covers else tuple({**s, "covers": ()} for s in DEFAULT_SLICES)
    )
    work.put("plans/p.md", build_plan(slices=slices))
    assert work.edit(
        "plans/p.md", "  - [ ] Step 1.1: step", "  - [x] Step 1.1: step"
    ) == (
        0,
        "",
        "",
    )


def test_a_plan_that_already_has_a_violation_accepts_an_unrelated_edit(work) -> None:
    broken = build_plan(
        slices=(
            DEFAULT_SLICES[0],
            {"covers": ("AC2",), "scenarios": 1, "steps": 0},
            DEFAULT_SLICES[2],
        )
    )
    record = hook._load_record()
    assert record.plan_violations(broken)
    work.put("plans/p.md", broken)
    result = work.edit(
        "plans/p.md", "The goal paragraph.", "A reworded goal paragraph."
    )
    assert result == (0, "", "")


def test_an_edit_that_removes_the_only_violation_is_allowed(work) -> None:
    broken = build_plan(
        slices=(
            DEFAULT_SLICES[0],
            {"covers": (), "scenarios": 1, "steps": 0},
            DEFAULT_SLICES[2],
        ),
        criteria=3,
    ).replace("AC2 Criterion 2", "AC2 Criterion 2")
    record = hook._load_record()
    assert ("scenario-no-step", "Slice 2") in _ids(record.plan_violations(broken))
    work.put("plans/p.md", broken)
    result = work.edit(
        "plans/p.md",
        "### Slice 3: Part 3",
        "#### Step 2.1: step\n\n**Covers**: AC2\n\n### Slice 3: Part 3",
    )
    assert result == (0, "", "")


def test_an_edit_that_fixes_one_violation_and_adds_another_is_refused(work) -> None:
    broken = build_plan(
        slices=(
            DEFAULT_SLICES[0],
            {"covers": ("AC2",), "scenarios": 1, "steps": 0},
            DEFAULT_SLICES[2],
        )
    )
    record = hook._load_record()
    assert ("scenario-no-step", "Slice 2") in _ids(record.plan_violations(broken))
    work.put("plans/p.md", broken)
    start = broken.index("### Slice 3: Part 3")
    end = broken.index("  Scenario: scenario 3.1\n", start) + len(
        "  Scenario: scenario 3.1\n"
    )
    old = broken[start:end]
    new = "#### Step 2.1: step\n\n**Covers**: AC2\n\n" + old.replace(
        "  Scenario: scenario 3.1\n", ""
    )
    found = _decide(work, "Edit", "plans/p.md", old_string=old, new_string=new)
    assert _ids(found) == {("ac-no-scenario", "AC3")}
    assert work.edit("plans/p.md", old, new)[0] == 2


@pytest.mark.parametrize(
    "case",
    [
        "invalid-json",
        "no-file-path",
        "old-absent",
        "old-twice",
        "old-empty",
        "replace-all-several",
        "unreadable-directory",
        "not-utf8",
    ],
)
def test_an_input_the_hook_cannot_judge_is_allowed_silently(
    work, monkeypatch, capsys, case: str
) -> None:
    plan = build_plan() + "dup\ndup\n"
    work.put("plans/p.md", plan)
    if case == "invalid-json":
        assert _run_main(monkeypatch, capsys, "{not json") == (0, "", "")
        return
    if case == "no-file-path":
        payload = {
            "tool_name": "Write",
            "cwd": str(work.root),
            "tool_input": {"content": "x"},
        }
        assert _run_main(monkeypatch, capsys, payload) == (0, "", "")
        return
    if case == "unreadable-directory":
        (work.root / "plans" / "d.md").mkdir()
        assert work.write("plans/d.md", build_plan(slices=(), criteria=0)) == (
            0,
            "",
            "",
        )
        return
    if case == "not-utf8":
        (work.root / "plans" / "b.md").write_bytes(b"\xff\xfe broken")
        assert work.write("plans/b.md", "x") == (0, "", "")
        return
    old, extra = {
        "old-absent": ("not in the file", {}),
        "old-twice": ("dup", {}),
        "old-empty": ("", {}),
        "replace-all-several": ("dup", {"replace_all": True}),
    }[case]
    assert work.edit("plans/p.md", old, "Step 1.1 removed", **extra) == (0, "", "")


def test_a_matching_edit_whose_result_is_unchanged_is_allowed(work) -> None:
    work.put("plans/p.md", build_plan())
    assert work.edit("plans/p.md", "The goal paragraph.", "The goal paragraph.") == (
        0,
        "",
        "",
    )


def test_an_internal_error_is_allowed_with_a_one_line_notice(work, monkeypatch) -> None:
    record = hook._load_record()

    def boom(*args, **kwargs):
        raise RuntimeError("parser exploded\nsecond line")

    monkeypatch.setattr(record, "plan_violations", boom)
    code, out, err = work.write("plans/p.md", build_plan())
    assert (code, out) == (0, "")
    assert err == "feature record check skipped: RuntimeError: parser exploded\n"


def test_a_missing_record_module_is_allowed_with_a_notice(work, monkeypatch) -> None:
    def cannot_import():
        raise ImportError("no module")

    monkeypatch.setattr(hook, "_load_record", cannot_import)
    code, _, err = work.write("plans/p.md", build_plan())
    assert code == 0
    assert err.startswith("feature record check skipped: ImportError")
    assert err.count("\n") == 1


def test_a_plan_is_checked_without_its_spec(work, monkeypatch) -> None:
    record = hook._load_record()
    real = record.plan_violations
    calls: list[tuple[tuple, dict]] = []

    def spy(*args, **kwargs):
        calls.append((args, kwargs))
        return real(*args, **kwargs)

    monkeypatch.setattr(record, "plan_violations", spy)
    work.put("plans/p.md", build_plan())
    work.edit("plans/p.md", "The goal paragraph.", "Another goal paragraph.")
    assert len(calls) == 2  # before and after
    for args, kwargs in calls:
        assert (kwargs.get("spec_text") if "spec_text" in kwargs else None) is None
        assert len(args) == 1


@pytest.mark.parametrize(
    "name,rel",
    [
        ("plan_shape_2270.md", "plans/2270-x.md"),
        ("plan_shape_2272.md", "plans/2272-x.md"),
        ("plan_shape_2274.md", "docs/specs/lanes/plans/p.md"),
        ("spec_shape.md", "docs/specs/lanes/spec.md"),
    ],
)
def test_committed_plan_shaped_fixtures_pass_as_new_files(
    work, name: str, rel: str
) -> None:
    text = (FIXTURES / name).read_text(encoding="utf-8")
    assert work.write(rel, text) == (0, "", "")


def test_the_covers_fixtures_exercise_the_coverage_invariant() -> None:
    record = hook._load_record()
    applies = {
        name: record.build_record((FIXTURES / name).read_text(encoding="utf-8"))[
            "applicability"
        ]["criterion_coverage"]
        for name in ("plan_shape_2270.md", "plan_shape_2272.md", "plan_shape_2274.md")
    }
    assert applies == {
        "plan_shape_2270.md": "applies",
        "plan_shape_2272.md": "not-applicable",
        "plan_shape_2274.md": "applies",
    }


@pytest.mark.parametrize(
    "name", ["plan_shape_2270.md", "plan_shape_2272.md", "plan_shape_2274.md"]
)
def test_a_fixture_with_its_step_headings_removed_is_refused(work, name: str) -> None:
    text = (FIXTURES / name).read_text(encoding="utf-8")
    broken = re.sub(r"(?m)^#### Step ", "Step ", text)
    assert broken != text
    assert work.write("plans/p.md", broken)[0] == 2


def test_the_hook_runs_end_to_end_in_a_fresh_interpreter(tmp_path: Path) -> None:
    payload = {
        "tool_name": "Write",
        "cwd": str(tmp_path),
        "tool_input": {
            "file_path": "plans/p.md",
            "content": build_plan(
                slices=({"covers": (), "scenarios": 1, "steps": 0},), criteria=1
            ),
        },
    }
    done = subprocess.run(
        [sys.executable, "-I", str(HOOK_PATH)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=tmp_path,
        check=False,
    )
    assert done.returncode == 2, done.stderr
    assert done.stderr.startswith("[BLOCK] feature record: plans/p.md")


def test_a_matching_path_imports_the_record_in_a_fresh_interpreter(
    tmp_path: Path,
) -> None:
    """Control for the fast-path test: a matching write does import the record."""
    payload = _payload("plans/p.md", cwd=tmp_path, content=build_plan())
    result = _run_isolated(tmp_path, payload)
    assert result["code"] == 0 and result["imported"] is True


def test_a_generated_500_line_plan_is_checked_within_a_second(
    work, monkeypatch, capsys
) -> None:
    six = tuple(
        {"covers": (f"AC{k}",), "scenarios": 2, "steps": 2} for k in range(1, 7)
    )
    plan = build_plan(slices=six, criteria=6, filler=260)
    assert len(plan.splitlines()) >= 500
    assert hook._load_record().plan_violations(plan, spec_text=None) == []
    work.put("plans/big.md", plan)
    payload = {
        "tool_name": "Write",
        "cwd": str(work.root),
        "tool_input": {"file_path": "plans/big.md", "content": plan},
    }
    runs = []
    for _ in range(5):
        start = time.perf_counter()
        result = _run_main(monkeypatch, capsys, payload)
        runs.append(time.perf_counter() - start)
        assert result == (0, "", "")
    assert min(runs) < 1.0, runs
