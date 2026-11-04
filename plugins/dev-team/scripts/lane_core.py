#!/usr/bin/env python3
"""lane_core -- refusal registry, git seam, trunk and lane detection for lane.py.

`lane.py` (open, compose, integrate) builds on this module. It owns the parts
every command shares:

- `Refusal` and `REFUSALS`: the what/why/how contract. A refusal is data; the
  renderer prints it as a `refused:`/`why:`/`how:` block on stderr.
- `_run` and `_git`: the only process seam. `_run` holds the single
  `subprocess.run` call; `_git` guards the argv before it reaches `_run`.
- `resolve_trunk`, `local_branch_of` and `lane_context`: which ref is trunk,
  which local branch it maps to, and whether the working directory is a lane.

Import whitelist (pinned by an AST test): the standard library and
`review_gate_hash`. Stdlib only otherwise. See ADR 0014 and ADR 0031.

This module never pushes, never skips git hooks and never forces anything.
"""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "hooks" / "lib"))

from review_gate_hash import default_base_ref

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_USAGE = 2

#: A ref the user may pass as `--trunk`. Validated before git sees it, so a
#: value starting with `-` can never be read as an option.
REF_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*")

#: Subcommands that publish history. This tool never runs them.
FORBIDDEN_SUBCOMMANDS = frozenset({"push", "send-pack"})

#: Tokens that skip a hook, a signature or a safety check. Matched by exact
#: equality, never by substring.
FORBIDDEN_TOKENS = frozenset(
    {"--no-verify", "--force", "--force-with-lease", "-f", "--no-gpg-sign"}
)

#: A `-c` override is allowed only with this value.
ALLOWED_CONFIG_OVERRIDE = "diff.relative=false"
HOOKS_PATH_PREFIX = "core.hookspath="

#: Global git options that take a separate value token.
_GLOBAL_OPTIONS_WITH_VALUE = frozenset({"-c", "-C"})

WHAT_GIT_COMMAND_FAILED = "git command failed"
WHAT_INVALID_LANE_NAME = "invalid lane name"
WHAT_BRANCH_EXISTS = "branch exists"
WHAT_PATH_EXISTS = "path exists"
WHAT_TRUNK_UNRESOLVED = "trunk ref cannot be resolved"
WHAT_NOT_A_GIT_REPOSITORY = "not a git repository"


@dataclass(frozen=True)
class Refusal:
    """What was refused, why, and how to fix it. Every field is non-empty."""

    what: str
    why: str
    how: str

    def __post_init__(self) -> None:
        for name in ("what", "why", "how"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Refusal.{name} must be a non-empty string")


class RefusalError(Exception):
    """Raised below the command layer; `lane.main` renders it as a block."""

    def __init__(self, refusal: Refusal) -> None:
        super().__init__(refusal.what)
        self.refusal = refusal


#: Stable `what` string -> constructor. Each step registers only the entries it
#: implements, so no commit carries an unimplemented refusal.
REFUSALS: dict[str, Callable[..., Refusal]] = {}


def _registered(
    what: str,
) -> Callable[[Callable[..., Refusal]], Callable[..., Refusal]]:
    def decorate(constructor: Callable[..., Refusal]) -> Callable[..., Refusal]:
        REFUSALS[what] = constructor
        return constructor

    return decorate


@_registered(WHAT_GIT_COMMAND_FAILED)
def git_command_failed(command: str, detail: str) -> Refusal:
    """`detail` is the last non-empty stderr line of git, or the guard's reason."""
    return Refusal(
        what=WHAT_GIT_COMMAND_FAILED,
        why=f"{detail.strip() or 'git gave no message'} (command: {command})",
        how=f"fix the cause named in why, then run the failed command again: {command}",
    )


@_registered(WHAT_INVALID_LANE_NAME)
def invalid_lane_name(name: str, reason: str) -> Refusal:
    return Refusal(
        what=WHAT_INVALID_LANE_NAME,
        why=f"lane name {name!r} is not usable: {reason}",
        how=(
            "use letters, digits, '.', '_', '-' and '/' only, starting with a "
            "letter or digit, in a form git accepts as a branch name"
        ),
    )


@_registered(WHAT_BRANCH_EXISTS)
def branch_exists(name: str) -> Refusal:
    return Refusal(
        what=WHAT_BRANCH_EXISTS,
        why=f"branch {name!r} already exists in this repository",
        how=(
            f"choose another name, or delete the old branch with "
            f"git branch -d {name} once it is merged"
        ),
    )


@_registered(WHAT_PATH_EXISTS)
def path_exists(path: Path) -> Refusal:
    return Refusal(
        what=WHAT_PATH_EXISTS,
        why=f"{path} already exists",
        how="pass --path with a directory that does not exist yet, or remove it first",
    )


@_registered(WHAT_TRUNK_UNRESOLVED)
def trunk_unresolved(ref: str | None) -> Refusal:
    why = (
        f"trunk ref {ref!r} does not resolve to a commit"
        if ref is not None
        else "no --trunk was given and no default branch could be found"
    )
    return Refusal(
        what=WHAT_TRUNK_UNRESOLVED,
        why=why,
        how="pass --trunk <ref> or run git remote set-head origin -a",
    )


@_registered(WHAT_NOT_A_GIT_REPOSITORY)
def not_a_git_repository(cwd: Path) -> Refusal:
    return Refusal(
        what=WHAT_NOT_A_GIT_REPOSITORY,
        why=f"{cwd} is not inside a git work tree",
        how="run lane.py from inside a git repository (cd into your repository first)",
    )


def render_block(refusal: Refusal) -> str:
    """Plain-text block: `refused:`, `why:`, `how:` lines, no color."""
    return f"refused: {refusal.what}\nwhy: {refusal.why}\nhow: {refusal.how}\n"


def emit_refusals(refusals: Sequence[Refusal]) -> int:
    """Print every block to stderr, blank line between, and return exit 1."""
    sys.stderr.write("\n".join(render_block(item) for item in refusals))
    return EXIT_REFUSED


def _last_line(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def _failure(argv: Sequence[str], detail: str) -> RefusalError:
    return RefusalError(git_command_failed(shlex.join(argv), detail))


def _run(argv: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """The only `subprocess.run` call in this module. Never `shell=True`."""
    try:
        return subprocess.run(
            list(argv),
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise _failure(argv, str(exc)) from exc


def _subcommand_index(args: Sequence[str]) -> int | None:
    """Index of the git subcommand, skipping global options and their values."""
    index = 0
    while index < len(args):
        token = args[index]
        if token in _GLOBAL_OPTIONS_WITH_VALUE:
            index += 2
            continue
        if not token.startswith("-"):
            return index
        index += 1
    return None


def _token_reason(token: str) -> str | None:
    if token in FORBIDDEN_TOKENS:
        return f"option {token} is never passed by lane.py"
    if token.lower().startswith(HOOKS_PATH_PREFIX):
        return "core.hooksPath override is never passed by lane.py"
    return None


def _config_override_reason(args: Sequence[str], sub_at: int | None) -> str | None:
    """Only `-c diff.relative=false` may appear among the global options."""
    global_end = len(args) if sub_at is None else sub_at
    for index in range(global_end):
        if args[index] != "-c":
            continue
        override = args[index + 1] if index + 1 < len(args) else ""
        if override != ALLOWED_CONFIG_OVERRIDE:
            return f"only -c {ALLOWED_CONFIG_OVERRIDE} is allowed, not -c {override}"
    return None


def _guard_reason(args: Sequence[str]) -> str | None:
    """Why `args` must not run, or None. Checks tokens this code builds."""
    sub_at = _subcommand_index(args)
    if sub_at is not None and args[sub_at] in FORBIDDEN_SUBCOMMANDS:
        return f"subcommand {args[sub_at]} is never run by lane.py"
    for token in args:
        reason = _token_reason(token)
        if reason is not None:
            return reason
    return _config_override_reason(args, sub_at)


def _git(args: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run `git <args>` in `cwd`. A guard hit raises before anything runs."""
    reason = _guard_reason(args)
    if reason is not None:
        raise _failure(["git", *args], reason)
    return _run(["git", *args], cwd)


def git_ok(args: Sequence[str], cwd: Path) -> bool:
    return _git(args, cwd).returncode == 0


def git_text(args: Sequence[str], cwd: Path) -> str:
    """Stripped stdout of a git command that must succeed."""
    done = _git(args, cwd)
    if done.returncode != 0:
        raise _failure(["git", *args], _last_line(done.stderr))
    return done.stdout.strip()


def require_work_tree(cwd: Path) -> None:
    """Refuse when `cwd` is not inside a git work tree."""
    done = _git(["rev-parse", "--is-inside-work-tree"], cwd)
    if done.returncode != 0 or done.stdout.strip() != "true":
        raise RefusalError(not_a_git_repository(cwd))


def resolve_trunk(arg: str | None, cwd: Path) -> str | None:
    """The trunk ref: `arg`, else the default base ref. None when unusable.

    A malformed value, no default, or a ref that is not a commit all give None;
    the command that called this turns None into its own refusal.
    """
    ref = arg if arg is not None else default_base_ref(cwd)
    if ref is None or REF_PATTERN.fullmatch(ref) is None:
        return None
    verify = [
        "rev-parse",
        "--verify",
        "--quiet",
        "--end-of-options",
        f"{ref}^{{commit}}",
    ]
    return ref if git_ok(verify, cwd) else None


def local_branch_of(ref: str, cwd: Path) -> str:
    """The local branch trunk maps to: `origin/main` -> `main`, else `ref`.

    A tag or SHA maps to itself; no such branch exists, which the
    fast-forward check refuses later.
    """
    if not git_ok(["show-ref", "--verify", "--quiet", f"refs/remotes/{ref}"], cwd):
        return ref
    return ref.split("/", 1)[1]


@dataclass(frozen=True)
class LaneContext:
    lane_path: Path
    branch: str
    trunk_ref: str
    trunk_branch: str
    primary_path: Path


def _primary_of(common_dir: Path) -> Path:
    return common_dir.parent if common_dir.name == ".git" else common_dir


def primary_checkout(cwd: Path) -> Path:
    """The primary checkout, even when `cwd` is inside a linked worktree."""
    common = git_text(["rev-parse", "--path-format=absolute", "--git-common-dir"], cwd)
    return _primary_of(Path(common))


def lane_context(trunk_ref: str, cwd: Path) -> LaneContext | None:
    """The lane `cwd` is in, or None.

    A lane is a linked worktree on a branch that is not the trunk branch.
    Detached HEAD, the primary checkout and the trunk branch are not lanes.
    """
    top, git_dir, common = git_text(
        [
            "rev-parse",
            "--path-format=absolute",
            "--show-toplevel",
            "--git-dir",
            "--git-common-dir",
        ],
        cwd,
    ).splitlines()
    if Path(git_dir) == Path(common):
        return None
    branch = _git(["symbolic-ref", "--short", "-q", "HEAD"], cwd).stdout.strip()
    trunk_branch = local_branch_of(trunk_ref, cwd)
    if not branch or branch == trunk_branch:
        return None
    return LaneContext(
        lane_path=Path(top),
        branch=branch,
        trunk_ref=trunk_ref,
        trunk_branch=trunk_branch,
        primary_path=_primary_of(Path(common)),
    )
