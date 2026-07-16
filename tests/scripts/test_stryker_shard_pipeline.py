"""Pytest tests for stryker_shard_pipeline.py + stryker_timeout_retry.py — the
Slice 5 shard pipeline (worktree-compounding + timeout-abort) and timeout-retry
helper (#1136).

Each test maps to a Slice 5 Gherkin scenario in
``plans/generalize-aci-mutation-pipeline-fold-into-mutation-kill.md``. Every
git / Stryker / subprocess call is mocked — no real .NET tooling, no real git
worktree — and every project name is generic. (The two wrapper line-callback
scenarios live in ``test_csharp_stryker_net_wrapper.py``, alongside the wrapper.)
"""

from __future__ import annotations

import json
import re
import sys
import threading
import time
from pathlib import Path

import pytest

SCRIPTS_DIR = (
    Path(__file__).resolve().parents[2]
    / "plugins"
    / "dev-team"
    / "skills"
    / "mutation-testing"
    / "scripts"
)
sys.path.insert(0, str(SCRIPTS_DIR))

import stryker_shard_pipeline as pipeline  # noqa: E402
import stryker_timeout_retry as retry  # noqa: E402

FORBIDDEN_LITERALS = [
    "Aci.Speedpay",
    "Controllers",
    "AwesomeAssertions",
    "Moq",
    "AutoFixture",
]

TS_RE = re.compile(r"\d{2}:\d{2}:\d{2}")


# =============================================================================
# Fixture helpers
# =============================================================================
def _write_shard_config(repo_root: Path, shard: str, *, test_projects=("test/W.Tests/W.Tests.csproj",)) -> Path:
    path = pipeline.shard_config_path(repo_root, shard)
    path.write_text(
        json.dumps(
            {
                "stryker-config": {
                    "solution": "Stryker.sln",
                    "project": f"src/W.{shard}/W.{shard}.csproj",
                    "test-projects": list(test_projects),
                    "mutate": [f"src/W.{shard}/**/*.cs"],
                }
            }
        ),
        encoding="utf-8",
    )
    return path


def _mutant(status: str, mutator: str = "ArithmeticOperator", line: int = 1) -> dict:
    return {
        "mutatorName": mutator,
        "status": status,
        "location": {"start": {"line": line}},
        "replacement": "<replacement>",
    }


def _write_report(out_dir: Path, files: dict) -> Path:
    rp = pipeline.report_path(out_dir)
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text(json.dumps({"files": files}), encoding="utf-8")
    return rp


class _Recorder:
    """Collects log lines + git commands + loop-launch commands."""

    def __init__(self):
        self.logs = []
        self.git = []
        self.launches = []

    def log(self, line):
        self.logs.append(line)

    def git_run(self, cmd, repo_root, check):
        self.git.append(list(cmd))

    def run(self, cmd, cwd=None):
        self.launches.append(list(cmd))


# =============================================================================
# Scenario: Shards are discovered from config files (sorted order)
# =============================================================================
def test_discovers_shards_in_sorted_order(tmp_path):
    _write_shard_config(tmp_path, "webapi")
    _write_shard_config(tmp_path, "application-services")
    _write_shard_config(tmp_path, "domain")
    assert pipeline.discover_shards(tmp_path) == [
        "application-services",
        "domain",
        "webapi",
    ]


# =============================================================================
# Scenario: Missing shard configs point to setup
# =============================================================================
def test_missing_shard_configs_raise_actionable_error(tmp_path):
    with pytest.raises(pipeline.ShardSetupMissing) as exc:
        pipeline.discover_shards(tmp_path)
    assert "shard setup" in str(exc.value).lower()
    assert "stryker_shard_setup.py" in str(exc.value)


def test_main_missing_configs_exits_nonzero_naming_setup(tmp_path, capsys):
    rc = pipeline.main(["--repo-root", str(tmp_path)])
    assert rc == 1
    assert "stryker_shard_setup.py" in capsys.readouterr().err


# =============================================================================
# Scenario: Each shard runs in its own worktree created from HEAD, and the
# second shard's worktree includes the first shard's committed fixes.
# =============================================================================
def test_worktrees_are_created_from_head_and_shards_compound(tmp_path):
    rec = _Recorder()
    out_base = tmp_path / "out"
    for shard in ("a", "b"):
        _write_shard_config(tmp_path, shard)
        _write_report(out_base / shard, {"src/W.a/Foo.cs": {"mutants": [_mutant("Survived")]}})

    events = []
    failed = pipeline.run_all(
        ["a", "b"],
        repo_root=tmp_path,
        worktree_base=tmp_path / ".wt",
        shard_out_base=out_base,
        stryker_bin="fake-stryker",
        model=None,
        max_rounds=3,
        skip_agent=False,
        skip_existing=False,
        max_age_hours=0,
        log=rec.log,
        run_stryker=lambda **kw: 0,
        run=rec.run,
        resolve_test_file=lambda *a: Path("test/W.Tests/FooTests.cs"),
        git_run=rec.git_run,
        events=events,
    )

    assert failed == []
    # Every worktree is created from HEAD.
    adds = [c for c in rec.git if c[:3] == ["git", "worktree", "add"]]
    assert len(adds) == 2
    assert all(c[-1] == "HEAD" for c in adds)
    # Compounding: each shard's fixes are committed (fix launch) BEFORE the
    # next shard's worktree is created from HEAD.
    assert events == [
        ("worktree_add", "a"),
        ("fix", "a"),
        ("worktree_add", "b"),
        ("fix", "b"),
    ]


# =============================================================================
# Scenario: The per-shard survivor-fix launch forces headless generation
# =============================================================================
def test_survivor_fix_launch_forces_headless(tmp_path):
    rec = _Recorder()
    out_dir = tmp_path / "out" / "a"
    config = _write_shard_config(tmp_path, "a")
    _write_report(out_dir, {"src/W.a/Foo.cs": {"mutants": [_mutant("Survived")]}})

    pipeline.launch_survivor_fix(
        "a",
        repo_root=tmp_path,
        out_dir=out_dir,
        config_path=config,
        model="claude-x",
        max_rounds=2,
        run=rec.run,
        resolve_test_file=lambda *a: Path("test/W.Tests/FooTests.cs"),
        log=rec.log,
    )

    assert len(rec.launches) == 1
    cmd = rec.launches[0]
    assert "--headless" in cmd
    assert pipeline.LOOP_SCRIPT in cmd
    assert "--file" in cmd and "Foo.cs" in cmd
    assert "--report" in cmd


def test_build_loop_command_always_includes_headless():
    cmd = pipeline.build_loop_command(
        config=Path("stryker-config.json"),
        source_file="Foo.cs",
        source_path="src/W/Foo.cs",
        test_file=Path("test/FooTests.cs"),
        report=Path("out/reports/mutation-report.json"),
        model=None,
        max_rounds=3,
    )
    assert "--headless" in cmd
    # No live-agent dependency: the invocation is a self-contained subprocess.
    assert cmd[0] == pipeline.PYTHON


# =============================================================================
# Scenario: A timeout aborts the shard via the callback
# =============================================================================
def test_timeout_callback_sets_flag_and_requests_abort():
    flag = threading.Event()
    cb = pipeline.make_timeout_callback(flag, log=lambda _l: None)
    assert cb("Testing mutants...\n") is False
    assert not flag.is_set()
    assert cb("5 mutants got status Timeout\n") is True
    assert flag.is_set()


def test_timeout_marks_shard_failed(tmp_path):
    rec = _Recorder()
    _write_shard_config(tmp_path, "a")

    def fake_run_stryker(**kw):
        cb = kw["line_callback"]
        for line in ["starting\n", "5 mutants got status Timeout\n", "tail\n"]:
            if cb(line):
                return -15  # terminated
        return 0

    ok = pipeline.run_shard_stryker(
        "a",
        repo_root=tmp_path,
        worktree=tmp_path / ".wt" / "shard-a",
        out_dir=tmp_path / "out" / "a",
        stryker_bin="fake-stryker",
        log=rec.log,
        run_stryker=fake_run_stryker,
    )
    assert ok is False
    assert any("ABORTED (timeout)" in line for line in rec.logs)


def test_run_all_marks_timed_out_shard_failed(tmp_path):
    rec = _Recorder()
    _write_shard_config(tmp_path, "a")

    def fake_run_stryker(**kw):
        kw["line_callback"]("7 mutants got status Timeout\n")
        return -15

    failed = pipeline.run_all(
        ["a"],
        repo_root=tmp_path,
        worktree_base=tmp_path / ".wt",
        shard_out_base=tmp_path / "out",
        stryker_bin="fake-stryker",
        model=None,
        max_rounds=3,
        skip_agent=True,
        skip_existing=False,
        max_age_hours=0,
        log=rec.log,
        run_stryker=fake_run_stryker,
        run=rec.run,
        git_run=rec.git_run,
    )
    assert failed == ["a"]


# =============================================================================
# Scenario: Resume precedence — --skip-existing wins over --max-age-hours
# =============================================================================
def test_skip_existing_wins_over_max_age(tmp_path):
    rec = _Recorder()
    out_dir = tmp_path / "out" / "a"
    rp = _write_report(out_dir, {"src/W.a/Foo.cs": {"mutants": [_mutant("Survived")]}})
    # Make the report ancient — far older than any --max-age-hours window.
    old = time.time() - 10 * 24 * 3600
    import os

    os.utime(rp, (old, old))

    skipped = pipeline.should_skip(
        out_dir, skip_existing=True, max_age_hours=1, shard="a", log=rec.log
    )
    assert skipped is True
    assert any("--skip-existing wins over --max-age-hours" in line for line in rec.logs)


def test_max_age_applies_only_when_skip_existing_unset(tmp_path):
    out_dir = tmp_path / "out" / "a"
    _write_report(out_dir, {"src/W.a/Foo.cs": {"mutants": []}})
    # Fresh report (just written) with a generous window → skipped by age.
    assert (
        pipeline.should_skip(
            out_dir, skip_existing=False, max_age_hours=24, shard="a", log=lambda _l: None
        )
        is True
    )
    # No report → never skipped.
    assert (
        pipeline.should_skip(
            tmp_path / "out" / "missing",
            skip_existing=True,
            max_age_hours=24,
            shard="missing",
            log=lambda _l: None,
        )
        is False
    )


# =============================================================================
# Scenario: Per-shard progress is emitted while running
# =============================================================================
def test_per_shard_start_and_done_lines_are_timestamped(tmp_path):
    rec = _Recorder()
    _write_shard_config(tmp_path, "a")

    pipeline.process_shard(
        "a",
        repo_root=tmp_path,
        worktree_base=tmp_path / ".wt",
        shard_out_base=tmp_path / "out",
        stryker_bin="fake-stryker",
        model=None,
        max_rounds=3,
        skip_agent=True,
        skip_existing=False,
        max_age_hours=0,
        log=rec.log,
        run_stryker=lambda **kw: 0,
        run=rec.run,
        git_run=rec.git_run,
    )
    starts = [ln for ln in rec.logs if "Shard START: a" in ln]
    dones = [ln for ln in rec.logs if "Shard DONE: a" in ln]
    assert starts and dones
    assert TS_RE.search(starts[0]) and TS_RE.search(dones[0])


# =============================================================================
# Scenario: The summary uses the honest score
# =============================================================================
def test_summary_uses_honest_score_with_timeout_and_nocoverage_separate(tmp_path, capsys):
    out_base = tmp_path / "out"
    mutants = (
        [_mutant("Killed")] * 2
        + [_mutant("Survived")] * 1
        + [_mutant("Timeout")] * 20
        + [_mutant("NoCoverage")] * 0
    )
    _write_report(out_base / "a", {"src/W.a/Foo.cs": {"mutants": mutants}})

    pipeline.print_summary(["a"], out_base)
    out = capsys.readouterr().out
    # Honest score = 2 / (2 + 1 + 0) = 66.7% — NOT the timeout-inflated
    # reported score of (2 + 20) / 23 ≈ 95.7%.
    assert "honest=66.7%" in out
    assert "95." not in out
    assert "timeout=20" in out
    assert "nocoverage=0" in out


def test_summary_reports_missing_report(tmp_path, capsys):
    pipeline.print_summary(["ghost"], tmp_path / "out")
    assert "ghost: no report" in capsys.readouterr().out


# =============================================================================
# Scenario: The timeout-retry helper targets only timed-out files
# =============================================================================
def test_timeout_retry_scopes_to_timed_out_files_with_increased_timeout(tmp_path):
    report = tmp_path / "mutation-report.json"
    report.write_text(
        json.dumps(
            {
                "files": {
                    "src/W/Slow.cs": {"mutants": [_mutant("Timeout"), _mutant("Timeout")]},
                    "src/W/Fast.cs": {"mutants": [_mutant("Killed"), _mutant("Survived")]},
                }
            }
        ),
        encoding="utf-8",
    )
    by_file = retry.timeout_files_from_report(report)
    assert by_file == {"src/W/Slow.cs": 2}  # Fast.cs (no timeouts) excluded

    base = {
        "solution": "App.sln",
        "test-projects": ["test/W.Tests/W.Tests.csproj"],
        "additional-timeout": 5000,
    }
    mutate = retry.build_mutate_globs(list(by_file))
    cfg = retry.build_retry_config(base, mutate, 10000)["stryker-config"]
    assert cfg["mutate"] == ["**/Slow.cs"]  # only the timed-out file
    assert cfg["additional-timeout"] == 15000  # 5000 base + 10000 increase
    assert cfg["test-projects"] == ["test/W.Tests/W.Tests.csproj"]


def test_timeout_retry_main_writes_scoped_config(tmp_path, capsys):
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps({"files": {"src/W/Slow.cs": {"mutants": [_mutant("Timeout")]}}}),
        encoding="utf-8",
    )
    base = tmp_path / "stryker-config.json"
    base.write_text(
        json.dumps(
            {"stryker-config": {"solution": "App.sln", "test-projects": ["t/T.csproj"]}}
        ),
        encoding="utf-8",
    )
    out = tmp_path / "retry.json"
    rc = retry.main(
        [str(report), "--base-config", str(base), "--out", str(out)]
    )
    assert rc == 0
    written = json.loads(out.read_text())["stryker-config"]
    assert written["mutate"] == ["**/Slow.cs"]
    assert written["additional-timeout"] == retry.DEFAULT_ADDITIONAL_TIMEOUT_MS


def test_timeout_retry_main_no_timeouts_is_noop(tmp_path, capsys):
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps({"files": {"src/W/Fast.cs": {"mutants": [_mutant("Killed")]}}}),
        encoding="utf-8",
    )
    rc = retry.main([str(report), "--out", str(tmp_path / "retry.json")])
    assert rc == 0
    assert "Nothing to retry" in capsys.readouterr().out
    assert not (tmp_path / "retry.json").exists()


# =============================================================================
# AC1: neither migrated module carries a repo-specific literal
# =============================================================================
@pytest.mark.parametrize(
    "module_name",
    ["stryker_shard_pipeline.py", "stryker_timeout_retry.py"],
)
def test_no_repo_specific_literal(module_name):
    source = (SCRIPTS_DIR / module_name).read_text(encoding="utf-8")
    for literal in FORBIDDEN_LITERALS:
        assert literal not in source, f"{literal} leaked into {module_name}"
