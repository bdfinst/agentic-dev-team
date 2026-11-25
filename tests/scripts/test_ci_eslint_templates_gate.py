"""The ESLint template gate fails on a broken fixture and passes once it is gone.

`ci-local.sh --only=chk_eslint_templates` runs the Node tests for the scaffolded
ESLint template under ESLint 9 and 10. This test proves the gate can fail: it
copies the template tree, appends a `var` declaration to the control fixture
the Node tests expect to lint clean, and runs the gate on the copy. Removing
the line must turn the gate green again, and the output must name both ESLint
majors.

It is slow (two ESLint majors, twice), so it runs only inside the gate, which
sets `DEVTEAM_REQUIRE_REAL_ESLINT=1`. The copy never touches the real tree, so
sibling checks running in parallel cannot see the broken fixture.
"""

from __future__ import annotations

import os
import shutil
import subprocess

import pytest

from _repo_root import REPO_ROOT

TEMPLATES = REPO_ROOT / "plugins" / "dev-team" / "templates" / "eslint"
CI_LOCAL = REPO_ROOT / "scripts" / "ci-local.sh"
ENV_REQUIRE_ESLINT = "DEVTEAM_REQUIRE_REAL_ESLINT"
CONTROL_FIXTURE = "clean.js"
INJECTED_LINE = "var injected = 1;\n"

pytestmark = pytest.mark.skipif(
    not os.environ.get(ENV_REQUIRE_ESLINT),
    reason=f"runs only inside chk_eslint_templates, which sets {ENV_REQUIRE_ESLINT}=1",
)


@pytest.fixture(scope="module")
def template_copy(tmp_path_factory):
    """The template tree at the depth its tests expect, with the installed
    `node_modules` linked in and the eval fixtures the corpus test reads."""
    root = tmp_path_factory.mktemp("eslint-gate")
    copy = root / "plugins" / "dev-team" / "templates" / "eslint"
    shutil.copytree(TEMPLATES, copy, ignore=shutil.ignore_patterns("node_modules"))
    (copy / "dev" / "node_modules").symlink_to(
        TEMPLATES / "dev" / "node_modules", target_is_directory=True
    )
    for name in ("fixtures", "expected"):
        shutil.copytree(REPO_ROOT / "evals" / name, root / "evals" / name)
    return copy


def run_gate(template_copy):
    env = {
        **os.environ,
        "DEVTEAM_ESLINT_TEMPLATES_DIR": str(template_copy),
        "DEVTEAM_ESLINT_GATE_NESTED": "1",
    }
    env.pop("DEVTEAM_ESLINT_ROOT", None)
    return subprocess.run(
        ["bash", str(CI_LOCAL), "--only=chk_eslint_templates"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )


def test_gate_fails_on_an_injected_fixture_and_passes_after_removal(template_copy):
    control = template_copy / "dev" / "fixtures" / CONTROL_FIXTURE
    original = control.read_bytes()
    try:
        control.write_bytes(original + INJECTED_LINE.encode())
        broken = run_gate(template_copy)
    finally:
        control.write_bytes(original)
    clean = run_gate(template_copy)

    assert broken.returncode != 0, broken.stdout + broken.stderr
    assert "a non-empty clean control yields nothing" in broken.stdout
    assert clean.returncode == 0, clean.stdout + clean.stderr
    assert "ESLint major 9 (" in clean.stdout
    assert "ESLint major 10 (" in clean.stdout
