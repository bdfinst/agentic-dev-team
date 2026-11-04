"""Tests for hooks/feature_record_guard.py (#2275, Slice 4).

Step 4.1 covers the path matcher, the payload layer and the no-work fast path.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_HOOKS_DIR = Path(__file__).resolve().parents[2] / "hooks"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

import feature_record_guard as hook  # type: ignore[import-not-found]

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
