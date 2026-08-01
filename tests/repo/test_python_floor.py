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
in `scripts/ci-local.sh`, which resolves a real 3.8 interpreter and makes it
byte-compile and import every shipped module. That check runs in the default
gate, so the pre-push hook enforces it on every push — and, since #1635, a
dedicated `python-floor` job in `.github/workflows/plugin-tests.yml` also
runs it on every PR, so a push that bypasses local hooks (`--no-verify`, a
hookless cloud session) is still caught by CI. Making a red run actually
block a GitHub-UI merge needs the job's name added to `main`'s
required-status-check ruleset — a follow-up, not yet configured.

What follows pins those parts to each other. It deliberately contains no
opinion about which APIs are too new; that question belongs to the
interpreter.

See the "deterministic tools over inference" rule in the repo CLAUDE.md.
"""

from __future__ import annotations

import re

import pytest

from _repo_root import REPO_ROOT

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
    body = "\n".join(
        line for line in workflow.splitlines() if not line.lstrip().startswith("#")
    )
    return [lst.split(",") for lst in re.findall(r"--only=([\w,-]+)", body)]


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
        """ADR 0014 carries the rationale. Prose that disagrees with the
        tooling is how a floor quietly stops meaning anything. Anchored to
        "Python 3.8" rather than a bare "3.8" substring, which could match an
        unrelated version reference or section number."""
        assert re.search(r"Python\s+" + re.escape(FLOOR_DOTTED), ADR.read_text(encoding="utf-8"))


def _floor_check_body(ci_local: str) -> str:
    return ci_local.split("chk_python_floor()", 1)[-1].split("\nchk_", 1)[0]


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
        # Split on a line that is exactly `)`; check labels contain literal
        # parens ("(run-all.sh)"), so a bare `)` split truncates the array.
        registry = ci_local.split("CHECKS=(", 1)[-1].split("\n)", 1)[0]
        assert "chk_python_floor" in registry, (
            "the floor check must be in the always-run CHECKS array, not opt-in"
        )

    def test_the_check_uses_a_real_interpreter(self, ci_local):
        body = _floor_check_body(ci_local)
        assert "_resolve_python310" in body
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


class TestTheFloorIsCheckedInCI:
    """chk_python_floor running in the default local gate (above) only
    enforces it on pushes that go through the pre-push hook. #1635: a push
    that bypasses hooks — --no-verify, a hookless cloud session — must still
    be run by something, which means a CI job has to name chk_python_floor
    in its own --only= list explicitly. (Blocking a GitHub-UI merge on a red
    run additionally needs the job in main's required-status-check ruleset
    — a follow-up, not something a test in this repo can pin.)"""

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
        """Pins the CI job's exact `name:` so a rename can't happen silently.
        Anchored to end-of-line: an unanchored match would also satisfy on
        the job's own *step* name ("Python N floor check (via ci-local)"),
        which shares the same literal prefix but isn't the job-level name at
        all — a step's `name:` is preceded by a `- ` list-item marker when
        it's the step's first key, as it is here, which `^\\s*` cannot
        absorb, so this pattern doesn't match it.

        Deliberately hardcoded to "3.8" here, NOT built from FLOOR_DOTTED
        (currently "3.10"): this string will be the status-check context the
        `main` ruleset matches once the job is added there (see the module
        docstring above — not yet configured). ADR 0031 raised the floor to
        3.10 everywhere else in this repo (ruff.toml, this file's own
        FLOOR_DOTTED, the ADR itself), but this session's git credentials
        cannot push a `.github/workflows/` edit (no `workflow` OAuth scope),
        so the workflow's actual job name has NOT moved off "Python 3.8
        floor" yet as of this commit. A human applies a combined patch
        (workflow rename + this one literal, together) once `workflow` scope
        is available or a maintainer applies it directly — the exact
        "deliberate ruleset update" this test's design has always required,
        never something that should silently follow FLOOR_DOTTED on its own.
        """
        assert re.search(r"(?m)^\s*name:\s*Python 3\.8 floor\s*$", ci_workflow), (
            "no job in .github/workflows/plugin-tests.yml is named exactly "
            '"Python 3.8 floor" (pending the ADR 0031 workflow patch — see '
            "this test's own docstring)"
        )
