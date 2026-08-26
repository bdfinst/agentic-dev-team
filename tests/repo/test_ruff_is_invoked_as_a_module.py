"""Every ruff invocation in this repo runs the PINNED module, never the bare
PATH binary (#1676, #2027).

#1676 established the rule and `scripts/ci-local.sh` states it at the call
site: both a PATH `ruff` and the `requirements-dev.txt`-pinned one can be
present at once and disagree on real findings. `python3 -m ruff` resolves to
the version this repo pins, so the gate means the same thing locally, in CI,
and on every contributor machine.

#2027 is the recurrence that motivated this file. `package.json`'s
`lint-staged` config was the one invocation site that never got the fix, so
the protection held for `ci-local.sh` and CI and was absent from the path that
runs on **every single commit**. Observed in this repo's own container, which
carried both:

    python3 -m ruff (pinned, what CI runs)  0.16.1  -> clean
    ruff from PATH (what lint-staged ran)   0.15.8  -> E402, 1 error

Note the direction is INVERTED from #1676's case: there the pinned version was
stricter, here the PATH version is. That is the point — two versions disagree
per-rule, so neither "newer is stricter" nor "older is stricter" is a safe
assumption. The only stable property is *which version this repo pins*.

The quiet failure runs the other way too: a contributor whose PATH ruff is
more permissive gets a clean pre-commit hook and a red `Lint (ruff + eslint)`
in CI, having done nothing wrong.

Per the repo CLAUDE.md ratchet — a mechanically-checkable finding reported a
second time becomes a check — this is that check.
"""

from __future__ import annotations

import json
import re

from _repo_root import REPO_ROOT

#: A bare-binary invocation: `ruff` at a command position, not preceded by
#: `-m ` (the module form) and not part of a longer word (`ruff.toml`,
#: `python3 -m ruff`).
_BARE_RUFF = re.compile(r"(?<!-m )(?<![\w./-])ruff(?![\w.-])")


def _shell_commands_from_package_json() -> dict[str, str]:
    """Every shell command package.json can run: scripts + lint-staged globs."""
    payload = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))
    commands: dict[str, str] = {}
    for name, command in (payload.get("scripts") or {}).items():
        commands[f"scripts.{name}"] = command
    lint_staged = payload.get("lint-staged") or {}
    for glob, command in lint_staged.items():
        # lint-staged values may be a string or a list of strings.
        entries = command if isinstance(command, list) else [command]
        for index, entry in enumerate(entries):
            commands[f"lint-staged[{glob}][{index}]"] = entry
    return commands


def test_package_json_never_invokes_the_bare_ruff_binary():
    """#2027: lint-staged runs on every commit — the one path where a stray
    PATH ruff does the most damage."""
    offenders = {
        where: command
        for where, command in _shell_commands_from_package_json().items()
        if _BARE_RUFF.search(command)
    }
    assert not offenders, (
        "package.json invokes the bare `ruff` binary from PATH, which may be a "
        "different version than requirements-dev.txt pins (#1676/#2027). Use "
        f"`python3 -m ruff` instead. Offending entries: {offenders}"
    )


def test_lint_staged_lints_python_through_the_pinned_module():
    """Positive assertion, so deleting the Python entry cannot pass this file
    by making the negative check above vacuous."""
    payload = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))
    lint_staged = payload.get("lint-staged") or {}
    python_entries = [
        command for glob, command in lint_staged.items() if glob.endswith(".py")
    ]
    assert python_entries, "lint-staged no longer lints *.py at all"
    flat = " ".join(
        " ".join(entry) if isinstance(entry, list) else entry for entry in python_entries
    )
    assert "-m ruff" in flat, f"lint-staged must run `python3 -m ruff`, got: {flat}"


def test_ci_local_invokes_ruff_as_a_module():
    """The rule's original site (#1676) — pinned here so the two cannot drift
    apart again, which is precisely how #2027 happened."""
    text = (REPO_ROOT / "scripts" / "ci-local.sh").read_text(encoding="utf-8")
    chk = re.search(r"chk_ruff\(\)\s*\{([^}]*)\}", text)
    assert chk is not None, "chk_ruff() not found in scripts/ci-local.sh"
    body = chk.group(1)
    assert "-m ruff" in body, f"chk_ruff must invoke `python3 -m ruff`, got: {body}"
    assert not _BARE_RUFF.search(body), f"chk_ruff invokes a bare ruff: {body}"


def test_the_bare_ruff_pattern_actually_matches_a_bare_invocation():
    """A gate that cannot fail is worse than no gate — pin the regex itself."""
    assert _BARE_RUFF.search("ruff check --fix")
    assert _BARE_RUFF.search("npx foo && ruff check")
    assert not _BARE_RUFF.search("python3 -m ruff check --fix")
    assert not _BARE_RUFF.search("cat ruff.toml")
    assert not _BARE_RUFF.search("path/to/ruff-config")
