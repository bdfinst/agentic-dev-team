#!/usr/bin/env python3
"""lane_core -- refusal registry, git seam, trunk and lane detection for lane.py.

`lane.py` (open, compose, integrate) builds on this module. It owns the parts
every command shares:

- `Refusal` and `REFUSALS`: the what/why/how contract. A refusal is data; the
  renderer prints it as a `refused:`/`why:`/`how:` block on stderr.
- `_run` and `_git`: the only seam for the process calls this module makes
  itself. `_run` holds the single `subprocess.run` call; `_git` guards the
  argv before it reaches `_run`. `review_gate_hash.default_base_ref` is the one
  delegated exception: it runs its own `git` calls, without this module's
  timeout, and a runtime spy in the tests covers it.
- `resolve_trunk`, `local_branch_of` and `lane_context`: which ref is trunk,
  which local branch it maps to, and whether the working directory is a lane.

Import whitelist (pinned by an AST test): the standard library and
`review_gate_hash`. Stdlib only otherwise. See ADR 0014 and ADR 0031.

This module never pushes, never skips git hooks and never forces anything.
"""

from __future__ import annotations

import functools
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

#: Seconds before a git call is abandoned. Nothing here waits on a person.
GIT_TIMEOUT_SECONDS = 120

GIT_DIR_NAME = ".git"
HEAD_REFS_PREFIX = "refs/heads/"
REMOTE_REFS_PREFIX = "refs/remotes/"
WORKTREE_LINE_PREFIX = "worktree "

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
CONFIG_OPTION = "-c"
CONFIG_ENV_OPTION = "--config-env"
ALLOWED_CONFIG_OVERRIDE = "diff.relative=false"
HOOKS_PATH_PREFIX = "core.hookspath="

#: A refspec starting with this forces the update.
FORCE_REFSPEC_PREFIX = "+"

#: Global git options that take a separate value token.
_GLOBAL_OPTIONS_WITH_VALUE = frozenset(
    {
        CONFIG_OPTION,
        "-C",
        "--git-dir",
        "--work-tree",
        "--namespace",
        "--super-prefix",
        CONFIG_ENV_OPTION,
    }
)

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
    """Register a constructor under `what`; it must build refusals of that `what`."""

    def decorate(constructor: Callable[..., Refusal]) -> Callable[..., Refusal]:
        @functools.wraps(constructor)
        def checked(*args: object, **kwargs: object) -> Refusal:
            refusal = constructor(*args, **kwargs)
            if refusal.what != what:
                raise ValueError(
                    f"{constructor.__name__} is registered as {what!r} "
                    f"but built {refusal.what!r}"
                )
            return refusal

        REFUSALS[what] = checked
        return checked

    return decorate


@_registered(WHAT_GIT_COMMAND_FAILED)
def git_command_failed_refusal(command: str, detail: str) -> Refusal:
    """`detail` is the last non-empty stderr line of git, or the guard's reason."""
    return Refusal(
        what=WHAT_GIT_COMMAND_FAILED,
        why=f"{detail.strip() or 'git gave no message'} (command: {command})",
        how=f"fix the cause named in why, then run the failed command again: {command}",
    )


@_registered(WHAT_INVALID_LANE_NAME)
def invalid_lane_name_refusal(name: str, reason: str) -> Refusal:
    return Refusal(
        what=WHAT_INVALID_LANE_NAME,
        why=f"lane name {name!r} is not usable: {reason}",
        how=(
            "use letters, digits, '.', '_', '-' and '/' only, starting with a "
            "letter or digit, in a form git accepts as a branch name"
        ),
    )


@_registered(WHAT_BRANCH_EXISTS)
def branch_exists_refusal(name: str) -> Refusal:
    return Refusal(
        what=WHAT_BRANCH_EXISTS,
        why=f"branch {name!r} already exists in this repository",
        how=(
            f"choose another name, or delete the old branch with "
            f"git branch -d {name} once it is merged"
        ),
    )


@_registered(WHAT_PATH_EXISTS)
def path_exists_refusal(path: Path) -> Refusal:
    return Refusal(
        what=WHAT_PATH_EXISTS,
        why=f"{path} already exists",
        how="pass --path with a directory that does not exist yet, or remove it first",
    )


@_registered(WHAT_TRUNK_UNRESOLVED)
def trunk_unresolved_refusal(ref: str | None, is_default: bool = False) -> Refusal:
    """`ref` is the ref that failed, or None when no default branch was found."""
    if ref is None:
        why = "no --trunk was given and no default branch could be found"
    elif is_default:
        why = f"the default trunk ref {ref!r} does not resolve to a commit"
    else:
        why = f"trunk ref {ref!r} does not resolve to a commit"
    return Refusal(
        what=WHAT_TRUNK_UNRESOLVED,
        why=why,
        how="pass --trunk <ref> or run git remote set-head origin -a",
    )


@_registered(WHAT_NOT_A_GIT_REPOSITORY)
def not_a_git_repository_refusal(cwd: Path) -> Refusal:
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
    return RefusalError(git_command_failed_refusal(shlex.join(argv), detail))


def _run(argv: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """The only `subprocess.run` call in this module. Never `shell=True`.

    Git never reads stdin and is abandoned after `GIT_TIMEOUT_SECONDS`.
    """
    try:
        return subprocess.run(
            list(argv),
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
            stdin=subprocess.DEVNULL,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        detail = f"timed out after {GIT_TIMEOUT_SECONDS} s"
        raise _failure(argv, detail) from exc
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
    if token.startswith(FORCE_REFSPEC_PREFIX):
        return f"forcing refspec {token} is never passed by lane.py"
    return None


def _config_override_reason(
    args: Sequence[str], subcommand_index: int | None
) -> str | None:
    """Only `-c diff.relative=false` may appear among the global options."""
    global_end = len(args) if subcommand_index is None else subcommand_index
    for index in range(global_end):
        if args[index].startswith(CONFIG_ENV_OPTION):
            return f"{CONFIG_ENV_OPTION} is never passed by lane.py"
        if args[index] != CONFIG_OPTION:
            continue
        override = args[index + 1] if index + 1 < len(args) else ""
        if override != ALLOWED_CONFIG_OVERRIDE:
            return (
                f"only {CONFIG_OPTION} {ALLOWED_CONFIG_OVERRIDE} is allowed, "
                f"not {CONFIG_OPTION} {override}"
            )
    return None


def _guard_reason(args: Sequence[str]) -> str | None:
    """Why `args` must not run, or None. Checks tokens this code builds."""
    subcommand_index = _subcommand_index(args)
    if subcommand_index is not None and args[subcommand_index] in FORBIDDEN_SUBCOMMANDS:
        return f"subcommand {args[subcommand_index]} is never run by lane.py"
    for token in args:
        reason = _token_reason(token)
        if reason is not None:
            return reason
    return _config_override_reason(args, subcommand_index)


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
    completed = _git(args, cwd)
    if completed.returncode != 0:
        raise _failure(["git", *args], _last_line(completed.stderr))
    return completed.stdout.strip()


def require_work_tree(cwd: Path) -> None:
    """Refuse when `cwd` is not inside a git work tree."""
    completed = _git(["rev-parse", "--is-inside-work-tree"], cwd)
    if completed.returncode != 0 or completed.stdout.strip() != "true":
        raise RefusalError(not_a_git_repository_refusal(cwd))


def _commit_of(ref: str, cwd: Path) -> str | None:
    """The commit SHA `ref` names, or None. A malformed `ref` never reaches git."""
    if REF_PATTERN.fullmatch(ref) is None:
        return None
    completed = _git(["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], cwd)
    return completed.stdout.strip() if completed.returncode == 0 else None


def _trunk_candidate(arg: str | None, cwd: Path) -> str | None:
    return arg if arg is not None else default_base_ref(cwd)


def resolve_trunk(arg: str | None, cwd: Path) -> str | None:
    """The trunk ref: `arg`, else the default base ref. None when unusable.

    A malformed value, no default, or a ref that is not a commit all give None.
    `resolve_trunk_commit` is the variant that refuses and names the ref.
    """
    candidate = _trunk_candidate(arg, cwd)
    if candidate is None or _commit_of(candidate, cwd) is None:
        return None
    return candidate


def resolve_trunk_commit(arg: str | None, cwd: Path) -> tuple[str, str]:
    """`(trunk ref, commit SHA)`, or a refusal that names the ref that failed."""
    candidate = _trunk_candidate(arg, cwd)
    commit = None if candidate is None else _commit_of(candidate, cwd)
    if candidate is None or commit is None:
        raise RefusalError(trunk_unresolved_refusal(candidate, is_default=arg is None))
    return candidate, commit


def _remote_names(cwd: Path) -> list[str]:
    return git_text(["remote"], cwd).splitlines()


def local_branch_of(ref: str, cwd: Path) -> str:
    """The local branch trunk maps to: `origin/main` -> `main`, else `ref`.

    `ref` must already match `REF_PATTERN`. Git gives the full ref name; a tag
    or SHA has no branch form and maps to itself, which the fast-forward check
    refuses later. A remote name may contain `/`, so the remote is matched
    against `git remote`, longest name first.
    """
    completed = _git(["rev-parse", "--symbolic-full-name", ref], cwd)
    full = completed.stdout.strip() if completed.returncode == 0 else ""
    if full.startswith(HEAD_REFS_PREFIX):
        return full.removeprefix(HEAD_REFS_PREFIX)
    if full.startswith(REMOTE_REFS_PREFIX):
        tracking = full.removeprefix(REMOTE_REFS_PREFIX)
        for remote in sorted(_remote_names(cwd), key=len, reverse=True):
            if tracking.startswith(f"{remote}/"):
                return tracking.removeprefix(f"{remote}/")
    return ref


@dataclass(frozen=True)
class LaneContext:
    lane_path: Path
    branch: str
    trunk_ref: str
    trunk_branch: str
    primary_path: Path


def _rev_parse_paths(flags: Sequence[str], cwd: Path) -> list[Path]:
    """Resolved paths for `git rev-parse <flags>`; git may print them relative."""
    lines = git_text(["rev-parse", *flags], cwd).splitlines()
    return [Path(cwd, line).resolve() for line in lines]


def _primary_of(common_dir: Path, cwd: Path) -> Path:
    """The main worktree: git lists it first. Without a listing, guess from the name."""
    for line in git_text(["worktree", "list", "--porcelain"], cwd).splitlines():
        if line.startswith(WORKTREE_LINE_PREFIX):
            return Path(line.removeprefix(WORKTREE_LINE_PREFIX)).resolve()
    return common_dir.parent if common_dir.name == GIT_DIR_NAME else common_dir


def primary_checkout(cwd: Path) -> Path:
    """The primary checkout, even when `cwd` is inside a linked worktree."""
    (common,) = _rev_parse_paths(["--git-common-dir"], cwd)
    return _primary_of(common, cwd)


def lane_context(trunk_ref: str, cwd: Path) -> LaneContext | None:
    """The lane `cwd` is in, or None.

    A lane is a linked worktree on a branch that is not the trunk branch.
    Detached HEAD, the primary checkout and the trunk branch are not lanes.
    """
    top, git_dir, common = _rev_parse_paths(
        ["--show-toplevel", "--git-dir", "--git-common-dir"], cwd
    )
    if git_dir == common:
        return None
    branch = _git(["symbolic-ref", "--short", "-q", "HEAD"], cwd).stdout.strip()
    trunk_branch = local_branch_of(trunk_ref, cwd)
    if not branch or branch == trunk_branch:
        return None
    return LaneContext(
        lane_path=top,
        branch=branch,
        trunk_ref=trunk_ref,
        trunk_branch=trunk_branch,
        primary_path=_primary_of(common, cwd),
    )
