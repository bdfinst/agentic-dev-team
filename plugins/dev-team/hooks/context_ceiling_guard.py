#!/usr/bin/env python3
"""Python port of hooks/context-ceiling-guard.sh (#595 / #572 Phase 3).

PreToolUse hook (Agent + Skill matchers). Enforces the context-window
ceiling from the Context Loading Protocol. Before a capability-loading call
— an Agent dispatch or a Skill invocation — it reads the *real* context
occupancy from the session transcript's most recent assistant-message usage
and compares it to the model's context window. Over the ceiling it nudges
the orchestrator to summarize (warn, the default) or blocks the load
(strict mode).

Utilization formula (identical in skills/context-loading-protocol/SKILL.md
and skills/handoff/SKILL.md — kept in sync by
tests/hooks/test_context_ceiling_guard.py's formula-equality test):
    utilization = (input + cache_read + cache_creation) / model_context_window

Why occupancy from the transcript and not a self-estimate: the model has no
reliable readout of its own context fill; the usage the harness recorded in
the transcript is the ground truth.

Posture: warn-by-default, fail-open. Writes the message to stderr and exits
0 to allow/warn, exit 2 to block. Any error, unmatched tool, or
unmeasurable context → exit 0 — a measurement failure never blocks a
session.

Recovery skills are never gated: blocking /handoff (the way
back under budget) would deadlock the session.

Env:
    DEV_TEAM_CONTEXT_CEILING=off     disable entirely (default on)
    DEV_TEAM_CONTEXT_STRICT=on       block over the ceiling (default: warn)
    DEV_TEAM_CONTEXT_CEILING_PCT=N   ceiling percent (default 40)
    DEV_TEAM_CONTEXT_WINDOW=N        context window in tokens; an explicit
                                     override that always wins over
                                     auto-detection. When unset, the window is
                                     auto-detected from the transcript's most
                                     recent `message.model` by family/version
                                     substring: Haiku family -> 200000;
                                     current 1M families (Fable, Mythos,
                                     Opus 4.6/4.7/4.8, Sonnet 5, Sonnet 4.6)
                                     -> 1000000; unrecognized or undetectable
                                     model -> 200000 (conservative fallback —
                                     window is a fixed per-model property, and
                                     an unrecognized model is never assumed to
                                     be a large-window one).
    DEV_TEAM_CONTEXT_ABS_CEILING=N   absolute token cap on the threshold;
                                     defaults to 150000 (Anthropic's
                                     server-side compaction default). The
                                     effective threshold is
                                     min(ceiling_pct * window // 100, abs_ceiling)
                                     — a no-op on a 200K window (40% = 80K
                                     < 150K) but caps a 1M window's 400K
                                     percentage threshold down to 150K. The
                                     warning names which bound is binding
                                     (percentage or absolute) and the window's
                                     provenance (override, detected, or
                                     default) so the operator can see why the
                                     threshold landed where it did.

Contract (docs/python-hook-contract.md):
    Input : PreToolUse JSON on stdin
    Output: exit 0 = allow (optionally with stderr warning)
            exit 2 = block (strict mode over ceiling)
    Posture: fail-open on any parse or IO error.

Stdlib-only (json/os/pathlib/re/sys). Python 3.8+. See ADR 0014.

Refs: #572 (bash → Python migration epic).
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Optional, Tuple

_LIB_DIR = Path(__file__).resolve().parent / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from stdin_json import read_stdin_json  # type: ignore[import-not-found]  # noqa: E402
from boundary_events import emit_boundary_event as _emit_boundary_event  # noqa: E402


def emit_boundary_event(*args, **kwargs) -> None:
    """Local safety net (#859): even a misbehaving helper must never affect
    this hook's exit code, stdout, or stderr."""
    try:
        _emit_boundary_event(*args, **kwargs)
    except Exception:  # noqa: BLE001 - fail-open by design
        pass


# Recovery skills that must never be gated — blocking them would deadlock a
# session that has climbed over the ceiling.
_RECOVERY_SKILLS = frozenset(
    {
        "handoff",
        "context-loading-protocol",
        "continue",
        "review-summary",
        "session-review",
    }
)

# Only capability-loading tools trigger the ceiling — everything else is a
# silent pass. "Agent" and "Task" are the same subagent-dispatch tool
# (renamed Task → Agent in Claude Code 2.1.63; both live on as payload
# tool_names, #1178).
_GATED_TOOLS = frozenset({"Agent", "Task", "Skill"})


# ---------------------------------------------------------------------------
# env parsing
# ---------------------------------------------------------------------------


def _positive_int_env(name: str, default: int) -> int:
    """Read `name`; return the value if it is a positive int, else `default`.

    Mirrors the .sh's `{ [[ "$x" =~ ^[0-9]+$ ]] && [ "$x" -gt 0 ]; } || x=N`.
    """
    raw = os.environ.get(name)
    if raw is None:
        return default
    if not re.fullmatch(r"[0-9]+", raw):
        return default
    value = int(raw)
    return value if value > 0 else default


# ---------------------------------------------------------------------------
# model -> context window auto-detection
# ---------------------------------------------------------------------------

# Window is a fixed per-model property, not a family-wide one: only the
# specific model ids known today to ship a 1M window are listed. A future
# model that merely shares a family name (e.g. a hypothetical small-window
# "sonnet-6") must NOT be assumed 1M just because "sonnet" matches — that is
# why this list is version-pinned rather than a bare family regex. Unknown
# models fall back to the 200K default: over-nudging a 1M session is a minor
# false-alarm; under-nudging a 200K session risks running well past the real
# ceiling. See ADR 0011's dated amendment for the rationale change from a
# pure env-var default to this per-model map.
#
# Family match order matters: Haiku is checked first so a hypothetical
# "haiku-opus" alias (or similar) can't fall through to the 1M branch.
_HAIKU_WINDOW = 200_000
_LARGE_WINDOW = 1_000_000
_DEFAULT_WINDOW = 200_000

_HAIKU_RE = re.compile(r"haiku", re.IGNORECASE)
_LARGE_WINDOW_RE = re.compile(
    r"fable|mythos|opus-4-6|opus-4-7|opus-4-8|sonnet-5|sonnet-4-6",
    re.IGNORECASE,
)


def _window_for_model(model: str) -> int:
    """Map a model name to its context window via family/version substring.

    Haiku family -> 200K. Current 1M-window models -> 1M: Fable (any
    version), Mythos (any version), Opus 4.6/4.7/4.8, Sonnet 5, Sonnet 4.6.
    Anything else (unrecognized model, or a same-family model outside the
    pinned versions above) -> the 200K conservative default.
    """
    if _HAIKU_RE.search(model):
        return _HAIKU_WINDOW
    if _LARGE_WINDOW_RE.search(model):
        return _LARGE_WINDOW
    return _DEFAULT_WINDOW


def _detect_window(transcript_path: Path) -> Tuple[int, bool]:
    """Auto-detect the context window from the transcript's most recent
    `message.model`. Mirrors `_measure_occupancy`'s scan (last 400 lines,
    last matching row wins) so the detected model tracks the same session
    state as the occupancy measurement.

    Returns (window, matched) — `matched` is True only when a model id was
    found AND it matched a known family (Haiku or a pinned 1M version);
    False when no model id was found, or the model id is unrecognized, in
    which case `window` is the 200K conservative default either way. The
    caller uses `matched` to report window provenance as "detected" vs
    "default".

    Fail-open: any parse error, missing/malformed `model` field, or a
    transcript with no model at all resolves to (200000, False) — this
    function never raises and never blocks.
    """
    lines = _tail_lines(transcript_path, 400)
    last_model: Optional[str] = None
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            row = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(row, dict):
            continue
        message = row.get("message")
        if not isinstance(message, dict):
            continue
        model = message.get("model")
        if isinstance(model, str) and model:
            last_model = model
    if last_model is None:
        return _DEFAULT_WINDOW, False
    if _HAIKU_RE.search(last_model) or _LARGE_WINDOW_RE.search(last_model):
        return _window_for_model(last_model), True
    return _DEFAULT_WINDOW, False


def _env_window_override() -> Optional[int]:
    """Explicit `DEV_TEAM_CONTEXT_WINDOW` override; `None` when unset or
    invalid, in which case the caller falls through to auto-detection.
    """
    raw = os.environ.get("DEV_TEAM_CONTEXT_WINDOW")
    if raw is None:
        return None
    if not re.fullmatch(r"[0-9]+", raw):
        return None
    value = int(raw)
    return value if value > 0 else None


def _resolve_window(transcript_path: Path) -> Tuple[int, str]:
    """Resolve the effective context window and its provenance tag.

    Precedence: `DEV_TEAM_CONTEXT_WINDOW` env ("override") > detected from
    the transcript model ("detected") > the 200K conservative default
    ("default") when the model is missing/unrecognized.
    """
    override = _env_window_override()
    if override is not None:
        return override, "override"
    window, matched = _detect_window(transcript_path)
    return window, ("detected" if matched else "default")


# ---------------------------------------------------------------------------
# transcript scan
# ---------------------------------------------------------------------------


def _tail_lines(path: Path, n: int) -> list:
    """Read the last `n` lines from `path`. Fail-safe: [] on any IO error.

    Reads the whole file (bounded by the transcript size — hook payloads
    already imply a live session). The .sh uses `tail -n 400`; we match that
    bound.
    """
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        return []
    return lines[-n:] if len(lines) > n else lines


def _measure_occupancy(transcript_path: Path) -> Optional[int]:
    """Extract the most-recent-assistant-message usage total from the transcript.

    Occupancy = prompt-side tokens (input + cache_read + cache_creation) of the
    latest transcript line whose `.message.usage` is set. Returns None when no
    such line exists or on any parse error.

    Matches the .sh's `tail -n 400 | jq -rc 'select(...)|...' | tail -n 1`.
    """
    lines = _tail_lines(transcript_path, 400)
    if not lines:
        return None
    last_total: Optional[int] = None
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            row = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(row, dict):
            continue
        message = row.get("message")
        if not isinstance(message, dict):
            continue
        usage = message.get("usage")
        if not isinstance(usage, dict):
            continue
        input_t = usage.get("input_tokens") or 0
        cache_read = usage.get("cache_read_input_tokens") or 0
        cache_creation = usage.get("cache_creation_input_tokens") or 0
        if not all(isinstance(x, int) for x in (input_t, cache_read, cache_creation)):
            # Non-integer usage → skip this row (fail-open).
            continue
        last_total = int(input_t) + int(cache_read) + int(cache_creation)
    return last_total if (last_total is not None and last_total > 0) else None


# ---------------------------------------------------------------------------
# skill name extraction
# ---------------------------------------------------------------------------


def _extract_skill_name(tool_input: dict) -> str:
    """Best-effort extract of the skill identifier.

    Matches the .sh's `.tool_input.skill // .tool_input.name // empty`, then
    strips a leading `<plugin>:` prefix.
    """
    skill = tool_input.get("skill") or tool_input.get("name") or ""
    if not isinstance(skill, str):
        return ""
    if ":" in skill:
        skill = skill.rsplit(":", 1)[-1]
    return skill


# ---------------------------------------------------------------------------
# bucket dedupe marker
# ---------------------------------------------------------------------------


def _sanitize_session(session_id: str) -> str:
    """Match the .sh's `tr -cd 'A-Za-z0-9_-'` + `[-z "$session"] && "nosession"`."""
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "", session_id or "")
    return cleaned or "nosession"


def _marker_path(session_id: str) -> Path:
    """The per-session dedupe marker path.

    Uses TMPDIR when set (the .sh does the same), falling back to the system
    temp dir. Both sides must agree on the path — the parity harness sandbox
    sets TMPDIR and both sides land at the same file.
    """
    tmpdir = os.environ.get("TMPDIR") or tempfile.gettempdir()
    return Path(tmpdir) / f"dev-team-ctx-ceiling-{session_id}.last"


def _read_last_bucket(marker: Path) -> int:
    try:
        raw = marker.read_text(encoding="utf-8").strip()
    except OSError:
        return 0
    if not re.fullmatch(r"[0-9]+", raw):
        return 0
    return int(raw)


def _write_bucket(marker: Path, bucket: int) -> None:
    try:
        marker.write_text(str(bucket), encoding="utf-8")
    except OSError:
        # Fail-open — a dedupe write error must not break the session.
        pass


# ---------------------------------------------------------------------------
# message shape
# ---------------------------------------------------------------------------


def _resolve_bound(pct_threshold_tokens: int, abs_ceiling: int) -> str:
    """Which of the two thresholds is binding for `min(pct, abs)` (#780).

    "percentage" when the percentage-of-window threshold is the smaller (or
    equal — ties read as percentage, matching `min()`'s first-argument
    preference), "absolute" when the absolute cap is strictly smaller. The
    two framings never co-occur in the message — exactly one is reported.
    """
    return "percentage" if pct_threshold_tokens <= abs_ceiling else "absolute"


# Graduated bands (#781): keyed to multiples of the *effective* ceiling
# (tokens), not raw window percentage — a band escalation always means
# "occupancy climbed further past the same computed threshold", regardless
# of which bound (percentage or absolute) produced that threshold.
#   [1x,   1.25x) -> band 0, nudge
#   [1.25x, 1.5x) -> band 1, run /handoff now
#   [1.5x,   inf) -> band 2, full summary + fresh conversation (top band)
# Integer math (eff * 5 // 4, eff * 3 // 2) avoids float imprecision.
_BAND_NUDGE, _BAND_RUN_NOW, _BAND_FULL_SUMMARY = 0, 1, 2

# Dedupe-key scale factor (#781): pct_bucket (occupancy % of window // 5)
# tops out at 20 (100% // 5). 100 keeps `band * _BAND_SCALE` strictly above
# any possible pct_bucket for every band >= 1, so a band transition always
# wins the `max()` and forces a re-fire regardless of the coarser bucket.
_BAND_SCALE = 100

_BAND_ACTIONS = {
    _BAND_NUDGE: (
        "nudge",
        "Consider running /handoff (write a memory/ progress "
        "file, continue in a fresh context) and defer non-essential "
        "agents/skills.",
    ),
    _BAND_RUN_NOW: (
        "run-now",
        "Run /handoff now — write a memory/ progress file "
        "and continue in a fresh context.",
    ),
    _BAND_FULL_SUMMARY: (
        "full-summary",
        "Write a full summary to memory/ and start a new conversation now "
        "— context is well past the effective ceiling.",
    ),
}


def _band_for_threshold_multiple(occ: int, threshold_tokens: int) -> int:
    """Map occupancy, as a multiple of the effective ceiling, to a band
    index. Only called once occupancy has already cleared the ceiling
    (`occ >= threshold_tokens`), so `threshold_tokens <= 0` never occurs on
    that path — the guard is defensive only, not a documented behavior.
    """
    if threshold_tokens <= 0:
        return _BAND_NUDGE
    if occ >= threshold_tokens * 3 // 2:  # 1.5x
        return _BAND_FULL_SUMMARY
    if occ >= threshold_tokens * 5 // 4:  # 1.25x
        return _BAND_RUN_NOW
    return _BAND_NUDGE


def _format_message(
    occ: int,
    window: int,
    threshold_tokens: int,
    bound: str,
    provenance: str,
    label: str,
) -> str:
    """Pinned message contract (#780) plus graduated band escalation
    (#781): plain token counts (not percentages), the binding bound
    (percentage vs absolute — never both), the window's provenance
    (override/detected/default), and a Handoff action band
    keyed to how far occupancy has climbed past the effective ceiling. The
    top band (full-summary) leads with the directive and drops the knob
    footer — at 1.5x the ceiling, tuning knobs are no longer the point."""
    band = _band_for_threshold_multiple(occ, threshold_tokens)
    band_name, action = _BAND_ACTIONS[band]
    diagnostic = (
        f"🪟 Context at {occ} of {window} tokens — over the effective "
        f"ceiling of {threshold_tokens} tokens ({bound} bound; "
        f"window {provenance}) before {label}."
    )

    if band == _BAND_FULL_SUMMARY:
        return f"[{band_name}] {action}\n{diagnostic}"

    knob_footer = (
        "Tune with DEV_TEAM_CONTEXT_WINDOW (overrides auto-detection) / "
        "DEV_TEAM_CONTEXT_CEILING_PCT / DEV_TEAM_CONTEXT_ABS_CEILING;\n"
        "DEV_TEAM_CONTEXT_STRICT=on hard-blocks; "
        "DEV_TEAM_CONTEXT_CEILING=off disables."
    )
    return f"{diagnostic}\n[{band_name}] {action}\n{knob_footer}"


def _build_label(tool_name: str, tool_input: dict) -> str:
    if tool_name == "Skill":
        skill = tool_input.get("skill") or tool_input.get("name") or "?"
        if not isinstance(skill, str) or not skill:
            skill = "?"
        return f"invoking skill '{skill}'"
    # Agent
    agent = tool_input.get("subagent_type") or "?"
    if not isinstance(agent, str) or not agent:
        agent = "?"
    return f"loading agent '{agent}'"


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def _resolve_verdict(payload: dict) -> Tuple[int, Optional[str], bool]:
    """Compute (exit_code, message_or_None, should_write_bucket).

    Split from main() for testability. Env-var reads still happen here — the
    hook is invoked once per fire, and the env is the source of truth.
    """
    if os.environ.get("DEV_TEAM_CONTEXT_CEILING") == "off":
        return 0, None, False

    tool_name = payload.get("tool_name") or ""
    if tool_name not in _GATED_TOOLS:
        return 0, None, False

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}

    # Recovery skills — never gate.
    if tool_name == "Skill":
        skill = _extract_skill_name(tool_input)
        if skill in _RECOVERY_SKILLS:
            return 0, None, False

    transcript_str = payload.get("transcript_path") or ""
    if not isinstance(transcript_str, str) or not transcript_str:
        return 0, None, False
    transcript_path = Path(transcript_str)
    if not transcript_path.is_file():
        return 0, None, False

    occ = _measure_occupancy(transcript_path)
    if occ is None:
        return 0, None, False

    window, provenance = _resolve_window(transcript_path)
    ceiling = _positive_int_env("DEV_TEAM_CONTEXT_CEILING_PCT", 40)
    abs_ceiling = _positive_int_env("DEV_TEAM_CONTEXT_ABS_CEILING", 150_000)

    # Effective threshold = min(ceiling_pct * window, absolute cap). On a
    # 200K window this is a no-op (40% = 80K < 150K); on a 1M window it caps
    # the 400K percentage threshold down to 150K (#786/#780).
    pct_threshold_tokens = (ceiling * window) // 100
    threshold_tokens = min(pct_threshold_tokens, abs_ceiling)
    bound = _resolve_bound(pct_threshold_tokens, abs_ceiling)

    # Bash: `pct=$((occ * 100 / window))` — integer truncation. Match exactly.
    # Still computed for the per-session dedupe bucket even though the
    # message itself now reports plain token counts, not a percentage.
    pct = (occ * 100) // window
    if occ < threshold_tokens:
        return 0, None, False

    label = _build_label(tool_name, tool_input)
    msg = _format_message(occ, window, threshold_tokens, bound, provenance, label)

    if os.environ.get("DEV_TEAM_CONTEXT_STRICT") == "on":
        return 2, f"{msg} [blocked: DEV_TEAM_CONTEXT_STRICT=on]", False

    # Warn mode dedupe, re-keyed on band identity (#781): the dedupe key is
    # max(band_index_scaled, pct_bucket). _BAND_SCALE (100) makes any band
    # transition dominate the coarser 5%-of-window pct_bucket (whose max
    # value is 20, well under 100), so an escalation always breaks through
    # even when the pct_bucket hasn't moved — worked 1M-window case: fires
    # at occ=150000 (band 0, pct_bucket 3, key 3), re-fires at occ=190000
    # (band 1 starts at 187500, key 100 > 3), and again at occ=226000 (band
    # 2 starts at 225000, key 200 > 100).
    band = _band_for_threshold_multiple(occ, threshold_tokens)
    session = _sanitize_session(payload.get("session_id") or "")
    marker = _marker_path(session)
    bucket = max(band * _BAND_SCALE, pct // 5)
    last_bucket = _read_last_bucket(marker)
    # Always write the marker (matches the .sh's `printf ... >"$marker"` that
    # runs before the bucket comparison).
    _write_bucket(marker, bucket)
    if bucket <= last_bucket:
        return 0, None, False

    return 0, msg, False


def main() -> int:
    payload = read_stdin_json()
    if payload is None:
        # Empty or malformed stdin → silent-pass, same as the .sh.
        return 0

    exit_code, message, _ = _resolve_verdict(payload)
    if message is not None:
        # The .sh uses `printf '%s\n' "$msg" >&2` — write to stderr with a
        # trailing newline.
        sys.stderr.write(message + "\n")
    if exit_code == 2 or message is not None:
        cwd = payload.get("cwd") or "."
        session_id = payload.get("session_id")
        tool = payload.get("tool_name") or "unknown"
        decision = "block" if exit_code == 2 else "warn"
        emit_boundary_event(
            cwd, "context_ceiling_guard", tool, decision, "context-ceiling", session_id
        )
    return exit_code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
