"""session_report_shared.py — building blocks common to both
session_report.py profiles (maintainer and downstream).

Split out of session_report.py (issue #2098) so the unified CLI has clear
domain layering: this module holds only what BOTH profiles need — the
session_log vocabulary aliases, schema constants, plugin-version resolution,
correction-cause classification, and skill/agent registry loading —
so session_report_maintainer.py and session_report_downstream.py each
import from here instead of each carrying their own copy.

PATH RESOLUTION (ADR 0032): this module lives at
plugins/dev-team/scripts/lib/, one level deeper than session_report.py
itself, so its own __file__-relative path resolution needs one more
`.parent` than the top-level CLI's did before the split.

Stdlib only (Python 3.10+ floor, ADR 0031).
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))
from session_log import classify, corrections, discovery, records, redact, signals

_redact = redact.redact

# --------------------------------------------------------------------------
# Shared classification/signal vocabulary (session_log.classify/.signals,
# issues #2042-#2044). Identical aliases in both predecessor scripts;
# defined once here and used, unmodified, by both profiles' extract logic.
# --------------------------------------------------------------------------
_VERIFY_RE = classify.VERIFY_RE
_CORRECTION_RE = classify.CORRECTION_RE
_PERMISSION_RE = classify.PERMISSION_RE
_OLDSTRING_RE = classify.OLDSTRING_RE
_EDIT_TOOLS = signals.EDIT_TOOLS
_GIT_GLOBAL_OPTS_WITH_ARG = classify.GIT_GLOBAL_OPTS_WITH_ARG
_COMMIT_BYPASS_TOKENS = classify.COMMIT_BYPASS_TOKENS
_statement_break_newlines = classify.statement_break_newlines
_bash_segments = classify.bash_segments
_is_git_commit_argv = classify.is_git_commit_argv
_SAFE_NAME_RE = classify.SAFE_NAME_RE
_UNSAFE_NAME = classify.UNSAFE_NAME
_HARNESS_ATTRIBUTIONS = classify.HARNESS_ATTRIBUTIONS
_MAIN_LABEL = "main"
_UNATTRIBUTED_LABEL = "unattributed"
_strip_ns = classify.strip_ns
_text_of = classify.text_of

_is_transcript_path = discovery.is_transcript_path
_is_subagent_transcript = discovery.is_subagent_transcript
# Two alias names for the same function (discovery.all_transcripts),
# matching each predecessor's own naming so each profile's body is
# otherwise unmodified.
_all_transcripts_under = discovery.all_transcripts
_all_transcripts = discovery.all_transcripts
_sorted_paths = discovery.sorted_paths
_relative_parts = discovery.relative_parts

_track_tool_call = signals.track_tool_call
_classify_tool_result = signals.classify_tool_result
_track_edit = signals.track_edit
_track_bash = signals.track_bash
_new_thread = signals.new_thread
_detect_correction_turn = signals.detect_correction_turn
_new_agent_bucket = signals.new_agent_bucket
_merge_agent_buckets = signals.merge_agent_buckets
_finalize_agent_buckets = signals.finalize_agent_buckets
_CONTEXT_TOKEN_FIELDS = signals.CONTEXT_TOKEN_FIELDS
_AGENT_BUCKET_FIELDS = signals.AGENT_BUCKET_FIELDS
_accumulate_skill_agent_signals = signals.accumulate_skill_agent_signals
_slim = records.slim_by_name
_iter_file_records = records.iter_file_records

# --------------------------------------------------------------------------
# Correction cause-data classification (session_log.corrections, #2013).
# --------------------------------------------------------------------------
_new_correction_context = corrections.new_context
_observe_assistant_turn = corrections.observe_assistant_turn
_classify_correction = corrections.classify_correction

_VERSION_RE = re.compile(r"^[0-9A-Za-z._+-]{1,32}$")

# --------------------------------------------------------------------------
# Schema versioning. See session_report.py's module docstring: both profiles
# bump to v3; the still-present predecessor scripts kept emitting v2
# unchanged (both predecessors were later retired in #2048).
# --------------------------------------------------------------------------
_DIGEST_SCHEMA = "session-digest/v4"
_SYNC_SCHEMA = "session-sync/v4"
#: Sync-record schemas a reader accepts, oldest first. Exported so
#: scripts/eval_rawlog.py (and any other reader) imports this constant
#: instead of literal-matching a schema string — the ADR 0036 failure mode
#: this guards against is a writer bumping the stamped schema while a
#: reader still exact-matches the old one, which silently drops every
#: record instead of erroring.
SYNC_SCHEMAS = (
    "session-sync/v1",
    "session-sync/v2",
    "session-sync/v3",
    "session-sync/v4",
)
_DOWNSTREAM_SCHEMA = "downstream-session-report/v4"


def _load_plugin_version(plugin_root: Path | None = None) -> str:
    """Read `.claude-plugin/plugin.json`'s version. `plugin_root` defaults
    to the dev-team plugin root (`plugins/dev-team/`) since both profiles
    now resolve it the same way."""
    if plugin_root is None:
        plugin_root = Path(__file__).resolve().parent.parent.parent
    manifest = Path(plugin_root) / ".claude-plugin" / "plugin.json"
    try:
        if manifest.stat().st_size > 64_000:
            return "unknown"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        version = data.get("version")
        if isinstance(version, str) and _VERSION_RE.match(version):
            return version
    except (OSError, ValueError):
        pass
    return "unknown"


def _new_correction_causes_state() -> dict:
    """Fresh accumulator for correction cause-data (#2013): three label
    Counters plus the ambiguous-shape tally, scoped to one `extract_*()`
    call (across every transcript file it processes) -- NOT reset per
    file, unlike `turn_context`/`active`/`thread` in each profile's loop."""
    return {"by_what": Counter(), "by_component": Counter(), "by_shape": Counter(), "ambiguous": 0}


def _record_correction_cause(state: dict, turn_context: dict, dispatch, text: str) -> None:
    """Classify one detected correction turn and fold it into `state`."""
    cause = _classify_correction(turn_context, dispatch, text)
    state["by_what"][cause["what"]] += 1
    state["by_component"][cause["component"]] += 1
    state["by_shape"][cause["shape"]] += 1
    if cause["confidence"] == "low":
        state["ambiguous"] += 1


def _finalize_correction_causes(state: dict, correction_turns: int) -> dict:
    """The `accuracy.correction_causes` object: three sorted label
    breakdowns plus the honest inference-share statistic (issue #2013
    acceptance: "the inference share reported rather than hidden")."""
    return {
        "by_what": dict(sorted(state["by_what"].items())),
        "by_component": dict(sorted(state["by_component"].items())),
        "by_shape": dict(sorted(state["by_shape"].items())),
        "ambiguous_share": round(state["ambiguous"] / correction_turns, 4)
        if correction_turns
        else 0.0,
    }


def _correction_rate_map(numerator: Counter, denominator: Counter) -> dict:
    """Correction RATE per dispatch/invocation (issue #2013 acceptance:
    "correction rate per dispatch is queryable by agent and by skill"),
    mirroring `signals.finalize_agent_buckets`'s `context_per_dispatch`
    pattern: a name with zero dispatches contributes no entry at all
    (never a 0.0 that would misrank an uninvoked skill/agent as
    "corrected 0% of the time")."""
    return {
        name: round(numerator.get(name, 0) / n, 4)
        for name, n in sorted(denominator.items())
        if n
    }


def _first_cwd(jsonl: Path) -> str | None:
    try:
        with jsonl.open(encoding="utf-8") as fh:
            for _ in range(20):
                line = fh.readline()
                if not line:
                    break
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rec_cwd = rec.get("cwd")
                if isinstance(rec_cwd, str) and rec_cwd:
                    return rec_cwd
    except OSError:
        pass
    return None


def resolve_session_plugin_version(session_id: str, boundary_events_path: Path) -> str:
    """Per-session plugin_version resolver (#2018).

    Correlates `session_id` against its own `boundary-events.jsonl` records
    — a stream `hooks/lib/boundary_events.py::emit_boundary_event` stamps
    LIVE, at hook-dispatch time, with the plugin version actually checked
    out at that moment (`boundary_events._load_plugin_version`, ~line 79 of
    that module). This is the one place a session's OWN version is
    recoverable at all — transcripts themselves carry no version tag.

    Choice — EARLIEST matching event by `ts` wins: a session's plugin
    version is ordinarily constant for its whole duration (the checked-out
    plugin doesn't change mid-session in the common case), so any matching
    event would agree: earliest is picked because it is the version active
    at the point the session first did dispatched work, the most
    defensible single answer for "which release produced this session's
    signals" when the session's activity happens to span more than one
    event. Documented limitation, deliberately not solved here: a session
    that runs `/dev-team:upgrade` (or otherwise changes the checked-out
    plugin) mid-session will have GENUINELY DIFFERENT versions among its
    own boundary-events, and this resolver reports only the first — there
    is no single correct answer for a session that spans two releases, and
    picking one is a documented trade-off, not an oversight.

    Falls back to the explicit string `"unknown"` — NEVER a live
    `plugin.json` read — when the file is missing, unreadable, has no
    record for this `session_id`, or every matching record's own
    `plugin_version` fails validation (`_VERSION_RE`, the same bound this
    module applies to every other externally-supplied version string).

    Shared by both profiles: the maintainer profile's `cmd_sync` uses it to
    stamp per-session sync records with the version that actually produced
    them (#2018); the downstream profile's own version-filter machinery
    (`sessions_matching_plugin_version`/`_sessions_with_known_plugin_version`)
    solves a related but different question and lives in
    session_report_downstream.py."""
    best_ts: str | None = None
    best_version: str | None = None
    for rec in _iter_file_records(boundary_events_path):
        if str(rec.get("session_id") or "") != session_id:
            continue
        version = rec.get("plugin_version")
        if not (isinstance(version, str) and _VERSION_RE.match(version)):
            continue
        ts = rec.get("ts")
        if not isinstance(ts, str):
            continue
        if best_ts is None or ts < best_ts:
            best_ts = ts
            best_version = version
    return best_version or "unknown"


def load_registry(plugin_root: Path | None = None) -> dict:
    """Enumerate shipped skills/agents so a digest/report can name
    never-observed ones. `plugin_root` defaults the same way as
    `_load_plugin_version` above."""
    if plugin_root is None:
        plugin_root = Path(__file__).resolve().parent.parent.parent
    skills_dir = Path(plugin_root) / "skills"
    agents_dir = Path(plugin_root) / "agents"
    skills = sorted(p.name for p in skills_dir.iterdir()) if skills_dir.is_dir() else []
    agents = (
        sorted(p.stem for p in agents_dir.glob("*.md")) if agents_dir.is_dir() else []
    )
    return {"skills": skills, "agents": agents}
