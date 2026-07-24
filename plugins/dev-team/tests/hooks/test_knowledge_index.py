"""Unit tests for hooks/knowledge_index.py (#580).

Mirror of tests/hooks/knowledge_index_hook_tests.bats. The PostToolUse
hook rebuilds knowledge/index.json when an Edit|Write touches a corpus
path. Builder invocation is injected via KNOWLEDGE_INDEX_BUILDER (the
test-only seam) so no real indexing runs.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_HOOK = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "knowledge_index.py"


@pytest.fixture
def sentinel_builder(tmp_path: Path) -> tuple[Path, Path]:
    """Fake builder that touches a sentinel; FAKE_BUILDER_MODE=fail forces exit 1."""
    sentinel = tmp_path / "builder-invoked.sentinel"
    builder = tmp_path / "fake-builder.sh"
    builder.write_text(
        "#!/usr/bin/env bash\n"
        f'touch "{sentinel}"\n'
        'if [[ "${FAKE_BUILDER_MODE:-ok}" = "fail" ]]; then\n'
        '  echo "boom" >&2\n'
        "  exit 1\n"
        "fi\n"
        "exit 0\n"
    )
    builder.chmod(0o755)
    return builder, sentinel


def _run(
    payload: dict,
    builder: Path,
    extra_env: dict | None = None,
) -> subprocess.CompletedProcess[str]:
    proc_env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "KNOWLEDGE_INDEX_BUILDER": str(builder),
        **(extra_env or {}),
    }
    return subprocess.run(
        ["python3", str(_HOOK)],
        input=json.dumps(payload),
        env=proc_env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_edit_on_knowledge_md_triggers_builder(sentinel_builder) -> None:
    builder, sentinel = sentinel_builder
    r = _run(
        {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "plugins/dev-team/knowledge/owasp-detection.md"
            },
        },
        builder,
    )
    assert r.returncode == 0
    assert sentinel.exists()
    assert "[knowledge-index] rebuilt" in r.stderr


def test_edit_on_skill_md_triggers_builder(sentinel_builder) -> None:
    builder, sentinel = sentinel_builder
    r = _run(
        {
            "tool_name": "Edit",
            "tool_input": {"file_path": "plugins/dev-team/skills/specs/SKILL.md"},
        },
        builder,
    )
    assert r.returncode == 0
    assert sentinel.exists()


def test_write_on_corpus_file_triggers_builder(sentinel_builder) -> None:
    builder, sentinel = sentinel_builder
    r = _run(
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "plugins/dev-team/knowledge/owasp-detection.md"
            },
        },
        builder,
    )
    assert r.returncode == 0
    assert sentinel.exists()


def test_edit_on_non_corpus_does_not_trigger(sentinel_builder) -> None:
    builder, sentinel = sentinel_builder
    r = _run(
        {"tool_name": "Edit", "tool_input": {"file_path": "README.md"}},
        builder,
    )
    assert r.returncode == 0
    assert not sentinel.exists()
    assert r.stderr == ""


def test_edit_on_schemas_subdir_does_not_trigger(sentinel_builder) -> None:
    builder, sentinel = sentinel_builder
    r = _run(
        {
            "tool_name": "Edit",
            "tool_input": {"file_path": "plugins/dev-team/knowledge/schemas/foo.md"},
        },
        builder,
    )
    assert r.returncode == 0
    assert not sentinel.exists()


def test_edit_on_agent_file_does_not_trigger(sentinel_builder) -> None:
    builder, sentinel = sentinel_builder
    r = _run(
        {
            "tool_name": "Edit",
            "tool_input": {"file_path": "plugins/dev-team/agents/security-review.md"},
        },
        builder,
    )
    assert r.returncode == 0
    assert not sentinel.exists()


def test_non_edit_write_tools_silent(sentinel_builder) -> None:
    builder, sentinel = sentinel_builder
    for tool in ["Bash", "Read", "Grep", "Glob"]:
        r = _run(
            {
                "tool_name": tool,
                "tool_input": {
                    "file_path": "plugins/dev-team/knowledge/owasp-detection.md"
                },
            },
            builder,
        )
        assert r.returncode == 0
        assert not sentinel.exists()


def test_builder_failure_still_exits_zero(sentinel_builder) -> None:
    builder, sentinel = sentinel_builder
    r = _run(
        {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "plugins/dev-team/knowledge/owasp-detection.md"
            },
        },
        builder,
        extra_env={"FAKE_BUILDER_MODE": "fail"},
    )
    assert r.returncode == 0
    assert sentinel.exists()
    assert "[knowledge-index] rebuild failed" in r.stderr
    assert "boom" in r.stderr


def test_malformed_stdin_fails_open(sentinel_builder) -> None:
    builder, sentinel = sentinel_builder
    r = subprocess.run(
        ["python3", str(_HOOK)],
        input="not json",
        env={
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "KNOWLEDGE_INDEX_BUILDER": str(builder),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0
    assert not sentinel.exists()


def test_empty_stdin_fails_open(sentinel_builder) -> None:
    builder, sentinel = sentinel_builder
    r = subprocess.run(
        ["python3", str(_HOOK)],
        input="",
        env={
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "KNOWLEDGE_INDEX_BUILDER": str(builder),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0
    assert not sentinel.exists()


def test_missing_file_path_silent(sentinel_builder) -> None:
    builder, sentinel = sentinel_builder
    r = _run({"tool_name": "Edit", "tool_input": {}}, builder)
    assert r.returncode == 0
    assert not sentinel.exists()
