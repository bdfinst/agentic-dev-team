"""Shared helpers for the model/effort A/B harness tests (scripts/model_effort_ab.py, scripts/lib/model_effort/).

Unit tests build their own agents, expected entries and fixtures in temp dirs. Each shipped asset (an agent
file, an expected entry, the recorded transcripts) has one named smoke test; the transcripts are the
harness's parser fixtures.
"""

from __future__ import annotations

import dataclasses
import json
import math
import signal
import sys
import threading
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from _repo_root import REPO_ROOT

for _path in (REPO_ROOT / "scripts", REPO_ROOT / "scripts" / "lib"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import model_effort_ab
from model_effort import (
    artifact,
    artifact_store,
    estimate,
    invocation,
    outcome,
    paths,
    process_record,
    run_types,
    runner,
    tools,
)
from model_effort import fixtures as fixture_resolution
from model_effort.arm import BASELINE_LABEL, CANDIDATE_LABEL, Arm
from model_effort.outcome import Outcome

TRANSCRIPT_FIXTURES = (
    Path(__file__).resolve().parent.parent / "fixtures" / "model_effort_ab"
)
HAIKU_MODEL_ID = "claude-haiku-5-5"
SONNET_MODEL_ID = "claude-sonnet-5-5"
NOW = datetime(2026, 10, 8, 12, 30, 45, tzinfo=timezone.utc)
RUN_ID = "20261008T123045Z-scout-haiku-high-0ab3"
SCOUT_TOOLS = "Read, Grep, mcp__x__y, Bash(graphify *)"
PASS_VERDICT = {"status": "pass", "issues": [], "summary": "Nothing to report."}
TRIAL_COST = 0.01
# The scout agent with its candidate arm on haiku, the tail most CLI runs share.
SCOUT_HAIKU_ARGS = ("scout", "--model", "haiku")
CLEAN_FORM_ARGS = (*SCOUT_HAIKU_ARGS, "--fixtures", "clean-form")
# Dollars per million tokens. Aliases mirror the agent files' `sonnet` and the
# candidate `haiku`; `opus` is deliberately absent so it is unpriced.
PRICEY_RATE = {"input": 4.0, "output": 20.0}
CHEAP_RATE = {"input": 1.0, "output": 5.0}
TEST_PRICING = {
    "models": {"test-pricey": PRICEY_RATE, "test-cheap": CHEAP_RATE},
    "aliases": {"sonnet": "test-pricey", "haiku": "test-cheap"},
}
# Pinned so CLI estimates do not move when the shipped calibration is retuned.
PINNED_CHARS_PER_TOKEN = 4
PINNED_TURN_MULTIPLIER = 2
PINNED_OUTPUT_TOKENS = 100
ARM_COUNT = 2
TERMINATION_SIGNALS = (signal.SIGTERM, signal.SIGHUP)
# The `scout` world resolves two fixtures: clean-form and layered-svc.
SCOUT_FIXTURE_COUNT = 2
SCOUT_TRIALS = 3


def _trial_input_chars(system_prompt_chars: int, fixture_chars: int, name: str) -> int:
    """Characters one trial sends: system prompt, fixture contents and the user prompt naming it."""
    return system_prompt_chars + fixture_chars + len(invocation.build_user_prompt(name))


def _arm_estimate_usd(input_chars: int, output_tokens: int, rate: dict) -> float:
    """What the estimator charges one arm for `SCOUT_TRIALS` rounds of the trial described."""
    input_tokens = input_chars / PINNED_CHARS_PER_TOKEN * PINNED_TURN_MULTIPLIER
    per_round_usd = (
        input_tokens * rate["input"] + output_tokens * rate["output"]
    ) / estimate.TOKENS_PER_RATE_UNIT
    return per_round_usd * SCOUT_TRIALS


# The `scout` world run over both fixtures with SCOUT_TRIALS trials per arm. A round
# is one trial on each fixture. The agent file's body keeps its trailing newline.
SCOUT_ROUND_INPUT_CHARS = _trial_input_chars(
    len("You are scout.\n"), len("<form></form>"), "clean-form.html"
) + _trial_input_chars(len("You are scout.\n"), len("app"), "layered-svc")
SCOUT_ROUND_OUTPUT_TOKENS = SCOUT_FIXTURE_COUNT * PINNED_OUTPUT_TOKENS
BASELINE_TWO_ARM_ESTIMATE = _arm_estimate_usd(
    SCOUT_ROUND_INPUT_CHARS, SCOUT_ROUND_OUTPUT_TOKENS, PRICEY_RATE
)
CANDIDATE_TWO_ARM_ESTIMATE = _arm_estimate_usd(
    SCOUT_ROUND_INPUT_CHARS, SCOUT_ROUND_OUTPUT_TOKENS, CHEAP_RATE
)
TWO_ARM_ESTIMATE = BASELINE_TWO_ARM_ESTIMATE + CANDIDATE_TWO_ARM_ESTIMATE
# A `--max-cost` under the estimate, so the startup refusal applies.
MAX_COST_BELOW_ESTIMATE = TWO_ARM_ESTIMATE / 2
# Calls and cost of one arm, and of both, when every planned trial runs.
ARM_RUN_CALLS = SCOUT_FIXTURE_COUNT * SCOUT_TRIALS
FULL_RUN_CALLS = ARM_COUNT * ARM_RUN_CALLS
FULL_RUN_COST = FULL_RUN_CALLS * TRIAL_COST
# A spend limit of two and a half trials' cost: the third trial takes the total past it.
LIMIT_IN_TRIALS = 2.5
MAX_COST_MID_RUN = LIMIT_IN_TRIALS * TRIAL_COST
TRIALS_BEFORE_STOP = math.ceil(LIMIT_IN_TRIALS)
ENABLED = ("Read", "Grep")
# The most characters of a trial's error text (and of its grader messages) that are kept.
CAUSE_LIMIT = 500
# Long enough that a slow interpreter start still reaches the stub before the kill.
TIMEOUT_SECONDS = 3


def _write_agent(
    agents_dir: Path,
    name: str,
    tools_line: str | None = None,
    *,
    model: str | None = None,
    effort: str | None = None,
    body: str = "Body.",
) -> None:
    lines = ["---", f"name: {name}"]
    for key, value in (("tools", tools_line), ("model", model), ("effort", effort)):
        if value is not None:
            lines.append(f"{key}: {value}")
    lines += ["---", "", body, ""]
    (agents_dir / f"{name}.md").write_text("\n".join(lines), encoding="utf-8")


def _write_expected(expected_dir: Path, stem: str, agent: str, status: str) -> None:
    entry = {
        "fixture": stem,
        "applicableAgents": [agent],
        "agents": {agent: {"expectedStatus": status}},
    }
    (expected_dir / f"{stem}.json").write_text(json.dumps(entry), encoding="utf-8")


def _make_file_fixture(
    root: Path, name: str = "form.html", content: str = "<form></form>"
) -> Path:
    fixture = root / name
    fixture.write_text(content, encoding="utf-8")
    return fixture


def _make_directory_fixture(root: Path) -> Path:
    fixture = root / "service"
    (fixture / "src" / "deep").mkdir(parents=True)
    (fixture / "README.md").write_text("readme", encoding="utf-8")
    (fixture / "src" / "app.py").write_text("print('app')", encoding="utf-8")
    (fixture / "src" / "deep" / "util.py").write_text("print('util')", encoding="utf-8")
    return fixture


def _snapshot(path: Path) -> dict[str, str]:
    files = (
        [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file())
    )
    return {str(p): p.read_text(encoding="utf-8") for p in files}


def _flag_value(argv: list[str], flag: str) -> str:
    return argv[argv.index(flag) + 1]


STUB_TEMPLATE = """#!/usr/bin/env python3
import json, os, signal, subprocess, sys, time
from pathlib import Path

RECORD = Path(__RECORD__)
QUEUE = Path(__QUEUE__)
BEHAVIOR = json.loads(__BEHAVIOR__)
if QUEUE.exists():
    queued = json.loads(QUEUE.read_text())
    if queued:
        BEHAVIOR = {**BEHAVIOR, **queued.pop(0)}
        QUEUE.write_text(json.dumps(queued))
cwd = Path(os.getcwd())
files_before = {
    str(p.relative_to(cwd)): p.read_text()
    for p in sorted(cwd.rglob("*"))
    if p.is_file()
}
symlinks = [str(p.relative_to(cwd)) for p in sorted(cwd.rglob("*")) if p.is_symlink()]
observed = None
if BEHAVIOR.get("observe"):
    target = Path(BEHAVIOR["observe"])
    observed = {
        "exists": target.exists(),
        "size": target.stat().st_size if target.exists() else None,
    }
calls = json.loads(RECORD.read_text()) if RECORD.exists() else []
calls.append({
    "pid": os.getpid(),
    "argv": sys.argv[1:],
    "cwd": str(cwd),
    "files_before": files_before,
    "symlinks": symlinks,
    "env_names": sorted(os.environ),
    "blocked_signals": sorted(
        s.name for s in signal.pthread_sigmask(signal.SIG_BLOCK, [])
    ),
    "observed": observed,
})
RECORD.write_text(json.dumps(calls))
if BEHAVIOR.get("tamper"):
    for p in cwd.rglob("*"):
        if p.is_file():
            p.write_text(p.read_text() + "TAMPERED")
if BEHAVIOR.get("touch"):
    Path(BEHAVIOR["touch"]).write_text("created during the run")
if BEHAVIOR.get("lock_subdir"):
    locked = cwd / "locked"
    locked.mkdir()
    (locked / "inner.txt").write_text("x")
    locked.chmod(0o500)
if BEHAVIOR.get("grandchild_marker"):
    code = "import pathlib, time; time.sleep(%s); pathlib.Path(%r).write_text('late')" % (
        BEHAVIOR["grandchild_delay"],
        BEHAVIOR["grandchild_marker"],
    )
    subprocess.Popen([sys.executable, "-c", code])
    Path(BEHAVIOR["grandchild_spawned"]).write_text("spawned")
if BEHAVIOR.get("holder_sleep"):
    # Inherits stdout and stderr, so it keeps both pipes open after this process exits.
    holder = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(%s)" % BEHAVIOR["holder_sleep"]],
        start_new_session=bool(BEHAVIOR.get("holder_new_session")),
    )
    if BEHAVIOR.get("holder_pid_file"):
        Path(BEHAVIOR["holder_pid_file"]).write_text(str(holder.pid))
if BEHAVIOR.get("stdout_hex"):
    sys.stdout.buffer.write(bytes.fromhex(BEHAVIOR["stdout_hex"]))
    sys.stdout.flush()
if BEHAVIOR.get("early_stdout") or BEHAVIOR.get("early_stderr"):
    # Written and flushed before any sleep, so a killed process has left it behind.
    sys.stdout.write(BEHAVIOR.get("early_stdout", ""))
    sys.stderr.write(BEHAVIOR.get("early_stderr", ""))
    sys.stdout.flush()
    sys.stderr.flush()
time.sleep(BEHAVIOR.get("sleep", 0))
sys.stdout.write(BEHAVIOR.get("stdout", ""))
sys.stderr.write(BEHAVIOR.get("stderr", ""))
if BEHAVIOR.get("stderr_cwd"):
    sys.stderr.write("cannot read " + str(cwd) + "/form.html")
sys.exit(BEHAVIOR.get("exit_code", 0))
"""


class StubClaude:
    """A stand-in `claude` executable that records every invocation."""

    def __init__(self, directory: Path, **behavior):
        self.path = directory / "claude-stub"
        self._record = directory / "calls.json"
        self._queue = directory / "queue.json"
        self.path.write_text(
            STUB_TEMPLATE.replace("__RECORD__", repr(str(self._record)))
            .replace("__QUEUE__", repr(str(self._queue)))
            .replace("__BEHAVIOR__", repr(json.dumps(behavior))),
            encoding="utf-8",
        )
        self.path.chmod(0o755)

    def queue(self, *per_call_behaviors: dict) -> None:
        """Make call N use the Nth behavior (merged over the defaults); later calls use the defaults."""
        self._queue.write_text(json.dumps(list(per_call_behaviors)), encoding="utf-8")

    @property
    def calls(self) -> list[dict]:
        if not self._record.exists():
            return []
        return json.loads(self._record.read_text(encoding="utf-8"))


def _eval_paths(**overrides: Path) -> paths.EvalPaths:
    """The shipped paths, with the named directories redirected."""
    return dataclasses.replace(paths.EvalPaths.default(), **overrides)


def _config(
    stub: StubClaude | None = None,
    *,
    model: str = "haiku",
    effort: str = "low",
    enabled_tools: tuple[str, ...] = ENABLED,
    system_prompt: str = "You are a reviewer.",
    claude_bin: str | None = None,
    eval_paths: paths.EvalPaths | None = None,
) -> invocation.TrialConfig:
    profile = tools.ToolProfile(
        enabled_tools=tuple(enabled_tools), withheld_tools=(), refused_tools=()
    )
    return invocation.TrialConfig(
        arm=Arm(label=CANDIDATE_LABEL, model=model, effort=effort),
        system_prompt=system_prompt,
        profile=profile,
        eval_paths=eval_paths or paths.EvalPaths.default(),
        claude_bin=claude_bin if claude_bin is not None else str(stub.path),
    )


def _raise_keyboard_interrupt(_signum, _frame) -> None:
    raise KeyboardInterrupt


INTERRUPT_SIGNALS = (signal.SIGINT, *TERMINATION_SIGNALS)


def _blocked_signals() -> set[signal.Signals]:
    return set(signal.pthread_sigmask(signal.SIG_BLOCK, []))


def _fixture_text(filename: str) -> str:
    return (TRANSCRIPT_FIXTURES / filename).read_text(encoding="utf-8")


def _stream(*events: dict | str) -> str:
    return "\n".join(e if isinstance(e, str) else json.dumps(e) for e in events)


def _result_event(text="ok", model_usage=None, **fields) -> dict:
    usage = {HAIKU_MODEL_ID: {}} if model_usage is None else model_usage
    return {
        "type": "result",
        "result": text,
        "is_error": False,
        "total_cost_usd": TRIAL_COST,
        "modelUsage": usage,
        **fields,
    }


def _tool_use_event(*names: str) -> dict:
    blocks = [{"type": "tool_use", "name": n, "input": {}} for n in names]
    return {"type": "assistant", "message": {"content": blocks}}


def _init_event(model_id: str = HAIKU_MODEL_ID, **fields) -> dict:
    return {
        "type": "system",
        "subtype": "init",
        "cwd": "/private/var/folders/XX/T/model-effort-ab-abc123",
        "session_id": "11111111-1111-1111-1111-111111111111",
        "model": model_id,
        "permissionMode": "default",
        "tools": ["Read", "Grep"],
        "mcp_servers": [],
        "plugins": [{"name": "builtin-a", "path": "/home/someone/.claude/plugins/a"}],
        **fields,
    }


def _expected_session_config(model_id: str) -> dict:
    return {
        "model": model_id,
        "permissionMode": "default",
        "tools": ["Read", "Grep"],
        "mcp_servers": [],
        "plugins": ["builtin-a"],
        "cwd": "<staged>",
    }


TRUNCATED_OUTER_OBJECT = '{"status":"fail","issues":[{"severity":"error","message":"x"}'


GRADED_AGENT = "x-review"
GRADED_STEM = "clean-form"


class FixedRng:
    """Stands in for `random.Random`: always returns the same bits."""

    def getrandbits(self, bits: int) -> int:
        assert bits == 16
        return 0x0AB3


def _trial_result(
    outcome_value: Outcome,
    cost=TRIAL_COST,
    model_id=None,
    note=None,
    session_config=None,
    cost_reported=True,
) -> outcome.TrialResult:
    return outcome.TrialResult(
        outcome=outcome_value,
        reported_cost_usd=cost,
        model_id=model_id,
        model_id_note=note,
        grader_messages=(),
        error=None,
        session_config=session_config,
        cost_reported=cost_reported,
    )


def _arm(label: str = CANDIDATE_LABEL) -> Arm:
    return Arm(label=label, model="haiku", effort="high")


READ_ONLY_PROFILE = tools.ToolProfile(
    enabled_tools=("Read",), withheld_tools=(), refused_tools=()
)


def _arm_run(
    label: str, results: list[outcome.TrialResult], expected_clean: bool = False
) -> run_types.ArmRun:
    fixture = run_types.FixtureTrials(
        stem="f",
        kind=fixture_resolution.FixtureKind.FILE,
        expected_clean=expected_clean,
        results=results,
    )
    return run_types.ArmRun(
        arm=_arm(label), trials_per_fixture=1, fixture_trials=[fixture]
    )


def _metadata() -> run_types.RunMetadata:
    return run_types.RunMetadata(
        run_id=RUN_ID,
        created=NOW,
        git_sha=None,
        agent="scout",
        knowledge_dir="knowledge",
    )


# One planned trial per arm, so an arm's per-trial estimate is its whole estimate.
ARM_ESTIMATE = 0.005


def _run_estimate(total_trials_per_arm: int = 1) -> estimate.RunEstimate:
    return estimate.RunEstimate(
        by_arm=(
            (BASELINE_LABEL, ARM_ESTIMATE * total_trials_per_arm),
            (CANDIDATE_LABEL, ARM_ESTIMATE * total_trials_per_arm),
        ),
        total_trials_per_arm=total_trials_per_arm,
    )


def _built_arm(
    results: list[outcome.TrialResult],
    expected_clean: bool = False,
    total_trials_per_arm: int = 1,
) -> dict:
    run = _arm_run(CANDIDATE_LABEL, results, expected_clean)
    built = artifact.build_artifact(
        _metadata(),
        [run],
        _run_estimate(total_trials_per_arm),
        READ_ONLY_PROFILE,
        None,
    )
    return built["arms"][0]


def _failing_replace(*_args, **_kwargs):
    raise OSError("disk full")


def _store_with_failing_replace(monkeypatch) -> None:
    """Make the final move fail while leaving every other os call working."""
    monkeypatch.setattr(artifact_store.os, "replace", _failing_replace)


def _verdict_call(
    verdict: dict, model_id: str, *tool_names: str, cost: float = TRIAL_COST
) -> dict:
    events = [_tool_use_event(*tool_names)] if tool_names else []
    result = _result_event(
        json.dumps(verdict), model_usage={model_id: {}}, total_cost_usd=cost
    )
    return {"stdout": _stream(_init_event(model_id), *events, result)}


WORLD_KNOWLEDGE_NOTE = "shared reference text"


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


def _cli(
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


def _cli_canned(
    world: World, deps: model_effort_ab.Deps, *args: str, yes: bool = True
) -> int:
    """Run the CLI over deps whose trials run no process; the stub binary is never called."""
    return _cli(world, StubClaude(world.stub_dir), *args, yes=yes, deps=deps)


def assert_nothing_ran(stub: StubClaude, world: World) -> None:
    assert stub.calls == [], "a trial ran"
    assert world.artifacts == [], "an artifact or placeholder was left behind"


def _written(world: World) -> dict:
    return json.loads(world.artifacts[0].read_text(encoding="utf-8"))


def _arm_block(written: dict, label: str) -> dict:
    return {arm["label"]: arm for arm in written["arms"]}[label]


def _passing_stub(world: World, **behavior) -> StubClaude:
    return StubClaude(
        world.stub_dir, **_verdict_call(PASS_VERDICT, SONNET_MODEL_ID), **behavior
    )


def _deps_with_canned_trials(
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
        stdout=_verdict_call(PASS_VERDICT, SONNET_MODEL_ID, cost=cost)["stdout"],
        stderr="",
        timed_out=False,
    )
    overrides = overrides or {}

    def canned_trial(*args, **kwargs):
        call_number = len(calls)
        calls.append(args)
        return overrides.get(call_number, default or passing)

    return dataclasses.replace(deps, run_trial=canned_trial), calls


def _stderr_lines(capsys) -> list[str]:
    return capsys.readouterr().err.splitlines()


class RaisingStdin:
    """A stdin whose read fails the way a terminal does on Ctrl-C."""

    def __init__(self, error: BaseException):
        self._error = error

    def readline(self) -> str:
        raise self._error


def _gated_deps(world: World, stdin, *, is_tty: bool = True) -> model_effort_ab.Deps:
    return dataclasses.replace(world.deps, stdin=stdin, stdin_is_tty=lambda: is_tty)


def _gated_cli(world: World, stub: StubClaude, stdin, *, is_tty: bool = True) -> int:
    return _cli(
        world,
        stub,
        *SCOUT_HAIKU_ARGS,
        "--trials",
        "1",
        yes=False,
        deps=_gated_deps(world, stdin, is_tty=is_tty),
    )


CLI_FAILURE = {"exit_code": 1, "stdout": "", "stderr": "boom: auth failed"}
CLI_FAILURE_RECORD = process_record.TrialProcessRecord(
    exit_code=1, stdout="", stderr="boom: auth failed", timed_out=False
)
TIMED_OUT_RECORD = process_record.TrialProcessRecord(
    exit_code=None, stdout="", stderr="", timed_out=True
)


def _deps_acting_after(
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


def _deps_raising_after(
    world: World, completed_trials: int, error: BaseException
) -> model_effort_ab.Deps:
    def raise_error() -> None:
        raise error

    return _deps_acting_after(world, completed_trials, raise_error)


def _deps_signalling_after(
    world: World, completed_trials: int, signum: int
) -> model_effort_ab.Deps:
    """Send `signum` to this process inside the trial after `completed_trials` real ones."""
    return _deps_acting_after(
        world, completed_trials, lambda: signal_own_thread(signum)
    )


def assert_cut_at_limit(text: str, prefix: str, filler: str) -> None:
    """Assert `text` shows `prefix` plus `filler` up to CAUSE_LIMIT characters, and no more."""
    __tracebackhide__ = True
    kept = filler * (CAUSE_LIMIT - len(prefix))
    assert prefix + kept in text, "the text was cut short of the limit"
    assert prefix + kept + filler not in text, "the text was kept beyond the limit"


def _deps_timing_out(
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


def _interrupting_deps(world: World, completed_trials: int) -> model_effort_ab.Deps:
    """Press Ctrl-C inside the trial after `completed_trials` real ones."""
    return _deps_raising_after(world, completed_trials, KeyboardInterrupt())


def _outcomes(written: dict, label: str) -> list[str]:
    return [
        trial["outcome"]
        for fixture in _arm_block(written, label)["fixtures"]
        for trial in fixture["trials"]
    ]


def _note_signal(_signum, _frame) -> None:
    """A harmless handler: the signal is delivered and nothing else happens."""


def signal_own_thread(signum: int) -> None:
    """Deliver `signum` to the test's own thread, where `interrupts` holds it back.

    `os.kill(os.getpid(), ...)` is process-directed, so the kernel may hand the
    signal to any thread that does not block it. A pytest-xdist worker runs a second
    OS thread (execnet's receiver, invisible to `threading`) that blocks nothing, so
    the signal can bypass the mask the test set on its own thread and is never seen
    pending there. A thread-directed signal stays pending on the thread that blocks it.
    """
    signal.pthread_kill(threading.main_thread().ident, signum)
