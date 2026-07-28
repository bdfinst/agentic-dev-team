"""Tests for .claude/ensure_npm_ci.py — the SessionStart hook that provisions
Husky git hooks in a fresh worktree/checkout that never ran `npm ci` (issue
#1469).

Every test runs the real script as a subprocess against a throwaway
``tmp_path`` (never the real repo's ``node_modules``/``.husky``), with a
stub ``npm`` on ``PATH`` standing in for the real one, and ``$HOME``
redirected so the hook's ``~/.cache/npm-ci-sessionstart.log`` never touches
the real home directory — so no test actually invokes the real ``npm ci``
or writes outside its own tmp_path.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

from _repo_root import REPO_ROOT

SCRIPT = REPO_ROOT / ".claude" / "ensure_npm_ci.py"


def _write_stub(path: Path, body: str) -> None:
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _run(
    project_root: Path, path_dirs: list, home: Path | None = None, package_json: bool = True
) -> subprocess.CompletedProcess:
    if package_json:
        (project_root / "package.json").write_text("{}")
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(project_root)
    env["HOME"] = str(home if home is not None else project_root)
    env["PATH"] = os.pathsep.join([*path_dirs, "/usr/bin", "/bin"])
    return subprocess.run(
        ["python3", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_syntax_is_valid() -> None:
    """python3 -c "import ast; ast.parse(...)" style guard: the script must
    at least parse cleanly."""
    import ast

    ast.parse(SCRIPT.read_text())


def test_noop_when_no_package_json(tmp_path: Path) -> None:
    # Not this repo's own checkout — the hook must not touch it.
    result = _run(tmp_path, [], package_json=False)

    assert result.returncode == 0
    assert result.stdout == ""


def test_noop_when_husky_marker_already_exists(tmp_path: Path) -> None:
    (tmp_path / "node_modules" / ".bin").mkdir(parents=True)
    (tmp_path / "node_modules" / ".bin" / "husky").write_text("")
    result = _run(tmp_path, [])

    assert result.returncode == 0
    assert result.stdout == ""


def test_noop_when_npm_not_on_path(tmp_path: Path) -> None:
    # No node_modules/.bin/husky, and PATH deliberately excludes any npm stub.
    result = _run(tmp_path, [])

    assert result.returncode == 0
    assert result.stdout == ""


def test_runs_npm_ci_and_reports_success(tmp_path: Path) -> None:
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    # Stub npm creates the husky binary, mimicking the real `npm ci`
    # running package.json's `prepare: husky` script.
    _write_stub(
        fakebin / "npm",
        'if [ "$1" = "ci" ]; then mkdir -p "$PWD/node_modules/.bin"; '
        'touch "$PWD/node_modules/.bin/husky"; exit 0; fi\nexit 1',
    )

    project_root = tmp_path / "project"
    project_root.mkdir()

    result = _run(project_root, [str(fakebin)])

    assert result.returncode == 0
    assert (project_root / "node_modules" / ".bin" / "husky").exists()
    payload = json.loads(result.stdout)
    assert payload["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "no longer silently inert" in payload["hookSpecificOutput"]["additionalContext"]


def test_runs_npm_ci_and_reports_failure(tmp_path: Path) -> None:
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    _write_stub(fakebin / "npm", "exit 1")

    project_root = tmp_path / "project"
    project_root.mkdir()
    home = tmp_path / "home"
    home.mkdir()

    result = _run(project_root, [str(fakebin)], home=home)

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    context = payload["hookSpecificOutput"]["additionalContext"]
    assert "failed or timed out" in context
    assert str(home / ".cache" / "npm-ci-sessionstart.log") in context
    assert (home / ".cache" / "npm-ci-sessionstart.log").exists()


def test_npm_ci_timeout_is_fail_open(tmp_path: Path, monkeypatch) -> None:
    # A stub npm that sleeps past the hook's real 180s timeout would make
    # this test slow; instead, load the script as a module and monkeypatch
    # the shared run_logged() call boundary to report a timeout directly.
    # monkeypatch.setattr ensures this patch is undone after this test.
    import importlib.util

    spec = importlib.util.spec_from_file_location("ensure_npm_ci_mod", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "package.json").write_text("{}")

    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/bin/npm")
    monkeypatch.setattr(module, "run_logged", lambda cmd, cwd, log_path, timeout: False)
    monkeypatch.setattr(module, "resolve_project_root", lambda: project_root)

    messages = []
    monkeypatch.setattr(module, "_emit", messages.append)

    exit_code = module.main()

    assert exit_code == 0
    assert len(messages) == 1
    assert "failed or timed out" in messages[0]


def test_never_raises_on_unexpected_error(monkeypatch) -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("ensure_npm_ci_mod2", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def boom():
        raise RuntimeError("unexpected")

    monkeypatch.setattr(module, "resolve_project_root", boom)

    # main() must swallow this and still return 0, never raise.
    assert module.main() == 0
