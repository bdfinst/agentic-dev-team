"""Model-pricing loader, rate lookup, and cost computation (issue #2045,
epic #2040).

Shared by `hooks/lib/cost_meter.py` (the Stop-hook cost meter) and
`session_report.py --profile maintainer` (originally a separate monorepo-only
session digest extractor, retired in #2048; #2045 unified the two). Before
this module existed each carried its
own near-identical copy of `_load_pricing`/`_rate`/`_cost`, and the two had
quietly drifted: cost_meter's loader raised on a missing/unreadable
pricing file where the extractor's degraded to an empty table, and
cost_meter's `_cost` required its caller to guard `if rate else 0.0` (it
indexed `rate["input"]` directly) where the extractor's guarded internally
and read `rate.get(...)`. Unified here on the more defensive shape throughout: an
absent/corrupt/`None` pricing path yields `{}` rather than raising, and
`cost()` itself returns `0.0` for an unpriced model rather than requiring
every caller to remember the ternary — consistent with this file's own
fail-open philosophy (see `cost_meter.py`'s `cmd_record`/`cmd_phase_mark`,
which return 0 on a missing transcript rather than raising: a hook must
never break a turn).

Placement — NOT `plugins/dev-team/scripts/lib/session_log/`, despite that
package's `__init__.py` briefly forward-declaring a `pricing` module for
this issue (corrected in the same commit that adds this file). Reason:
`hooks/lib/cost_meter.py` is a real Stop hook, registered in `settings.json`
and run on every session in every installed project.
`hooks/lib/review_agent_registry.py` and `hooks/lib/review_dispatch_ledger.py`
already established the rule this module follows — "a hook must be
import-safe without any `scripts/` module on its path; the dependency
direction is scripts/ -> hooks/lib/, never the reverse" (#1461) — so a
module a hook needs lives in `hooks/lib/`, and the `scripts/` side reaches
into it, exactly mirroring how `scripts/check_review_agent_mcp_tools.py`
already imports `review_agent_registry` from `hooks/lib/`. Putting pricing
here instead of `session_log/` keeps that boundary intact rather than
inverting it for this one module.

Downstream-cost decision (#2045): `session_report.py --profile downstream`
(originally a separate shipped script, retired in #2048; the shipped
report a downstream user hands to the plugin
maintainer) does NOT gain a cost figure as part of this issue, and does not
import this module. ADR 0036 already decided this narrower question — "The extractors'
divergent layers stay forked: discovery/CLI surface, **pricing and cost**,
rollup, escalation, and the report shapes... cost/pricing/rollup/escalation
exist only in the monorepo one. Divergence is not drift." — for exactly the
reason issue #2045 itself names as the argument against: a pricing table
shipped inside the plugin is unverifiable by the downstream user and goes
stale between releases, so it's presented in `cost_meter.py`'s own reports
(which run in the environment that produced the spend) rather than baked
into a portable summary file.

Stdlib only. See ADR 0014 / ADR 0015.
"""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_CACHE_WRITE_MULTIPLIER = 1.25
DEFAULT_CACHE_READ_MULTIPLIER = 0.1


def _usage_field(usage: dict, field: str) -> int | float:
    """`.get(field, 0) or 0` — the one canonical usage-field reader (matches
    `scripts/lib/session_log/records.usage_field`'s null-handling contract;
    duplicated here rather than imported, in service of the hooks/lib ->
    scripts/ dependency direction described in the module docstring above —
    this module must not reach INTO `scripts/lib/session_log/` any more than
    `cost_meter.py` may)."""
    return usage.get(field, 0) or 0


def load_pricing(path: Path | None) -> dict:
    """Load a model-pricing.json table. Defensive: an absent path, a `None`
    path, or malformed JSON all degrade to `{}` (every model then prices at
    $0.00 and is flagged `unpriced`) rather than raising."""
    if not path or not Path(path).is_file():
        return {}
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def rate(pricing: dict, model: str) -> dict | None:
    """Resolve one model id to its `{"input": .., "output": ..}` rate,
    following a pricing table's `aliases` indirection when the model id has
    no direct entry."""
    models = pricing.get("models", {})
    if model in models:
        return models[model]
    alias = pricing.get("aliases", {}).get(model)
    if alias and alias in models:
        return models[alias]
    return None


def cost(usage: dict, rate_entry: dict | None, pricing: dict) -> float:
    """Dollar cost of one usage block at `rate_entry`. `0.0` when no rate is
    known for the model — an unpriced model contributes $0, never raises."""
    if not rate_entry:
        return 0.0
    input_tokens = _usage_field(usage, "input_tokens")
    output_tokens = _usage_field(usage, "output_tokens")
    cache_write_tokens = _usage_field(usage, "cache_creation_input_tokens")
    cache_read_tokens = _usage_field(usage, "cache_read_input_tokens")
    in_rate = rate_entry.get("input", 0)
    return (
        input_tokens / 1e6 * in_rate
        + output_tokens / 1e6 * rate_entry.get("output", 0)
        + cache_write_tokens
        / 1e6
        * in_rate
        * pricing.get("cache_write_multiplier", DEFAULT_CACHE_WRITE_MULTIPLIER)
        + cache_read_tokens
        / 1e6
        * in_rate
        * pricing.get("cache_read_multiplier", DEFAULT_CACHE_READ_MULTIPLIER)
    )
