"""Tests for .claude/ensure_code_graph_tools.py — the SessionStart hook that
builds a missing CodeGraph/Repowise/Graphify index in a fresh
worktree/checkout when the corresponding CLI is already installed (issue
#1469).

Every test runs the real script as a subprocess against a throwaway
``tmp_path`` project root, with stub CLIs on ``PATH`` standing in for the
real ones, and ``$HOME`` redirected so the hook's ``~/.cache/*.log`` files
never touch the real home directory.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path


from _repo_root import REPO_ROOT

SCRIPT = REPO_ROOT / ".claude" / "ensure_code_graph_tools.py"


def _write_stub(path: Path, body: str) -> None:
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _run(project_root: Path, path_dirs: list, home: Path | None = None) -> subprocess.CompletedProcess:
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
    import ast

    ast.parse(SCRIPT.read_text())


def test_noop_when_no_tools_on_path(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()

    result = _run(project_root, [])

    assert result.returncode == 0
    assert result.stdout == ""


def test_noop_when_all_three_already_indexed(tmp_path: Path) -> None:
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    for tool in ("codegraph", "repowise", "graphify"):
        _write_stub(fakebin / tool, "exit 1")  # must never be invoked

    project_root = tmp_path / "project"
    (project_root / ".codegraph").mkdir(parents=True)
    (project_root / ".repowise").mkdir(parents=True)
    (project_root / "graphify-out").mkdir(parents=True)
    (project_root / "graphify-out" / "graph.json").write_text("{}")

    result = _run(project_root, [str(fakebin)])

    assert result.returncode == 0
    assert result.stdout == ""


def test_builds_codegraph_index_when_missing(tmp_path: Path) -> None:
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    _write_stub(fakebin / "codegraph", 'mkdir -p "$PWD/.codegraph"\nexit 0')

    project_root = tmp_path / "project"
    project_root.mkdir()

    result = _run(project_root, [str(fakebin)])

    assert result.returncode == 0
    assert (project_root / ".codegraph").exists()
    payload = json.loads(result.stdout)
    context = payload["hookSpecificOutput"]["additionalContext"]
    assert "CodeGraph" in context and "initialized" in context


def test_codegraph_never_invoked_when_already_indexed(tmp_path: Path) -> None:
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    _write_stub(fakebin / "codegraph", "exit 1")  # must never run

    project_root = tmp_path / "project"
    (project_root / ".codegraph").mkdir(parents=True)

    result = _run(project_root, [str(fakebin)])

    assert result.returncode == 0
    assert result.stdout == ""


def test_builds_graphify_index_when_missing(tmp_path: Path) -> None:
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    _write_stub(
        fakebin / "graphify",
        'mkdir -p "$PWD/graphify-out"\necho "{}" > "$PWD/graphify-out/graph.json"\nexit 0',
    )

    project_root = tmp_path / "project"
    project_root.mkdir()

    result = _run(project_root, [str(fakebin)])

    assert result.returncode == 0
    assert (project_root / "graphify-out" / "graph.json").exists()
    payload = json.loads(result.stdout)
    context = payload["hookSpecificOutput"]["additionalContext"]
    assert "Graphify" in context and "built" in context


def test_repowise_index_preserves_tracked_claude_md(tmp_path: Path) -> None:
    # As documented: repowise init writes its own usage-instructions block
    # into the TRACKED .claude/CLAUDE.md file. The hook must snapshot and
    # restore it so the tracked file is left untouched by this run.
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    _write_stub(
        fakebin / "repowise",
        'mkdir -p "$PWD/.repowise"\n'
        'echo "## repowise usage instructions injected" >> "$PWD/.claude/CLAUDE.md"\n'
        "exit 0",
    )

    project_root = tmp_path / "project"
    claude_md = project_root / ".claude"
    claude_md.mkdir(parents=True)
    original = "# Original CLAUDE.md content\n"
    (claude_md / "CLAUDE.md").write_text(original)

    result = _run(project_root, [str(fakebin)])

    assert result.returncode == 0
    assert (project_root / ".repowise").exists()
    assert (claude_md / "CLAUDE.md").read_text() == original


def test_repowise_index_removes_claude_md_it_created(tmp_path: Path) -> None:
    # If .claude/CLAUDE.md did not exist before this run, the hook must
    # remove whatever CLAUDE.md that repowise created from nothing.
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    _write_stub(
        fakebin / "repowise",
        'mkdir -p "$PWD/.repowise"\n'
        'mkdir -p "$PWD/.claude"\n'
        'echo "## repowise usage instructions injected" > "$PWD/.claude/CLAUDE.md"\n'
        "exit 0",
    )

    project_root = tmp_path / "project"
    project_root.mkdir()
    claude_md = project_root / ".claude" / "CLAUDE.md"

    result = _run(project_root, [str(fakebin)])

    assert result.returncode == 0
    assert (project_root / ".repowise").exists()
    assert not claude_md.exists()


def test_one_tool_failure_does_not_block_others(tmp_path: Path) -> None:
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    _write_stub(fakebin / "codegraph", "exit 1")
    _write_stub(
        fakebin / "graphify",
        'mkdir -p "$PWD/graphify-out"\necho "{}" > "$PWD/graphify-out/graph.json"\nexit 0',
    )

    project_root = tmp_path / "project"
    project_root.mkdir()
    home = tmp_path / "home"
    home.mkdir()

    result = _run(project_root, [str(fakebin)], home=home)

    assert result.returncode == 0
    assert not (project_root / ".codegraph").exists()
    assert (project_root / "graphify-out" / "graph.json").exists()
    payload = json.loads(result.stdout)
    context = payload["hookSpecificOutput"]["additionalContext"]
    assert "CodeGraph" in context and "failed or timed out" in context
    assert "Graphify" in context


def test_index_timeout_is_fail_open(tmp_path: Path, monkeypatch) -> None:
    # As in the ensure_npm_ci timeout test: monkeypatch the module's shared
    # run_logged() call boundary to report a failure/timeout directly rather
    # than waiting out a real timeout with a sleeping stub. monkeypatch
    # auto-restores after this test.
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "ensure_code_graph_tools_mod", SCRIPT
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    project_root = tmp_path / "project"
    project_root.mkdir()

    monkeypatch.setattr(module.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(module, "run_logged", lambda cmd, cwd, log_path, timeout_seconds: False)
    monkeypatch.setattr(module, "resolve_project_root", lambda: project_root)

    exit_code = module.main()

    assert exit_code == 0


def test_never_raises_on_unexpected_error(monkeypatch) -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "ensure_code_graph_tools_mod2", SCRIPT
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def boom():
        raise RuntimeError("unexpected")

    monkeypatch.setattr(module, "resolve_project_root", boom)

    assert module.main() == 0
