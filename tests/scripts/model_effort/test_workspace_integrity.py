"""After the agent exits, the harness acts only on the working copy it staged.

An agent that swaps its working copy (or the staging dir above it) for a symlink
or another directory fails its own trial, and nothing is diffed, restored or
tested through the swap. An agent that locks the copy with chmod cannot make the
restore abort the run: the restore unlocks it, and a restore that still fails is
recorded on the trial with its cost kept.

Every `claude` process here is a small fake CLI; no test reaches a model.
"""

from __future__ import annotations

import dataclasses
import json
import sys
import tempfile
from pathlib import Path

import _model_effort_support  # noqa: F401  (puts the harness on sys.path first)
import pytest
from _model_effort_support import _config
from model_effort import outcome, runner, transcript
from model_effort.outcome import Outcome

FAKE_COST_USD = 0.25
CHECKER = (
    "import pathlib, sys\n"
    "sys.exit(0 if pathlib.Path('tests/t.py').read_text() == 'original' else 4)\n"
)


def _fake_cli(directory: Path, action: str) -> Path:
    """A fake `claude` that runs `action` in its cwd (the staging dir), then reports a cost."""
    path = directory / "fake-claude"
    path.write_text(
        f"#!{sys.executable}\n"
        "import json, os, pathlib, shutil\n"
        "cwd = pathlib.Path(os.getcwd())\n"
        f"{action}\n"
        "print(json.dumps({'type': 'result', 'result': 'done', 'is_error': False,"
        f" 'total_cost_usd': {FAKE_COST_USD}, 'modelUsage': {{}}}}))\n",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


@pytest.fixture(autouse=True)
def staging_under_tmp_path(tmp_path: Path, monkeypatch) -> None:
    """Stage trials under `tmp_path`, so a staging dir an agent moved is cleaned up too."""
    staging_root = tmp_path / "staging"
    staging_root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(staging_root))


@pytest.fixture
def fixture(tmp_path: Path) -> Path:
    root = tmp_path / "fx"
    (root / "tests").mkdir(parents=True)
    (root / "tests" / "t.py").write_text("original")
    (root / "check.py").write_text(CHECKER)
    return root


@pytest.fixture
def outside(tmp_path: Path) -> Path:
    """A directory the agent points its working copy at; holds a look-alike fixture."""
    root = tmp_path / "outside"
    (root / "fx" / "tests").mkdir(parents=True)
    (root / "tests").mkdir()
    for base in (root, root / "fx"):
        (base / "tests" / "t.py").write_text("outside file")
        (base / "check.py").write_text("raise SystemExit(0)\n")
    return root


def _snapshot(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): path.read_text()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _test_graded(fake: Path, *, sandbox: bool = False):
    return dataclasses.replace(
        _config(claude_bin=str(fake)),
        sandbox=sandbox,
        test_commands=("{python} check.py",),
        protected_paths=("tests/t.py",),
    )


def _cost(record) -> float:
    return outcome.resolve_outcome(
        record,
        transcript.parse_stream(record.stdout),
        (),
        lambda _json: (True, []),
        requires_agent_json=False,
    ).reported_cost_usd


class TestSwappedWorkingCopy:
    @pytest.mark.parametrize(
        "action",
        [
            (
                "(cwd / 'fx').rename(cwd / 'fx-moved')\n"
                "(cwd / 'fx').symlink_to(OUTSIDE / 'fx', target_is_directory=True)"
            ),
            (
                "(cwd / 'fx').rename(cwd / 'fx-moved')\n"
                "shutil.copytree(cwd / 'fx-moved', cwd / 'fx')"
            ),
            (
                "moved = cwd.with_name(cwd.name + '-moved')\n"
                "cwd.rename(moved)\n"
                "cwd.symlink_to(OUTSIDE, target_is_directory=True)"
            ),
            # The copy itself moves along, so only the staging dir's identity changed.
            (
                "elsewhere = OUTSIDE.parent / 'elsewhere'\n"
                "elsewhere.mkdir()\n"
                "(cwd / 'fx').rename(elsewhere / 'fx')\n"
                "cwd.rename(cwd.with_name(cwd.name + '-moved'))\n"
                "cwd.symlink_to(elsewhere, target_is_directory=True)"
            ),
        ],
        ids=[
            "work-dir-symlink",
            "work-dir-replaced",
            "staging-dir-symlink",
            "staging-dir-symlink-to-the-moved-copy",
        ],
    )
    def test_the_trial_fails_and_nothing_is_diffed_restored_or_tested_through_it(
        self, tmp_path, fixture, outside, action
    ):
        before = _snapshot(outside)
        fake = _fake_cli(
            tmp_path, f"OUTSIDE = pathlib.Path({str(outside)!r})\n{action}"
        )

        record = runner.run_trial(fixture, _test_graded(fake, sandbox=True))

        assert record.workspace_error is not None
        assert "working copy" in record.workspace_error
        assert record.work_diff is None
        assert record.check_results == ()
        assert _snapshot(outside) == before

    def test_an_untouched_working_copy_has_no_workspace_error(self, tmp_path, fixture):
        fake = _fake_cli(tmp_path, "pass")

        record = runner.run_trial(fixture, _test_graded(fake))

        assert record.workspace_error is None
        assert [result["exit_code"] for result in record.check_results] == [0]

    def test_a_workspace_error_is_a_tool_violation_with_its_cost_kept(self, tmp_path):
        stdout = json.dumps(
            {
                "type": "result",
                "result": "done",
                "is_error": False,
                "total_cost_usd": FAKE_COST_USD,
                "modelUsage": {},
            }
        )
        record = runner.TrialProcessRecord(
            exit_code=0,
            stdout=stdout,
            stderr="",
            timed_out=False,
            workspace_error="the working copy was replaced",
        )

        result = outcome.resolve_outcome(
            record,
            transcript.parse_stream(stdout),
            (),
            lambda _json: (True, []),
            requires_agent_json=False,
        )

        assert result.outcome is Outcome.TOOL_VIOLATION
        assert "working copy was replaced" in result.error
        assert result.reported_cost_usd == FAKE_COST_USD


class TestLockedWorkingCopy:
    def test_a_copy_locked_with_chmod_is_unlocked_and_restored(self, tmp_path, fixture):
        fake = _fake_cli(
            tmp_path,
            "(cwd / 'fx' / 'tests' / 't.py').write_text('weakened')\n"
            "(cwd / 'fx' / 'tests').chmod(0)\n"
            "(cwd / 'fx').chmod(0)",
        )

        record = runner.run_trial(fixture, _test_graded(fake))

        assert record.workspace_error is None
        assert [result["exit_code"] for result in record.check_results] == [0]

    def test_a_restore_that_still_fails_is_recorded_on_the_trial_with_its_cost(
        self, tmp_path, fixture, monkeypatch
    ):
        def refuse(*_args):
            raise PermissionError(13, "Permission denied")

        monkeypatch.setattr(runner, "_copy_in", refuse)
        fake = _fake_cli(tmp_path, "pass")

        record = runner.run_trial(fixture, _test_graded(fake))

        assert record.workspace_error is not None
        assert "restore" in record.workspace_error
        assert record.check_results == ()
        assert _cost(record) == FAKE_COST_USD
