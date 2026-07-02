"""Unit tests for hooks/agent_model_resolve.py (#732 dedup fix).

agent_model_resolve.py imports hooks/lib/model_resolve.py already — this
suite guards against re-introducing local, drifted copies of
normalize_band/load_json/ladder_is_valid instead of calling model_resolve's
versions directly.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_HOOKS_DIR = _REPO_ROOT / "plugins" / "dev-team" / "hooks"
sys.path.insert(0, str(_HOOKS_DIR))
sys.path.insert(0, str(_HOOKS_DIR / "lib"))

import agent_model_resolve  # noqa: E402
import model_resolve  # noqa: E402


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
