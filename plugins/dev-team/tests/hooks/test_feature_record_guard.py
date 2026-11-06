"""Tests for hooks/feature_record_guard.py (#2275, Slice 4).

Step 4.1 covers the path matcher, the payload layer and the no-work fast path;
Step 4.2 the decision (what a write introduces) and its fail-open handling;
Step 4.3 the refusal text and the boundary event.
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
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
        ("docs/specs/x/other/p.md", None),
        ("docs/specs/plans/p.md", None),
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


def _symlinked_checkout(tmp_path: Path) -> tuple[Path, Path]:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    return real, link


def test_target_path_matches_when_cwd_is_a_symlink_to_the_checkout(
    tmp_path: Path,
) -> None:
    real, link = _symlinked_checkout(tmp_path)
    got = hook.target_path(_payload(str(real / "plans" / "p.md"), cwd=link))
    assert got is not None and got[1] == "plans/p.md"
    assert os.path.realpath(got[0]) == os.path.realpath(real / "plans" / "p.md")


def test_target_path_matches_when_file_path_goes_through_a_symlink(
    tmp_path: Path,
) -> None:
    real, link = _symlinked_checkout(tmp_path)
    got = hook.target_path(_payload(str(link / "plans" / "p.md"), cwd=real))
    assert got is not None and got[1] == "plans/p.md"


def test_target_path_with_a_symlinked_cwd_still_rejects_other_directories(
    tmp_path: Path,
) -> None:
    _, link = _symlinked_checkout(tmp_path)
    other = tmp_path / "other" / "plans" / "p.md"
    assert hook.target_path(_payload(str(other), cwd=link)) is None


def test_target_path_without_cwd_resolves_against_the_process_directory(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    payload = _payload("plans/p.md")
    assert "cwd" not in payload
    assert hook.target_path(payload) == (
        str(Path(os.getcwd()) / "plans" / "p.md"),
        "plans/p.md",
    )


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


def test_write_to_a_new_file_has_no_before_state(tmp_path: Path) -> None:
    payload = _payload("plans/p.md", cwd=tmp_path, content="new\n")
    assert hook.proposed_text(payload, _reader({})) == (None, "new\n")


def test_write_to_an_existing_empty_file_has_an_empty_before_state(
    tmp_path: Path,
) -> None:
    abs_path = str(tmp_path / "plans" / "p.md")
    payload = _payload("plans/p.md", cwd=tmp_path, content="new\n")
    assert hook.proposed_text(payload, _reader({abs_path: ""})) == ("", "new\n")


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


def _cannot_judge_cases(tmp_path: Path) -> dict[str, tuple[dict, dict[str, str]]]:
    abs_path = str(tmp_path / "plans" / "p.md")
    on_disk = {abs_path: "one\ntwo\ntwo\n"}

    def edit(**fields) -> dict:
        return _payload("plans/p.md", tool="Edit", cwd=tmp_path, **fields)

    return {
        "old_string absent": (edit(old_string="zzz", new_string="x"), on_disk),
        "old_string twice": (edit(old_string="two", new_string="x"), on_disk),
        "old_string empty on an existing file": (
            edit(old_string="", new_string="x"),
            on_disk,
        ),
        "old_string empty on an existing empty file": (
            edit(old_string="", new_string="x"),
            {abs_path: ""},
        ),
        "replace_all, several matches": (
            edit(old_string="two", new_string="x", replace_all=True),
            on_disk,
        ),
        "Edit on a missing file": (edit(old_string="one", new_string="x"), {}),
        "old_string not text": (edit(old_string=3, new_string="x"), on_disk),
        "new_string missing": (edit(old_string="one"), on_disk),
        "Write content not text": (
            _payload("plans/p.md", cwd=tmp_path, content=5),
            on_disk,
        ),
        "Write content missing": (_payload("plans/p.md", cwd=tmp_path), on_disk),
        "no file_path": (
            {"tool_name": "Write", "tool_input": {"content": "x"}},
            on_disk,
        ),
        "other tool": (
            _payload("plans/p.md", tool="Read", cwd=tmp_path, content="x"),
            on_disk,
        ),
    }


@pytest.mark.parametrize("label", list(_cannot_judge_cases(Path("/unused"))))
def test_inputs_the_hook_cannot_judge_return_none(tmp_path: Path, label: str) -> None:
    payload, files = _cannot_judge_cases(tmp_path)[label]
    assert hook.proposed_text(payload, _reader(files)) is None


def test_an_edit_with_an_empty_old_string_creates_a_missing_file(
    tmp_path: Path,
) -> None:
    payload = _payload(
        "plans/p.md", tool="Edit", cwd=tmp_path, old_string="", new_string="new\n"
    )
    assert hook.proposed_text(payload, _reader({})) == (None, "new\n")


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


def test_read_text_translates_crlf_so_an_lf_old_string_can_match(
    tmp_path: Path,
) -> None:
    path = tmp_path / "p.md"
    path.write_bytes(b"a\r\nb\r\n")
    assert hook._read_text(str(path)) == "a\nb\n"


# ---------------------------------------------------------------------------
# main: escape hatch and the no-work path
# ---------------------------------------------------------------------------


def _run_main(monkeypatch, capsys, payload: object, env: dict[str, str] | None = None):
    """Run `hook.main()` on one payload (a dict, text, or raw bytes for stdin)."""
    if isinstance(payload, bytes):
        stdin = io.TextIOWrapper(io.BytesIO(payload), encoding="utf-8")
    else:
        stdin = io.StringIO(
            payload if isinstance(payload, str) else json.dumps(payload)
        )
    monkeypatch.setattr(sys, "stdin", stdin)
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


def test_main_allows_a_non_utf8_stdin_payload_with_one_notice(
    monkeypatch, capsys
) -> None:
    code, out, err = _run_main(monkeypatch, capsys, b'{"tool_input": "\xff\xfe"}')
    assert (code, out) == (0, "")
    assert err.startswith("feature record check skipped: UnicodeDecodeError")
    assert err.count("\n") == 1


def test_main_allows_a_write_when_the_working_directory_is_gone(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    doomed = tmp_path / "doomed"
    doomed.mkdir()
    monkeypatch.chdir(doomed)
    doomed.rmdir()
    payload = _payload("plans/p.md", content="x\n")  # no cwd: needs os.getcwd()
    code, out, err = _run_main(monkeypatch, capsys, payload)
    assert (code, out) == (0, "")
    assert err.startswith("feature record check skipped: FileNotFoundError")
    assert err.count("\n") == 1


def test_main_allows_a_path_that_cannot_be_opened_with_one_notice(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    """A real fault (a NUL byte in a path that matches the checked set) reaches
    the fail-open notice, naming the exception."""
    payload = _payload("plans/p\x00.md", cwd=tmp_path, content="x\n")
    code, out, err = _run_main(monkeypatch, capsys, payload)
    assert (code, out) == (0, "")
    assert err.startswith("feature record check skipped: ValueError")
    assert err.count("\n") == 1


def test_main_allows_a_matching_write_when_the_record_module_is_missing(
    tmp_path: Path,
) -> None:
    """Copy the hook and its stdin helper into a tree with no `scripts/` beside
    them, so the lazy import of `feature_record` really fails."""
    tree = tmp_path / "plugin" / "hooks"
    (tree / "lib").mkdir(parents=True)
    (tree / "feature_record_guard.py").write_text(HOOK_PATH.read_text(encoding="utf-8"))
    (tree / "lib" / "stdin_json.py").write_text(
        (_HOOKS_DIR / "lib" / "stdin_json.py").read_text(encoding="utf-8")
    )
    work = tmp_path / "work"
    work.mkdir()
    payload = _payload("plans/p.md", cwd=work, content=build_plan())
    done = _run_hook(tree / "feature_record_guard.py", payload, work)
    assert done.returncode == 0
    assert done.stdout == ""
    assert done.stderr.startswith(
        "feature record check skipped: ModuleNotFoundError: No module named"
    )
    assert done.stderr.count("\n") == 1


def test_main_escape_hatch_allows_a_violating_plan(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    payload = _payload("plans/p.md", cwd=tmp_path, content=_stranded_slice_two())
    assert _run_main(monkeypatch, capsys, payload)[0] == 2  # control: it is refused
    events_after_refusal = _events(tmp_path)
    assert len(events_after_refusal) == 1
    code, out, _ = _run_main(monkeypatch, capsys, payload, {hook.ESCAPE_ENV: "off"})
    assert (code, out) == (0, "")
    assert _events(tmp_path) == events_after_refusal  # no second event


def test_main_escape_hatch_prints_one_notice(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    payload = _payload("plans/p.md", cwd=tmp_path, content="anything\n")
    _, _, err = _run_main(monkeypatch, capsys, payload, {hook.ESCAPE_ENV: "off"})
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

_LOADED_MODULES = (
    "feature_record",
    "plan_parse",
    "plan_record_parse",
    "commit_evidence",
    "boundary_events",
)

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
                      "loaded": [m for m in json.loads(sys.argv[2]) if m in sys.modules]}))
    """
)


def _clean_env() -> dict[str, str]:
    """The test process environment without the guard's escape hatch, so a
    developer who exported it cannot make these subprocess tests pass or fail."""
    return {k: v for k, v in os.environ.items() if k != hook.ESCAPE_ENV}


def _run_hook(script: Path, payload: dict, cwd: Path):
    return subprocess.run(
        [sys.executable, "-I", str(script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=cwd,
        env=_clean_env(),
        check=False,
    )


def _run_isolated(tmp_path: Path, payload: dict):
    wrapper = tmp_path / "wrapper.py"
    wrapper.write_text(_WRAPPER)
    done = subprocess.run(
        [
            sys.executable,
            "-I",
            str(wrapper),
            str(_HOOKS_DIR),
            json.dumps(_LOADED_MODULES),
        ],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=_clean_env(),
        check=False,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_a_path_outside_the_matcher_reads_no_file_and_loads_no_record_module(
    tmp_path: Path,
) -> None:
    payload = _payload("src/app.py", cwd=tmp_path, content="x = 1\n")
    assert _run_isolated(tmp_path, payload) == {
        "code": 0,
        "opened": [],
        "loaded": [],
    }


def test_the_audit_wrapper_sees_a_file_read(tmp_path: Path) -> None:
    """Control: the wrapper does record an open when the hook reads a file."""
    (tmp_path / "plans").mkdir()
    (tmp_path / "plans" / "p.md").write_text("x\n")
    payload = _payload("plans/p.md", cwd=tmp_path, content="y\n")
    result = _run_isolated(tmp_path, payload)
    assert str(tmp_path / "plans" / "p.md") in result["opened"]


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
    spec_ref: str = "https://example.test/issues/1",
) -> str:
    """A plan in the shape `/plan` writes. `covers` names the criteria the
    slice's first step covers; `steps` and `scenarios` are counts."""
    lines = [
        "# Plan: Sample",
        "",
        "**Status**: approved",
        f"**Spec**: {spec_ref}",
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
    record = hook._import_feature_record()
    assert record.plan_violations(build_plan(), spec_text=None) == []


def test_the_generated_plan_with_covers_opts_in_to_criterion_coverage() -> None:
    record = hook._import_feature_record()
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
    assert empty != COMPLETE_SPEC
    code, _, err = work.write("docs/specs/x/spec.md", empty)
    assert code == 2
    assert "[spec-missing-section]" in err
    assert 'HOW: Add "## Acceptance Criteria" with at least one line of text.' in err


def test_a_complete_spec_write_is_allowed(work) -> None:
    assert work.write("docs/specs/x.md", COMPLETE_SPEC) == (0, "", "")


_PARTIAL_SPEC = "## Intent Description\n\nWhy the change exists.\n"
_OTHER_SECTIONS = {
    ("spec-missing-section", "## Architecture Specification"),
    ("spec-missing-section", "## Acceptance Criteria"),
}


def test_a_write_to_an_existing_empty_spec_is_judged_against_the_empty_text(
    work,
) -> None:
    """An empty file already lacks all three sections, so a write that adds one
    and leaves the rest missing introduces nothing."""
    work.put("docs/specs/x.md", "")
    assert _decide(work, "Write", "docs/specs/x.md", content=_PARTIAL_SPEC) == []
    assert work.write("docs/specs/x.md", _PARTIAL_SPEC) == (0, "", "")


def test_the_same_write_to_a_missing_spec_is_refused_for_every_missing_section(
    work,
) -> None:
    assert not (work.root / "docs/specs/x.md").exists()
    found = _decide(work, "Write", "docs/specs/x.md", content=_PARTIAL_SPEC)
    assert _ids(found) == _OTHER_SECTIONS
    assert work.write("docs/specs/x.md", _PARTIAL_SPEC)[0] == 2


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
    code, _, err = work.edit("plans/p.md", "  Scenario: scenario 3.1\n", "")
    assert code == 2
    assert "[ac-no-scenario]" in err
    assert 'WHAT: AC3 "Criterion 3" has no scenario' in err


def _tick(slice_no: int) -> tuple[str, str]:
    return (
        f"- [ ] Slice {slice_no}: Part {slice_no}",
        f"- [x] Slice {slice_no}: Part {slice_no}",
    )


def test_ticking_a_slice_that_has_an_open_blocker_is_refused(work) -> None:
    work.put("plans/p.md", build_plan(blockers=("Slice 2 - missing error path",)))
    old, new = _tick(2)
    code, _, err = work.edit("plans/p.md", old, new)
    assert code == 2
    assert "WHAT: Slice 2 is ticked done while an open blocker names it." in err
    how = [line for line in err.splitlines() if line.startswith("HOW:")]
    assert len(how) == 1
    assert "## Plan Review Summary" in how[0] and "untick Slice 2" in how[0]
    assert how[0].endswith(hook.EDIT_HOW_SUFFIX)


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
    record = hook._import_feature_record()
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
    record = hook._import_feature_record()
    assert record.plan_violations(broken)
    work.put("plans/p.md", broken)
    result = work.edit(
        "plans/p.md", "The goal paragraph.", "A reworded goal paragraph."
    )
    assert result == (0, "", "")


def test_an_edit_that_removes_every_violation_is_allowed(work) -> None:
    broken = build_plan(
        slices=(
            DEFAULT_SLICES[0],
            {"covers": (), "scenarios": 1, "steps": 0},
            DEFAULT_SLICES[2],
        )
    )
    record = hook._import_feature_record()
    assert _ids(record.plan_violations(broken)) == {
        ("scenario-no-step", "Slice 2"),
        ("ac-no-scenario", "AC2"),
    }
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
    record = hook._import_feature_record()
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


def _stepless_plan() -> str:
    """A plan every judged write of which would be refused."""
    return _stranded_slice_two()


def test_the_judged_form_of_these_writes_is_refused(work) -> None:
    """Control for the table below: judged, the proposed content is refused."""
    assert work.write("plans/ctl.md", _stepless_plan())[0] == 2
    work.put("plans/p.md", build_plan())
    assert work.edit("plans/p.md", "#### Step 1.1: step", "Step 1.1: step")[0] == 2


@pytest.mark.parametrize(
    "label",
    [
        "invalid-json",
        "no-file-path",
        "old-absent",
        "old-twice",
        "old-empty-on-existing-file",
        "replace-all-several",
        "unreadable-directory",
        "not-utf8",
    ],
)
def test_an_input_the_hook_cannot_judge_is_allowed_silently(
    work, monkeypatch, capsys, label: str
) -> None:
    """Each row would be refused if the hook judged it: the new text or the
    applied edit holds a scenario with no step."""
    work.put("plans/p.md", build_plan())
    bad = _stepless_plan()
    if label == "invalid-json":
        result = _run_main(monkeypatch, capsys, "{" + json.dumps({"content": bad}))
    elif label == "no-file-path":
        payload = {
            "tool_name": "Write",
            "cwd": str(work.root),
            "tool_input": {"content": bad},
        }
        result = _run_main(monkeypatch, capsys, payload)
    elif label == "unreadable-directory":
        (work.root / "plans" / "d.md").mkdir()
        result = work.write("plans/d.md", bad)
    elif label == "not-utf8":
        (work.root / "plans" / "b.md").write_bytes(b"\xff\xfe broken")
        result = work.write("plans/b.md", bad)
    else:
        # "#### Step " occurs once per step: applied (first or all), it would
        # strip a step heading and strand its slice's scenario.
        old, extra = {
            "old-absent": ("not in the file", {}),
            "old-twice": ("#### Step ", {}),
            "old-empty-on-existing-file": ("", {}),
            "replace-all-several": ("#### Step ", {"replace_all": True}),
        }[label]
        new = bad if old != "#### Step " else "Step "
        result = work.edit("plans/p.md", old, new, **extra)
    assert result == (0, "", "")


def test_a_matching_edit_whose_result_is_unchanged_is_allowed(work) -> None:
    work.put("plans/p.md", build_plan())
    assert work.edit("plans/p.md", "The goal paragraph.", "The goal paragraph.") == (
        0,
        "",
        "",
    )


def test_an_edit_matches_a_crlf_file_with_an_lf_old_string(work) -> None:
    crlf = build_plan().replace("\n", "\r\n")
    path = work.root / "plans" / "p.md"
    path.parent.mkdir(parents=True)
    path.write_bytes(crlf.encode("utf-8"))
    old = "#### Step 2.1: step\n\n**IMPLEMENT**: do it"
    assert old.replace("\n", "\r\n") in crlf and old not in crlf
    code, _, err = work.edit(
        "plans/p.md", old, "Step 2.1: step\n\n**IMPLEMENT**: do it"
    )
    assert code == 2
    assert "[scenario-no-step]" in err
    assert path.read_bytes() == crlf.encode("utf-8")


def test_an_edit_with_an_empty_old_string_creates_a_violating_plan_and_is_refused(
    work,
) -> None:
    assert not (work.root / "plans" / "new.md").exists()
    code, _, err = work.edit("plans/new.md", "", _stepless_plan())
    assert code == 2 and "[scenario-no-step]" in err


def test_an_edit_with_an_empty_old_string_creates_a_valid_plan_and_is_allowed(
    work,
) -> None:
    assert work.edit("plans/new.md", "", build_plan()) == (0, "", "")


def test_a_write_through_a_symlinked_working_directory_is_checked(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    payload = {
        "tool_name": "Write",
        "cwd": str(link),
        "tool_input": {
            "file_path": str(real / "plans" / "p.md"),
            "content": _stepless_plan(),
        },
    }
    code, _, err = _run_main(monkeypatch, capsys, payload)
    assert code == 2
    assert err.startswith("[BLOCK] feature record: plans/p.md")


def test_a_write_without_cwd_resolves_against_the_process_directory(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.chdir(tmp_path)
    payload = _payload("plans/p.md", content=_stepless_plan())
    assert "cwd" not in payload
    assert _run_main(monkeypatch, capsys, payload)[0] == 2
    assert _run_main(
        monkeypatch, capsys, _payload("plans/p.md", content=build_plan())
    ) == (0, "", "")


def test_a_plan_whose_spec_line_names_an_incomplete_spec_is_still_allowed(
    work,
) -> None:
    """The hook checks a plan without its spec: an incomplete spec on disk,
    named by the plan's **Spec** line, adds nothing to the plan's violations."""
    work.put("docs/specs/x.md", "# Spec: incomplete\n")
    plan = build_plan(spec_ref="docs/specs/x.md")
    assert "**Spec**: docs/specs/x.md" in plan
    assert work.write("plans/p.md", plan) == (0, "", "")


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
    record = hook._import_feature_record()
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
    code, _, err = work.write("plans/p.md", broken)
    assert code == 2
    assert "[scenario-no-step]" in err


def test_a_covers_line_inside_a_code_fence_does_not_cover_its_criterion(work) -> None:
    """Refusal direction for the parser's fence rule: AC3's only Covers line
    sits in a fenced block, so AC3 has no covering step."""
    fenced = build_plan(
        slices=(DEFAULT_SLICES[0], DEFAULT_SLICES[1], NO_COVERS[2])
    ).replace(
        "#### Step 3.1: step\n\n**IMPLEMENT**: do it\n",
        "#### Step 3.1: step\n\n**IMPLEMENT**: do it\n```text\n**Covers**: AC3\n```\n",
    )
    assert "```text\n**Covers**: AC3" in fenced
    code, _, err = work.write("plans/fenced.md", fenced)
    assert code == 2
    assert 'WHAT: AC3 "Criterion 3" has no scenario' in err
    unfenced = fenced.replace("```text\n**Covers**: AC3\n```\n", "**Covers**: AC3\n")
    assert unfenced != fenced
    assert work.write("plans/unfenced.md", unfenced) == (0, "", "")


def test_a_section_whose_only_content_is_in_a_comment_is_empty(work) -> None:
    commented = COMPLETE_SPEC.replace("- One module.\n", "<!-- - One module. -->\n")
    assert commented != COMPLETE_SPEC
    code, _, err = work.write("docs/specs/x.md", commented)
    assert code == 2
    assert 'WHAT: The spec has no "## Architecture Specification" section' in err
    assert err.count("WHAT:") == 1


def test_an_incomplete_spec_on_disk_accepts_an_unrelated_edit(work) -> None:
    work.put("docs/specs/x.md", _spec_without("## Acceptance Criteria"))
    assert work.edit(
        "docs/specs/x.md", "Why the change exists.", "Why it exists, reworded."
    ) == (0, "", "")


def test_an_edit_that_adds_the_missing_spec_section_is_allowed(work) -> None:
    work.put("docs/specs/x.md", _spec_without("## Acceptance Criteria"))
    assert work.edit(
        "docs/specs/x.md",
        "- One module.\n",
        "- One module.\n\n## Acceptance Criteria\n\n- [ ] AC1 It works.\n",
    ) == (0, "", "")


def test_an_edit_that_drops_a_second_spec_section_is_refused_naming_only_it(
    work,
) -> None:
    work.put("docs/specs/x.md", _spec_without("## Architecture Specification"))
    code, _, err = work.edit("docs/specs/x.md", "## Intent Description\n", "")
    assert code == 2
    assert err.count("WHAT:") == 1
    assert 'WHAT: The spec has no "## Intent Description" section' in err
    assert "Architecture Specification" not in err


def test_the_hook_runs_end_to_end_in_a_fresh_interpreter(tmp_path: Path) -> None:
    payload = {
        "tool_name": "Write",
        "cwd": str(tmp_path),
        "tool_input": {
            "file_path": "plans/p.md",
            "content": _stranded_slice_two(),
        },
    }
    done = _run_hook(HOOK_PATH, payload, tmp_path)
    assert done.returncode == 2, done.stderr
    assert done.stderr.startswith("[BLOCK] feature record: plans/p.md")
    assert done.stdout == done.stderr


def test_a_matching_path_loads_the_record_modules_in_a_fresh_interpreter(
    tmp_path: Path,
) -> None:
    """Control for the fast-path test: a matching write does load them."""
    payload = _payload("plans/p.md", cwd=tmp_path, content=build_plan())
    result = _run_isolated(tmp_path, payload)
    assert result["code"] == 0
    assert {"feature_record", "plan_parse", "plan_record_parse"} <= set(
        result["loaded"]
    )


def _big_plan() -> str:
    six = tuple(
        {"covers": (f"AC{k}",), "scenarios": 2, "steps": 2} for k in range(1, 7)
    )
    plan = build_plan(slices=six, criteria=6, filler=260)
    assert len(plan.splitlines()) >= 500
    return plan


def test_a_generated_500_line_plan_is_checked_within_a_second(
    work, monkeypatch, capsys
) -> None:
    plan = _big_plan()
    assert hook._import_feature_record().plan_violations(plan, spec_text=None) == []
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


def test_a_cold_hook_process_checks_a_500_line_plan_within_a_generous_bound(
    tmp_path: Path,
) -> None:
    """Interpreter start-up and imports included; the bound is loose on purpose
    so a slow CI host does not flake, while a hang or quadratic parse would."""
    payload = _payload("plans/big.md", cwd=tmp_path, content=_big_plan())
    start = time.perf_counter()
    done = _run_hook(HOOK_PATH, payload, tmp_path)
    elapsed = time.perf_counter() - start
    assert (done.returncode, done.stdout, done.stderr) == (0, "", "")
    assert elapsed < 10.0, elapsed


# ---------------------------------------------------------------------------
# Step 4.3: refusal text (pinned copy) and the boundary event
# ---------------------------------------------------------------------------

NO_COVERS = tuple({**spec, "covers": ()} for spec in DEFAULT_SLICES)


def _stranded_slice_two() -> str:
    """Slice 2 has a scenario and no step; no `Covers` line, so nothing else breaks."""
    return build_plan(
        slices=(
            NO_COVERS[0],
            {"covers": (), "scenarios": 1, "steps": 0},
            NO_COVERS[2],
        )
    )


def _refusal(work, rel: str, content: str, **env) -> tuple[int, str, str]:
    return work.write(rel, content, env or None)


def test_refusal_text_for_scenario_no_step_is_the_pinned_copy(work) -> None:
    path = work.put("plans/p.md", build_plan(slices=NO_COVERS))
    before = path.read_bytes()
    code, out, err = _refusal(work, "plans/p.md", _stranded_slice_two())
    assert code == 2
    assert err == (
        "[BLOCK] feature record: plans/p.md - 1 violation(s) introduced\n"
        "\n"
        "WHAT: Slice 2 has a scenario and no step heading. [scenario-no-step]\n"
        "WHY: A scenario with no step is behavior nobody is told to build.\n"
        'HOW: Add a "#### Step 2.1: <title>" heading under **Steps:** in Slice 2.\n'
    )
    assert out == err
    assert path.read_bytes() == before


def test_refusal_text_for_ac_no_scenario_is_the_pinned_copy(work) -> None:
    uncovered = build_plan(slices=(DEFAULT_SLICES[0], DEFAULT_SLICES[1], NO_COVERS[2]))
    work.put("plans/p.md", build_plan())
    code, _, err = _refusal(work, "plans/p.md", uncovered)
    assert code == 2
    assert err == (
        "[BLOCK] feature record: plans/p.md - 1 violation(s) introduced\n"
        "\n"
        'WHAT: AC3 "Criterion 3" has no scenario: no step names it, or its '
        "covering slices have none. [ac-no-scenario]\n"
        "WHY: A criterion with no scenario has no behavior that proves it.\n"
        'HOW: Add "**Covers**: AC3" to a step, and a Scenario: under '
        "**Behavior:** in that step's slice.\n"
    )


def test_refusal_text_for_closed_slice_open_blocker_is_the_pinned_copy(work) -> None:
    work.put("plans/p.md", build_plan())
    blocked = build_plan(blockers=("Slice 2 - missing error path",), ticked=(2,))
    code, _, err = _refusal(work, "plans/p.md", blocked)
    assert code == 2
    assert err == (
        "[BLOCK] feature record: plans/p.md - 1 violation(s) introduced\n"
        "\n"
        "WHAT: Slice 2 is ticked done while an open blocker names it. "
        "[closed-slice-open-blocker]\n"
        "WHY: A critic blocker means the slice is not done.\n"
        'HOW: Resolve the blocker and add "**Resolved blocker**: Slice 2 - <text>" '
        "under ## Plan Review Summary, or untick Slice 2 under ## Build Progress.\n"
    )


def test_refusal_text_for_spec_missing_section_is_the_pinned_copy(work) -> None:
    work.put("docs/specs/x.md", COMPLETE_SPEC)
    code, _, err = _refusal(
        work, "docs/specs/x.md", _spec_without("## Architecture Specification")
    )
    assert code == 2
    assert err == (
        "[BLOCK] feature record: docs/specs/x.md - 1 violation(s) introduced\n"
        "\n"
        'WHAT: The spec has no "## Architecture Specification" section, or it is '
        "empty. [spec-missing-section]\n"
        "WHY: A plan built on an incomplete spec has no intent or criteria to "
        "check against.\n"
        'HOW: Add "## Architecture Specification" with at least one line of text.\n'
    )


def test_an_edit_refusal_adds_the_single_write_advice_to_how(work) -> None:
    work.put("plans/p.md", build_plan(slices=NO_COVERS))
    code, _, err = work.edit("plans/p.md", "#### Step 2.1: step", "Step 2.1: step")
    assert code == 2
    how = [line for line in err.splitlines() if line.startswith("HOW:")]
    assert how == [
        (
            'HOW: Add a "#### Step 2.1: <title>" heading under **Steps:** in Slice 2.'
            " Make the change in a single Edit or Write;"
            " the hook checks the state after each write."
        )
    ]


def test_a_write_refusal_has_no_single_write_advice(work) -> None:
    work.put("plans/p.md", build_plan(slices=NO_COVERS))
    _, _, err = _refusal(work, "plans/p.md", _stranded_slice_two())
    assert "single Edit or Write" not in err


def test_a_refusal_lists_at_most_five_violations(work) -> None:
    seven = build_plan(
        slices=tuple({"covers": (), "scenarios": 1, "steps": 0} for _ in range(7)),
        criteria=1,
    )
    code, _, err = _refusal(work, "plans/p.md", seven)
    assert code == 2
    lines = err.splitlines()
    assert lines[0] == "[BLOCK] feature record: plans/p.md - 7 violation(s) introduced"
    assert sum(line.startswith("WHAT:") for line in lines) == 5
    assert sum(line.startswith("WHY:") for line in lines) == 5
    assert sum(line.startswith("HOW:") for line in lines) == 5
    assert lines[-1] == "and 2 more."
    assert [ln for ln in lines if ln.startswith("WHAT:")][-1].startswith(
        "WHAT: Slice 5 has"
    )


def test_exactly_five_violations_have_no_overflow_line(work) -> None:
    five = build_plan(
        slices=tuple({"covers": (), "scenarios": 1, "steps": 0} for _ in range(5)),
        criteria=1,
    )
    _, _, err = _refusal(work, "plans/p.md", five)
    assert "more." not in err
    assert sum(line.startswith("WHAT:") for line in err.splitlines()) == 5


def _events(root: Path) -> list[dict]:
    log = root / ".claude" / "metrics" / "boundary-events.jsonl"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines()]


def test_a_refusal_emits_one_boundary_event(work, monkeypatch, capsys) -> None:
    work.put("plans/p.md", build_plan(slices=NO_COVERS))
    payload = {
        "tool_name": "Write",
        "cwd": str(work.root),
        "session_id": "sess-1",
        "tool_input": {"file_path": "plans/p.md", "content": _stranded_slice_two()},
    }
    assert _run_main(monkeypatch, capsys, payload)[0] == 2
    events = _events(work.root)
    assert len(events) == 1
    event = events[0]
    assert {k: event[k] for k in ("hook", "tool", "decision", "matched_rule")} == {
        "hook": "feature_record_guard",
        "tool": "Write",
        "decision": "block",
        "matched_rule": "feature-record-violation",
    }
    assert event["session_id"] == "sess-1"


def test_an_edit_refusal_records_the_edit_tool(work) -> None:
    work.put("plans/p.md", build_plan(slices=NO_COVERS))
    work.edit("plans/p.md", "#### Step 2.1: step", "Step 2.1: step")
    assert [e["tool"] for e in _events(work.root)] == ["Edit"]


def test_an_allowed_write_emits_no_event(work) -> None:
    work.write("plans/p.md", build_plan())
    assert _events(work.root) == []


def test_an_emitter_that_cannot_write_does_not_change_the_refusal(work) -> None:
    """A regular file at `<root>/.claude` makes the metrics directory
    impossible to create, a real fault in the emit path. The refusal text,
    stdout mirror and exit code are the same as with a working emitter.
    (`boundary_events` swallows the fault itself, before the hook's own
    try/except is reached; that second net is a one-line wrapper.)"""
    work.put("plans/p.md", build_plan(slices=NO_COVERS))
    with_emitter = _refusal(work, "plans/p.md", _stranded_slice_two())
    assert with_emitter[0] == 2 and len(_events(work.root)) == 1

    shutil.rmtree(work.root / ".claude")
    (work.root / ".claude").write_text("not a directory\n")
    assert _refusal(work, "plans/p.md", _stranded_slice_two()) == with_emitter
    assert (work.root / ".claude").is_file()
