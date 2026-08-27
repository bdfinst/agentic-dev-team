"""The shipped Python floor is declared once and proven by running it (#1623).

ADR 0014 originally put shipped plugin code on **Python 3.8, stdlib only**,
because 3.8 is what Ubuntu 20.04 LTS, Homebrew, and python.org still handed a
user who installed this plugin at the time. Nothing enforced that, and it
drifted: five shipped scripts raised `TypeError: 'type' object is not
subscriptable` at import time on a real 3.8.20, eight more called
`str.removeprefix` (3.9+), and `cost_meter.py` used PEP 584's `dict | dict`
merge (3.9+).

ADR 0031 later raised the floor to **Python 3.10** once 3.8's own
justification had expired (3.9 also went EOL; Ubuntu 20.04 left standard
support) — see issue #1679. The mechanism this file pins is unchanged by
that move; only the version and the ADR of record are.

## Why this file pins a mechanism and not a list of APIs

The first attempt at this gate was a static checker with a hand-maintained
denylist of post-3.8 stdlib APIs. It found the `removeprefix` calls and the
type aliases — and reported the tree **clean** while `cost_meter.py`'s
`dict | dict` sat in it, because nobody had thought to add PEP 584 to the
list. Running the suite on a real 3.8 found that in nine failing tests.

A denylist is an inference about what 3.8 rejects. The interpreter *is* what
3.8 rejects. Only one of those two can be wrong, and the wrong one still
prints "clean" — which is worse than no gate, because it reads as a guarantee.
The same lesson is already written into `package.json`: `engines.node` sat at
`>=24` while this project's own containers ran Node 22, so `npm ci` failed,
`node_modules` never installed, husky went inert, and `ci-local.sh` skipped
eslint *while still reporting success*.

So the floor is declared in exactly one machine-readable place —
`ruff.toml`'s `[per-file-target-version]` — and proven by `chk_python_floor`
in `scripts/ci-local.sh`, which resolves a real floor interpreter and makes it
byte-compile and import every shipped module. That check runs in the default
gate, so the pre-push hook enforces it on every push — and, since #1635, a
dedicated `python-floor` job in `.github/workflows/plugin-tests.yml` also
runs it on every PR, so a push that bypasses local hooks (`--no-verify`, a
hookless cloud session) is still caught by CI. That job's name is a required
status check on `main`, so a red run blocks a GitHub-UI merge too.

Byte-compiling and importing still has a blind spot of its own, closed in
#1650: neither one executes a function *body*, so a runtime-only API used
only inside a function (`asyncio.to_thread` in `orchestrator.py`, 3.9+) stays
invisible to both regardless of which version the floor is pinned to.
`chk_python_floor` now also actually runs, under the resolved floor
interpreter, the test slice declared as `FLOOR_TEST_SLICE` below (each entry's
per-module justification lives in `chk_python_floor`'s own comment) — not the
plugin's entire
suite, which would double this gate's wall-clock re-running everything under
a second interpreter, but enough real execution to catch what compiling and
importing alone cannot.

The slice is a hand-maintained list, so it can go stale the moment a shipped
module lands without joining it — which is what happened to the
coverage-discovery modules (#1826). `coverage_config.parse_iso8601` holds an
explicit 3.10-vs-3.11 shim (`datetime.fromisoformat` rejects a trailing `Z`
before 3.11); compile and import both passed on 3.10 whether or not that shim
was correct, and a 3.11-only API injected into its body was measured passing
all three of byte-compile, import-probe, and the pre-#1826 six-file slice.
`FLOOR_TEST_SLICE` below is the one declaration of that list, held equal to
`chk_python_floor`'s actual pytest arguments in both directions — so a slice
that shrinks and a slice that grows past its declaration both fail a named
test. What is still convention rather than gate: nothing detects a NEW shipped
module that never joins the slice at all, which is the shape #1826 itself was
— tracked as #1829, which proposes accounting for every shipped module with a
test against the slice, with reasoned exclusions rather than silent absence.

What follows pins those parts to each other. It deliberately contains no
opinion about which APIs are too new; that question belongs to the
interpreter.

See the "deterministic tools over inference" rule in the repo CLAUDE.md.
"""

from __future__ import annotations

import re
from pathlib import Path

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

#: The bash function name every parser call below is scoped to.
FLOOR_FN = "chk_python_floor"

RUFF_CONFIG = REPO_ROOT / "ruff.toml"
# The current floor version's ADR of record (ADR 0031), not ADR 0014 where the
# floor was originally set — 0014's own version stanza is superseded by 0031,
# and prose that disagrees with the tooling is exactly the drift this file
# exists to catch.
ADR = REPO_ROOT / "docs" / "adr" / "0031-raise-shipped-python-floor-to-3-10.md"
CI_LOCAL = REPO_ROOT / "scripts" / "ci-local.sh"
IMPORT_PROBE = REPO_ROOT / "scripts" / "import_probe_shipped.py"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "plugin-tests.yml"

#: The floor every part below must agree on, in each part's own notation.
FLOOR_RUFF = "py310"
FLOOR_DOTTED = "3.10"

#: The floor test slice `chk_python_floor` must hand to pytest. One declaration
#: for every test that pins it — the alternative was this list written out once
#: per test, the same hand-maintained duplication that let the coverage-discovery
#: modules go missing in the first place (#1826).
#:
#: Add an entry when a shipped `plugins/dev-team/scripts/*.py` module's function
#: BODIES carry floor-sensitive runtime behavior — a version shim, or a stdlib
#: API that only resolves above the floor. That is the criterion, and it is here
#: rather than in `chk_python_floor` because this is the file a maintainer opens
#: when adding a module. Compile and import cannot see inside a body, which is
#: the whole reason this slice exists.
#:
#: Two roots deliberately: repo-root `tests/scripts/` for the shipped agent
#: scripts, `plugins/dev-team/tests/scripts/` for the coverage-discovery modules.
FLOOR_TEST_SLICE = (
    "tests/scripts/test_codebase_recon.py",
    "tests/scripts/test_orchestrator.py",
    "tests/scripts/test_orchestrator_cli.py",
    "tests/scripts/test_progress_guardian.py",
    "tests/scripts/test_token_efficiency_review_script.py",
    "tests/scripts/test_claude_setup_review.py",
    "tests/scripts/test_extract_session_report.py",
    "plugins/dev-team/tests/scripts/test_coverage_config.py",
    "plugins/dev-team/tests/scripts/test_coverage_discovery_dotnet.py",
    "plugins/dev-team/tests/scripts/test_coverage_discovery_js.py",
    "plugins/dev-team/tests/scripts/test_autoship_reclaim.py",
)

#: Issue #1829: `FLOOR_TEST_SLICE` above is hand-maintained, so a new shipped,
#: tested module can land and never join it — the exact #1826 shape,
#: recurring. `TestTheFloorSliceAccountsForEveryShippedScript` below enumerates
#: every `plugins/dev-team/scripts/*.py` module that has a corresponding test
#: and asserts it is either in `FLOOR_TEST_SLICE` or named here with a real
#: reason — mirroring `coverage_config.py`'s `needs_accounting` /
#: `drift_check` convention: accounted for, or excluded WITH a reason, never
#: silently absent from both.
#:
#: Add an entry here when a module's function bodies carry NO floor-sensitive
#: runtime behavior (the stdlib modules it imports resolve the same way on
#: 3.10 as on any newer floor-relevant interpreter) — the same criterion
#: `FLOOR_TEST_SLICE`'s own docstring states for the inverse case. A module
#: whose body DOES carry such behavior (a version shim, a 3.11+-only stdlib
#: API) belongs in `FLOOR_TEST_SLICE` instead, not here.
SLICE_EXCLUSIONS = {
    "autoship_discover.py": "stdlib argparse/json/pathlib only; no floor-sensitive runtime API",
    "autoship_group.py": "stdlib argparse/json/pathlib only; no floor-sensitive runtime API",
    "autoship_proposals.py": "stdlib argparse/json/re/pathlib only; no floor-sensitive runtime API",
    "autoship_queue.py": "stdlib argparse/json/pathlib only; no floor-sensitive runtime API",
    "build_jobs.py": "stdlib os/sys only; no floor-sensitive runtime API",
    "build_rollback_point.py": (
        "stdlib argparse/json/subprocess/pathlib only; its datetime usage is "
        "timezone-aware construction, not a floor-sensitive parse shim"
    ),
    "build_slice_scope.py": (
        "stdlib argparse/json/re/pathlib only; its datetime usage is "
        "timezone-aware construction, not a floor-sensitive parse shim"
    ),
    "build_wave.py": "stdlib json/os/subprocess/pathlib only; no floor-sensitive runtime API",
    "build_wave_reconcile.py": (
        "stdlib argparse/os/re/shlex/subprocess only; no floor-sensitive runtime API"
    ),
    "build_worktree_baseref.py": "stdlib json/os/pathlib only; no floor-sensitive runtime API",
    "check_agent_scope.py": "stdlib argparse/pathlib only; no floor-sensitive runtime API",
    "check_agent_tool_mapping.py": (
        "stdlib argparse/json/re/pathlib only; no floor-sensitive runtime API"
    ),
    "check_review_agent_mcp_tools.py": (
        "stdlib argparse/json/pathlib only; no floor-sensitive runtime API"
    ),
    "check_security_assessment_mcp_tools.py": (
        "stdlib argparse/json/pathlib only; no floor-sensitive runtime API"
    ),
    "coverage_delta_steering.py": "stdlib argparse/json/pathlib only; no floor-sensitive runtime API",
    "mutation_yield_steering.py": (
        "stdlib argparse/json/sys/pathlib only; no floor-sensitive runtime API "
        "— same import set and same classification as its coverage sibling "
        "coverage_delta_steering.py, which #2033 ports"
    ),
    "coverage_discovery_java.py": (
        "stdlib re/sys/xml.etree/pathlib only; no floor-sensitive body of its "
        "own — the fromisoformat shim it could exercise lives in "
        "coverage_config.py, which already has its own slice entry"
    ),
    "coverage_gap_ranking.py": (
        "stdlib argparse/json/math/fractions/pathlib only; arithmetic and "
        "shared-parser delegation, no floor-sensitive runtime API of its own "
        "(per-format parsing moved to coverage_report_parse.py, issue #1873, "
        "itself stdlib-only)"
    ),
    "coverage_readiness.py": "stdlib argparse/json/re/pathlib only; no floor-sensitive runtime API",
    "coverage_report_parse.py": (
        "stdlib csv/json/re/xml.etree/dataclasses/pathlib only; no "
        "floor-sensitive runtime API"
    ),
    "detect_bdd_convention.py": (
        "stdlib argparse/fnmatch/json/re/pathlib/typing only; no "
        "floor-sensitive runtime API"
    ),
    "eval_ablation.py": (
        "stdlib argparse/json/pathlib only; its datetime usage is "
        "timezone-aware construction, not a floor-sensitive parse shim"
    ),
    "gherkin_analysis_coverage_gate.py": (
        "stdlib argparse/json/re/dataclasses/pathlib only; no "
        "floor-sensitive runtime API"
    ),
    "gherkin_cross_feature_duplicate_titles_gate.py": (
        "stdlib argparse/json/collections/pathlib only; no floor-sensitive "
        "runtime API"
    ),
    "gherkin_effectiveness_rollup.py": (
        "stdlib argparse/json/re/pathlib only; no floor-sensitive runtime API"
    ),
    "gherkin_failure_path_gate.py": (
        "stdlib argparse/json/pathlib only; no floor-sensitive runtime API"
    ),
    "gherkin_feature_merge.py": (
        "stdlib argparse/json/os/tempfile/dataclasses/pathlib only; no "
        "floor-sensitive runtime API"
    ),
    "gherkin_stub_gate.py": "stdlib argparse/json/pathlib only; no floor-sensitive runtime API",
    "gherkin_stub_merge.py": (
        "stdlib argparse/json/os/tempfile/dataclasses/pathlib only; no "
        "floor-sensitive runtime API"
    ),
    "git_origin_host.py": "stdlib subprocess/sys only; no floor-sensitive runtime API",
    "install-java-static-analysis.py": (
        "stdlib hashlib/hmac/os/shutil/subprocess/tempfile/urllib.request/"
        "zipfile/pathlib only; no floor-sensitive runtime API"
    ),
    "issue_deps.py": "stdlib json/os/subprocess/pathlib only; no floor-sensitive runtime API",
    "mutation_stack_sections.py": (
        "stdlib argparse/json/pathlib only; no floor-sensitive runtime API"
    ),
    "plan_gherkin_export.py": (
        "stdlib argparse/re/pathlib/typing only; no floor-sensitive runtime API"
    ),
    "plan_waves.py": (
        "stdlib argparse/fnmatch/json/re/pathlib only; no floor-sensitive "
        "runtime API"
    ),
    "pr_close_keyword_lint.py": (
        "stdlib argparse/json/re/dataclasses only; no floor-sensitive "
        "runtime API"
    ),
    "recon_inventory.py": "stdlib os/re/subprocess/pathlib only; no floor-sensitive runtime API",
    "run_invariants.py": (
        "stdlib argparse/subprocess/pathlib/typing only; no floor-sensitive "
        "runtime API"
    ),
    "select_lenses.py": "stdlib argparse/json/re/pathlib only; no floor-sensitive runtime API",
    "specs_convention_marker.py": "stdlib subprocess/pathlib only; no floor-sensitive runtime API",
    "test_improve_resume.py": (
        "stdlib argparse/json/re/pathlib only; no floor-sensitive runtime API"
    ),
    "verify_gherkin_quality_critic_isolation.py": (
        "stdlib argparse/os/secrets/shutil/subprocess/tempfile/textwrap/"
        "pathlib only; no floor-sensitive runtime API"
    ),
    "verify_tier.py": "stdlib argparse/json/re/pathlib only; no floor-sensitive runtime API",
}


def _ruff_shipped_target_version() -> str | None:
    """The shipped tree's entry in ruff.toml's `[per-file-target-version]`.

    Scoped, not global: repo-root `scripts/` and `tests/` run on a maintainer's
    or CI's interpreter and are outside ADR 0014's scope, so the global
    `target-version` is deliberately higher.

    Regex rather than a TOML library: `tomllib` is 3.11+, `tomli` is not
    stdlib, and this test has to run on whatever interpreter a contributor
    has. The key is a flat scalar inside a single table.
    """
    text = RUFF_CONFIG.read_text(encoding="utf-8")
    match = re.search(
        r'(?m)^\s*"plugins/dev-team/\*\*"\s*=\s*"([^"]+)"',
        text,
    )
    return match.group(1) if match else None


@pytest.fixture(scope="module")
def ci_local() -> str:
    return CI_LOCAL.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def ci_workflow() -> str:
    return CI_WORKFLOW.read_text(encoding="utf-8")


def _only_lists(workflow: str) -> list[list[str]]:
    """Every `--only=<comma-list>` argument actually invoked in the
    workflow, split into its component check names. Comment lines are
    stripped first — a future `#`-prefixed mention of `--only=chk_python_
    floor` (a commented-out step, or a comment quoting the rejected
    content-guard-tests wiring this file's own docstrings describe) must
    not satisfy a caller looking for the real invocation."""
    return [
        lst.split(",")
        for lst in re.findall(r"--only=([\w,-]+)", without_comments(workflow))
    ]


#: A slice entry, anchored to a known test root so a flag that merely embeds a
#: path (`--ignore=tests/scripts/test_x.py`) is never mistaken for one. Matched
#: against the literal token: a quoted path or a shell array expansion is
#: deliberately NOT resolved, because a parser that resolved `"${slice[@]}"`
#: would equally resolve `"${slice[@]:0:3}"` — the silent-subset bypass. Writing
#: the paths literally is the price of that, and a refactor that stops doing so
#: fails loudly rather than quietly running three of nine.
_SLICE_PATH_RE = re.compile(r"(?:tests|plugins)/[\w./-]*test_\w+\.py")

#: Every token of the invocation BEFORE `-m pytest`, declared rather than
#: inferred. This half decides which interpreter runs the slice and which
#: plugins load, so leaving it unasserted let the gate be reduced to nothing
#: without touching a single path: `export PYTEST_ADDOPTS=--collect-only` above
#: the call executes zero function bodies and exits 0, and dropping the
#: pytest-asyncio `--with` silently turns async tests into skips. The cleared
#: env vars are part of the declaration precisely so that ambient shell state
#: cannot narrow the run either.
FLOOR_INVOCATION_PREFIX = (
    "PYTEST_ADDOPTS=",
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD=",
    "uv",
    "run",
    "--python",
    '"$py310"',
    "--with",
    "'pytest>=7.0'",
    "--with",
    "'pytest-asyncio>=0.23'",
    "--with",
    "'jsonschema>=4.0'",
)


def _floor_invocation(ci_local: str) -> PytestInvocation | None:
    """`chk_python_floor`'s pytest command, split at `-m pytest` and at any
    `||`. Thin wrapper over the shared parser in `_ci_local_invocation` —
    see `pytest_invocation()` there for the full boundary rules (backslash
    continuation, the single-marker requirement, why comments are not
    stripped first, and why the `||` tail is returned rather than dropped,
    and why `None` — not an empty-but-valid-shaped tuple — is the
    unparseable sentinel).
    """
    return pytest_invocation(ci_local, FLOOR_FN)


def _floor_invocation_prefix(ci_local: str) -> list[str]:
    """Everything the command says before `-m pytest`."""
    result = _floor_invocation(ci_local)
    return result.prefix if result is not None else []


def _floor_invocation_tail(ci_local: str) -> list[str]:
    """Everything the command says after `||` — the failure path."""
    result = _floor_invocation(ci_local)
    return result.tail if result is not None else []


def _floor_slice_files(ci_local: str) -> list[str]:
    """The slice's test-file paths, in the order pytest receives them."""
    result = _floor_invocation(ci_local)
    args = result.args if result is not None else []
    return [t for t in args if _SLICE_PATH_RE.fullmatch(t)]


def _floor_slice_extra_args(ci_local: str) -> list[str]:
    """Every pytest argument that is not a declared slice path.

    An allowlist, not a denylist of known-bad flags: the point is to fail closed
    on arguments nobody has thought of yet. `--collect-only`, `--ignore=`,
    `--deselect`, `-k` and a trailing `-m` all leave the path list byte-identical
    while reducing — or eliminating — what actually executes. Named "extra args"
    rather than "flags" because it deliberately also catches things that are not
    flags at all, such as a truncating comment's own tokens.
    """
    result = _floor_invocation(ci_local)
    args = result.args if result is not None else []
    return [t for t in args if not _SLICE_PATH_RE.fullmatch(t)]


class TestTheFloorIsDeclaredOnce:
    def test_ruff_declares_it_for_the_shipped_tree(self):
        """The single source of truth, and the only thing that keeps ruff's own
        autofixes from rewriting shipped code into 3.9+ syntax."""
        assert _ruff_shipped_target_version() == FLOOR_RUFF, (
            "ruff.toml's [per-file-target-version] entry for plugins/dev-team/** is "
            "the one declaration of the shipped Python floor; removing or changing "
            "it silently un-pins every other check"
        )

    def test_the_floor_is_scoped_to_shipped_code_only(self):
        """Repo-root scripts and tests are outside ADR 0014's scope. Holding
        them to the shipped floor would impose a constraint the ADR explicitly
        declines to make."""
        text = RUFF_CONFIG.read_text(encoding="utf-8")
        globals_ = re.findall(r'(?m)^target-version\s*=\s*"([^"]+)"', text)
        assert globals_, "ruff.toml should still declare a global target-version"
        assert globals_[0] != FLOOR_RUFF, (
            "the global target-version applies to repo-root tooling; pinning it to "
            "the shipped floor makes every dev script obey a user-facing constraint"
        )

    def test_the_adr_states_the_same_floor(self):
        """ADR 0031 carries the current floor's rationale (`ADR` above points at
        it; ADR 0014 set the original 3.8 floor and its version question is
        superseded). Prose that disagrees with the tooling is how a floor quietly
        stops meaning anything — this docstring said "ADR 0014" and "Python 3.8"
        for a while after the constant moved, which is that same drift.

        Anchored to "Python <FLOOR_DOTTED>", built from the constant at assertion
        time rather than restated here, so this prose cannot go stale again; a
        bare version substring could match a section number."""
        assert re.search(r"Python\s+" + re.escape(FLOOR_DOTTED), ADR.read_text(encoding="utf-8"))


def _floor_check_body(ci_local: str) -> str:
    """The text of `chk_python_floor`'s function body. Thin wrapper over the
    shared `check_body()` in `_ci_local_invocation`."""
    return check_body(ci_local, FLOOR_FN)


class TestTheFloorIsProvenByRunningIt:
    """The gate is a real interpreter, not a description of one. These pin that
    it stays that way — an edit that downgrades it to a source scan, or lets it
    skip itself, should fail here.

    Wiring note: `chk_python_floor` runs in the default (no `--only`) gate, so
    the pre-push hook enforces it on every push. Since #1635 it also runs in
    its own `python-floor` CI job, via a `--only=chk_python_floor` invocation
    — see `TestTheFloorIsCheckedInCI` below for that leg's pin.
    """

    def test_ci_local_defines_the_floor_check(self, ci_local):
        assert "chk_python_floor()" in ci_local, (
            "scripts/ci-local.sh must define the floor check — it is the single "
            "place CI jobs and the pre-push hook both call into"
        )

    def test_the_check_runs_in_the_default_gate(self, ci_local):
        """Opt-in-only checks live in a separate array and never run unless
        named. The floor must not be one of them."""
        registry = check_registry(ci_local, "CHECKS")
        assert "chk_python_floor" in registry, (
            "the floor check must be in the always-run CHECKS array, not opt-in"
        )

    def test_the_check_uses_a_real_interpreter(self, ci_local):
        body = _floor_check_body(ci_local)
        # The value, not just the token. `FLOOR_INVOCATION_PREFIX` pins the literal
        # `"$py310"`, and a substring check for the resolver's name is satisfied by
        # a comment — so `py310="$(command -v python3)"` anywhere above the call
        # would run every stage of this gate on the dev interpreter with all tests
        # green. Pin the single assignment and its source.
        assert re.findall(
            r"\bpy310=\S*", without_comments(body)
        ) == ['py310="$(_resolve_python310)"'], (
            "py310 must be assigned exactly once, from _resolve_python310. "
            "Reassigning it silently runs the whole gate off-floor."
        )
        assert "py_compile" in body, "must byte-compile under the floor interpreter"
        assert "import_probe_shipped.py" in body, "must import under it too"

    def test_the_check_fails_rather_than_skips_without_an_interpreter(self, ci_local):
        """The decisive property. A floor check that reports 'skipped' on
        machines without the floor interpreter is silent exactly where it is
        most needed — the same shape as `engines.node` at >=24 letting
        ci-local skip eslint while printing 'All local CI checks passed'."""
        body = _floor_check_body(ci_local)
        assert "does not skip" in body, (
            "the no-interpreter branch must fail with an actionable message"
        )
        assert "return 1" in body
        assert "skipped" not in body, (
            "the floor check must never emit a 'skipped' status — see the module "
            "docstring"
        )

    def test_the_import_probe_actually_imports(self):
        """The probe must load modules, not grep them. If it ever grows a list
        of banned API names it has become the thing this gate replaced."""
        source = IMPORT_PROBE.read_text(encoding="utf-8")
        assert "exec_module" in source, "the probe must actually import modules"
        assert "VERSION_ERRORS" in source, "failures must come from the interpreter"

    def test_the_check_also_runs_a_real_test_slice_under_the_floor_interpreter(self, ci_local):
        """#1650: byte-compiling and importing prove a module parses and
        loads, not that its function bodies run clean under the floor
        interpreter. `chk_python_floor` must actually execute pytest against
        the shipped tree's test files, under the resolved floor
        interpreter specifically (not whatever `python3` happens to be on
        PATH), or a runtime-only API used only inside a function stays
        invisible to this gate again.

        The slice spans two test roots — repo-root `tests/scripts/` for the
        agent scripts and `plugins/dev-team/tests/scripts/` for the
        coverage-discovery modules (#1826). Both in one pytest invocation is
        safe because `pytest.ini` pins `--import-mode=importlib` (#1120), so
        the duplicate-basename "import file mismatch" that the default
        `prepend` mode would raise cannot occur."""
        assert _floor_invocation_prefix(ci_local) == list(FLOOR_INVOCATION_PREFIX), (
            "chk_python_floor's pytest command differs, before `-m pytest`, from "
            "FLOOR_INVOCATION_PREFIX. That half decides which interpreter runs "
            "the slice and which plugins load, and pytest also honours "
            "PYTEST_ADDOPTS — so it is declared, not merely present somewhere in "
            "the function. A substring check here would be satisfied by a comment."
        )

    def test_the_check_passes_pytest_exactly_the_declared_slice(self, ci_local):
        """Equality against the parsed argument list, not containment in the
        function text: a path merely *mentioned* in a comment satisfies `in body`
        just as well as a real argument, and containment says nothing about a
        path present in the invocation but absent from `FLOOR_TEST_SLICE`. Both
        directions matter — a slice that quietly shrinks is the "gate that cannot
        fail" this whole check exists to prevent, and a slice that grows without
        the declaration following it puts this file back to guessing.

        Compared as multisets. Order is not load-bearing (pytest runs the same
        tests whichever way the paths are wrapped), so alphabetizing them must
        not fail this test — but duplicates and membership changes must."""
        assert sorted(_floor_slice_files(ci_local)) == sorted(FLOOR_TEST_SLICE), (
            "chk_python_floor's pytest arguments and FLOOR_TEST_SLICE have "
            "diverged. Whichever one is wrong, they must be changed together."
        )

    def test_the_check_passes_pytest_no_narrowing_arguments(self, ci_local):
        """The slice's *paths* being right does not mean the slice *runs*.

        `--collect-only` makes pytest exit 0 having executed zero function
        bodies — reverting this gate to exactly the compile-and-import blind spot
        #1650 created it to close. `--ignore=`, `--deselect`, `-k` and a trailing
        `-m` each drop or filter tests the same way, all while leaving the path
        list byte-identical and the equality test above green.

        So this is an allowlist, not a denylist of known-bad flags: any argument
        that is not a declared path must be named here deliberately. That fails
        closed on flags nobody has thought of yet."""
        assert _floor_slice_extra_args(ci_local) == ["-q"], (
            "chk_python_floor passes pytest an argument other than `-q` and the "
            "declared slice paths. If it is genuinely wanted, add it here — but "
            "check first that it does not reduce what actually executes "
            "(--collect-only, --ignore, --deselect, -k, -m all do, silently)."
        )

    def test_the_check_does_not_suppress_its_own_verdict(self, ci_local):
        """The pytest invocation's exit status IS this gate's verdict, and this
        gate is a required status check on `main`. `-q || true`, or an early
        `return 0` above the invocation, leaves every other test here green while
        the slice never runs or never fails — a green required check that
        guarantees nothing, which this repo rates worse than no check at all.

        `_resolve_python310`'s own `return 0` sits above `chk_python_floor()` and
        is correctly outside `_floor_check_body`'s window."""
        body = _floor_check_body(ci_local)
        trailing = lines_after_invocation(ci_local, FLOOR_FN)
        assert not trailing, (
            f"chk_python_floor runs {trailing} after its pytest invocation. A bash "
            "function returns its LAST command's status and ci-local.sh runs "
            "without `set -e`, so a trailing line silently becomes the gate's "
            "verdict. The invocation must be last."
        )
        # The failure path is an ALLOWLIST, not a substring check. Everything after
        # `||` used to be unparsed, guarded only by `"-q || return 1" in body` —
        # which a comment satisfies, and this function's own comment block quotes
        # that idiom while explaining it. `-q || printf 'failed'` therefore reported
        # a failing slice as success with every test green.
        assert _floor_invocation_tail(ci_local) == ["return", "1"], (
            "the pytest invocation's failure path must be exactly `|| return 1`. "
            "Anything else there — `|| printf …`, `|| rc=$?`, a `; fi` closing a "
            "wrapper — discards or conditions the verdict, and this gate is a "
            "required status check on `main`."
        )
        # No early exit anywhere in the function: the structural check above only
        # constrains lines AFTER the command, so a `return 0` guard above it (or a
        # softened uv branch) would leave the gate green on machines that never run
        # the slice. Every legitimate guard here returns 1.
        code = without_comments(body)
        assert "return 0" not in code, (
            "chk_python_floor must never return 0 except by reaching the end of "
            "its pytest invocation; an early `return 0` makes the gate pass "
            "without running the slice. Comment lines are excluded — documenting "
            "this rule must not break it, the same reason `_only_lists` strips "
            "them. An obfuscated `return $((0))` is not caught here; that is "
            "deliberate evasion rather than the accidental shape, and it is "
            "recorded in #1829."
        )
        found = [x for x in ("|| true", "|| :", "&& true", "set +e") if x in code]
        assert not found, f"chk_python_floor contains {found}, which discards the verdict"

    def test_the_declared_slice_files_all_exist(self):
        """A slice entry naming a file that is not in the tree fails the gate
        loudly (pytest exits 4, "file or directory not found") rather than
        silently shrinking — confirmed by renaming a slice file away. That is
        the right failure mode, but it fails the whole gate for a typo, so catch
        a bad path here, where the message names it. The one assertion in this
        class with an oracle outside the two artifacts that pin each other."""
        missing = [rel for rel in FLOOR_TEST_SLICE if not (REPO_ROOT / rel).is_file()]
        assert not missing, (
            f"the declared floor test slice names files that do not exist: "
            f"{missing}. A stale path fails the gate with pytest's exit 4."
        )


#: Every top-level shipped script — deliberately NOT recursive: `scripts/lib/`
#: holds helpers shared BY these scripts, not shipped entry points of their
#: own (issue #1829 scopes the enumeration to `plugins/dev-team/scripts/*.py`).
SHIPPED_SCRIPTS_DIR = REPO_ROOT / "plugins" / "dev-team" / "scripts"

#: Both roots a shipped script's test can live under (mirrors FLOOR_TEST_SLICE
#: spanning both).
_TEST_ROOTS = (REPO_ROOT / "plugins" / "dev-team" / "tests", REPO_ROOT / "tests")


def _shipped_scripts() -> list[str]:
    return sorted(p.name for p in SHIPPED_SCRIPTS_DIR.glob("*.py"))


#: Confirmed-by-hand exceptions where the test file's name does not match
#: `test_<script_stem>.py` but genuinely exercises the named script — a
#: hyphenated script name that can only ever be referenced from Python as a
#: string (never imported), or a test scoped to a broader behavior than one
#: script. A generic content scan (grep the test bodies for the script name)
#: was tried and rejected: it also matched test files that merely mention
#: the script name as a fake/mock filename or import an unrelated helper
#: for fixture setup, which silently marked scripts as "covered" that were
#: not — a worse failure mode than the one this file exists to close.
_NONCANONICAL_TEST_FILES = {
    "build_worktree_baseref.py": "tests/skills/test_build_worktree_baseref_detect.py",
    "install-java-static-analysis.py": "tests/scripts/test_install_java_static_analysis.py",
    "mutation_stack_sections.py": "tests/skills/test_setup_mutation_stack_gate.py",
    # token_efficiency_review.py's canonical `test_token_efficiency_review.py`
    # (tests/hooks/) covers its hook-integration behavior; the dedicated
    # script-level test FLOOR_TEST_SLICE already runs under the floor
    # interpreter is this differently-named file.
    "token_efficiency_review.py": "tests/scripts/test_token_efficiency_review_script.py",
}


def _corresponding_test_files(script_name: str) -> list[str]:
    """Every `test_*.py` under either test root that exercises `script_name`
    — the canonical `test_<module_name>.py` (hyphens normalized to
    underscores), plus any confirmed `_NONCANONICAL_TEST_FILES` entry. Paths
    are returned relative to REPO_ROOT, POSIX-separated, matching
    FLOOR_TEST_SLICE's own notation."""
    module_name = Path(script_name).stem.replace("-", "_")
    canonical_name = f"test_{module_name}.py"
    found: list[str] = []
    for root in _TEST_ROOTS:
        if not root.is_dir():
            continue
        for candidate in sorted(root.rglob(canonical_name)):
            found.append(candidate.relative_to(REPO_ROOT).as_posix())
    noncanonical = _NONCANONICAL_TEST_FILES.get(script_name)
    if noncanonical and (REPO_ROOT / noncanonical).is_file():
        found.append(noncanonical)
    return found


class TestTheFloorSliceAccountsForEveryShippedScript:
    """#1829: `FLOOR_TEST_SLICE` is hand-maintained, so a tested shipped
    script can land and never join it — the exact shape #1826 was, recurring
    unchecked. This enumerates every `plugins/dev-team/scripts/*.py` module
    that HAS a test and asserts it is either in `FLOOR_TEST_SLICE` (a real
    test runs it under the floor interpreter) or named in `SLICE_EXCLUSIONS`
    with a reason — mirroring `coverage_config.py`'s `needs_accounting` /
    `drift_check` convention: accounted for, or excluded WITH a reason,
    never silently absent from both.

    A script with NO test at all (`_corresponding_test_files` returns
    `[]`) is out of scope here — that is a test-coverage gap, a different
    concern from this file's "is a real test wired to the floor
    interpreter" question."""

    def test_every_tested_script_is_in_the_slice_or_excluded_with_a_reason(self):
        unaccounted = []
        for script in _shipped_scripts():
            test_files = _corresponding_test_files(script)
            if not test_files:
                continue
            if any(t in FLOOR_TEST_SLICE for t in test_files):
                continue
            if script in SLICE_EXCLUSIONS:
                continue
            unaccounted.append(script)
        assert not unaccounted, (
            "these shipped, tested scripts are neither in FLOOR_TEST_SLICE "
            f"nor SLICE_EXCLUSIONS (with a reason): {unaccounted}. Add a "
            "FLOOR_TEST_SLICE entry if the module's function bodies carry "
            "floor-sensitive runtime behavior, or a SLICE_EXCLUSIONS entry "
            "with a real reason if they legitimately don't."
        )

    def test_slice_exclusions_name_real_shipped_scripts(self):
        """A stale or typo'd key silently stops accounting for anything —
        the same failure mode a wrong path in FLOOR_TEST_SLICE would be."""
        shipped = set(_shipped_scripts())
        stale = sorted(set(SLICE_EXCLUSIONS) - shipped)
        assert not stale, (
            f"SLICE_EXCLUSIONS names scripts that are not in "
            f"plugins/dev-team/scripts/: {stale}"
        )

    def test_slice_exclusions_all_carry_a_real_reason(self):
        empty = [name for name, reason in SLICE_EXCLUSIONS.items() if not reason.strip()]
        assert not empty, f"SLICE_EXCLUSIONS entries with no reason: {empty}"

    def test_no_script_is_both_slice_covered_and_excluded(self):
        """A script in both is a contradiction — is it exercised under the
        floor interpreter or not? — that this test would otherwise mask
        (the accounting test above only checks that at least one of the two
        holds)."""
        contradictions = [
            script
            for script in _shipped_scripts()
            if script in SLICE_EXCLUSIONS
            and any(t in FLOOR_TEST_SLICE for t in _corresponding_test_files(script))
        ]
        assert not contradictions, (
            f"these scripts are both in SLICE_EXCLUSIONS and covered by a "
            f"FLOOR_TEST_SLICE test: {contradictions}. Pick one."
        )


def _synthetic_floor_check(body: str) -> str:
    """A minimal `ci-local.sh` shaped so `_floor_check_body` finds its
    window. Thin wrapper over the shared `synthetic_check()` in
    `_ci_local_invocation`."""
    return synthetic_check(FLOOR_FN, body)


def test_without_comments_strips_whole_lines_but_keeps_inline_ones():
    """`without_comments` (shared with `test_python_ceiling.py` via
    `_ci_local_invocation`) backs three separate guards here — the `--only=`
    scan, the `py310=` single-assignment pin, and the verdict-suppression
    scan — so a bug in it would defang all three at once. Whole-line
    stripping is what makes documenting a rule safe; keeping inline comments
    is what stops a suppressor hiding behind one on a live code line."""
    text = "# whole line\n  # indented whole line\ncode()  # inline stays\nmore()"
    assert without_comments(text) == "code()  # inline stays\nmore()"


class TestTheSliceParserItself:
    """`_floor_invocation` decides whether every test above is asking the right
    question, so its rules are pinned here against synthetic input rather than
    only exercised once, indirectly, against whatever `ci-local.sh` happens to
    say today. Each case is a way a real edit could make the parser agree with a
    gate that had stopped proving anything — every one was first confirmed by
    hand against the live script, then written down here so it stays confirmed.
    """

    def test_it_reads_the_paths_the_invocation_actually_passes(self):
        body = _synthetic_floor_check(
            '  uv run --python "$py310" \\\n'
            "    -m pytest \\\n"
            "    tests/scripts/test_a.py \\\n"
            "    plugins/dev-team/tests/scripts/test_b.py \\\n"
            "    -q"
        )
        assert _floor_slice_files(body) == [
            "tests/scripts/test_a.py",
            "plugins/dev-team/tests/scripts/test_b.py",
        ]
        assert _floor_slice_extra_args(body) == ["-q"]

    def test_a_reflow_onto_one_line_changes_nothing(self):
        """pytest does not care how the continuation wraps, so neither may this."""
        body = _synthetic_floor_check(
            "  uv run -m pytest tests/scripts/test_a.py tests/scripts/test_b.py -q"
        )
        assert _floor_slice_files(body) == [
            "tests/scripts/test_a.py",
            "tests/scripts/test_b.py",
        ]

    def test_a_path_before_the_marker_is_not_an_argument(self):
        """A shell array declared above the call, with a subset expanded into it,
        must not be readable as the argument list."""
        body = _synthetic_floor_check(
            "  slice=( tests/scripts/test_a.py tests/scripts/test_b.py )\n"
            '  uv run -m pytest "${slice[@]:0:1}" -q'
        )
        assert _floor_slice_files(body) == []

    def test_a_second_marker_makes_the_parse_refuse_to_guess(self):
        """A decoy invocation must not supply the paths for the real one."""
        body = _synthetic_floor_check(
            "  printf 'about to run -m pytest\\n'\n"
            "  uv run -m pytest tests/scripts/test_a.py -q"
        )
        assert _floor_invocation(body) is None

    def test_a_flag_embedding_a_path_is_not_a_path(self):
        body = _synthetic_floor_check(
            "  uv run -m pytest \\\n"
            "    tests/scripts/test_a.py \\\n"
            "    --ignore=tests/scripts/test_b.py \\\n"
            "    -q"
        )
        assert _floor_slice_files(body) == ["tests/scripts/test_a.py"]
        assert "--ignore=tests/scripts/test_b.py" in _floor_slice_extra_args(body)

    def test_a_truncating_comment_is_surfaced_not_swallowed(self):
        """A `#` line carrying a trailing backslash does not comment itself out of
        a continued command — it ends the command there, so pytest receives only
        the arguments above it. The parser must not report the paths below as if
        they had been passed; keeping the comment's tokens means the flag
        allowlist rejects them and the gate's own test fails."""
        body = _synthetic_floor_check(
            "  uv run -m pytest \\\n"
            "    tests/scripts/test_a.py \\\n"
            "    # note \\\n"
            "    tests/scripts/test_b.py \\\n"
            "    -q"
        )
        assert _floor_slice_extra_args(body) != ["-q"], (
            "the truncating comment's tokens must survive into the argument list, "
            "where the allowlist rejects them. Asserting on the literal `#` would "
            "pin how the tokenizer spells it rather than the property that guards "
            "the gate."
        )

    def test_a_backslash_with_a_trailing_space_ends_the_command(self):
        """bash reads `\\` + space as an escaped space that ENDS the command, so
        every path below such a line is never passed to pytest. The parser must
        agree, or it reports nine paths for a command the shell cut short — the
        silent-subset outcome this gate exists to prevent. Pins the one
        `_floor_invocation` rule an `rstrip()` "tidy-up" would quietly undo."""
        body = _synthetic_floor_check(
            "  uv run -m pytest \\\n"
            "    tests/scripts/test_a.py \\ \n"
            "    tests/scripts/test_b.py \\\n"
            "    -q"
        )
        assert _floor_slice_files(body) == ["tests/scripts/test_a.py"]

    def test_the_failure_path_is_returned_not_discarded(self):
        """Everything after `||` was dropped, leaving the region unasserted."""
        body = _synthetic_floor_check(
            "  uv run -m pytest tests/scripts/test_a.py -q || printf 'failed'"
        )
        assert _floor_invocation(body)[2] == ["printf", "'failed'"]

    def test_a_missing_marker_yields_nothing_rather_than_the_whole_body(self):
        body = _synthetic_floor_check("  uv run tests/scripts/test_a.py")
        assert _floor_invocation(body) is None

    def test_it_stops_at_the_end_of_the_continued_command(self):
        """Anything after the invocation — including the closing brace — is not
        an argument."""
        body = _synthetic_floor_check(
            "  uv run -m pytest tests/scripts/test_a.py -q\n"
            "  echo tests/scripts/test_unrelated.py"
        )
        assert _floor_slice_files(body) == ["tests/scripts/test_a.py"]
        assert "}" not in _floor_slice_extra_args(body)


class TestTheFloorIsCheckedInCI:
    """chk_python_floor running in the default local gate (above) only
    enforces it on pushes that go through the pre-push hook. #1635: a push
    that bypasses hooks — --no-verify, a hookless cloud session — must still
    be run by something, which means a CI job has to name chk_python_floor
    in its own --only= list explicitly. (Blocking a GitHub-UI merge on a red
    run additionally needs the job in main's required-status-check ruleset,
    where it now is — repo settings live outside the tree, so no test here
    can pin that half.)"""

    def test_a_ci_job_runs_the_floor_check(self, ci_workflow):
        """A bare `in workflow` check passes on any mention of the name — a
        comment, a doc reference, a commented-out step — without the check
        being wired into a job's --only= list. Anchor to the real invocation,
        matching this file's own _floor_check_body/CHECKS-array rigor
        elsewhere."""
        only_lists = _only_lists(ci_workflow)
        assert any("chk_python_floor" in lst for lst in only_lists), (
            "no job in .github/workflows/plugin-tests.yml passes chk_python_floor "
            "in a --only= list — the floor is only enforced by the local "
            "pre-push hook, which a --no-verify push, a hookless cloud "
            "session, or a GitHub-UI merge all bypass"
        )

    def test_the_floor_job_runs_nothing_else(self, ci_workflow):
        """Defence-in-depth against #1635's own review fallout: a first
        attempt co-tenanted this check via actions/setup-python, which DID
        put the floor interpreter on PATH ahead of a check that needs 3.9+
        (chk_md_references' str.removeprefix) and silently degraded a
        pytest-backed check to 'skipped' (chk_hook_units). The shipped `uv`
        mechanism doesn't have that failure mode, but pinning the isolation
        — not just the presence — means a future edit can't quietly revert
        to co-tenanting without this test noticing, without also forbidding
        a second, equally-isolated invocation (e.g. a future matrix leg)
        that the isolation property itself has no objection to."""
        floor_lists = [lst for lst in _only_lists(ci_workflow) if "chk_python_floor" in lst]
        assert floor_lists and all(lst == ["chk_python_floor"] for lst in floor_lists), (
            "chk_python_floor must be the only check in every --only= list "
            f"that invokes it — found {floor_lists!r}. Co-tenanting it risks "
            "the exact PATH-shadowing regression #1635's review caught once "
            "already"
        )

    def test_the_floor_job_is_named_for_the_docs_that_reference_it(self, ci_workflow):
        """ruff.toml and root CLAUDE.md both cite a "Python N floor" job by
        that exact string. Nothing else pins the job's `name:` to those
        references, so a rename would leave both silently stale. Anchored to
        end-of-line: an unanchored match would also satisfy on the job's own
        *step* name ("Python N floor check (via ci-local)"), which shares
        the same literal prefix but isn't the job-level name at all — a
        step's `name:` is preceded by a `- ` list-item marker when it's the
        step's first key, as it is here, which `^\\s*` cannot absorb, so
        this pattern doesn't match it. The version here is deliberately a
        literal built from FLOOR_DOTTED at assertion time, not hardcoded:
        this string IS the status-check context the `main` ruleset matches
        on (see the module docstring above), so a future floor bump (ADR 0031's
        own
        successor) must update the workflow job name deliberately — this
        test failing IS that reminder, not something to silence by hardcoding
        a stale version here instead."""
        assert re.search(
            rf"(?m)^\s*name:\s*Python {re.escape(FLOOR_DOTTED)} floor\s*$", ci_workflow
        ), (
            "no job in .github/workflows/plugin-tests.yml is named exactly "
            f'"Python {FLOOR_DOTTED} floor" — ruff.toml and CLAUDE.md both '
            "reference it by that literal string"
        )
