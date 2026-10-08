#!/usr/bin/env python3
"""Compare an agent's frontmatter model/effort (baseline) with a candidate.

Runs each trial through `claude -p` with the agent's read-only built-in tools
against a fresh copy of a fixture, grades it against `evals/expected`, and
writes one JSON artifact per run to the runs directory. Trials alternate
baseline, candidate, baseline, ... so a broken candidate fails on its first trial.

Exit codes:
  0  the run completed and the artifact was written
  1  the run was declined, aborted or incomplete, or the artifact could not be
     written (its JSON is printed to stdout so paid results survive)
  2  usage error or pre-run refusal
Messages go to stderr.
"""

from __future__ import annotations

import argparse
import random
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
# The only sys.path bootstrap: the package imports `eval_grade` (scripts/) and `minimal_yaml`.
for _path in (
    REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib",
    REPO_ROOT / "scripts" / "lib",
    REPO_ROOT / "scripts",
):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from model_effort import artifact, artifact_store, paths, runner
from model_effort.errors import UsageError
from model_effort.execution import TrialSettings, run_trials
from model_effort.plan import plan_run

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

DEFAULT_TRIALS = 5


def _read_git_head_sha() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=paths.REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip() or None


@dataclass(frozen=True)
class Deps:
    """Everything nondeterministic or environment-specific, so tests can inject it."""

    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    rng: random.Random = field(default_factory=random.Random)
    read_git_sha: Callable[[], str | None] = _read_git_head_sha
    agents_dir: Path = paths.AGENTS_DIR
    expected_dir: Path = paths.EXPECTED_DIR
    fixtures_dir: Path = paths.FIXTURES_DIR


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
        default=paths.RUNS_DIR,
        help="directory the artifact is written to "
        f"(default: {paths.RUNS_DIR.relative_to(paths.REPO_ROOT)})",
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


def _split_csv(text: str | None) -> list[str] | None:
    if text is None:
        return None
    return list(dict.fromkeys(part.strip() for part in text.split(",") if part.strip()))


def _save_artifact(path: Path, data: dict) -> int:
    """Write the artifact atomically; on any write error print the JSON so paid results survive."""
    text = artifact_store.render_artifact(data)
    try:
        artifact_store.write_artifact(path, text)
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
        plan = plan_run(
            args.agent,
            candidate_model=args.model,
            candidate_effort=args.effort,
            fixture_stems=_split_csv(args.fixtures),
            runs_dir=args.runs_dir,
            now=deps.clock(),
            rng=deps.rng,
            git_sha=deps.read_git_sha(),
            agents_dir=deps.agents_dir,
            expected_dir=deps.expected_dir,
            fixtures_dir=deps.fixtures_dir,
        )
    except UsageError as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_USAGE
    settings = TrialSettings(
        trials=args.trials,
        trial_timeout=args.trial_timeout,
        claude_bin=args.claude_bin,
        expected_dir=deps.expected_dir,
    )
    with artifact_store.release_if_unwritten(plan.artifact_path):
        arm_runs = run_trials(plan, settings)
        data = artifact.build_artifact(plan.metadata, arm_runs)
        return _save_artifact(plan.artifact_path, data)


if __name__ == "__main__":
    sys.exit(main())
