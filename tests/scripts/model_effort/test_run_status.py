"""The artifact's reservation and final write, and what a failed write leaves behind."""

from __future__ import annotations

import json

import pytest
from _model_effort_support import (
    CLEAN_FORM_ARGS,
    RUN_ID,
    RaisingStdin,
    _cli,
    _gated_cli,
    _passing_stub,
    _store_with_failing_replace,
)


class TestArtifactReservationAndWrite:
    def test_run_that_fails_before_any_trial_starts_leaves_no_placeholder(self, world):
        stdin = RaisingStdin(RuntimeError("stdin closed"))

        with pytest.raises(RuntimeError):
            _gated_cli(world, _passing_stub(world), stdin)

        assert world.artifacts == []

    def test_failed_final_write_prints_the_artifact_to_stdout_exits_1_and_leaves_no_files(
        self, world, capsys, monkeypatch
    ):
        stub = _passing_stub(world)
        _store_with_failing_replace(monkeypatch)

        code = _cli(
            world,
            stub,
            *CLEAN_FORM_ARGS,
            "--trials",
            "1",
        )

        captured = capsys.readouterr()
        printed = json.loads(captured.out)
        assert code == 1
        assert printed["run_id"] == RUN_ID and printed["status"] == "complete"
        assert "stdout" in captured.err
        assert world.artifacts == []

    def test_failed_final_write_keeps_a_placeholder_that_gained_content(
        self, world, monkeypatch
    ):
        stub = _passing_stub(world, touch=str(world.artifact_path))
        _store_with_failing_replace(monkeypatch)

        code = _cli(
            world,
            stub,
            *CLEAN_FORM_ARGS,
            "--trials",
            "1",
        )

        assert code == 1
        assert world.artifact_path.read_text(encoding="utf-8") == (
            "created during the run"
        )
        assert world.artifacts == [world.artifact_path]
