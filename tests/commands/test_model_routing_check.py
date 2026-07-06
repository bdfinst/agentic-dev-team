"""Tests for /model-routing-check — read-only diagnostic command (effort
model). Side-effect-free; surfaces the band→model map, the ladder (or a
starter), the session model, and recent routing bumps.

Ported from tests/commands/model_routing_check_tests.bats (issue #675:
bats -> pytest).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMAND_MD = (
    REPO_ROOT / "plugins" / "dev-team" / "skills" / "model-routing-check" / "SKILL.md"
)
RESOLVER = REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib" / "model_resolve.py"

ROUTING_JSON_CONTENT = """{
  "low": "claude-haiku-4-5-20251001",
  "medium": "claude-sonnet-4-6",
  "high": "claude-opus-4-8",
  "haiku": "claude-haiku-4-5-20251001",
  "sonnet": "claude-sonnet-4-6",
  "opus": "claude-opus-4-8",
  "rounding": "round_half_up"
}
"""


def _extract_exec_script(command_md_text: str) -> str:
    match = re.search(
        r"<!-- BEGIN EXEC -->(.*)<!-- END EXEC -->", command_md_text, re.DOTALL
    )
    assert match, "no <!-- BEGIN EXEC --> ... <!-- END EXEC --> block found"
    body = match.group(1)
    # Drop fenced-code delimiter lines, mirroring the bats sed filter.
    lines = [line for line in body.splitlines() if not line.strip().startswith("```")]
    return "\n".join(lines) + "\n"


@pytest.fixture
def case(tmp_path: Path) -> dict:
    (tmp_path / "knowledge").mkdir()
    (tmp_path / ".claude" / "metrics").mkdir(parents=True)
    routing_json = tmp_path / "knowledge" / "model-routing.json"
    routing_json.write_text(ROUTING_JSON_CONTENT, encoding="utf-8")

    exec_script = tmp_path / "run.sh"
    command_text = COMMAND_MD.read_text(encoding="utf-8")
    exec_script.write_text(_extract_exec_script(command_text), encoding="utf-8")
    exec_script.chmod(0o755)

    env = dict(os.environ)
    env["MODEL_ROUTING_JSON"] = str(routing_json)
    env["MODEL_LADDER_JSON"] = str(tmp_path / ".claude" / "model-ladder.json")
    env["SESSION_MODEL_FILE"] = str(tmp_path / ".claude" / "session-model")
    env["MODEL_BUMP_LOG"] = str(tmp_path / ".claude" / "metrics" / "model-routing.log")
    env["MODEL_ROUTING_RESOLVER"] = str(RESOLVER)
    env["CALIBRATION_FLOORS_JSON"] = str(tmp_path / "knowledge" / "calibration-floors.json")
    env["CALIBRATION_RECORDS_JSON"] = str(
        tmp_path / ".claude" / "evals" / "calibration-records.json"
    )

    return {
        "tmp_path": tmp_path,
        "exec_script": exec_script,
        "env": env,
        "command_text": command_text,
    }


def _routing_hash(routing_path: Path, ladder_path: Path | None) -> str:
    """Mirrors scripts/agent_calibrate.py's routing_hash() exactly."""
    h = hashlib.sha256()
    for p in (routing_path, ladder_path):
        if p is not None and p.exists():
            h.update(p.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def _write_floors(case: dict, entries: dict) -> None:
    Path(case["env"]["CALIBRATION_FLOORS_JSON"]).write_text(
        json.dumps(entries), encoding="utf-8"
    )


def _write_records(case: dict, records: dict) -> None:
    records_path = Path(case["env"]["CALIBRATION_RECORDS_JSON"])
    records_path.parent.mkdir(parents=True, exist_ok=True)
    records_path.write_text(json.dumps(records), encoding="utf-8")


def _run(case: dict, extra_env: dict | None = None) -> subprocess.CompletedProcess:
    # Combine stdout+stderr into one stream to mirror bats' `run`, which
    # captures both into a single $output.
    env = dict(case["env"])
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["bash", str(case["exec_script"])],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )


def _seed_bumps(case: dict, n: int) -> None:
    log_path = Path(case["env"]["MODEL_BUMP_LOG"])
    with log_path.open("a", encoding="utf-8") as fh:
        for i in range(n):
            fh.write(
                '{"ts":"2026-06-01T12:%02d:00Z","band":"high",'
                '"served":"claude-sonnet-4-6","reason":"effort",'
                '"caller":"caller-%d","session":"claude-opus-4-8"}\n' % (i, i)
            )


# ---------------------------------------------------------------------------
# Doc-inspection
# ---------------------------------------------------------------------------


def test_doc_command_markdown_file_exists() -> None:
    assert COMMAND_MD.is_file()


def test_doc_frontmatter_declares_name_and_user_invocable(case: dict) -> None:
    text = case["command_text"]
    assert re.search(r"^name:\s+model-routing-check\s*$", text, re.MULTILINE)
    assert re.search(r"^user-invocable:\s+true\s*$", text, re.MULTILINE)


def test_doc_allowed_tools_lists_read_and_bash(case: dict) -> None:
    text = case["command_text"]
    assert re.search(
        r"^allowed-tools:.*Read.*Bash|^allowed-tools:.*Bash.*Read",
        text,
        re.MULTILINE,
    )


def test_doc_body_declares_read_only_no_side_effects(case: dict) -> None:
    text = case["command_text"].lower()
    assert "read-only" in text
    assert "no side effects" in text


def test_doc_body_documents_four_required_sections(case: dict) -> None:
    text = case["command_text"]
    assert "band → model" in text
    assert "Ladder" in text
    assert "session model" in text.lower()
    assert "recent routing bumps" in text.lower()


def test_doc_body_no_longer_references_retired_probe_or_overrides_file(
    case: dict,
) -> None:
    text = case["command_text"]
    assert not re.search(r"probe|model-overrides", text)


def test_doc_body_contains_executable_block_extractable_by_harness(
    case: dict,
) -> None:
    text = case["command_text"]
    assert "<!-- BEGIN EXEC -->" in text
    assert "<!-- END EXEC -->" in text
    assert case["exec_script"].stat().st_size > 0


# ---------------------------------------------------------------------------
# Behavioral: clean install (no ladder, no session, no log)
# ---------------------------------------------------------------------------


def test_clean_prints_all_three_band_model_pairs(case: dict) -> None:
    result = _run(case)
    assert result.returncode == 0, result.stdout
    assert "low" in result.stdout and "claude-haiku-4-5-20251001" in result.stdout
    assert "medium" in result.stdout and "claude-sonnet-4-6" in result.stdout
    assert "high" in result.stdout and "claude-opus-4-8" in result.stdout


def test_band_model_map_section_is_exact_three_lines_no_garbage(
    case: dict,
) -> None:
    """Regression test for #718: the exec block ran the Python resolver
    through `bash` instead of `python3`, silently corrupting this section
    with bash's line-by-line misinterpretation of Python syntax while the
    command still exited 0. Anchor on the exact section contents so a
    reintroduced `bash "$RESOLVER"` invocation fails this test."""
    result = _run(case)
    assert result.returncode == 0, result.stdout
    lines = result.stdout.splitlines()
    start = lines.index("Effective band → model map:") + 1
    end = start
    while end < len(lines) and lines[end].strip() != "":
        end += 1
    section = lines[start:end]
    assert section == [
        "  low     → claude-haiku-4-5-20251001",
        "  medium  → claude-sonnet-4-6",
        "  high    → claude-opus-4-8",
    ], f"band->model map section corrupted: {section!r}"


def test_clean_run_produces_no_stderr(case: dict) -> None:
    """Regression test for #718: bash-interpreting the Python resolver
    file emits `command not found` / syntax errors. Both stdout and
    stderr are captured together elsewhere in this suite; here they are
    kept separate so stray interpreter errors can't hide as stdout."""
    env = dict(case["env"])
    result = subprocess.run(
        ["bash", str(case["exec_script"])],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == "", result.stderr


def test_clean_prints_starter_ladder_seeded_from_defaults(case: dict) -> None:
    result = _run(case)
    assert result.returncode == 0, result.stdout
    assert "Ladder: none" in result.stdout
    assert "Starter ladder" in result.stdout
    # The starter is the default map as a capability-ascending array.
    assert (
        '["claude-haiku-4-5-20251001","claude-sonnet-4-6","claude-opus-4-8"]'
        in result.stdout
    )


def test_clean_session_model_reported_unknown_when_not_captured(
    case: dict,
) -> None:
    result = _run(case)
    assert result.returncode == 0, result.stdout
    assert "Session model: unknown" in result.stdout


def test_clean_recent_bumps_section_says_none_recorded(case: dict) -> None:
    result = _run(case)
    assert result.returncode == 0, result.stdout
    assert "Recent routing bumps: none recorded" in result.stdout


def test_ladder_present_reflected_in_band_model_map_and_printed(
    case: dict,
) -> None:
    Path(case["env"]["MODEL_LADDER_JSON"]).write_text(
        '["claude-sonnet-4-6", "claude-opus-4-8"]', encoding="utf-8"
    )
    result = _run(case)
    assert result.returncode == 0, result.stdout
    assert "Ladder: from" in result.stdout
    # low → bottom of ladder (sonnet) under the ladder.
    assert "low" in result.stdout and "claude-sonnet-4-6" in result.stdout


def test_session_model_captured_is_printed(case: dict) -> None:
    Path(case["env"]["SESSION_MODEL_FILE"]).write_text(
        "claude-opus-4-8\n", encoding="utf-8"
    )
    result = _run(case)
    assert result.returncode == 0, result.stdout
    assert "Session model: claude-opus-4-8" in result.stdout


def test_clean_run_is_side_effect_free(case: dict) -> None:
    def tree_hash() -> str:
        digest = hashlib.sha256()
        for path in sorted(case["tmp_path"].rglob("*")):
            if path.is_file():
                digest.update(str(path.relative_to(case["tmp_path"])).encode())
                digest.update(path.read_bytes())
        return digest.hexdigest()

    before = tree_hash()
    result = _run(case)
    assert result.returncode == 0, result.stdout
    after = tree_hash()
    assert before == after


# ---------------------------------------------------------------------------
# Recent routing bumps
# ---------------------------------------------------------------------------


def test_three_pre_seeded_bumps_are_all_printed(case: dict) -> None:
    _seed_bumps(case, 3)
    result = _run(case)
    assert result.returncode == 0, result.stdout
    assert "caller-0" in result.stdout
    assert "caller-1" in result.stdout
    assert "caller-2" in result.stdout


def test_bump_lines_carry_band_served_session_and_caller(case: dict) -> None:
    _seed_bumps(case, 1)
    result = _run(case)
    assert result.returncode == 0, result.stdout
    assert "high → claude-sonnet-4-6" in result.stdout
    assert "[effort]" in result.stdout
    assert "session=claude-opus-4-8" in result.stdout
    assert "caller=caller-0" in result.stdout


def test_25_events_default_to_last_10_plus_showing_line(case: dict) -> None:
    _seed_bumps(case, 25)
    result = _run(case)
    assert result.returncode == 0, result.stdout
    assert (
        "Showing last 10 of 25 bump events; raise MODEL_BUMP_TAIL to see more."
        in result.stdout
    )
    assert "caller=caller-15" in result.stdout
    assert "caller=caller-24" in result.stdout


def test_model_bump_tail_30_shows_all_25_no_showing_last_line(
    case: dict,
) -> None:
    _seed_bumps(case, 25)
    result = _run(case, extra_env={"MODEL_BUMP_TAIL": "30"})
    assert result.returncode == 0, result.stdout
    assert "caller=caller-0" in result.stdout
    assert "caller=caller-24" in result.stdout
    assert "Showing last 10 of 25" not in result.stdout


# ---------------------------------------------------------------------------
# Recalibration staleness advisory (issue #883, slice 4 of epic #879)
# ---------------------------------------------------------------------------


def test_doc_body_documents_recalibration_staleness_advisory(case: dict) -> None:
    text = case["command_text"].lower()
    assert "recalibration staleness advisory" in text
    assert "never blocks dispatch" in text
    assert "calibration-stale" in text
    assert "never-calibrated" in text


def test_doc_body_documents_five_sections(case: dict) -> None:
    assert "Five sections" in case["command_text"]


def test_routing_map_changed_since_last_calibration_flags_stale(case: dict) -> None:
    """Gherkin: Routing map changed since last calibration."""
    _write_floors(case, {"security-review": {"riskClass": "high", "floor": 1.0}})
    routing_path = Path(case["env"]["MODEL_ROUTING_JSON"])
    ladder_path = Path(case["env"]["MODEL_LADDER_JSON"])
    stale_hash = _routing_hash(routing_path, None)  # hash of a prior, different state
    _write_records(
        case,
        {
            "security-review": {
                "target": "security-review",
                "timestamp": "2026-01-01T00:00:00Z",
                "declared_band": "high",
                "calibrated_band": "high",
                "verdict": "aligned",
                "routing_hash": "not-the-current-hash-" + stale_hash[:8],
            }
        },
    )

    result = _run(case)
    assert result.returncode == 0, result.stdout
    assert "security-review" in result.stdout
    assert "calibration-stale" in result.stdout
    assert "/agent-eval --calibrate --agent security-review" in result.stdout


def test_target_never_calibrated_is_listed(case: dict) -> None:
    """Gherkin: Target never calibrated."""
    _write_floors(case, {"naming-review": {"riskClass": "standard", "floor": 0.9}})
    # No calibration-records.json written at all.

    result = _run(case)
    assert result.returncode == 0, result.stdout
    assert "naming-review" in result.stdout
    assert "never-calibrated" in result.stdout
    assert "/agent-eval --calibrate --agent naming-review" in result.stdout


def test_calibration_current_when_hash_matches(case: dict) -> None:
    routing_path = Path(case["env"]["MODEL_ROUTING_JSON"])
    ladder_path = Path(case["env"]["MODEL_LADDER_JSON"])
    _write_floors(case, {"doc-review": {"riskClass": "standard", "floor": 0.9}})
    current_hash = _routing_hash(routing_path, None)  # ladder doesn't exist yet
    _write_records(
        case,
        {
            "doc-review": {
                "target": "doc-review",
                "timestamp": "2026-01-01T00:00:00Z",
                "declared_band": "medium",
                "calibrated_band": "medium",
                "verdict": "aligned",
                "routing_hash": current_hash,
            }
        },
    )

    result = _run(case)
    assert result.returncode == 0, result.stdout
    assert "doc-review" in result.stdout
    assert "calibration-current" in result.stdout


def test_advisory_never_blocks_even_when_every_record_is_stale(case: dict) -> None:
    """Gherkin: Advisory never blocks — the model-resolution hook's dispatch
    behavior (here, the band -> model map this same command prints) is
    unchanged regardless of how many targets are stale/never-calibrated."""
    _write_floors(
        case,
        {
            "security-review": {"riskClass": "high", "floor": 1.0},
            "concurrency-review": {"riskClass": "high", "floor": 1.0},
        },
    )
    _write_records(
        case,
        {
            "security-review": {
                "target": "security-review",
                "timestamp": "2026-01-01T00:00:00Z",
                "declared_band": "high",
                "calibrated_band": "high",
                "verdict": "aligned",
                "routing_hash": "definitely-stale",
            },
            "concurrency-review": {
                "target": "concurrency-review",
                "timestamp": "2026-01-01T00:00:00Z",
                "declared_band": "high",
                "calibrated_band": "high",
                "verdict": "aligned",
                "routing_hash": "also-stale",
            },
        },
    )

    result = _run(case)
    assert result.returncode == 0, result.stdout
    assert result.stdout.count("calibration-stale") == 2
    # The band -> model map (a stand-in for hook dispatch resolution) is
    # still printed correctly, unaffected by the advisory findings.
    assert "low" in result.stdout and "claude-haiku-4-5-20251001" in result.stdout
    assert "medium" in result.stdout and "claude-sonnet-4-6" in result.stdout
    assert "high" in result.stdout and "claude-opus-4-8" in result.stdout


def test_no_floors_entries_prints_graceful_message(case: dict) -> None:
    """No calibration-floors.json at all — advisory degrades gracefully,
    never errors."""
    result = _run(case)
    assert result.returncode == 0, result.stdout
    assert "no calibration-floors.json entries found" in result.stdout
