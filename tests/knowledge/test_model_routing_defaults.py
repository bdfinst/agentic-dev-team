"""Tests for plugins/dev-team/knowledge/model-routing.json — the single
source of truth for effort band → model resolution defaults.

(precondition): the routing.json file is the ONLY in-tree place that ships
a concrete model ID, and it pins the ladder rounding convention. Every value
is a bare canonical model ID (no dated snapshot suffix) — see ADR 0024. Every
dispatch flows through it. The legacy tier keys (haiku/sonnet/opus) were
dropped: the resolver normalizes those tokens to bands (low/medium/high) in
model_resolve.normalize_band() *before* the JSON lookup, so the alias keys
were dead — never dereferenced.

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


def test_model_routing_json_contains_only_bands_and_rounding(data: dict) -> None:
    assert sorted(data.keys()) == [
        "high",
        "low",
        "medium",
        "rounding",
    ]


# --- Effort band defaults (the post-migration vocabulary) ------------------


def test_low_band_maps_to_unpinned_canonical_haiku_id(data: dict) -> None:
    assert data["low"] == "claude-haiku-4-5"


def test_medium_band_maps_to_unpinned_canonical_sonnet_id(data: dict) -> None:
    assert data["medium"] == "claude-sonnet-5"


def test_high_band_maps_to_unpinned_canonical_opus_id(data: dict) -> None:
    assert data["high"] == "claude-opus-4-8"


# --- legacy tier keys are gone --------------------------------------------


def test_legacy_tier_alias_keys_are_dropped(data: dict) -> None:
    for alias in ("haiku", "sonnet", "opus"):
        assert alias not in data


# --- ladder rounding convention is pinned -----------------------------


def test_rounding_convention_is_pinned_to_round_half_up(data: dict) -> None:
    assert data["rounding"] == "round_half_up"


# --- No band resolves to null ----------------------------------------------


def test_no_band_resolves_to_null(data: dict) -> None:
    for key in ("low", "medium", "high"):
        assert data[key] is not None
        assert isinstance(data[key], str)
