"""A throwaway repo slice (`World`) and drivers that run the A/B harness CLI over it."""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from pathlib import Path

import ab_harness_path  # noqa: F401  (puts the harness on sys.path first)
import model_effort_ab
from ab_constants import (
    CAUSE_LIMIT,
    PASS_VERDICT,
    RUN_ID,
    SCOUT_HAIKU_ARGS,
    SONNET_MODEL_ID,
    TRIAL_COST,
)
from ab_results import TIMED_OUT_RECORD
from ab_signals import signal_own_thread
from ab_stub_claude import StubClaude, verdict_call
from model_effort import (
    process_record,
    runner,
)


@dataclass
class World:
    """A throwaway repo slice: agents, expected entries, fixtures and a runs dir."""

    root: Path
    deps: model_effort_ab.Deps

    @property
    def runs_dir(self) -> Path:
        return self.root / "runs"

    @property
    def expected_dir(self) -> Path:
        return self.root / "expected"

    @property
    def stub_dir(self) -> Path:
        return self.root / "stub"

    @property
    def artifacts(self) -> list[Path]:
        return sorted(self.runs_dir.iterdir())

    @property
    def artifact_path(self) -> Path:
        return self.runs_dir / f"{RUN_ID}.json"


def cli(
    world: World,
    stub: StubClaude,
    *args: str,
    yes: bool = True,
    deps: model_effort_ab.Deps | None = None,
) -> int:
    """Run the CLI; `yes` passes the approval gate unless a test exercises the gate itself."""
    argv = [
        *args,
        *(["--yes"] if yes else []),
        "--claude-bin",
        str(stub.path),
        "--runs-dir",
        str(world.runs_dir),
    ]
    return model_effort_ab.main(argv, deps=deps or world.deps)


def cli_canned(
    world: World, deps: model_effort_ab.Deps, *args: str, yes: bool = True
) -> int:
    """Run the CLI over deps whose trials run no process; the stub binary is never called."""
    return cli(world, StubClaude(world.stub_dir), *args, yes=yes, deps=deps)


def assert_nothing_ran(stub: StubClaude, world: World) -> None:
    assert stub.calls == [], "a trial ran"
    assert world.artifacts == [], "an artifact or placeholder was left behind"


def read_artifact(world: World) -> dict:
    return json.loads(world.artifacts[0].read_text(encoding="utf-8"))


def arm_block(written: dict, label: str) -> dict:
    return {arm["label"]: arm for arm in written["arms"]}[label]


def passing_stub(world: World, **behavior) -> StubClaude:
    return StubClaude(
        world.stub_dir, **verdict_call(PASS_VERDICT, SONNET_MODEL_ID), **behavior
    )


def deps_with_canned_trials(
    deps: model_effort_ab.Deps,
    *,
    cost: float = TRIAL_COST,
    default: process_record.TrialProcessRecord | None = None,
    overrides: Mapping[int, process_record.TrialProcessRecord] | None = None,
) -> tuple[model_effort_ab.Deps, list[tuple]]:
    """Deps whose trials run no process: each returns a canned record and is logged.

    The record is a passing verdict costing `cost`, unless `default` replaces it for
    every trial or `overrides` replaces it for the trials at those 0-based call
    numbers. For tests of what the run does with trials (how many, with what
    arguments, what it prints and records), not of the process itself; the call log
    holds each trial's positional arguments (fixture path, config, timeout).
    """
    calls: list[tuple] = []
    passing = process_record.TrialProcessRecord(
        exit_code=0,
        stdout=verdict_call(PASS_VERDICT, SONNET_MODEL_ID, cost=cost)["stdout"],
        stderr="",
        timed_out=False,
    )
    overrides = overrides or {}

    def canned_trial(*args, **kwargs):
        call_number = len(calls)
        calls.append(args)
        return overrides.get(call_number, default or passing)

    return dataclasses.replace(deps, run_trial=canned_trial), calls


def stderr_lines(capsys) -> list[str]:
    return capsys.readouterr().err.splitlines()


class RaisingStdin:
    """A stdin whose read fails the way a terminal does on Ctrl-C."""

    def __init__(self, error: BaseException):
        self._error = error

    def readline(self) -> str:
        raise self._error


def gated_deps(world: World, stdin, *, is_tty: bool = True) -> model_effort_ab.Deps:
    return dataclasses.replace(world.deps, stdin=stdin, stdin_is_tty=lambda: is_tty)


def gated_cli(world: World, stub: StubClaude, stdin, *, is_tty: bool = True) -> int:
    return cli(
        world,
        stub,
        *SCOUT_HAIKU_ARGS,
        "--trials",
        "1",
        yes=False,
        deps=gated_deps(world, stdin, is_tty=is_tty),
    )


def deps_acting_after(
    world: World, completed_trials: int, action: Callable[[], None]
) -> model_effort_ab.Deps:
    """Let the first `completed_trials` trials run for real, then run `action` in place of the next."""
    started = []

    def run_then_act(*args, **kwargs):
        if len(started) == completed_trials:
            action()
        started.append(args)
        return runner.run_trial(*args, **kwargs)

    return dataclasses.replace(world.deps, run_trial=run_then_act)


def deps_raising_after(
    world: World, completed_trials: int, error: BaseException
) -> model_effort_ab.Deps:
    def raise_error() -> None:
        raise error

    return deps_acting_after(world, completed_trials, raise_error)


def deps_signalling_after(
    world: World, completed_trials: int, signum: int
) -> model_effort_ab.Deps:
    """Send `signum` to this process inside the trial after `completed_trials` real ones."""
    return deps_acting_after(world, completed_trials, lambda: signal_own_thread(signum))


def assert_cut_at_limit(text: str, prefix: str, filler: str) -> None:
    """Assert `text` shows `prefix` plus `filler` up to CAUSE_LIMIT characters, and no more."""
    __tracebackhide__ = True
    kept = filler * (CAUSE_LIMIT - len(prefix))
    assert prefix + kept in text, "the text was cut short of the limit"
    assert prefix + kept + filler not in text, "the text was kept beyond the limit"


def deps_timing_out(
    world: World, timed_out_calls: Collection[int] | None = None, stderr: str = ""
) -> model_effort_ab.Deps:
    """Make the trials at `timed_out_calls` (0-based; default all) end as timeouts.

    The killed process left `stderr` behind.

    No process runs for those; the other trials run the stub. A real timeout is
    covered at the runner layer.
    """
    started = []

    def run_or_time_out(*args, **kwargs):
        call_number = len(started)
        started.append(args)
        if timed_out_calls is None or call_number in timed_out_calls:
            return dataclasses.replace(TIMED_OUT_RECORD, stderr=stderr)
        return runner.run_trial(*args, **kwargs)

    return dataclasses.replace(world.deps, run_trial=run_or_time_out)


def interrupting_deps(world: World, completed_trials: int) -> model_effort_ab.Deps:
    """Press Ctrl-C inside the trial after `completed_trials` real ones."""
    return deps_raising_after(world, completed_trials, KeyboardInterrupt())


def outcomes_of(written: dict, label: str) -> list[str]:
    return [
        trial["outcome"]
        for fixture in arm_block(written, label)["fixtures"]
        for trial in fixture["trials"]
    ]
