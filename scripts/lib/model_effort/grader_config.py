"""Which grader an agent's trials use, read from the committed grader map.

`evals/model-effort/graders.json` names the grader per agent; an agent it does
not list uses the expected-findings grader. The map also says whether a
write-capable agent may use its write tools inside the trial sandbox, and, for a
rubric-graded agent, which pinned model judges it and which committed rubric the
judge applies. The run artifact records the grader, so the decision log can cite it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from .errors import UsageError

AGENTS_KEY = "agents"
# Weakest first: the judge for an agent is the next entry, capped at the last.
MODEL_TIERS = ("haiku", "sonnet", "opus")
# A rubric criterion line: `- **<id>**: <requirement>`.
_CRITERION_PATTERN = re.compile(r"^- \*\*([a-z0-9][a-z0-9-]*)\*\*:", re.MULTILINE)


class GraderKind(StrEnum):
    """Grader types; values are the run artifact's `grader` strings."""

    EXPECTED_FINDINGS = "expected-findings"
    TESTS_PASS = "tests-pass"
    DISPATCH_SET = "dispatch-set"
    RUBRIC = "rubric"


@dataclass(frozen=True)
class Judge:
    """The pinned rubric judge and the committed rubric it applies."""

    model: str
    effort: str
    rubric_path: Path
    rubric_text: str
    criterion_ids: tuple[str, ...]


@dataclass(frozen=True)
class AgentGrading:
    kind: GraderKind
    sandbox: bool = False
    judge: Judge | None = None


DEFAULT_GRADING = AgentGrading(GraderKind.EXPECTED_FINDINGS)


def load_grader_map(path: Path) -> dict[str, dict]:
    """The map's per-agent entries; an absent file means every agent uses the default.

    Raises:
        UsageError: the file is not valid JSON or has no `agents` object.
    """
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise UsageError(f"cannot read the grader map {path}: {error}") from error
    agents = data.get(AGENTS_KEY) if isinstance(data, dict) else None
    if not isinstance(agents, dict):
        raise UsageError(f"grader map {path} has no `{AGENTS_KEY}` object")
    return agents


def resolve_agent_grading(agent: str, map_path: Path) -> AgentGrading:
    """Return how `agent` is graded, with a rubric agent's rubric read now.

    Raises:
        UsageError: the map is unreadable, names an unknown grader, or a rubric
            entry lacks its judge or rubric, or the rubric has no criteria.
    """
    entry = load_grader_map(map_path).get(agent)
    if entry is None:
        return DEFAULT_GRADING
    try:
        kind = GraderKind(entry.get("grader"))
    except ValueError as error:
        known = ", ".join(kind.value for kind in GraderKind)
        raise UsageError(
            f"grader map {map_path}: agent {agent!r} names grader "
            f"{entry.get('grader')!r}; use one of {known}"
        ) from error
    judge = _load_judge(agent, entry, map_path) if kind is GraderKind.RUBRIC else None
    return AgentGrading(kind=kind, sandbox=entry.get("sandbox") is True, judge=judge)


def _load_judge(agent: str, entry: dict, map_path: Path) -> Judge:
    judge = entry.get("judge")
    rubric = entry.get("rubric")
    if not isinstance(judge, dict) or not judge.get("model") or not judge.get("effort"):
        raise UsageError(
            f"grader map {map_path}: rubric agent {agent!r} needs a judge with a "
            "pinned `model` and `effort`"
        )
    if not isinstance(rubric, str) or not rubric:
        raise UsageError(
            f"grader map {map_path}: rubric agent {agent!r} needs a `rubric` path"
        )
    rubric_path = map_path.parent / rubric
    try:
        rubric_text = rubric_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise UsageError(
            f"cannot read the rubric for agent {agent!r} ({rubric_path}): {error}"
        ) from error
    criterion_ids = parse_criterion_ids(rubric_text)
    if not criterion_ids:
        raise UsageError(
            f"rubric {rubric_path} lists no criteria: add `- **<id>**: <requirement>` lines"
        )
    return Judge(
        model=judge["model"],
        effort=judge["effort"],
        rubric_path=rubric_path,
        rubric_text=rubric_text,
        criterion_ids=criterion_ids,
    )


def parse_criterion_ids(rubric_text: str) -> tuple[str, ...]:
    """The criterion IDs a rubric declares, in order, without repeats."""
    return tuple(dict.fromkeys(_CRITERION_PATTERN.findall(rubric_text)))


def model_tier(model: str) -> int | None:
    """Index in `MODEL_TIERS` for an alias or a full model ID; None when unknown."""
    lowered = model.lower()
    for index, tier in enumerate(MODEL_TIERS):
        if lowered == tier or f"-{tier}-" in f"-{lowered}-":
            return index
    return None


def required_judge_tier(arm_models: list[str]) -> int | None:
    """The lowest judge tier allowed: one above the strongest arm, capped at the top tier.

    None when an arm's model has no known tier.
    """
    tiers = [model_tier(model) for model in arm_models]
    if any(tier is None for tier in tiers):
        return None
    return min(max(tiers) + 1, len(MODEL_TIERS) - 1)


def check_judge_tier(judge: Judge, arm_models: list[str]) -> None:
    """Refuse a judge weaker than one tier above every arm under test.

    Raises:
        UsageError: an arm's or the judge's tier is unknown, or the judge is too weak.
    """
    required = required_judge_tier(arm_models)
    judge_tier = model_tier(judge.model)
    if required is None or judge_tier is None:
        raise UsageError(
            f"cannot place the judge {judge.model!r} or an arm "
            f"({', '.join(arm_models)}) on the {'/'.join(MODEL_TIERS)} ladder, so the "
            "rubric judge cannot be checked to sit one tier above the agent"
        )
    if judge_tier < required:
        raise UsageError(
            f"the rubric judge {judge.model!r} must be at least {MODEL_TIERS[required]} "
            f"to sit one tier above the arms ({', '.join(arm_models)}): pin a stronger "
            "judge in evals/model-effort/graders.json or choose a weaker candidate"
        )
