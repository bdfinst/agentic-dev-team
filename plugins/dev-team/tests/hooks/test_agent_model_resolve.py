"""Unit tests for hooks/agent_model_resolve.py (#732).

Covers two independent #732 fixes:
  * dedup fix — agent_model_resolve.py imports hooks/lib/model_resolve.py
    already, so this suite guards against re-introducing local, drifted
    copies of normalize_band/load_json/ladder_is_valid instead of calling
    model_resolve's versions directly.
  * naming cleanup — `_read_effort`'s cryptic `infm` flag (renamed to
    describe what it actually tracks: whether the current line is inside
    the YAML frontmatter block).
"""

from __future__ import annotations

import inspect
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_HOOKS_DIR = _REPO_ROOT / "plugins" / "dev-team" / "hooks"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))
if str(_HOOKS_DIR / "lib") not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR / "lib"))

import agent_model_resolve  # type: ignore[import-not-found]  # noqa: E402
import model_resolve  # type: ignore[import-not-found]  # noqa: E402


# ---------------------------------------------------------------------------
# No local duplicate helpers — must call model_resolve's public versions.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["_normalize_band", "_load_json", "_ladder_is_valid"],
)
def test_no_local_duplicate_helper(name: str) -> None:
    assert not hasattr(agent_model_resolve, name), (
        f"agent_model_resolve.{name} should not exist — call "
        f"model_resolve's public equivalent directly instead of keeping a "
        f"local (and driftable) copy."
    )


def test_snapshot_in_ladder_uses_shared_ladder_validity(
    tmp_path: Path, monkeypatch
) -> None:
    """`_snapshot_in_ladder` must delegate ladder-validity to
    model_resolve.ladder_is_valid so both hooks always agree, even on edge
    cases like a mis-encoded ladder file (must degrade to False, not raise).
    """
    bad_ladder = tmp_path / "ladder.json"
    bad_ladder.write_bytes(b"\xff\xfe\x00\x00invalid")
    monkeypatch.setenv("MODEL_LADDER_JSON", str(bad_ladder))

    assert model_resolve.ladder_is_valid(bad_ladder) is False
    assert agent_model_resolve._snapshot_in_ladder("claude-opus-4-8") is False


def test_snapshot_in_ladder_false_when_ladder_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MODEL_LADDER_JSON", str(tmp_path / "missing.json"))
    assert agent_model_resolve._snapshot_in_ladder("claude-opus-4-8") is False


def test_snapshot_in_ladder_true_when_present(tmp_path, monkeypatch) -> None:
    ladder = tmp_path / "ladder.json"
    ladder.write_text('["a", "b", "c"]', encoding="utf-8")
    monkeypatch.setenv("MODEL_LADDER_JSON", str(ladder))
    assert agent_model_resolve._snapshot_in_ladder("b") is True
    assert agent_model_resolve._snapshot_in_ladder("z") is False


# ---------------------------------------------------------------------------
# _read_effort — frontmatter parsing + naming cleanup
# ---------------------------------------------------------------------------


def test_read_effort_extracts_value_from_frontmatter(tmp_path):
    agent_file = tmp_path / "reviewer.md"
    agent_file.write_text('---\neffort: "medium"\n---\n\n# Reviewer\n')
    assert agent_model_resolve._read_effort(agent_file) == "medium"


def test_read_effort_returns_empty_when_no_frontmatter(tmp_path):
    agent_file = tmp_path / "reviewer.md"
    agent_file.write_text("# Reviewer\n\nNo frontmatter here.\n")
    assert agent_model_resolve._read_effort(agent_file) == ""


def test_read_effort_returns_empty_when_frontmatter_has_no_effort(tmp_path):
    agent_file = tmp_path / "reviewer.md"
    agent_file.write_text("---\nname: reviewer\n---\n")
    assert agent_model_resolve._read_effort(agent_file) == ""


def test_read_effort_returns_empty_for_missing_file(tmp_path):
    assert agent_model_resolve._read_effort(tmp_path / "absent.md") == ""


def test_read_effort_uses_descriptive_frontmatter_flag_name():
    # Low-severity naming finding (#732): the loop's "are we inside the
    # frontmatter block" flag was named `infm`. It should now be named
    # descriptively rather than as a cryptic abbreviation.
    source = inspect.getsource(agent_model_resolve._read_effort)
    assert "infm" not in source
    assert "in_frontmatter" in source


# ---------------------------------------------------------------------------
# #1178 — dispatch tool name coverage + dispatch-layer alias translation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("model_id", "alias"),
    [
        ("claude-haiku-4-5-20251001", "haiku"),
        ("claude-sonnet-4-6", "sonnet"),
        ("claude-opus-4-8", "opus"),
        ("claude-fable-5", "fable"),
        ("haiku", "haiku"),  # already an alias — unchanged
    ],
)
def test_dispatch_alias_translates_model_family(model_id: str, alias: str) -> None:
    assert agent_model_resolve._dispatch_alias(model_id) == alias


def test_dispatch_alias_passes_unknown_ids_through() -> None:
    # Fail-open: a ladder entry with no recognizable family is emitted
    # as-is rather than guessed at.
    assert (
        agent_model_resolve._dispatch_alias("some-custom-model")
        == "some-custom-model"
    )


def _run_hook(payload: dict, env_overrides: dict) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, str(_HOOKS_DIR / "agent_model_resolve.py")],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        env=env,
        check=False,
    )


def _dispatch_env(tmp_path: Path) -> dict:
    """Isolated path seams: one high-effort agent, the shipped default map,
    no ladder, no session model."""
    agents = tmp_path / "agents"
    agents.mkdir()
    (agents / "correctness-review.md").write_text(
        "---\neffort: high\n---\n", encoding="utf-8"
    )
    routing = tmp_path / "model-routing.json"
    routing.write_text(
        '{"low": "claude-haiku-4-5-20251001", "medium": "claude-sonnet-4-6", '
        '"high": "claude-opus-4-8"}',
        encoding="utf-8",
    )
    return {
        "MODEL_AGENTS_DIR": str(agents),
        "MODEL_ROUTING_JSON": str(routing),
        "MODEL_LADDER_JSON": str(tmp_path / "no-ladder.json"),
        "SESSION_MODEL_FILE": str(tmp_path / "no-session-model"),
        "MODEL_BUMP_LOG": str(tmp_path / "bump.log"),
    }


@pytest.mark.parametrize("tool_name", ["Agent", "Task"])
def test_rewrite_fires_for_both_dispatch_tool_names(
    tmp_path: Path, tool_name: str
) -> None:
    """#1178: the subagent-dispatch tool is "Task" before Claude Code 2.1.63
    and "Agent" after — the hook must rewrite under either payload name."""
    result = _run_hook(
        {
            "session_id": "s1",
            "tool_name": tool_name,
            "tool_input": {"subagent_type": "dev-team:correctness-review"},
        },
        _dispatch_env(tmp_path),
    )
    assert result.returncode == 0
    envelope = json.loads(result.stdout)
    updated = envelope["hookSpecificOutput"]["updatedInput"]
    # #1178 alias bug: the Agent/Task tool's `model` parameter silently
    # ignores full snapshot IDs — the rewrite must carry the alias.
    assert updated["model"] == "opus"


def test_non_dispatch_tool_names_pass_through_silently(tmp_path: Path) -> None:
    result = _run_hook(
        {
            "session_id": "s1",
            "tool_name": "Bash",
            "tool_input": {"command": "true"},
        },
        _dispatch_env(tmp_path),
    )
    assert result.returncode == 0
    assert result.stdout == b""
