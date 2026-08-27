"""Delta D extractor slice (#178): cross-project, incremental, per-session
sync. Builds a fake ~/.claude/projects tree with two projects and verifies
the --sync-out mode emits one metrics-only record per new/changed session,
labels each by project basename, and is incremental via the watermark.

Ported from tests/repo/session_extract_sync_tests.bats (#673).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

EXTRACT = REPO_ROOT / "scripts" / "session_extract.py"
PLUGIN = REPO_ROOT / "plugins" / "dev-team"


@pytest.fixture
def scratch(tmp_path: Path) -> dict[str, Path]:
    root = tmp_path
    projects = root / "projects"
    proj_a = projects / "projA"
    proj_b = projects / "projB"
    proj_a.mkdir(parents=True)
    proj_b.mkdir(parents=True)

    # One transcript per project. Filename stem = session id. cwd basename =
    # project.
    (proj_a / "sess-a.jsonl").write_text(
        '{"type":"assistant","cwd":"/home/u/work/alpha","sessionId":"s-a",'
        '"isSidechain":false,"timestamp":"2026-06-07T10:00:00Z",'
        '"message":{"model":"claude-opus-4-8","usage":{"input_tokens":1000,'
        '"output_tokens":100,"cache_read_input_tokens":400}}}\n'
    )
    (proj_b / "sess-b.jsonl").write_text(
        '{"type":"assistant","cwd":"/srv/code/beta","sessionId":"s-b",'
        '"isSidechain":true,"timestamp":"2026-06-07T11:00:00Z",'
        '"message":{"model":"claude-sonnet-4-6","usage":{"input_tokens":2000,'
        '"output_tokens":200}}}\n'
    )
    out = root / "digests" / "testhost" / "session-digest.jsonl"
    watermark = root / "watermark.json"
    return {"root": root, "projects": projects, "out": out, "watermark": watermark}


def _sync(scratch: dict[str, Path]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(EXTRACT),
            "--sync-out",
            str(scratch["out"]),
            "--watermark",
            str(scratch["watermark"]),
            "--projects-root",
            str(scratch["projects"]),
            "--host",
            "testhost",
            "--plugin-root",
            str(PLUGIN),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def _records(out: Path) -> list:
    return [json.loads(line) for line in out.read_text().splitlines() if line]


def test_sync_emits_one_record_per_session_labeled_by_basename(
    scratch: dict[str, Path],
) -> None:
    result = _sync(scratch)
    assert result.returncode == 0, result.stdout + result.stderr
    records = _records(scratch["out"])
    assert len(records) == 2

    by_id = {r["session_id"]: r for r in records}
    assert by_id["sess-a"]["schema"] == "session-sync/v2"
    assert by_id["sess-a"]["project"] == "alpha"
    assert by_id["sess-b"]["project"] == "beta"
    assert by_id["sess-a"]["host"] == "testhost"
    # ts comes from transcript data, not wall-clock
    assert by_id["sess-a"]["ts"] == "2026-06-07T10:00:00Z"
    # main/subagent thread split is preserved. #2044: by_thread entries are
    # now signals.new_agent_bucket() dicts, not bare message-count ints —
    # "messages" is the old int's direct equivalent.
    assert by_id["sess-b"]["by_thread"]["sidechain"]["messages"] == 1


def test_sync_incremental_second_run_with_no_changes_emits_nothing_new(
    scratch: dict[str, Path],
) -> None:
    _sync(scratch)
    before = len(_records(scratch["out"]))
    _sync(scratch)
    after = len(_records(scratch["out"]))
    assert before == 2
    assert after == 2
    # watermark records both sessions
    watermark = json.loads(scratch["watermark"].read_text())
    assert len(watermark["synced"]) == 2


def test_sync_a_newly_added_session_is_the_only_new_emission_on_rerun(
    scratch: dict[str, Path],
) -> None:
    _sync(scratch)
    (scratch["projects"] / "projA" / "sess-c.jsonl").write_text(
        '{"type":"assistant","cwd":"/home/u/work/alpha","sessionId":"s-c",'
        '"timestamp":"2026-06-07T12:00:00Z",'
        '"message":{"model":"claude-opus-4-8","usage":{"input_tokens":500,'
        '"output_tokens":50}}}\n'
    )
    _sync(scratch)
    records = _records(scratch["out"])
    assert len(records) == 3
    # exactly one record for the new session
    assert len([r for r in records if r["session_id"] == "sess-c"]) == 1


def test_sync_a_grown_session_is_re_emitted(scratch: dict[str, Path]) -> None:
    _sync(scratch)
    # append another usage record to an existing session -> file grows
    with (scratch["projects"] / "projA" / "sess-a.jsonl").open("a") as f:
        f.write(
            '{"type":"assistant","cwd":"/home/u/work/alpha","sessionId":"s-a",'
            '"timestamp":"2026-06-07T10:05:00Z",'
            '"message":{"model":"claude-opus-4-8","usage":{"input_tokens":300,'
            '"output_tokens":30}}}\n'
        )
    _sync(scratch)
    records = _records(scratch["out"])
    # sess-a re-emitted (now appears twice in the append-only host digest)
    assert len([r for r in records if r["session_id"] == "sess-a"]) == 2


def test_sync_privacy_basename_only_no_full_paths_or_content(
    scratch: dict[str, Path],
) -> None:
    _sync(scratch)
    text = scratch["out"].read_text()
    assert "/home/u/work/alpha" not in text  # no full cwd path
    assert "/srv/code/beta" not in text
    assert '"project": "alpha"' in text or '"project":"alpha"' in text


def test_sync_record_carries_correction_by_skill_and_by_agent(
    tmp_path: Path,
) -> None:
    # #711: sync_record's accuracy block must carry the full by_skill/by_agent
    # correction-attribution maps through from the digest, not just the
    # slimmed scalar.
    projects = tmp_path / "projects"
    proj = projects / "projC"
    proj.mkdir(parents=True)
    (proj / "sess-corr.jsonl").write_text(
        '{"type":"assistant","cwd":"/home/u/work/gamma","sessionId":"s-corr",'
        '"timestamp":"2026-06-07T10:00:00Z","message":{"content":'
        '[{"type":"tool_use","id":"u1","name":"Skill",'
        '"input":{"skill":"dev-team:plan"}}]}}\n'
        '{"type":"user","cwd":"/home/u/work/gamma","sessionId":"s-corr",'
        '"message":{"content":"No, actually revert that change"}}\n'
    )
    out = tmp_path / "digests" / "testhost" / "session-digest.jsonl"
    watermark = tmp_path / "watermark.json"
    result = subprocess.run(
        [
            sys.executable,
            str(EXTRACT),
            "--sync-out",
            str(out),
            "--watermark",
            str(watermark),
            "--projects-root",
            str(projects),
            "--host",
            "testhost",
            "--plugin-root",
            str(PLUGIN),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    records = _records(out)
    assert len(records) == 1
    accuracy = records[0]["accuracy"]
    assert accuracy["user_correction_turns"] == 1
    assert accuracy["by_skill"] == {"plan": 1}
    assert accuracy["by_agent"] == {"unattributed": 1}


def test_all_projects_non_sync_digest_aggregates_sessions_across_projects(
    scratch: dict[str, Path],
) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(EXTRACT),
            "--all-projects",
            "--projects-root",
            str(scratch["projects"]),
            "--plugin-root",
            str(PLUGIN),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["sessions"] == 2
