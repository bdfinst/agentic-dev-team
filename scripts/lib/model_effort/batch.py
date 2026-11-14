"""A stress batch: a stress-matrix run for every agent at one model tier, approved once.

Every agent whose frontmatter `model:` sits at the batch tier is planned up
front. One that cannot run (no fixture, a write-capable agent the grader map
does not sandbox, a judge below the required tier, results excluded from
evidence) is listed as skipped with its reason. The batch prints each agent's
configuration and estimate, then one combined estimate with the rubric judge
included, and asks for approval once. The agents then run one after another,
each writing its own artifact; the batch stops at the first run that does not
complete.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from contextlib import AbstractContextManager, ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path

from . import approval, interrupts, report
from .agent_file import (
    AgentFrontmatterError,
    UnknownAgentError,
    list_agent_names,
    load_agent_file,
)
from .agent_spec import build_agent_spec
from .cost import total_cost_usd
from .errors import UsageError
from .estimate import RunEstimate
from .execution import TrialRunner, run_trials
from .formatting import format_usd
from .judge_tier import MODEL_TIERS, model_tier
from .plan import RunPlan
from .rubric_judge import ProcessRunner
from .run_types import RunResult, TrialSettings
from .session import EXIT_FAILED, EXIT_OK, Console, estimate_and_echo, finish_run
from .stop_rules import SpendLimit
from .verdict import RECALL_GAP_EXCLUDED_AGENTS

PlanAgent = Callable[[str], AbstractContextManager[RunPlan]]
SettingsFor = Callable[[RunPlan], TrialSettings]


@dataclass(frozen=True)
class Skipped:
    agent: str
    reason: str


@dataclass(frozen=True)
class BatchPlan:
    plans: tuple[RunPlan, ...]
    skipped: tuple[Skipped, ...]


def agents_at_tier(tier: str, agents_dir: Path) -> tuple[list[str], list[Skipped]]:
    """The agents whose frontmatter model is at `tier`, and those whose model cannot be read."""
    wanted = MODEL_TIERS.index(tier)
    selected: list[str] = []
    unreadable: list[Skipped] = []
    for agent in list_agent_names(agents_dir):
        try:
            spec = build_agent_spec(agent, load_agent_file(agent, agents_dir))
        except (UnknownAgentError, AgentFrontmatterError) as error:
            unreadable.append(Skipped(agent, str(error)))
            continue
        if model_tier(spec.model) == wanted:
            selected.append(agent)
    return selected, unreadable


@contextmanager
def plan_batch(
    tier: str, agents_dir: Path, plan_agent: PlanAgent
) -> Iterator[BatchPlan]:
    """Plan every runnable agent at `tier`; the plans' resources are released on exit.

    Raises:
        UsageError: no agent at the tier can run.
    """
    selected, skipped = agents_at_tier(tier, agents_dir)
    plans: list[RunPlan] = []
    with ExitStack() as stack:
        for agent in selected:
            if agent in RECALL_GAP_EXCLUDED_AGENTS:
                skipped.append(Skipped(agent, RECALL_GAP_EXCLUDED_AGENTS[agent]))
                continue
            try:
                plans.append(stack.enter_context(plan_agent(agent)))
            except UsageError as error:
                skipped.append(Skipped(agent, str(error)))
        if not plans:
            reasons = (
                "; ".join(f"{s.agent}: {s.reason}" for s in skipped) or "none found"
            )
            raise UsageError(
                f"no agent at the {tier} tier can run a stress batch ({reasons})"
            )
        yield BatchPlan(tuple(plans), tuple(skipped))


def run_batch(
    batch: BatchPlan,
    settings_for: SettingsFor,
    spend_limit: SpendLimit | None,
    console: Console,
    *,
    assume_yes: bool,
    pricing_table: dict,
    run_trial: TrialRunner,
    guard: interrupts.RunGuard,
    run_judge_process: ProcessRunner | None = None,
) -> int:
    """Echo every agent's estimate and the combined one, ask once, then run each agent in turn.

    `spend_limit` bounds the combined estimate at the start and the charged cost
    across the whole batch: each agent's run gets what is left of it, and no
    agent starts once nothing is left.

    Raises:
        UsageError: a model is unpriced, or the combined estimate is above `spend_limit`.
    """
    priced = [
        (
            plan,
            settings,
            estimate_and_echo(plan, settings, None, pricing_table, console),
        )
        for plan in batch.plans
        for settings in (settings_for(plan),)
    ]
    estimates = [run_estimate for _, _, run_estimate in priced]
    _echo_skipped(batch.skipped, console)
    total_usd = total_cost_usd(e.estimated_total_usd for e in estimates)
    print(_render_batch_estimate(estimates, total_usd), file=console.stderr)
    if spend_limit is not None and spend_limit.refuses(total_usd):
        raise UsageError(
            f"batch estimate {format_usd(total_usd)} is above --max-cost "
            f"{format_usd(spend_limit.max_cost_usd)}: raise --max-cost, or lower --trials"
        )
    refusal = approval.refusal_unless_approved(
        assume_yes=assume_yes,
        stdin=console.stdin,
        stdin_is_tty=console.stdin_is_tty,
        stderr=console.stderr,
    )
    if refusal is not None:
        print(f"error: {refusal}", file=console.stderr)
        return EXIT_FAILED
    charged_usd = 0.0
    for index, (plan, settings, run_estimate) in enumerate(priced):
        remaining = None
        if spend_limit is not None:
            left_usd = spend_limit.max_cost_usd - charged_usd
            if left_usd <= 0:
                # Any trial would charge past the limit, so the agent is not started.
                print(
                    "error: spend limit reached; not run: "
                    f"{', '.join(p.agent for p, _, _ in priced[index:])}",
                    file=console.stderr,
                )
                return EXIT_FAILED
            remaining = SpendLimit(left_usd)
        with guard.held():
            run = run_trials(
                plan,
                settings,
                run_estimate,
                run_trial=run_trial,
                run_judge_process=run_judge_process,
                spend_limit=remaining,
                on_trial=lambda progress: print(
                    report.render_progress(progress), file=console.stderr
                ),
            )
            exit_code = finish_run(plan, run, run_estimate, console)
        charged_usd += _charged_usd(run, run_estimate)
        if exit_code != EXIT_OK or guard.arrived:
            not_run = [p.agent for p, _, _ in priced[index + 1 :]]
            print(
                f"error: batch stopped after {plan.agent}; not run: "
                f"{', '.join(not_run) or 'none'}",
                file=console.stderr,
            )
            return EXIT_FAILED
    return EXIT_OK


def _charged_usd(run: RunResult, run_estimate: RunEstimate) -> float:
    return total_cost_usd(
        run_estimate.total_charged_usd(arm_run.arm.label, result)
        for arm_run in run.arm_runs
        for result in arm_run.results
    )


def _echo_skipped(skipped: Sequence[Skipped], console: Console) -> None:
    if not skipped:
        return
    print("Skipped:", file=console.stderr)
    for item in skipped:
        print(f"  {item.agent}: {item.reason}", file=console.stderr)


def _render_batch_estimate(estimates: Sequence[RunEstimate], total_usd: float) -> str:
    judge_usd = total_cost_usd(e.judge_usd for e in estimates)
    return (
        f"Batch estimate (rough; real cost is usually lower, by up to several times): "
        f"{len(estimates)} agents, rubric judge {format_usd(judge_usd)}, "
        f"total {format_usd(total_usd)}"
    )
