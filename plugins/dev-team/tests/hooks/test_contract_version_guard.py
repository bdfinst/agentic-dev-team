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

import contract_version_guard as hook  # type: ignore[import-not-found]
from hermetic import hermetic_git_env  # type: ignore[import-not-found]

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
    target_lib = target_hooks / "lib"
    target_lib.mkdir(parents=True, exist_ok=True)
    # boundary_events.py's sibling module imports (artifact_paths,
    # atomic_state (#1874, append-lock fix)) must be copied alongside it or
    # the subprocess's import fails with ModuleNotFoundError. One loop over
    # the dependency list, rather than a copy-pasted block per module, so
    # the next new import boundary_events.py picks up needs only a new
    # entry here, not a new block (test-smell review, #1874).
    for _module_name in (
        "boundary_events.py",
        "artifact_paths.py",
        "atomic_state.py",
        "plugin_version.py",
        "stdin_json.py",
    ):
        target_module = target_lib / _module_name
        if not target_module.exists():
            target_module.write_bytes((_HOOKS_DIR / "lib" / _module_name).read_bytes())
    # The plugin manifest path is resolved relative to hooks/lib/, i.e.
    # hooks/../.claude-plugin/plugin.json — create a minimal one so
    # emit_boundary_event's version lookup doesn't hit a missing-file path
    # (harmless either way since it's fail-open, but keeps behavior tidy).
    manifest_dir = repo_root / "plugins" / "dev-team" / ".claude-plugin"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / "plugin.json"
    if not manifest_path.exists():
        manifest_path.write_text('{"version": "0.0.0-test"}')
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


# ---------------------------------------------------------------------------
# #1354 mutant-kill pass: exact operator-message text, _normalize_path,
# _log_bypass audit line, the "path"-key fallback, and the previously
# untested Edit-tool end-to-end path. Substring assertions passed against
# XX-wrapped string mutants, so these assert the FULL messages / that no XX
# marker leaks.
# ---------------------------------------------------------------------------


_CONTRACT = "plugins/dev-team/knowledge/security-primitives-contract.md"


def test_msg_initial_add_is_exact() -> None:
    assert hook._msg_initial_add() == (
        f"contract-version-guard: initial add of {_CONTRACT} must "
        "include a 'version:' field in frontmatter."
    )


def test_msg_removed_version_is_exact() -> None:
    assert hook._msg_removed_version() == (
        "contract-version-guard: proposed edit removes or blanks the "
        "'version:' field. The contract MUST carry a semver version string."
    )


def test_msg_missing_bump_is_exact() -> None:
    expected = (
        f"contract-version-guard: edit to {_CONTRACT} changes the body "
        "without bumping 'version:'.\n"
        "\n"
        "  current HEAD version: 1.2.3\n"
        "  proposed version:     1.2.3\n"
        "\n"
        "Per the contract's semver policy:\n"
        "  - PATCH (1.2.3 → next) for typos / clarifications / doc polish\n"
        "  - MINOR (e.g. 1.x → 1.(x+1)) for additive changes (new optional "
        "fields, new enum values, new agent/skill IDs)\n"
        "  - MAJOR (e.g. 1.y → 2.0.0) for breaking changes (renamed/removed "
        "fields, new required fields)\n"
        "\n"
        "Bump the version to match your change, then retry the edit."
    )
    assert hook._msg_missing_bump("1.2.3", "1.2.3") == expected
    assert "XX" not in expected  # guard against a copy-paste regression here


def test_msg_missing_bump_shows_none_for_blank_head_version() -> None:
    msg = hook._msg_missing_bump("", "1.0.0")
    assert "current HEAD version: <none>" in msg
    assert "current HEAD version: None" not in msg


def test_normalize_path_strips_repo_root_prefix() -> None:
    absolute = str(hook._REPO_ROOT) + "/" + _CONTRACT
    assert hook._normalize_path(absolute) == _CONTRACT


def test_normalize_path_passes_relative_through() -> None:
    assert hook._normalize_path("some/relative/path.md") == "some/relative/path.md"


def test_log_bypass_writes_expected_audit_fields(monkeypatch, tmp_path: Path) -> None:
    audit = tmp_path / "audit.jsonl"
    monkeypatch.setattr(hook, "_AUDIT_LOG", audit)
    monkeypatch.setenv("GITHUB_ACTOR", "release-please[bot]")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "rp@example.com")
    hook._log_bypass("release-please-actor")
    line = audit.read_text(encoding="utf-8").strip()
    record = json.loads(line)  # must be valid JSON (kills f-string segment mutants)
    assert record["bypass"] is True
    assert record["reason"] == "release-please-actor"
    assert record["github_actor"] == "release-please[bot]"
    assert record["git_email"] == "rp@example.com"
    # ts is a real UTC timestamp, not None and not an XX-wrapped format string.
    assert record["ts"].endswith("Z")
    assert record["ts"][0].isdigit()
    assert record["ts"] != "None"


def test_log_bypass_env_defaults_are_empty(monkeypatch, tmp_path: Path) -> None:
    audit = tmp_path / "audit.jsonl"
    monkeypatch.setattr(hook, "_AUDIT_LOG", audit)
    monkeypatch.delenv("GITHUB_ACTOR", raising=False)
    monkeypatch.delenv("GIT_AUTHOR_EMAIL", raising=False)
    hook._log_bypass("some-reason")
    record = json.loads(audit.read_text(encoding="utf-8").strip())
    assert record["github_actor"] == ""
    assert record["git_email"] == ""


def test_block_uses_path_key_when_file_path_absent(tmp_path: Path) -> None:
    """The `path` key is the fallback for `file_path`; a body-changing Write
    routed through it must still be blocked."""
    _init_hermetic_repo(tmp_path, "---\nversion: 1.0.0\n---\n# Original body\n")
    stdin = json.dumps(
        {
            "tool_name": "Write",
            "tool_input": {
                "path": _CONTRACT,
                "content": "---\nversion: 1.0.0\n---\n# Changed body\n",
            },
        }
    )
    result = _run_hook_from(tmp_path, stdin)
    assert result.returncode == 2
    assert b"changes the body without bumping" in result.stderr


def test_block_write_stderr_has_no_leaked_mutation_marker(tmp_path: Path) -> None:
    _init_hermetic_repo(tmp_path, "---\nversion: 1.0.0\n---\n# Original body\n")
    stdin = json.dumps(
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": _CONTRACT,
                "content": "---\nversion: 1.0.0\n---\n# Changed body\n",
            },
        }
    )
    result = _run_hook_from(tmp_path, stdin)
    assert result.returncode == 2
    assert b"XX" not in result.stderr


def test_edit_body_change_without_bump_is_blocked(tmp_path: Path) -> None:
    """The Edit tool path had no end-to-end coverage. An Edit that rewrites a
    body line without bumping the version must block (exit 2)."""
    _init_hermetic_repo(tmp_path, "---\nversion: 1.0.0\n---\n# Original body\n")
    stdin = json.dumps(
        {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": _CONTRACT,
                "old_string": "# Original body",
                "new_string": "# Changed body",
            },
        }
    )
    result = _run_hook_from(tmp_path, stdin)
    assert result.returncode == 2
    assert b"changes the body without bumping" in result.stderr
    assert b"XX" not in result.stderr


def test_edit_with_empty_old_string_is_conservatively_allowed(tmp_path: Path) -> None:
    """An Edit with an empty old_string is the 'unusual edit' branch and must
    pass through with exit 0 rather than block."""
    _init_hermetic_repo(tmp_path, "---\nversion: 1.0.0\n---\n# Original body\n")
    stdin = json.dumps(
        {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": _CONTRACT,
                "old_string": "",
                "new_string": "# injected",
            },
        }
    )
    result = _run_hook_from(tmp_path, stdin)
    assert result.returncode == 0
    assert result.stderr == b""


def test_edit_frontmatter_only_change_is_allowed(tmp_path: Path) -> None:
    """An Edit that only touches frontmatter (body digest unchanged) passes."""
    _init_hermetic_repo(tmp_path, "---\nversion: 1.0.0\n---\n# Body\n")
    stdin = json.dumps(
        {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": _CONTRACT,
                "old_string": "version: 1.0.0",
                "new_string": "version: 1.0.0\nextra-key: v",
            },
        }
    )
    result = _run_hook_from(tmp_path, stdin)
    assert result.returncode == 0
    assert result.stderr == b""
