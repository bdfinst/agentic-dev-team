"""Tests for plugins/dev-team/scripts/lane.py: the command line and `open`.

Every test runs in-process against real git repositories built by
`lane_fixtures`. The refusal registry, the git seam, trunk resolution and lane
detection are tested in `test_lane_core.py`; `compose` in `test_lane_compose.py`.
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
import sys
from pathlib import Path

import pytest
from lane_fixtures import (
    GIT_FAILED,
    add_linked_worktree,
    argv_spy,
    commit_file,
    covers,
    default_lane_dir,
    enforce_covers,
    git,
    hermetic_process_env,
    imported_modules,
    non_stdlib,
    parse_output,
    plain_directory,
    repo_with_origin,
    repo_without_default_branch,
    repo_without_remote,
    run_main,
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


@pytest.mark.parametrize("command", ["open", "compose"])
def test_trunk_help_names_the_default_trunk_rule(command, tmp_path, capsys):
    code, out, _ = run_main([command, "--help"], tmp_path, capsys)

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
    assert (
        lane_core.primary_checkout(context.lane_path)
        == repo_without_remote.path.resolve()
    )


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
    state_before = unchanged_state(repo_without_remote.path)
    records_before = len(argv_spy.records)

    code, out, err = run_main(["open", name], repo_without_remote.path, capsys)

    block = single_refusal(code, out, err, "invalid lane name")
    assert repr(name) in block["why"]
    assert reason in block["why"]
    assert "letters, digits" in block["how"]
    assert unchanged_state(repo_without_remote.path) == state_before
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
    state_before = unchanged_state(repo_without_remote.path)
    records_before = len(argv_spy.records)

    code, out, err = run_main(["open", "--", "-lead"], repo_without_remote.path, capsys)

    block = single_refusal(code, out, err, "invalid lane name")
    assert "'-lead'" in block["why"]
    assert PATTERN_REASON in block["why"]
    assert "letters, digits" in block["how"]
    assert unchanged_state(repo_without_remote.path) == state_before
    assert [argv for argv in argv_spy.records[records_before:] if "-lead" in argv] == []


def test_a_leading_dash_name_without_double_dash_is_a_usage_error(
    repo_without_remote, capsys
):
    state_before = unchanged_state(repo_without_remote.path)

    code, out, err = run_main(["open", "-lead"], repo_without_remote.path, capsys)

    assert code == 2
    assert out == ""
    assert "usage" in err
    assert unchanged_state(repo_without_remote.path) == state_before


@covers("branch exists")
def test_open_refuses_an_existing_branch(repo_without_remote, capsys):
    git(repo_without_remote.path, "branch", "taken")
    state_before = unchanged_state(repo_without_remote.path)

    code, out, err = run_main(["open", "taken"], repo_without_remote.path, capsys)

    block = single_refusal(code, out, err, "branch exists")
    assert "'taken'" in block["why"]
    assert "another name" in block["how"]
    assert "git branch -d taken" in block["how"]
    assert unchanged_state(repo_without_remote.path) == state_before
    assert not default_lane_dir(repo_without_remote, "taken").exists()


@covers("path exists")
def test_open_refuses_an_existing_path(repo_without_remote, tmp_path, capsys):
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    state_before = unchanged_state(repo_without_remote.path)

    code, out, err = run_main(
        ["open", "feature-x", "--path", str(occupied)], repo_without_remote.path, capsys
    )

    block = single_refusal(code, out, err, "path exists")
    assert str(occupied) in block["why"]
    assert "--path" in block["how"]
    assert unchanged_state(repo_without_remote.path) == state_before


@covers("path exists")
def test_open_refuses_a_default_path_that_is_taken(repo_without_remote, capsys):
    taken = default_lane_dir(repo_without_remote, "feature-x")
    taken.mkdir()
    state_before = unchanged_state(repo_without_remote.path)

    code, out, err = run_main(["open", "feature-x"], repo_without_remote.path, capsys)

    block = single_refusal(code, out, err, "path exists")
    assert str(taken) in block["why"]
    assert unchanged_state(repo_without_remote.path) == state_before


@covers("trunk ref cannot be resolved")
def test_open_refuses_a_trunk_that_does_not_resolve(repo_without_remote, capsys):
    state_before = unchanged_state(repo_without_remote.path)

    code, out, err = run_main(
        ["open", "feature-x", "--trunk", "missing-ref"],
        repo_without_remote.path,
        capsys,
    )

    block = single_refusal(code, out, err, "trunk ref cannot be resolved")
    assert "'missing-ref'" in block["why"]
    assert "--trunk <ref>" in block["how"]
    assert "git remote set-head origin -a" in block["how"]
    assert unchanged_state(repo_without_remote.path) == state_before
    assert not default_lane_dir(repo_without_remote, "feature-x").exists()


@covers("trunk ref cannot be resolved")
def test_open_refuses_when_no_default_trunk_exists(repo_without_default_branch, capsys):
    state_before = unchanged_state(repo_without_default_branch)

    code, out, err = run_main(
        ["open", "feature-x"], repo_without_default_branch, capsys
    )

    block = single_refusal(code, out, err, "trunk ref cannot be resolved")
    assert "no --trunk was given" in block["why"]
    assert "git remote set-head origin -a" in block["how"]
    assert unchanged_state(repo_without_default_branch) == state_before


@covers("trunk ref cannot be resolved")
def test_open_names_a_default_trunk_that_does_not_resolve(repo_without_remote, capsys):
    repo = repo_without_remote.path
    git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/gone")

    code, out, err = run_main(["open", "feature-x"], repo, capsys)

    block = single_refusal(code, out, err, "trunk ref cannot be resolved")
    assert "'origin/gone'" in block["why"]


@covers("not a git repository")
def test_open_outside_a_repository_is_a_refusal_block(plain_directory, capsys):
    plain = plain_directory

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


@covers("branch exists")
def test_a_lane_opened_concurrently_under_the_same_name_is_reported_as_branch_exists(
    repo_without_remote, capsys, monkeypatch
):
    add_linked_worktree(repo_without_remote, "taken")
    skip_first_call(monkeypatch, "_require_free_branch")
    skip_first_call(monkeypatch, "_require_free_path")

    code, out, err = run_main(["open", "taken"], repo_without_remote.path, capsys)

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
