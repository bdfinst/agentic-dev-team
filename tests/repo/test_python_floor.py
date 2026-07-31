"""The shipped Python floor is declared once and proven by running it (#1623).

ADR 0014 puts shipped plugin code on **Python 3.8, stdlib only**, because 3.8
is what Ubuntu 20.04 LTS, Homebrew, and python.org still hand a user who
installs this plugin. Nothing enforced that, and it drifted: five shipped
scripts raised `TypeError: 'type' object is not subscriptable` at import time
on a real 3.8.20, eight more called `str.removeprefix` (3.9+), and
`cost_meter.py` used PEP 584's `dict | dict` merge (3.9+).

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
`ruff.toml`'s `target-version` — and proven by the "Python 3.8 floor" CI job
running the plugin's real test suite on a real 3.8. What follows pins those
parts to each other. It deliberately contains no opinion about which APIs are
too new; that question belongs to the interpreter.

See the "deterministic tools over inference" rule in the repo CLAUDE.md.
"""

from __future__ import annotations

import re

import pytest

from _repo_root import REPO_ROOT

RUFF_CONFIG = REPO_ROOT / "ruff.toml"
ADR = REPO_ROOT / "docs" / "adr" / "0014-python-for-cross-os-scripts.md"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "plugin-tests.yml"
IMPORT_PROBE = REPO_ROOT / "scripts" / "import_probe_shipped.py"

#: The floor every part below must agree on, in each part's own notation.
FLOOR_RUFF = "py38"
FLOOR_DOTTED = "3.8"


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
def workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


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
        tooling is how a floor quietly stops meaning anything."""
        assert FLOOR_DOTTED in ADR.read_text(encoding="utf-8")


class TestTheFloorIsProvenByRunningIt:
    """The gate is a real interpreter executing real tests. These pin that it
    stays that way — a future edit that downgrades this job to a linter pass
    or a static scan should fail here."""

    def test_a_job_pins_the_floor_interpreter(self, workflow):
        assert 'python-version: "{}"'.format(FLOOR_DOTTED) in workflow, (
            "no CI job provisions Python {} — without a real interpreter the floor "
            "is only ever an assertion".format(FLOOR_DOTTED)
        )

    def test_that_job_runs_the_plugin_test_suite(self, workflow):
        """Byte-compiling and importing are necessary but not sufficient: a
        3.9-only call inside a function body only surfaces when the body runs.
        Executing the suite is what makes this gate behavioural."""
        floor_job = workflow.split("python-floor:", 1)[-1].split("\n  shell-tests:", 1)[0]
        assert "pytest plugins/dev-team/tests" in floor_job, (
            "the floor job must run the plugin suite, not merely import-check it — "
            "`dict | dict` in cost_meter.py imported fine and failed 9 tests"
        )

    def test_that_job_also_byte_compiles_and_imports(self, workflow):
        """Covers shipped modules the suite never touches."""
        floor_job = workflow.split("python-floor:", 1)[-1].split("\n  shell-tests:", 1)[0]
        assert "py_compile" in floor_job
        assert "import_probe_shipped.py" in floor_job

    def test_the_import_probe_exists_and_is_not_a_pattern_matcher(self):
        """The probe must load modules, not grep them. If it ever grows a list
        of banned API names it has become the thing this gate replaced."""
        source = IMPORT_PROBE.read_text(encoding="utf-8")
        assert "exec_module" in source, "the probe must actually import modules"


class TestTheFloorJobCannotSilentlyVanish:
    def test_the_job_is_not_conditional(self, workflow):
        """A floor job behind an `if:` can skip on the very pushes that break
        it, and a skipped required check reads as a passing one."""
        floor_job = workflow.split("python-floor:", 1)[-1].split("\n  shell-tests:", 1)[0]
        assert "\n    if:" not in floor_job, (
            "the floor job must run unconditionally on every PR"
        )

    def test_the_job_does_not_continue_on_error(self, workflow):
        floor_job = workflow.split("python-floor:", 1)[-1].split("\n  shell-tests:", 1)[0]
        assert "continue-on-error" not in floor_job
