"""#182 - utilization is read from Skill/Agent tool_use (not the
non-existent attributionSkill). #178 - `--rollup` unions all hosts'
per-session sync records into one cross-machine view.

Ported from tests/repo/session_extract_rollup_tests.bats (#673).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from _repo_root import REPO_ROOT

EXTRACT = REPO_ROOT / "scripts" / "session_extract.py"
PLUGIN = REPO_ROOT / "plugins" / "dev-team"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(EXTRACT), *args, "--plugin-root", str(PLUGIN)],
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# #182: utilization from tool_use
# ---------------------------------------------------------------------------


def test_utilization_skills_agents_counted_from_tool_use(tmp_path: Path) -> None:
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(
        '{"type":"assistant","message":{"model":"claude-opus-4-8",'
        '"usage":{"input_tokens":10,"output_tokens":1},'
        '"content":[{"type":"tool_use","id":"u1","name":"Skill",'
        '"input":{"skill":"dev-team:plan"}}]}}\n'
        '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"u2",'
        '"name":"Skill","input":{"skill":"dev-team:plan"}}]}}\n'
        '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"u3",'
        '"name":"Agent","input":{"subagent_type":"dev-team:software-engineer",'
        '"description":"x"}}]}}\n'
        '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"u4",'
        '"name":"Skill","input":{"skill":"update-config"}}]}}\n'
    )
    result = _run("--transcript", str(transcript))
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    utilization = data["utilization"]
    # namespace stripped so it matches the registry
    assert utilization["skills_invoked"]["plan"] == 2
    assert utilization["agents_invoked"]["software-engineer"] == 1
    # other-plugin skill kept as-is
    assert utilization["skills_invoked"]["update-config"] == 1
    # an invoked skill is NOT in never-observed
    assert "plan" not in utilization["never_observed_skills"]


# ---------------------------------------------------------------------------
# #178: rollup union read
# ---------------------------------------------------------------------------


def _seed_digests(tmp_path: Path) -> Path:
    box_a = tmp_path / "digests" / "boxA"
    box_b = tmp_path / "digests" / "boxB"
    box_a.mkdir(parents=True)
    box_b.mkdir(parents=True)
    (box_a / "session-digest.jsonl").write_text(
        '{"schema":"session-sync/v1","host":"boxA","project":"alpha","session_id":"s1",'
        '"tokens":{"input_tokens":1000,"output_tokens":100,"cache_read_input_tokens":400},'
        '"cost_usd":0.5,"rework":{"failed_edits":1},'
        '"accuracy":{"tool_calls":10,"tool_error_rate":0.1,"user_correction_turns":1,'
        '"by_skill":{"plan":1},"by_agent":{"unattributed":1}},'
        '"utilization":{"skills_invoked":{"plan":1},"agents_invoked":{}}}\n'
        '{"schema":"session-sync/v1","host":"boxA","project":"beta","session_id":"s2",'
        '"tokens":{"input_tokens":2000,"output_tokens":200},"cost_usd":1.0,'
        '"rework":{"failed_edits":0},'
        '"accuracy":{"tool_calls":5,"tool_error_rate":0.0,"user_correction_turns":0},'
        '"utilization":{"skills_invoked":{},"agents_invoked":{"software-engineer":1}}}\n'
    )
    (box_b / "session-digest.jsonl").write_text(
        '{"schema":"session-sync/v1","host":"boxB","project":"alpha","session_id":"s3",'
        '"tokens":{"input_tokens":500,"output_tokens":50},"cost_usd":0.25,'
        '"rework":{"failed_edits":2},'
        '"accuracy":{"tool_calls":4,"tool_error_rate":0.25,"user_correction_turns":1,'
        '"by_skill":{"code-review":1},"by_agent":{"software-engineer":1}},'
        '"utilization":{"skills_invoked":{"plan":2},"agents_invoked":{}}}\n'
    )
    return tmp_path / "digests"


def _rollup(digests: Path) -> dict:
    result = _run("--rollup", str(digests))
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def test_rollup_aggregates_sessions_tokens_cost_across_hosts_and_projects(
    tmp_path: Path,
) -> None:
    digests = _seed_digests(tmp_path)
    data = _rollup(digests)
    assert data["sessions"] == 3
    assert ",".join(data["hosts"]) == "boxA,boxB"
    assert ",".join(data["projects"]) == "alpha,beta"
    assert data["tokens"]["input_tokens"] == 3500
    assert data["cost_usd"] == 1.75
    assert data["cache_hit_ratio"] == 1.0


def test_rollup_by_host_and_by_project_breakdowns(tmp_path: Path) -> None:
    digests = _seed_digests(tmp_path)
    data = _rollup(digests)
    assert data["by_host"]["boxA"]["sessions"] == 2
    assert data["by_host"]["boxB"]["sessions"] == 1
    assert data["by_project"]["alpha"]["sessions"] == 2
    assert data["by_project"]["beta"]["sessions"] == 1


def test_rollup_utilization_unions_invocations_and_never_observed(
    tmp_path: Path,
) -> None:
    digests = _seed_digests(tmp_path)
    data = _rollup(digests)
    # plan invoked on both hosts: 1 + 2
    assert data["utilization"]["skills_invoked"]["plan"] == 3
    assert data["utilization"]["agents_invoked"]["software-engineer"] == 1
    # a skill invoked on ANY host is not in the cross-machine never-observed
    # set
    assert "plan" not in data["utilization"]["never_observed_skills"]
    assert len(data["utilization"]["never_observed_skills"]) > 5


def test_rollup_accuracy_sums_correction_by_skill_and_by_agent_across_hosts(
    tmp_path: Path,
) -> None:
    # #711: rollup must sum the per-session correction-attribution maps, and
    # the summed total must equal the scalar user_correction_turns rollup.
    digests = _seed_digests(tmp_path)
    data = _rollup(digests)
    accuracy = data["accuracy"]
    assert accuracy["user_correction_turns"] == 2
    assert accuracy["by_skill"] == {"code-review": 1, "plan": 1}
    assert accuracy["by_agent"] == {"software-engineer": 1, "unattributed": 1}
    assert sum(accuracy["by_skill"].values()) == accuracy["user_correction_turns"]
    assert sum(accuracy["by_agent"].values()) == accuracy["user_correction_turns"]


def test_rollup_a_session_id_seen_twice_is_deduped(tmp_path: Path) -> None:
    digests = _seed_digests(tmp_path)
    # boxB re-emits s1 (e.g. grown) -> must count once, not twice
    with (digests / "boxB" / "session-digest.jsonl").open("a") as f:
        f.write(
            '{"schema":"session-sync/v1","host":"boxB","project":"alpha",'
            '"session_id":"s1","tokens":{"input_tokens":9999,"output_tokens":1},'
            '"cost_usd":9.9,"rework":{},'
            '"accuracy":{"tool_calls":1,"tool_error_rate":0,"user_correction_turns":0},'
            '"utilization":{"skills_invoked":{},"agents_invoked":{}}}\n'
        )
    data = _rollup(digests)
    # still 3 unique sessions (s1 deduped, last write wins)
    assert data["sessions"] == 3


def test_rollup_renormalizes_legacy_unstripped_namespace_prefixes(
    tmp_path: Path,
) -> None:
    """#712: a per-session digest written before `_strip_ns` existed (or before
    a prefix was added to its known list) can carry a raw `agentic-dev-team:x`
    key in `utilization.agents_invoked`/`skills_invoked` alongside an
    already-stripped `x` key from a newer digest. `rollup` must fold both into
    the same bare registry name — summing them and excluding it from
    never_observed — rather than treating them as two distinct, separately
    under-counted entries."""
    digests = tmp_path / "digests" / "boxA"
    digests.mkdir(parents=True)
    (digests / "session-digest.jsonl").write_text(
        '{"schema":"session-sync/v1","host":"boxA","project":"alpha","session_id":"s1",'
        '"tokens":{"input_tokens":100,"output_tokens":10},"cost_usd":0.1,'
        '"rework":{},"accuracy":{"tool_calls":1,"tool_error_rate":0,'
        '"user_correction_turns":0},'
        '"utilization":{"skills_invoked":{},'
        '"agents_invoked":{"agentic-dev-team:product-manager":6}}}\n'
        '{"schema":"session-sync/v1","host":"boxA","project":"alpha","session_id":"s2",'
        '"tokens":{"input_tokens":100,"output_tokens":10},"cost_usd":0.1,'
        '"rework":{},"accuracy":{"tool_calls":1,"tool_error_rate":0,'
        '"user_correction_turns":0},'
        '"utilization":{"skills_invoked":{},'
        '"agents_invoked":{"product-manager":2}}}\n'
    )
    data = _rollup(tmp_path / "digests")
    # both the legacy-prefixed and already-stripped records fold into one key
    assert data["utilization"]["agents_invoked"]["product-manager"] == 8
    assert (
        "agentic-dev-team:product-manager" not in data["utilization"]["agents_invoked"]
    )
    assert "product-manager" not in data["utilization"]["never_observed_agents"]


def test_rollup_empty_missing_dir_yields_a_well_formed_empty_rollup(
    tmp_path: Path,
) -> None:
    data = _rollup(tmp_path / "nope")
    assert data["sessions"] == 0


# ---------------------------------------------------------------------------
# #171: --cost-log per-session cost series for the regression gate
# ---------------------------------------------------------------------------


def _seed_cost_digests(tmp_path: Path) -> Path:
    box_a = tmp_path / "digests" / "boxA"
    box_b = tmp_path / "digests" / "boxB"
    box_a.mkdir(parents=True)
    box_b.mkdir(parents=True)
    # ts deliberately out of file order; cost-log must sort oldest->newest by
    # ts.
    (box_a / "session-digest.jsonl").write_text(
        '{"schema":"session-sync/v1","host":"boxA","session_id":"s2",'
        '"ts":"2026-06-02T00:00:00Z","cost_usd":2.0}\n'
        '{"schema":"session-sync/v1","host":"boxA","session_id":"s1",'
        '"ts":"2026-06-01T00:00:00Z","cost_usd":1.0}\n'
    )
    (box_b / "session-digest.jsonl").write_text(
        '{"schema":"session-sync/v1","host":"boxB","session_id":"s3",'
        '"ts":"2026-06-03T00:00:00Z","cost_usd":3.0}\n'
    )
    return tmp_path / "digests"


def test_cost_log_emits_a_ts_ordered_per_session_cost_series_across_hosts(
    tmp_path: Path,
) -> None:
    digests = _seed_cost_digests(tmp_path)
    result = _run("--cost-log", str(digests))
    assert result.returncode == 0, result.stdout + result.stderr
    lines = result.stdout.splitlines()
    # three records, oldest first, in cost-meter shape
    assert len(lines) == 3
    records = [json.loads(line) for line in lines]
    assert [r["total"]["cost_usd"] for r in records] == [1, 2, 3]
    assert records[0]["ts"] == "2026-06-01T00:00:00Z"


def test_cost_log_dedups_a_session_id_seen_twice_last_write_wins(
    tmp_path: Path,
) -> None:
    digests = _seed_cost_digests(tmp_path)
    # re-emit s1 with a higher cost -> one record, newest value
    with (digests / "boxB" / "session-digest.jsonl").open("a") as f:
        f.write(
            '{"schema":"session-sync/v1","host":"boxB","session_id":"s1",'
            '"ts":"2026-06-01T00:00:00Z","cost_usd":5.0}\n'
        )
    result = _run("--cost-log", str(digests))
    lines = result.stdout.splitlines()
    assert len(lines) == 3
    records = [json.loads(line) for line in lines]
    assert [r["total"]["cost_usd"] for r in records] == [5, 2, 3]


def test_cost_log_empty_missing_dir_yields_no_records_clean_exit(
    tmp_path: Path,
) -> None:
    result = _run("--cost-log", str(tmp_path / "nope"))
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == ""
