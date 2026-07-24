"""#1236 — dev-setup.sh must skip the requirements-dev.txt install when the
deps are already present, and only install what is missing.

The substantive logic is the `dev_deps_satisfied()` probe: it decides whether
the pip install runs at all. These tests assert (1) the guard is wired into a
skip branch, and (2) the probe's module list stays in sync with
requirements-dev.txt — the drift the guard's own comment warns about, which
would otherwise let a newly-declared dep silently escape the "already
satisfied" check and reinstall on every run.
"""

from __future__ import annotations

import re

from _repo_root import REPO_ROOT

DEV_SETUP = REPO_ROOT / "scripts" / "dev-setup.sh"
REQUIREMENTS = REPO_ROOT / "requirements-dev.txt"

# requirements-dev.txt distribution name -> importable module name. `ruff`
# ships only a console script (no importable module), so the probe checks it
# with `shutil.which` instead of `find_spec`; it maps to None here.
DIST_TO_MODULE = {
    "PyYAML": "yaml",
    "semgrep": "semgrep",
    "httpx": "httpx",
    "jsonschema": "jsonschema",
    "pytest": "pytest",
    "pytest-asyncio": "pytest_asyncio",
    "pytest-xdist": "xdist",
    "pytest-cov": "pytest_cov",
    "ruff": None,
    "mypy": "mypy",
}


def _dev_setup() -> str:
    return DEV_SETUP.read_text(encoding="utf-8")


def _declared_dists() -> set[str]:
    dists = set()
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Strip any version specifier (>=, ==, <, ~=, etc.).
        name = re.split(r"[<>=~!]", line, maxsplit=1)[0].strip()
        if name:
            dists.add(name)
    return dists


def test_guard_function_is_wired_into_a_skip_branch():
    body = _dev_setup()
    assert "dev_deps_satisfied()" in body, "probe function must be defined"
    # It must gate the install as a skip branch, not run unconditionally.
    assert re.search(r"elif\s+dev_deps_satisfied", body)
    assert "already satisfied" in body


def test_pip_install_only_runs_in_the_else_arm():
    """The pip install must live in the `else` arm below the satisfied check,
    not merely somewhere after it — a regression that made the install
    unconditional (moved above the `else`) must fail this test."""
    body = _dev_setup()
    assert "elif dev_deps_satisfied" in body, "satisfied guard removed"
    assert (
        "pip install --quiet -r requirements-dev.txt" in body
    ), "requirements-dev install removed"
    sat_idx = body.index("elif dev_deps_satisfied")
    # An `else` must separate the satisfied guard from the install, and the
    # install must fall after that `else` — i.e. inside the else arm.
    else_idx = body.index("else", sat_idx)
    install_idx = body.index("pip install --quiet -r requirements-dev.txt")
    assert (
        sat_idx < else_idx < install_idx
    ), "install must live in the else arm below the satisfied guard"


def test_probe_module_list_covers_every_requirement():
    """Every requirements-dev.txt dist is checked by the probe: importable ones
    appear in the find_spec module list; ruff (CLI-only) via shutil.which."""
    body = _dev_setup()
    # Isolate the embedded Python probe so we don't match module names elsewhere.
    probe = body[body.index("python3 - <<'PY'") : body.index("\nPY\n")]

    declared = _declared_dists()
    # Every declared dist must be known to this test's mapping (forces the test
    # to be updated alongside requirements-dev.txt).
    unknown = declared - set(DIST_TO_MODULE)
    assert not unknown, f"unmapped requirements-dev.txt entries: {sorted(unknown)}"

    for dist in declared:
        module = DIST_TO_MODULE[dist]
        if module is None:
            assert 'which("ruff")' in probe, "ruff must be checked via which()"
        else:
            assert (
                f'"{module}"' in probe
            ), f"probe omits module {module!r} for dist {dist!r}"
