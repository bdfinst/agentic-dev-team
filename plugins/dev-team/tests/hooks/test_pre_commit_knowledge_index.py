"""Unit tests for hooks/pre_commit_knowledge_index.py (#582).

Mirror of tests/hooks/pre_commit_knowledge_index_tests.bats. The hook
blocks `git commit` when the working-tree knowledge/index.json is stale
relative to the corpus. Uses the ported knowledge_index_paths (#575) and
pre_commit_detect (#576) modules.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[4]
_HOOK = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "pre_commit_knowledge_index.py"

_TESTS_LIB = Path(__file__).resolve().parents[2] / "tests" / "lib"
if str(_TESTS_LIB) not in sys.path:
    sys.path.insert(0, str(_TESTS_LIB))

from hermetic import hermetic_git_env  # type: ignore[import-not-found]  # noqa: E402


def _run(
    payload: dict, cwd: Path, extra_env: dict = None
) -> subprocess.CompletedProcess[str]:
    proc_env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        **(extra_env or {}),
    }
    # Run the COPY of the hook inside the temp repo — the .bats does the
    # same for the .sh sibling. This is what ties the builder's __file__
    # resolution to the test repo's corpus rather than this working tree.
    hook_in_repo = (
        cwd / "plugins" / "dev-team" / "hooks" / "pre_commit_knowledge_index.py"
    )
    return subprocess.run(
        ["python3", str(hook_in_repo)],
        input=json.dumps(payload),
        env=proc_env,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A tiny hermetic git repo with a plugin corpus tree + fresh index."""
    env = hermetic_git_env(home=tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t.dev"], cwd=tmp_path, env=env, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "tester"], cwd=tmp_path, env=env, check=True
    )
    plugin = tmp_path / "plugins" / "dev-team"
    (plugin / "knowledge").mkdir(parents=True)
    (plugin / "skills" / "specs").mkdir(parents=True)
    (plugin / "agents").mkdir(parents=True)
    (plugin / "hooks" / "lib").mkdir(parents=True)

    (plugin / "knowledge" / "foo.md").write_text(
        "# Foo\n## Section A\nFirst sentence of A.\n"
    )
    (plugin / "agents" / "some-agent.md").write_text(
        "# Some Agent\n## Section\nBody.\n"
    )

    # Copy the shared libs + builder into the test repo so its layout mirrors
    # a real plugin install and the hook can resolve its dependencies.
    src_lib = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"
    for name in (
        "build_knowledge_index.py",
        "knowledge_index_paths.py",
        "pre_commit_detect.py",
        "stdin_json.py",
    ):
        (plugin / "hooks" / "lib" / name).write_text((src_lib / name).read_text())
    # Copy the hook itself too so it can find its siblings on sys.path.
    (plugin / "hooks" / "pre_commit_knowledge_index.py").write_text(_HOOK.read_text())

    subprocess.run(["git", "add", "-A"], cwd=tmp_path, env=env, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "initial"], cwd=tmp_path, env=env, check=True
    )

    # Build the fresh index against the temp repo and stage it.
    subprocess.run(
        ["python3", "plugins/dev-team/hooks/lib/build_knowledge_index.py"],
        cwd=tmp_path,
        env=env,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "add", "plugins/dev-team/knowledge/index.json"],
        cwd=tmp_path,
        env=env,
        check=True,
    )
    return tmp_path


def test_non_commit_invocation_silent(repo: Path) -> None:
    r = _run({"tool_name": "Bash", "tool_input": {"command": "ls -la"}}, cwd=repo)
    assert r.returncode == 0
    assert r.stdout == ""
    assert r.stderr == ""


def test_no_verify_bypass(repo: Path) -> None:
    # Make the index stale.
    (repo / "plugins" / "dev-team" / "knowledge" / "foo.md").write_text(
        "# Foo\n## Section A\nEdited body.\n"
    )
    env = hermetic_git_env(home=repo)
    subprocess.run(
        ["git", "add", "plugins/dev-team/knowledge/foo.md"],
        cwd=repo,
        env=env,
        check=True,
    )
    r = _run(
        {
            "tool_name": "Bash",
            "tool_input": {"command": "git commit --no-verify -m foo"},
        },
        cwd=repo,
    )
    assert r.returncode == 0


def test_commit_with_only_non_corpus_staged_is_allowed(repo: Path) -> None:
    env = hermetic_git_env(home=repo)
    (repo / "plugins" / "dev-team" / "agents" / "some-agent.md").write_text(
        "# Some Agent\n## New\nBody.\n"
    )
    subprocess.run(
        ["git", "add", "plugins/dev-team/agents/some-agent.md"],
        cwd=repo,
        env=env,
        check=True,
    )
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m test"}}, cwd=repo
    )
    assert r.returncode == 0


def test_commit_with_corpus_and_matching_index_passes(repo: Path) -> None:
    env = hermetic_git_env(home=repo)
    (repo / "plugins" / "dev-team" / "knowledge" / "foo.md").write_text(
        "# Foo\n## Section A\nFirst sentence of A.\n## New Section\nBody of new section.\n"
    )
    subprocess.run(
        ["python3", "plugins/dev-team/hooks/lib/build_knowledge_index.py"],
        cwd=repo,
        env=env,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "add",
            "plugins/dev-team/knowledge/foo.md",
            "plugins/dev-team/knowledge/index.json",
        ],
        cwd=repo,
        env=env,
        check=True,
    )
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m 'add section'"}},
        cwd=repo,
    )
    assert r.returncode == 0


def test_commit_with_stale_index_blocks_with_remediation(repo: Path) -> None:
    env = hermetic_git_env(home=repo)
    (repo / "plugins" / "dev-team" / "knowledge" / "foo.md").write_text(
        "# Foo\n## Section A\nFirst sentence of A.\n## New Section\nBody of new section.\n"
    )
    subprocess.run(
        ["git", "add", "plugins/dev-team/knowledge/foo.md"],
        cwd=repo,
        env=env,
        check=True,
    )
    r = _run(
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m 'add section'"}},
        cwd=repo,
    )
    assert r.returncode == 2
    assert "knowledge/index.json is stale" in r.stderr
    assert "python3 plugins/dev-team/hooks/lib/build_knowledge_index.py" in r.stderr
    assert "git add plugins/dev-team/knowledge/index.json" in r.stderr


def test_commit_blocks_when_working_tree_drifts_past_staged_pair(repo: Path) -> None:
    env = hermetic_git_env(home=repo)
    (repo / "plugins" / "dev-team" / "knowledge" / "foo.md").write_text(
        "# Foo\n## Section A\nFirst sentence of A.\n## First\nBody of first.\n"
    )
    subprocess.run(
        ["python3", "plugins/dev-team/hooks/lib/build_knowledge_index.py"],
        cwd=repo,
        env=env,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "add",
            "plugins/dev-team/knowledge/foo.md",
            "plugins/dev-team/knowledge/index.json",
        ],
        cwd=repo,
        env=env,
        check=True,
    )
    # Re-edit the working tree past the staged pair.
    (repo / "plugins" / "dev-team" / "knowledge" / "foo.md").write_text(
        "# Foo\n## Section A\nFirst sentence of A.\n## First\nBody of first.\n"
        "## Second\nBody of second.\n"
    )
    r = _run(
        {
            "tool_name": "Bash",
            "tool_input": {"command": "git commit -m 'add sections'"},
        },
        cwd=repo,
    )
    assert r.returncode == 2
    assert "knowledge/index.json is stale" in r.stderr


def test_malformed_stdin_silent(repo: Path) -> None:
    r = subprocess.run(
        ["python3", str(_HOOK)],
        input="not json",
        env={
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0
    assert r.stderr == ""
