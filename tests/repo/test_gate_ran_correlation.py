"""#2037 — correlating commit-attempt Bash records against `gate_ran`
boundary events to publish the deliberate/absent/errored distribution
`_BYPASS_RE` alone cannot see (causes 2-4 from #2009's original framing: an
inert hook, a hook that errors but exits 0, or a commit made through an
unregistered path — all leave a command line that looks entirely ordinary).

See `tests/repo/test_gate_ran_husky.py` for where the `gate_ran` event
itself gets emitted (`.husky/pre-commit`); this file covers the OTHER half
— `scripts/session_extract.py`'s correlation of that event stream against
commit-attempt Bash records.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from _repo_root import REPO_ROOT

EXTRACT = REPO_ROOT / "scripts" / "session_extract.py"
PLUGIN = REPO_ROOT / "plugins" / "dev-team"


def _gate_ran_line(ts: str, verdict: str) -> str:
    return (
        json.dumps(
            {
                "ts": ts,
                "hook": "pre-commit-gate",
                "tool": "Bash",
                "decision": "record",
                "matched_rule": f"gate-ran-{verdict}",
                "plugin_version": "0.0.0",
            }
        )
        + "\n"
    )


def _run(transcript: Path, boundary_events: Path | None) -> dict:
    args = [
        sys.executable,
        str(EXTRACT),
        "--transcript",
        str(transcript),
        "--plugin-root",
        str(PLUGIN),
    ]
    if boundary_events is not None:
        args += ["--boundary-events", str(boundary_events)]
    res = subprocess.run(args, capture_output=True, text=True, check=False)
    assert res.returncode == 0, res.stdout + res.stderr
    return json.loads(res.stdout)


def _commit_transcript(tmp_path: Path, ts: str, extra_flags: str = "") -> Path:
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(
        json.dumps(
            {
                "type": "assistant",
                "cwd": "/p",
                "sessionId": "s",
                "timestamp": ts,
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Bash",
                            "input": {"command": f"git commit -m x{extra_flags}"},
                        }
                    ]
                },
            }
        )
        + "\n"
    )
    return transcript


def test_gate_ran_absent_when_no_boundary_events_file_exists(tmp_path: Path) -> None:
    """A commit attempt with no `--boundary-events` file at all (the gate
    never ran, or was never instrumented) is `gate_ran_absent` — the
    previously-unmeasured cause-2/3/4 population."""
    transcript = _commit_transcript(tmp_path, "2026-06-07T10:00:00Z")
    missing = tmp_path / "no-such-boundary-events.jsonl"
    data = _run(transcript, missing)
    assert data["gate"]["commit_attempts"] == 1
    assert data["gate"]["commit_bypasses"] == 0
    assert data["gate"]["gate_ran_absent"] == 1
    assert data["gate"]["gate_ran_errored"] == 0
    assert data["gate"]["gate_ran_clean"] == 0


def test_gate_ran_clean_when_an_allow_event_correlates_within_the_window(
    tmp_path: Path,
) -> None:
    transcript = _commit_transcript(tmp_path, "2026-06-07T10:00:00Z")
    events = tmp_path / "boundary-events.jsonl"
    events.write_text(_gate_ran_line("2026-06-07T10:00:01Z", "allow"))
    data = _run(transcript, events)
    assert data["gate"]["gate_ran_clean"] == 1
    assert data["gate"]["gate_ran_absent"] == 0
    assert data["gate"]["gate_ran_errored"] == 0


def test_gate_ran_clean_when_a_block_event_correlates_within_the_window(
    tmp_path: Path,
) -> None:
    """A "block" verdict is still evidence the gate RAN — a legitimate
    rejection is not part of the unmeasured population."""
    transcript = _commit_transcript(tmp_path, "2026-06-07T10:00:00Z")
    events = tmp_path / "boundary-events.jsonl"
    events.write_text(_gate_ran_line("2026-06-07T10:00:01Z", "block"))
    data = _run(transcript, events)
    assert data["gate"]["gate_ran_clean"] == 1
    assert data["gate"]["gate_ran_errored"] == 0
    assert data["gate"]["gate_ran_absent"] == 0


def test_gate_ran_errored_when_the_correlated_event_recorded_a_failure(
    tmp_path: Path,
) -> None:
    transcript = _commit_transcript(tmp_path, "2026-06-07T10:00:00Z")
    events = tmp_path / "boundary-events.jsonl"
    events.write_text(_gate_ran_line("2026-06-07T10:00:01Z", "errored"))
    data = _run(transcript, events)
    assert data["gate"]["gate_ran_errored"] == 1
    assert data["gate"]["gate_ran_absent"] == 0
    assert data["gate"]["gate_ran_clean"] == 0


def test_gate_ran_absent_when_the_nearest_event_is_outside_the_window(
    tmp_path: Path,
) -> None:
    transcript = _commit_transcript(tmp_path, "2026-06-07T10:00:00Z")
    events = tmp_path / "boundary-events.jsonl"
    # 1 hour away — far outside GATE_RAN_WINDOW_SECONDS (120s).
    events.write_text(_gate_ran_line("2026-06-07T11:00:00Z", "allow"))
    data = _run(transcript, events)
    assert data["gate"]["gate_ran_absent"] == 1
    assert data["gate"]["gate_ran_clean"] == 0


def test_deliberate_bypass_is_never_counted_toward_absent_or_errored(
    tmp_path: Path,
) -> None:
    """A deliberate --no-verify/-n bypass means the gate genuinely could not
    run (git itself skips ALL hooks) — it is fully explained by
    `commit_bypasses` already and must not ALSO inflate `gate_ran_absent`,
    even with zero boundary events on file."""
    transcript = _commit_transcript(tmp_path, "2026-06-07T10:00:00Z", " --no-verify")
    missing = tmp_path / "no-such-boundary-events.jsonl"
    data = _run(transcript, missing)
    assert data["gate"]["commit_bypasses"] == 1
    assert data["gate"]["gate_ran_absent"] == 0
    assert data["gate"]["gate_ran_errored"] == 0
    assert data["gate"]["gate_ran_clean"] == 0


def test_default_boundary_events_path_resolves_under_cwd(tmp_path: Path) -> None:
    """With no --boundary-events override, the default resolves to
    <cwd>/.claude/metrics/boundary-events.jsonl (#2037) — the same
    convention `hooks/lib/boundary_events.py` itself writes to."""
    project = tmp_path / "proj"
    project.mkdir()
    transcript = project / "t.jsonl"
    transcript.write_text(
        json.dumps(
            {
                "type": "assistant",
                "cwd": "/p",
                "sessionId": "s",
                "timestamp": "2026-06-07T10:00:00Z",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Bash",
                            "input": {"command": "git commit -m x"},
                        }
                    ]
                },
            }
        )
        + "\n"
    )
    events_dir = project / ".claude" / "metrics"
    events_dir.mkdir(parents=True)
    (events_dir / "boundary-events.jsonl").write_text(
        _gate_ran_line("2026-06-07T10:00:01Z", "allow")
    )

    res = subprocess.run(
        [
            sys.executable,
            str(EXTRACT),
            "--transcript",
            str(transcript),
            "--plugin-root",
            str(PLUGIN),
            "--cwd",
            str(project),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    data = json.loads(res.stdout)
    assert data["gate"]["gate_ran_clean"] == 1
