"""The commit invariant of scripts/feature_record.py (#2275).

Library cases take a fake evidence callback; no git is involved. The CLI
cases run `view` and `check` against real temporary git repositories.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_SCRIPTS = _REPO_ROOT / "plugins" / "dev-team" / "scripts"
sys.path.insert(0, str(_SCRIPTS))
sys.path.insert(0, str(_SCRIPTS / "lib"))

import feature_record

# Unindented items, as the guardian reads them: a slice and two steps.
PLAN = """# Plan: sample

## Build Progress

- [x] Slice 1: Parse
- [x] Step 1.1: Parse a line
- [x] Add the builder
- [ ] Step 2.1: Build a file
"""


def _backed(by_id: dict[str, bool | None]):
    """A callback answering by item id; records every item it is asked about."""
    asked: list[dict] = []

    def callback(item):
        asked.append(item)
        return by_id[item["id"]]

    callback.asked = asked
    return callback


def _commit_backed(record) -> dict[str, bool | None]:
    return {i["id"]: i["commit_backed"] for i in record["build_progress"]["items"]}


def _ids(found) -> list[str]:
    return [v["subject"] for v in found if v["id"] == "tick-without-commit"]


def test_without_a_callback_every_item_is_null_and_not_evaluated():
    record = feature_record.build_record(PLAN)
    assert set(_commit_backed(record).values()) == {None}
    assert record["applicability"]["commit_evidence"] == "not-evaluated"
    assert feature_record.unverifiable(record) == []
    assert _ids(feature_record.violations(record)) == []


def test_a_callback_marks_the_record_evaluated():
    record = feature_record.build_record(PLAN, commit_evidence=lambda item: True)
    assert record["applicability"]["commit_evidence"] == "evaluated"


def test_the_callback_answers_land_on_the_ticked_items_of_either_kind():
    callback = _backed({"1": True, "1.1": False, "Add the builder": None})
    record = feature_record.build_record(PLAN, commit_evidence=callback)
    assert _commit_backed(record) == {
        "1": True,
        "1.1": False,
        "Add the builder": None,
        "2.1": None,
    }


def test_an_unticked_item_is_never_asked_and_stays_null():
    callback = _backed({"1": True, "1.1": True, "Add the builder": True})
    record = feature_record.build_record(PLAN, commit_evidence=callback)
    assert [i["id"] for i in callback.asked] == ["1", "1.1", "Add the builder"]
    assert _commit_backed(record)["2.1"] is None


def test_the_callback_is_given_the_item_it_is_asked_about():
    callback = _backed({"1": True, "1.1": True, "Add the builder": True})
    feature_record.build_record(PLAN, commit_evidence=callback)
    assert callback.asked[0]["kind"] == "slice"
    assert callback.asked[0]["header"] == "Slice 1: Parse"
    assert callback.asked[1]["kind"] == "step"


def test_a_callback_that_mutates_its_item_does_not_change_the_record():
    def callback(item):
        item["header"] = "tampered"
        item["done"] = False
        return True

    record = feature_record.build_record(PLAN, commit_evidence=callback)
    first = record["build_progress"]["items"][0]
    assert first["header"] == "Slice 1: Parse"
    assert first["done"] is True


def test_only_a_bool_counts_as_an_answer():
    record = feature_record.build_record(PLAN, commit_evidence=lambda item: "yes")
    assert set(_commit_backed(record).values()) == {None}
    record = feature_record.build_record(PLAN, commit_evidence=lambda item: 1)
    assert set(_commit_backed(record).values()) == {None}


def test_a_callback_that_raises_leaves_the_item_unverifiable():
    def callback(item):
        raise RuntimeError("git exploded")

    record = feature_record.build_record(PLAN, commit_evidence=callback)
    assert _commit_backed(record) == {
        "1": None,
        "1.1": None,
        "Add the builder": None,
        "2.1": None,
    }
    assert feature_record.unverifiable(record) == ["1", "1.1", "Add the builder"]


def test_an_unbacked_ticked_item_is_a_violation_naming_it():
    callback = _backed({"1": True, "1.1": False, "Add the builder": True})
    found = feature_record.violations(
        feature_record.build_record(PLAN, commit_evidence=callback)
    )
    assert _ids(found) == ["Step 1.1"]
    violation = found[0]
    assert violation["what"] == (
        "Step 1.1 is ticked done and no commit on this branch backs it. "
        "[tick-without-commit]"
    )
    assert (
        violation["why"]
        == "A tick with no commit claims work the history does not show."
    )
    assert violation["how"] == (
        "Commit the step (touching <declared files>), or untick it "
        "under ## Build Progress."
    )


def test_an_unbacked_slice_item_is_named_as_the_slice():
    callback = _backed({"1": False, "1.1": True, "Add the builder": True})
    found = feature_record.violations(
        feature_record.build_record(PLAN, commit_evidence=callback)
    )
    assert _ids(found) == ["Slice 1"]


def test_declared_files_on_an_item_fill_the_how_text():
    record = feature_record.build_record(
        PLAN,
        commit_evidence=_backed({"1": False, "1.1": True, "Add the builder": True}),
    )
    record["build_progress"]["items"][0]["declared_files"] = ["docs/b.md", "docs/c.md"]
    (found,) = feature_record.violations(record)
    assert "touching docs/b.md, docs/c.md" in found["how"]


def test_a_backed_or_unverifiable_item_is_not_a_violation():
    callback = _backed({"1": True, "1.1": None, "Add the builder": True})
    record = feature_record.build_record(PLAN, commit_evidence=callback)
    assert _ids(feature_record.violations(record)) == []
    assert feature_record.unverifiable(record) == ["1.1"]


def test_an_unticked_item_with_false_evidence_is_not_a_violation():
    record = feature_record.build_record(PLAN)
    record["applicability"]["commit_evidence"] = "evaluated"
    record["build_progress"]["items"][3]["commit_backed"] = False  # "- [ ] Step 2.1"
    assert _ids(feature_record.violations(record)) == []


def test_the_commit_violation_comes_after_the_structural_ones():
    plan = (
        "### Slice 1: Parse\n\n"
        + PLAN
        + "\n## Plan Review Summary\n\n**Open blocker**: Slice 1 - not done\n"
    )
    record = feature_record.build_record(
        plan,
        commit_evidence=_backed({"1": False, "1.1": True, "Add the builder": True}),
    )
    assert [v["id"] for v in feature_record.violations(record)] == [
        "closed-slice-open-blocker",
        "tick-without-commit",
    ]


def test_the_record_with_evidence_is_json_serialisable():
    record = feature_record.build_record(
        PLAN,
        commit_evidence=_backed({"1": True, "1.1": False, "Add the builder": None}),
    )
    assert json.loads(json.dumps(record)) == record


@pytest.mark.parametrize("text", ["", "x", "- [x] a\n" * 3, "\x00\x01- [x] b"])
def test_build_record_with_a_callback_is_total(text):
    record = feature_record.build_record(text, commit_evidence=lambda item: False)
    feature_record.violations(record)


# ---------------------------------------------------------------------------
# view and check against real git repositories
# ---------------------------------------------------------------------------

_GIT_SCRUB = (
    "GIT_DIR",
    "GIT_INDEX_FILE",
    "GIT_WORK_TREE",
    "GIT_PREFIX",
    "GIT_REFLOG_ACTION",
)


@pytest.fixture(autouse=True)
def _hermetic_git(monkeypatch, tmp_path):
    for key in _GIT_SCRUB:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/dev/null")
    # A temporary directory is outside any repository, even on a host whose
    # temp root sits inside one.
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env=dict(os.environ),
    )
    return result.stdout.strip()


def _init(cwd: Path, branch: str = "main") -> None:
    _git(cwd, "init", "-q", f"--initial-branch={branch}")
    _git(cwd, "config", "user.email", "test@test.com")
    _git(cwd, "config", "user.name", "Test")


def _commit(cwd: Path, name: str | None, message: str) -> None:
    if name is None:
        _git(cwd, "commit", "-q", "--allow-empty", "-m", message)
        return
    target = cwd / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("work\n")
    _git(cwd, "add", name)
    _git(cwd, "commit", "-q", "-m", message)


@pytest.fixture
def repo(tmp_path) -> Path:
    """`main` holds one seed commit; HEAD is on `feature` at that commit."""
    root = tmp_path / "repo"
    root.mkdir()
    _init(root)
    _commit(root, "seed.txt", "chore: seed")
    _git(root, "checkout", "-q", "-b", "feature")
    return root


def _slice_plan(*slices: tuple[str, str, bool]) -> str:
    """A plan with one `### Slice n: title` section per `(title, files, ticked)`
    and a Build Progress line for each."""
    body = []
    progress = []
    for number, (title, files, ticked) in enumerate(slices, start=1):
        body.append(f"### Slice {number}: {title}\n\n**Files:** {files}\n")
        progress.append(f"- [{'x' if ticked else ' '}] Slice {number}: {title}")
    return "\n".join(body) + "\n## Build Progress\n\n" + "\n".join(progress) + "\n"


def _write(root: Path, text: str) -> Path:
    plan = root / "plan.md"
    plan.write_text(text, encoding="utf-8")
    return plan


def _check(plan: Path, capsys) -> tuple[int, dict, str]:
    code = feature_record.main(["check", str(plan)])
    out, err = capsys.readouterr()
    return code, json.loads(out), err


def _view(plan: Path, capsys) -> dict:
    assert feature_record.main(["view", str(plan)]) == 0
    return json.loads(capsys.readouterr().out)


def _unbacked(result: dict) -> list[str]:
    return [
        v["subject"] for v in result["violations"] if v["id"] == "tick-without-commit"
    ]


PARSE = ("Parse", "`docs/a.md`", True)


def test_a_ticked_slice_with_a_commit_touching_its_declared_file_passes(repo, capsys):
    _commit(repo, "docs/a.md", "feat: wording that never names the slice")
    code, result, err = _check(_write(repo, _slice_plan(PARSE)), capsys)
    assert code == 0
    assert result["violations"] == []
    assert result["unverifiable"] == []
    assert err.strip() == "0 violations, 0 unverifiable"


def test_the_view_marks_a_ticked_slice_item_with_a_matching_commit_as_backed(
    repo, capsys
):
    _commit(repo, "docs/a.md", "feat: parse")
    record = _view(_write(repo, _slice_plan(PARSE)), capsys)
    (item,) = record["build_progress"]["items"]
    assert item["commit_backed"] is True
    assert record["applicability"]["commit_evidence"] == "evaluated"


def test_a_ticked_slice_with_no_commit_on_its_declared_file_is_a_violation(
    repo, capsys
):
    _commit(repo, "docs/a.md", "feat: parse")
    plan = _write(repo, _slice_plan(("Parse", "`docs/b.md`", True)))
    code, result, err = _check(plan, capsys)
    assert code == 1
    assert _unbacked(result) == ["Slice 1"]
    (violation,) = result["violations"]
    assert "docs/b.md" in violation["how"]
    assert err.strip() == "1 violations, 0 unverifiable"


def test_the_violation_names_every_declared_file(repo, capsys):
    _commit(repo, "docs/a.md", "feat: parse")
    plan = _write(repo, _slice_plan(("Parse", "`docs/b.md`, `docs/c.md`", True)))
    _, result, _ = _check(plan, capsys)
    assert "touching docs/b.md, docs/c.md" in result["violations"][0]["how"]


def test_a_commit_older_than_the_branch_base_does_not_back_a_slice(repo, capsys):
    _git(repo, "checkout", "-q", "main")
    _commit(repo, "docs/a.md", "feat: on main before the branch point")
    _git(repo, "checkout", "-q", "-b", "feature2")
    _commit(repo, "other.md", "feat: unrelated")
    code, result, _ = _check(_write(repo, _slice_plan(PARSE)), capsys)
    assert code == 1
    assert _unbacked(result) == ["Slice 1"]


def test_only_the_unbacked_ticked_item_is_reported(repo, capsys):
    _commit(repo, "docs/a.md", "feat: parse")
    plan = _write(
        repo,
        _slice_plan(PARSE, ("Build", "`docs/b.md`", True)),
    )
    code, result, _ = _check(plan, capsys)
    assert code == 1
    assert _unbacked(result) == ["Slice 2"]


def test_an_item_with_no_declared_files_falls_back_to_the_commit_subject(repo, capsys):
    _commit(repo, "x.txt", "feat: add the parser")
    plan = _write(repo, "## Build Progress\n\n- [x] Add the parser\n")
    code, result, _ = _check(plan, capsys)
    assert code == 0
    assert result["violations"] == []


def test_an_unindented_step_with_no_matching_subject_is_a_violation(repo, capsys):
    _commit(repo, "x.txt", "feat: something else")
    plan = _write(repo, "## Build Progress\n\n- [x] Step 1.1: Add the parser\n")
    code, result, _ = _check(plan, capsys)
    assert code == 1
    assert _unbacked(result) == ["Step 1.1"]


def test_an_indented_step_tick_is_not_an_item(repo, capsys):
    plan = _write(
        repo,
        "## Build Progress\n\n- [ ] Slice 1: Parse\n  - [x] Step 1.1: Parse a line\n",
    )
    code, result, _ = _check(plan, capsys)
    assert code == 0
    assert _unbacked(result) == []
    assert result["unverifiable"] == []


def test_an_unticked_item_is_not_reported_and_stays_null(repo, capsys):
    _commit(repo, "docs/a.md", "feat: parse")
    plan = _write(repo, _slice_plan(("Parse", "`docs/b.md`", False)))
    code, result, _ = _check(plan, capsys)
    assert code == 0
    assert result["violations"] == []
    record = _view(plan, capsys)
    assert [i["commit_backed"] for i in record["build_progress"]["items"]] == [None]


def test_the_view_reports_commit_evidence_per_ticked_item(repo, capsys):
    _commit(repo, "docs/a.md", "feat: parse")
    plan = _write(repo, _slice_plan(PARSE, ("Build", "`docs/b.md`", True)))
    record = _view(plan, capsys)
    assert [i["commit_backed"] for i in record["build_progress"]["items"]] == [
        True,
        False,
    ]


def test_a_detached_head_with_a_trunk_ref_still_has_a_base(repo, capsys):
    _commit(repo, "docs/a.md", "feat: parse")
    _git(repo, "checkout", "-q", "--detach")
    code, result, _ = _check(_write(repo, _slice_plan(PARSE)), capsys)
    assert code == 0
    assert result["violations"] == [] and result["unverifiable"] == []


def test_a_branch_whose_only_commit_past_the_base_is_a_merge_has_no_evidence(
    repo, capsys
):
    # The base resolves (main moved on), but the range holds only a merge commit.
    _git(repo, "checkout", "-q", "main")
    _commit(repo, "docs/a.md", "feat: lands on main")
    _git(repo, "checkout", "-q", "feature")
    _git(repo, "merge", "-q", "--no-ff", "-m", "Merge main", "main")
    code, result, _ = _check(_write(repo, _slice_plan(PARSE)), capsys)
    assert code == 0
    assert result["violations"] == []
    assert result["unverifiable"] == ["1"]


# One row per situation in the Gherkin Outline: evidence cannot be established.


def _no_commits_past_base(root: Path, monkeypatch) -> None:
    pass  # the `repo` fixture is already a branch at the trunk commit


def _no_resolvable_base(root: Path, monkeypatch) -> None:
    _git(root, "branch", "-m", "main", "dev")  # no main/master/origin ref left
    _git(root, "branch", "-m", "feature", "wip")
    _commit(root, "docs/a.md", "feat: parse")


def _detached_with_no_base(root: Path, monkeypatch) -> None:
    _no_resolvable_base(root, monkeypatch)
    _git(root, "checkout", "-q", "--detach")


def _git_error(root: Path, monkeypatch) -> None:
    _commit(root, "docs/a.md", "feat: parse")
    (root / ".git" / "HEAD").write_text("garbage\n")


def _git_missing(root: Path, monkeypatch) -> None:
    _commit(root, "docs/a.md", "feat: parse")
    monkeypatch.setenv("PATH", str(root / "no-bin"))


SITUATIONS = {
    "no-commits-past-base": _no_commits_past_base,
    "no-resolvable-base": _no_resolvable_base,
    "detached-head-no-base": _detached_with_no_base,
    "git-error": _git_error,
    "git-missing": _git_missing,
}


@pytest.mark.parametrize("situation", list(SITUATIONS))
def test_a_ticked_item_whose_evidence_cannot_be_established_is_unverifiable(
    situation, repo, monkeypatch, capsys
):
    SITUATIONS[situation](repo, monkeypatch)
    plan = _write(repo, _slice_plan(PARSE))
    code, result, err = _check(plan, capsys)
    assert code == 0
    assert result["violations"] == []
    assert result["unverifiable"] == ["1"]
    assert err.strip() == "0 violations, 1 unverifiable"
    assert _view(plan, capsys)["build_progress"]["items"][0]["commit_backed"] is None


def test_a_plan_outside_any_repository_is_unverifiable(tmp_path, capsys):
    plan = _write(tmp_path, _slice_plan(PARSE))
    code, result, err = _check(plan, capsys)
    assert code == 0
    assert result["violations"] == []
    assert result["unverifiable"] == ["1"]
    assert err.strip() == "0 violations, 1 unverifiable"


def test_every_unbacked_tick_is_reported_and_sets_the_exit_code(repo, capsys):
    _commit(repo, "docs/a.md", "feat: parse")
    plan = _write(
        repo,
        "## Build Progress\n\n- [x] Slice 1: Parse\n- [x] Slice 2: Build\n",
    )
    # Slice 1 and 2 declare nothing; neither subject matches: both unbacked.
    code, result, _ = _check(plan, capsys)
    assert code == 1
    assert _unbacked(result) == ["Slice 1", "Slice 2"]


def test_git_is_not_run_when_nothing_is_ticked(repo, monkeypatch, capsys):
    import commit_evidence

    def fail(*args, **kwargs):
        raise AssertionError("git ran for a plan with no ticked item")

    monkeypatch.setattr(commit_evidence, "run_git", fail)
    plan = _write(repo, _slice_plan(("Parse", "`docs/a.md`", False)))
    code, result, _ = _check(plan, capsys)
    assert code == 0 and result["unverifiable"] == []


def test_git_is_read_once_however_many_items_are_ticked(repo, monkeypatch, capsys):
    import commit_evidence

    _commit(repo, "docs/a.md", "feat: parse")
    calls: list[list[str]] = []
    real = commit_evidence.run_git

    def counting(args, cwd):
        calls.append(args)
        return real(args, cwd)

    monkeypatch.setattr(commit_evidence, "run_git", counting)
    _check(_write(repo, _slice_plan(PARSE)), capsys)
    for_one_item = len(calls)
    calls.clear()
    _check(_write(repo, _slice_plan(PARSE, ("Build", "`docs/a.md`", True))), capsys)
    assert for_one_item > 0
    assert len(calls) == for_one_item


def test_the_script_exits_1_for_an_unbacked_tick_in_a_real_repository(repo):
    _commit(repo, "docs/a.md", "feat: parse")
    plan = _write(repo, _slice_plan(("Parse", "`docs/b.md`", True)))
    result = subprocess.run(
        [sys.executable, str(_SCRIPTS / "feature_record.py"), "check", str(plan)],
        capture_output=True,
        text=True,
        check=False,
        env=dict(os.environ),
    )
    assert result.returncode == 1, result.stderr
    assert _unbacked(json.loads(result.stdout)) == ["Slice 1"]


# ---------------------------------------------------------------------------
# module boundaries
# ---------------------------------------------------------------------------


def _top_level_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_feature_record_has_no_module_level_import_of_the_guardian_or_git_rule():
    imported = _top_level_imports(_SCRIPTS / "feature_record.py")
    assert "progress_guardian" not in imported
    assert "commit_evidence" not in imported


@pytest.mark.parametrize(
    "imports",
    [
        "import progress_guardian\nimport feature_record",
        "import feature_record\nimport progress_guardian",
    ],
    ids=["guardian-first", "record-first"],
)
def test_the_two_modules_share_one_plan_parse_and_one_commit_evidence(
    imports, tmp_path
):
    plan = tmp_path / "plan.md"
    plan.write_text(_slice_plan(PARSE), encoding="utf-8")
    script = (
        f"import sys; sys.path.insert(0, {str(_SCRIPTS)!r})\n"
        f"{imports}\n"
        f"feature_record.main(['check', {str(plan)!r}])\n"
        "def count(name):\n"
        "    return [k for k in sys.modules if k.split('.')[-1] == name]\n"
        "assert count('plan_parse') == ['plan_parse'], count('plan_parse')\n"
        "assert count('commit_evidence') == ['commit_evidence'], count('commit_evidence')\n"
        "assert progress_guardian.commit_evidence is sys.modules['commit_evidence']\n"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", script],
        capture_output=True,
        text=True,
        check=False,
        env=dict(os.environ),
    )
    assert result.returncode == 0, result.stderr
