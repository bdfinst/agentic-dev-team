"""Tests for the #868 agent-ablation feature: `/agent-eval --ablation <agent>`
runs the integration tier twice (baseline: full roster, ablated: roster minus
target agent), K=3 trials per arm, and reports a deterministic delta across
three dimensions (issues caught, testCommands, tokens) that `/harness-audit`
can cite as causal drop-candidate evidence.

Covers, per the issue's Acceptance Criteria:
  - ablation-runs-exactly-two-integration-passes (roster-exclusion wiring)
  - delta-report-covers-issues-testcommands-and-token-cost
  - results-persist-with-model-version-and-timestamp
  - harness-audit-cites-ablation-evidence-in-drop-recommendations (lookup helper)
  - failing-baseline-blocks-delta-claims

No live `claude -p` dispatch or real ephemeral worktree is exercised — the
orchestrator subprocess and worktree creation are mocked/stubbed throughout.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

SCRIPTS = REPO_ROOT / "scripts"
RIE_PATH = SCRIPTS / "run_integration_eval.py"
ABLATION_PATH = SCRIPTS / "eval_ablation.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


rie = _load_module(RIE_PATH, "run_integration_eval_agentablation")
ablation = _load_module(ABLATION_PATH, "eval_ablation_agentablation")


# ---------------------------------------------------------------------------
# run_integration_eval.py: --ablate-agent / DEV_TEAM_ABLATE_AGENT wiring,
# and per-run token/issues_caught recording. The orchestrator subprocess
# itself is stubbed (monkeypatched) — no live dispatch or real worktree.
# ---------------------------------------------------------------------------


def test_dispatch_orchestrator_injects_ablate_agent_env_var(monkeypatch, tmp_path):
    captured = {}

    def fake_run(cmd, cwd, env, capture_output, text, check):
        captured["cmd"] = cmd
        captured["env"] = env

        class Result:
            stdout = '{"usage": {"input_tokens": 10, "output_tokens": 5}}'

        return Result()

    monkeypatch.setattr(rie.subprocess, "run", fake_run)
    tokens = rie.dispatch_orchestrator(
        tmp_path, Path("spec.md"), "claude-sonnet-4-6", ablate_agent="security-review"
    )
    assert captured["env"]["DEV_TEAM_ABLATE_AGENT"] == "security-review"
    assert tokens == 15


def test_dispatch_orchestrator_omits_ablate_agent_env_var_when_not_set(
    monkeypatch, tmp_path
):
    captured = {}

    def fake_run(cmd, cwd, env, capture_output, text, check):
        captured["env"] = env

        class Result:
            stdout = "{}"

        return Result()

    monkeypatch.setattr(rie.subprocess, "run", fake_run)
    rie.dispatch_orchestrator(tmp_path, Path("spec.md"), "claude-sonnet-4-6")
    assert "DEV_TEAM_ABLATE_AGENT" not in captured["env"]


def test_run_fixture_records_tokens_and_issues_caught(monkeypatch, tmp_path):
    fixtures_dir = tmp_path / "fixtures"
    fixture_dir = fixtures_dir / "int-demo"
    fixture_dir.mkdir(parents=True)

    # A trivial, valid tarball is unnecessary: stub extract_golden_repo and
    # init_worktree so no real worktree/tarball machinery runs.
    monkeypatch.setattr(rie, "extract_golden_repo", lambda tarball, dest: None)
    monkeypatch.setattr(rie, "init_worktree", lambda workdir: None)

    def fake_dispatch(workdir, spec_path, model, ablate_agent=""):
        # Simulate the orchestrator writing a review-value log inside the
        # worktree, as /build's inline review checkpoints do.
        metrics_dir = workdir / "metrics"
        metrics_dir.mkdir(parents=True, exist_ok=True)
        (metrics_dir / "review-value.jsonl").write_text(
            json.dumps({"issues_found": 2}) + "\n" + json.dumps({"issues_found": 1}) + "\n"
        )
        return 42

    monkeypatch.setattr(rie, "dispatch_orchestrator", fake_dispatch)
    monkeypatch.setattr(rie, "run_commands", lambda workdir, commands: [
        {"command": c, "exit_code": 0, "stderr_first_line": ""} for c in commands
    ])

    actual = rie.run_fixture(
        "int-demo",
        "orchestrator",
        {"goldenRepo": "golden.tar.gz", "spec": "spec.md", "testCommands": ["pytest"]},
        fixtures_dir,
        skip_dispatch=False,
        model="claude-sonnet-4-6",
        ablate_agent="security-review",
    )
    assert actual["tokens"] == 42
    assert actual["issues_caught"] == 3
    assert actual["results"] == [{"command": "pytest", "exit_code": 0, "stderr_first_line": ""}]


def test_run_fixture_skip_dispatch_records_zero_tokens_and_issues(monkeypatch, tmp_path):
    fixtures_dir = tmp_path / "fixtures"
    (fixtures_dir / "int-demo").mkdir(parents=True)
    monkeypatch.setattr(rie, "extract_golden_repo", lambda tarball, dest: None)
    monkeypatch.setattr(rie, "init_worktree", lambda workdir: None)
    monkeypatch.setattr(rie, "run_commands", lambda workdir, commands: [])

    actual = rie.run_fixture(
        "int-demo", "orchestrator",
        {"goldenRepo": "g.tar.gz", "spec": "spec.md", "testCommands": []},
        fixtures_dir, skip_dispatch=True, model="claude-sonnet-4-6",
    )
    assert actual == {"results": [], "tokens": 0, "issues_caught": 0}


# ---------------------------------------------------------------------------
# eval_ablation.py --mode agent: delta computation across all three
# dimensions, failing-baseline gate, and the harness-audit lookup helper.
# ---------------------------------------------------------------------------

EXPECTED_INT_DEMO = json.dumps({
    "fixture": "int-demo",
    "applicableSkills": ["orchestrator"],
    "integration": {
        "orchestrator": {
            "grader": "integration",
            "spec": "spec.md",
            "goldenRepo": "golden-repo.tar.gz",
            "testCommands": ["pytest"],
        }
    },
})


def _trial_actual(exit_code: int, tokens: int, issues_caught: int) -> dict:
    return {
        "int-demo": {
            "integration": {
                "orchestrator": {
                    "results": [{"command": "pytest", "exit_code": exit_code,
                                "stderr_first_line": ""}],
                    "tokens": tokens,
                    "issues_caught": issues_caught,
                }
            }
        }
    }


@pytest.fixture
def expected_dir(tmp_path: Path) -> Path:
    d = tmp_path / "expected"
    d.mkdir()
    (d / "int-demo.json").write_text(EXPECTED_INT_DEMO)
    return d


def test_agent_ablation_report_covers_all_three_delta_dimensions(expected_dir):
    baseline_trials = [_trial_actual(0, 100, 4) for _ in range(3)]
    ablated_trials = [_trial_actual(0, 60, 4) for _ in range(3)]

    report = ablation.agent_ablation_report(
        expected_dir, baseline_trials, ablated_trials,
        ablated_agent="security-review", model="claude-sonnet-4-6",
    )
    assert report["schema"] == "eval-ablation/v1"
    assert report["ablated_agent"] == "security-review"
    assert report["model"] == "claude-sonnet-4-6"
    assert "recorded_at" in report and report["recorded_at"].endswith("Z")
    assert set(report["delta"]) == {"issues_caught", "test_commands_passed", "tokens"}
    assert report["delta"]["issues_caught"] == 0
    assert report["delta"]["tokens"] == -40
    assert report["delta"]["test_commands_passed"] == 0
    assert report["baseline"]["grade"] == "pass"
    assert report["verdict"] == "no measured impact — supports drop"


def test_agent_ablation_load_bearing_agent_shows_negative_delta_and_retain_verdict(
    expected_dir,
):
    baseline_trials = [_trial_actual(0, 100, 4) for _ in range(3)]
    # Ablated arm: the same test now fails (agent was catching a regression
    # the orchestrator introduced) -> dropped in issues too.
    ablated_trials = [_trial_actual(1, 100, 1) for _ in range(3)]

    report = ablation.agent_ablation_report(
        expected_dir, baseline_trials, ablated_trials,
        ablated_agent="security-review", model="claude-sonnet-4-6",
    )
    assert report["delta"]["issues_caught"] == -3
    assert report["delta"]["test_commands_passed"] == -1
    assert report["verdict"] == "agent is load-bearing — retain"


def test_agent_ablation_failing_baseline_blocks_verdict(expected_dir):
    # Baseline itself never passes -> uninterpretable, regardless of ablated arm.
    baseline_trials = [_trial_actual(1, 100, 0) for _ in range(3)]
    ablated_trials = [_trial_actual(0, 100, 4) for _ in range(3)]

    report = ablation.agent_ablation_report(
        expected_dir, baseline_trials, ablated_trials,
        ablated_agent="security-review", model="claude-sonnet-4-6",
    )
    assert report["baseline"]["grade"] == "fail"
    assert report["verdict"] == "baseline failed — inconclusive"


def test_agent_ablation_report_persists_as_valid_jsonl(expected_dir, tmp_path):
    baseline_trials = [_trial_actual(0, 100, 4) for _ in range(3)]
    ablated_trials = [_trial_actual(0, 100, 4) for _ in range(3)]
    log = tmp_path / "eval-ablation.jsonl"

    report = ablation.agent_ablation_report(
        expected_dir, baseline_trials, ablated_trials,
        ablated_agent="doc-review", model="claude-sonnet-4-6",
    )
    with open(log, "a") as fh:
        fh.write(json.dumps(report, sort_keys=True) + "\n")

    lines = log.read_text().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["schema"] == "eval-ablation/v1"
    assert parsed["model"] == "claude-sonnet-4-6"
    assert "recorded_at" in parsed


def test_find_latest_ablation_record_returns_most_recent_for_agent(tmp_path):
    log = tmp_path / "eval-ablation.jsonl"
    older = {"schema": "eval-ablation/v1", "ablated_agent": "doc-review",
             "recorded_at": "2026-01-01T00:00:00Z", "verdict": "no measured impact — supports drop"}
    newer = {"schema": "eval-ablation/v1", "ablated_agent": "doc-review",
             "recorded_at": "2026-06-01T00:00:00Z", "verdict": "agent is load-bearing — retain"}
    other_agent = {"schema": "eval-ablation/v1", "ablated_agent": "security-review",
                   "recorded_at": "2026-12-01T00:00:00Z", "verdict": "no measured impact — supports drop"}
    log.write_text(
        json.dumps(older) + "\n" + json.dumps(newer) + "\n" + json.dumps(other_agent) + "\n"
    )
    result = ablation.find_latest_ablation_record(log, "doc-review")
    assert result == newer


def test_find_latest_ablation_record_returns_none_when_no_match(tmp_path):
    log = tmp_path / "eval-ablation.jsonl"
    log.write_text(json.dumps(
        {"schema": "eval-ablation/v1", "ablated_agent": "other", "recorded_at": "2026-01-01T00:00:00Z"}
    ) + "\n")
    assert ablation.find_latest_ablation_record(log, "doc-review") is None


def test_find_latest_ablation_record_missing_file_returns_none(tmp_path):
    assert ablation.find_latest_ablation_record(tmp_path / "absent.jsonl", "doc-review") is None


# ---------------------------------------------------------------------------
# CLI-level checks (subprocess) for --mode agent argument validation and
# --find-latest, matching the style of the existing eval_ablation.py tests.
# ---------------------------------------------------------------------------


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ABLATION_PATH), *args], capture_output=True, text=True
    )


def test_cli_agent_mode_requires_model(tmp_path):
    baseline_dir = tmp_path / "baseline"
    ablated_dir = tmp_path / "ablated"
    baseline_dir.mkdir()
    ablated_dir.mkdir()
    res = _run_cli(
        "--mode", "agent",
        "--baseline-trials-dir", str(baseline_dir),
        "--ablated-trials-dir", str(ablated_dir),
        "--ablated-agent", "doc-review",
    )
    assert res.returncode == 2
    assert "--model" in res.stderr


def test_cli_find_latest_prints_null_when_absent(tmp_path):
    res = _run_cli("--find-latest", "doc-review", "--jsonl", str(tmp_path / "none.jsonl"))
    assert res.returncode == 0
    assert res.stdout.strip() == "null"
