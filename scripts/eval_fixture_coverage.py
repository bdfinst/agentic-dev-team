#!/usr/bin/env python3
"""Count each review agent's eval fixtures, hard fixtures and clean fixtures.

A fixture counts for an agent when an `evals/expected/<stem>.json` entry has
that agent in its `agents` block and a file or directory with the same stem
exists in `evals/fixtures`. A fixture is:

- clean when the agent's `expectedStatus` is `pass`, or `skip` for an agent
  whose Skip rule covers a target with nothing to report. It has no expected
  finding, so any finding is a false positive. The rule is
  `is_clean_expectation` in scripts/lib/model_effort/fixtures.py, which the
  model/effort harness uses too.
- hard when the agent's entry carries a `hard` marker (a subtle defect,
  distractor code or a long file; see evals/README.md).

The review agents are `plugins/dev-team/agents/*-review.md`. Every one of them
needs at least MIN_FIXTURES fixtures, MIN_HARD hard and MIN_CLEAN clean.

Exit codes: 0 every review agent meets the minimums, 1 at least one does not,
2 a directory is missing or an expected file is malformed (invalid JSON, not
an object, or `agents` not an object). Every expected file is validated, with
or without a fixture.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_PACKAGE_PARENT = REPO_ROOT / "scripts" / "lib"
if str(_PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_PARENT))

from model_effort.fixtures import is_clean_expectation

MIN_FIXTURES = 5
MIN_HARD = 2
MIN_CLEAN = 1
REVIEW_AGENT_SUFFIX = "-review.md"


class MalformedExpectedError(Exception):
    """An expected file is invalid JSON, not an object, or has a non-object `agents`."""


@dataclass
class AgentCoverage:
    agent: str
    fixtures: list[str] = field(default_factory=list)
    hard: list[str] = field(default_factory=list)
    clean: list[str] = field(default_factory=list)

    def gaps(self) -> list[str]:
        found = []
        if len(self.fixtures) < MIN_FIXTURES:
            found.append(f"{len(self.fixtures)}/{MIN_FIXTURES} fixtures")
        if len(self.hard) < MIN_HARD:
            found.append(f"{len(self.hard)}/{MIN_HARD} hard")
        if len(self.clean) < MIN_CLEAN:
            found.append(f"{len(self.clean)}/{MIN_CLEAN} clean")
        return found


def review_agents(agents_dir: Path) -> list[str]:
    return sorted(
        path.name[: -len(".md")] for path in agents_dir.glob(f"*{REVIEW_AGENT_SUFFIX}")
    )


def fixture_stems(fixtures_dir: Path) -> set[str]:
    """A directory's stem is its name; a file's stem drops one extension."""
    return {p.name if p.is_dir() else p.stem for p in fixtures_dir.iterdir()}


def coverage(
    agents_dir: Path, expected_dir: Path, fixtures_dir: Path
) -> list[AgentCoverage]:
    agents = review_agents(agents_dir)
    by_agent = {agent: AgentCoverage(agent) for agent in agents}
    stems = fixture_stems(fixtures_dir)
    for path in sorted(expected_dir.glob("*.json")):
        entry = _load_entry(path)
        stem = path.stem
        if stem not in stems:
            continue
        for agent, expectation in entry.get("agents", {}).items():
            if agent not in by_agent or not isinstance(expectation, dict):
                continue
            row = by_agent[agent]
            row.fixtures.append(stem)
            if expectation.get("hard"):
                row.hard.append(stem)
            if is_clean_expectation(expectation):
                row.clean.append(stem)
    return [by_agent[agent] for agent in agents]


def _load_entry(path: Path) -> dict:
    try:
        entry = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise MalformedExpectedError(f"{path.name}: not valid JSON: {error}") from error
    if not isinstance(entry, dict):
        raise MalformedExpectedError(f"{path.name}: not a JSON object")
    agents = entry.get("agents", {})
    if not isinstance(agents, dict):
        raise MalformedExpectedError(f"{path.name}: `agents` is not a JSON object")
    return entry


def render(rows: list[AgentCoverage]) -> str:
    width = max((len(row.agent) for row in rows), default=5)
    lines = [f"{'agent':<{width}}  fixtures  hard  clean  gaps"]
    for row in rows:
        gaps = ", ".join(row.gaps()) or "-"
        lines.append(
            f"{row.agent:<{width}}  {len(row.fixtures):>8}  {len(row.hard):>4}"
            f"  {len(row.clean):>5}  {gaps}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--agents-dir", type=Path, default=REPO_ROOT / "plugins" / "dev-team" / "agents"
    )
    parser.add_argument(
        "--expected-dir", type=Path, default=REPO_ROOT / "evals" / "expected"
    )
    parser.add_argument(
        "--fixtures-dir", type=Path, default=REPO_ROOT / "evals" / "fixtures"
    )
    args = parser.parse_args(argv)
    for directory in (args.agents_dir, args.expected_dir, args.fixtures_dir):
        if not directory.is_dir():
            print(f"error: directory not found: {directory}", file=sys.stderr)
            return 2
    try:
        rows = coverage(args.agents_dir, args.expected_dir, args.fixtures_dir)
    except MalformedExpectedError as error:
        print(f"error: malformed expected file {error}", file=sys.stderr)
        return 2
    print(render(rows))
    short = [row.agent for row in rows if row.gaps()]
    if short:
        print(
            f"\n{len(short)} review agent(s) below the minimum: {', '.join(short)}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
