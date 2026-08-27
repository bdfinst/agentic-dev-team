"""Unit tests for hooks/lib/pricing.py (#2045, epic #2040).

Extracted from hooks/lib/cost_meter.py's and the maintainer extractor's
(now session_report.py --profile maintainer) own, previously independent
`_load_pricing`/`_rate`/`_cost` copies. Pins
both the unified (defensive) behavior and the two divergences that existed
between the two originals before unification:
  * cost_meter's `_load_pricing` raised on a missing/unreadable file;
    session_extract's degraded to `{}`. Unified on the defensive form.
  * cost_meter's `_cost` required its caller to guard `if rate else 0.0`;
    session_extract's guarded internally. Unified on the internal guard.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from _repo_root import REPO_ROOT as _REPO_ROOT

_PLUGIN_DIR = _REPO_ROOT / "plugins" / "dev-team"
_LIB_DIR = _PLUGIN_DIR / "hooks" / "lib"

if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import pricing  # type: ignore[import-not-found]

_PRICING = {
    "cache_write_multiplier": 1.25,
    "cache_read_multiplier": 0.1,
    "models": {
        "claude-x": {"input": 3.0, "output": 15.0},
    },
    "aliases": {"x": "claude-x"},
}


# ---------------------------------------------------------------------------
# load_pricing()
# ---------------------------------------------------------------------------


def test_load_pricing_reads_a_valid_file(tmp_path: Path) -> None:
    p = tmp_path / "model-pricing.json"
    p.write_text(json.dumps(_PRICING))
    assert pricing.load_pricing(p) == _PRICING


def test_load_pricing_returns_empty_dict_for_none_path() -> None:
    assert pricing.load_pricing(None) == {}


def test_load_pricing_returns_empty_dict_for_missing_file(tmp_path: Path) -> None:
    assert pricing.load_pricing(tmp_path / "does-not-exist.json") == {}


def test_load_pricing_returns_empty_dict_for_malformed_json(tmp_path: Path) -> None:
    p = tmp_path / "broken.json"
    p.write_text("{not valid json")
    assert pricing.load_pricing(p) == {}


# ---------------------------------------------------------------------------
# rate()
# ---------------------------------------------------------------------------


def test_rate_resolves_direct_model_id() -> None:
    assert pricing.rate(_PRICING, "claude-x") == {"input": 3.0, "output": 15.0}


def test_rate_resolves_via_alias() -> None:
    assert pricing.rate(_PRICING, "x") == {"input": 3.0, "output": 15.0}


def test_rate_returns_none_for_unknown_model() -> None:
    assert pricing.rate(_PRICING, "claude-unknown") is None


# ---------------------------------------------------------------------------
# cost()
# ---------------------------------------------------------------------------


def test_cost_computes_expected_dollars() -> None:
    usage = {
        "input_tokens": 1_000_000,
        "output_tokens": 1_000_000,
        "cache_creation_input_tokens": 1_000_000,
        "cache_read_input_tokens": 1_000_000,
    }
    rate_entry = _PRICING["models"]["claude-x"]
    result = pricing.cost(usage, rate_entry, _PRICING)
    expected = 3.0 + 15.0 + (3.0 * 1.25) + (3.0 * 0.1)
    assert result == expected


def test_cost_returns_zero_for_no_rate() -> None:
    usage = {"input_tokens": 1_000_000, "output_tokens": 1_000_000}
    assert pricing.cost(usage, None, _PRICING) == 0.0


def test_cost_treats_missing_usage_fields_as_zero() -> None:
    rate_entry = _PRICING["models"]["claude-x"]
    assert pricing.cost({}, rate_entry, _PRICING) == 0.0


def test_cost_treats_null_usage_fields_as_zero() -> None:
    # A model turn with no prompt caching support has been observed to emit
    # cache fields explicitly as null rather than omitting them.
    usage = {
        "input_tokens": 1_000_000,
        "output_tokens": 0,
        "cache_creation_input_tokens": None,
        "cache_read_input_tokens": None,
    }
    rate_entry = _PRICING["models"]["claude-x"]
    assert pricing.cost(usage, rate_entry, _PRICING) == 3.0
