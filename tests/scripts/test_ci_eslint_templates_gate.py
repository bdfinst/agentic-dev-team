"""The ESLint template gate fails closed and fails on a broken fixture.

`ci-local.sh --only=chk_eslint_templates` runs the Node tests for the scaffolded
ESLint template under ESLint 9 and 10. These tests prove the gate can fail:

- fast tests (need `node`, or only bash): a wrong ESLint major, a missing
  install and a missing `node` under `CI=1` each fail with a message that says
  what to do, and the gate never runs `npm ci` itself (it would delete the
  `node_modules` that `chk_hook_units` reads concurrently);
- one slow test copies the template tree, appends a `var` declaration to the
  control fixture the Node tests expect to lint clean, and runs the gate on the
  copy. Removing the line must turn the gate green again, and the output must
  name both ESLint majors. It runs only inside the gate, which sets
  `DEVTEAM_REQUIRE_REAL_ESLINT=1`. The copy never touches the real tree, so
  sibling checks running in parallel cannot see the broken fixture.

Every gate run gets an allowlisted environment, so nothing the developer or CI
exports reaches it, and runs in its own process group so a timeout kills `node`
and `pytest` too.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys

import pytest

from _repo_root import REPO_ROOT

TEMPLATES = REPO_ROOT / "plugins" / "dev-team" / "templates" / "eslint"
CI_LOCAL = REPO_ROOT / "scripts" / "ci-local.sh"
ENV_REQUIRE_ESLINT = "DEVTEAM_REQUIRE_REAL_ESLINT"
CONTROL_FIXTURE = "clean.js"
INJECTED_LINE = "var injected = 1;\n"
ENV_ALLOWLIST = ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "TERM")
# What ci-local.sh and the gate call before they reach the node/npm probe.
SHELL_TOOLS = [
    *("bash", "env", "git", "getconf", "mktemp", "cat", "rm", "tput", "dirname"),
    *("basename", "uname", "sed", "tr", "grep", "mkdir", "date", "sleep", "head"),
    *("tail", "awk", "cut", "sort", "wc"),
]
NPM_SHIM = '#!/bin/sh\necho "$@" >> "$NPM_CALLS_FILE"\nexit 1\n'

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None,
    reason="ci-local.sh is a bash script",
)
needs_node = pytest.mark.skipif(
    shutil.which("node") is None, reason="the gate needs node on PATH"
)
slow_gate = pytest.mark.skipif(
    not os.environ.get(ENV_REQUIRE_ESLINT),
    reason=f"runs only inside chk_eslint_templates, which sets {ENV_REQUIRE_ESLINT}=1",
)


def gate_env(templates_dir, **extra):
    env = {name: os.environ[name] for name in ENV_ALLOWLIST if name in os.environ}
    env["DEVTEAM_ESLINT_TEMPLATES_DIR"] = str(templates_dir)
    env["DEVTEAM_ESLINT_GATE_NESTED"] = "1"
    env.update(extra)
    return env


def run_gate(env, timeout=600):
    """Run the gate in its own process group; kill the whole group on timeout."""
    proc = subprocess.Popen(
        ["bash", str(CI_LOCAL), "--only=chk_eslint_templates"],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    try:
        output, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        pytest.fail(f"gate did not finish within {timeout}s; process group killed")
    return proc.returncode, output


def npm_shim_dir(tmp_path):
    """A directory with an `npm` that records its calls and fails."""
    shim = tmp_path / "shim"
    shim.mkdir()
    npm = shim / "npm"
    npm.write_text(NPM_SHIM, encoding="utf-8")
    npm.chmod(0o755)
    return shim, tmp_path / "npm-calls.txt"


def fake_template_tree(root, eslint_version=None):
    """A template tree holding only `dev/`, with a stub ESLint when given a version."""
    (root / "dev").mkdir(parents=True)
    if eslint_version is not None:
        eslint = root / "dev" / "node_modules" / "eslint"
        eslint.mkdir(parents=True)
        (eslint / "package.json").write_text(
            f'{{"version": "{eslint_version}"}}', encoding="utf-8"
        )
    return root


@needs_node
def test_wrong_eslint_major_fails_naming_the_needed_major(tmp_path):
    templates = fake_template_tree(tmp_path / "eslint", eslint_version="8.0.0")
    code, output = run_gate(gate_env(templates), timeout=120)
    assert code != 0, output
    assert "needs ESLint 9" in output, output


@needs_node
def test_missing_install_fails_telling_you_to_run_npm_ci_and_never_runs_it(tmp_path):
    templates = fake_template_tree(tmp_path / "eslint")
    shim, calls = npm_shim_dir(tmp_path)
    env = gate_env(
        templates,
        PATH=f"{shim}{os.pathsep}{os.environ['PATH']}",
        NPM_CALLS_FILE=str(calls),
    )
    code, output = run_gate(env, timeout=120)
    assert code != 0, output
    assert "run npm ci in" in output, output
    assert not calls.exists(), f"the gate ran npm: {calls.read_text()}"
    assert not (templates / "dev" / "node_modules" / ".package-lock.json").exists()


def test_missing_node_fails_under_ci(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in SHELL_TOOLS:
        found = shutil.which(tool)
        if found:
            (bin_dir / tool).symlink_to(found)
    templates = fake_template_tree(tmp_path / "eslint", eslint_version="9.0.0")
    env = gate_env(templates, PATH=str(bin_dir), CI="1")
    code, output = run_gate(env, timeout=120)
    assert code != 0, output
    assert "node and npm are required in CI" in output, output


def link_or_copy(src, dst):
    """Hard-link when the filesystem allows it (fast, shares no write path the
    gate uses), copy otherwise."""
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


@pytest.fixture(scope="module")
def template_copy(tmp_path_factory):
    """The template tree at the depth its tests expect, with its own copy of the
    installed `node_modules` (hard links, never a symlink an `npm ci` could
    follow) and the eval fixtures the corpus test reads."""
    root = tmp_path_factory.mktemp("eslint-gate")
    copy = root / "plugins" / "dev-team" / "templates" / "eslint"
    shutil.copytree(TEMPLATES, copy, symlinks=True, copy_function=link_or_copy)
    for name in ("fixtures", "expected"):
        shutil.copytree(REPO_ROOT / "evals" / name, root / "evals" / name)
    return copy


@slow_gate
@needs_node
def test_gate_fails_on_an_injected_fixture_and_passes_after_removal(
    template_copy, tmp_path
):
    shim, calls = npm_shim_dir(tmp_path)
    env = gate_env(
        template_copy,
        PATH=f"{shim}{os.pathsep}{os.environ['PATH']}",
        NPM_CALLS_FILE=str(calls),
    )
    control = template_copy / "dev" / "fixtures" / CONTROL_FIXTURE
    original = control.read_bytes()
    try:
        # Break the copy only; hard links share inodes, so replace the file
        # rather than write through the link to the real fixture.
        control.unlink()
        control.write_bytes(original + INJECTED_LINE.encode())
        broken_code, broken_out = run_gate(env)
    finally:
        control.unlink()
        control.write_bytes(original)
    clean_code, clean_out = run_gate(env)

    assert broken_code != 0, broken_out
    assert "a non-empty clean control yields nothing" in broken_out
    assert clean_code == 0, clean_out
    assert "ESLint major 9 (" in clean_out
    assert "ESLint major 10 (" in clean_out
    assert not calls.exists(), f"the gate ran npm: {calls.read_text()}"
    assert (TEMPLATES / "dev" / "node_modules" / "eslint").is_dir()
    assert (TEMPLATES / "dev" / "fixtures" / CONTROL_FIXTURE).read_bytes() == original
