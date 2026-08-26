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
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from _mutation_test_helpers import FORBIDDEN_LITERALS, SCRIPTS_DIR

sys.path.insert(0, str(SCRIPTS_DIR))

import stryker_shard_pipeline as pipeline
import stryker_timeout_retry as retry

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
    """Collects log lines + git commands + loop-launch commands.

    ``run`` returns a ``subprocess.CompletedProcess``-shaped stand-in (with a
    ``.returncode``) — mirrors the real ``subprocess.run`` contract that
    ``launch_survivor_fix`` inspects. Set ``run_returncode`` (or
    ``run_returncodes`` for a per-call sequence) before invoking to simulate
    a launched fix exiting non-zero (e.g. the #1598 fatal-revert exit code).
    """

    def __init__(self):
        self.logs = []
        self.git = []
        self.launches = []
        self.run_returncode = 0
        self.run_returncodes: list[int] | None = None

    def log(self, line):
        self.logs.append(line)

    def git_run(self, cmd, repo_root, check):
        self.git.append(list(cmd))

    def run(self, cmd, cwd=None):
        self.launches.append(list(cmd))
        rc = (
            self.run_returncodes.pop(0)
            if self.run_returncodes
            else self.run_returncode
        )
        return subprocess.CompletedProcess(cmd, rc)


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
# Scenario: main()'s exit code reflects run_all's failed/exhausted results.
# Drives main() end to end through a fake run_all — real git worktree
# creation and Stryker/.NET invocation are not exercised here (covered by
# the run_all/process_shard tests above); this harness isolates main()'s own
# exit-code decision logic.
# =============================================================================
def _run_main_with_fake_run_all(tmp_path, monkeypatch, *, failed, exhausted):
    _write_shard_config(tmp_path, "a")
    monkeypatch.setattr(
        pipeline.wrapper, "resolve_dotnet_root", lambda **kw: ("/fake/dotnet", None)
    )
    monkeypatch.setattr(
        pipeline, "run_all", lambda *a, **kw: pipeline.ShardRunResult(failed, exhausted)
    )
    return pipeline.main(["--repo-root", str(tmp_path)])


def test_main_returns_zero_for_clean_run(tmp_path, monkeypatch):
    rc = _run_main_with_fake_run_all(tmp_path, monkeypatch, failed=[], exhausted=[])
    assert rc == 0


def test_main_returns_one_on_shard_failure(tmp_path, monkeypatch):
    rc = _run_main_with_fake_run_all(tmp_path, monkeypatch, failed=["a"], exhausted=[])
    assert rc == 1


def test_main_returns_exit_generation_exhausted_for_exhaustion_only_run(tmp_path, monkeypatch):
    rc = _run_main_with_fake_run_all(
        tmp_path, monkeypatch, failed=[], exhausted=["a/src/W.a/Foo.cs"]
    )
    assert rc == pipeline.EXIT_GENERATION_EXHAUSTED


def test_main_prioritizes_failure_over_exhaustion(tmp_path, monkeypatch):
    rc = _run_main_with_fake_run_all(
        tmp_path, monkeypatch, failed=["a"], exhausted=["a/src/W.a/Foo.cs"]
    )
    assert rc == 1


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
    result = pipeline.run_all(
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

    assert result.failed == []
    assert result.exhausted == []
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


# =============================================================================
# Scenario: A non-zero exit from the headless loop (e.g. the #1598
# fatal-revert exit code) stops the per-file loop instead of silently
# continuing onto a working tree that may already be in an unknown state.
# =============================================================================
def test_survivor_fix_stops_launching_further_files_after_a_nonzero_exit(tmp_path):
    rec = _Recorder()
    rec.run_returncode = 4  # mutation_kill_headless's fatal-revert exit code
    out_dir = tmp_path / "out" / "a"
    config = _write_shard_config(tmp_path, "a")
    _write_report(
        out_dir,
        {
            "src/W.a/Foo.cs": {"mutants": [_mutant("Survived")]},
            "src/W.a/Bar.cs": {"mutants": [_mutant("Survived")]},
        },
    )

    ok = pipeline.launch_survivor_fix(
        "a",
        repo_root=tmp_path,
        out_dir=out_dir,
        config_path=config,
        model=None,
        max_rounds=2,
        run=rec.run,
        resolve_test_file=lambda source, *a: Path(f"test/W.Tests/{Path(source).stem}Tests.cs"),
        log=rec.log,
    )

    assert ok is False
    # Only the first file's fix is launched — the second file is never
    # reached once the first exits non-zero.
    assert len(rec.launches) == 1
    assert any("FAILED (headless)" in line and "exit 4" in line for line in rec.logs)


# =============================================================================
# Scenario: launch_survivor_fix stops the shard on ANY non-zero, non-4,
# non-5 exit code — not just the fatal-revert exit code 4 (#1930's "this
# treats every non-4-non-5 exit the same as a failed revert" claim was
# previously only verified with rc=4).
# =============================================================================
def test_survivor_fix_stops_on_an_arbitrary_nonzero_exit_not_just_4(tmp_path):
    rec = _Recorder()
    rec.run_returncode = 99  # arbitrary non-zero, non-4, non-5 exit code
    out_dir = tmp_path / "out" / "a"
    config = _write_shard_config(tmp_path, "a")
    _write_report(
        out_dir,
        {
            "src/W.a/Foo.cs": {"mutants": [_mutant("Survived")]},
            "src/W.a/Bar.cs": {"mutants": [_mutant("Survived")]},
        },
    )

    ok = pipeline.launch_survivor_fix(
        "a",
        repo_root=tmp_path,
        out_dir=out_dir,
        config_path=config,
        model=None,
        max_rounds=2,
        run=rec.run,
        resolve_test_file=lambda source, *a: Path(f"test/W.Tests/{Path(source).stem}Tests.cs"),
        log=rec.log,
    )

    assert ok is False
    # Only the first file's fix is launched — the second file is never
    # reached once the first exits non-zero.
    assert len(rec.launches) == 1
    assert any("FAILED (headless)" in line and "exit 99" in line for line in rec.logs)


# =============================================================================
# Scenario: A GenerationExhausted exit (code 5) — a clean retry-then-downgrade
# budget exhaustion, nothing mutated — is logged as unfixed but does NOT stop
# the shard: the loop continues to the next file (#1908 review), and the tree
# is not mutated. The pipeline's overall exit code becomes
# EXIT_GENERATION_EXHAUSTED (5) at the end if any file exhausted (unless a
# hard failure elsewhere makes it 1) — see main()'s 3-branch priority.
# Distinct from exit code 4 above, which does stop it.
# =============================================================================
def test_survivor_fix_continues_past_a_generation_exhausted_exit(tmp_path):
    rec = _Recorder()
    rec.run_returncode = 5  # GenerationExhausted's dedicated exit code
    out_dir = tmp_path / "out" / "a"
    config = _write_shard_config(tmp_path, "a")
    _write_report(
        out_dir,
        {
            "src/W.a/Foo.cs": {"mutants": [_mutant("Survived")]},
            "src/W.a/Bar.cs": {"mutants": [_mutant("Survived")]},
        },
    )

    ok = pipeline.launch_survivor_fix(
        "a",
        repo_root=tmp_path,
        out_dir=out_dir,
        config_path=config,
        model=None,
        max_rounds=2,
        run=rec.run,
        resolve_test_file=lambda source, *a: Path(f"test/W.Tests/{Path(source).stem}Tests.cs"),
        log=rec.log,
    )

    assert ok is True
    # Both files are launched — exit 5 does not stop the loop.
    assert len(rec.launches) == 2
    assert any("EXHAUSTED (headless)" in line and "exit 5" in line for line in rec.logs)


# =============================================================================
# Scenario: A single exhausted file in an otherwise-clean shard is recorded
# =============================================================================
def test_survivor_fix_records_exhausted_file_in_accumulator(tmp_path):
    rec = _Recorder()
    rec.run_returncode = 5  # GenerationExhausted's dedicated exit code
    out_dir = tmp_path / "out" / "a"
    config = _write_shard_config(tmp_path, "a")
    _write_report(out_dir, {"src/W.a/Foo.cs": {"mutants": [_mutant("Survived")]}})

    exhausted: list[str] = []
    ok = pipeline.launch_survivor_fix(
        "a",
        repo_root=tmp_path,
        out_dir=out_dir,
        config_path=config,
        model=None,
        max_rounds=2,
        run=rec.run,
        resolve_test_file=lambda source, *a: Path(f"test/W.Tests/{Path(source).stem}Tests.cs"),
        log=rec.log,
        exhausted=exhausted,
    )

    assert ok is True
    assert exhausted == ["a/src/W.a/Foo.cs"]


# =============================================================================
# Scenario: A mixed return-code sequence within one shard — the first
# survivor file exhausts (recorded, loop continues), the second file exits
# the fatal-revert code (loop stops). Exercises _Recorder.run_returncodes,
# the per-call sequence field, which nothing previously set.
# =============================================================================
def test_survivor_fix_exhausted_then_fatal_failure_stops_after_second_file(tmp_path):
    rec = _Recorder()
    rec.run_returncodes = [5, 4]  # file 1: GenerationExhausted, file 2: fatal-revert
    out_dir = tmp_path / "out" / "a"
    config = _write_shard_config(tmp_path, "a")
    # survivor_source_files (mutation_report.files_with_survivors) returns
    # files sorted by key — "Bar.cs" precedes "Foo.cs" — so Bar.cs is file 1
    # (exhausted, continues) and Foo.cs is file 2 (fatal-revert, stops).
    _write_report(
        out_dir,
        {
            "src/W.a/Foo.cs": {"mutants": [_mutant("Survived")]},
            "src/W.a/Bar.cs": {"mutants": [_mutant("Survived")]},
        },
    )

    exhausted: list[str] = []
    ok = pipeline.launch_survivor_fix(
        "a",
        repo_root=tmp_path,
        out_dir=out_dir,
        config_path=config,
        model=None,
        max_rounds=2,
        run=rec.run,
        resolve_test_file=lambda source, *a: Path(f"test/W.Tests/{Path(source).stem}Tests.cs"),
        log=rec.log,
        exhausted=exhausted,
    )

    assert ok is False
    # Only the first file's (Bar.cs) exhaustion is recorded before the second
    # file (Foo.cs) hits the fatal-revert exit and stops the loop.
    assert exhausted == ["a/src/W.a/Bar.cs"]
    # Exactly 2 launches: file 1 (exhausted, continues) then file 2 (fatal,
    # stops) — never a third attempt.
    assert len(rec.launches) == 2


def test_survivor_fix_exhausted_none_default_does_not_raise(tmp_path):
    rec = _Recorder()
    rec.run_returncode = 5  # GenerationExhausted's dedicated exit code
    out_dir = tmp_path / "out" / "a"
    config = _write_shard_config(tmp_path, "a")
    _write_report(out_dir, {"src/W.a/Foo.cs": {"mutants": [_mutant("Survived")]}})

    # exhausted is not passed — defaults to None — the append must be guarded.
    ok = pipeline.launch_survivor_fix(
        "a",
        repo_root=tmp_path,
        out_dir=out_dir,
        config_path=config,
        model=None,
        max_rounds=2,
        run=rec.run,
        resolve_test_file=lambda source, *a: Path(f"test/W.Tests/{Path(source).stem}Tests.cs"),
        log=rec.log,
    )

    assert ok is True


def test_survivor_fix_all_files_launched_when_every_exit_is_zero(tmp_path):
    rec = _Recorder()
    out_dir = tmp_path / "out" / "a"
    config = _write_shard_config(tmp_path, "a")
    _write_report(
        out_dir,
        {
            "src/W.a/Foo.cs": {"mutants": [_mutant("Survived")]},
            "src/W.a/Bar.cs": {"mutants": [_mutant("Survived")]},
        },
    )

    ok = pipeline.launch_survivor_fix(
        "a",
        repo_root=tmp_path,
        out_dir=out_dir,
        config_path=config,
        model=None,
        max_rounds=2,
        run=rec.run,
        resolve_test_file=lambda source, *a: Path(f"test/W.Tests/{Path(source).stem}Tests.cs"),
        log=rec.log,
    )

    assert ok is True
    assert len(rec.launches) == 2


def test_process_shard_marks_failed_when_a_survivor_fix_exits_nonzero(tmp_path):
    rec = _Recorder()
    rec.run_returncode = 4
    _write_shard_config(tmp_path, "a")
    _write_report(tmp_path / "out" / "a", {"src/W.a/Foo.cs": {"mutants": [_mutant("Survived")]}})

    result = pipeline.process_shard(
        "a",
        repo_root=tmp_path,
        worktree_base=tmp_path / ".wt",
        shard_out_base=tmp_path / "out",
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
    )

    assert result == "failed"


# =============================================================================
# Scenario: A shard with only exhausted files still reports "ok" from
# process_shard, and the exhausted accumulator is populated.
# =============================================================================
def test_process_shard_populates_exhausted_and_still_reports_ok(tmp_path):
    rec = _Recorder()
    rec.run_returncode = 5  # GenerationExhausted's dedicated exit code
    _write_shard_config(tmp_path, "a")
    _write_report(tmp_path / "out" / "a", {"src/W.a/Foo.cs": {"mutants": [_mutant("Survived")]}})

    exhausted: list[str] = []
    result = pipeline.process_shard(
        "a",
        repo_root=tmp_path,
        worktree_base=tmp_path / ".wt",
        shard_out_base=tmp_path / "out",
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
        exhausted=exhausted,
    )

    assert result == "ok"
    assert exhausted == ["a/src/W.a/Foo.cs"]


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

    result = pipeline.run_all(
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
    assert result.failed == ["a"]
    assert result.exhausted == []


# =============================================================================
# Scenario: run_all returns both the failed list and the exhausted list
# =============================================================================
def test_run_all_returns_shard_run_result_with_failed_and_exhausted(tmp_path):
    rec = _Recorder()
    out_base = tmp_path / "out"
    for shard in ("a", "b"):
        _write_shard_config(tmp_path, shard)

    # Shard "a" exhausts one file (headless loop exits 5); shard "b" fails
    # outright (Stryker itself reports non-zero).
    _write_report(out_base / "a", {"src/W.a/Foo.cs": {"mutants": [_mutant("Survived")]}})

    def fake_run_stryker(**kw):
        # "a" succeeds (its report was pre-seeded above); "b" fails.
        return 0 if kw["cwd"] == tmp_path / ".wt" / "shard-a" else 1

    rec.run_returncode = 5  # GenerationExhausted, for shard "a"'s one file

    result = pipeline.run_all(
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
        run_stryker=fake_run_stryker,
        run=rec.run,
        resolve_test_file=lambda *a: Path("test/W.Tests/FooTests.cs"),
        git_run=rec.git_run,
    )

    # Both a 2-tuple (positional unpack) and field access work.
    failed, exhausted = result
    assert failed == result.failed == ["b"]
    assert exhausted == result.exhausted == ["a/src/W.a/Foo.cs"]


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
# Scenario: print_summary prints an EXHAUSTED line when the list is non-empty
# =============================================================================
def test_summary_prints_exhausted_line_when_non_empty(tmp_path):
    logs = []
    pipeline.print_summary(
        ["ghost"],
        tmp_path / "out",
        log=logs.append,
        exhausted=["a/src/W.a/Foo.cs", "b/src/W.b/Bar.cs"],
    )
    exhausted_lines = [ln for ln in logs if "EXHAUSTED" in ln]
    assert len(exhausted_lines) == 1
    assert "EXHAUSTED files (2)" in exhausted_lines[0]
    assert "a/src/W.a/Foo.cs" in exhausted_lines[0]
    assert "b/src/W.b/Bar.cs" in exhausted_lines[0]


def test_summary_omits_exhausted_line_when_empty(tmp_path):
    logs_default = []
    pipeline.print_summary(["ghost"], tmp_path / "out", log=logs_default.append)

    logs_explicit_empty = []
    pipeline.print_summary(
        ["ghost"], tmp_path / "out", log=logs_explicit_empty.append, exhausted=[]
    )

    # Byte-identical output to today: no EXHAUSTED line, and the default
    # (unspecified) call matches the explicit-empty-list call.
    assert logs_default == logs_explicit_empty
    assert not any("EXHAUSTED" in ln for ln in logs_default)


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


# =============================================================================
# #1953 — the DEFAULT git_run path. Every other test in this file injects a
# fake git_run, which is exactly why a broken default survived: the production
# path (main() -> run_all(...) with no git_run) was never exercised. These
# tests deliberately use the real default.
# =============================================================================
def test_default_git_runner_satisfies_the_GitRunner_alias_positionally(tmp_path):
    """`GitRunner` is `Callable[[Sequence[str], Path, bool], object]` and every
    call site passes `check` positionally. `_git` declaring it keyword-only
    made the shipped default the one implementation that did not satisfy its
    own alias — TypeError on every real invocation."""
    import inspect

    param = inspect.signature(pipeline._git).parameters["check"]
    assert param.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD


def test_worktree_remove_runs_with_the_default_git_runner(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    # Must not raise TypeError. check=False, so a missing worktree is fine.
    pipeline.worktree_remove(tmp_path, tmp_path / "absent-worktree")


def test_worktree_add_runs_with_the_default_git_runner(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@e.st"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    (repo / "f.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "init"], check=True)

    worktree = tmp_path / "wt"
    pipeline.worktree_add(repo, worktree)
    assert worktree.is_dir()
    pipeline.worktree_remove(repo, worktree)
