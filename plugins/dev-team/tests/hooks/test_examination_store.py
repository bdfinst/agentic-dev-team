"""Unit tests for hooks/lib/examination_store.py (#2270, Step 1.3)."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_HOOKS_LIB = Path(__file__).resolve().parents[2] / "hooks" / "lib"
if str(_HOOKS_LIB) not in sys.path:
    sys.path.insert(0, str(_HOOKS_LIB))

_TESTS_LIB = Path(__file__).resolve().parents[2] / "tests" / "lib"
if str(_TESTS_LIB) not in sys.path:
    sys.path.insert(0, str(_TESTS_LIB))

import atomic_state  # type: ignore[import-not-found]
import examination_store as store  # type: ignore[import-not-found]
from hermetic import hermetic_git_env  # type: ignore[import-not-found]

PLAN_ID = "plans/x.md"
HASH_A = "a" * 64


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _commit_file(root: Path, rel: str, content: str, message: str) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    _git(root, "add", rel)
    _git(root, "commit", "-q", "-m", message)


def _init(root: Path, branch: str) -> None:
    root.mkdir()
    _git(root, "init", "-q", "-b", branch)
    _git(root, "config", "init.defaultBranch", "main")
    _git(root, "config", "user.name", "tester")
    _git(root, "config", "user.email", "t@t.dev")


@pytest.fixture(autouse=True)
def _hermetic_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Production code under test shells out to git with the process env, so
    pin that env: no global/system config, no inherited GIT_DIR and friends,
    and no discovery of a repo above tmp_path."""
    wanted = hermetic_git_env(home=tmp_path)
    for key in set(os.environ) - set(wanted):
        monkeypatch.delenv(key)
    for key, value in wanted.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """`main` as base, `work` one commit ahead; the plan is tracked on `work`."""
    root = tmp_path / "repo"
    _init(root, "main")
    _commit_file(root, "base.txt", "base\n", "base")
    _git(root, "checkout", "-q", "-b", "work")
    _commit_file(root, PLAN_ID, "# plan\n", "add plan")
    return root


def _valid_record() -> dict:
    return {
        "schema": 1,
        "plan": PLAN_ID,
        "overall": "met",
        "criteria": [],
        "binding_hash": HASH_A,
        "inputs_digest": "b" * 64,
    }


# --- binding ---------------------------------------------------------------


def test_binding_hash_ignores_a_plan_only_commit(repo: Path) -> None:
    before = store.current_binding(repo, PLAN_ID)
    _commit_file(repo, PLAN_ID, "# plan\n- [x] ticked\n", "tick plan")
    assert store.current_binding(repo, PLAN_ID) == before


def test_binding_hash_changes_on_a_source_commit(repo: Path) -> None:
    before = store.current_binding(repo, PLAN_ID)
    _commit_file(repo, "src/app.py", "print(1)\n", "add source")
    assert store.current_binding(repo, PLAN_ID) != before


def test_binding_hash_is_a_binding_hash(repo: Path) -> None:
    _commit_file(repo, "src/app.py", "print(1)\n", "add source")
    assert store.is_binding_hash(store.current_binding(repo, PLAN_ID))


def test_binding_is_unresolvable_without_a_base_ref(tmp_path: Path) -> None:
    root = tmp_path / "solo"
    _init(root, "work")
    _commit_file(root, "a.txt", "1\n", "one")
    _commit_file(root, "b.txt", "2\n", "two")
    assert store.current_binding(root, PLAN_ID) == store.BASE_UNRESOLVABLE


def test_binding_is_empty_diff_when_work_equals_main(tmp_path: Path) -> None:
    root = tmp_path / "same"
    _init(root, "main")
    _commit_file(root, "base.txt", "base\n", "base")
    _git(root, "checkout", "-q", "-b", "work")
    assert store.current_binding(root, PLAN_ID) == store.EMPTY_DIFF


def test_binding_is_empty_diff_when_only_the_plan_differs(repo: Path) -> None:
    assert store.current_binding(repo, PLAN_ID) == store.EMPTY_DIFF


@pytest.mark.parametrize(
    "value",
    [HASH_A, hashlib.sha256(b"x").hexdigest()],
)
def test_is_binding_hash_accepts_a_sha256_hex_digest(value: str) -> None:
    assert store.is_binding_hash(value)


@pytest.mark.parametrize(
    "value",
    [
        store.BASE_UNRESOLVABLE,
        store.EMPTY_DIFF,
        hashlib.sha256(b"").hexdigest(),
        "A" * 64,
        "a" * 63,
        "",
        None,
        12,
    ],
)
def test_is_binding_hash_rejects_everything_else(value: object) -> None:
    assert not store.is_binding_hash(value)


# --- identity --------------------------------------------------------------


def test_canonical_plan_id_is_repo_relative_whatever_form_is_given(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (repo / "sub").mkdir()
    plan = repo / PLAN_ID
    from_absolute = store.canonical_plan_id(plan, repo)
    monkeypatch.chdir(repo)
    from_relative = store.canonical_plan_id(Path(PLAN_ID), repo)
    monkeypatch.chdir(repo / "sub")
    from_parent = store.canonical_plan_id(Path("..") / PLAN_ID, repo)
    assert (from_absolute, from_relative, from_parent) == (PLAN_ID,) * 3


def test_canonical_plan_id_rejects_a_plan_outside_the_root(
    repo: Path, tmp_path: Path
) -> None:
    with pytest.raises(ValueError):
        store.canonical_plan_id(tmp_path / "elsewhere.md", repo)


def test_repo_root_from_a_file_inside_a_subdirectory(repo: Path) -> None:
    (repo / "sub").mkdir()
    assert store.repo_root(repo / "sub" / "plan.md") == repo.resolve()


def test_repo_root_outside_a_repository_raises(tmp_path: Path) -> None:
    outside = tmp_path / "plain"
    outside.mkdir()
    with pytest.raises(store.NotARepository):
        store.repo_root(outside / "plan.md")


def test_same_stem_plans_in_different_directories_have_different_records(
    repo: Path,
) -> None:
    first = store.record_path(repo, "plans/x.md")
    second = store.record_path(repo, "docs/plans/x.md")
    assert first != second


def test_record_path_lives_in_the_memory_dir_with_escaped_separators(
    repo: Path,
) -> None:
    expected = repo / ".claude" / "memory" / "acceptance-examination-plans__x.md.json"
    assert store.record_path(repo, "plans/x.md") == expected


# --- persistence -----------------------------------------------------------


def test_record_round_trips_through_the_store(tmp_path: Path) -> None:
    path = tmp_path / "memory" / "record.json"
    record = _valid_record()
    store.write_record(path, record)
    assert store.read_record(path) == record


def test_write_record_creates_the_parent_directory(tmp_path: Path) -> None:
    path = tmp_path / "does" / "not" / "exist" / "record.json"
    store.write_record(path, _valid_record())
    assert path.is_file()


def test_write_record_replaces_an_existing_record(tmp_path: Path) -> None:
    path = tmp_path / "record.json"
    store.write_record(path, _valid_record())
    newer = {**_valid_record(), "overall": "not-met"}
    store.write_record(path, newer)
    assert store.read_record(path) == newer


def test_write_record_leaves_no_temp_file_behind(tmp_path: Path) -> None:
    path = tmp_path / "record.json"
    store.write_record(path, _valid_record())
    assert sorted(
        p.name for p in tmp_path.iterdir() if p.name != "record.json.lock"
    ) == ["record.json"]


def test_write_record_propagates_a_write_failure(tmp_path: Path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, not a directory")
    with pytest.raises(atomic_state.LockAcquisitionError):
        store.write_record(blocker / "record.json", _valid_record())


def test_tainted_overall_is_readable(tmp_path: Path) -> None:
    path = tmp_path / "record.json"
    path.write_text(json.dumps({**_valid_record(), "overall": "tainted"}))
    assert store.read_record(path)["overall"] == "tainted"


def _without(key: str) -> dict:
    record = _valid_record()
    del record[key]
    return record


@pytest.mark.parametrize(
    ("content", "problem"),
    [
        pytest.param("", "invalid JSON", id="empty-file"),
        pytest.param("{not json", "invalid JSON", id="not-valid-json"),
        pytest.param(b"\xff\xfe\x00", "invalid JSON", id="not-utf8"),
        pytest.param(json.dumps([1, 2]), "not an object", id="json-array"),
        pytest.param(
            json.dumps(_without("binding_hash")),
            "missing key binding_hash",
            id="missing-binding-hash",
        ),
        pytest.param(
            json.dumps(_without("inputs_digest")),
            "missing key inputs_digest",
            id="missing-inputs-digest",
        ),
        pytest.param(
            json.dumps({**_valid_record(), "criteria": {}}),
            "invalid criteria",
            id="criteria-not-a-list",
        ),
        pytest.param(
            json.dumps({**_valid_record(), "plan": 7}),
            "invalid plan",
            id="plan-not-a-string",
        ),
        pytest.param(
            json.dumps({**_valid_record(), "schema": 2}),
            "unsupported schema",
            id="schema-2",
        ),
        pytest.param(
            json.dumps({**_valid_record(), "schema": True}),
            "unsupported schema",
            id="schema-true",
        ),
        pytest.param(
            json.dumps(_without("schema")),
            "unsupported schema",
            id="schema-absent",
        ),
        pytest.param(
            json.dumps({**_valid_record(), "overall": "pass"}),
            "invalid overall",
            id="overall-pass",
        ),
    ],
)
def test_malformed_record_is_unreadable_naming_the_problem(
    tmp_path: Path, content: str | bytes, problem: str
) -> None:
    path = tmp_path / "record.json"
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content)
    with pytest.raises(store.RecordUnreadable) as caught:
        store.read_record(path)
    assert caught.value.problem == problem


def test_missing_record_file_is_absent_not_unreadable(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        store.read_record(tmp_path / "nope.json")
