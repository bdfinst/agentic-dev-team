"""Plan a run: validate everything that can be checked before spending, then reserve the artifact.

Planning takes plain values, not parsed command-line arguments, so it can be
driven from tests and from other callers.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import artifact_store, external, interrupts, paths
from .agent_file import AgentFrontmatterError, UnknownAgentError, load_agent_file
from .agent_spec import AgentSpec, build_agent_spec
from .arm import BASELINE_LABEL, CANDIDATE_LABEL, Arm
from .errors import UsageError
from .fixtures import ResolvedFixture, resolve_fixtures
from .paths import EvalPaths
from .run_id import make_run_id
from .run_types import RunMetadata
from .snapshot import InputSnapshot, take_snapshot
from .tools import ToolProfile, WriteCapableAgentError, resolve_tool_profile

AGENT_ERROR_FIX_HINTS = {
    WriteCapableAgentError: " Choose an agent whose tools are limited to Read, Grep and Glob.",
    AgentFrontmatterError: " Fix the agent file's frontmatter; the baseline arm needs `model:` and `effort:`.",
}


@dataclass(frozen=True)
class RunPlan:
    agent: str
    system_prompt: str
    arms: tuple[Arm, ...]
    profile: ToolProfile
    snapshot: InputSnapshot
    metadata: RunMetadata
    artifact_path: Path

    @property
    def fixtures(self) -> tuple[ResolvedFixture, ...]:
        """The fixtures to run, as paths into the plan's snapshot."""
        return self.snapshot.fixtures


@contextmanager
def plan_run(
    agent: str,
    *,
    candidate_model: str | None,
    candidate_effort: str | None,
    fixture_stems: list[str] | None,
    runs_dir: Path,
    now: datetime,
    rng,
    git_sha: str | None,
    eval_paths: EvalPaths,
) -> Iterator[RunPlan]:
    """Yield the plan, with the artifact path reserved; the reservation is the last step.

    The candidate arm takes `candidate_model`/`candidate_effort`, each defaulting
    to the baseline (frontmatter) value. The baseline's frontmatter values and any
    explicit candidate values are checked against the agent contract before the
    run ID, which names the artifact file, is built from them. `rng` needs
    `getrandbits`. `eval_paths` names the directories the agent file, expected
    entries, fixtures and knowledge are read from.

    The grader and the environment scrub the trials use are loaded here, so the
    ones in place at approval are the ones every trial uses.

    The fixtures, their expected entries and the knowledge directory are copied
    into `plan.snapshot`. Leaving the `with` removes the snapshot and an artifact
    placeholder still empty. The interrupt signals are held while the plan's
    resources are made and while they are released, so a signal never leaves a
    partial copy or a stray placeholder behind: it is delivered once that step is done.

    Raises:
        UsageError: a script the trials rely on cannot be loaded or no longer fits;
            the agent is unknown, write-capable or has unusable
            frontmatter (a missing or invalid `model:` or `effort:` included); a
            candidate value is invalid or leaves the candidate identical to the
            baseline; fixtures cannot be resolved or copied; or the artifact
            path is unavailable.
    """
    _load_external_scripts()
    agent_spec, profile = _load_agent(agent, eval_paths.agents_dir)
    _refuse_invalid_values(
        agent_spec.model,
        agent_spec.effort,
        model_label=f"agent {agent!r} frontmatter `model:`",
        effort_label=f"agent {agent!r} frontmatter `effort:`",
    )
    validate_candidate(candidate_model, candidate_effort)
    fixtures = resolve_fixtures(
        agent, fixture_stems, eval_paths.expected_dir, eval_paths.fixtures_dir
    )
    baseline = Arm(BASELINE_LABEL, agent_spec.model, agent_spec.effort)
    candidate = Arm(
        CANDIDATE_LABEL,
        candidate_model or baseline.model,
        candidate_effort or baseline.effort,
    )
    _refuse_identical_arms(baseline, candidate)
    run_id = make_run_id(now, agent, candidate.model, candidate.effort, rng)
    owned = ExitStack()
    try:
        with interrupts.held_signals():
            try:
                snapshot = take_snapshot(eval_paths, fixtures)
            except OSError as error:
                raise UsageError(
                    f"cannot copy the run's inputs (fixtures, expected entries, knowledge) "
                    f"to a temp directory: {error}"
                ) from error
            owned.callback(snapshot.remove)
            artifact_path = artifact_store.reserve_artifact_path(runs_dir, run_id)
            owned.enter_context(artifact_store.release_if_unwritten(artifact_path))
            planned = RunPlan(
                agent=agent,
                system_prompt=agent_spec.system_prompt,
                arms=(baseline, candidate),
                profile=profile,
                snapshot=snapshot,
                metadata=RunMetadata(
                    run_id=run_id,
                    created=now,
                    git_sha=git_sha,
                    agent=agent,
                    knowledge_dir=_relative_to_repo(eval_paths.knowledge_dir),
                ),
                artifact_path=artifact_path,
            )
        yield planned
    finally:
        with interrupts.held_signals():
            owned.close()


def _load_external_scripts() -> None:
    try:
        external.load_for_run()
    except (ImportError, OSError, SyntaxError) as error:
        raise UsageError(
            f"cannot load a script the trials rely on: {error}. "
            "Restore it, or update the harness to match it"
        ) from error


def _refuse_identical_arms(baseline: Arm, candidate: Arm) -> None:
    if (candidate.model, candidate.effort) == (baseline.model, baseline.effort):
        raise UsageError(
            f"the candidate arm (model {candidate.model}, effort {candidate.effort}) "
            "is identical to the agent's frontmatter, so there is nothing to compare: "
            "pass a different --model or --effort"
        )


def validate_candidate(model: str | None, effort: str | None) -> None:
    """Check explicit candidate values against the agent contract's enums.

    Raises:
        UsageError: a value is not in the contract, or the contract is unreadable.
    """
    if model is None and effort is None:
        return
    _refuse_invalid_values(
        model,
        effort,
        model_label="candidate --model",
        effort_label="candidate --effort",
    )


def _refuse_invalid_values(
    model: str | None, effort: str | None, *, model_label: str, effort_label: str
) -> None:
    """Refuse a model or effort outside the agent contract; `None` is skipped.

    Raises:
        UsageError: a value is not in the contract, or the contract is unreadable.
    """
    enums = external.contract_enums()
    if enums is None:
        raise UsageError(
            "cannot read the agent contract (plugins/marketplace-dev/knowledge/"
            "agent-contract.json) to validate model and effort values: restore the file"
        )
    models, efforts = enums
    if model is not None and not external.model_is_valid(model, models):
        raise UsageError(
            f"{model_label} {model!r} is not valid: use one of "
            f"{', '.join(models)}, or a full model ID such as claude-opus-4-8"
        )
    if effort is not None and effort not in efforts:
        raise UsageError(
            f"{effort_label} {effort!r} is not valid: use one of {', '.join(efforts)}"
        )


def _load_agent(agent: str, agents_dir: Path) -> tuple[AgentSpec, ToolProfile]:
    try:
        loaded = load_agent_file(agent, agents_dir)
        profile = resolve_tool_profile(agent, loaded.frontmatter)
        return build_agent_spec(agent, loaded), profile
    except (
        UnknownAgentError,
        WriteCapableAgentError,
        AgentFrontmatterError,
    ) as error:
        hint = AGENT_ERROR_FIX_HINTS.get(type(error), "")
        raise UsageError(f"{error}{hint}") from error


def _relative_to_repo(path: Path) -> str:
    try:
        return path.relative_to(paths.REPO_ROOT).as_posix()
    except ValueError:
        return str(path)
