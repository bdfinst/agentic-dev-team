"""hooks/lib/model_resolve.py's resolve_band() used to parse the ladder JSON
file twice per call: once inside _ladder_is_valid() to validate it, and
again immediately after to actually use it. These tests lock resolve_band's
existing behavior and then assert the ladder file is only read/parsed once.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LIB_DIR = REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"
sys.path.insert(0, str(LIB_DIR))

import model_resolve  # noqa: E402


@pytest.fixture
def routing_path(tmp_path: Path) -> Path:
    p = tmp_path / "model-routing.json"
    p.write_text(
        json.dumps(
            {"low": "haiku-default", "medium": "sonnet-default", "high": "opus-default"}
        )
    )
    return p


@pytest.fixture
def ladder_path(tmp_path: Path) -> Path:
    p = tmp_path / "model-ladder.json"
    p.write_text(json.dumps(["model-a", "model-b", "model-c"]))
    return p


def test_resolve_band_uses_the_ladder_when_valid(
    routing_path: Path, ladder_path: Path
) -> None:
    # 3-entry ladder: low->index 0, medium->index 1, high->index 2.
    assert model_resolve.resolve_band("low", routing_path, ladder_path) == "model-a"
    assert model_resolve.resolve_band("medium", routing_path, ladder_path) == "model-b"
    assert model_resolve.resolve_band("high", routing_path, ladder_path) == "model-c"


def test_resolve_band_falls_back_to_default_map_without_a_valid_ladder(
    tmp_path: Path, routing_path: Path
) -> None:
    missing_ladder = tmp_path / "no-such-ladder.json"
    assert (
        model_resolve.resolve_band("medium", routing_path, missing_ladder)
        == "sonnet-default"
    )


def test_resolve_band_reads_the_ladder_file_at_most_once(
    routing_path: Path, ladder_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[Path] = []
    real_load_json = model_resolve.load_json

    def counting_load_json(path: Path):
        calls.append(path)
        return real_load_json(path)

    monkeypatch.setattr(model_resolve, "load_json", counting_load_json)

    model_resolve.resolve_band("medium", routing_path, ladder_path)

    ladder_reads = [c for c in calls if c == ladder_path]
    assert len(ladder_reads) == 1, (
        f"expected the ladder file to be parsed exactly once, got {len(ladder_reads)}"
    )
