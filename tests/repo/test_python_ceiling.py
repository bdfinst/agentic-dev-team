"""`chk_python_ceiling` must not be neutralizable by ambient pytest env (#1876).

`chk_python_ceiling` (scripts/ci-local.sh) is this repo's designated backstop
for the class of regression tracked in #1832 — a stdlib contract change on the
newest supported interpreter that the floor gate's narrow slice cannot see.
It also runs in CI as its own `Python ceiling` job, but that job is listed
`exempt` (advisory-only) in `.github/required-status-checks.json` — a red run
does not block a GitHub-UI merge the way a required check would, so nothing
else catches a silently neutralized run of it.

`chk_python_floor` (pinned in `tests/repo/test_python_floor.py`) was hardened
against exactly this: an ambient `PYTEST_ADDOPTS=--collect-only` in a
contributor's shell — or a future CI `env:` block — makes pytest exit 0
having executed zero function bodies, because `PYTEST_ADDOPTS` is honoured
even when nothing on the command line asks for it. `chk_python_ceiling` was
added later and did not inherit that hardening: its `uv run --python
"$pyceil" ...` invocation passed the ambient environment straight through.
Proven live before the fix: with `PYTEST_ADDOPTS=--collect-only` exported,
`bash scripts/ci-local.sh --only=chk_python_ceiling` collected 8265 tests,
ran none of them, and still printed "All local CI checks passed." Proven live
after the fix: the identical invocation ran all 8265 (8222 passed, 43
skipped) in ~138s — the ambient var no longer reaches pytest.

This file pins the fix with the same parser shape `test_python_floor.py`
built for `chk_python_floor` — split the invocation at `-m pytest` and at any
`||`, walking backslash continuations the way the shell does — but declares
an equality pin over the pytest arguments (directories + `--ignore=` pair +
trailing flags) rather than `test_python_floor.py`'s allowlist-over-a-slice,
because `chk_python_ceiling` has no hand-maintained slice to diverge from: it
runs the full directory list, so an ordered equality check is the direct
translation of "no argument narrows what actually executes."
"""

from __future__ import annotations

import re

import pytest

from _ci_local_invocation import (
    PytestInvocation,
    check_body,
    check_registry,
    lines_after_invocation,
    pytest_invocation,
    synthetic_check,
    without_comments,
)
from _repo_root import REPO_ROOT

CI_LOCAL = REPO_ROOT / "scripts" / "ci-local.sh"

#: The bash function name every parser call below is scoped to.
CEILING_FN = "chk_python_ceiling"

#: Mirrors `test_python_floor.py`'s `FLOOR_DOTTED` — the single declaration
#: of the ceiling version, held equal to `PYTHON_CEILING`'s actual value in
#: scripts/ci-local.sh by `test_the_declared_ceiling_version_matches` below.
#: A silent `PYTHON_CEILING="3.12"` edit (dropping the gate onto roughly the
#: dev interpreter instead of the newest supported one) would otherwise pass
#: every other assertion in this file unnoticed — none of them inspect the
#: version, only the shape of the invocation around it.
CEILING_DOTTED = "3.14"

#: Mirrors `test_python_floor.py`'s `FLOOR_INVOCATION_PREFIX` — the same two
#: env vars cleared, immediately before the same `uv run --python` shape.
#: Declared as a tuple of literal tokens (not a substring check) for the same
#: reason the floor test gives: a comment mentioning the vars would satisfy an
#: `in body` check without the invocation itself clearing anything.
CEILING_INVOCATION_PREFIX = (
    "PYTEST_ADDOPTS=",
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD=",
    "uv",
    "run",
    "--python",
    '"$pyceil"',
    "--with",
    "'pytest>=7.0'",
    "--with",
    "'pytest-asyncio>=0.23'",
    "--with",
    "'pytest-xdist>=3.0'",
    "--with",
    "'jsonschema>=4.0'",
    "--with",
    "'PyYAML>=6.0'",
)

#: The full pytest argument list `chk_python_ceiling` must pass, in order.
#: Equality (not containment) is the point: `--ignore=plugins/dev-team/tests`
#: quietly dropping the largest directory, or a stray `-m 'not slow'`
#: narrowing what runs, both leave every *other* token in place — only an
#: ordered equality check over the whole list catches either.
CEILING_PYTEST_ARGS = (
    "plugins/dev-team/tests",
    "tests/repo",
    "tests/agents",
    "tests/commands",
    "tests/docs",
    "tests/knowledge",
    "tests/stack_aware",
    "tests/skills",
    "tests/scripts",
    "tests/hooks",
    "--ignore=tests/scripts/test_csharp_stryker_net_wrapper.py",
    "--ignore=tests/scripts/test_csharp_stryker_net_status_loop.py",
    "-q",
    "-n",
    "auto",
    "--dist",
    "loadgroup",
)


@pytest.fixture(scope="module")
def ci_local() -> str:
    return CI_LOCAL.read_text(encoding="utf-8")


def _ceiling_check_body(ci_local: str) -> str:
    """The text of `chk_python_ceiling`'s function body. Thin wrapper over
    the shared `check_body()` in `_ci_local_invocation`."""
    return check_body(ci_local, CEILING_FN)


def _ceiling_invocation(ci_local: str) -> PytestInvocation | None:
    """`chk_python_ceiling`'s pytest command, split at `-m pytest` and at any
    trailing `||`. Thin wrapper over the shared parser in
    `_ci_local_invocation` — see `pytest_invocation()` there for the full
    boundary rules (backslash continuation, the single-marker requirement,
    why comments are not stripped first, why the `||` tail is returned
    rather than dropped, and why `None` — not an empty-but-valid-shaped
    tuple — is the unparseable sentinel). Mirrors `test_python_floor.py`'s
    `_floor_invocation`, which wraps the same shared function for
    `chk_python_floor`."""
    return pytest_invocation(ci_local, CEILING_FN)


def _ceiling_invocation_prefix(ci_local: str) -> list[str]:
    """Everything the command says before `-m pytest`."""
    result = _ceiling_invocation(ci_local)
    return result.prefix if result is not None else []


def _ceiling_invocation_args(ci_local: str) -> list[str]:
    """Every argument pytest itself receives, after `-m pytest`."""
    result = _ceiling_invocation(ci_local)
    return result.args if result is not None else []


def _ceiling_invocation_tail(ci_local: str) -> list[str]:
    """Everything the command says after a `||` — the failure path, if any."""
    result = _ceiling_invocation(ci_local)
    return result.tail if result is not None else []


def _ceiling_lines_after_invocation(ci_local: str) -> list[str]:
    """Real code lines in the function body strictly after the (possibly
    multi-line) pytest invocation ends. Thin wrapper over the shared
    `lines_after_invocation()` in `_ci_local_invocation` — see that
    function's docstring for why a trailing statement matters and why a
    trailing comment is excluded from the result."""
    return lines_after_invocation(ci_local, CEILING_FN)


class TestTheCeilingCheckClearsAmbientPytestEnv:
    """The decisive property for #1876: this gate must not honour an ambient
    `PYTEST_ADDOPTS` / `PYTEST_DISABLE_PLUGIN_AUTOLOAD` the way a bare `uv run
    --python "$pyceil" -m pytest ...` would."""

    def test_ci_local_defines_the_ceiling_check(self, ci_local):
        assert "chk_python_ceiling()" in ci_local, (
            "scripts/ci-local.sh must define chk_python_ceiling — the single "
            "place the CI job and --only=chk_python_ceiling both call into"
        )

    def test_the_check_is_opt_in_not_default(self, ci_local):
        """Unlike chk_python_floor, chk_python_ceiling deliberately lives in
        OPTIONAL_CHECKS (own rationale in its comment block: it races
        chk_hook_units over hooks/careful-state.json, and duplicates the long
        pole locally). CI still runs it, via its own `Python ceiling` job,
        but that job is advisory-only (`exempt` in
        .github/required-status-checks.json — see the module docstring). If
        this check ever moves into the default CHECKS array, that is a real
        decision to make deliberately, not something that should slip in
        silently."""
        registry = check_registry(ci_local, "CHECKS")
        optional = check_registry(ci_local, "OPTIONAL_CHECKS")
        assert "chk_python_ceiling" not in registry
        assert "chk_python_ceiling" in optional

    def test_the_declared_ceiling_version_matches(self, ci_local):
        """`PYTHON_CEILING` (scripts/ci-local.sh) is the single declaration
        of which interpreter this gate resolves — `.github/workflows/
        plugin-tests.yml` states that convention explicitly ("The pinned
        version lives in one place ... so a runner-image bump cannot move it
        silently and raising it is a deliberate edit"). Nothing before this
        test inspected the version itself: `test_the_check_clears_
        pytest_addopts_and_plugin_autoload` and `test_the_check_passes_
        pytest_exactly_the_declared_arguments` both pin the literal token
        `"$pyceil"`, which stays byte-identical regardless of what
        `PYTHON_CEILING` resolves to. A silent `PYTHON_CEILING="3.12"` edit —
        dropping the gate onto roughly the dev interpreter instead of the
        newest supported one, reopening the #1832 blind spot this gate
        exists to close — would pass every other assertion in this file.
        Mirrors `test_python_floor.py::TestTheFloorIsDeclaredOnce::
        test_the_adr_states_the_same_floor`'s role for `FLOOR_DOTTED`, one
        layer down (a shell constant here, an ADR there)."""
        assert re.search(
            rf'(?m)^PYTHON_CEILING="{re.escape(CEILING_DOTTED)}"$', ci_local
        ), (
            f'scripts/ci-local.sh must declare PYTHON_CEILING="{CEILING_DOTTED}" '
            "exactly — if the ceiling is being deliberately raised, update "
            "CEILING_DOTTED here alongside it"
        )

    def test_the_ceiling_variable_is_assigned_exactly_once(self, ci_local):
        """The value, not just the token. A second `pyceil="$(command -v
        python3)"` anywhere in this function above the invocation would run
        every stage of this gate on the dev interpreter (~3.12) instead of
        the declared ceiling (3.14) with every test in this file still
        green — `local pyceil` (scripts/ci-local.sh:350) shadows any
        same-named variable outside the function, which is what makes this
        function-scoped window sufficient rather than needing to scan the
        whole file — because
        `CEILING_INVOCATION_PREFIX` only pins the literal `"$pyceil"` — not
        what that variable resolves to. Mirrors
        `test_python_floor.py::TestTheFloorIsProvenByRunningIt::
        test_the_check_uses_a_real_interpreter`'s identical pin for `py310`."""
        body = without_comments(_ceiling_check_body(ci_local))
        assert re.findall(r"\bpyceil=\S*", body) == [
            'pyceil="$(_resolve_python_ceiling)"'
        ], (
            "pyceil must be assigned exactly once, from "
            "_resolve_python_ceiling. Reassigning it silently runs the whole "
            "gate off-ceiling."
        )

    def test_the_check_clears_pytest_addopts_and_plugin_autoload(self, ci_local):
        """The fix for #1876. Before the fix, `chk_python_ceiling`'s
        invocation prefix was just `uv run --python "$pyceil" ...` — an
        ambient `PYTEST_ADDOPTS=--collect-only` passed straight through,
        making the gate collect every test and execute none of them while
        still exiting 0. `chk_python_floor` was hardened against exactly this
        already (`test_python_floor.py::TestTheFloorIsProvenByRunningIt::
        test_the_check_also_runs_a_real_test_slice_under_the_floor_interpreter`);
        this pins the identical clearing prefix on the ceiling gate.

        Token equality, not `in body`: a comment mentioning both variable
        names would satisfy a substring check without the invocation itself
        clearing anything — the same reasoning the floor test gives for its
        own `FLOOR_INVOCATION_PREFIX` pin."""
        assert _ceiling_invocation_prefix(ci_local) == list(
            CEILING_INVOCATION_PREFIX
        ), (
            "chk_python_ceiling's pytest command differs, before `-m pytest`, "
            "from CEILING_INVOCATION_PREFIX. pytest honours PYTEST_ADDOPTS and "
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD from the ambient environment unless "
            "the invocation explicitly clears them — this is what lets a "
            "contributor's `PYTEST_ADDOPTS=--collect-only` (or a future CI "
            "`env:` block) silently reduce this gate to running zero test "
            "bodies while still exiting 0."
        )

    def test_the_check_passes_pytest_exactly_the_declared_arguments(self, ci_local):
        """Equality over the whole argument list, not a denylist of known-bad
        flags: the point is to fail closed on a narrowing flag nobody has
        thought of yet. `--collect-only`, `-k`, `--deselect`, a stray `-m`,
        or a widened `--ignore=` set all leave the rest of the list
        byte-identical while reducing — or eliminating — what actually
        executes; only comparing the full ordered list against
        CEILING_PYTEST_ARGS catches every one of those the same way."""
        assert _ceiling_invocation_args(ci_local) == list(CEILING_PYTEST_ARGS), (
            "chk_python_ceiling's pytest arguments differ from "
            "CEILING_PYTEST_ARGS. If a new directory or --ignore= entry is "
            "genuinely wanted, add it to both — but check first that no "
            "change narrows what actually executes (--collect-only, -k, "
            "--deselect, or a second -m all do, silently)."
        )

    def test_the_check_does_not_suppress_its_own_verdict(self, ci_local):
        """Same shape as chk_python_floor's own pin
        (`test_the_check_does_not_suppress_its_own_verdict`): the pytest
        invocation's exit status IS this gate's verdict. Two independent
        ways to lose that silently — a `||` tail that discards or replaces
        it, and a statement appended after the invocation, which a bash
        function without `set -e` would return instead of pytest's own code.

        `chk_python_ceiling` has no `||` tail today and relies purely on
        being the function's last statement (positional verdict) — unlike
        `chk_python_floor`, which makes the verdict explicit with `|| return
        1` (pinned as `== ["return", "1"]` in
        `test_python_floor.py::test_the_check_does_not_suppress_its_own_verdict`).
        Both shapes are safe; what is never safe is a tail that CONDITIONS
        or REPLACES the exit status — `|| printf 'failed'`, `|| rc=$?` — so
        the allowlist here is the two known-safe shapes, not "empty only.\""""
        tail = _ceiling_invocation_tail(ci_local)
        assert tail in ([], ["return", "1"]), (
            f"chk_python_ceiling's pytest invocation has a `||` tail of "
            f"{tail}. `|| return 1` (explicit, matching chk_python_floor) or "
            "no tail at all (positional, since the invocation is the "
            "function's last statement) are the only shapes that don't "
            "condition or discard pytest's own exit status — anything else, "
            "such as `|| printf 'failed'` or `|| rc=$?`, does."
        )
        trailing = _ceiling_lines_after_invocation(ci_local)
        assert not trailing, (
            f"chk_python_ceiling runs {trailing} after its pytest invocation. "
            "A bash function returns its LAST command's status and "
            "ci-local.sh runs without `set -e`, so a trailing line silently "
            "becomes the gate's verdict. The invocation must be last."
        )

    def test_the_check_never_returns_0_except_by_reaching_the_end(self, ci_local):
        """An early `return 0` guard above the invocation would leave the
        gate green on a path that never runs the suite at all — a stronger
        and more direct failure mode than a discarded verdict below the
        invocation, which the previous test covers."""
        body = without_comments(_ceiling_check_body(ci_local))
        assert "return 0" not in body, (
            "chk_python_ceiling must never return 0 except by reaching the "
            "end of its pytest invocation; an early `return 0` makes the "
            "gate pass without running the suite"
        )
        found = [x for x in ("|| true", "|| :", "&& true", "set +e") if x in body]
        assert not found, f"chk_python_ceiling contains {found}, which discards the verdict"


class TestTheCeilingParserItself:
    """`_ceiling_invocation` is what every assertion above trusts, so its edge
    cases are pinned against synthetic input the same way
    `test_python_floor.py::TestTheSliceParserItself` pins its own parser."""

    @staticmethod
    def _synthetic(body: str) -> str:
        """Thin wrapper over the shared `synthetic_check()` in
        `_ci_local_invocation`."""
        return synthetic_check(CEILING_FN, body)

    def test_it_reads_the_prefix_and_args(self):
        body = self._synthetic(
            "  FOO= BAR= uv run --python \"$pyceil\" \\\n"
            "    -m pytest \\\n"
            "    tests/repo \\\n"
            "    -q"
        )
        prefix, args, tail = _ceiling_invocation(body)
        assert prefix == ["FOO=", "BAR=", "uv", "run", "--python", '"$pyceil"']
        assert args == ["tests/repo", "-q"]
        assert tail == []

    def test_a_second_marker_makes_the_parse_refuse_to_guess(self):
        body = self._synthetic(
            "  printf 'about to run -m pytest\\n'\n"
            "  uv run -m pytest tests/repo -q"
        )
        assert _ceiling_invocation(body) is None

    def test_a_reflow_onto_one_line_changes_nothing(self):
        body = self._synthetic(
            "  PYTEST_ADDOPTS= uv run --python \"$pyceil\" -m pytest tests/repo -q"
        )
        prefix, args, _ = _ceiling_invocation(body)
        assert prefix == ["PYTEST_ADDOPTS=", "uv", "run", "--python", '"$pyceil"']
        assert args == ["tests/repo", "-q"]

    def test_a_missing_marker_yields_nothing(self):
        body = self._synthetic("  uv run --python \"$pyceil\" tests/repo")
        assert _ceiling_invocation(body) is None

    def test_a_stray_m_flag_is_visible_in_args(self):
        """A second `-m` after the marker must land in the *args* list, where
        the equality pin against CEILING_PYTEST_ARGS rejects it — not get
        silently absorbed by the prefix/marker split."""
        body = self._synthetic(
            "  uv run -m pytest tests/repo -m not-slow -q"
        )
        _, args, _ = _ceiling_invocation(body)
        assert args == ["tests/repo", "-m", "not-slow", "-q"]

    def test_a_truncating_comment_is_surfaced_not_swallowed(self):
        """A `#` line carrying a trailing backslash does not comment itself
        out of a continued command — it ends the command there, so pytest
        would receive only the arguments above it. If `_ceiling_invocation`
        stripped comments before walking the continuation (the bug
        structure-review and test-smell-review both independently flagged),
        this would silently splice `tests/repo` and `tests/other` back
        together into one clean two-path args list. It must not: the
        comment's own tokens have to survive into `args`, where the
        CEILING_PYTEST_ARGS equality pin rejects them."""
        body = self._synthetic(
            "  uv run -m pytest \\\n"
            "    tests/repo \\\n"
            "    # note \\\n"
            "    tests/other \\\n"
            "    -q"
        )
        _, args, _ = _ceiling_invocation(body)
        assert args != ["tests/repo", "tests/other", "-q"], (
            "the truncating comment's tokens must survive into the argument "
            "list, where the CEILING_PYTEST_ARGS equality pin rejects them — "
            "asserting the exact tokenization would pin how the tokenizer "
            "spells a comment rather than the property that guards the gate"
        )

    def test_a_backslash_with_a_trailing_space_ends_the_command(self):
        """bash reads `\\` + space as an escaped space that ENDS the
        command, so every path below such a line is never passed to pytest.
        Mirrors `test_python_floor.py::TestTheSliceParserItself::
        test_a_backslash_with_a_trailing_space_ends_the_command` — that test
        asserts its own `_floor_slice_files` (which filters tokens through a
        test-path regex, so the line's own stray trailing token disappears
        from its result); `_ceiling_invocation` has no such per-token filter
        (ceiling's arguments are directories and flags, not a slice of
        individually-matchable file paths), so the assertion here is over
        the raw token list and keeps that stray token explicit rather than
        silently dropping it — the decisive property is still that
        `tests/other` and `-q`, below the escaped-space line, never appear."""
        body = self._synthetic(
            "  uv run -m pytest \\\n"
            "    tests/repo \\ \n"
            "    tests/other \\\n"
            "    -q"
        )
        _, args, _ = _ceiling_invocation(body)
        assert "tests/other" not in args and "-q" not in args
        assert args == ["tests/repo", "\\"]

    def test_the_failure_tail_is_returned_not_discarded(self):
        body = self._synthetic(
            "  uv run -m pytest tests/repo -q || printf 'failed'"
        )
        assert _ceiling_invocation(body)[2] == ["printf", "'failed'"]

    def test_a_trailing_statement_is_detected(self):
        body = self._synthetic(
            "  uv run -m pytest tests/repo -q\n"
            "  echo done"
        )
        assert _ceiling_lines_after_invocation(body) == ["echo done"]

    def test_no_trailing_statement_is_the_clean_case(self):
        body = self._synthetic("  uv run -m pytest tests/repo -q")
        assert _ceiling_lines_after_invocation(body) == []
