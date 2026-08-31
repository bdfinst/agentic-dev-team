#!/usr/bin/env python3
"""Unified session-log report CLI (epic #2040, issue #2046).

One shipped entry point over the ``session_log`` package, with two profiles
selected by ``--profile``:

``--profile maintainer``
    Replaces ``scripts/session_extract.py`` (monorepo-only developer
    tooling: feeds ``/session-review`` and the ``session-digest.jsonl``
    trend stream this repo uses to judge its own harness). Emits
    ``session-digest/v4``. Retains every mode that exists nowhere else:
    ``--sync-out``/``--watermark``/``--host``, ``--rollup``, ``--cost-log``,
    ``--escalate``, ``--correlate``, ``--append``, ``--all-projects``,
    ``--transcript``, ``--project-dir``, ``--cwd``, ``--pricing``,
    ``--plugin-root``.

``--profile downstream``
    Replaces ``plugins/dev-team/scripts/extract_session_report.py`` (the
    standalone, shippable report any dev-team user can hand to the plugin
    maintainer). Emits ``downstream-session-report/v4``. Retains
    ``--project``, ``--all-projects``, ``--since DAYS``, ``--until``,
    ``--plugin-version``, ``--out``.

Because this script ships under ``plugins/dev-team/scripts/`` (unlike its
monorepo-only predecessor), the maintainer profile is now available to a
normally-installed plugin — closing #1779 at the root instead of guarding it
per-invocation as PR #1820 did.

SCHEMA VERSIONING: both profiles bump to v3 (from v2) purely as a version
label on this new, unified entry point — the still-present, still-working
predecessor scripts (retired in #2048) are UNCHANGED and continue emitting
v2. ``SYNC_SCHEMAS`` is the one exported constant naming every sync-record
schema a reader (``_read_synced_records``/``rollup``) accepts; no call site
literal-matches a schema string. See ADR 0036 for why a half-applied bump
(a writer stamping a new version while a reader still exact-matches the old
one) silently drops data rather than erroring.

v3 -> v4 (issue #2018): ``plugin_version``'s MEANING changes on the per-
session ``--sync-out`` stream — the one path that runs unattended on every
``SessionStart`` (``.claude/ensure_session_archive.py``) and accumulates
into a durable, cross-release archive. It used to be stamped with whatever
``.claude-plugin/plugin.json`` said on the machine running the *extraction*
(``_load_plugin_version``), which mislabels every archived session with
today's version regardless of which release actually produced it. Each
``--sync-out`` record is now tagged by ``resolve_session_plugin_version()``,
which correlates the session's own ``session_id`` against
``<cwd>/.claude/metrics/boundary-events.jsonl`` — a stream stamped LIVE, at
hook-dispatch time, by ``hooks/lib/boundary_events.py`` — and falls back to
the explicit string ``"unknown"`` when no matching event exists, never to
the extractor's own version. The single-shot digest (``--transcript``/
``--project-dir``, no ``--sync-out``) and the downstream report's top-level
``plugin_version`` field are UNCHANGED by this bump: both can aggregate many
sessions in one record, and a single field cannot honestly attribute a
multi-session aggregate to one version — see ``resolve_session_plugin_version``'s
own docstring and the "Version tagging" note in ``knowledge/telemetry-
schema.md`` for the full scoping rationale. A version-filtered downstream
report (``--plugin-version``) now also reports its own coverage —
``version_filter_coverage`` breaks the considered sessions into three
buckets: matching the requested version, attributed to a DIFFERENT known
version (the filter working as intended, not a data gap), and genuinely
unattributed (no resolvable version at all) — instead of dropping
unattributable sessions silently or conflating them with sessions that
simply belong to another release.

PATH RESOLUTION (ADR 0032): this script is Category 1 (shipped and
portable) in both profiles — every path it touches (``session_log``,
``hooks/lib/pricing``, its own ``knowledge/model-pricing.json``, its own
``skills``/``agents`` directories for the default registry) resolves
relative to its own location inside ``plugins/dev-team/``, with no
dependency on a monorepo checkout.

STRUCTURE (issue #2098): this file is now a thin CLI dispatcher —
argument parsing (`_build_parser`) and per-profile orchestration
(`_main_maintainer`/`_main_downstream`) only. The actual extraction logic
lives in three modules under `scripts/lib/`: `session_report_shared.py`
(building blocks both profiles need), `session_report_maintainer.py`, and
`session_report_downstream.py`. Every name a test or an external consumer
(`scripts/bash_failure_taxonomy.py`, `scripts/eval_rawlog.py`) previously
imported from this module is re-exported below so `import session_report`
and `from session_report import X` keep working unchanged.

Stdlib only (Python 3.10+ floor, ADR 0031) — deliberately uses
``timezone.utc``, not ``datetime.UTC`` (a 3.11+ addition that
``scripts/session_extract.py`` could use only because that monorepo-only
script isn't subject to the shipped-tree floor).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# This script ships at plugins/dev-team/scripts/session_report.py — a
# sibling of plugins/dev-team/scripts/lib/, so no parent.parent indirection
# is needed (unlike scripts/session_extract.py, which reaches across from
# the repo root).
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from session_report_downstream import (
    _scan_all_session_ids,
    _sessions_with_known_plugin_version,
    combine,
    discover_projects,
    extract_downstream,
    resolve_single_project,
    sessions_matching_plugin_version,
)
from session_report_maintainer import (  # noqa: F401 -- re-exported for tests/external consumers
    _REWORK_KEYS,
    _append_trend,
    _iter_records,
    _read_synced_records,
    _rewrite_name_keys,
    _safe_number,
    cmd_correlate,
    cmd_cost_log,
    cmd_escalate,
    cmd_rollup,
    cmd_sync,
    extract_maintainer,
    resolve_all_transcripts,
    resolve_transcripts,
)
from session_report_shared import (  # noqa: F401 -- re-exported for tests/external consumers
    _DOWNSTREAM_SCHEMA,
    SYNC_SCHEMAS,
    _all_transcripts,
    _all_transcripts_under,
    _load_plugin_version,
    _merge_agent_buckets,
    _redact,
    load_registry,
    resolve_session_plugin_version,
)

# hooks/lib/pricing.py, not session_log/pricing.py (see hooks/lib/cost_meter.py's
# established rule, #1461/#2045): a hook must be import-safe without any
# scripts/ module on its path, so the dependency direction is scripts/ ->
# hooks/lib/, never the reverse. This script lives at plugins/dev-team/
# scripts/, so parent.parent is plugins/dev-team/, then hooks/lib.
sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "hooks" / "lib")
)
from pricing import load_pricing as _load_pricing


def _non_negative_int(value: str) -> int:
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not an integer") from None
    if n < 0:
        raise argparse.ArgumentTypeError(f"{value!r} must not be negative")
    return n


# ==========================================================================
# Unified CLI
# ==========================================================================


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--profile",
        choices=["maintainer", "downstream"],
        required=True,
        help="maintainer: scripts/session_extract.py's replacement "
        "(monorepo developer tooling). downstream: "
        "extract_session_report.py's replacement (shippable, hand-to-"
        "maintainer report).",
    )

    # --- maintainer-only flags ---
    ap.add_argument(
        "--transcript",
        action="append",
        help="[maintainer] explicit transcript JSONL file(s); repeatable",
    )
    ap.add_argument(
        "--project-dir", help="[maintainer] a directory of *.jsonl transcripts"
    )
    ap.add_argument("--cwd", help="[maintainer] project cwd to match (default: $PWD)")
    ap.add_argument("--pricing", help="[maintainer] model-pricing.json for cost (optional)")
    ap.add_argument(
        "--plugin-root", help="[maintainer] dev-team plugin root for the registry"
    )
    ap.add_argument(
        "--append",
        metavar="LOG",
        help="[maintainer] append one metrics-only summary record to a trend "
        "stream (append-only JSONL), e.g. metrics/session-digest.jsonl",
    )
    ap.add_argument(
        "--sync-out",
        metavar="FILE",
        help="[maintainer] cross-project incremental SYNC mode (#178)",
    )
    ap.add_argument(
        "--watermark",
        metavar="FILE",
        help="[maintainer] watermark JSON for incremental sync",
    )
    ap.add_argument("--host", help="[maintainer] host label for sync records")
    ap.add_argument(
        "--rollup",
        metavar="DIR",
        help="[maintainer] union read (#178): aggregate all hosts' "
        "DIR/<host>/session-digest.jsonl into one cross-machine view",
    )
    ap.add_argument(
        "--cost-log",
        metavar="DIR",
        help="[maintainer] cost-meter baseline (#171)",
    )
    ap.add_argument(
        "--escalate",
        metavar="DIR",
        help="[maintainer] Delta C (#179): rank friction signals and recommend a lever",
    )
    ap.add_argument(
        "--correlate",
        metavar="DIR",
        help="[maintainer] process eval (#111): compare rework between "
        "review-gate-bypass and non-bypass sessions",
    )
    ap.add_argument(
        "--rare-rate",
        type=float,
        default=0.25,
        help="[maintainer] per-session rate below which a friction is a hint (default 0.25)",
    )
    ap.add_argument(
        "--frequent-rate",
        type=float,
        default=1.0,
        help="[maintainer] per-session rate at/above which a matchable friction "
        "becomes a hook (default 1.0)",
    )
    ap.add_argument(
        "--version-scope",
        choices=["all", "current-and-previous"],
        default="all",
        help="[maintainer] scope --rollup/--escalate/--correlate to plugin_version-tagged records (#1480)",
    )
    ap.add_argument(
        "--boundary-events",
        metavar="FILE",
        help="[maintainer] gate-run correlation (#2037): boundary-events.jsonl to read gate_ran events from",
    )

    # --- downstream-only flags ---
    ap.add_argument(
        "--project",
        metavar="PATH",
        help="[downstream] extract only the project whose cwd is PATH (default: current directory)",
    )
    ap.add_argument(
        "--since",
        metavar="DAYS",
        type=_non_negative_int,
        help="[downstream] only include activity from the last DAYS days",
    )
    ap.add_argument(
        "--until",
        metavar="ISO8601",
        help="[downstream] only include activity at/before this UTC timestamp or date",
    )
    ap.add_argument(
        "--plugin-version",
        metavar="VERSION",
        help="[downstream] best-effort: only include sessions this project's "
        "local .claude/metrics/boundary-events.jsonl recorded under VERSION "
        "-- the report's version_filter_coverage field then breaks the "
        "considered sessions into matched/other-version/unattributed (#2018)",
    )

    # --- shared flags ---
    ap.add_argument(
        "--projects-root",
        help="root of Claude Code project transcripts (default: ~/.claude/projects)",
    )
    ap.add_argument(
        "--all-projects",
        action="store_true",
        help="aggregate/extract across ALL projects, not just the current cwd's",
    )
    ap.add_argument(
        "-o", "--out", help="output file path (meaning is profile-specific; see docstring)"
    )
    return ap


def _main_maintainer(args) -> int:
    pricing_path = (
        Path(args.pricing)
        if args.pricing
        else (Path(__file__).resolve().parent.parent / "knowledge" / "model-pricing.json")
    )
    pricing = _load_pricing(pricing_path)
    plugin_root = Path(args.plugin_root) if args.plugin_root else None
    registry = load_registry(plugin_root)
    version = _load_plugin_version(plugin_root)

    if args.rollup:
        return cmd_rollup(args, registry, plugin_root)
    if args.cost_log:
        return cmd_cost_log(args)
    if args.escalate:
        return cmd_escalate(args, registry, plugin_root)
    if args.correlate:
        return cmd_correlate(args, plugin_root)
    if args.sync_out:
        host = args.host or socket.gethostname()
        return cmd_sync(args, pricing, registry, host, version)

    paths = (
        resolve_all_transcripts(args)
        if args.all_projects
        else resolve_transcripts(args)
    )

    root = Path(args.projects_root or (Path.home() / ".claude" / "projects"))
    boundary_events_path = (
        Path(args.boundary_events)
        if args.boundary_events
        else Path(os.path.abspath(args.cwd or os.getcwd()))
        / ".claude"
        / "metrics"
        / "boundary-events.jsonl"
    )
    digest = extract_maintainer(
        paths,
        pricing,
        registry,
        version,
        projects_root=root,
        boundary_events_path=boundary_events_path,
    )
    out = json.dumps(digest, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(out + "\n")
    else:
        print(out)

    if args.append:
        _append_trend(Path(args.append), digest)
    return 0


def _main_downstream(args) -> int:
    since = None
    if args.since is not None:
        since = (datetime.now(timezone.utc) - timedelta(days=args.since)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    until = args.until
    if until and re.fullmatch(r"\d{4}-\d{2}-\d{2}", until):
        until = f"{until}T23:59:59Z"

    projects_root = Path(args.projects_root or (Path.home() / ".claude" / "projects"))
    plugin_root = Path(__file__).resolve().parent.parent
    registry = load_registry(plugin_root)
    plugin_version = _load_plugin_version(plugin_root)
    host = socket.gethostname()

    def _allowed_sessions(cwd: str | None) -> set[str] | None:
        return (
            sessions_matching_plugin_version(cwd, args.plugin_version)
            if args.plugin_version
            else None
        )

    digests: dict[str, dict] = {}
    # #2018 acceptance: a --plugin-version-filtered report states its own
    # coverage instead of dropping sessions silently. Three buckets,
    # accumulated per-project below alongside each extract_downstream()
    # call rather than with a second pass over `by_project`/`digests`
    # afterward: sessions matching the requested version (attributed);
    # sessions with a DIFFERENT known version (also attributed -- the
    # filter correctly excluded them, this is not a data gap); and
    # sessions with no resolvable version at all (genuinely unattributed).
    # Conflating the last two into a single "excluded" count would
    # misrepresent "the filter worked as intended" as "data is missing".
    coverage_considered = 0
    coverage_attributed = 0
    coverage_other_version = 0

    if args.all_projects:
        by_project = discover_projects(projects_root)
        if not by_project:
            print(f"no session transcripts found under {projects_root}")
            return 1
        for label, entry in sorted(by_project.items()):
            allowed = _allowed_sessions(entry["cwd"])
            digests[label] = extract_downstream(
                entry["paths"], registry, projects_root, since, until, allowed
            )
            if args.plugin_version:
                seen = _scan_all_session_ids(entry["paths"], since, until)
                known = _sessions_with_known_plugin_version(entry["cwd"])
                coverage_considered += len(seen)
                coverage_attributed += len(seen & (allowed or set()))
                coverage_other_version += len(seen & known - (allowed or set()))
        mode = "all-projects"
        scope = "all"
    else:
        target = args.project or os.getcwd()
        label, cwd, paths = resolve_single_project(projects_root, target)
        if not paths:
            print(f"no session transcripts found for project matching {target!r} under {projects_root}")
            return 1
        allowed = _allowed_sessions(cwd)
        digests[label] = extract_downstream(
            paths, registry, projects_root, since, until, allowed
        )
        if args.plugin_version:
            seen = _scan_all_session_ids(paths, since, until)
            known = _sessions_with_known_plugin_version(cwd)
            coverage_considered += len(seen)
            coverage_attributed += len(seen & (allowed or set()))
            coverage_other_version += len(seen & known - (allowed or set()))
        mode = "single-project"
        scope = label

    # None (not an empty/zeroed object) when no --plugin-version filter was
    # requested -- the filter's exclusion BEHAVIOR is unchanged by this
    # field (#2018 acceptance: "don't change the exclusion behavior itself,
    # just make it observable"), so an unfiltered report has nothing to
    # report coverage OF.
    version_filter_coverage = (
        {
            "requested_version": args.plugin_version,
            "sessions_considered": coverage_considered,
            "sessions_attributed": coverage_attributed,
            "sessions_attributed_other_version": coverage_other_version,
            "sessions_unattributed": (
                coverage_considered - coverage_attributed - coverage_other_version
            ),
        }
        if args.plugin_version
        else None
    )

    report = {
        "schema": _DOWNSTREAM_SCHEMA,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "host": host,
        "plugin_version": plugin_version,
        "mode": mode,
        "filters": {
            "since": since,
            "until": until,
            "plugin_version": args.plugin_version,
        },
        "version_filter_coverage": version_filter_coverage,
        "projects": digests,
        "combined": combine(digests, registry),
    }

    out_path = Path(
        args.out
        or f"session-report-{scope}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {out_path} ({len(digests)} project(s), {report['combined']['sessions']} session(s))")
    return 0


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    if args.profile == "maintainer":
        return _main_maintainer(args)
    return _main_downstream(args)


if __name__ == "__main__":
    raise SystemExit(main())
