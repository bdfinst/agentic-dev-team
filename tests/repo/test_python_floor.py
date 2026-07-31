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
`ruff.toml`'s `[per-file-target-version]` — and proven by `chk_python_floor`
in `scripts/ci-local.sh`, which resolves a real 3.8 interpreter and makes it
byte-compile and import every shipped module. That check runs in the default
gate, so the pre-push hook enforces it on every push.

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
ADR = REPO_ROOT / "docs" / "adr" / "0014-python-for-cross-os-scripts.md"
CI_LOCAL = REPO_ROOT / "scripts" / "ci-local.sh"
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
def ci_local() -> str:
    return CI_LOCAL.read_text(encoding="utf-8")


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


def _floor_check_body(ci_local: str) -> str:
    return ci_local.split("chk_python_floor()", 1)[-1].split("\nchk_", 1)[0]


class TestTheFloorIsProvenByRunningIt:
    """The gate is a real interpreter, not a description of one. These pin that
    it stays that way — an edit that downgrades it to a source scan, or lets it
    skip itself, should fail here.

    Wiring note: `chk_python_floor` runs in the default (no `--only`) gate, so
    the pre-push hook enforces it on every push. Adding it to a CI job means
    appending `chk_python_floor` to that job's `--only=` list, which needs
    `workflow` scope on the pushing credential.
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
        assert "_resolve_python38" in body
        assert "py_compile" in body, "must byte-compile under the floor interpreter"
        assert "import_probe_shipped.py" in body, "must import under it too"

    def test_the_check_fails_rather_than_skips_without_an_interpreter(self, ci_local):
        """The decisive property. A floor check that reports 'skipped' on
        machines without 3.8 is silent exactly where it is most needed —
        the same shape as `engines.node` at >=24 letting ci-local skip eslint
        while printing 'All local CI checks passed'."""
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
