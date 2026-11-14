"""Which grader an agent's trials use, read from the committed grader map.

`evals/model-effort/graders.json` names the grader per agent; an agent it does
not list uses the expected-findings grader. The map also says whether a
write-capable agent may use its write tools inside the trial sandbox, and, for a
rubric-graded agent, which pinned model judges it (the map's top-level `judge`,
unless the agent overrides it) and which committed rubric the judge applies. The
run artifact records the grader, so the decision log can cite it.

The judge-tier ladder lives in `judge_tier`, rubric reading in `rubric_file`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from .errors import UsageError
from .rubric_file import Judge, load_judge

AGENTS_KEY = "agents"
JUDGE_KEY = "judge"
# The `scripts/eval_graders` grader an `agents` block uses when it names none.
AGENT_BLOCK_DEFAULT_GRADER = "verdict"


class GraderKind(StrEnum):
    """Grader types; values are the run artifact's `grader` strings."""

    EXPECTED_FINDINGS = "expected-findings"
    TESTS_PASS = "tests-pass"
    DISPATCH_SET = "dispatch-set"
    RUBRIC = "rubric"


# The one place a harness kind is tied to the `scripts/eval_graders` registry
# names its fixtures' expected entries may declare.
REGISTRY_GRADERS: dict[GraderKind, frozenset[str]] = {
    GraderKind.EXPECTED_FINDINGS: frozenset({"verdict", "finding_ids"}),
    GraderKind.TESTS_PASS: frozenset({"tests_pass"}),
    GraderKind.DISPATCH_SET: frozenset({"dispatch_set"}),
    GraderKind.RUBRIC: frozenset({"rubric"}),
}


def entry_grader(agent_block: dict) -> str:
    """The registry grader an expected entry's agent block uses, default included."""
    return agent_block.get("grader", AGENT_BLOCK_DEFAULT_GRADER)


@dataclass(frozen=True)
class AgentGrading:
    kind: GraderKind
    sandbox: bool = False
    judge: Judge | None = None


DEFAULT_GRADING = AgentGrading(GraderKind.EXPECTED_FINDINGS)


def _read_map(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise UsageError(f"cannot read the grader map {path}: {error}") from error
    if not isinstance(data, dict) or not isinstance(data.get(AGENTS_KEY), dict):
        raise UsageError(f"grader map {path} has no `{AGENTS_KEY}` object")
    return data


def load_grader_map(path: Path) -> dict[str, dict]:
    """The map's per-agent entries; an absent file means every agent uses the default.

    Raises:
        UsageError: the file is not valid JSON or has no `agents` object.
    """
    return _read_map(path).get(AGENTS_KEY, {})


def resolve_agent_grading(agent: str, map_path: Path) -> AgentGrading:
    """Return how `agent` is graded, with a rubric agent's rubric read now.

    Raises:
        UsageError: the map is unreadable, the agent's entry is not an object or
            names an unknown grader, or a rubric entry lacks its judge or rubric,
            or the rubric has no criteria.
    """
    data = _read_map(map_path)
    entry = data.get(AGENTS_KEY, {}).get(agent)
    if entry is None:
        return DEFAULT_GRADING
    if not isinstance(entry, dict):
        raise UsageError(
            f"grader map {map_path}: agent {agent!r} entry must be an object, "
            f"got {type(entry).__name__}"
        )
    try:
        kind = GraderKind(entry.get("grader"))
    except ValueError as error:
        known = ", ".join(kind.value for kind in GraderKind)
        raise UsageError(
            f"grader map {map_path}: agent {agent!r} names grader "
            f"{entry.get('grader')!r}; use one of {known}"
        ) from error
    judge = (
        _judge_for(agent, entry, data.get(JUDGE_KEY), map_path)
        if kind is GraderKind.RUBRIC
        else None
    )
    return AgentGrading(kind=kind, sandbox=entry.get("sandbox") is True, judge=judge)


def _judge_for(agent: str, entry: dict, default_judge, map_path: Path) -> Judge:
    own_judge = entry.get(JUDGE_KEY)
    merged = {
        **(default_judge if isinstance(default_judge, dict) else {}),
        **(own_judge if isinstance(own_judge, dict) else {}),
    }
    rubric = entry.get("rubric")
    if not merged.get("model") or not merged.get("effort"):
        raise UsageError(
            f"grader map {map_path}: rubric agent {agent!r} needs a judge with a "
            "pinned `model` and `effort` (its own, or the map's top-level `judge`)"
        )
    if not isinstance(rubric, str) or not rubric:
        raise UsageError(
            f"grader map {map_path}: rubric agent {agent!r} needs a `rubric` path"
        )
    return load_judge(
        agent, merged["model"], merged["effort"], map_path.parent / rubric
    )
