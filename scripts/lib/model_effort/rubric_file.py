"""Read a committed agent-level rubric: its text and the criterion IDs it declares."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .errors import UsageError

# A rubric criterion line: `- **<id>**: <requirement>`.
_CRITERION_PATTERN = re.compile(r"^- \*\*([a-z0-9][a-z0-9-]*)\*\*:", re.MULTILINE)


@dataclass(frozen=True)
class Judge:
    """The pinned rubric judge and the committed rubric it applies."""

    model: str
    effort: str
    rubric_path: Path
    rubric_text: str
    criterion_ids: tuple[str, ...]


def parse_criterion_ids(rubric_text: str) -> tuple[str, ...]:
    """The criterion IDs a rubric declares, in order, without repeats."""
    return tuple(dict.fromkeys(_CRITERION_PATTERN.findall(rubric_text)))


def load_judge(agent: str, model: str, effort: str, rubric_path: Path) -> Judge:
    """Read the rubric at `rubric_path` and pair it with the pinned judge.

    Raises:
        UsageError: the rubric cannot be read or lists no criteria.
    """
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
        model=model,
        effort=effort,
        rubric_path=rubric_path,
        rubric_text=rubric_text,
        criterion_ids=criterion_ids,
    )
