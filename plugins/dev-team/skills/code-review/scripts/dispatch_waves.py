#!/usr/bin/env python3
"""Split a review's agent roster into bounded, sequential dispatch waves (#1752).

`/code-review` Step 4 used to spawn every eligible agent as parallel `Agent`
tool calls in a single message, regardless of roster size. A real run with 16
agents in one message lost its last 6 to `[Tool result missing due to
internal error]` — the first 10 calls returned normal `agentId`s with the
identical parameter shape, so this reads as the harness dropping calls past
some concurrent-dispatch ceiling within that one message, not a malformed
request. (The incident observed 10 succeeding as the first slice of a
16-call message; it does not, on its own, prove 10 is the largest size that
would succeed as its own dedicated message — see `DEFAULT_MAX_PARALLEL`
below.) Nothing detected the gap: the review report simply had six fewer
lenses' worth of findings.

This module is the deterministic half of the fix — it decides *how many
agents go out per message* and *how the roster splits into waves*, in the
order it's given. It does not decide that order (that's the orchestrator's
job, assembling `--agents` from Step 3's eligibility gates in `SKILL.md`) and
it cannot decide whether a given wave's dispatch actually succeeded (that only
the orchestrator, holding the real `Agent` tool, can observe) — `SKILL.md`'s
retry-once-then-report handling covers that half.

Pure policy — no filesystem, no network. The only ambient read is
`os.environ`, and it's injectable via `resolve_max_parallel`'s `env`
parameter for testability. Stdlib-only.

**A note on "wave"**: this repo uses the word for three different things.
`scripts/orchestrator.py`'s wave carries barrier-and-reconcile semantics
(a failed slice raises and blocks state persistence); `scripts/plan_waves.py`
derives wave membership from step *dependencies*. This module's wave is
neither — just a fixed-size slice of an already-ordered roster, with no
barrier or reconciliation semantics of its own.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# Shares the DEV_TEAM_MAX_PARALLEL_* naming convention with build_jobs.py's
# DEV_TEAM_MAX_PARALLEL_BUILDS, but inverts its clamping direction: that knob
# is a worker *floor* (fan-out is opt-in, so malformed/unset -> 1, sequential);
# this one is a *ceiling* on an already-parallel panel, so malformed/unset ->
# DEFAULT_MAX_PARALLEL rather than 1 — collapsing to 1 here would silently
# serialize a review that's supposed to stay parallel.
MAX_PARALLEL_ENV_VAR = "DEV_TEAM_MAX_PARALLEL_REVIEW_AGENTS"

# 10 is what stayed reliable in the #1752 incident (the first 10 of a 16-call
# message all returned valid agentIds) — a real observation, not a measured
# ceiling: it doesn't by itself prove 10 is the *largest* size that would
# succeed as its own dedicated message. Revisit if real usage shows this
# miscalibrated in either direction.
DEFAULT_MAX_PARALLEL = 10

# A pathologically long digit string is never a real configuration value, and
# is believed to trip CPython's int-string conversion limit inside `int()` on
# 3.11+ (default 4300 digits, per CVE-2020-10735 — not independently probed
# in this repo) — a limit that doesn't exist on this repo's 3.10 floor (ADR
# 0031), so this guard is a defensive ceiling independent of which
# interpreter runs it, not a floor-specific workaround. Kept well under
# either boundary so a malformed override never crashes instead of falling
# back.
_MAX_ENV_DIGITS = 12


def _is_valid_max_parallel(value: object) -> bool:
    """One predicate, shared by both callers that need "a valid wave size":
    :func:`resolve_max_parallel`'s override branch (falls back on failure)
    and :func:`form_dispatch_waves` (raises on failure). ``bool`` is a
    subclass of ``int`` in Python, so it's explicitly excluded — `True` would
    otherwise pass as `1`."""
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def resolve_max_parallel(env: dict | None = None, override: int | None = None) -> int:
    """Return the effective max-parallel-agents-per-wave value.

    ``override`` (e.g. an explicit `--max-parallel` flag) wins whenever it is
    given at all — valid or not. An invalid override (non-int, bool, or
    non-positive) falls back to :data:`DEFAULT_MAX_PARALLEL` and does **not**
    fall through to the env: an explicit flag always takes precedence over
    config, so a malformed flag value is a request to use the safe default,
    not a signal to consult the environment instead.

    Otherwise reads ``DEV_TEAM_MAX_PARALLEL_REVIEW_AGENTS`` from ``env``
    (defaults to ``os.environ``), tolerating incidental surrounding
    whitespace. Unset, empty, too long to parse safely, non-integer, or
    non-positive values all fall back to :data:`DEFAULT_MAX_PARALLEL` —
    deterministic, never an error, and never silently degrading concurrency
    to 1 just because an override was malformed.
    """
    if override is not None:
        return override if _is_valid_max_parallel(override) else DEFAULT_MAX_PARALLEL

    source = os.environ if env is None else env
    raw = source.get(MAX_PARALLEL_ENV_VAR, "").strip()
    if not raw:
        return DEFAULT_MAX_PARALLEL
    if not (raw.isascii() and raw.isdigit()) or len(raw) > _MAX_ENV_DIGITS:
        return DEFAULT_MAX_PARALLEL
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MAX_PARALLEL
    return value if _is_valid_max_parallel(value) else DEFAULT_MAX_PARALLEL


def form_dispatch_waves(agents: list[str], max_parallel: int) -> list[list[str]]:
    """Split ``agents`` into ordered waves of at most ``max_parallel`` each.

    The per-message dispatch ceiling, the wave size, and ``max_parallel``
    below are the same number — ``maxParallel`` is its name in the CLI's JSON
    output and in the env knob (:data:`MAX_PARALLEL_ENV_VAR`).

    Roster order is preserved both within and across waves, so a fixed input
    always yields the same waves in the same order — this function does not
    decide that order, only where it gets cut. An empty roster yields ``[]``.
    Raises ``ValueError`` if ``max_parallel`` is not a positive integer —
    callers should route through :func:`resolve_max_parallel`, which never
    returns an invalid value, but this function guards its own contract too.
    """
    if not _is_valid_max_parallel(max_parallel):
        raise ValueError(f"max_parallel must be a positive integer, got {max_parallel!r}")
    if not agents:
        return []
    return [
        list(agents[start : start + max_parallel])
        for start in range(0, len(agents), max_parallel)
    ]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--agents", required=True,
        help="comma-separated agent names to dispatch, in roster order",
    )
    parser.add_argument(
        "--max-parallel", type=int, default=None,
        help=f"override the resolved max (default: env {MAX_PARALLEL_ENV_VAR} or {DEFAULT_MAX_PARALLEL})",
    )
    args = parser.parse_args(argv)

    agents = [a.strip() for a in args.agents.split(",") if a.strip()]
    max_parallel = resolve_max_parallel(override=args.max_parallel)

    waves = form_dispatch_waves(agents, max_parallel)
    print(json.dumps({"maxParallel": max_parallel, "waves": waves}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))


__all__ = (
    "DEFAULT_MAX_PARALLEL",
    "MAX_PARALLEL_ENV_VAR",
    "form_dispatch_waves",
    "resolve_max_parallel",
)
