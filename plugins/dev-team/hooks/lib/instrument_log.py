"""instrument_log — fail-open JSONL rows for benefit-measurement streams (#2201).

The smallest logging addition that makes a number exist: each caller appends
one compact row to a named ``.claude/metrics/<stream>.jsonl`` and nothing
else changes — no stdout, no exit code, no control flow. Any failure (bad
cwd, unwritable directory, disk full) is swallowed. Streams and row shapes
are documented in ``knowledge/telemetry-schema.md``.

Kept separate from ``boundary_events.py`` on purpose: a ``record`` row there
is read by the review-gate corroboration path, so observational measurement
rows must not share that stream.

Stdlib-only. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import artifact_paths
import plugin_version

#: Closed set of stream names this module may write.
STREAMS = frozenset({
    "subagent-stops",
    "skill-injection",
    "ledger-skips",
    "checkpoint-aborts",
})


#: Environment variables that carry the session id to a script run outside a
#: hook, first non-blank wins. Claude Code exports the first into the Bash
#: tool's environment (checked by running a CLI emitter from a live session);
#: the second is the hook variable in docs/python-hook-contract.md.
SESSION_ENV_VARS = ("CLAUDE_CODE_SESSION_ID", "CLAUDE_SESSION_ID")


def env_session_id() -> str | None:
    """The current session id from the environment, or None. For CLI emitters
    that have no hook payload to read it from."""
    for name in SESSION_ENV_VARS:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return None


def append_row(stream: str, row: dict, cwd: str | Path | None = None,
               session_id: str | None = None) -> bool:
    """Append ``row`` (plus ``ts``/``plugin_version``/``session_id``) to
    ``.claude/metrics/<stream>.jsonl``. Returns whether a row was written;
    never raises."""
    if stream not in STREAMS:
        return False
    try:
        base = Path(cwd) if cwd else Path.cwd()
        log = artifact_paths.resolve_file("metrics", f"{stream}.jsonl", base)
        log.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "plugin_version": plugin_version.shipped_version(),
            **row,
        }
        if session_id:
            payload["session_id"] = session_id
        line = json.dumps(payload, separators=(",", ":")) + "\n"
        fd = os.open(log, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, line.encode("utf-8"))
        finally:
            os.close(fd)
        return True
    except Exception:  # noqa: BLE001 — fail-open by design, see module docstring
        return False
