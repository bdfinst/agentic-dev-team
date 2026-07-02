#!/usr/bin/env python3
"""Python port of hooks/agent-model-resolve.sh (#585 / #572 Phase 2).

PreToolUse hook on the `Agent` matcher. Resolves an agent's effort band to
a concrete model before any sub-agent dispatch reaches the harness, then
rewrites `tool_input.model` so the harness dispatches on it.

Emits one of:
  - rewrite:      {"hookSpecificOutput":{"hookEventName":"PreToolUse",
                    "updatedInput": {...tool_input with model set...}}}
  - pass-through: {}

Resolution order for an Agent dispatch:
  1. Strip any "<plugin>:" prefix from subagent_type.
  2. Read the effort band from agents/<name>.md frontmatter and resolve it
     via hooks/lib/model_resolve.py (default map or ladder). ALWAYS rewrite
     the model — effort agents declare no model: of their own.
  3. If the agent declares no effort band, fall back to a legacy
     tool_input.model tier (haiku|sonnet|opus → band) and rewrite, marking
     the dispatch as legacy in the bump log.
  4. If tool_input.model is an explicit snapshot that a present ladder does
     NOT contain, fall back to the session model. With no ladder, or a
     snapshot the ladder has, pass it through untouched.
  5. Unreadable/unknown agent with no usable band/model → pass-through.

Session model is never a ceiling: a high-effort agent maps to the top of
the ladder even when the session started on a lower model.

Bump logging is owned HERE (single site): the resolver no longer logs. A
JSONL line is appended when the resolved model differs from the band's
shipped default (a ladder override / upgrade / downgrade), always for a
legacy-tier dispatch (deprecation marker), and for a session-model
fallback.

Posture: fail-open on any parse/internal/resolver error → empty stdout,
exit 0. A buggy hook (or a missing routing.json) must never block dispatch.

Contract (docs/python-hook-contract.md):
    Input : PreToolUse JSON on stdin (session_id, tool_name, tool_input)
    Output: JSON line on stdout — either the rewrite envelope or `{}`
    Exit  : 0 always

Stdlib-only (json/os/pathlib/re/sys). Uses the sibling
`hooks/lib/model_resolve.py` module for the resolver call (imports it as
a Python module — no subprocess needed).

Refs: #572, #577.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_HOOK_DIR = Path(__file__).resolve().parent
_LIB_DIR = _HOOK_DIR / "lib"

# Load the resolver as a Python module. Falls back to a subprocess dispatch
# if the module cannot be imported (unusual — should not happen in tree).
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

try:
    import model_resolve  # type: ignore[import-not-found]

    _MODEL_RESOLVE_AVAILABLE = True
except ImportError:  # pragma: no cover
    _MODEL_RESOLVE_AVAILABLE = False


# ---------------------------------------------------------------------------
# path seams (env-driven; defaults mirror the .sh)
# ---------------------------------------------------------------------------


def _routing_json() -> Path:
    return Path(
        os.environ.get(
            "MODEL_ROUTING_JSON",
            str(_HOOK_DIR / ".." / "knowledge" / "model-routing.json"),
        )
    )


def _agents_dir() -> Path:
    return Path(
        os.environ.get(
            "MODEL_AGENTS_DIR",
            str(_HOOK_DIR / ".." / "agents"),
        )
    )


def _ladder_json() -> Path:
    return Path(
        os.environ.get(
            "MODEL_LADDER_JSON",
            ".claude/model-ladder.json",
        )
    )


def _session_model_file() -> Path:
    return Path(
        os.environ.get(
            "SESSION_MODEL_FILE",
            ".claude/session-model",
        )
    )


def _bump_log() -> Path:
    return Path(
        os.environ.get(
            "MODEL_BUMP_LOG",
            ".claude/metrics/model-routing.log",
        )
    )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_EFFORT_RE = re.compile(r"^effort:[ \t]*(.*)$")
_FRONTMATTER_DELIM_RE = re.compile(r"^---[ \t]*$")


def _read_effort(agent_file: Path) -> str:
    """Extract the effort band from an agent file's YAML frontmatter.

    Returns "" when the file is unreadable or declares no effort. Matches
    the .sh's awk pipeline byte-for-byte: only the FIRST-line `---` opens
    the frontmatter, the second `---` closes it (or exits), and the
    effort value has all whitespace and quotes stripped.
    """
    try:
        with agent_file.open("r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        return ""
    if not lines:
        return ""
    infm = False
    for idx, raw in enumerate(lines):
        line = raw.rstrip("\n")
        if idx == 0 and line == "---":
            infm = True
            continue
        if infm and line == "---":
            return ""
        if infm:
            m = _EFFORT_RE.match(line)
            if m:
                val = m.group(1)
                val = re.sub(r"[\"'\s]", "", val)
                return val
    return ""


def _snapshot_in_ladder(snap: str) -> bool:
    """True iff `snap` is a model ID present in the ladder file.

    Delegates band-normalization/JSON-loading/ladder-validity to
    hooks/lib/model_resolve.py (#732) rather than keeping local, driftable
    copies of those helpers.
    """
    if not model_resolve.ladder_is_valid(_ladder_json()):
        return False
    data = model_resolve.load_json(_ladder_json())
    assert isinstance(data, list)
    return snap in data


def _session_model() -> str:
    path = _session_model_file()
    if not path.is_file():
        return ""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return ""
    return first.rstrip("\n")


def _log_bump(band: str, served: str, reason: str, caller: str, session: str) -> None:
    """Append one JSONL line to the bump log. Silent on any IO error."""
    log = _bump_log()
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # jq -nc emits keys in declaration order, so build the object in the
    # same order the .sh uses.
    payload = {
        "ts": ts,
        "band": band,
        "served": served,
        "reason": reason,
        "caller": caller,
        "session": session,
    }
    try:
        with log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, separators=(",", ":")) + "\n")
    except OSError:
        return


# ---------------------------------------------------------------------------
# resolver call — prefer the imported module; else subprocess fallback.
# ---------------------------------------------------------------------------


def _resolve_band(band: str) -> str:
    """Return the resolved snapshot for a band, or "" on any error."""
    if _MODEL_RESOLVE_AVAILABLE:
        try:
            # model_resolve.resolve_band handles routing.json presence
            # internally — but the .sh's fail-open contract requires that
            # we treat any exception (missing routing, bad JSON) as ''.
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
# stdout emitters
# ---------------------------------------------------------------------------


def _emit_pass_through() -> None:
    sys.stdout.write("{}\n")


def _emit_rewrite(payload: dict, new_model: str) -> None:
    """Print the updatedInput envelope rewriting tool_input.model.

    Fail-open: an unusable payload → pass-through rather than a partial
    line. The .sh emits compact JSON via `jq -c`; match that by using
    separators=(",", ":").
    """
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        _emit_pass_through()
        return
    updated = dict(tool_input)
    updated["model"] = new_model
    envelope = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "updatedInput": updated,
        }
    }
    sys.stdout.write(json.dumps(envelope, separators=(",", ":")) + "\n")


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

    tool_name = payload.get("tool_name") or ""
    if tool_name != "Agent":
        return 0

    if not _MODEL_RESOLVE_AVAILABLE:  # pragma: no cover
        # Sibling hooks/lib/model_resolve.py should always ship alongside
        # this file; if it's somehow missing, fail open rather than raise.
        _emit_pass_through()
        return 0

    tool_input = (
        payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    )
    requested_model = tool_input.get("model") or ""
    subagent_type = tool_input.get("subagent_type") or ""
    if not isinstance(requested_model, str):
        requested_model = ""
    if not isinstance(subagent_type, str):
        subagent_type = ""

    # Strip any "<plugin>:" prefix.
    agent_name = (
        subagent_type.split(":", 1)[-1] if ":" in subagent_type else subagent_type
    )

    effort = ""
    if _SAFE_NAME_RE.match(agent_name):
        effort = _read_effort(_agents_dir() / f"{agent_name}.md")

    band = ""
    reason = ""
    explicit_snapshot = ""
    if effort:
        band = model_resolve.normalize_band(effort)
        reason = "effort"
    elif requested_model:
        band = model_resolve.normalize_band(requested_model)
        if band:
            reason = "legacy-tier"
        else:
            explicit_snapshot = requested_model

    session = _session_model()

    if not band:
        # Explicit out-of-ladder snapshot → session fallback.
        if (
            explicit_snapshot
            and model_resolve.ladder_is_valid(_ladder_json())
            and not _snapshot_in_ladder(explicit_snapshot)
            and session
        ):
            _log_bump("", session, "session-fallback", agent_name, session)
            _emit_rewrite(payload, session)
            return 0
        _emit_pass_through()
        return 0

    resolved = _resolve_band(band)
    if not resolved:
        _emit_pass_through()
        return 0

    # Bump logging (single site).
    routing = _routing_json()
    default_snapshot = ""
    if routing.is_file():
        data = model_resolve.load_json(routing)
        if isinstance(data, dict):
            v = data.get(band)
            if isinstance(v, str):
                default_snapshot = v
    if reason == "legacy-tier" or resolved != default_snapshot:
        _log_bump(band, resolved, reason, agent_name, session)

    _emit_rewrite(payload, resolved)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
