"""Tests for plugins/dev-team/scripts/lane.py: the command line and `open`.

Every test runs in-process against real git repositories built by
`lane_fixtures`. The refusal registry, the git seam, trunk resolution and lane
detection are tested in `test_lane_core.py`.
"""

# Fixtures from lane_fixtures are imported by name so pytest finds them; a
# test argument of the same name then looks like an unused import and a
# redefinition to ruff.
# ruff: noqa: F401, F811

from __future__ import annotations

import argparse
import ast
import dataclasses
import re
import stat
import sys
from pathlib import Path

import pytest
from lane_fixtures import (
    GIT_FAILED,
    add_linked_worktree,
    argv_spy,
    build_repo_with_origin,
    build_repo_without_remote,
    commit_file,
    covers,
    default_lane_dir,
    enforce_covers,
    git,
    hermetic_process_env,
    imported_modules,
    lane_state,
    merge_in_progress,
    non_stdlib,
    parse_blocks,
    parse_output,
    repo_with_origin,
    repo_without_default_branch,
    repo_without_remote,
    single_refusal,
    unchanged_state,
)

from _repo_root import REPO_ROOT

SCRIPTS_DIR = REPO_ROOT / "plugins" / "dev-team" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import lane
import lane_core

#: An invalid name and the part of the reason that says which check refused it.
PATTERN_REASON = "safe characters"
GIT_RULE_REASON = "git does not accept"
INVALID_NAMES = [
    ("bad name", PATTERN_REASON),
    ("a;b", PATTERN_REASON),
    ("x~1", PATTERN_REASON),
    ("a..b", GIT_RULE_REASON),
    ("a//b", GIT_RULE_REASON),
    ("feat.lock", GIT_RULE_REASON),
]


def run_main(argv, cwd, capsys):
    code = lane.main(argv, cwd=cwd)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


@pytest.fixture
def open_handler(monkeypatch):
    """Replace the real `open` handler to drive the renderer with a fault."""

    def install(handler):
        original = lane.COMMANDS[lane.OPEN_COMMAND]
        replaced = dataclasses.replace(original, handler=lambda args, cwd: handler(cwd))
        monkeypatch.setitem(lane.COMMANDS, lane.OPEN_COMMAND, replaced)

    return install


def worktree_paths(cwd: Path) -> list[str]:
    porcelain = git(cwd, "worktree", "list", "--porcelain")
    return [
        line.removeprefix("worktree ")
        for line in porcelain.splitlines()
        if line.startswith("worktree ")
    ]


def skip_first_call(monkeypatch, name: str) -> None:
    """Make the first call to `lane.<name>` a no-op; later calls are real."""
    real = getattr(lane, name)
    calls: list[int] = []

    def stub(*args):
        if calls:
            return real(*args)
        calls.append(1)
        return None

    monkeypatch.setattr(lane, name, stub)


# --- the command line -------------------------------------------------------


def test_help_exits_zero_and_lists_open_among_the_commands(tmp_path, capsys):
    code, out, _ = run_main(["--help"], tmp_path, capsys)

    assert code == 0
    assert re.search(r"^\s+open\s+create a lane", out, re.MULTILINE)


def test_open_is_a_registered_command_with_its_own_arguments():
    args = lane.build_parser().parse_args(["open", "x", "--path", "p", "--trunk", "t"])

    assert (args.command, args.name, args.path, args.trunk) == ("open", "x", "p", "t")


def test_compose_is_a_registered_command_that_takes_only_a_trunk():
    args = lane.build_parser().parse_args(["compose", "--trunk", "t"])

    assert (args.command, args.trunk) == ("compose", "t")


def test_help_lists_compose(tmp_path, capsys):
    _, out, _ = run_main(["--help"], tmp_path, capsys)

    assert re.search(r"^\s+compose\s+merge trunk into the lane", out, re.MULTILINE)


def test_every_registered_command_is_keyed_by_its_own_name():
    assert {key: command.name for key, command in lane.COMMANDS.items()} == {
        key: key for key in lane.COMMANDS
    }


def test_the_parser_exposes_exactly_the_registered_commands():
    parser = lane.build_parser()
    (subparsers,) = [
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    ]

    assert set(subparsers.choices) == set(lane.COMMANDS)


def test_a_command_name_is_written_once_and_used_for_its_parser(monkeypatch):
    renamed = dataclasses.replace(lane.COMMANDS[lane.OPEN_COMMAND], name="renamed")
    monkeypatch.setattr(lane, "COMMANDS", {renamed.name: renamed})

    args = lane.build_parser().parse_args(["renamed", "x"])

    assert (args.command, args.name) == ("renamed", "x")


def test_trunk_help_names_the_default_trunk_rule(tmp_path, capsys):
    code, out, _ = run_main(["open", "--help"], tmp_path, capsys)

    flattened = " ".join(out.split())
    assert code == 0
    assert "origin's default branch, else main or master" in flattened


def test_a_missing_subcommand_is_a_usage_error(tmp_path, capsys):
    code, _, err = run_main([], tmp_path, capsys)

    assert code == 2
    assert "usage" in err


@covers("git command failed")
def test_a_refusal_prints_a_complete_block_on_stderr_and_exits_one(
    repo_without_remote, capsys, open_handler
):
    open_handler(
        lambda cwd: lane_core.git_text(["rev-parse", "--verify", "no-such"], cwd)
    )

    code, out, err = run_main(["open", "x"], repo_without_remote.path, capsys)

    block = single_refusal(code, out, err, GIT_FAILED)
    assert "\x1b" not in err
    assert "no-such" in block["why"]


@covers("git command failed")
def test_a_guard_hit_renders_a_git_command_failed_block(
    repo_without_remote, capsys, open_handler
):
    open_handler(lambda cwd: lane_core._git(["push", "origin", "main"], cwd).returncode)

    code, out, err = run_main(["open", "x"], repo_without_remote.path, capsys)

    block = single_refusal(code, out, err, GIT_FAILED)
    assert "subcommand push" in block["why"]


def test_lane_imports_only_stdlib_lane_core_and_the_origin_classifier():
    """The whitelist of plan decision 1 and A7, as far as this module uses it."""
    modules = imported_modules(SCRIPTS_DIR / "lane.py")

    assert non_stdlib(modules) == {"lane_core", "git_origin_host"}


#: Private `lane_core` names `lane.py` may use. Empty: everything it needs is public.
ALLOWED_PRIVATE_CORE_NAMES: frozenset[str] = frozenset()


def private_core_references(source: str) -> set[str]:
    """Private `lane_core` names a module reads: `lane_core._x` or `from lane_core import _x`."""
    tree = ast.parse(source)
    aliases = {"lane_core"}
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            aliases.update(
                alias.asname or alias.name
                for alias in node.names
                if alias.name == "lane_core"
            )
        if isinstance(node, ast.ImportFrom) and node.module == "lane_core":
            found.update(a.name for a in node.names if a.name.startswith("_"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in aliases
            and node.attr.startswith("_")
        ):
            found.add(node.attr)
    return found


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import lane_core\nlane_core._run([], 1)", {"_run"}),
        ("import lane_core\nlane_core._git([], 1)", {"_git"}),
        ("import lane_core as core\ncore._commit_of('x')", {"_commit_of"}),
        ("from lane_core import _run", {"_run"}),
        ("import lane_core\nlane_core.git_text([], 1)", set()),
        ("import lane_core\nother._run()", set()),
    ],
)
def test_the_seam_check_sees_private_core_references(source, expected):
    assert private_core_references(source) == expected


def test_lane_reaches_lane_core_only_through_its_public_names():
    source = (SCRIPTS_DIR / "lane.py").read_text(encoding="utf-8")

    assert private_core_references(source) - ALLOWED_PRIVATE_CORE_NAMES == set()


# --- open: the new lane -----------------------------------------------------


def test_open_creates_a_linked_worktree_at_the_sibling_default_path(
    repo_without_remote, capsys
):
    expected = default_lane_dir(repo_without_remote, "feature-x")

    code, _, _ = run_main(["open", "feature-x"], repo_without_remote.path, capsys)

    assert code == 0
    assert str(expected) in worktree_paths(repo_without_remote.path)
    assert (expected / "base.txt").is_file()


def test_open_points_the_branch_at_the_former_trunk_tip(repo_without_remote, capsys):
    former_tip = git(repo_without_remote.path, "rev-parse", "main")

    run_main(["open", "feature-x"], repo_without_remote.path, capsys)

    assert git(repo_without_remote.path, "rev-parse", "feature-x") == former_tip


def test_open_prints_worktree_and_branch_lines(repo_without_remote, capsys):
    code, out, err = run_main(["open", "feature-x"], repo_without_remote.path, capsys)

    expected = default_lane_dir(repo_without_remote, "feature-x")
    assert (code, err) == (0, "")
    assert out == f"worktree: {expected}\nbranch: feature-x\n"


def test_open_maps_a_slash_in_the_name_to_a_dash_in_the_path(
    repo_without_remote, capsys
):
    code, out, _ = run_main(["open", "feature/x"], repo_without_remote.path, capsys)

    assert code == 0
    assert parse_output(out) == {
        "worktree": str(default_lane_dir(repo_without_remote, "feature-x")),
        "branch": "feature/x",
    }
    assert git(
        repo_without_remote.path, "rev-parse", "--verify", "refs/heads/feature/x"
    )


def test_an_opened_lane_is_a_lane_beside_the_primary(repo_without_remote, capsys):
    _, out, _ = run_main(["open", "A"], repo_without_remote.path, capsys)

    context = lane_core.lane_context("main", Path(parse_output(out)["worktree"]))

    assert context is not None
    assert context.branch == "A"
    assert context.primary_path == repo_without_remote.path.resolve()


def test_open_from_inside_a_lane_places_the_new_lane_beside_the_primary(
    repo_without_remote, capsys
):
    lane_a = add_linked_worktree(repo_without_remote, "A")

    code, out, _ = run_main(["open", "B"], lane_a, capsys)

    assert code == 0
    assert parse_output(out)["worktree"] == str(
        default_lane_dir(repo_without_remote, "B")
    )


def test_open_branches_from_the_trunk_ref_not_a_local_branch_that_ran_ahead(
    repo_with_origin, capsys
):
    origin_tip = git(repo_with_origin.path, "rev-parse", "origin/main")
    commit_file(repo_with_origin.path, "local.txt", "local\n", "local only")

    run_main(["open", "feature-x"], repo_with_origin.path, capsys)

    assert git(repo_with_origin.path, "rev-parse", "feature-x") == origin_tip


def test_open_honours_path(repo_without_remote, tmp_path, capsys):
    target = tmp_path / "custom-lane"

    code, out, _ = run_main(
        ["open", "feature-y", "--path", str(target)], repo_without_remote.path, capsys
    )

    assert code == 0
    assert parse_output(out)["worktree"] == str(target)
    assert str(target.resolve()) in worktree_paths(repo_without_remote.path)


def test_open_honours_trunk(repo_without_remote, capsys):
    repo = repo_without_remote.path
    git(repo, "switch", "-q", "-c", "dev")
    dev_tip = commit_file(repo, "dev.txt", "dev\n", "dev work")
    git(repo, "switch", "-q", "main")

    code, out, _ = run_main(["open", "feature-y", "--trunk", "dev"], repo, capsys)

    assert code == 0
    assert git(repo, "rev-parse", "feature-y") == dev_tip
    assert (Path(parse_output(out)["worktree"]) / "dev.txt").is_file()


@pytest.mark.parametrize("trunk", ["refs/heads/main", "heads/main"])
def test_open_accepts_a_full_or_partial_ref_name_as_trunk(
    trunk, repo_without_remote, capsys
):
    code, _, _ = run_main(
        ["open", "feature-y", "--trunk", trunk], repo_without_remote.path, capsys
    )

    assert code == 0
    assert git(repo_without_remote.path, "rev-parse", "feature-y") == git(
        repo_without_remote.path, "rev-parse", "main"
    )


def test_open_registers_a_relative_path_against_the_working_directory(
    repo_without_remote, tmp_path, capsys
):
    code, out, _ = run_main(
        ["open", "feature-y", "--path", "../elsewhere"],
        repo_without_remote.path,
        capsys,
    )

    expected = (tmp_path / "elsewhere").resolve()
    assert code == 0
    assert Path(parse_output(out)["worktree"]).resolve() == expected
    assert str(expected) in worktree_paths(repo_without_remote.path)


def test_open_resolves_a_relative_working_directory_once(
    repo_without_remote, tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)

    code, out, _ = run_main(
        ["open", "feature-y", "--path", "lane-y"], Path("repo"), capsys
    )

    expected = (repo_without_remote.path / "lane-y").resolve()
    assert code == 0
    assert Path(parse_output(out)["worktree"]) == expected
    assert str(expected) in worktree_paths(repo_without_remote.path)


# --- open: refusals ---------------------------------------------------------


@pytest.mark.parametrize(("name", "reason"), INVALID_NAMES)
@covers("invalid lane name")
def test_open_refuses_an_invalid_name_and_says_which_check_refused_it(
    name, reason, repo_without_remote, capsys, argv_spy
):
    state_before = lane_state(repo_without_remote.path)
    records_before = len(argv_spy.records)

    code, out, err = run_main(["open", name], repo_without_remote.path, capsys)

    block = single_refusal(code, out, err, "invalid lane name")
    assert repr(name) in block["why"]
    assert reason in block["why"]
    assert "letters, digits" in block["how"]
    assert lane_state(repo_without_remote.path) == state_before
    mentioning = [
        argv
        for argv in argv_spy.records[records_before:]
        if any(name in token for token in argv)
    ]
    # A pattern failure never reaches git. A name the pattern allows reaches
    # git only in the check that refuses it.
    if reason == PATTERN_REASON:
        assert mentioning == []
    else:
        assert mentioning != []
        assert all("check-ref-format" in argv for argv in mentioning)


@covers("invalid lane name")
def test_open_refuses_a_leading_dash_name_given_after_double_dash(
    repo_without_remote, capsys, argv_spy
):
    state_before = lane_state(repo_without_remote.path)
    records_before = len(argv_spy.records)

    code, out, err = run_main(["open", "--", "-lead"], repo_without_remote.path, capsys)

    block = single_refusal(code, out, err, "invalid lane name")
    assert "'-lead'" in block["why"]
    assert PATTERN_REASON in block["why"]
    assert "letters, digits" in block["how"]
    assert lane_state(repo_without_remote.path) == state_before
    assert [argv for argv in argv_spy.records[records_before:] if "-lead" in argv] == []


def test_a_leading_dash_name_without_double_dash_is_a_usage_error(
    repo_without_remote, capsys
):
    state_before = lane_state(repo_without_remote.path)

    code, out, err = run_main(["open", "-lead"], repo_without_remote.path, capsys)

    assert code == 2
    assert out == ""
    assert "usage" in err
    assert lane_state(repo_without_remote.path) == state_before


@covers("branch exists")
def test_open_refuses_an_existing_branch(repo_without_remote, capsys):
    git(repo_without_remote.path, "branch", "taken")
    state_before = lane_state(repo_without_remote.path)

    code, out, err = run_main(["open", "taken"], repo_without_remote.path, capsys)

    block = single_refusal(code, out, err, "branch exists")
    assert "'taken'" in block["why"]
    assert "another name" in block["how"]
    assert "git branch -d taken" in block["how"]
    assert lane_state(repo_without_remote.path) == state_before
    assert not default_lane_dir(repo_without_remote, "taken").exists()


@covers("path exists")
def test_open_refuses_an_existing_path(repo_without_remote, tmp_path, capsys):
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    state_before = lane_state(repo_without_remote.path)

    code, out, err = run_main(
        ["open", "feature-x", "--path", str(occupied)], repo_without_remote.path, capsys
    )

    block = single_refusal(code, out, err, "path exists")
    assert str(occupied) in block["why"]
    assert "--path" in block["how"]
    assert lane_state(repo_without_remote.path) == state_before


@covers("path exists")
def test_open_refuses_a_default_path_that_is_taken(repo_without_remote, capsys):
    taken = default_lane_dir(repo_without_remote, "feature-x")
    taken.mkdir()
    state_before = lane_state(repo_without_remote.path)

    code, out, err = run_main(["open", "feature-x"], repo_without_remote.path, capsys)

    block = single_refusal(code, out, err, "path exists")
    assert str(taken) in block["why"]
    assert lane_state(repo_without_remote.path) == state_before


@covers("trunk ref cannot be resolved")
def test_open_refuses_a_trunk_that_does_not_resolve(repo_without_remote, capsys):
    state_before = lane_state(repo_without_remote.path)

    code, out, err = run_main(
        ["open", "feature-x", "--trunk", "missing-ref"],
        repo_without_remote.path,
        capsys,
    )

    block = single_refusal(code, out, err, "trunk ref cannot be resolved")
    assert "'missing-ref'" in block["why"]
    assert "--trunk <ref>" in block["how"]
    assert "git remote set-head origin -a" in block["how"]
    assert lane_state(repo_without_remote.path) == state_before
    assert not default_lane_dir(repo_without_remote, "feature-x").exists()


@covers("trunk ref cannot be resolved")
def test_open_refuses_when_no_default_trunk_exists(repo_without_default_branch, capsys):
    state_before = lane_state(repo_without_default_branch)

    code, out, err = run_main(
        ["open", "feature-x"], repo_without_default_branch, capsys
    )

    block = single_refusal(code, out, err, "trunk ref cannot be resolved")
    assert "no --trunk was given" in block["why"]
    assert "git remote set-head origin -a" in block["how"]
    assert lane_state(repo_without_default_branch) == state_before


@covers("trunk ref cannot be resolved")
def test_open_names_a_default_trunk_that_does_not_resolve(repo_without_remote, capsys):
    repo = repo_without_remote.path
    git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/gone")

    code, out, err = run_main(["open", "feature-x"], repo, capsys)

    block = single_refusal(code, out, err, "trunk ref cannot be resolved")
    assert "'origin/gone'" in block["why"]


@covers("not a git repository")
def test_open_outside_a_repository_is_a_refusal_block(tmp_path, capsys):
    plain = tmp_path / "plain"
    plain.mkdir()

    code, out, err = run_main(["open", "x"], plain, capsys)

    block = single_refusal(code, out, err, "not a git repository")
    assert str(plain) in block["why"]
    assert "inside a git repository" in block["how"]
    assert "Traceback" not in err


@covers("not a git repository")
def test_open_inside_the_git_directory_is_a_refusal_block(repo_without_remote, capsys):
    code, out, err = run_main(["open", "x"], repo_without_remote.path / ".git", capsys)

    single_refusal(code, out, err, "not a git repository")


@covers("git command failed")
def test_open_renders_a_failed_worktree_add_as_a_git_command_failed_block(
    repo_without_remote, tmp_path, capsys
):
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, so nothing can be created below it\n")

    code, out, err = run_main(
        ["open", "feature-x", "--path", str(blocker / "sub")],
        repo_without_remote.path,
        capsys,
    )

    block = single_refusal(code, out, err, GIT_FAILED)
    assert "worktree add" in block["why"]
    assert str(blocker) in block["why"]


@covers("branch exists")
def test_a_branch_taken_while_open_runs_is_reported_as_branch_exists(
    repo_without_remote, capsys, monkeypatch
):
    holder = add_linked_worktree(repo_without_remote, "taken")
    skip_first_call(monkeypatch, "_require_free_branch")

    code, out, err = run_main(
        ["open", "taken", "--path", str(holder.parent / "other")],
        repo_without_remote.path,
        capsys,
    )

    block = single_refusal(code, out, err, "branch exists")
    assert "'taken'" in block["why"]


@covers("path exists")
def test_a_path_taken_while_open_runs_is_reported_as_path_exists(
    repo_without_remote, tmp_path, capsys, monkeypatch
):
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "file.txt").write_text("keeps the directory non-empty\n")
    skip_first_call(monkeypatch, "_require_free_path")

    code, out, err = run_main(
        ["open", "feature-x", "--path", str(occupied)], repo_without_remote.path, capsys
    )

    block = single_refusal(code, out, err, "path exists")
    assert str(occupied) in block["why"]


# --- compose: merge and identity output -------------------------------------

SHA_PATTERN = re.compile(r"[0-9a-f]{40}")


def lane_with_commit(repo, name="feature"):
    """A lane beside `repo` with one commit of its own."""
    lane_path = add_linked_worktree(repo, name)
    commit_file(lane_path, "lane.txt", "lane\n", "lane work")
    return lane_path


def advance_trunk(repo, name="trunk.txt"):
    """A new commit on the primary checkout's trunk branch; returns its SHA."""
    return commit_file(repo.path, name, "trunk\n", f"trunk adds {name}")


def advance_trunk_with(repo, name, content):
    """Commit `content` to `name` on the primary checkout's trunk branch."""
    return commit_file(repo.path, name, content, f"trunk edits {name}")


def is_ancestor(cwd, ancestor, descendant):
    return lane_core.git_ok(["merge-base", "--is-ancestor", ancestor, descendant], cwd)


def test_compose_merges_a_moved_trunk_into_the_lane(repo_without_remote, capsys):
    lane_path = lane_with_commit(repo_without_remote)
    trunk_tip = advance_trunk(repo_without_remote)

    code, _, err = run_main(["compose"], lane_path, capsys)

    assert (code, err) == (0, "")
    assert is_ancestor(lane_path, trunk_tip, "HEAD")
    assert (lane_path / "trunk.txt").is_file()
    assert (lane_path / "lane.txt").is_file()


def test_compose_prints_the_trunk_commit_and_the_head_tree_as_identities(
    repo_without_remote, capsys
):
    lane_path = lane_with_commit(repo_without_remote)
    trunk_tip = advance_trunk(repo_without_remote)

    _, out, _ = run_main(["compose"], lane_path, capsys)

    printed = parse_output(out)
    assert printed["expected-trunk"] == trunk_tip
    assert printed["expected-tree"] == git(lane_path, "rev-parse", "HEAD^{tree}")
    assert SHA_PATTERN.fullmatch(printed["expected-trunk"])
    assert SHA_PATTERN.fullmatch(printed["expected-tree"])
    assert (printed["lane"], printed["trunk"]) == ("feature", "main")


def test_compose_prints_a_ready_to_run_integrate_line(repo_without_remote, capsys):
    lane_path = lane_with_commit(repo_without_remote)
    advance_trunk(repo_without_remote)

    _, out, _ = run_main(["compose"], lane_path, capsys)

    printed = parse_output(out)
    assert printed["next"] == (
        f"lane.py integrate --expected-trunk {printed['expected-trunk']}"
        f" --expected-tree {printed['expected-tree']}"
    )


def test_compose_repeats_trunk_in_the_next_line_only_when_it_was_given(
    repo_without_remote, capsys
):
    lane_path = lane_with_commit(repo_without_remote)

    _, out, _ = run_main(["compose", "--trunk", "main"], lane_path, capsys)

    assert parse_output(out)["next"].endswith(" --trunk main")


def merge_argvs(argv_spy, start):
    """Recorded `git merge <target>` invocations after record index `start`.

    `merge --abort` is a merge command too, but it merges nothing.
    """
    return [
        argv
        for argv in argv_spy.records[start:]
        if argv[:2] == ["git", "merge"] and "--abort" not in argv
    ]


def test_compose_is_a_no_op_when_the_lane_already_contains_trunk(
    repo_without_remote, capsys, argv_spy
):
    lane_path = lane_with_commit(repo_without_remote)
    advance_trunk(repo_without_remote)
    first = run_main(["compose"], lane_path, capsys)
    head_after_first = git(lane_path, "rev-parse", "HEAD")
    records_before = len(argv_spy.records)

    second = run_main(["compose"], lane_path, capsys)

    assert first[0] == second[0] == 0
    assert second[1] == first[1]
    assert git(lane_path, "rev-parse", "HEAD") == head_after_first
    assert merge_argvs(argv_spy, records_before) == []


def test_a_lane_that_is_only_behind_fast_forwards_without_a_merge_commit(
    repo_without_remote, capsys
):
    lane_path = add_linked_worktree(repo_without_remote, "feature")
    trunk_tip = advance_trunk(repo_without_remote)

    code, out, _ = run_main(["compose"], lane_path, capsys)

    printed = parse_output(out)
    assert code == 0
    assert git(lane_path, "rev-parse", "HEAD") == trunk_tip
    assert printed["expected-tree"] == git(
        repo_without_remote.path, "rev-parse", "main^{tree}"
    )
    assert git(lane_path, "rev-list", "--merges", "--count", "HEAD") == "0"


def open_origin_lane(repo, name="feature"):
    """A lane on fixture R, branched from origin/main, with one commit of its own."""
    lane_path = add_linked_worktree(repo, name, start="origin/main")
    commit_file(lane_path, "lane.txt", "lane\n", "lane work")
    return lane_path


def test_compose_also_merges_a_local_trunk_branch_that_is_ahead_of_the_trunk_ref(
    repo_with_origin, capsys
):
    lane_path = open_origin_lane(repo_with_origin)
    origin_tip = git(repo_with_origin.path, "rev-parse", "origin/main")
    local_tip = advance_trunk(repo_with_origin, "local.txt")

    code, out, _ = run_main(["compose"], lane_path, capsys)

    assert code == 0
    assert is_ancestor(lane_path, local_tip, "HEAD")
    assert (lane_path / "local.txt").is_file()
    printed = parse_output(out)
    assert printed["trunk"] == "origin/main"
    assert printed["expected-trunk"] == origin_tip


def advance_origin(repo, name="remote.txt"):
    """Move the bare origin's main forward without pushing, then fetch it."""
    scratch = repo.path.parent / "scratch-origin-work"
    git(repo.path.parent, "clone", "-q", str(repo.origin), str(scratch))
    tip = commit_file(scratch, name, "remote\n", f"origin adds {name}")
    git(repo.origin, "fetch", "-q", str(scratch), "main:main")
    git(repo.path, "fetch", "-q", "origin")
    return tip


def test_compose_merges_the_trunk_ref_then_the_local_branch_when_they_diverged(
    repo_with_origin, capsys, argv_spy
):
    lane_path = open_origin_lane(repo_with_origin)
    origin_tip = advance_origin(repo_with_origin)
    local_tip = advance_trunk(repo_with_origin, "local.txt")
    records_before = len(argv_spy.records)

    code, out, _ = run_main(["compose"], lane_path, capsys)

    assert code == 0
    assert is_ancestor(lane_path, origin_tip, "HEAD")
    assert is_ancestor(lane_path, local_tip, "HEAD")
    assert parse_output(out)["expected-trunk"] == origin_tip
    merges = merge_argvs(argv_spy, records_before)
    assert [argv[-1] for argv in merges] == ["origin/main", "refs/heads/main"]


# --- compose: refusals outside a usable lane --------------------------------


def primary_on_trunk(repo):
    return repo.path


def detached_linked_worktree(repo):
    lane_path = add_linked_worktree(repo, "feature")
    git(lane_path, "switch", "-q", "--detach")
    return lane_path


def linked_worktree_on_trunk(repo):
    git(repo.path, "switch", "-q", "-c", "elsewhere")
    path = default_lane_dir(repo, "on-main")
    git(repo.path, "worktree", "add", "-q", str(path), "main")
    return path


@pytest.mark.parametrize(
    "place",
    [primary_on_trunk, detached_linked_worktree, linked_worktree_on_trunk],
    ids=["primary-on-trunk", "detached-head", "linked-worktree-on-trunk"],
)
@covers("not in a lane")
def test_compose_refuses_outside_a_lane(place, repo_without_remote, capsys):
    cwd = place(repo_without_remote)
    state_before = lane_state(cwd)

    code, out, err = run_main(["compose"], cwd, capsys)

    block = single_refusal(code, out, err, "not in a lane")
    assert str(cwd) in block["why"]
    assert "lane.py open <name>" in block["how"]
    assert lane_state(cwd) == state_before


def make_staged(lane_path):
    (lane_path / "staged.txt").write_text("staged\n")
    git(lane_path, "add", "--", "staged.txt")
    return "staged.txt"


def make_unstaged(lane_path):
    (lane_path / "base.txt").write_text("edited\n")
    return "base.txt"


def make_untracked(lane_path):
    (lane_path / "untracked.txt").write_text("new\n")
    return "untracked.txt"


@pytest.mark.parametrize(
    "make_dirty", [make_staged, make_unstaged, make_untracked], ids=lambda f: f.__name__
)
@covers("lane has uncommitted changes")
def test_compose_refuses_a_lane_with_any_uncommitted_change(
    make_dirty, repo_without_remote, capsys
):
    lane_path = lane_with_commit(repo_without_remote)
    advance_trunk(repo_without_remote)
    dirty_path = make_dirty(lane_path)
    head_before = git(lane_path, "rev-parse", "HEAD")

    code, out, err = run_main(["compose"], lane_path, capsys)

    block = single_refusal(code, out, err, "lane has uncommitted changes")
    assert dirty_path in block["why"]
    assert "commit or stash" in block["how"]
    assert "add .claude/ to .gitignore" in block["how"]
    assert "/setup" in block["how"]
    assert git(lane_path, "rev-parse", "HEAD") == head_before


@covers("trunk ref cannot be resolved")
def test_compose_refuses_a_trunk_that_does_not_resolve(repo_without_remote, capsys):
    lane_path = lane_with_commit(repo_without_remote)
    head_before = git(lane_path, "rev-parse", "HEAD")

    code, out, err = run_main(["compose", "--trunk", "missing-ref"], lane_path, capsys)

    block = single_refusal(code, out, err, "trunk ref cannot be resolved")
    assert "'missing-ref'" in block["why"]
    assert git(lane_path, "rev-parse", "HEAD") == head_before


# --- compose: a merge that cannot complete ----------------------------------


@covers("compose conflict")
def test_a_merge_conflict_leaves_the_lane_as_it_was(repo_without_remote, capsys):
    lane_path = add_linked_worktree(repo_without_remote, "feature")
    commit_file(lane_path, "base.txt", "lane edit\n", "lane edits base")
    advance_trunk_with(repo_without_remote, "base.txt", "trunk edit\n")
    before = unchanged_state(lane_path)

    code, out, err = run_main(["compose"], lane_path, capsys)

    block = single_refusal(code, out, err, "compose conflict")
    assert "merging main into the lane" in block["why"]
    assert "base.txt" in block["why"]
    assert "merge main by hand" in block["how"]
    assert "compose again" in block["how"]
    assert unchanged_state(lane_path) == before
    assert not merge_in_progress(lane_path)
    assert "expected-" not in out


@covers("compose conflict")
def test_a_conflict_on_the_local_trunk_merge_undoes_the_first_merge_too(
    repo_with_origin, capsys, argv_spy
):
    lane_path = add_linked_worktree(repo_with_origin, "feature", start="origin/main")
    commit_file(lane_path, "base.txt", "lane edit\n", "lane edits base")
    advance_origin(repo_with_origin)
    advance_trunk_with(repo_with_origin, "base.txt", "local main edit\n")
    before = unchanged_state(lane_path)
    records_before = len(argv_spy.records)

    code, out, err = run_main(["compose"], lane_path, capsys)

    block = single_refusal(code, out, err, "compose conflict")
    assert "merging main into the lane" in block["why"]
    assert "base.txt" in block["why"]
    merges = merge_argvs(argv_spy, records_before)
    assert [argv[-1] for argv in merges] == ["origin/main", "refs/heads/main"]
    assert unchanged_state(lane_path) == before
    assert not merge_in_progress(lane_path)


HOOK_SENTINEL = "LANE-HOOK-REJECT"
REJECT_HOOK = f"#!/bin/sh\necho {HOOK_SENTINEL} >&2\nexit 1\n"


def install_hook(repo, name, script):
    """An executable hook in the common git directory (never `core.hooksPath`)."""
    hook = repo.path / ".git" / "hooks" / name
    hook.parent.mkdir(exist_ok=True)
    hook.write_text(script, encoding="utf-8")
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR)
    return hook


@covers("compose merge failed")
def test_a_rejected_merge_leaves_the_lane_as_it_was(repo_without_remote, capsys):
    lane_path = lane_with_commit(repo_without_remote)
    advance_trunk(repo_without_remote)
    install_hook(repo_without_remote, "pre-merge-commit", REJECT_HOOK)
    before = unchanged_state(lane_path)

    code, out, err = run_main(["compose"], lane_path, capsys)

    block = single_refusal(code, out, err, "compose merge failed")
    assert HOOK_SENTINEL in block["why"]
    assert "git merge --no-edit main" in block["why"]
    assert "resolve" in block["how"]
    assert "compose again" in block["how"]
    assert unchanged_state(lane_path) == before
    assert not merge_in_progress(lane_path)
    assert "expected-" not in out


def test_the_restore_undoes_a_merged_index_that_has_no_merge_head(
    repo_without_remote,
):
    """Git 2.x keeps MERGE_HEAD after a rejected merge; the restore must not rely on it."""
    lane_path = lane_with_commit(repo_without_remote)
    advance_trunk(repo_without_remote)
    snapshot = lane._snapshot(lane_path)
    before = unchanged_state(lane_path)
    git(lane_path, "merge", "--no-commit", "--no-ff", "main")
    merge_head = lane_path / git(lane_path, "rev-parse", "--git-path", "MERGE_HEAD")
    merge_head.unlink()
    assert unchanged_state(lane_path) != before

    assert lane._restore_verified(snapshot, lane_path)

    assert unchanged_state(lane_path) == before
    assert not merge_in_progress(lane_path)


@covers("compose merge failed")
def test_a_rejected_second_merge_restores_the_lane_to_before_the_first(
    repo_with_origin, tmp_path, capsys
):
    lane_path = open_origin_lane(repo_with_origin)
    advance_origin(repo_with_origin)
    advance_trunk(repo_with_origin, "local.txt")
    counter = tmp_path / "hook-calls"
    install_hook(
        repo_with_origin,
        "pre-merge-commit",
        f"#!/bin/sh\necho call >> {counter}\n"
        f'[ "$(wc -l < {counter})" -lt 2 ] && exit 0\n'
        f"echo {HOOK_SENTINEL} >&2\nexit 1\n",
    )
    before = unchanged_state(lane_path)

    code, out, err = run_main(["compose"], lane_path, capsys)

    block = single_refusal(code, out, err, "compose merge failed")
    assert len(counter.read_text().splitlines()) == 2
    assert "could not merge main:" in block["why"]
    assert HOOK_SENTINEL in block["why"]
    assert unchanged_state(lane_path) == before
    assert not merge_in_progress(lane_path)


@covers("compose restore unverified")
def test_an_unverifiable_restore_names_the_pre_compose_commit_and_the_reset_command(
    repo_without_remote, capsys, monkeypatch
):
    lane_path = add_linked_worktree(repo_without_remote, "feature")
    commit_file(lane_path, "base.txt", "lane edit\n", "lane edits base")
    advance_trunk_with(repo_without_remote, "base.txt", "trunk edit\n")
    pre_compose = git(lane_path, "rev-parse", "HEAD")
    monkeypatch.setattr(lane, "_restore_verified", lambda snapshot, lane_path: False)

    code, out, err = run_main(["compose"], lane_path, capsys)

    block = single_refusal(code, out, err, "compose restore unverified")
    assert pre_compose in block["why"]
    assert "base.txt" in block["why"]
    assert f"git reset --hard {pre_compose}" in block["how"]
    assert "save any edits" in block["how"]


@covers("compose restore unverified")
def test_a_restore_that_does_not_take_effect_is_reported_as_unverified(
    repo_with_origin, capsys, monkeypatch
):
    lane_path = open_origin_lane(repo_with_origin)
    advance_origin(repo_with_origin)
    advance_trunk_with(repo_with_origin, "base.txt", "local main edit\n")
    commit_file(lane_path, "base.txt", "lane edit\n", "lane edits base")
    pre_compose = git(lane_path, "rev-parse", "HEAD")
    real = lane_core.git_ok

    def reset_does_nothing(args, cwd):
        return False if args[:1] == ["reset"] else real(args, cwd)

    monkeypatch.setattr(lane_core, "git_ok", reset_does_nothing)

    code, out, err = run_main(["compose"], lane_path, capsys)

    block = single_refusal(code, out, err, "compose restore unverified")
    assert pre_compose in block["why"]
    assert git(lane_path, "rev-parse", "HEAD") != pre_compose


@pytest.fixture
def restore_commands_do_nothing(monkeypatch):
    """`merge --abort` and `reset` report failure and change nothing."""
    real = lane_core.git_ok

    def inert(args, cwd):
        if args[:1] == ["reset"] or args[:2] == ["merge", "--abort"]:
            return False
        return real(args, cwd)

    monkeypatch.setattr(lane_core, "git_ok", inert)


def test_the_restore_is_unverified_while_a_merge_is_still_in_progress(
    repo_without_remote, restore_commands_do_nothing
):
    lane_path = lane_with_commit(repo_without_remote)
    advance_trunk(repo_without_remote)
    snapshot = lane._snapshot(lane_path)
    # Tree, index and working tree equal HEAD's; only MERGE_HEAD is left over.
    git(lane_path, "merge", "-s", "ours", "--no-commit", "--no-ff", "main")
    assert git(lane_path, "status", "--porcelain=v1") == ""

    assert not lane._restore_verified(snapshot, lane_path)


def test_the_restore_is_unverified_while_the_working_tree_is_dirty(
    repo_without_remote, restore_commands_do_nothing
):
    lane_path = lane_with_commit(repo_without_remote)
    snapshot = lane._snapshot(lane_path)
    (lane_path / "base.txt").write_text("edited\n")

    assert not lane._restore_verified(snapshot, lane_path)


def test_the_restore_is_unverified_when_a_check_cannot_run(
    repo_without_remote, monkeypatch
):
    lane_path = lane_with_commit(repo_without_remote)
    snapshot = lane._snapshot(lane_path)

    def cannot_run(_path):
        raise lane_core.RefusalError(
            lane_core.git_command_failed_refusal("git status", "boom")
        )

    monkeypatch.setattr(lane_core, "dirty_paths", cannot_run)

    assert not lane._restore_verified(snapshot, lane_path)


def test_a_restore_that_worked_is_verified(repo_without_remote):
    lane_path = lane_with_commit(repo_without_remote)
    advance_trunk(repo_without_remote)
    snapshot = lane._snapshot(lane_path)
    git(lane_path, "merge", "-q", "--no-edit", "main")

    assert lane._restore_verified(snapshot, lane_path)
    assert git(lane_path, "rev-parse", "HEAD") == snapshot.head


# --- compose: merges only what exists and differs ---------------------------


def row_local_branch_is_the_trunk(root):
    repo = build_repo_without_remote(root)
    lane_path = lane_with_commit(repo)
    advance_trunk(repo)
    return lane_path, [], ["main"]


def row_trunk_is_a_tag(root):
    repo = build_repo_with_origin(root)
    lane_path = open_origin_lane(repo)
    advance_origin(repo)
    git(repo.path, "tag", "v1", "origin/main")
    advance_trunk(repo, "local.txt")
    return lane_path, ["--trunk", "v1"], ["v1"]


def row_local_main_contains_origin_main(root):
    repo = build_repo_with_origin(root)
    lane_path = open_origin_lane(repo)
    advance_origin(repo)
    git(repo.path, "merge", "-q", "--ff-only", "origin/main")
    advance_trunk(repo, "local.txt")
    return lane_path, [], ["refs/heads/main"]


def row_origin_main_contains_local_main(root):
    repo = build_repo_with_origin(root)
    lane_path = open_origin_lane(repo)
    advance_origin(repo)
    git(repo.path, "reset", "-q", "--hard", "origin/main")
    return lane_path, [], ["origin/main"]


def row_lane_contains_both(root):
    repo = build_repo_with_origin(root)
    lane_path = open_origin_lane(repo)
    advance_trunk(repo, "local.txt")
    git(lane_path, "merge", "-q", "--no-edit", "main")
    return lane_path, [], []


@pytest.mark.parametrize(
    "row",
    [
        row_local_branch_is_the_trunk,
        row_trunk_is_a_tag,
        row_local_main_contains_origin_main,
        row_origin_main_contains_local_main,
        row_lane_contains_both,
    ],
    ids=lambda row: row.__name__.removeprefix("row_"),
)
def test_compose_merges_each_target_at_most_once_and_only_when_it_is_missing(
    row, tmp_path, capsys, argv_spy
):
    lane_path, trunk_args, expected_targets = row(tmp_path)
    records_before = len(argv_spy.records)

    code, out, err = run_main(["compose", *trunk_args], lane_path, capsys)

    assert (code, err) == (0, "")
    merges = merge_argvs(argv_spy, records_before)
    assert [argv[-1] for argv in merges] == expected_targets
    assert "does not exist" not in err
    assert SHA_PATTERN.fullmatch(parse_output(out)["expected-trunk"])


# --- open and compose behave the same on every origin -----------------------

GITHUB_URL = "https://github.com/acme/widgets.git"
PR_NEXT_LINE = "open a PR with /pr (or pass --local-trunk to integrate locally)"


def origin_github(root):
    repo = build_repo_with_origin(root)
    git(repo.path, "remote", "set-url", "origin", GITHUB_URL)
    return repo


@pytest.mark.parametrize(
    ("build", "pr_repository"),
    [
        (origin_github, True),
        (build_repo_with_origin, False),
        (build_repo_without_remote, False),
    ],
    ids=["github", "other", "none"],
)
def test_open_then_compose_prints_the_identities_on_every_origin(
    build, pr_repository, tmp_path, capsys
):
    repo = build(tmp_path)

    open_code, open_out, _ = run_main(["open", "feat"], repo.path, capsys)
    compose_code, out, err = run_main(
        ["compose"], Path(parse_output(open_out)["worktree"]), capsys
    )

    printed = parse_output(out)
    assert (open_code, compose_code, err) == (0, 0, "")
    for key in ("expected-trunk", "expected-tree"):
        assert SHA_PATTERN.fullmatch(printed[key])
    assert ("lane.py integrate" not in printed["next"]) == pr_repository
    assert (printed["next"] == PR_NEXT_LINE) == pr_repository
    assert out.count("next:") == 1


def test_a_github_origin_keeps_the_pr_next_line_when_a_trunk_is_given(tmp_path, capsys):
    repo = origin_github(tmp_path)
    lane_path = add_linked_worktree(repo, "feat", start="origin/main")

    _, out, _ = run_main(["compose", "--trunk", "origin/main"], lane_path, capsys)

    assert parse_output(out)["next"] == PR_NEXT_LINE


# --- compose: outside a repository ------------------------------------------


@covers("not a git repository")
def test_compose_outside_a_repository_is_a_refusal_block(tmp_path, capsys):
    plain = tmp_path / "plain"
    plain.mkdir()

    code, out, err = run_main(["compose"], plain, capsys)

    block = single_refusal(code, out, err, "not a git repository")
    assert str(plain) in block["why"]
    assert "inside a git repository" in block["how"]
    assert "Traceback" not in err


def test_the_lane_is_restored_even_when_the_failure_cannot_be_read(
    repo_without_remote, capsys, monkeypatch
):
    lane_path = add_linked_worktree(repo_without_remote, "feature")
    commit_file(lane_path, "base.txt", "lane edit\n", "lane edits base")
    advance_trunk_with(repo_without_remote, "base.txt", "trunk edit\n")
    before = unchanged_state(lane_path)

    def unreadable(_path):
        raise lane_core.RefusalError(
            lane_core.git_command_failed_refusal("git diff", "boom")
        )

    monkeypatch.setattr(lane, "_unmerged_paths", unreadable)

    code, out, err = run_main(["compose"], lane_path, capsys)

    assert (code, out) == (1, "")
    assert parse_blocks(err)[0]["refused"] == GIT_FAILED
    assert unchanged_state(lane_path) == before
    assert not merge_in_progress(lane_path)
