#!/usr/bin/env python3
"""Python port of hooks/session-model-banner.sh (#586 / #572 Phase 2).

Claude Code SessionStart hook (the single one that owns model routing).
It:
    1. Captures the session model from the SessionStart payload and
       persists it to `.claude/session-model` so per-dispatch resolution
       can fall back to it. When the payload carries no model, reuses the
       last persisted value if one exists.
    2. Announces the effort band→model routing table on stderr, flagging
       any band whose model is more capable than the session model.
    3. Emits a one-line notification when the pending-review queue has
       unreviewed entries.

Replaces the retired overrides-banner.sh (one SessionStart hook, not two).

Env seams (TEST-ONLY):
    MODEL_ROUTING_JSON   defaults to <plugin>/knowledge/model-routing.json
    MODEL_LADDER_JSON    defaults to .claude/model-ladder.json
    SESSION_MODEL_FILE   defaults to .claude/session-model
    PENDING_REVIEW_FILE  defaults to <cwd>/metrics/pending-review.jsonl

Contract (docs/python-hook-contract.md):
    Input : SessionStart JSON on stdin (hook_event_name, cwd, model, ...).
    Output: banner text on stderr. Exit 0 always.
    Posture: fail-open — a buggy banner must never block a session.

Stdlib-only (json/os/re/pathlib/sys). Uses the sibling
hooks/lib/model_resolve.py module for band resolution (imports as a
Python module — no subprocess).

Refs: #572, #577.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import List, Optional

_HOOK_DIR = Path(__file__).resolve().parent
_LIB_DIR = _HOOK_DIR / "lib"

if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

try:
    import model_resolve  # type: ignore[import-not-found]

    _MODEL_RESOLVE_AVAILABLE = True
except ImportError:  # pragma: no cover
    _MODEL_RESOLVE_AVAILABLE = False


# Constrained token — matches the .sh's `[A-Za-z0-9._-]+`. A model ID that
# fails this regex is dropped rather than persisted.
_MODEL_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


# ---------------------------------------------------------------------------
# path seams
# ---------------------------------------------------------------------------


def _routing_json() -> Path:
    return Path(
        os.environ.get(
            "MODEL_ROUTING_JSON",
            str(_HOOK_DIR / ".." / "knowledge" / "model-routing.json"),
        )
    )


def _ladder_json() -> Path:
    return Path(os.environ.get("MODEL_LADDER_JSON", ".claude/model-ladder.json"))


def _session_model_file() -> Path:
    return Path(os.environ.get("SESSION_MODEL_FILE", ".claude/session-model"))


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> Optional[object]:
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def _ladder_is_valid() -> bool:
    data = _load_json(_ladder_json())
    if not isinstance(data, list) or len(data) == 0:
        return False
    return all(isinstance(x, str) for x in data)


def _ordered_models() -> List[str]:
    """Capability-ascending model list: ladder when valid, else the shipped
    default map values (low → medium → high)."""
    if _ladder_is_valid():
        data = _load_json(_ladder_json())
        assert isinstance(data, list)
        return [str(x) for x in data]
    routing = _load_json(_routing_json())
    if not isinstance(routing, dict):
        return []
    return [
        str(routing.get(band, ""))
        for band in ("low", "medium", "high")
        if isinstance(routing.get(band), str)
    ]


def _rank(target: str, ordered: List[str]) -> int:
    """1-based position of `target` in `ordered`; 0 if not present."""
    for i, m in enumerate(ordered, start=1):
        if m == target:
            return i
    return 0


def _extract_model(payload: dict) -> str:
    """`(.model // empty)` handling for both string and object-with-.id."""
    raw = payload.get("model")
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        v = raw.get("id")
        return v if isinstance(v, str) else ""
    return ""


def _resolve_band(band: str) -> str:
    if _MODEL_RESOLVE_AVAILABLE:
        try:
            if not _routing_json().is_file():
                return ""
            return model_resolve.resolve_band(
                band,
                routing_path=_routing_json(),
                ladder_path=_ladder_json(),
            )
        except Exception:  # pragma: no cover
            return ""
    return ""  # pragma: no cover


# ---------------------------------------------------------------------------
# banner rendering
# ---------------------------------------------------------------------------


def _render_banner(session_model: str, session_known: bool, reused: bool) -> str:
    ordered = _ordered_models()
    n = len(ordered)

    if n == 1:
        return (
            f"Model routing: all effort bands → {ordered[0]} "
            "(single-model environment).\n"
        )

    session_rank = 0
    if session_known:
        session_rank = _rank(session_model, ordered)

    lines: List[str] = ["Model routing (effort band → model):"]
    for band in ("low", "medium", "high"):
        m = _resolve_band(band)
        flag = ""
        if session_known and session_rank > 0:
            mrank = _rank(m, ordered)
            if mrank > session_rank:
                flag = "  ↑ above session model"
        lines.append(f"  {band:<7} → {m}{flag}")

    if not _ladder_is_valid():
        lines.append(
            f"No ladder ({_ladder_json()}) — using shipped defaults; "
            "create it to override the band→model map."
        )

    if not session_known:
        lines.append(
            "Session model unknown — upgrade flags and session fallback "
            "unavailable this session; effort routing still applies via "
            "the default map/ladder."
        )
    elif reused:
        lines.append(f"(using last known session model: {session_model})")

    return "\n".join(lines) + "\n"


def _notify_pending_findings(cwd: str) -> Optional[str]:
    """Count still-pending entries in the pending-review queue, rotating out
    disposed ones so the file stays bounded (#732).

    A finding gains exactly one disposition (`reviewed_at` on approval,
    `rejected_at` on rejection — see feedback-learning/SKILL.md); once either
    is present, its audit trail lives in metrics/config-changelog.jsonl (on
    approval) and the entry itself has no further use here. Rewriting the
    queue to drop disposed entries every SessionStart keeps it bounded to the
    outstanding backlog instead of growing without limit across the life of
    a project. Lines that fail to parse can't be classified either way, so
    they are left untouched — /session-review handles malformed-line
    reporting on its own.
    """
    queue_env = os.environ.get("PENDING_REVIEW_FILE")
    queue = (
        Path(queue_env) if queue_env else Path(cwd) / "metrics" / "pending-review.jsonl"
    )
    if not queue.is_file():
        return None
    try:
        with queue.open("r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        return None

    kept_lines: List[str] = []
    dropped_any = False
    count = 0
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            dropped_any = True
            continue
        try:
            entry = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            # Can't classify — keep it as-is rather than silently losing it.
            kept_lines.append(line)
            continue
        if isinstance(entry, dict) and (
            "reviewed_at" in entry or "rejected_at" in entry
        ):
            # Disposed — rotate it out of the queue.
            dropped_any = True
            continue
        if isinstance(entry, dict):
            count += 1
        kept_lines.append(line)

    if dropped_any:
        try:
            queue.write_text(
                "".join(f"{line}\n" for line in kept_lines), encoding="utf-8"
            )
        except OSError:
            pass

    if count <= 0:
        return None
    return (
        f"📋 {count} queued finding(s) from background analysis — "
        "run /session-review to review\n"
    )


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> int:
    try:
        raw = sys.stdin.read()
    except (OSError, ValueError):
        return 0
    if not raw:
        return 0
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return 0
    if not isinstance(payload, dict):
        return 0

    model = _extract_model(payload)
    if model and not _MODEL_ID_RE.match(model):
        model = ""

    file_path = _session_model_file()
    session_model = ""
    session_known = False
    reused = False
    if model:
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(model + "\n", encoding="utf-8")
        except OSError:
            pass
        session_model = model
        session_known = True
    elif file_path.is_file():
        try:
            with file_path.open("r", encoding="utf-8", errors="replace") as fh:
                session_model = fh.read().rstrip("\n")
        except OSError:
            session_model = ""
        if session_model:
            session_known = True
            reused = True

    cwd = payload.get("cwd") or ""
    if not isinstance(cwd, str) or not cwd or not Path(cwd).is_dir():
        cwd = os.getcwd()

    banner = _render_banner(session_model, session_known, reused)
    sys.stderr.write(banner)

    notice = _notify_pending_findings(cwd)
    if notice is not None:
        # The .sh emits this via `echo` to stdout — reproduce that channel.
        sys.stdout.write(notice)

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
