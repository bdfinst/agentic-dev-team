#!/usr/bin/env python3
"""Pre-dispatch effort band → model resolver (Python port of model-resolve.sh, #577).

Maps an effort band (low|medium|high) to an Anthropic model using:
  1. an optional ordered ladder at .claude/model-ladder.json — a JSON array
     of model IDs from least to most capable — via
     index = round_half_up(weight·(N−1)) with weights low=0, medium=0.5,
     high=1; OR
  2. the shipped default map in knowledge/model-routing.json, used whenever
     no ladder exists or the ladder is malformed/empty.

Legacy tier aliases (haiku|sonnet|opus) are accepted for the migration
window and normalized to bands (haiku→low, sonnet→medium, opus→high).

A missing or malformed ladder degrades to the default map and never aborts
dispatch. This resolver does NOT log routing bumps — the dispatch hook
(agent-model-resolve) owns that single site, so there is no double-log.

Called by:
  - hooks/agent-model-resolve.sh (PreToolUse hook on the Agent matcher)
  - skills/model-routing-check/SKILL.md (via --dump-map)

CLI usage (mirrors model-resolve.sh):
  python3 model_resolve.py <band|tier> [--caller <name>]
  python3 model_resolve.py --dump-map

Library usage:
  from model_resolve import resolve_band, dump_map
  model_id = resolve_band("medium")

Env vars (TEST-ONLY injection seams — do not document as user-facing):
  MODEL_ROUTING_JSON   defaults to <plugin>/knowledge/model-routing.json
  MODEL_LADDER_JSON    defaults to .claude/model-ladder.json

Exit codes:
  0 — resolved
  2 — unknown band/tier or missing argument (caller error)
  4 — knowledge/model-routing.json missing

Note: the legacy deny-relevant exits (3 exhausted/cycle, 5 malformed
overrides) are no longer reachable — band resolution always succeeds once
routing.json is present, because a bad ladder degrades to the default map.

Stdlib-only (subprocess/pathlib/json/argparse only). Python 3.8+.
See docs/adr/0014-python-for-cross-os-scripts.md.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# Public exit codes — kept identical to model-resolve.sh so callers that pipe
# through subprocess don't need to change behavior.
# ---------------------------------------------------------------------------
EXIT_OK = 0
EXIT_CALLER_ERROR = 2
EXIT_ROUTING_MISSING = 4


# ---------------------------------------------------------------------------
# _resolve_paths — populate input paths with defaults if env vars aren't set.
# Test isolation hinges on these env vars.
# ---------------------------------------------------------------------------
def _resolve_paths() -> Tuple[Path, Path]:
    script_dir = Path(__file__).resolve().parent
    routing = Path(
        os.environ.get(
            "MODEL_ROUTING_JSON",
            str(script_dir / ".." / ".." / "knowledge" / "model-routing.json"),
        )
    )
    ladder = Path(
        os.environ.get(
            "MODEL_LADDER_JSON",
            ".claude/model-ladder.json",
        )
    )
    return routing, ladder


# ---------------------------------------------------------------------------
# normalize_band — map a band or legacy tier to a canonical band.
# Returns "" for an unrecognized token (matches the .sh's echo "").
#
# Public (#732): also called directly by hooks/agent_model_resolve.py, which
# used to keep its own copy of this function. Promoted so there is exactly
# one implementation to keep in sync.
# ---------------------------------------------------------------------------
def normalize_band(token: str) -> str:
    if token in ("low", "haiku"):
        return "low"
    if token in ("medium", "sonnet"):
        return "medium"
    if token in ("high", "opus"):
        return "high"
    return ""


# ---------------------------------------------------------------------------
# _band_weight — the ladder weight for a band (low=0, medium=0.5, high=1).
# ---------------------------------------------------------------------------
def _band_weight(band: str) -> float:
    return {"low": 0.0, "medium": 0.5, "high": 1.0}[band]


# ---------------------------------------------------------------------------
# load_json — read a JSON file if present; return None on any failure.
#
# Public (#732): also called directly by hooks/agent_model_resolve.py. The
# exception tuple deliberately includes `ValueError` in addition to
# `json.JSONDecodeError` (a `ValueError` subclass) so a mis-encoded file
# (e.g. `UnicodeDecodeError`, also a `ValueError` subclass) degrades to None
# rather than raising — this hook's fail-open posture requires it, and it
# was the one behavior agent_model_resolve.py's now-removed local copy had
# that this shared version previously lacked.
# ---------------------------------------------------------------------------
def load_json(path: Path) -> Optional[object]:
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# _load_valid_ladder — parse the ladder file once and return it only if it's
# a non-empty JSON array of strings; None otherwise (degrades to the default
# map). resolve_band uses this directly so it never parses the ladder twice
# (validate, then reload) in a single call.
# ---------------------------------------------------------------------------
def _load_valid_ladder(ladder_path: Path) -> Optional[List[str]]:
    if not ladder_path.exists():
        return None
    data = load_json(ladder_path)
    if not isinstance(data, list) or len(data) == 0:
        return None
    if not all(isinstance(x, str) for x in data):
        return None
    return data


# ---------------------------------------------------------------------------
# ladder_is_valid — true iff the ladder file exists and is a non-empty JSON
# array of strings. Anything else degrades to the default map.
#
# Public (#732): also called directly by hooks/agent_model_resolve.py.
# ---------------------------------------------------------------------------
def ladder_is_valid(ladder_path: Path) -> bool:
    return _load_valid_ladder(ladder_path) is not None


# ---------------------------------------------------------------------------
# _default_for_band — the shipped default snapshot for a band.
# Returns "" when the band key is absent (matches jq's // empty behavior).
# ---------------------------------------------------------------------------
def _default_for_band(routing_path: Path, band: str) -> str:
    data = load_json(routing_path)
    if not isinstance(data, dict):
        return ""
    value = data.get(band)
    return value if isinstance(value, str) else ""


# ---------------------------------------------------------------------------
# _round_half_up — the pinned rounding convention. floor(x + 0.5) for x ≥ 0
# reproduces the bash `awk 'printf "%d", int(w*(n-1)+0.5)'` byte-for-byte.
# ---------------------------------------------------------------------------
def _round_half_up(weight: float, n: int) -> int:
    return int(weight * (n - 1) + 0.5)


# ---------------------------------------------------------------------------
# resolve_band — map a canonical band to a model: ladder when valid, else
# the shipped default map. Public API for downstream consumers (#585-#587).
# ---------------------------------------------------------------------------
def resolve_band(
    band: str, routing_path: Optional[Path] = None, ladder_path: Optional[Path] = None
) -> str:
    if routing_path is None or ladder_path is None:
        r, l = _resolve_paths()
        routing_path = routing_path or r
        ladder_path = ladder_path or l

    ladder = _load_valid_ladder(ladder_path)
    if ladder is not None:
        n = len(ladder)
        weight = _band_weight(band)
        idx = _round_half_up(weight, n)
        return str(ladder[idx])

    return _default_for_band(routing_path, band)


# ---------------------------------------------------------------------------
# dump_map — pretty-print the effective band → model map. Used by
# /model-routing-check.
#
# Format matches model-resolve.sh's `printf '  %-7s → %s\n'` — two leading
# spaces, band left-padded to width 7, " → ", model id, newline.
# ---------------------------------------------------------------------------
def dump_map(
    routing_path: Optional[Path] = None, ladder_path: Optional[Path] = None
) -> str:
    lines: List[str] = []
    for band in ("low", "medium", "high"):
        model = resolve_band(band, routing_path=routing_path, ladder_path=ladder_path)
        lines.append(f"  {band:<7} → {model}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# _die_missing_routing — the one surviving fatal case (exit 4).
# ---------------------------------------------------------------------------
def _die_missing_routing(routing_path: Path) -> None:
    sys.stderr.write(
        f"Model routing file missing: {routing_path}\n"
        "  This file ships with the plugin and must be present.\n"
        "  Restore with: git checkout knowledge/model-routing.json\n"
    )


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)

    if len(args) < 1:
        sys.stderr.write(
            "Usage: model_resolve.py <band> [--caller <name>]\n"
            "       model_resolve.py --dump-map\n"
            "Valid bands: low, medium, high\n"
        )
        return EXIT_CALLER_ERROR

    routing_path, ladder_path = _resolve_paths()

    # All paths require routing.json — fail early with the proper template.
    if not routing_path.is_file():
        _die_missing_routing(routing_path)
        return EXIT_ROUTING_MISSING

    # --dump-map mode
    if args[0] == "--dump-map":
        sys.stdout.write(dump_map(routing_path=routing_path, ladder_path=ladder_path))
        return EXIT_OK

    requested = args[0]
    band = normalize_band(requested)
    if not band:
        sys.stderr.write(
            f"Unknown effort band '{requested}'. Valid bands: low, medium, "
            "high (legacy tiers haiku, sonnet, opus accepted).\n"
        )
        return EXIT_CALLER_ERROR

    # Parse optional --caller flag. Accepted but ignored: the dispatch hook
    # owns bump logging, so the resolver no longer needs the caller name.
    remaining = args[1:]
    i = 0
    while i < len(remaining):
        arg = remaining[i]
        if arg == "--caller":
            # consume the caller name if present, otherwise silently accept.
            i += 2
            continue
        sys.stderr.write(f"Unknown argument: {arg}\n")
        return EXIT_CALLER_ERROR

    sys.stdout.write(
        resolve_band(band, routing_path=routing_path, ladder_path=ladder_path) + "\n"
    )
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
