"""Tests for plugins/dev-team/scripts/lane_core.py and lane.py (issue #2274).

Scope so far: the CLI shell, the refusal registry and renderer, the git seam
and its guard, trunk resolution and lane detection, and `open`. Every test runs
in-process against real git repositories built by `lane_fixtures`.
"""

from __future__ import annotations

import ast
import dataclasses
import os
import subprocess
import sys
from pathlib import Path

import pytest
from lane_fixtures import (
    ArgvSpy,
    Repo,
    add_linked_worktree,
    build_fixture_n,
    build_fixture_r,
    commit_file,
    covers,
    git,
    git_env,
    lane_state,
    parse_blocks,
    parse_output,
)

from _repo_root import REPO_ROOT

SCRIPTS_DIR = REPO_ROOT / "plugins" / "dev-team" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import lane
import lane_core

#: The final refusal vocabulary (plan decision 3). A `covers` literal outside
#: this set is a typo; every key registered so far must be covered.
FINAL_VOCABULARY = frozenset(
    {
        "invalid lane name",
        "branch exists",
        "path exists",
        "trunk ref cannot be resolved",
        "not a git repository",
        "not in a lane",
        "lane has uncommitted changes",
        "compose conflict",
        "compose merge failed",
        "compose restore unverified",
        "tree mismatch",
        "review gate stale or missing",
        "trunk moved",
        "trunk cannot fast-forward",
        "PR repository",
        "invalid identity argument",
        "git command failed",
    }
)

#: Every token and subcommand the guard rejects (plan decision 2).
GUARD_CASES = {
    "push": ["push", "origin", "main"],
    "send-pack": ["send-pack", "somewhere"],
    "push-after-global-option": ["-C", "/tmp", "push"],
    "--no-verify": ["commit", "--no-verify", "-m", "x"],
    "--force": ["branch", "--force", "x"],
    "--force-with-lease": ["branch", "--force-with-lease", "x"],
    "-f": ["branch", "-f", "x"],
    "--no-gpg-sign": ["commit", "--no-gpg-sign", "-m", "x"],
    "core.hooksPath": ["-c", "core.hooksPath=/hooks", "status"],
    "core.hooksPath-lowercase": ["-c", "core.hookspath=/hooks", "status"],
    "other-config-override": ["-c", "user.name=x", "status"],
}

GIT_FAILED = "git command failed"


# --- autouse instrumentation ------------------------------------------------


@pytest.fixture(autouse=True)
def hermetic_process_env(monkeypatch, tmp_path):
    """The code under test inherits the process env: make it hermetic too."""
    hermetic = git_env(tmp_path)
    for key in set(os.environ) - set(hermetic):
        monkeypatch.delenv(key)
    for key, value in hermetic.items():
        monkeypatch.setenv(key, value)


@pytest.fixture(autouse=True)
def argv_spy(monkeypatch, hermetic_process_env):
    """Record every argv; the forbidden set is asserted in this test's teardown."""
    spy = ArgvSpy()
    spy.install(monkeypatch)
    yield spy
    assert spy.violations() == [], "a recorded git call pushed, forced or skipped hooks"


@pytest.fixture(scope="session")
def rendered_whats(request):
    """Every `what` the renderer printed this session; checked at session finish.

    The check only holds for a complete, single-process, green run of the whole
    file. A partial or distributed run cannot prove coverage, so it is skipped
    there; `test_every_registered_refusal_has_a_covering_test` is the
    selection-independent guard.
    """
    seen: set[str] = set()
    yield seen
    config = request.config
    partial = (
        config.getoption("keyword")
        or config.getoption("markexpr")
        or config.getoption("deselect")
        or config.getoption("lf", default=False)
        or any("::" in arg for arg in config.args)
        or hasattr(config, "workerinput")
        or request.session.testsfailed
    )
    if partial:
        return
    missing = set(lane_core.REFUSALS) - seen
    assert not missing, (
        f"registered refusals never rendered by any test: {sorted(missing)}"
    )


@pytest.fixture(autouse=True)
def record_rendered(monkeypatch, rendered_whats):
    real = lane_core.render_block

    def recording(refusal):
        rendered_whats.add(refusal.what)
        return real(refusal)

    monkeypatch.setattr(lane_core, "render_block", recording)


# --- fixtures ---------------------------------------------------------------


@pytest.fixture
def repo_n(tmp_path) -> Repo:
    return build_fixture_n(tmp_path)


@pytest.fixture
def repo_r(tmp_path) -> Repo:
    return build_fixture_r(tmp_path)


def run_main(argv, cwd, capsys):
    code = lane.main(argv, cwd=cwd)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


@pytest.fixture
def open_handler(monkeypatch):
    """Replace the real `open` handler to drive the renderer with a fault."""

    def install(handler):
        monkeypatch.setitem(lane.HANDLERS, "open", lambda args, cwd: handler(cwd))

    return install


# --- scenario: help lists the registered subcommands -------------------------


def test_help_exits_zero_and_lists_open(tmp_path, capsys):
    code, out, _ = run_main(["--help"], tmp_path, capsys)

    assert code == 0
    assert "open" in out


def test_a_missing_subcommand_is_a_usage_error(tmp_path, capsys):
    code, _, err = run_main([], tmp_path, capsys)

    assert code == 2
    assert "usage" in err


def test_main_returns_instead_of_raising_system_exit(tmp_path):
    assert lane.main(["--help"], cwd=tmp_path) == 0


# --- Refusal ----------------------------------------------------------------


@pytest.mark.parametrize("field", ["what", "why", "how"])
@pytest.mark.parametrize("empty", ["", "   ", "\n\t "])
def test_refusal_rejects_a_field_that_is_empty_after_strip(field, empty):
    fields = {"what": "w", "why": "y", "how": "h", field: empty}

    with pytest.raises(ValueError, match=field):
        lane_core.Refusal(**fields)


def test_refusal_accepts_three_non_empty_fields():
    refusal = lane_core.Refusal(what="w", why="y", how="h")

    assert (refusal.what, refusal.why, refusal.how) == ("w", "y", "h")


def test_refusal_is_frozen():
    refusal = lane_core.Refusal(what="w", why="y", how="h")

    with pytest.raises(dataclasses.FrozenInstanceError):
        refusal.what = "other"  # type: ignore[misc]


def test_refusals_are_registered_under_their_own_what():
    assert lane_core.REFUSALS[GIT_FAILED] is lane_core.git_command_failed


def test_git_command_failed_names_the_command_and_the_detail():
    refusal = lane_core.git_command_failed("git status", "fatal: boom")

    assert refusal.what == GIT_FAILED
    assert "fatal: boom" in refusal.why
    assert "git status" in refusal.why
    assert "git status" in refusal.how


def test_git_command_failed_stays_complete_when_git_said_nothing():
    refusal = lane_core.git_command_failed("git status", "  ")

    assert refusal.why.strip() != ""


# --- renderer ---------------------------------------------------------------


def test_render_block_is_three_plain_lines():
    block = lane_core.render_block(lane_core.Refusal(what="w", why="y", how="h"))

    assert block == "refused: w\nwhy: y\nhow: h\n"


def test_emit_refusals_separates_blocks_with_a_blank_line(capsys):
    first = lane_core.Refusal(what="a", why="b", how="c")
    second = lane_core.Refusal(what="d", why="e", how="f")

    code = lane_core.emit_refusals([first, second])

    assert code == lane_core.EXIT_REFUSED
    assert capsys.readouterr().err == (
        "refused: a\nwhy: b\nhow: c\n\nrefused: d\nwhy: e\nhow: f\n"
    )


@covers("git command failed")
def test_a_refusal_prints_a_complete_block_on_stderr_and_exits_one(
    repo_n, capsys, open_handler
):
    open_handler(
        lambda cwd: lane_core.git_text(["rev-parse", "--verify", "no-such"], cwd)
    )

    code, out, err = run_main(["open", "x"], repo_n.path, capsys)

    (block,) = parse_blocks(err)
    assert code == 1
    assert out == ""
    assert block["refused"] == GIT_FAILED
    assert block["why"].strip() != ""
    assert block["how"].strip() != ""
    assert "\x1b" not in err


# --- the git seam and its guard ---------------------------------------------


@pytest.mark.parametrize("args", GUARD_CASES.values(), ids=GUARD_CASES.keys())
def test_the_guard_rejects_and_runs_nothing(args, repo_n, argv_spy):
    before = len(argv_spy.records)

    with pytest.raises(lane_core.RefusalError) as caught:
        lane_core._git(args, repo_n.path)

    assert caught.value.refusal.what == GIT_FAILED
    assert argv_spy.records[before:] == []


@pytest.mark.parametrize("args", GUARD_CASES.values(), ids=GUARD_CASES.keys())
@covers("git command failed")
def test_a_guard_hit_renders_a_git_command_failed_block(
    args, repo_n, capsys, open_handler
):
    open_handler(lambda cwd: lane_core._git(args, cwd).returncode)

    code, _, err = run_main(["open", "x"], repo_n.path, capsys)

    (block,) = parse_blocks(err)
    assert code == 1
    assert block["refused"] == GIT_FAILED
    assert block["why"].strip() != ""
    assert block["how"].strip() != ""


def test_the_guard_allows_the_one_permitted_config_override(repo_n):
    head = lane_core.git_text(
        ["-c", "diff.relative=false", "rev-parse", "--verify", "HEAD"], repo_n.path
    )

    assert head == git(repo_n.path, "rev-parse", "HEAD")


def test_the_guard_reads_the_subcommand_not_a_substring(repo_n):
    lane_core.git_text(["branch", "pushed"], repo_n.path)

    assert git(repo_n.path, "rev-parse", "--verify", "pushed") == git(
        repo_n.path, "rev-parse", "HEAD"
    )


@covers("git command failed")
def test_a_failing_git_command_raises_a_refusal_with_the_last_stderr_line(
    monkeypatch, tmp_path
):
    failed = subprocess.CompletedProcess(
        args=["git"], returncode=128, stdout="", stderr="hint: noise\nfatal: boom\n\n"
    )
    monkeypatch.setattr(lane_core, "_run", lambda argv, cwd: failed)

    with pytest.raises(lane_core.RefusalError) as caught:
        lane_core.git_text(["status"], tmp_path)

    assert caught.value.refusal.what == GIT_FAILED
    assert "fatal: boom" in caught.value.refusal.why
    assert "hint: noise" not in caught.value.refusal.why
    assert "git status" in caught.value.refusal.how


def test_a_missing_git_binary_is_a_refusal_not_a_traceback(monkeypatch, tmp_path):
    def missing(*_args, **_kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", missing)

    with pytest.raises(lane_core.RefusalError) as caught:
        lane_core._git(["status"], tmp_path)

    assert caught.value.refusal.what == GIT_FAILED


def test_run_is_the_only_subprocess_run_call_in_lane_core():
    tree = ast.parse((SCRIPTS_DIR / "lane_core.py").read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"run", "Popen", "call", "check_output", "check_call"}
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "subprocess"
    ]

    assert len(calls) == 1


def test_no_subprocess_call_in_lane_core_uses_shell_true():
    tree = ast.parse((SCRIPTS_DIR / "lane_core.py").read_text(encoding="utf-8"))
    shell_keywords = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.keyword) and node.arg == "shell"
    ]

    assert shell_keywords == []


# --- import whitelist ---------------------------------------------------------


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            assert node.level == 0, "relative import"
            modules.add((node.module or "").split(".")[0])
    return modules


def _non_stdlib(modules: set[str]) -> set[str]:
    return {name for name in modules if name not in sys.stdlib_module_names}


def test_lane_core_imports_only_stdlib_and_review_gate_hash():
    modules = _imported_modules(SCRIPTS_DIR / "lane_core.py")

    assert _non_stdlib(modules) == {"review_gate_hash"}


def test_lane_imports_only_stdlib_and_lane_core():
    modules = _imported_modules(SCRIPTS_DIR / "lane.py")

    assert _non_stdlib(modules) == {"lane_core"}


def test_lane_core_never_imports_lane():
    assert "lane" not in _imported_modules(SCRIPTS_DIR / "lane_core.py")


# --- open ---------------------------------------------------------------------

LANE_DIR_INFIX = "-lane-"


def single_refusal(code, out, err, what):
    """Assert one complete refusal block (three non-empty fields) and exit 1."""
    (block,) = parse_blocks(err)
    assert code == 1
    assert out == ""
    assert block["refused"] == what
    assert block["why"].strip() != ""
    assert block["how"].strip() != ""
    return block


def default_lane_dir(repo: Repo, dashed_name: str) -> Path:
    return repo.path.parent / f"{repo.path.name}{LANE_DIR_INFIX}{dashed_name}"


def worktree_paths(cwd: Path) -> list[str]:
    porcelain = git(cwd, "worktree", "list", "--porcelain")
    return [
        line.removeprefix("worktree ")
        for line in porcelain.splitlines()
        if line.startswith("worktree ")
    ]


def test_open_creates_a_linked_worktree_at_the_sibling_default_path(repo_n, capsys):
    expected = default_lane_dir(repo_n, "feature-x")

    code, _, _ = run_main(["open", "feature-x"], repo_n.path, capsys)

    assert code == 0
    assert str(expected.resolve()) in worktree_paths(repo_n.path)
    assert (expected / "base.txt").is_file()


def test_open_points_the_branch_at_the_former_trunk_tip(repo_n, capsys):
    former_tip = git(repo_n.path, "rev-parse", "main")

    run_main(["open", "feature-x"], repo_n.path, capsys)

    assert git(repo_n.path, "rev-parse", "feature-x") == former_tip


def test_open_prints_worktree_and_branch_lines(repo_n, capsys):
    code, out, err = run_main(["open", "feature-x"], repo_n.path, capsys)

    expected = default_lane_dir(repo_n, "feature-x")
    assert (code, err) == (0, "")
    assert out == f"worktree: {expected}\nbranch: feature-x\n"


def test_open_maps_a_slash_in_the_name_to_a_dash_in_the_path(repo_n, capsys):
    code, out, _ = run_main(["open", "feature/x"], repo_n.path, capsys)

    assert code == 0
    assert parse_output(out) == {
        "worktree": str(default_lane_dir(repo_n, "feature-x")),
        "branch": "feature/x",
    }
    assert git(repo_n.path, "rev-parse", "--verify", "refs/heads/feature/x")


def test_open_from_inside_a_lane_places_the_new_lane_beside_the_primary(repo_n, capsys):
    lane_a = add_linked_worktree(repo_n, "A")

    code, out, _ = run_main(["open", "B"], lane_a, capsys)

    assert code == 0
    assert parse_output(out)["worktree"] == str(default_lane_dir(repo_n, "B"))


def test_open_branches_from_the_trunk_ref_not_a_local_branch_that_ran_ahead(
    repo_r, capsys
):
    origin_tip = git(repo_r.path, "rev-parse", "origin/main")
    commit_file(repo_r.path, "local.txt", "local\n", "local only")

    run_main(["open", "feature-x"], repo_r.path, capsys)

    assert git(repo_r.path, "rev-parse", "feature-x") == origin_tip


def test_open_honours_path_and_trunk(repo_n, tmp_path, capsys):
    git(repo_n.path, "switch", "-q", "-c", "dev")
    dev_tip = commit_file(repo_n.path, "dev.txt", "dev\n", "dev work")
    git(repo_n.path, "switch", "-q", "main")
    target = tmp_path / "custom-lane"

    code, out, _ = run_main(
        ["open", "feature-y", "--path", str(target), "--trunk", "dev"],
        repo_n.path,
        capsys,
    )

    assert code == 0
    assert parse_output(out)["worktree"] == str(target)
    assert git(repo_n.path, "rev-parse", "feature-y") == dev_tip
    assert (target / "dev.txt").is_file()


def test_open_makes_a_relative_path_absolute_against_the_working_directory(
    repo_n, tmp_path, capsys
):
    code, out, _ = run_main(
        ["open", "feature-y", "--path", "../elsewhere"], repo_n.path, capsys
    )

    assert code == 0
    assert parse_output(out)["worktree"] == str(tmp_path / "elsewhere")


@pytest.mark.parametrize("name", ["bad name", "a..b", "feat.lock", "a;b", "x~1"])
@covers("invalid lane name")
def test_open_refuses_an_invalid_name(name, repo_n, capsys):
    before = lane_state(repo_n.path)

    code, out, err = run_main(["open", name], repo_n.path, capsys)

    block = single_refusal(code, out, err, "invalid lane name")
    assert repr(name) in block["why"]
    assert "letters, digits" in block["how"]
    assert lane_state(repo_n.path) == before


@covers("invalid lane name")
def test_open_refuses_a_leading_dash_name_given_after_double_dash(repo_n, capsys):
    before = lane_state(repo_n.path)

    code, out, err = run_main(["open", "--", "-lead"], repo_n.path, capsys)

    block = single_refusal(code, out, err, "invalid lane name")
    assert "'-lead'" in block["why"]
    assert "letters, digits" in block["how"]
    assert lane_state(repo_n.path) == before


def test_a_leading_dash_name_without_double_dash_is_a_usage_error(repo_n, capsys):
    before = lane_state(repo_n.path)

    code, out, err = run_main(["open", "-lead"], repo_n.path, capsys)

    assert code == 2
    assert out == ""
    assert "usage" in err
    assert lane_state(repo_n.path) == before


@covers("branch exists")
def test_open_refuses_an_existing_branch(repo_n, capsys):
    git(repo_n.path, "branch", "taken")
    before = lane_state(repo_n.path)

    code, out, err = run_main(["open", "taken"], repo_n.path, capsys)

    block = single_refusal(code, out, err, "branch exists")
    assert "'taken'" in block["why"]
    assert "another name" in block["how"]
    assert "git branch -d taken" in block["how"]
    assert lane_state(repo_n.path) == before
    assert not default_lane_dir(repo_n, "taken").exists()


@covers("path exists")
def test_open_refuses_an_existing_path(repo_n, tmp_path, capsys):
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    before = lane_state(repo_n.path)

    code, out, err = run_main(
        ["open", "feature-x", "--path", str(occupied)], repo_n.path, capsys
    )

    block = single_refusal(code, out, err, "path exists")
    assert str(occupied) in block["why"]
    assert "--path" in block["how"]
    assert lane_state(repo_n.path) == before


@covers("path exists")
def test_open_refuses_a_default_path_that_is_taken(repo_n, capsys):
    taken = default_lane_dir(repo_n, "feature-x")
    taken.mkdir()
    before = lane_state(repo_n.path)

    code, out, err = run_main(["open", "feature-x"], repo_n.path, capsys)

    block = single_refusal(code, out, err, "path exists")
    assert str(taken) in block["why"]
    assert lane_state(repo_n.path) == before


@covers("trunk ref cannot be resolved")
def test_open_refuses_a_trunk_that_does_not_resolve(repo_n, capsys):
    before = lane_state(repo_n.path)

    code, out, err = run_main(
        ["open", "feature-x", "--trunk", "missing-ref"], repo_n.path, capsys
    )

    block = single_refusal(code, out, err, "trunk ref cannot be resolved")
    assert "'missing-ref'" in block["why"]
    assert "--trunk <ref>" in block["how"]
    assert "git remote set-head origin -a" in block["how"]
    assert lane_state(repo_n.path) == before
    assert not default_lane_dir(repo_n, "feature-x").exists()


@covers("trunk ref cannot be resolved")
def test_open_refuses_when_no_default_trunk_exists(tmp_path, capsys):
    odd = tmp_path / "odd"
    odd.mkdir()
    git(odd, "init", "-q", "-b", "elsewhere", home=tmp_path)
    commit_file(odd, "a.txt", "a\n", "a")
    before = lane_state(odd)

    code, out, err = run_main(["open", "feature-x"], odd, capsys)

    block = single_refusal(code, out, err, "trunk ref cannot be resolved")
    assert "no --trunk was given" in block["why"]
    assert "git remote set-head origin -a" in block["how"]
    assert lane_state(odd) == before


@covers("not a git repository")
def test_open_outside_a_repository_is_a_refusal_block(tmp_path, capsys):
    plain = tmp_path / "plain"
    plain.mkdir()

    code, out, err = run_main(["open", "x"], plain, capsys)

    block = single_refusal(code, out, err, "not a git repository")
    assert str(plain) in block["why"]
    assert "inside a git repository" in block["how"]
    assert "Traceback" not in err


# --- resolve_trunk ----------------------------------------------------------


def test_trunk_defaults_to_the_local_branch_without_a_remote(repo_n):
    assert lane_core.resolve_trunk(None, repo_n.path) == "main"


def test_trunk_defaults_to_the_remote_tracking_branch(repo_r):
    assert lane_core.resolve_trunk(None, repo_r.path) == "origin/main"


@pytest.mark.parametrize("ref", ["main", "HEAD"])
def test_an_explicit_resolvable_trunk_is_returned_as_given(ref, repo_n):
    assert lane_core.resolve_trunk(ref, repo_n.path) == ref


def test_a_tag_is_a_usable_trunk(repo_r):
    git(repo_r.path, "tag", "v1", "origin/main")

    assert lane_core.resolve_trunk("v1", repo_r.path) == "v1"


def test_an_unknown_ref_is_not_a_trunk(repo_n):
    assert lane_core.resolve_trunk("missing-ref", repo_n.path) is None


@pytest.mark.parametrize(
    "ref", ["-lead", "--help", "bad name", "a;b", "", "main^{tree}", "$(x)"]
)
def test_a_malformed_trunk_is_rejected_before_git_runs(ref, repo_n, argv_spy):
    before = len(argv_spy.records)

    assert lane_core.resolve_trunk(ref, repo_n.path) is None
    assert argv_spy.records[before:] == []


def test_no_default_and_no_argument_gives_none(tmp_path):
    bare = tmp_path / "empty"
    bare.mkdir()
    git(bare, "init", "-q", "-b", "trunk-less")

    assert lane_core.resolve_trunk(None, bare) is None


# --- local_branch_of --------------------------------------------------------


def test_a_local_branch_maps_to_itself(repo_n):
    assert lane_core.local_branch_of("main", repo_n.path) == "main"


def test_a_remote_tracking_ref_maps_to_the_branch_without_the_remote(repo_r):
    assert lane_core.local_branch_of("origin/main", repo_r.path) == "main"


def test_a_slash_in_the_branch_name_survives(repo_r):
    git(repo_r.origin, "branch", "feat/x", "main")
    git(repo_r.path, "fetch", "-q", "origin")

    assert lane_core.local_branch_of("origin/feat/x", repo_r.path) == "feat/x"


def test_a_tag_maps_to_itself(repo_r):
    git(repo_r.path, "tag", "v1")

    assert lane_core.local_branch_of("v1", repo_r.path) == "v1"


# --- lane_context -----------------------------------------------------------


def test_the_primary_checkout_is_not_a_lane(repo_n):
    assert lane_core.lane_context("main", repo_n.path) is None


def test_a_linked_worktree_on_its_own_branch_is_a_lane(repo_n):
    worktree = add_linked_worktree(repo_n, "feature-x")

    context = lane_core.lane_context("main", worktree)

    assert context == lane_core.LaneContext(
        lane_path=worktree.resolve(),
        branch="feature-x",
        trunk_ref="main",
        trunk_branch="main",
        primary_path=repo_n.path.resolve(),
    )


def test_a_subdirectory_of_a_lane_reports_the_lane_root(repo_n):
    worktree = add_linked_worktree(repo_n, "feature-x")
    (worktree / "sub").mkdir()

    context = lane_core.lane_context("main", worktree / "sub")

    assert context is not None
    assert context.lane_path == worktree.resolve()


def test_a_detached_head_in_a_linked_worktree_is_not_a_lane(repo_n):
    worktree = add_linked_worktree(repo_n, "feature-x")
    git(worktree, "checkout", "-q", "--detach")

    assert lane_core.lane_context("main", worktree) is None


def test_a_linked_worktree_on_the_trunk_branch_is_not_a_lane(repo_n, tmp_path):
    git(repo_n.path, "switch", "-q", "-c", "parking")
    on_trunk = tmp_path / "on-trunk"
    git(repo_n.path, "worktree", "add", "-q", str(on_trunk), "main")

    assert lane_core.lane_context("main", on_trunk) is None


def test_the_trunk_branch_of_a_remote_tracking_trunk_is_the_local_branch(repo_r):
    worktree = add_linked_worktree(repo_r, "feature-x", start="origin/main")

    context = lane_core.lane_context("origin/main", worktree)

    assert context is not None
    assert (context.trunk_ref, context.trunk_branch) == ("origin/main", "main")


def test_a_lane_finds_the_primary_checkout_not_itself(repo_r):
    worktree = add_linked_worktree(repo_r, "feature-x")

    assert lane_core.primary_checkout(worktree) == repo_r.path.resolve()


# --- refusal registry coverage ------------------------------------------------


def _covered_whats() -> set[str]:
    """Every `@covers("<what>")` literal in this file, read from the source."""
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    whats: set[str] = set()
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call) and getattr(node.func, "id", None) == "covers"
        ):
            continue
        whats.update(arg.value for arg in node.args if isinstance(arg, ast.Constant))
    return whats


def test_every_registered_refusal_has_a_covering_test():
    missing = set(lane_core.REFUSALS) - _covered_whats()

    assert not missing, (
        f"no @covers(...) test for registered refusals: {sorted(missing)}"
    )


def test_every_covers_literal_is_in_the_final_vocabulary():
    assert _covered_whats() <= FINAL_VOCABULARY


def test_the_registry_only_holds_final_vocabulary_keys():
    assert set(lane_core.REFUSALS) <= FINAL_VOCABULARY
