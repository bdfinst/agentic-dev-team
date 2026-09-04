"""#2110 — retried_bash_commands gains skill/agent attribution.

Session digest analysis found a large gap between two rework counters
(`rework.retried_bash_commands: 3947` vs. `rework.repeated_verify_runs: 1`)
with no per-skill/per-agent breakdown to trace the volume to a cause. This
file end-to-ends the fix through the `--profile maintainer` pipeline:
extract -> --sync-out -> --rollup, proving the breakdown survives each hop
and the scalar total stays derived from it (single source of truth, #2108's
own lesson applied here).

Unit-level coverage of the underlying `track_bash` attribution primitive
lives in `plugins/dev-team/tests/scripts/test_session_log_signals.py`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from _repo_root import REPO_ROOT

EXTRACT = REPO_ROOT / "plugins" / "dev-team" / "scripts" / "session_report.py"
PLUGIN = REPO_ROOT / "plugins" / "dev-team"


def _rec(ts: str, content: list) -> str:
    return (
        json.dumps(
            {
                "type": "assistant",
                "cwd": "/p",
                "sessionId": "s",
                "timestamp": ts,
                "message": {
                    "model": "claude-opus-4-8",
                    "usage": {"input_tokens": 10, "output_tokens": 1},
                    "content": content,
                },
            }
        )
        + "\n"
    )


def _bash(command: str) -> dict:
    return {"type": "tool_use", "name": "Bash", "input": {"command": command}}


def _skill(name: str) -> dict:
    return {"type": "tool_use", "name": "Skill", "input": {"skill": name}}


def _run(*args: str) -> dict:
    res = subprocess.run(
        [sys.executable, str(EXTRACT), "--profile", "maintainer", *args],
        capture_output=True, text=True, check=False,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    return json.loads(res.stdout)


def test_extract_maintainer_attributes_a_retry_to_the_active_skill(tmp_path: Path) -> None:
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(
        _rec("2026-06-07T10:00:00Z", [_skill("build")])
        + _rec("2026-06-07T10:00:01Z", [_bash("python3 -m pytest -q")])
        + _rec("2026-06-07T10:00:02Z", [_bash("python3 -m pytest -q")]),
        encoding="utf-8",
    )
    data = _run("--transcript", str(transcript), "--plugin-root", str(PLUGIN))
    rew = data["rework"]
    assert rew["retried_bash_commands"] == 1
    assert rew["retried_bash_commands_by_skill"] == {"build": 1}
    assert rew["retried_bash_commands_by_agent"] == {"unattributed": 1}


def test_extract_maintainer_reports_unattributed_with_no_active_skill_or_agent(
    tmp_path: Path,
) -> None:
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(
        _rec("2026-06-07T10:00:00Z", [_bash("npm run lint")])
        + _rec("2026-06-07T10:00:01Z", [_bash("npm run lint")]),
        encoding="utf-8",
    )
    data = _run("--transcript", str(transcript), "--plugin-root", str(PLUGIN))
    rew = data["rework"]
    assert rew["retried_bash_commands"] == 1
    assert rew["retried_bash_commands_by_skill"] == {"unattributed": 1}
    assert rew["retried_bash_commands_by_agent"] == {"unattributed": 1}


def test_sync_out_carries_the_breakdown_through(tmp_path: Path) -> None:
    projects = tmp_path / "projects" / "projA"
    projects.mkdir(parents=True)
    (projects / "sess-a.jsonl").write_text(
        _rec("2026-06-07T10:00:00Z", [_skill("triage")])
        + _rec("2026-06-07T10:00:01Z", [_bash("go test ./...")])
        + _rec("2026-06-07T10:00:02Z", [_bash("go test ./...")]),
        encoding="utf-8",
    )
    out = tmp_path / "digests" / "testhost" / "session-digest.jsonl"
    watermark = tmp_path / "watermark.json"
    res = subprocess.run(
        [
            sys.executable, str(EXTRACT), "--profile", "maintainer",
            "--sync-out", str(out),
            "--watermark", str(watermark),
            "--projects-root", str(tmp_path / "projects"),
            "--host", "testhost",
            "--plugin-root", str(PLUGIN),
        ],
        capture_output=True, text=True, check=False,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    record = json.loads(out.read_text().splitlines()[0])
    rew = record["rework"]
    assert rew["retried_bash_commands"] == 1
    assert rew["retried_bash_commands_by_skill"] == {"triage": 1}


def test_rollup_aggregates_the_breakdown_across_sessions(tmp_path: Path) -> None:
    manifest_dir = tmp_path / "fake-plugin" / ".claude-plugin"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "plugin.json").write_text(json.dumps({"version": "1.0.0"}))

    digests = tmp_path / "digests" / "box"
    digests.mkdir(parents=True)
    digests.joinpath("session-digest.jsonl").write_text(
        "\n".join(
            json.dumps(rec)
            for rec in (
                {
                    "schema": "session-sync/v3",
                    "plugin_version": "1.0.0",
                    "session_id": "s1",
                    "rework": {
                        "retried_bash_commands": 2,
                        "retried_bash_commands_by_skill": {"build": 2},
                        "retried_bash_commands_by_agent": {"unattributed": 2},
                    },
                },
                {
                    "schema": "session-sync/v3",
                    "plugin_version": "1.0.0",
                    "session_id": "s2",
                    "rework": {
                        "retried_bash_commands": 1,
                        "retried_bash_commands_by_skill": {"fix": 1},
                        "retried_bash_commands_by_agent": {"software-engineer": 1},
                    },
                },
            )
        )
        + "\n"
    )
    res = subprocess.run(
        [
            sys.executable, str(EXTRACT), "--profile", "maintainer",
            "--rollup", str(tmp_path / "digests"),
            "--plugin-root", str(tmp_path / "fake-plugin"),
        ],
        capture_output=True, text=True, check=False,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    data = json.loads(res.stdout)
    rew = data["rework"]
    assert rew["retried_bash_commands"] == 3
    assert rew["retried_bash_commands_by_skill"] == {"build": 2, "fix": 1}
    assert rew["retried_bash_commands_by_agent"] == {
        "software-engineer": 1, "unattributed": 2,
    }
