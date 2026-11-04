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
- `resolve_trunk_commit`, `local_branch_of` and `lane_context`: which ref is
  the trunk, which local branch it maps to (None for a tag or SHA), and
  whether the working directory is a lane.
- `worktrees`, `branch_exists`, `branch_commit`, `branch_checked_out` and
  `primary_checkout`: the one worktree-listing parser and the questions built
  on it.
- `dirty_paths`: the one reader of `git status`; `origin_url`: the one reader
  of the `origin` remote.
- `head_commit`, `commit_tree`, `head_tree`, `is_ancestor`, `unmerged_paths`,
  `has_unmerged_entries` and `merge_in_progress`: one reader per fact about the
  history and merge state of a work tree.
- `local_files_a_merge_would_overwrite`: the ignored files a merge would clobber.
- `git_attempt`: a git call whose failure the caller handles itself.
- `git_message`: the one summary of a failed git call's output.
- `display_text`: how `render_block` shows an untrusted value (a path, git's
  stderr) without letting it forge or hide a line of the block.

Import whitelist (pinned by an AST test): the standard library and
`review_gate_hash`. Stdlib only otherwise. See ADR 0014 and ADR 0031.

This module never pushes, never skips git hooks and never forces anything.
"""

from __future__ import annotations

import functools
import os
import re
import shlex
import subprocess
import sys
import unicodedata
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

#: What a `git status -z` entry looks like: two status letters, a space, the
#: path. A rename or copy entry (`R`, `C`) is followed by a second entry that
#: names its origin.
PORCELAIN_PATH_OFFSET = 3
PORCELAIN_ORIGIN_FOLLOWS = frozenset("RC")

#: Separates the paths of every `-z` listing.
NUL = "\0"

#: Exists in the git directory only while a merge is unfinished.
MERGE_HEAD = "MERGE_HEAD"

NO_GIT_MESSAGE = "git gave no message"
#: The claim every restored-lane refusal ends with; made only after a verified restore.
RESTORED_CLAUSE = "the lane was restored to its state before compose"

GIT_DIR_NAME = ".git"
HEAD_REFS_PREFIX = "refs/heads/"
REMOTE_REFS_PREFIX = "refs/remotes/"
WORKTREE_LINE_PREFIX = "worktree "
BRANCH_LINE_PREFIX = "branch "

#: A ref the user may pass as `--trunk` and the form a lane name must take.
#: Validated before git sees it, so a value starting with `-` can never be read
#: as an option.
REF_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*")
LANE_NAME_PATTERN = REF_PATTERN

#: Subcommands that publish history. This tool never runs them.
FORBIDDEN_SUBCOMMANDS = frozenset({"push", "send-pack"})

#: This tool never writes git config, so it never runs the `config` subcommand.
CONFIG_SUBCOMMAND = "config"

#: Long options that skip a hook, a signature or a safety check.
FORBIDDEN_LONG_OPTIONS = frozenset(
    {
        "--no-verify",
        "--force",
        "--force-with-lease",
        "--force-if-includes",
        "--no-gpg-sign",
    }
)

#: Tokens that skip a hook, a signature or a safety check. Matched by exact
#: equality (or `--name=value`), never by substring. Other spellings of the
#: same options are caught by the abbreviation and short-cluster rules.
FORBIDDEN_TOKENS = FORBIDDEN_LONG_OPTIONS | {"-f"}

#: Git accepts an unambiguous prefix of a long option. A prefix of a forbidden
#: option at least this long (after `--`) is refused too.
MIN_ABBREVIATION_LENGTH = 3

#: A short-option cluster such as `-fd` or `-qf`.
SHORT_CLUSTER_PATTERN = re.compile(r"-[A-Za-z]+")
FORCE_SHORT_LETTER = "f"

#: `-n` is `--no-verify` for these subcommands.
NO_VERIFY_SHORT_SUBCOMMANDS = frozenset({"commit", "merge", "am", "rebase"})
NO_VERIFY_SHORT_LETTER = "n"

#: `-D`, `-M`, `-B` and `-C` force a delete, move, reset or copy here.
FORCE_UPPER_SUBCOMMANDS = frozenset({"branch", "worktree", "checkout", "switch"})
FORCE_UPPER_LETTERS = frozenset("DMBC")

#: The only global option lane_core's own calls may put before the subcommand.
CONFIG_OPTION = "-c"
ALLOWED_CONFIG_OVERRIDE = "diff.relative=false"
HOOKS_PATH_NAME = "core.hookspath"
HOOKS_PATH_PREFIX = f"{HOOKS_PATH_NAME}="

#: A refspec starting with this forces the update.
FORCE_REFSPEC_PREFIX = "+"

#: Environment variables that redirect or reconfigure git. They are not passed
#: on to the git calls this module makes.
GIT_ENV_DROPPED = frozenset(
    {
        "GIT_CONFIG_PARAMETERS",
        "GIT_CONFIG_COUNT",
        "GIT_EXEC_PATH",
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_COMMON_DIR",
        "GIT_INDEX_FILE",
        "GIT_NAMESPACE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_ATTR_SOURCE",
        "GIT_REPLACE_REF_BASE",
        "GIT_NO_REPLACE_OBJECTS",
    }
)
GIT_ENV_DROPPED_PREFIXES = ("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")

WHAT_GIT_COMMAND_FAILED = "git command failed"
WHAT_INVALID_LANE_NAME = "invalid lane name"
WHAT_BRANCH_EXISTS = "branch exists"
WHAT_PATH_EXISTS = "path exists"
WHAT_TRUNK_UNRESOLVED = "trunk ref cannot be resolved"
WHAT_NOT_A_GIT_REPOSITORY = "not a git repository"
WHAT_NOT_IN_A_LANE = "not in a lane"
WHAT_LANE_HAS_UNCOMMITTED_CHANGES = "lane has uncommitted changes"
WHAT_COMPOSE_CONFLICT = "compose conflict"
WHAT_COMPOSE_MERGE_FAILED = "compose merge failed"
WHAT_COMPOSE_RESTORE_UNVERIFIED = "compose restore unverified"

#: Unicode categories `display_text` escapes: control (C0, DEL, C1), line
#: separator (U+2028) and paragraph separator (U+2029).
DISPLAY_ESCAPED_CATEGORIES = frozenset({"Cc", "Zl", "Zp"})

#: Paths named in a dirty-tree refusal before it says "and N more".
MAX_LISTED_PATHS = 10


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


def _building(
    what: str,
) -> Callable[[Callable[..., Refusal]], Callable[..., Refusal]]:
    """Check that a constructor builds refusals of `what`; do not register it.

    For a second constructor of a `what` whose registered constructor is
    another one.
    """

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

        return checked

    return decorate


def _registered(
    what: str,
) -> Callable[[Callable[..., Refusal]], Callable[..., Refusal]]:
    """Register a constructor under `what`; it must build refusals of that `what`."""

    def decorate(constructor: Callable[..., Refusal]) -> Callable[..., Refusal]:
        checked = _building(what)(constructor)
        REFUSALS[what] = checked
        return checked

    return decorate


@_registered(WHAT_GIT_COMMAND_FAILED)
def git_command_failed_refusal(command: str, detail: str) -> Refusal:
    """`detail` is `git_message` of the failed call, or the guard's reason."""
    return Refusal(
        what=WHAT_GIT_COMMAND_FAILED,
        why=f"{detail.strip() or NO_GIT_MESSAGE} (command: {command})",
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
def trunk_unresolved_refusal(given: str | None, default: str | None = None) -> Refusal:
    """`given` is the `--trunk` value; `default` is the default trunk found.

    `given` wins. With neither, no --trunk was given and no default trunk exists.
    """
    if given is not None:
        why = f"trunk ref {given!r} does not resolve to a commit"
    elif default is not None:
        why = f"the default trunk {default!r} does not resolve to a commit"
    else:
        why = "no --trunk was given and no default trunk could be found"
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


@_registered(WHAT_NOT_IN_A_LANE)
def not_in_a_lane_refusal(cwd: Path, trunk_ref: str) -> Refusal:
    return Refusal(
        what=WHAT_NOT_IN_A_LANE,
        why=(
            f"{cwd} is not in a lane: a lane is a linked worktree on a branch "
            f"other than the trunk branch (trunk: {trunk_ref})"
        ),
        how="create one with lane.py open <name>, then run this command inside it",
    )


def listed_paths(paths: Sequence[str]) -> str:
    """The first `MAX_LISTED_PATHS` paths, then "and N more"."""
    extra = len(paths) - MAX_LISTED_PATHS
    more = f" and {extra} more" if extra > 0 else ""
    return f"{', '.join(paths[:MAX_LISTED_PATHS])}{more}"


@_registered(WHAT_LANE_HAS_UNCOMMITTED_CHANGES)
def lane_has_uncommitted_changes_refusal(paths: Sequence[str]) -> Refusal:
    return Refusal(
        what=WHAT_LANE_HAS_UNCOMMITTED_CHANGES,
        why=f"the lane has uncommitted changes: {listed_paths(paths)}",
        how=(
            "commit or stash the listed paths; if they are .claude/ files, "
            "add .claude/ to .gitignore (run /setup)"
        ),
    )


@_building(WHAT_LANE_HAS_UNCOMMITTED_CHANGES)
def unfinished_merge_refusal(paths: Sequence[str] = ()) -> Refusal:
    """A merge begun and not concluded; `paths` are the lane's uncommitted paths."""
    changes = f"; uncommitted paths: {listed_paths(paths)}" if paths else ""
    return Refusal(
        what=WHAT_LANE_HAS_UNCOMMITTED_CHANGES,
        why=f"the lane has a merge in progress ({MERGE_HEAD} exists){changes}",
        how=(
            "conclude the merge with git commit in the lane, or abort it with "
            "git merge --abort, then run this command again"
        ),
    )


def merge_step_failed(target_label: str) -> str:
    """The step that failed, for `compose_restore_unverified_refusal`."""
    return f"merging {target_label} failed"


def compose_failed_after(merged_labels: Sequence[str]) -> str:
    """The step that failed when no merge itself did: after the merges in `merged_labels`."""
    if not merged_labels:
        return "compose failed"
    return f"compose failed after merging {' and '.join(merged_labels)}"


def compose_conflict_cause(paths: Sequence[str]) -> str:
    return f"conflicts in {', '.join(paths)}"


def compose_merge_failed_cause(command: str, detail: str) -> str:
    """`detail` is git's own message; `command` is the merge that failed."""
    return f"{detail.strip() or NO_GIT_MESSAGE} (command: {command})"


@_registered(WHAT_COMPOSE_CONFLICT)
def compose_conflict_refusal(target_label: str, paths: Sequence[str]) -> Refusal:
    """Raised only after the lane was restored."""
    return Refusal(
        what=WHAT_COMPOSE_CONFLICT,
        why=(
            f"merging {target_label} into the lane {compose_conflict_cause(paths)}; "
            f"{RESTORED_CLAUSE}"
        ),
        how=(
            f"merge {target_label} by hand in the lane, resolve the conflicts, "
            "commit, then run compose again"
        ),
    )


@_registered(WHAT_COMPOSE_MERGE_FAILED)
def compose_merge_failed_refusal(
    target_label: str, command: str, detail: str
) -> Refusal:
    """Raised only after the lane was restored."""
    return Refusal(
        what=WHAT_COMPOSE_MERGE_FAILED,
        why=(
            f"git could not merge {target_label}: "
            f"{compose_merge_failed_cause(command, detail)}; "
            f"{RESTORED_CLAUSE}"
        ),
        how="resolve the cause named in why, then run compose again",
    )


@_registered(WHAT_COMPOSE_RESTORE_UNVERIFIED)
def compose_restore_unverified_refusal(
    failed_step: str, pre_compose_head: str, cause: str
) -> Refusal:
    """`failed_step` is `merge_step_failed` or `compose_failed_after`.

    `cause` is why it failed, without any claim about the lane's state.
    """
    return Refusal(
        what=WHAT_COMPOSE_RESTORE_UNVERIFIED,
        why=(
            f"{failed_step} ({cause}), and the lane could not be "
            f"verified as restored to its pre-compose commit {pre_compose_head}"
        ),
        how=(
            "save any edits you want to keep, then run "
            f"git reset --hard {pre_compose_head} in the lane yourself"
        ),
    )


def compose_restored_refusal(cause: Refusal) -> Refusal:
    """`cause` (a refusal raised after a merge moved HEAD), worded for a restored lane.

    Raised only after the lane was restored. It keeps the cause's `what` and
    `why`, and replaces its `how`, which was written for a command run alone.
    """
    return Refusal(
        what=cause.what,
        why=f"{cause.why}; {RESTORED_CLAUSE}",
        how="fix the cause named in why, then run compose again",
    )


def display_text(value: str) -> str:
    """`value` with every control or line-breaking character shown as an escape.

    A path or a git message is data from outside this tool. A raw newline, ESC
    or U+2028 in it could forge a `why:` line or rewrite the terminal. Newline
    becomes `\\x0a`, ESC `\\x1b`, U+2028 `\\u2028`. Nothing else changes.
    """
    return "".join(_visible(char) for char in value)


def _visible(char: str) -> str:
    if unicodedata.category(char) not in DISPLAY_ESCAPED_CATEGORIES:
        return char
    code = ord(char)
    return f"\\x{code:02x}" if code <= 0xFF else f"\\u{code:04x}"


def render_block(refusal: Refusal) -> str:
    """Plain-text block: `refused:`, `why:`, `how:` lines, no color.

    The one place a refusal is made safe to print: every field goes through
    `display_text`, so a constructor never has to.
    """
    what, why, how = (
        display_text(field) for field in (refusal.what, refusal.why, refusal.how)
    )
    return f"refused: {what}\nwhy: {why}\nhow: {how}\n"


def emit_refusals(refusals: Sequence[Refusal]) -> int:
    """Print every block to stderr, blank line between, and return exit 1."""
    sys.stderr.write("\n".join(render_block(item) for item in refusals))
    return EXIT_REFUSED


def _last_line(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def git_message(completed: subprocess.CompletedProcess[str]) -> str:
    """What git said about a failed call: all non-empty stderr lines joined with
    `; `, else the last stdout line (git prints some failures there)."""
    lines = [line.strip() for line in completed.stderr.splitlines() if line.strip()]
    return "; ".join(lines) or _last_line(completed.stdout)


def _failure(argv: Sequence[str], detail: str) -> RefusalError:
    return RefusalError(git_command_failed_refusal(shlex.join(argv), detail))


def _git_env() -> dict[str, str]:
    """The parent environment without the variables that reconfigure git.

    `GIT_CONFIG_GLOBAL` and `GIT_CONFIG_SYSTEM` are kept: they name a whole
    config file the operator chose, and the test fixtures point them at
    /dev/null. `review_gate_hash.default_base_ref` (delegated) still inherits
    the full environment.
    """
    return {
        key: value
        for key, value in os.environ.items()
        if key not in GIT_ENV_DROPPED and not key.startswith(GIT_ENV_DROPPED_PREFIXES)
    }


def _run(argv: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """The only `subprocess.run` call in this module. Never `shell=True`.

    Git never reads stdin, runs with `_git_env()` and is abandoned after
    `GIT_TIMEOUT_SECONDS`.
    """
    try:
        return subprocess.run(
            list(argv),
            cwd=str(cwd),
            env=_git_env(),
            capture_output=True,
            # A path git prints need not be UTF-8; it must not raise here.
            encoding="utf-8",
            errors="replace",
            check=False,
            stdin=subprocess.DEVNULL,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        detail = f"timed out after {GIT_TIMEOUT_SECONDS} s"
        raise _failure(argv, detail) from exc
    except OSError as exc:
        raise _failure(argv, str(exc)) from exc


def _global_options_reason(args: Sequence[str]) -> tuple[int | None, str | None]:
    """`(subcommand index, None)` or `(None, why the leading options are refused)`.

    An allowlist: the only option allowed before the subcommand is
    `-c diff.relative=false`. Anything else (`-C`, `--git-dir`, `--exec-path`,
    `--attr-source`, an unknown option) could redirect git, so it is refused.
    The location comes from `cwd`.
    """
    index = 0
    while index < len(args):
        token = args[index]
        if not token.startswith("-"):
            return index, None
        if token == CONFIG_OPTION:
            override = args[index + 1] if index + 1 < len(args) else ""
            if override != ALLOWED_CONFIG_OVERRIDE:
                return None, (
                    f"only {CONFIG_OPTION} {ALLOWED_CONFIG_OVERRIDE} is allowed, "
                    f"not {CONFIG_OPTION} {override}"
                )
            index += 2
            continue
        return None, f"global option {token} is never passed by lane.py"
    return None, "no git subcommand was given"


def _forbidden_long_option(name: str) -> str | None:
    """The forbidden long option `name` is, or abbreviates; else None."""
    if not name.startswith("--") or len(name) - 2 < MIN_ABBREVIATION_LENGTH:
        return None
    for option in sorted(FORBIDDEN_LONG_OPTIONS):
        if option.startswith(name):
            return option
    return None


def _cluster_reason(token: str, subcommand: str) -> str | None:
    if SHORT_CLUSTER_PATTERN.fullmatch(token) is None:
        return None
    letters = set(token[1:])
    if FORCE_SHORT_LETTER in letters:
        return f"option {token} contains -{FORCE_SHORT_LETTER} (force)"
    if subcommand in NO_VERIFY_SHORT_SUBCOMMANDS and NO_VERIFY_SHORT_LETTER in letters:
        return f"option {token} contains -{NO_VERIFY_SHORT_LETTER} (--no-verify)"
    if subcommand in FORCE_UPPER_SUBCOMMANDS and letters & FORCE_UPPER_LETTERS:
        return f"option {token} forces a branch or worktree change"
    return None


def _token_reason(token: str, subcommand: str) -> str | None:
    name = token.partition("=")[0]
    if name in FORBIDDEN_TOKENS:
        return f"option {name} is never passed by lane.py"
    abbreviated = _forbidden_long_option(name)
    if abbreviated is not None:
        return f"option {name} abbreviates {abbreviated}, never passed by lane.py"
    cluster = _cluster_reason(token, subcommand)
    if cluster is not None:
        return cluster
    lowered = token.lower()
    if lowered == HOOKS_PATH_NAME or lowered.startswith(HOOKS_PATH_PREFIX):
        return "core.hooksPath override is never passed by lane.py"
    if token.startswith(FORCE_REFSPEC_PREFIX):
        return f"forcing refspec {token} is never passed by lane.py"
    return None


def _guard_reason(args: Sequence[str]) -> str | None:
    """Why `args` must not run, or None. Checks tokens this code builds."""
    subcommand_index, reason = _global_options_reason(args)
    if subcommand_index is None:
        return reason
    subcommand = args[subcommand_index]
    if subcommand in FORBIDDEN_SUBCOMMANDS or subcommand == CONFIG_SUBCOMMAND:
        return f"subcommand {subcommand} is never run by lane.py"
    for token in args:
        reason = _token_reason(token, subcommand)
        if reason is not None:
            return reason
    return None


def _git(args: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run `git <args>` in `cwd`. A guard hit raises before anything runs."""
    reason = _guard_reason(args)
    if reason is not None:
        raise _failure(["git", *args], reason)
    return _run(["git", *args], cwd)


@dataclass(frozen=True)
class GitAttempt:
    """A git command that may fail without ending the caller's sequence.

    `detail` is git's non-empty stderr lines joined with `; `, falling back to
    the last stdout line (git prints some failures there). When the command
    could not run at all (the guard, a timeout), `ok` is False and `detail`
    is the reason.
    """

    ok: bool
    command: str
    detail: str
    stdout: str


def git_attempt(args: Sequence[str], cwd: Path) -> GitAttempt:
    """Run `git <args>` and report the outcome. Never raises `RefusalError`."""
    command = shlex.join(["git", *args])
    try:
        completed = _git(args, cwd)
    except RefusalError as exc:
        return GitAttempt(False, command, exc.refusal.why, "")
    return GitAttempt(
        completed.returncode == 0,
        command,
        git_message(completed),
        completed.stdout.strip(),
    )


def origin_url(cwd: Path) -> str:
    """The `origin` remote's URL, or "" when there is no `origin`."""
    attempt = git_attempt(["remote", "get-url", "origin"], cwd)
    return attempt.stdout if attempt.ok else ""


def git_ok(args: Sequence[str], cwd: Path) -> bool:
    return _git(args, cwd).returncode == 0


def _git_checked(args: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """`_git`, but a non-zero exit raises the `git command failed` refusal."""
    completed = _git(args, cwd)
    if completed.returncode != 0:
        raise _failure(["git", *args], git_message(completed))
    return completed


def git_text(args: Sequence[str], cwd: Path) -> str:
    """Stripped stdout of a git command that must succeed."""
    return _git_checked(args, cwd).stdout.strip()


def dirty_paths(cwd: Path) -> list[str]:
    """Every path `git status` reports: staged, unstaged and untracked.

    Read raw (`-z`), because `git_text` strips the leading space of the first
    status entry. A rename or copy entry is followed by its origin path, which
    is skipped. Ignored files are not reported.
    """
    args = ["status", "--porcelain=v1", "-z", "--untracked-files=all"]
    entries = _git_checked(args, cwd).stdout.split(NUL)
    paths: list[str] = []
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if len(entry) <= PORCELAIN_PATH_OFFSET:
            continue
        paths.append(entry[PORCELAIN_PATH_OFFSET:])
        if set(entry[:2]) & PORCELAIN_ORIGIN_FOLLOWS:
            index += 1
    return paths


def head_commit(cwd: Path) -> str:
    """The commit SHA `HEAD` names."""
    return git_text(["rev-parse", "--verify", "HEAD^{commit}"], cwd)


def commit_tree(commit: str, cwd: Path) -> str:
    """The tree SHA of `commit`, a SHA read from git."""
    return git_text(["rev-parse", "--verify", f"{commit}^{{tree}}"], cwd)


def head_tree(cwd: Path) -> str:
    """The tree of `HEAD`, read from the commit `head_commit` names."""
    return commit_tree(head_commit(cwd), cwd)


def is_ancestor(ancestor: str, descendant: str, cwd: Path) -> bool:
    """True when `ancestor` is `descendant` or in its history."""
    return git_ok(["merge-base", "--is-ancestor", ancestor, descendant], cwd)


def unmerged_paths(cwd: Path) -> list[str]:
    """Paths with unresolved merge conflicts."""
    listed = git_text(["diff", "--name-only", "--diff-filter=U", "-z"], cwd)
    return [path for path in listed.split(NUL) if path]


def has_unmerged_entries(cwd: Path) -> bool:
    """True when the index holds a conflicted entry (a stage above 0).

    Index-level (`ls-files -u` reads the index entries themselves), beside
    the diff-level `unmerged_paths` (`diff --diff-filter=U` compares the index
    with the work tree). `unmerged_paths` names the conflicted paths for a
    refusal; this answers only "is the index conflict-free?", for the restore
    check, and does not depend on how git renders a diff.
    """
    return bool(git_text(["ls-files", "-u"], cwd))


def local_files_a_merge_would_overwrite(commit: str, cwd: Path) -> list[str]:
    """Paths `commit` adds over HEAD that already exist in the work tree.

    Run in a lane with no uncommitted change, such a file can only be one git
    ignores. A merge writes the tracked file over it without a word: `ort`
    does not honor `--no-overwrite-ignore`, which guards only a fast-forward.
    """
    args = ["diff-tree", "-r", "--name-only", "--no-renames", "--diff-filter=A", "-z"]
    added = _git_checked([*args, "HEAD", commit], cwd).stdout.split(NUL)
    return [path for path in added if path and os.path.lexists(cwd / path)]


def merge_in_progress(cwd: Path) -> bool:
    """True while a merge is begun and not concluded or aborted."""
    return git_ok(["rev-parse", "--verify", "--quiet", MERGE_HEAD], cwd)


def branch_commit(name: str, cwd: Path) -> str | None:
    """The commit local branch `name` points at, or None when it does not exist."""
    return _commit_of(f"{HEAD_REFS_PREFIX}{name}", cwd)


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


def resolve_trunk_commit(arg: str | None, cwd: Path) -> tuple[str, str]:
    """`(trunk ref, commit SHA)`: `arg`, else the default trunk.

    A malformed value, no default trunk, or a ref that is not a commit all
    refuse, naming which of the three applies.
    """
    candidate = arg if arg is not None else default_base_ref(cwd)
    commit = None if candidate is None else _commit_of(candidate, cwd)
    if candidate is None or commit is None:
        default = candidate if arg is None else None
        raise RefusalError(trunk_unresolved_refusal(arg, default))
    return candidate, commit


def _remote_names(cwd: Path) -> list[str]:
    return git_text(["remote"], cwd).splitlines()


def _branch_of_full_ref(full: str) -> str | None:
    """`refs/heads/x` -> `x`; None when `full` is not a local-branch ref."""
    if full.startswith(HEAD_REFS_PREFIX):
        return full.removeprefix(HEAD_REFS_PREFIX)
    return None


def local_branch_of(ref: str, cwd: Path) -> str | None:
    """The local branch the trunk maps to: `origin/main` -> `main`, else None.

    None means the ref has no local-branch form: a tag, a SHA, or a value that
    does not match `REF_PATTERN` (which never reaches git). Git gives the full
    ref name. A remote name may contain `/`, so the remote is matched against
    `git remote`, longest name first.
    """
    if REF_PATTERN.fullmatch(ref) is None:
        return None
    completed = _git(["rev-parse", "--symbolic-full-name", ref], cwd)
    full = completed.stdout.strip() if completed.returncode == 0 else ""
    local = _branch_of_full_ref(full)
    if local is not None:
        return local
    if full.startswith(REMOTE_REFS_PREFIX):
        tracking = full.removeprefix(REMOTE_REFS_PREFIX)
        for remote in sorted(_remote_names(cwd), key=len, reverse=True):
            if tracking.startswith(f"{remote}/"):
                return tracking.removeprefix(f"{remote}/")
    return None


@dataclass(frozen=True)
class LaneContext:
    """`trunk_branch` is None when the trunk has no local-branch form."""

    lane_path: Path
    branch: str
    trunk_ref: str
    trunk_branch: str | None


def worktrees(cwd: Path) -> list[tuple[Path, str | None]]:
    """Every worktree git lists, primary first: `(path, checked-out branch | None)`.

    The branch is None for a detached HEAD and for a bare repository.
    """
    entries: list[tuple[Path, str | None]] = []
    path: Path | None = None
    branch: str | None = None
    for line in git_text(["worktree", "list", "--porcelain"], cwd).splitlines():
        if line.startswith(WORKTREE_LINE_PREFIX):
            if path is not None:
                entries.append((path, branch))
            path = Path(line.removeprefix(WORKTREE_LINE_PREFIX)).resolve()
            branch = None
        elif line.startswith(BRANCH_LINE_PREFIX) and path is not None:
            branch = _branch_of_full_ref(line.removeprefix(BRANCH_LINE_PREFIX))
    if path is not None:
        entries.append((path, branch))
    return entries


def branch_exists(name: str, cwd: Path) -> bool:
    """True when local branch `name` exists."""
    return git_ok(["show-ref", "--verify", "--quiet", f"{HEAD_REFS_PREFIX}{name}"], cwd)


def branch_checked_out(name: str, cwd: Path) -> bool:
    """True when a worktree has local branch `name` checked out."""
    return any(branch == name for _, branch in worktrees(cwd))


def _rev_parse_paths(flags: Sequence[str], cwd: Path) -> list[Path]:
    """Resolved paths for `git rev-parse <flags>`; git may print them relative."""
    lines = git_text(["rev-parse", *flags], cwd).splitlines()
    return [Path(cwd, line).resolve() for line in lines]


def _primary_of(common_dir: Path, cwd: Path) -> Path:
    """The primary checkout: git lists it first. Without a listing, guess from the name."""
    listed = worktrees(cwd)
    if listed:
        return listed[0][0]
    return common_dir.parent if common_dir.name == GIT_DIR_NAME else common_dir


def primary_checkout(cwd: Path) -> Path:
    """The primary checkout, even when `cwd` is inside a linked worktree."""
    (common,) = _rev_parse_paths(["--git-common-dir"], cwd)
    return _primary_of(common, cwd)


def lane_context(trunk_ref: str, cwd: Path) -> LaneContext | None:
    """The lane `cwd` is in, or None.

    A lane is a linked worktree on a branch that is not the trunk branch.
    Detached HEAD, the primary checkout and the trunk branch are not lanes. A
    trunk with no local branch (a tag or SHA) has no branch to match, so any
    branch in a linked worktree is a lane.
    """
    top, git_dir, common = _rev_parse_paths(
        ["--show-toplevel", "--git-dir", "--git-common-dir"], cwd
    )
    if git_dir == common:
        return None
    # The full ref: `--short` prints `heads/v1` when a tag `v1` also exists.
    head = _git(["symbolic-ref", "-q", "HEAD"], cwd).stdout.strip()
    branch = _branch_of_full_ref(head) or ""
    trunk_branch = local_branch_of(trunk_ref, cwd)
    if not branch or (trunk_branch is not None and branch == trunk_branch):
        return None
    return LaneContext(
        lane_path=top,
        branch=branch,
        trunk_ref=trunk_ref,
        trunk_branch=trunk_branch,
    )
