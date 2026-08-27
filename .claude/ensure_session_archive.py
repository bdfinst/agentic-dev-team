#!/usr/bin/env python3
"""SessionStart hook (registered in .claude/settings.json): archive this
machine's new/changed sessions into a durable local file before Claude
Code's default 30-day transcript retention (`cleanupPeriodDays`, unset here)
ages them out from under the harness-measurement corpus (#2018).

Why this matters: this repo's session-report analysis (feeding #1973, #1999,
#2008) reads directly from live `~/.claude/projects/**/*.jsonl` transcripts.
Those expire in 30 days. A prior durable archive
(`digests/<host>/session-digest.jsonl` in a separate telemetry repo) existed
and stopped being written on 2026-07-27 -- no workflow, hook, or job called
it. This is the "small and urgent" half of #2018's fix: it stops today's
bleeding by writing `session_report.py --profile maintainer --sync-out`'s
incremental, metrics-only stream to a LOCAL file under `.claude/metrics/`
(gitignored, `**/metrics/*` -- never committed), independent of whether/how
a session's `plugin_version` gets fixed (#2018's second, larger half,
tracked separately). It never pushes anywhere and never touches git.

The cross-machine telemetry-sync mechanism (`scripts/telemetry-sync.sh`,
which clones/commits/pushes to a *separate*, explicitly-configured
`DEV_TEAM_TELEMETRY_REMOTE` repo) is deliberately NOT what this hook runs --
that is a real, consequential network write an operator opts into by hand,
not something a SessionStart hook should trigger silently.

Fail-open and time-boxed -- never blocks session start. Stdlib-only.
"""

from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))
try:
    from session_start_common import resolve_project_root, run_logged
except ImportError:
    # The shared module must be present for this hook to do anything useful;
    # if it's missing (e.g. a partial checkout), fail open rather than raise.
    sys.exit(0)

_TIMEOUT_SECONDS = 120


def _emit(message: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": message,
                }
            }
        )
    )


def main() -> int:
    try:
        root = resolve_project_root()

        # Only meaningful in THIS repo's own checkout(s) -- same in-repo
        # detection /dev-team:setup uses (requirements-dev.txt +
        # plugins/dev-team/.claude-plugin/plugin.json), so this hook is
        # inert for a downstream project that merely has the plugin
        # installed.
        if not (root / "requirements-dev.txt").is_file():
            return 0
        if not (
            root / "plugins" / "dev-team" / ".claude-plugin" / "plugin.json"
        ).is_file():
            return 0

        script = root / "plugins" / "dev-team" / "scripts" / "session_report.py"
        if not script.is_file():
            return 0

        metrics_dir = root / ".claude" / "metrics"
        digest_out = metrics_dir / "session-digest.jsonl"
        watermark = metrics_dir / "session-digest-watermark.json"
        metrics_dir.mkdir(parents=True, exist_ok=True)

        host = socket.gethostname() or "unknown-host"
        log_path = Path.home() / ".cache" / "session-archive-sessionstart.log"
        ok = run_logged(
            [
                sys.executable,
                str(script),
                "--profile",
                "maintainer",
                "--sync-out",
                str(digest_out),
                "--watermark",
                str(watermark),
                "--host",
                host,
                "--plugin-root",
                str(root / "plugins" / "dev-team"),
            ],
            root,
            log_path,
            _TIMEOUT_SECONDS,
        )

        if not ok:
            _emit(
                "Session archival (session_report.py --profile maintainer "
                f"--sync-out, #2018) failed or timed out this run -- transcripts "
                f"still age out at 30 days until it succeeds. See {log_path}."
            )
        # Silent on success -- this runs every session start, and a
        # steady-state "archived N sessions" line on every launch is exactly
        # the noise a SessionStart hook should not add once it's working.
        return 0
    except Exception:  # noqa: BLE001 - never let this hook block or fail session start.
        return 0


if __name__ == "__main__":
    sys.exit(main())
