"""Unit tests for the Python port of hooks/contract-version-guard.sh (#596).

White-box tests on the port's helpers + end-to-end subprocess dispatch
against a hermetic git repo. Byte-parity with the .sh is enforced separately
by the parity harness.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


_HOOKS_DIR = Path(__file__).resolve().parents[2] / "hooks"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

_TESTS_LIB = Path(__file__).resolve().parents[2] / "tests" / "lib"
if str(_TESTS_LIB) not in sys.path:
    sys.path.insert(0, str(_TESTS_LIB))

import contract_version_guard as hook  # type: ignore[import-not-found]  # noqa: E402
from hermetic import hermetic_git_env  # type: ignore[import-not-found]  # noqa: E402


# ---------------------------------------------------------------------------
# extract_version
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("---\nversion: 1.2.3\n---\nbody\n", "1.2.3"),
        ("---\nversion: '1.2.3'\n---\nbody\n", "1.2.3"),
        ('---\nversion: "1.2.3"\n---\nbody\n', "1.2.3"),
        ("---\nversion:  1.0.0  \n---\n", "1.0.0"),
        ("---\nname: x\n---\n", ""),
        ("body only\n", ""),
        ("", ""),
        # version outside the first --- block should not match
        ("---\nname: x\n---\nversion: 9.9.9\n", ""),
        # multi-line frontmatter with other keys
        ("---\nkey: v\nversion: 2.0.0\nname: x\n---\n", "2.0.0"),
    ],
)
def test_extract_version(text: str, expected: str) -> None:
    assert hook._extract_version(text) == expected


# ---------------------------------------------------------------------------
# body_digest
# ---------------------------------------------------------------------------


def test_body_digest_strips_frontmatter() -> None:
    text = "---\nversion: 1.0.0\n---\nHello\nWorld\n"
    assert hook._body_digest(text) == "Hello World "


def test_body_digest_collapses_whitespace() -> None:
    text = "---\nversion: 1.0.0\n---\n  hello   \n\n  world\n"
    assert hook._body_digest(text) == " hello world "


def test_body_digest_empty_body() -> None:
    text = "---\nversion: 1.0.0\n---\n"
    assert hook._body_digest(text) == ""


def test_body_digest_no_frontmatter() -> None:
    # No `---` markers → in_body never becomes True → empty body.
    text = "just some text\nwith no frontmatter\n"
    assert hook._body_digest(text) == ""


# ---------------------------------------------------------------------------
# release-please detection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "env_var",
    ["GITHUB_ACTOR", "GIT_AUTHOR_EMAIL", "GIT_AUTHOR_NAME"],
)
def test_is_release_please_true_when_var_contains_marker(
    monkeypatch,
    env_var: str,
) -> None:
    for v in ("GITHUB_ACTOR", "GIT_AUTHOR_EMAIL", "GIT_AUTHOR_NAME"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv(env_var, "release-please[bot]")
    assert hook._is_release_please() is True


def test_is_release_please_false_when_no_var_matches(monkeypatch) -> None:
    for v in ("GITHUB_ACTOR", "GIT_AUTHOR_EMAIL", "GIT_AUTHOR_NAME"):
        monkeypatch.setenv(v, "regular-user")
    assert hook._is_release_please() is False


# ---------------------------------------------------------------------------
# apply_edit_first_line
# ---------------------------------------------------------------------------


def test_apply_edit_first_line_replaces_first_occurrence_only() -> None:
    head = "foo bar\nfoo baz\nfoo qux\n"
    out = hook._apply_edit_first_line(head, "foo", "FOO")
    assert out == "FOO bar\nfoo baz\nfoo qux\n"


def test_apply_edit_first_line_no_match_returns_unchanged() -> None:
    head = "hello world\n"
    out = hook._apply_edit_first_line(head, "xyz", "ABC")
    assert out == "hello world\n"


# ---------------------------------------------------------------------------
# End-to-end subprocess tests via a hermetic git repo
# ---------------------------------------------------------------------------


def _init_hermetic_repo(root: Path, contract_content: str) -> None:
    """Create a git repo at `root` and commit the contract file at HEAD.

    This mirrors the .sh's assumption that the contract lives at
    plugins/dev-team/knowledge/security-primitives-contract.md relative to
    repo root.
    """
    env = hermetic_git_env(home=root)
    subprocess.run(
        ["git", "init", "--quiet", "-b", "main"],
        cwd=root,
        env=env,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "t@t"],
        cwd=root,
        env=env,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "t"],
        cwd=root,
        env=env,
        check=True,
        capture_output=True,
    )
    contract_dir = root / "plugins" / "dev-team" / "knowledge"
    contract_dir.mkdir(parents=True, exist_ok=True)
    (contract_dir / "security-primitives-contract.md").write_text(contract_content)
    subprocess.run(
        ["git", "add", "-A"], cwd=root, env=env, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "--quiet", "-m", "init"],
        cwd=root,
        env=env,
        check=True,
        capture_output=True,
    )


def _run_hook_from(
    repo_root: Path, stdin: str, env_extras: dict | None = None
) -> subprocess.CompletedProcess:
    """Run the hook AS IF it lived at repo_root/plugins/dev-team/hooks/.

    The hook resolves REPO_ROOT from its own path, so we symlink (or copy)
    the .py into the hermetic repo's plugins/dev-team/hooks/ directory.
    """
    target_hooks = repo_root / "plugins" / "dev-team" / "hooks"
    target_hooks.mkdir(parents=True, exist_ok=True)
    target_py = target_hooks / "contract_version_guard.py"
    if not target_py.exists():
        target_py.write_bytes((_HOOKS_DIR / "contract_version_guard.py").read_bytes())
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(repo_root),
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
    }
    if env_extras:
        env.update(env_extras)
    return subprocess.run(
        [sys.executable, str(target_py)],
        input=stdin.encode("utf-8"),
        capture_output=True,
        cwd=str(repo_root),
        env=env,
        check=False,
    )


def test_block_write_removing_version(tmp_path: Path) -> None:
    _init_hermetic_repo(tmp_path, "---\nversion: 1.0.0\n---\n# Contract body\n")
    stdin = json.dumps(
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "plugins/dev-team/knowledge/security-primitives-contract.md",
                "content": "---\nno-version: yep\n---\n# Contract body\n",
            },
        }
    )
    result = _run_hook_from(tmp_path, stdin)
    assert result.returncode == 2
    assert b"'version:'" in result.stderr


def test_block_body_change_without_version_bump(tmp_path: Path) -> None:
    _init_hermetic_repo(tmp_path, "---\nversion: 1.0.0\n---\n# Original body\n")
    stdin = json.dumps(
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "plugins/dev-team/knowledge/security-primitives-contract.md",
                "content": "---\nversion: 1.0.0\n---\n# Changed body\n",
            },
        }
    )
    result = _run_hook_from(tmp_path, stdin)
    assert result.returncode == 2
    assert b"changes the body without bumping" in result.stderr


def test_allow_body_change_with_version_bump(tmp_path: Path) -> None:
    _init_hermetic_repo(tmp_path, "---\nversion: 1.0.0\n---\n# Original body\n")
    stdin = json.dumps(
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "plugins/dev-team/knowledge/security-primitives-contract.md",
                "content": "---\nversion: 1.1.0\n---\n# Changed body\n",
            },
        }
    )
    result = _run_hook_from(tmp_path, stdin)
    assert result.returncode == 0
    assert result.stderr == b""


def test_allow_frontmatter_only_change(tmp_path: Path) -> None:
    _init_hermetic_repo(tmp_path, "---\nversion: 1.0.0\n---\n# Unchanged body\n")
    stdin = json.dumps(
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "plugins/dev-team/knowledge/security-primitives-contract.md",
                "content": "---\nversion: 1.0.0\nnew-key: v\n---\n# Unchanged body\n",
            },
        }
    )
    result = _run_hook_from(tmp_path, stdin)
    assert result.returncode == 0


def test_release_please_bypass_lets_missing_version_through(
    tmp_path: Path,
) -> None:
    _init_hermetic_repo(tmp_path, "---\nversion: 1.0.0\n---\n# Body\n")
    stdin = json.dumps(
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "plugins/dev-team/knowledge/security-primitives-contract.md",
                "content": "no version at all",
            },
        }
    )
    result = _run_hook_from(
        tmp_path,
        stdin,
        env_extras={
            "GITHUB_ACTOR": "release-please[bot]",
        },
    )
    assert result.returncode == 0


def test_non_contract_file_pass(tmp_path: Path) -> None:
    _init_hermetic_repo(tmp_path, "---\nversion: 1.0.0\n---\n# Body\n")
    stdin = json.dumps(
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "some/other/file.md",
                "content": "hello",
            },
        }
    )
    result = _run_hook_from(tmp_path, stdin)
    assert result.returncode == 0
    assert result.stderr == b""


def test_initial_add_without_version_blocks(tmp_path: Path) -> None:
    # Hermetic repo does NOT commit the contract → HEAD_CONTENT is empty.
    env = hermetic_git_env(home=tmp_path)
    subprocess.run(
        ["git", "init", "--quiet", "-b", "main"],
        cwd=tmp_path,
        env=env,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "t@t"],
        cwd=tmp_path,
        env=env,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "t"],
        cwd=tmp_path,
        env=env,
        check=True,
        capture_output=True,
    )
    (tmp_path / "sentinel").write_text("")
    subprocess.run(
        ["git", "add", "-A"], cwd=tmp_path, env=env, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "--quiet", "-m", "init"],
        cwd=tmp_path,
        env=env,
        check=True,
        capture_output=True,
    )
    stdin = json.dumps(
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "plugins/dev-team/knowledge/security-primitives-contract.md",
                "content": "no version anywhere",
            },
        }
    )
    result = _run_hook_from(tmp_path, stdin)
    assert result.returncode == 2
    assert b"initial add" in result.stderr


def test_initial_add_with_version_passes(tmp_path: Path) -> None:
    env = hermetic_git_env(home=tmp_path)
    subprocess.run(
        ["git", "init", "--quiet", "-b", "main"],
        cwd=tmp_path,
        env=env,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "t@t"],
        cwd=tmp_path,
        env=env,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "t"],
        cwd=tmp_path,
        env=env,
        check=True,
        capture_output=True,
    )
    (tmp_path / "sentinel").write_text("")
    subprocess.run(
        ["git", "add", "-A"], cwd=tmp_path, env=env, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "--quiet", "-m", "init"],
        cwd=tmp_path,
        env=env,
        check=True,
        capture_output=True,
    )
    stdin = json.dumps(
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "plugins/dev-team/knowledge/security-primitives-contract.md",
                "content": "---\nversion: 0.1.0\n---\nnew contract",
            },
        }
    )
    result = _run_hook_from(tmp_path, stdin)
    assert result.returncode == 0


def test_empty_stdin_pass(tmp_path: Path) -> None:
    _init_hermetic_repo(tmp_path, "---\nversion: 1.0.0\n---\n# Body\n")
    result = _run_hook_from(tmp_path, "")
    assert result.returncode == 0
    assert result.stderr == b""


def test_malformed_stdin_pass(tmp_path: Path) -> None:
    _init_hermetic_repo(tmp_path, "---\nversion: 1.0.0\n---\n# Body\n")
    result = _run_hook_from(tmp_path, "not { valid ] json")
    assert result.returncode == 0
    assert result.stderr == b""
