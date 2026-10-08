#!/usr/bin/env python3
"""Compare an agent's frontmatter model/effort (baseline) with a candidate.

Runs each trial through `claude -p` with the agent's read-only built-in tools
against a fresh copy of a fixture, grades it against `evals/expected`, and
writes one JSON artifact per run to the runs directory. Trials alternate
baseline, candidate, baseline, ... so a broken candidate fails on its first trial.

Exit codes: 0 complete, 1 the artifact could not be written (its JSON is
printed to stdout), 2 usage error or pre-run refusal. Messages go to stderr.
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for _path in (
    REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib",
    REPO_ROOT / "scripts" / "lib",
    REPO_ROOT / "scripts",
):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from model_effort import (
    agent_spec,
    artifact,
    grading,
    outcome,
    runner,
    tools,
    transcript,
)

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

DEFAULT_TRIALS = 5
DEFAULT_RUNS_DIR = REPO_ROOT / "evals" / "model-effort" / "runs"
FIXTURES_DIR = REPO_ROOT / "evals" / "fixtures"
BASELINE_LABEL = "baseline"
CANDIDATE_LABEL = "candidate"
FIXTURE_KIND_DIRECTORY = "directory"
FIXTURE_KIND_FILE = "file"

PROFILE_FIX_HINTS = {
    tools.WriteCapableAgentError: " Choose an agent whose tools are limited to Read, Grep and Glob.",
    tools.AgentFrontmatterError: " Fix the agent file's frontmatter; the baseline arm needs `model:` and `effort:`.",
}


class UsageError(Exception):
    """A pre-run refusal; the message says what is wrong and how to fix it."""


@dataclass(frozen=True)
class Deps:
    """Everything nondeterministic or environment-specific, so tests can inject it."""

    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    rng: random.Random = field(default_factory=random.Random)
    git_sha: Callable[[], str | None] = lambda: _git_head_sha()
    agents_dir: Path = tools.AGENTS_DIR
    expected_dir: Path = grading.EXPECTED_DIR
    fixtures_dir: Path = FIXTURES_DIR


@dataclass(frozen=True)
class Arm:
    spec: artifact.ArmSpec
    config: runner.TrialConfig


@dataclass(frozen=True)
class ResolvedFixture:
    stem: str
    path: Path
    kind: str
    expected_clean: bool


@dataclass(frozen=True)
class RunPlan:
    agent: str
    arms: Sequence[Arm]
    fixtures: Sequence[ResolvedFixture]
    metadata: artifact.RunMetadata
    artifact_path: Path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="model_effort_ab.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "agent", help="agent name, as in plugins/dev-team/agents/<agent>.md"
    )
    parser.add_argument(
        "--model",
        help="candidate model alias (default: the agent's frontmatter `model:`)",
    )
    parser.add_argument(
        "--effort",
        help="candidate effort level (default: the agent's frontmatter `effort:`)",
    )
    parser.add_argument(
        "--fixtures",
        help="comma-separated fixture stems (default: every evals/expected/*.json "
        "entry that names the agent)",
    )
    parser.add_argument(
        "--trials",
        type=_positive_int,
        default=DEFAULT_TRIALS,
        help=f"trials per arm per fixture (default: {DEFAULT_TRIALS})",
    )
    parser.add_argument(
        "--trial-timeout",
        type=_positive_int,
        default=runner.DEFAULT_TRIAL_TIMEOUT_SECONDS,
        help="seconds before a trial is killed and recorded as timeout "
        f"(default: {runner.DEFAULT_TRIAL_TIMEOUT_SECONDS})",
    )
    parser.add_argument(
        "--claude-bin",
        default=runner.DEFAULT_CLAUDE_BIN,
        help=f"claude executable to run (default: {runner.DEFAULT_CLAUDE_BIN})",
    )
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=DEFAULT_RUNS_DIR,
        help="directory the artifact is written to "
        f"(default: {DEFAULT_RUNS_DIR.relative_to(REPO_ROOT)})",
    )
    return parser


def _positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        value = 0
    if value < 1:
        raise argparse.ArgumentTypeError(f"{text!r} is not a positive integer")
    return value


def _git_head_sha() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip() or None


def _relative_to_repo(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def _load_agent(agent: str, agents_dir: Path):
    try:
        return tools.load_tool_profile(agent, agents_dir), agent_spec.load_agent_spec(
            agent, agents_dir
        )
    except (
        tools.UnknownAgentError,
        tools.WriteCapableAgentError,
        tools.AgentFrontmatterError,
    ) as error:
        raise UsageError(f"{error}{PROFILE_FIX_HINTS.get(type(error), '')}") from error


def _expected_entries(agent: str, expected_dir: Path) -> dict[str, dict]:
    """Map fixture stem to its expected entry, for entries that name `agent`."""
    entries = {}
    for path in sorted(expected_dir.glob("*.json")):
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise UsageError(
                f"malformed expected entry {path}: {error}. Fix the JSON."
            ) from error
        if agent in entry.get("agents", {}):
            entries[path.stem] = entry
    return entries


def _fixture_index(fixtures_dir: Path) -> dict[str, Path]:
    """Map stem to fixture path; a directory's stem is its name, a file's drops one extension."""
    return {
        (path.name if path.is_dir() else path.stem): path
        for path in sorted(fixtures_dir.iterdir())
    }


def _split_csv(text: str | None) -> list[str] | None:
    if text is None:
        return None
    return list(dict.fromkeys(part.strip() for part in text.split(",") if part.strip()))


def _resolve_fixtures(
    agent: str, requested: list[str] | None, deps: Deps
) -> list[ResolvedFixture]:
    entries = _expected_entries(agent, deps.expected_dir)
    available = _fixture_index(deps.fixtures_dir)
    valid = sorted(stem for stem in entries if stem in available)
    stems = valid if requested is None else requested
    unknown = [stem for stem in stems if stem not in valid]
    if unknown:
        raise UsageError(
            f"unknown fixture {', '.join(unknown)} for agent {agent!r}: it needs both an "
            f"evals/expected entry naming the agent and a fixture. "
            f"Valid fixtures: {', '.join(valid) or '(none)'}"
        )
    if not stems:
        raise UsageError(
            f"no fixtures were found for agent {agent!r}: no evals/expected entry names it. "
            "Pass --fixtures with stems from evals/expected, or choose an agent that has entries"
        )
    return [
        ResolvedFixture(
            stem=stem,
            path=available[stem],
            kind=FIXTURE_KIND_DIRECTORY
            if available[stem].is_dir()
            else FIXTURE_KIND_FILE,
            expected_clean=grading.is_expected_clean(entries[stem], agent),
        )
        for stem in stems
    ]


def _build_arms(
    args: argparse.Namespace, spec: agent_spec.AgentSpec, profile: tools.ToolProfile
) -> list[Arm]:
    candidate_model = args.model or spec.model
    candidate_effort = args.effort or spec.effort
    return [
        _build_arm(label, model, effort, spec, profile, args.claude_bin)
        for label, model, effort in (
            (BASELINE_LABEL, spec.model, spec.effort),
            (CANDIDATE_LABEL, candidate_model, candidate_effort),
        )
    ]


def _build_arm(
    label: str,
    model: str,
    effort: str,
    spec: agent_spec.AgentSpec,
    profile: tools.ToolProfile,
    claude_bin: str,
) -> Arm:
    return Arm(
        spec=artifact.ArmSpec(
            label=label,
            model=model,
            effort=effort,
            tools_enabled=profile.enabled,
            tools_withheld=profile.withheld,
        ),
        config=runner.TrialConfig(
            model=model,
            effort=effort,
            system_prompt=spec.system_prompt,
            enabled_tools=profile.enabled,
            claude_bin=claude_bin,
        ),
    )


def _plan_run(args: argparse.Namespace, deps: Deps) -> RunPlan:
    """Validate everything that can be checked before spending, or raise UsageError."""
    profile, spec = _load_agent(args.agent, deps.agents_dir)
    fixtures = _resolve_fixtures(args.agent, _split_csv(args.fixtures), deps)
    arms = _build_arms(args, spec, profile)
    now = deps.clock()
    candidate = arms[1].spec
    run_id = artifact.make_run_id(
        now, args.agent, candidate.model, candidate.effort, deps.rng
    )
    artifact_path = _free_artifact_path(args.runs_dir, run_id)
    metadata = artifact.RunMetadata(
        run_id=run_id,
        created=now,
        git_sha=deps.git_sha(),
        agent=args.agent,
        knowledge_dir=_relative_to_repo(runner.KNOWLEDGE_DIR),
    )
    return RunPlan(args.agent, arms, fixtures, metadata, artifact_path)


def _free_artifact_path(runs_dir: Path, run_id: str) -> Path:
    if not runs_dir.is_dir():
        raise UsageError(
            f"runs directory {runs_dir} does not exist: create it or pass --runs-dir"
        )
    path = runs_dir / f"{run_id}.json"
    if path.exists():
        raise UsageError(
            f"artifact {path} already exists and is never overwritten: "
            "rerun to get a new run ID, or move the file away"
        )
    return path


def _run_trial(
    fixture: ResolvedFixture, config: runner.TrialConfig, timeout: int, grader
) -> outcome.TrialResult:
    record = runner.run_trial(fixture.path, config, timeout)
    parsed = transcript.parse_stream(record.stdout)
    return outcome.resolve_outcome(record, parsed, config.enabled_tools, grader)


def _run_fixture(
    fixture: ResolvedFixture,
    arms: Sequence[Arm],
    trials: int,
    timeout: int,
    grader,
) -> list[list[outcome.TrialResult]]:
    """Run `trials` rounds, each round one trial per arm in arm order; results are per arm."""
    per_arm: list[list[outcome.TrialResult]] = [[] for _ in arms]
    for _ in range(trials):
        for results, arm in zip(per_arm, arms):
            results.append(_run_trial(fixture, arm.config, timeout, grader))
    return per_arm


def _run_trials(
    plan: RunPlan, args: argparse.Namespace, deps: Deps
) -> list[artifact.ArmRun]:
    per_fixture = []
    for fixture in plan.fixtures:
        grader = partial(
            grading.grade_trial,
            plan.agent,
            fixture.stem,
            expected_dir=deps.expected_dir,
        )
        per_fixture.append(
            _run_fixture(fixture, plan.arms, args.trials, args.trial_timeout, grader)
        )
    return [
        artifact.ArmRun(
            spec=arm.spec,
            trials_per_fixture=args.trials,
            fixtures=[
                artifact.FixtureTrials(
                    stem=fixture.stem,
                    kind=fixture.kind,
                    expected_clean=fixture.expected_clean,
                    results=per_fixture[fixture_index][arm_index],
                )
                for fixture_index, fixture in enumerate(plan.fixtures)
            ],
        )
        for arm_index, arm in enumerate(plan.arms)
    ]


def _write_artifact(path: Path, data: dict) -> int:
    """Create `path` exclusively; on any write error print the JSON so paid results survive."""
    text = json.dumps(data, indent=2) + "\n"
    try:
        with open(path, "x", encoding="utf-8") as handle:
            handle.write(text)
    except OSError as error:
        sys.stdout.write(text)
        print(
            f"error: cannot write artifact {path}: {error}. The trials ran; the artifact "
            f"JSON is on stdout. Save it to a new file in {path.parent}.",
            file=sys.stderr,
        )
        return EXIT_FAILED
    print(f"artifact written: {path}", file=sys.stderr)
    return EXIT_OK


def main(argv: Sequence[str] | None = None, *, deps: Deps | None = None) -> int:
    deps = deps or Deps()
    args = _build_parser().parse_args(argv)
    try:
        plan = _plan_run(args, deps)
    except UsageError as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_USAGE
    arm_runs = _run_trials(plan, args, deps)
    data = artifact.build_artifact(plan.metadata, arm_runs)
    return _write_artifact(plan.artifact_path, data)


if __name__ == "__main__":
    sys.exit(main())
