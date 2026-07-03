#!/usr/bin/env python3
"""Python port of hooks/context-ceiling-guard.sh (#595 / #572 Phase 3).

PreToolUse hook (Agent + Skill matchers). Enforces the 40% context-window
ceiling from the Context Loading Protocol. Before a capability-loading call
— an Agent dispatch or a Skill invocation — it reads the *real* context
occupancy from the session transcript's most recent assistant-message usage
(input + cache_read + cache_creation tokens) and compares to the model's
context window. Over the ceiling it nudges the orchestrator to summarize
(warn, the default) or blocks the load (strict mode).

Why occupancy from the transcript and not a self-estimate: the model has no
reliable readout of its own context fill; the usage the harness recorded in
the transcript is the ground truth.

Posture: warn-by-default, fail-open. Writes the message to stderr and exits
0 to allow/warn, exit 2 to block. Any error, unmatched tool, or
unmeasurable context → exit 0 — a measurement failure never blocks a
session.

Recovery skills are never gated: blocking /context-summarization (the way
back under budget) would deadlock the session.

Env:
    DEV_TEAM_CONTEXT_CEILING=off     disable entirely (default on)
    DEV_TEAM_CONTEXT_STRICT=on       block over the ceiling (default: warn)
    DEV_TEAM_CONTEXT_CEILING_PCT=N   ceiling percent (default 40)
    DEV_TEAM_CONTEXT_WINDOW=N        context window in tokens; defaults to
                                     200000 (every current Claude model's
                                     base window). Set 1000000 on 1M models.

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


# Recovery skills that must never be gated — blocking them would deadlock a
# session that has climbed over the ceiling.
_RECOVERY_SKILLS = frozenset(
    {
        "context-summarization",
        "context-loading-protocol",
        "continue",
        "review-summary",
        "session-review",
    }
)

# Only these two tool matchers trigger the ceiling — everything else is a
# silent pass. Keeps the guard scoped to capability-loading calls.
_GATED_TOOLS = frozenset({"Agent", "Skill"})


# ---------------------------------------------------------------------------
# stdin + env parsing
# ---------------------------------------------------------------------------


def _read_stdin() -> str:
    try:
        return sys.stdin.read()
    except (OSError, ValueError):
        return ""


def _load_input(raw: str) -> Optional[dict]:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


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


def _band_for_pct(pct: int) -> Tuple[str, str]:
    """Map occupancy percent to a Context Summarization action band.

    Mirrors the action-band table in
    skills/context-summarization/SKILL.md (`## When to Summarize`):
    30-40% prepare, 40-50% summarize + fresh context, 50-65% summarize
    everything but the current task, 65%+ full summary to memory/. The
    guard only ever fires at or above the configured ceiling (default
    40%), so the "<30%" band is unreachable at default settings but is
    included for completeness when DEV_TEAM_CONTEXT_CEILING_PCT is
    lowered below 30.
    """
    if pct >= 65:
        return (
            "65%+",
            "write a full summary to memory/ and start a new conversation",
        )
    if pct >= 50:
        return ("50-65%", "summarize everything except the current task")
    if pct >= 40:
        return (
            "40-50%",
            "write a summary to memory/ and start a fresh context window",
        )
    if pct >= 30:
        return (
            "30-40%",
            "prepare: identify summarization candidates",
        )
    return ("<30%", "no action needed yet")


def _format_message(
    pct: int,
    window: int,
    ceiling: int,
    label: str,
) -> str:
    """Graduated warning message (#787): names the Context Summarization
    action band (see `_band_for_pct`) that applies at the current
    occupancy, escalating the wording as occupancy climbs further past
    the ceiling instead of repeating one fixed message."""
    band_name, action = _band_for_pct(pct)
    return (
        f"🪟 Context at {pct}% of the {window}-token window "
        f"(≥ {ceiling}% ceiling) before {label}.\n"
        f"Per the Context Loading Protocol [{band_name} band]: {action}. "
        "Run /context-summarization\n"
        "(write a memory/ progress file, continue in a fresh context) "
        "and defer non-essential agents/skills.\n"
        "Tune with DEV_TEAM_CONTEXT_WINDOW (set 1000000 on a 1M-context "
        "model) / DEV_TEAM_CONTEXT_CEILING_PCT;\n"
        "DEV_TEAM_CONTEXT_STRICT=on hard-blocks; "
        "DEV_TEAM_CONTEXT_CEILING=off disables."
    )


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

    window = _positive_int_env("DEV_TEAM_CONTEXT_WINDOW", 200_000)
    ceiling = _positive_int_env("DEV_TEAM_CONTEXT_CEILING_PCT", 40)

    # Bash: `pct=$((occ * 100 / window))` — integer truncation. Match exactly.
    pct = (occ * 100) // window
    if pct < ceiling:
        return 0, None, False

    label = _build_label(tool_name, tool_input)
    msg = _format_message(pct, window, ceiling, label)

    if os.environ.get("DEV_TEAM_CONTEXT_STRICT") == "on":
        return 2, f"{msg} [blocked: DEV_TEAM_CONTEXT_STRICT=on]", False

    # Warn mode with per-session per-5%-bucket dedupe.
    session = _sanitize_session(payload.get("session_id") or "")
    marker = _marker_path(session)
    bucket = pct // 5
    last_bucket = _read_last_bucket(marker)
    # Always write the marker (matches the .sh's `printf ... >"$marker"` that
    # runs before the bucket comparison).
    _write_bucket(marker, bucket)
    if bucket <= last_bucket:
        return 0, None, False

    return 0, msg, False


def main() -> int:
    raw = _read_stdin()
    payload = _load_input(raw)
    if payload is None:
        # Empty or malformed stdin → silent-pass, same as the .sh.
        return 0

    exit_code, message, _ = _resolve_verdict(payload)
    if message is not None:
        # The .sh uses `printf '%s\n' "$msg" >&2` — write to stderr with a
        # trailing newline.
        sys.stderr.write(message + "\n")
    return exit_code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
