"""Tests for plugins/dev-team/knowledge/model-routing.json — the single
source of truth for effort band → model resolution defaults.

(precondition): the routing.json file is the ONLY in-tree place that ships
a concrete model ID, and it pins the ladder rounding convention. Each band
value is a concrete model ID for the right family; per ADR 0025 it may be a
bare canonical ID OR a dated snapshot (the map is deliberately mixed-shape,
since the staleness bot pins whatever the Models API returns), so these tests
assert the family NAME (tier word, version digits stripped) — not an exact
version. The legacy tier keys (haiku/sonnet/opus) were dropped: the resolver
normalizes those tokens to bands (low/medium/high) in
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


# --- Effort band families (version-agnostic — see ADR 0025) ----------------


def _family(model_id: str) -> str:
    """The tier word of a model ID with `claude-` and all version digits removed.

    `claude-opus-4-8` -> `opus`; `claude-haiku-4-5-20251001` -> `haiku`. This
    is what lets the assertions below tolerate any version (bare or dated).
    """
    return "-".join(
        tok
        for tok in model_id.split("-")
        if tok != "claude" and tok and not tok.isdigit()
    )


@pytest.mark.parametrize(
    "band,family",
    [("low", "haiku"), ("medium", "sonnet"), ("high", "opus")],
)
def test_band_resolves_to_expected_family(data: dict, band: str, family: str) -> None:
    value = data[band]
    assert value.startswith("claude-")
    assert _family(value) == family


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
