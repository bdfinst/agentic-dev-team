#!/usr/bin/env python3
"""churn_recurrence — commit-gap session-boundary heuristic (issue #2039).

Sibling module to `scripts/churn_coupling_report.py`, split out per the
plan's design note so the second, unrelated responsibility (cross-session
churn recurrence) doesn't grow that 735-line script into a god object.
`churn_coupling_report.py` -> `churn_recurrence.py` is the only allowed
import direction: this module never imports the `Commit` dataclass, and
takes plain `(sha, timestamp)` tuples or `{"sha", "timestamp"}` dicts
instead, matching this repo's `scripts/lib/` convention of taking plain
dict/list input rather than a caller-defined dataclass (see
`apply_severity_floors.py`).

No transcript data is available to this script, so "session" here is a
**commit-timestamp-gap proxy**, never the transcript-derived `session_id`
concept `session_extract.py` owns. To keep that distinction visible at every
call site, this module deliberately never uses the bare word "session" for
its own concept -- it is always `commit_session`.

## All-files cross-session ranking (Step 2.3, #2039)

`rank_all_files` ranks every historically-edited path -- not just the
test/subject pairs `churn_coupling_report.py`'s own `build_report` maps --
by how often it is revisited across a commit-gap boundary. It owns its own
`AllFilesRow` dataclass and its own `render_text`/`render_json` functions
rather than adding branches to `churn_coupling_report.py`'s existing
renderers, and excludes-filtering stays owned by the caller (which already
has `DEFAULT_EXCLUDES`/`is_excluded`): this module never re-implements glob
matching. A path whose commit history cannot be attributed to a current
working-tree path (deleted, or renamed mid-window with no clean path back)
is reported in `unattributed` -- a distinct key from the existing mode's
`unmapped`, and never scored 0.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta

#: Default gap, in hours, above which two chronologically-adjacent commits
#: touching the same file are treated as separate commit-sessions rather
#: than one continuous editing session.
DEFAULT_COMMIT_GAP_HOURS = 4.0


@dataclass
class AllFilesRow:
    """One ranked row of `rank_all_files`'s output.

    `cross_session` counts commit-sessions after the file's first (i.e. how
    many times it was *revisited* after a commit-gap boundary -- a file
    edited within a single commit-session, however many times, scores 0
    here). `within_session` is `edits - cross_session`: the file's first-ever
    edit plus every same-session continuation, none of which count as
    recurrence.
    """

    path: str
    edits: int
    within_session: int
    cross_session: int


def _normalize(commit) -> tuple[str, str]:
    """Read a `(sha, timestamp)` tuple or `{"sha", "timestamp"}` dict.

    Deliberately does not accept `churn_coupling_report.Commit` -- accepting
    that type here would create a two-way import dependency between the two
    modules.
    """
    if isinstance(commit, dict):
        return str(commit.get("sha", "")), str(commit.get("timestamp", ""))
    sha, timestamp = commit
    return str(sha), str(timestamp)


class TimestampError(ValueError):
    """A commit's timestamp is missing or unparseable for session partitioning.

    `churn_coupling_report.Commit.timestamp` defaults to `""` for call sites
    that never supplied one, and `datetime.fromisoformat` on that default (or
    on any malformed value) would otherwise raise a bare, unnamed
    `ValueError`. This repo's own convention (see
    `churn_coupling_report.Refusal`) is to name why a run cannot produce a
    trustworthy number rather than crash -- this is that name for this
    module's own boundary. `churn_coupling_report.py` converts it into a
    `Refusal` at its own call boundary rather than importing this class into
    a bare `except ValueError`.
    """

    def __init__(self, sha: str, timestamp: str, detail: str) -> None:
        super().__init__(detail)
        self.sha = sha
        self.timestamp = timestamp


def _parse_timestamp(sha: str, timestamp: str) -> datetime:
    if not timestamp:
        raise TimestampError(
            sha, timestamp, f"commit {sha!r} has no timestamp; cannot partition it into a commit-session"
        )
    try:
        return datetime.fromisoformat(timestamp)
    except ValueError as exc:
        raise TimestampError(
            sha, timestamp, f"commit {sha!r} has an unparseable timestamp {timestamp!r}: {exc}"
        ) from exc


def partition_commit_sessions(
    commits, commit_gap_hours: float = DEFAULT_COMMIT_GAP_HOURS
) -> list[list[dict[str, str]]]:
    """Partition one file's commits into commit-session groups.

    `commits` is a list of `(sha, timestamp)` tuples or `{"sha",
    "timestamp"}` dicts for a single file, with `timestamp` an ISO 8601
    string (the shape `churn_coupling_report.Commit.timestamp` carries,
    e.g. git's `%aI` author-date format). Input is expected to be
    chronologically sorted already; this function re-sorts ascending by
    timestamp regardless, so partitioning is correct even if the caller's
    ordering discipline is wrong -- a sorted input simply sorts to itself.

    Raises `TimestampError` when any commit's timestamp is empty or
    unparseable, rather than letting `datetime.fromisoformat` raise a bare
    `ValueError`.

    Returns a list of commit-session groups, each a list of `{"sha",
    "timestamp"}` dicts in ascending-time order. Two chronologically
    adjacent commits start a new commit-session when the gap between them
    is **greater than or equal to** `commit_gap_hours` -- an inclusive
    boundary, matching `churn_coupling_report.py`'s existing `--max-commits`
    inclusive-boundary convention (`len(commits) >= args.max_commits`). A
    gap strictly less than the threshold keeps both commits in the same
    commit-session.
    """
    if not commits:
        return []

    parsed = sorted(
        ((sha, ts, _parse_timestamp(sha, ts)) for sha, ts in (_normalize(c) for c in commits)),
        key=lambda item: item[2],
    )

    threshold = timedelta(hours=commit_gap_hours)
    sessions: list[list[dict[str, str]]] = [
        [{"sha": parsed[0][0], "timestamp": parsed[0][1]}]
    ]
    previous_ts = parsed[0][2]

    for sha, ts_str, ts in parsed[1:]:
        if ts - previous_ts >= threshold:
            sessions.append([{"sha": sha, "timestamp": ts_str}])
        else:
            sessions[-1].append({"sha": sha, "timestamp": ts_str})
        previous_ts = ts

    return sessions


def _normalize_all_files_commit(commit) -> tuple[str, frozenset, str]:
    """Read a `(sha, paths, timestamp)` tuple or `{"sha", "paths",
    "timestamp"}` dict -- the shape `churn_coupling_report.py` converts its
    `Commit` objects into at the call boundary (never the `Commit` type
    itself; see the module docstring).
    """
    if isinstance(commit, dict):
        sha = str(commit.get("sha", ""))
        paths = frozenset(commit.get("paths", ()))
        timestamp = str(commit.get("timestamp", ""))
        return sha, paths, timestamp
    sha, paths, timestamp = commit
    return str(sha), frozenset(paths), str(timestamp)


def rank_all_files(
    commits, tracked, commit_gap_hours: float = DEFAULT_COMMIT_GAP_HOURS
) -> dict:
    """Rank every historically-edited path by cross-session recurrence.

    `commits` is the full scanned window as `(sha, paths, timestamp)` tuples
    or `{"sha", "paths", "timestamp"}` dicts -- already excludes-filtered by
    the caller (this module never re-implements `churn_coupling_report.py`'s
    glob matching). `tracked` is the set of currently-tracked working-tree
    paths: a path not in it cannot be attributed to a current file (deleted,
    or renamed mid-window with no clean path back) and is reported in
    `unattributed` instead of being ranked or scored -- mirroring
    `build_report`'s unmapped-is-not-zero rule, under a distinct key.

    Returns a dict with `commits_scanned`, `files_seen` (every distinct
    historically-edited path, ranked plus unattributed), `rows` (a list of
    `AllFilesRow`, sorted by cross-session count descending, then edits
    descending, then path -- mirroring `build_report`'s own tie-break
    ordering), and `unattributed` (a list of `{"path", "edits"}` dicts,
    sorted the same way `build_report` sorts `unmapped`).
    """
    commits = list(commits)
    per_path: dict[str, list[tuple[str, str]]] = {}
    for sha, paths, timestamp in (_normalize_all_files_commit(c) for c in commits):
        for path in paths:
            per_path.setdefault(path, []).append((sha, timestamp))

    tracked_set = set(tracked)
    rows: list[AllFilesRow] = []
    unattributed: list[dict] = []
    for path, path_commits in per_path.items():
        edits = len(path_commits)
        if path not in tracked_set:
            unattributed.append({"path": path, "edits": edits})
            continue
        sessions = partition_commit_sessions(path_commits, commit_gap_hours=commit_gap_hours)
        cross_session = max(len(sessions) - 1, 0)
        rows.append(
            AllFilesRow(
                path=path,
                edits=edits,
                within_session=edits - cross_session,
                cross_session=cross_session,
            )
        )

    rows.sort(key=lambda r: (-r.cross_session, -r.edits, r.path))
    unattributed.sort(key=lambda u: (-u["edits"], u["path"]))

    return {
        "commits_scanned": len(commits),
        "files_seen": len(per_path),
        "rows": rows,
        "unattributed": unattributed,
    }


def append_hidden_note(lines: list, total: int, top: int) -> None:
    """Append a "... and N more" note when `total` exceeds `top`.

    Named, not dropped: `--top` caps the display, and `--json` still carries
    every entry. Shared by this module's `render_text` and
    `churn_coupling_report.render_text` -- both had the identical inline
    block before it was extracted here (the one-way import direction is
    `churn_coupling_report.py` -> `churn_recurrence.py`, so the shared
    helper lives on this side).
    """
    hidden = total - top
    if hidden > 0:
        lines.append(f"  ... and {hidden} more (raise --top, or use --json)")


def render_json(report, top) -> str:
    payload = dict(report)
    payload["rows"] = [
        {
            "rank": index,
            "path": row.path,
            "edits": row.edits,
            "within_session": row.within_session,
            "cross_session": row.cross_session,
        }
        for index, row in enumerate(report["rows"][:top], start=1)
    ]
    return json.dumps(payload, indent=2, sort_keys=True)


def render_text(report, top) -> str:
    lines = []
    window = report["window"]
    lines.append(
        f"Cross-session churn recurrence  window: {window}  commits scanned: "
        f"{report['commits_scanned']}"
    )
    if report.get("truncated"):
        lines.append(
            "  NOTE: --max-commits truncated the window; counts describe the "
            "scanned slice, not the full window."
        )
    lines.append(
        f"  files touched: {report['files_seen']}  "
        f"ranked: {len(report['rows'])}  unattributed: {len(report['unattributed'])}"
    )
    lines.append("")

    rows = report["rows"][:top]
    if not rows:
        lines.append("No file recurred across a commit-session boundary in this window.")
    else:
        header = f"{'#':>3}  {'edits':>5} {'within':>6} {'cross':>5}  path"
        lines.append(header)
        lines.append("-" * len(header))
        for index, row in enumerate(rows, start=1):
            lines.append(
                f"{index:>3}  {row.edits:>5} {row.within_session:>6} "
                f"{row.cross_session:>5}  {row.path}"
            )

    if report["unattributed"]:
        lines.append("")
        lines.append(
            f"Unattributed ({len(report['unattributed'])}) -- commit history could not be "
            "attributed to a current working-tree path (deleted, or renamed mid-window "
            "with no clean path back), so NOT scored:"
        )
        for item in report["unattributed"][:top]:
            lines.append(f"  {item['edits']:>5} edits  {item['path']}")
        append_hidden_note(lines, len(report["unattributed"]), top)

    lines.append("")
    lines.append(
        "Reading it: a high cross-session count means the file keeps getting revisited "
        "across separate commit-sessions -- recurring rework, not one continuous edit. "
        "This report ranks; it does not decide what to do about a row."
    )
    return "\n".join(lines)
