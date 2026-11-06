"""Fixtures, builders and assertions for the `lane.py integrate` tests.

Shared by `test_lane_integrate_checks.py`, `test_lane_integrate_command.py` and
`test_lane_structure.py`. Built on `lane_fixtures` (repositories, the argv
oracle, `GitFailure`); named without a leading `test_` so pytest does not
collect it.

The autouse fixtures of `lane_fixtures` apply only to a test module that
imports them by name; the pytest fixtures defined here (`composed_without_remote`,
`composed_with_origin`) are imported the same way.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from lane_fixtures import (
    GITHUB_URL,
    TRUNK,
    Repo,
    build_repo_with_origin,
    build_repo_without_remote,
    commit_file,
    default_lane_dir,
    git,
    git_succeeds,
    is_ancestor,
    parse_blocks,
    parse_output,
    run_main,
    set_origin_url,
    single_refusal,
    unchanged_state,
    use_github_origin,
)

from _repo_root import REPO_ROOT

# `lane_fixtures` puts the lane scripts and `hooks/lib` on `sys.path`; import
# them after it.
# isort: split

import lane
import lane_core
from review_gate_hash import branch_diff_gate_hash

PR_HOOK_PATH = REPO_ROOT / "plugins" / "dev-team" / "hooks" / "pre_pr_review.py"

GATE_RELATIVE_PATH = Path(".claude") / "memory" / ".pr-review-passed"
LEDGER_RELATIVE_PATH = Path(".claude") / "metrics" / "boundary-events.jsonl"
#: Two distinct registered review agents: the PR hook counts distinct names.
GATE_DISPATCH_AGENTS = ("security-review", "structure-review")
GATE_DISPATCH_AGE_SECONDS = 60
#: How far outside the hook's recency window a "too old" dispatch is stamped.
STALE_MARGIN_SECONDS = 120
#: Age of a dispatch-failure row: newer than the dispatches it vetoes.
FAILURE_AGE_SECONDS = 30
#: A gate hash that belongs to no lane's content.
OTHER_CONTENT_HASH = "e" * 64

#: A host that only looks like GitHub: not a PR repository.
LOOKALIKE_URL = "https://notgithub.example.com/acme/widgets.git"

#: Git subcommands that talk to a remote. An `integrate` run starts none.
NETWORK_ARGV_PREFIXES = (
    ["git", "fetch"],
    ["git", "pull"],
    ["git", "ls-remote"],
    ["git", "push"],
    ["git", "clone"],
    ["git", "remote", "update"],
)


# --- the review gate: ledger rows, the gate file, the seeds ----------------------


def ledger_row(
    hook: str, decision: str, matched_rule: str, subject_hash: str, age_seconds: int
) -> dict[str, str]:
    """One boundary-events row stamped `age_seconds` before now.

    Stamped from the real clock. The hook's window is `WINDOW_SECONDS` (1800 s)
    and every age used here is at least `FAILURE_AGE_SECONDS` away from both
    edges, so the seconds a test run takes cannot flip a verdict.
    """
    stamp = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    return {
        "ts": stamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "hook": hook,
        "tool": "Agent",
        "decision": decision,
        "matched_rule": matched_rule,
        "plugin_version": "0.0.0",
        "subject_hash": subject_hash,
    }


def dispatch_row(agent: str, subject_hash: str, age_seconds: int) -> dict[str, str]:
    """A genuine review-agent dispatch, as the dispatch ledger records it."""
    return ledger_row(
        "agent_dispatch_ledger", "record", agent, subject_hash, age_seconds
    )


def append_ledger(lane_path: Path, rows: Iterable[dict[str, str]]) -> None:
    ledger = lane_path / LEDGER_RELATIVE_PATH
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row) + "\n")


def gate_hash_of(lane_path: Path, trunk_ref: str) -> str:
    """The real branch-diff gate hash of the lane against `trunk_ref`."""
    return branch_diff_gate_hash(trunk_ref, cwd=lane_path)


def write_gate_file(lane_path: Path, content: str) -> Path:
    gate = lane_path / GATE_RELATIVE_PATH
    gate.parent.mkdir(parents=True, exist_ok=True)
    gate.write_text(content, encoding="utf-8")
    return gate


def seed_gate(
    lane_path: Path,
    trunk_ref: str,
    agents: Sequence[str] = GATE_DISPATCH_AGENTS,
    age_seconds: int = GATE_DISPATCH_AGE_SECONDS,
) -> str:
    """Write the PR review gate for the lane's current state; return its hash.

    The hash is the real `branch_diff_gate_hash("<trunk_ref>")` of the lane, in
    the gate file, and the ledger holds one dispatch per distinct agent bound to
    it, stamped `age_seconds` before now (by default inside the hook's window).
    Writes only inside the lane's `.claude/`.

    Provenance: the hash is the real `branch_diff_gate_hash`, whose correctness
    the `review_gate_hash` tests cover; this only binds a gate to the lane's
    current state.
    """
    gate_hash = gate_hash_of(lane_path, trunk_ref)
    write_gate_file(lane_path, gate_hash)
    append_ledger(
        lane_path, [dispatch_row(agent, gate_hash, age_seconds) for agent in agents]
    )
    return gate_hash


def load_pr_hook():
    """The PR hook module, loaded here independently of `lane.py`."""
    spec = importlib.util.spec_from_file_location("pr_hook_under_parity", PR_HOOK_PATH)
    module = importlib.util.module_from_spec(spec)
    saved_path = list(sys.path)  # the hook puts its own lib directory first
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = saved_path
    return module


# Seeds for the gate parity table: each leaves the lane in one gate state. Every
# seed takes the lane's real gate hash; `seed_missing` and the two seeds that
# build the gate file by hand ignore it.
def seed_missing(composed, gate_hash):
    pass


def seed_different_content(composed, gate_hash):
    write_gate_file(composed.path, OTHER_CONTENT_HASH)


def seed_hash_only(composed, gate_hash):
    write_gate_file(composed.path, gate_hash)


def seed_hash_and_empty_ledger(composed, gate_hash):
    seed_hash_only(composed, gate_hash)
    ledger = composed.path / LEDGER_RELATIVE_PATH
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text("", encoding="utf-8")


def seed_one_dispatch(composed, gate_hash):
    seed_hash_only(composed, gate_hash)
    append_ledger(
        composed.path,
        [dispatch_row(GATE_DISPATCH_AGENTS[0], gate_hash, GATE_DISPATCH_AGE_SECONDS)],
    )


def seed_two_dispatches(composed, gate_hash):
    seed_gate(composed.path, composed.trunk_ref)


def seed_old_dispatches(composed, gate_hash):
    seed_hash_only(composed, gate_hash)
    age = load_pr_hook().WINDOW_SECONDS + STALE_MARGIN_SECONDS
    append_ledger(
        composed.path,
        [dispatch_row(agent, gate_hash, age) for agent in GATE_DISPATCH_AGENTS],
    )


def seed_doc_only_exemption(composed, gate_hash):
    seed_hash_only(composed, gate_hash)
    append_ledger(
        composed.path,
        [
            ledger_row(
                "code-review",
                "bypass",
                "doc-only-review-exempt",
                gate_hash,
                GATE_DISPATCH_AGE_SECONDS,
            )
        ],
    )


def seed_dispatches_for_other_content(composed, gate_hash):
    seed_hash_only(composed, gate_hash)
    append_ledger(
        composed.path,
        [
            dispatch_row(agent, OTHER_CONTENT_HASH, GATE_DISPATCH_AGE_SECONDS)
            for agent in GATE_DISPATCH_AGENTS
        ],
    )


def seed_dispatch_failure(composed, gate_hash):
    seed_two_dispatches(composed, gate_hash)
    append_ledger(
        composed.path,
        [
            ledger_row(
                "code-review",
                "dispatch-failure",
                GATE_DISPATCH_AGENTS[0],
                gate_hash,
                FAILURE_AGE_SECONDS,
            )
        ],
    )


def seed_gate_is_a_directory(composed, gate_hash):
    (composed.path / GATE_RELATIVE_PATH).mkdir(parents=True)


def seed_binary_garbage(composed, gate_hash):
    gate = composed.path / GATE_RELATIVE_PATH
    gate.parent.mkdir(parents=True)
    gate.write_bytes(b"\xff\xfe\x00\x80 not a hash \x00")


def seed_legacy_location_only(composed, gate_hash):
    """The gate file where the hook used to keep it (`<lane>/memory/`), none in `.claude/`."""
    legacy = composed.path / "memory" / GATE_RELATIVE_PATH.name
    legacy.parent.mkdir()
    legacy.write_text(gate_hash, encoding="utf-8")
    append_ledger(
        composed.path,
        [
            dispatch_row(agent, gate_hash, GATE_DISPATCH_AGE_SECONDS)
            for agent in GATE_DISPATCH_AGENTS
        ],
    )


# --- a composed lane ------------------------------------------------------------


@dataclass(frozen=True)
class ComposedLane:
    """A lane after `compose`, with its gate seeded and the identities printed."""

    repo: Repo
    path: Path
    name: str
    trunk_ref: str
    expected_trunk: str
    expected_tree: str


def composed_gated_lane(
    repo: Repo,
    capsys,
    name: str = "feature",
    gate: bool = True,
    lane_file: str | None = "lane.txt",
) -> ComposedLane:
    """`main(open)`, one lane commit, `main(compose)`, then `seed_gate`.

    The lane and its identities come from the tool's own stdout, as a user
    gets them. `gate=False` leaves the lane without a gate file (and without
    the `.claude/` directory the gate would create). `lane_file` is the one
    file the lane commits; None commits nothing (an empty lane).
    """
    code, _, _ = run_main(["open", name], repo.path, capsys)
    assert code == 0
    # Where `open` puts it by default, not read from its output: a path with a
    # newline in it cannot be read back from lines.
    path = default_lane_dir(repo, name)
    if lane_file is not None:
        commit_file(path, lane_file, "lane\n", "lane work")
    code, out, _ = run_main(["compose"], path, capsys)
    assert code == 0
    printed = parse_output(out)
    trunk_ref = printed["trunk"]
    if gate:
        seed_gate(path, trunk_ref)
    return ComposedLane(
        repo=repo,
        path=path,
        name=name,
        trunk_ref=trunk_ref,
        expected_trunk=printed["expected-trunk"],
        expected_tree=printed["expected-tree"],
    )


def build_composed_without_remote(tmp_path, capsys) -> ComposedLane:
    """A composed, gated lane in a repository with no remote."""
    return composed_gated_lane(build_repo_without_remote(tmp_path), capsys)


def build_composed_with_other_origin(
    tmp_path, capsys, url: str | None = None
) -> ComposedLane:
    """A composed, gated lane whose `origin` is not on GitHub (`url`, else a bare
    repository on disk)."""
    repo = build_repo_with_origin(tmp_path)
    composed = composed_gated_lane(repo, capsys)
    if url is not None:
        set_origin_url(repo, url)
    return composed


def build_composed_with_github_origin(
    tmp_path, capsys, url: str = GITHUB_URL
) -> ComposedLane:
    """A composed, gated lane whose `origin` is on GitHub (a PR repository)."""
    repo = build_repo_with_origin(tmp_path)
    composed = composed_gated_lane(repo, capsys)
    use_github_origin(repo, url)
    return composed


@pytest.fixture
def composed_without_remote(repo_without_remote, capsys) -> ComposedLane:
    return composed_gated_lane(repo_without_remote, capsys)


@pytest.fixture
def composed_with_origin(repo_with_origin, capsys) -> ComposedLane:
    return composed_gated_lane(repo_with_origin, capsys)


# --- faults and probes -------------------------------------------------------------


def leave_untracked_file(worktree: Path) -> None:
    (worktree / "scratch.txt").write_text("x\n", encoding="utf-8")


def edit_tracked_file(worktree: Path) -> None:
    (worktree / "base.txt").write_text("edited\n", encoding="utf-8")


def branch_exists_in(repo_path: Path, branch: str) -> bool:
    return git_succeeds(
        repo_path, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"
    )


def claude_snapshot(worktree: Path) -> list[tuple[str, bool, bytes | None]]:
    """Every entry under `<worktree>/.claude`: (relative path, is a directory, bytes).

    `unchanged_state` collapses an ignored directory to one status line, so it
    cannot see a file written or changed inside `.claude/`; this can.
    """
    root = worktree / ".claude"
    if not root.exists():
        return []
    return sorted(
        (
            str(entry.relative_to(root)),
            entry.is_dir(),
            None if entry.is_dir() else entry.read_bytes(),
        )
        for entry in root.rglob("*")
    )


def observed_state(composed: ComposedLane) -> dict[str, object]:
    """What must be equal before and after a refused run: both worktrees (git
    state and everything under their `.claude/`), and the gate file's bytes
    (None when absent)."""
    gate = composed.path / GATE_RELATIVE_PATH
    return {
        "lane": unchanged_state(composed.path),
        "trunk": unchanged_state(composed.repo.path),
        "lane .claude": claude_snapshot(composed.path),
        "trunk .claude": claude_snapshot(composed.repo.path),
        "gate": gate.read_bytes() if gate.is_file() else None,
    }


# --- running integrate ---------------------------------------------------------------


class _Omit:
    def __repr__(self) -> str:
        return "OMIT"


#: Pass as `expected_trunk` or `expected_tree` to leave that flag out.
OMIT = _Omit()


def integrate_argv(
    composed: ComposedLane,
    *extra: str,
    expected_trunk: str | _Omit | None = None,
    expected_tree: str | _Omit | None = None,
) -> list[str]:
    """`integrate` with the composed identities. A string overrides an identity;
    `OMIT` leaves its flag out."""
    trunk = composed.expected_trunk if expected_trunk is None else expected_trunk
    tree = composed.expected_tree if expected_tree is None else expected_tree
    argv = ["integrate"]
    for flag, value in (("--expected-trunk", trunk), ("--expected-tree", tree)):
        if value is not OMIT:
            argv += [flag, value]
    return [*argv, *extra]


def run_integrate(
    composed: ComposedLane,
    capsys,
    *extra: str,
    cwd=None,
    expected_trunk: str | _Omit | None = None,
    expected_tree: str | _Omit | None = None,
):
    """`main(["integrate", ...])` in the lane; `(exit code, stdout, stderr)`."""
    argv = integrate_argv(
        composed, *extra, expected_trunk=expected_trunk, expected_tree=expected_tree
    )
    return run_main(argv, cwd or composed.path, capsys)


# --- the check engine, driven directly ---------------------------------------------------


def refusals_for(
    composed: ComposedLane,
    *,
    trunk: str | None = None,
    expected_trunk: str | None = None,
    expected_tree: str | None = None,
    cwd: Path | None = None,
    allow_local_integration: bool = False,
) -> list[lane_core.Refusal]:
    """The refusals the checks give for `composed`, with its own identities
    unless overridden. Changes nothing."""
    return lane.check_lane(
        trunk,
        expected_trunk or composed.expected_trunk,
        expected_tree or composed.expected_tree,
        cwd or composed.path,
        allow_local_integration=allow_local_integration,
    ).refusals


def printed_blocks(refusals, capsys) -> list[dict[str, str]]:
    """Print `refusals` as `main` would and return the parsed blocks."""
    code = lane_core.emit_refusals(refusals)
    captured = capsys.readouterr()
    assert (code, captured.out) == (1, "")
    return parse_blocks(captured.err)


def only_block(composed: ComposedLane, capsys, **overrides) -> dict[str, str]:
    """The single block the checks print for `composed`; nothing else changed."""
    before = observed_state(composed)
    (block,) = printed_blocks(refusals_for(composed, **overrides), capsys)
    assert observed_state(composed) == before
    for field in ("refused", "why", "how"):
        assert block[field].strip() != ""
    return block


def hook_exit_code(composed: ComposedLane, monkeypatch) -> int:
    """The PR hook's own `main()` on a `gh pr create` payload run in the lane."""
    payload = {"tool_input": {"command": "gh pr create"}, "cwd": str(composed.path)}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    return load_pr_hook().main()


def hook_block_rule(composed: ComposedLane) -> str:
    """The `matched_rule` the hook logged for its last block in the lane."""
    log = (composed.path / LEDGER_RELATIVE_PATH).read_text(encoding="utf-8")
    blocks = [
        json.loads(line)
        for line in log.splitlines()
        if '"pre_pr_review"' in line and '"block"' in line
    ]
    return blocks[-1]["matched_rule"]


# --- assertions ----------------------------------------------------------------------------


def assert_block_mentions(block: dict[str, str], pinned: dict[str, Sequence[str]]):
    """Each fragment appears in its own field of the block; a miss names it."""
    for field, fragments in pinned.items():
        for fragment in fragments:
            assert fragment in block[field], f"{fragment!r} not in {field}: {block}"


def assert_refused_unchanged(
    composed: ComposedLane,
    capsys,
    what: str,
    pinned: dict[str, Sequence[str]] | None = None,
    *extra: str,
    cwd=None,
    expected_trunk: str | _Omit | None = None,
    expected_tree: str | _Omit | None = None,
) -> dict[str, str]:
    """Run integrate: exactly one refusal of `what`, exit 1, and nothing changed.

    `pinned` maps a block field (`why`, `how`) to fragments it must contain.
    Returns the block.
    """
    before = observed_state(composed)

    code, out, err = run_integrate(
        composed,
        capsys,
        *extra,
        cwd=cwd,
        expected_trunk=expected_trunk,
        expected_tree=expected_tree,
    )

    block = single_refusal(code, out, err, what)
    assert_block_mentions(block, pinned or {})
    assert observed_state(composed) == before, "a refused run changed the repository"
    return block


def assert_trunk_at_lane_head(composed: ComposedLane, lane_head: str) -> None:
    """The trunk branch, and the primary checkout's HEAD, are at `lane_head`: a
    value read from git before the run, never the tool's own output."""
    repo_path = composed.repo.path
    assert git(repo_path, "rev-parse", TRUNK) == lane_head, "trunk is not at the lane"
    assert git(repo_path, "rev-parse", "HEAD") == lane_head, "the checkout did not move"


def assert_integrated(composed: ComposedLane, lane_head: str) -> None:
    """`lane_head` (read from git before the run) is the trunk branch's tip by
    fast-forward alone from the checked trunk; the gate file, worktree and branch
    are gone."""
    repo_path = composed.repo.path
    assert_trunk_at_lane_head(composed, lane_head)
    assert (
        git(repo_path, "rev-list", "--merges", f"{composed.expected_trunk}..{TRUNK}")
        == ""
    )
    assert is_ancestor(repo_path, composed.expected_trunk, lane_head)
    assert not (composed.path / GATE_RELATIVE_PATH).exists()
    assert not composed.path.exists(), "the lane worktree is still there"
    assert str(composed.path) not in git(repo_path, "worktree", "list", "--porcelain")
    assert not branch_exists_in(repo_path, composed.name), (
        "the lane branch is still there"
    )


def assert_lane_kept(composed: ComposedLane, *, gate_kept: bool = True) -> None:
    """A refused or interrupted `integrate` left the lane as it was: its
    worktree and its branch are still there, and so is its gate file unless the
    test deleted it (`gate_kept=False` then asserts nothing about it)."""
    assert composed.path.exists(), "the lane worktree is gone"
    assert branch_exists_in(composed.repo.path, composed.name), (
        "the lane branch is gone"
    )
    if gate_kept:
        assert (composed.path / GATE_RELATIVE_PATH).exists(), "the gate file is gone"


def report_lines(err: str, key: str) -> list[str]:
    """The values of the `key: value` lines of an apply-failure report."""
    prefix = f"{key}: "
    return [
        line.removeprefix(prefix)
        for line in err.splitlines()
        if line.startswith(prefix)
    ]


def commit_in(lane_path: Path, name: str = "sneaked.txt") -> str:
    """A new commit in the lane, for a race that lands one between two steps."""
    return commit_file(lane_path, name, f"{name}\n", f"adds {name}")
