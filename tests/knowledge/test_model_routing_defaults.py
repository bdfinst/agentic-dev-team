"""Tests for plugins/dev-team/knowledge/model-routing.json — the single
source of truth for effort band → snapshot resolution defaults.

(migration safety): each band default must equal the legacy tier it
replaces, snapshot-for-snapshot (low→haiku, medium→sonnet, high→opus).
(precondition): the routing.json file is the ONLY in-tree place that ships
a pinned snapshot ID, and it pins the ladder rounding convention. Every
dispatch flows through it. Legacy tier keys are retained for the
migration window so the unchanged resolver keeps resolving.

Ported from tests/knowledge/model_routing_defaults.bats (issue #675:
bats -> pytest).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTING_JSON = REPO_ROOT / "plugins" / "dev-team" / "knowledge" / "model-routing.json"


@pytest.fixture(scope="module")
def data() -> dict:
    return json.loads(ROUTING_JSON.read_text(encoding="utf-8"))


def test_model_routing_json_exists() -> None:
    assert ROUTING_JSON.is_file()


def test_model_routing_json_is_valid_json() -> None:
    json.loads(ROUTING_JSON.read_text(encoding="utf-8"))


def test_model_routing_json_contains_bands_and_legacy_tiers(data: dict) -> None:
    assert sorted(data.keys()) == [
        "haiku",
        "high",
        "low",
        "medium",
        "opus",
        "rounding",
        "sonnet",
    ]


# --- Effort band defaults (the post-migration vocabulary) ------------------


def test_low_band_maps_to_documented_haiku_snapshot(data: dict) -> None:
    assert data["low"] == "claude-haiku-4-5-20251001"


def test_medium_band_maps_to_unpinned_canonical_sonnet_id(data: dict) -> None:
    assert data["medium"] == "claude-sonnet-4-6"


def test_high_band_maps_to_unpinned_canonical_opus_id(data: dict) -> None:
    assert data["high"] == "claude-opus-4-8"


# --- bands equal the legacy tiers they replace, snapshot-for-snapshot ------


def test_each_band_default_equals_its_legacy_tier_snapshot(data: dict) -> None:
    assert data["low"] == data["haiku"]
    assert data["medium"] == data["sonnet"]
    assert data["high"] == data["opus"]


# --- legacy tier keys retained for the migration window --------------------


def test_haiku_tier_maps_to_documented_snapshot(data: dict) -> None:
    assert data["haiku"] == "claude-haiku-4-5-20251001"


def test_sonnet_tier_maps_to_unpinned_canonical_id(data: dict) -> None:
    assert data["sonnet"] == "claude-sonnet-4-6"


def test_opus_tier_maps_to_unpinned_canonical_id(data: dict) -> None:
    assert data["opus"] == "claude-opus-4-8"


# --- ladder rounding convention is pinned -----------------------------


def test_rounding_convention_is_pinned_to_round_half_up(data: dict) -> None:
    assert data["rounding"] == "round_half_up"


# --- No band or tier resolves to null --------------------------------------


def test_no_band_or_tier_resolves_to_null(data: dict) -> None:
    for key in ("low", "medium", "high", "haiku", "sonnet", "opus"):
        assert data[key] is not None
        assert isinstance(data[key], str)
