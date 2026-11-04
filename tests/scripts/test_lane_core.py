"""Tests for plugins/dev-team/scripts/lane_core.py.

The refusal registry and renderer, the git seam and its guard, the argv
oracle that watches every git call, trunk resolution, and lane detection.
Every test runs in-process against real git repositories built by
`lane_fixtures`. The command line itself is tested in `test_lane.py`.
"""

# Fixtures from lane_fixtures are imported by name so pytest finds them; a
# test argument of the same name then looks like an unused import and a
# redefinition to ruff.
# ruff: noqa: F401, F811

from __future__ import annotations

import ast
import dataclasses
import subprocess
import sys
from pathlib import Path

import pytest
from lane_fixtures import (
    ORACLE_FORBIDDEN_TOKENS,
    ArgvSpy,
    add_linked_worktree,
    argv_spy,
    commit_file,
    covered_whats,
    enforce_covers,
    forbidden_hits,
    git,
    hermetic_process_env,
    imported_modules,
    non_stdlib,
    repo_with_origin,
    repo_without_remote,
)

from _repo_root import REPO_ROOT

SCRIPTS_DIR = REPO_ROOT / "plugins" / "dev-team" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import lane_core

TEST_DIR = Path(__file__).resolve().parent
TEST_SOURCES = [TEST_DIR / "test_lane.py", TEST_DIR / "test_lane_core.py"]

#: Every `what` the finished tool can print. A `covers` literal outside this
#: set is a typo; every key registered so far must be covered.
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

GIT_FAILED = "git command failed"

#: Sample constructor arguments for every registered refusal.
SAMPLE_ARGUMENTS = {
    "git command failed": ("git status", "fatal: boom"),
    "invalid lane name": ("bad name", "a reason"),
    "branch exists": ("taken",),
    "path exists": (Path("/occupied"),),
    "trunk ref cannot be resolved": ("missing-ref",),
    "not a git repository": (Path("/plain"),),
}

#: Every argv the guard rejects: id -> (args, text the reason must contain).
#: The reason proves which check fired, not just that something did.
GUARD_CASES = {
    "push": (["push", "origin", "main"], "subcommand push"),
    "send-pack": (["send-pack", "somewhere"], "subcommand send-pack"),
    "push-after-C": (["-C", "/tmp", "push"], "subcommand push"),
    "push-after-git-dir": (["--git-dir", "/x", "push"], "subcommand push"),
    "push-after-work-tree": (["--work-tree", "/x", "push"], "subcommand push"),
    "push-after-namespace": (["--namespace", "n", "push"], "subcommand push"),
    "push-after-super-prefix": (["--super-prefix", "p", "push"], "subcommand push"),
    "push-after-config-env-value": (["--config-env", "a=B", "push"], "--config-env"),
    "--no-verify": (["commit", "--no-verify", "-m", "x"], "option --no-verify"),
    "--force": (["branch", "--force", "x"], "option --force"),
    "--force-with-lease": (
        ["branch", "--force-with-lease", "x"],
        "option --force-with-lease",
    ),
    "-f": (["branch", "-f", "x"], "option -f"),
    "--no-gpg-sign": (["commit", "--no-gpg-sign", "-m", "x"], "option --no-gpg-sign"),
    "hooksPath-via-c": (["-c", "core.hooksPath=/hooks", "status"], "core.hooksPath"),
    "hooksPath-via-c-lowercase": (
        ["-c", "core.hookspath=/hooks", "status"],
        "core.hooksPath",
    ),
    "hooksPath-via-config": (["config", "core.hooksPath=/hooks"], "core.hooksPath"),
    "hooksPath-via-config-uppercase": (
        ["config", "CORE.HOOKSPATH=/hooks"],
        "core.hooksPath",
    ),
    "other-config-override": (["-c", "user.name=x", "status"], "only -c diff.relative"),
    "config-env-equals-form": (["--config-env=a=B", "status"], "--config-env"),
    "force-refspec": (["fetch", "origin", "+refs/heads/*:refs/x/*"], "forcing refspec"),
    "force-refspec-short": (["fetch", "origin", "+main"], "forcing refspec"),
}


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


def test_git_command_failed_names_the_command_and_the_detail():
    refusal = lane_core.git_command_failed_refusal("git status", "fatal: boom")

    assert refusal.what == GIT_FAILED
    assert "fatal: boom" in refusal.why
    assert "git status" in refusal.why
    assert "git status" in refusal.how


def test_git_command_failed_stays_complete_when_git_said_nothing():
    refusal = lane_core.git_command_failed_refusal("git status", "  ")

    assert refusal.why.strip() != ""


def test_a_trunk_refusal_tells_an_explicit_ref_from_a_default_one():
    explicit = lane_core.trunk_unresolved_refusal("mine")
    default = lane_core.trunk_unresolved_refusal("origin/gone", is_default=True)
    none_found = lane_core.trunk_unresolved_refusal(None)

    assert "'mine'" in explicit.why and "default" not in explicit.why
    assert "'origin/gone'" in default.why and "default" in default.why
    assert "no default branch" in none_found.why


# --- registry ---------------------------------------------------------------


def test_every_registered_refusal_has_sample_arguments():
    assert set(lane_core.REFUSALS) == set(SAMPLE_ARGUMENTS)


@pytest.mark.parametrize("what", sorted(SAMPLE_ARGUMENTS))
def test_each_registered_constructor_builds_a_refusal_with_its_own_key(what):
    refusal = lane_core.REFUSALS[what](*SAMPLE_ARGUMENTS[what])

    assert refusal.what == what


def test_a_constructor_cannot_register_under_a_key_that_differs_from_its_what(
    monkeypatch,
):
    monkeypatch.setattr(lane_core, "REFUSALS", {})

    @lane_core._registered("registered as")
    def drifted() -> lane_core.Refusal:
        return lane_core.Refusal(what="built as", why="y", how="h")

    with pytest.raises(ValueError, match="registered as 'registered as'.*'built as'"):
        lane_core.REFUSALS["registered as"]()


def test_every_registered_refusal_has_a_covering_test():
    missing = set(lane_core.REFUSALS) - covered_whats(TEST_SOURCES)

    assert not missing, (
        f"no @covers(...) test for registered refusals: {sorted(missing)}"
    )


def test_every_covers_literal_is_in_the_final_vocabulary():
    assert covered_whats(TEST_SOURCES) <= FINAL_VOCABULARY


def test_the_registry_only_holds_final_vocabulary_keys():
    assert set(lane_core.REFUSALS) <= FINAL_VOCABULARY


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


# --- the git seam and its guard ---------------------------------------------


@pytest.mark.parametrize(
    ("args", "reason"), GUARD_CASES.values(), ids=GUARD_CASES.keys()
)
def test_the_guard_rejects_and_runs_nothing(args, reason, tmp_path, argv_spy):
    records_before = len(argv_spy.records)

    with pytest.raises(lane_core.RefusalError) as caught:
        lane_core._git(args, tmp_path)

    assert caught.value.refusal.what == GIT_FAILED
    assert reason in caught.value.refusal.why
    assert argv_spy.records[records_before:] == []


@pytest.mark.parametrize("subcommand", sorted(lane_core.FORBIDDEN_SUBCOMMANDS))
def test_the_guard_rejects_every_forbidden_subcommand(subcommand, tmp_path):
    with pytest.raises(lane_core.RefusalError):
        lane_core._git([subcommand], tmp_path)


@pytest.mark.parametrize("token", sorted(lane_core.FORBIDDEN_TOKENS))
def test_the_guard_rejects_every_forbidden_token(token, tmp_path):
    with pytest.raises(lane_core.RefusalError):
        lane_core._git(["status", token], tmp_path)


def test_the_guard_allows_the_one_permitted_config_override(repo_without_remote):
    head = lane_core.git_text(
        ["-c", "diff.relative=false", "rev-parse", "--verify", "HEAD"],
        repo_without_remote.path,
    )

    assert head == git(repo_without_remote.path, "rev-parse", "HEAD")


def test_the_guard_reads_the_subcommand_not_a_substring(repo_without_remote):
    repo = repo_without_remote.path

    lane_core.git_text(["branch", "pushed"], repo)

    assert git(repo, "rev-parse", "--verify", "pushed") == git(
        repo, "rev-parse", "HEAD"
    )


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


def test_a_missing_git_binary_is_a_refusal_that_names_the_command(
    monkeypatch, tmp_path
):
    def missing(*_args, **_kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", missing)

    with pytest.raises(lane_core.RefusalError) as caught:
        lane_core._git(["status"], tmp_path)

    assert caught.value.refusal.what == GIT_FAILED
    assert "git status" in caught.value.refusal.why


def test_a_git_call_that_hangs_is_a_refusal_after_the_timeout(monkeypatch, tmp_path):
    def hang(argv, **_kwargs):
        raise subprocess.TimeoutExpired(argv, lane_core.GIT_TIMEOUT_SECONDS)

    monkeypatch.setattr(subprocess, "run", hang)

    with pytest.raises(lane_core.RefusalError) as caught:
        lane_core._git(["fetch"], tmp_path)

    refusal = caught.value.refusal
    assert refusal.what == GIT_FAILED
    assert f"timed out after {lane_core.GIT_TIMEOUT_SECONDS} s" in refusal.why
    assert "git fetch" in refusal.why


def test_git_runs_with_a_timeout_and_no_stdin(monkeypatch, tmp_path):
    seen: dict[str, object] = {}

    def capture(argv, **kwargs):
        seen.update(kwargs)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", capture)

    lane_core._git(["status"], tmp_path)

    assert seen["timeout"] == lane_core.GIT_TIMEOUT_SECONDS
    assert seen["stdin"] is subprocess.DEVNULL


# Calls that start a process, by module. An alias or a `from` import of one of
# these is resolved before counting.
_SPAWNERS = {
    "subprocess": {
        "run",
        "Popen",
        "call",
        "check_output",
        "check_call",
        "getoutput",
        "getstatusoutput",
    },
    "os": {"system", "popen"},
}


def _spawning_calls(source: str) -> int:
    """Count calls that start a process, resolving aliases and `from` imports."""
    tree = ast.parse(source)
    module_names: dict[str, str] = {}
    function_names: dict[str, tuple[str, str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in _SPAWNERS:
                    module_names[alias.asname or alias.name] = alias.name
        if isinstance(node, ast.ImportFrom) and node.module in _SPAWNERS:
            for alias in node.names:
                function_names[alias.asname or alias.name] = (node.module, alias.name)
    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            module = module_names.get(func.value.id)
            count += module is not None and func.attr in _SPAWNERS[module]
        if isinstance(func, ast.Name) and func.id in function_names:
            module, attr = function_names[func.id]
            count += attr in _SPAWNERS[module]
    return count


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import subprocess\nsubprocess.run(['a'])", 1),
        ("import subprocess as sp\nsp.run(['a'])", 1),
        ("from subprocess import run\nrun(['a'])", 1),
        ("from subprocess import Popen as P\nP(['a'])", 1),
        ("import os\nos.system('x')", 1),
        ("import os as o\no.popen('x')", 1),
        ("import subprocess\nsubprocess.run([])\nsubprocess.check_output([])", 2),
        ("import subprocess\nsubprocess.list2cmdline([])", 0),
        ("import os\nos.getcwd()", 0),
    ],
)
def test_the_process_call_counter_sees_aliases_and_from_imports(source, expected):
    assert _spawning_calls(source) == expected


def test_run_is_the_only_process_call_in_lane_core():
    source = (SCRIPTS_DIR / "lane_core.py").read_text(encoding="utf-8")

    assert _spawning_calls(source) == 1


def test_lane_starts_no_process_itself():
    assert _spawning_calls((SCRIPTS_DIR / "lane.py").read_text(encoding="utf-8")) == 0


def test_no_subprocess_call_in_lane_core_uses_shell_true():
    tree = ast.parse((SCRIPTS_DIR / "lane_core.py").read_text(encoding="utf-8"))
    shell_keywords = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.keyword) and node.arg == "shell"
    ]

    assert shell_keywords == []


def test_lane_core_imports_only_stdlib_and_review_gate_hash():
    modules = imported_modules(SCRIPTS_DIR / "lane_core.py")

    assert non_stdlib(modules) == {"review_gate_hash"}


def test_lane_core_never_imports_lane():
    assert "lane" not in imported_modules(SCRIPTS_DIR / "lane_core.py")


# --- the argv oracle ----------------------------------------------------------


@pytest.mark.parametrize(
    "argv",
    [
        ["git", "push", "origin", "main"],
        ["git", "send-pack", "somewhere"],
        ["git", "commit", "--no-verify"],
        ["git", "branch", "-f", "x"],
        ["git", "branch", "--force", "x"],
        ["git", "-c", "core.hooksPath=/hooks", "status"],
        ["git", "-c", "CORE.HOOKSPATH=/hooks", "status"],
        ["git", "fetch", "origin", "+main:main"],
    ],
)
def test_the_oracle_flags_a_forbidden_call(argv):
    spy = ArgvSpy()
    spy.records.append(argv)

    assert spy.violations() == [argv]
    assert forbidden_hits(argv) != []


def test_the_oracle_does_not_flag_a_branch_that_merely_looks_like_push():
    spy = ArgvSpy()
    spy.records.append(["git", "branch", "pushed"])

    assert spy.violations() == []


def test_the_oracle_and_the_guard_forbid_the_same_words():
    guarded = lane_core.FORBIDDEN_TOKENS | lane_core.FORBIDDEN_SUBCOMMANDS

    assert ORACLE_FORBIDDEN_TOKENS == guarded


def test_the_spy_records_a_call_made_inside_a_library_module(
    repo_with_origin, argv_spy
):
    records_before = len(argv_spy.records)

    lane_core.resolve_trunk(None, repo_with_origin.path)

    recorded = argv_spy.records[records_before:]
    assert ["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"] in recorded


def test_the_spy_records_a_bare_popen(argv_spy):
    records_before = len(argv_spy.records)

    subprocess.Popen(["git", "--version"], stdout=subprocess.DEVNULL).wait()

    assert argv_spy.records[records_before:] == [["git", "--version"]]


def test_the_spy_records_a_run_once(argv_spy):
    records_before = len(argv_spy.records)

    subprocess.run(["git", "--version"], capture_output=True, check=False)

    assert argv_spy.records[records_before:] == [["git", "--version"]]


# --- require_work_tree ------------------------------------------------------


def test_inside_a_work_tree_is_accepted(repo_without_remote):
    lane_core.require_work_tree(repo_without_remote.path)


def test_a_plain_directory_is_not_a_work_tree(tmp_path):
    with pytest.raises(lane_core.RefusalError) as caught:
        lane_core.require_work_tree(tmp_path)

    assert caught.value.refusal.what == "not a git repository"
    assert str(tmp_path) in caught.value.refusal.why


def test_the_git_directory_itself_is_not_a_work_tree(repo_without_remote):
    git_dir = repo_without_remote.path / ".git"

    with pytest.raises(lane_core.RefusalError) as caught:
        lane_core.require_work_tree(git_dir)

    assert caught.value.refusal.what == "not a git repository"


# --- resolve_trunk ----------------------------------------------------------


def test_trunk_defaults_to_the_local_branch_without_a_remote(repo_without_remote):
    assert lane_core.resolve_trunk(None, repo_without_remote.path) == "main"


def test_trunk_defaults_to_the_remote_tracking_branch(repo_with_origin):
    assert lane_core.resolve_trunk(None, repo_with_origin.path) == "origin/main"


@pytest.mark.parametrize("ref", ["main", "HEAD"])
def test_an_explicit_resolvable_trunk_is_returned_as_given(ref, repo_without_remote):
    assert lane_core.resolve_trunk(ref, repo_without_remote.path) == ref


def test_a_tag_is_a_usable_trunk(repo_with_origin):
    git(repo_with_origin.path, "tag", "v1", "origin/main")

    assert lane_core.resolve_trunk("v1", repo_with_origin.path) == "v1"


def test_a_tag_on_a_tree_is_not_a_trunk(repo_without_remote):
    repo = repo_without_remote.path
    git(repo, "tag", "tree-tag", git(repo, "rev-parse", "HEAD^{tree}"))

    assert lane_core.resolve_trunk("tree-tag", repo) is None


def test_an_unknown_ref_is_not_a_trunk(repo_without_remote):
    assert lane_core.resolve_trunk("missing-ref", repo_without_remote.path) is None


@pytest.mark.parametrize(
    "ref", ["-lead", "--help", "bad name", "a;b", "", "main^{tree}", "$(x)"]
)
def test_a_malformed_trunk_is_rejected_before_git_runs(ref, tmp_path, argv_spy):
    records_before = len(argv_spy.records)

    assert lane_core.resolve_trunk(ref, tmp_path) is None
    assert argv_spy.records[records_before:] == []


def test_no_default_and_no_argument_gives_none(tmp_path):
    commitless_repo = tmp_path / "empty"
    commitless_repo.mkdir()
    git(commitless_repo, "init", "-q", "-b", "trunk-less")

    assert lane_core.resolve_trunk(None, commitless_repo) is None


def test_resolve_trunk_commit_returns_the_ref_and_its_commit(repo_with_origin):
    repo = repo_with_origin.path

    assert lane_core.resolve_trunk_commit(None, repo) == (
        "origin/main",
        git(repo, "rev-parse", "origin/main"),
    )


def test_resolve_trunk_commit_names_an_explicit_ref_that_fails(repo_without_remote):
    with pytest.raises(lane_core.RefusalError) as caught:
        lane_core.resolve_trunk_commit("missing-ref", repo_without_remote.path)

    assert caught.value.refusal.what == "trunk ref cannot be resolved"
    assert "'missing-ref'" in caught.value.refusal.why
    assert "default" not in caught.value.refusal.why


def test_resolve_trunk_commit_names_a_dangling_default_ref(repo_without_remote):
    repo = repo_without_remote.path
    git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/gone")

    with pytest.raises(lane_core.RefusalError) as caught:
        lane_core.resolve_trunk_commit(None, repo)

    assert "'origin/gone'" in caught.value.refusal.why
    assert "default" in caught.value.refusal.why


def test_resolve_trunk_commit_says_so_when_no_default_exists(tmp_path):
    repo_without_default_branch = tmp_path / "odd"
    repo_without_default_branch.mkdir()
    git(repo_without_default_branch, "init", "-q", "-b", "elsewhere", home=tmp_path)
    commit_file(repo_without_default_branch, "a.txt", "a\n", "a")

    with pytest.raises(lane_core.RefusalError) as caught:
        lane_core.resolve_trunk_commit(None, repo_without_default_branch)

    assert "no --trunk was given" in caught.value.refusal.why


# --- local_branch_of --------------------------------------------------------


def test_a_local_branch_maps_to_itself(repo_without_remote):
    assert lane_core.local_branch_of("main", repo_without_remote.path) == "main"


@pytest.mark.parametrize(
    "ref",
    [
        "origin/main",
        "refs/remotes/origin/main",
        "remotes/origin/main",
        "refs/heads/main",
        "heads/main",
    ],
)
def test_every_spelling_of_the_trunk_maps_to_the_local_branch(ref, repo_with_origin):
    assert lane_core.local_branch_of(ref, repo_with_origin.path) == "main"


def test_a_slash_in_the_branch_name_survives(repo_with_origin):
    git(repo_with_origin.origin, "branch", "feat/x", "main")
    git(repo_with_origin.path, "fetch", "-q", "origin")

    assert lane_core.local_branch_of("origin/feat/x", repo_with_origin.path) == "feat/x"


def test_a_remote_name_with_a_slash_is_stripped_whole(repo_with_origin):
    repo = repo_with_origin.path
    for remote in ("team", "team/up"):
        git(repo, "remote", "add", remote, str(repo_with_origin.origin))
        git(repo, "fetch", "-q", remote)

    assert lane_core.local_branch_of("team/up/main", repo) == "main"
    assert lane_core.local_branch_of("team/main", repo) == "main"


def test_a_tag_maps_to_itself(repo_with_origin):
    git(repo_with_origin.path, "tag", "v1")

    assert lane_core.local_branch_of("v1", repo_with_origin.path) == "v1"


def test_a_sha_maps_to_itself(repo_without_remote):
    sha = git(repo_without_remote.path, "rev-parse", "HEAD")

    assert lane_core.local_branch_of(sha, repo_without_remote.path) == sha


# --- lane_context -----------------------------------------------------------


def test_the_primary_checkout_is_not_a_lane(repo_without_remote):
    assert lane_core.lane_context("main", repo_without_remote.path) is None


def test_the_primary_checkout_on_another_branch_is_not_a_lane(repo_without_remote):
    git(repo_without_remote.path, "switch", "-q", "-c", "side")

    assert lane_core.lane_context("main", repo_without_remote.path) is None


def test_a_linked_worktree_on_its_own_branch_is_a_lane(repo_without_remote):
    worktree = add_linked_worktree(repo_without_remote, "feature-x")

    context = lane_core.lane_context("main", worktree)

    assert context == lane_core.LaneContext(
        lane_path=worktree.resolve(),
        branch="feature-x",
        trunk_ref="main",
        trunk_branch="main",
        primary_path=repo_without_remote.path.resolve(),
    )


def test_a_subdirectory_of_a_lane_reports_the_lane_root(repo_without_remote):
    worktree = add_linked_worktree(repo_without_remote, "feature-x")
    (worktree / "sub").mkdir()

    context = lane_core.lane_context("main", worktree / "sub")

    assert context is not None
    assert context.lane_path == worktree.resolve()
    assert context.primary_path == repo_without_remote.path.resolve()


def test_a_detached_head_in_a_linked_worktree_is_not_a_lane(repo_without_remote):
    worktree = add_linked_worktree(repo_without_remote, "feature-x")
    git(worktree, "checkout", "-q", "--detach")

    assert lane_core.lane_context("main", worktree) is None


@pytest.mark.parametrize(
    "trunk_ref",
    [
        "origin/main",
        "refs/remotes/origin/main",
        "main",
        "refs/heads/main",
        "heads/main",
    ],
)
def test_a_linked_worktree_on_the_trunk_branch_is_not_a_lane_for_any_trunk_spelling(
    trunk_ref, repo_with_origin, tmp_path
):
    git(repo_with_origin.path, "switch", "-q", "-c", "parking")
    on_trunk = tmp_path / "on-trunk"
    git(repo_with_origin.path, "worktree", "add", "-q", str(on_trunk), "main")

    assert lane_core.lane_context(trunk_ref, on_trunk) is None


def test_the_trunk_branch_of_a_remote_tracking_trunk_is_the_local_branch(
    repo_with_origin,
):
    worktree = add_linked_worktree(repo_with_origin, "feature-x", start="origin/main")

    context = lane_core.lane_context("origin/main", worktree)

    assert context is not None
    assert (context.trunk_ref, context.trunk_branch) == ("origin/main", "main")


# --- primary_checkout -------------------------------------------------------


def test_a_lane_finds_the_primary_checkout_not_itself(repo_with_origin):
    worktree = add_linked_worktree(repo_with_origin, "feature-x")

    assert lane_core.primary_checkout(worktree) == repo_with_origin.path.resolve()


def test_the_primary_checkout_finds_itself(repo_without_remote):
    assert (
        lane_core.primary_checkout(repo_without_remote.path)
        == repo_without_remote.path.resolve()
    )


def test_a_separate_git_dir_checkout_gets_the_main_worktree_git_lists(tmp_path):
    repo = tmp_path / "sep"
    git_dir = tmp_path / "gd"
    git(
        tmp_path,
        "init",
        "-q",
        "-b",
        "main",
        "--separate-git-dir",
        str(git_dir),
        str(repo),
    )
    commit_file(repo, "a.txt", "a\n", "a")
    lane_dir = tmp_path / "sep-lane"
    git(repo, "worktree", "add", "-q", "-b", "x", str(lane_dir))
    listing = git(lane_dir, "worktree", "list", "--porcelain").splitlines()
    # Which path git lists first depends on the git version when the git
    # directory lives apart from the work tree; the contract is to follow git.
    listed = Path(listing[0].removeprefix("worktree ")).resolve()

    context = lane_core.lane_context("main", lane_dir)

    assert lane_core.primary_checkout(lane_dir) == listed
    assert context is not None
    assert context.primary_path == listed


def test_a_bare_primary_is_the_bare_repository(repo_without_remote, tmp_path):
    bare = tmp_path / "bare.git"
    git(tmp_path, "clone", "-q", "--bare", str(repo_without_remote.path), str(bare))
    from_bare = tmp_path / "from-bare"
    git(bare, "worktree", "add", "-q", "-b", "feat", str(from_bare), "main")

    assert lane_core.primary_checkout(from_bare) == bare.resolve()


@pytest.fixture
def without_worktree_listing(monkeypatch):
    """`git worktree list` gives nothing, so only the common directory is left."""
    real = lane_core.git_text

    def silent(args, cwd):
        return "" if list(args[:2]) == ["worktree", "list"] else real(args, cwd)

    monkeypatch.setattr(lane_core, "git_text", silent)


def test_without_a_listing_a_dot_git_directory_gives_its_parent(
    repo_without_remote, without_worktree_listing
):
    assert (
        lane_core.primary_checkout(repo_without_remote.path)
        == repo_without_remote.path.resolve()
    )


def test_without_a_listing_a_bare_directory_is_its_own_primary(
    repo_without_remote, tmp_path, without_worktree_listing
):
    bare = tmp_path / "bare.git"
    git(tmp_path, "clone", "-q", "--bare", str(repo_without_remote.path), str(bare))

    assert lane_core.primary_checkout(bare) == bare.resolve()
