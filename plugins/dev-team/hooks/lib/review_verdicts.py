"""review_verdicts.py — per-lens review verdict store (#2166).

Records, per genuine review-agent dispatch, an outcome (`pass` | `findings`)
bound to `(lens, file_path, file_content_hash)` — NOT per-diff (Decision 3,
plans/2164-verdict-ledger-writer.md): a verdict row answers "did this lens
pass this exact file content", so it can be looked up again the next time the
same file content recurs, regardless of which diff produced it.

A deliberate sibling of `hooks/lib/boundary_events.py`, not an extension of
it (Decision 1): `boundary_events.py`'s own docstring forbids ever writing a
real `file_path` into that stream ("Never write free text ... file paths ...
must never appear"), so a per-file verdict needs its own store,
`.claude/metrics/review-verdicts.jsonl`, written via the same
`atomic_state.append_line_locked` primitive `boundary_events.py` uses.

ALWAYS-ON (Decision 2): unlike `telemetry.py`, this stream is not gated by
`DEV_TEAM_TELEMETRY`/`~/.claude/telemetry.json` consent — same posture as
`boundary-events.jsonl` itself, for the same reason (local-only, mechanical
accountability data: lens/path/hash/outcome, no prose).

Fail-open: every exception in `emit_review_verdict()` is swallowed. A full
disk, read-only `.claude/metrics/`, or malformed state must never change the
calling hook's stdout, stderr, or exit code. `load_verdicts()` never raises
either — an absent file, a corrupted line, or a stale `plugin_version` row
all degrade to "no usable rows" rather than an exception.

`load_verdicts()` remains unconsumed in this slice (Step 2.2) — Step 2.3's
`hooks/review_verdict_recorder.py` is a writer only, it never calls
`load_verdicts()`; `#2167` (a not-yet-built slice) is the first intended
consumer; see this module's own test
`test_load_verdicts_has_no_other_consumers` for the mechanical check that
enforces that boundary.

Stdlib only. See ADR 0014 / ADR 0015.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import artifact_paths
import atomic_state
import plugin_version

_LOG_NAME = "review-verdicts.jsonl"

# The literal text prefix `skills/code-review/SKILL.md` step 4 renders into
# each per-agent dispatch prompt (`Files in scope for this review: <path>,
# ...`) and that Step 2.3's SubagentStop verdict recorder parses back out of
# the transcript. Sharing one constant between the renderer's test (Step 2.1)
# and the future parser (Step 2.3) keeps the marker format and its parser
# from silently drifting apart.
SCOPE_MARKER_PREFIX = "Files in scope for this review: "


def _isoformat_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def emit_review_verdict(
    cwd,
    lens: str,
    file_path: str,
    file_content_hash: str,
    outcome: str,
    session_id: str | None = None,
) -> None:
    """Append one compact JSON line to
    `<cwd>/.claude/metrics/review-verdicts.jsonl`.

    Unconditional (Decision 2) — no consent check. Fail-open: any error (bad
    `cwd`, unwritable `.claude/metrics/`, disk full, etc.) is swallowed
    silently, matching `emit_boundary_event`'s own contract.

    Args:
        cwd: Directory whose `.claude/metrics/` subdirectory receives the
            row. Accepts `str` or `Path`.
        lens: The review agent's name (e.g. "security-review").
        file_path: The in-scope file this verdict is about.
        file_content_hash: Content hash of `file_path` at review time.
        outcome: `"pass"` or `"findings"`.
        session_id: Optional opaque session ID from the hook payload.
    """
    try:
        base = Path(cwd) if cwd else Path.cwd()
        log = artifact_paths.resolve_file("metrics", _LOG_NAME, base)
        log.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "ts": _isoformat_utc(),
            "lens": lens,
            "file_path": file_path,
            "file_content_hash": file_content_hash,
            "outcome": outcome,
            "plugin_version": plugin_version.shipped_version(),
        }
        if session_id:
            payload["session_id"] = session_id

        line = json.dumps(payload, separators=(",", ":")) + "\n"
        atomic_state.append_line_locked(log, line)
    except Exception:  # noqa: BLE001, S110 — fail-open by design, see module docstring
        pass


def _version_tuple(version: object) -> tuple[int, ...] | None:
    """Parse a dotted numeric version string into a comparable tuple, or
    `None` when it isn't one (e.g. the `"unknown"` fallback
    `plugin_version.shipped_version()` can return)."""
    if not isinstance(version, str) or not version:
        return None
    parts: list[int] = []
    for segment in version.split("."):
        if not segment.isdigit():
            return None
        parts.append(int(segment))
    return tuple(parts) if parts else None


def _is_usable_version(row_version: object, current_version: str) -> bool:
    """A row is usable when its `plugin_version` is the current one, or a
    numerically parseable version no older than it. Anything else — a
    strictly older version, or a value that fails to parse and isn't an
    exact string match — is treated as stale/unusable (fail toward
    excluding, never toward raising)."""
    if row_version == current_version:
        return True
    row_tuple = _version_tuple(row_version)
    current_tuple = _version_tuple(current_version)
    if row_tuple is None or current_tuple is None:
        return False
    return row_tuple >= current_tuple


def load_verdicts(cwd) -> list[dict]:
    """Read `<cwd>/.claude/metrics/review-verdicts.jsonl` and return its
    usable rows.

    "Usable" excludes: an absent file, a line that isn't valid JSON, a line
    that isn't a JSON object, and a row whose `plugin_version` is older than
    `plugin_version.shipped_version()`. Never raises — every failure mode
    degrades to an empty (or partial) list.
    """
    try:
        base = Path(cwd) if cwd else Path.cwd()
        log = artifact_paths.resolve_file("metrics", _LOG_NAME, base, migrate=False)
        if not log.is_file():
            return []
        text = log.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001 — fail-open by design, see module docstring
        return []

    current_version = plugin_version.shipped_version()
    rows: list[dict] = []
    for raw_line in text.splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            row = json.loads(raw_line)
        except ValueError:
            continue
        if not isinstance(row, dict):
            continue
        if not _is_usable_version(row.get("plugin_version"), current_version):
            continue
        rows.append(row)
    return rows
