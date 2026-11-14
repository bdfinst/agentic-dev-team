#!/usr/bin/env python3
"""Append a `keep` row for a new agent to a repo's model/effort decision log.

Usage: append_model_effort_row.py <agent-file> [--repo-root DIR]

The log is `docs/model-effort-decisions.md` under the repo root. A repo
without that file is left untouched and the script prints nothing. The row
records the agent's frontmatter `model:`/`effort:` as both baseline and final,
counts the `evals/expected/*.json` fixtures that name the agent, and picks the
matching keep reason. The row goes into the decision table in name order,
among the rows from the agent's directory. A directory with no row in the log
is not tracked by it, so the script skips that agent.

Exit codes: 0 row appended or nothing to do; 1 the agent file's `model:` or
`effort:` value is missing or has no rank in the log.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath

LOG_RELATIVE = Path("docs") / "model-effort-decisions.md"
EXPECTED_RELATIVE = Path("evals") / "expected"
FIXTURES_RELATIVE = Path("evals") / "fixtures"
MIN_FIXTURES = 3
REASON_NO_FIXTURE = "no fixture"
REASON_INSUFFICIENT_FIXTURES = "insufficient fixtures"
REASON_DIRECTORY_FIXTURES_ONLY = "directory fixtures only"
REASON_NOT_SELECTED = "not selected"
AGENT_COLUMN = "Agent"
SOURCE_COLUMN = "Source"
# The decision log ranks these values; `inherit`, a full model ID, or another
# effort has no rank there, so its row must be written by hand.
LOG_MODELS = {"haiku", "sonnet", "opus", "fable"}
LOG_EFFORTS = {"low", "medium", "high", "xhigh", "max"}
FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---", re.DOTALL)


def frontmatter_field(text: str, field: str) -> str:
    """One frontmatter value, unquoted and without an inline comment; "" if absent."""
    block = FRONTMATTER_RE.match(text)
    if not block:
        return ""
    match = re.search(rf"^{re.escape(field)}\s*:\s*(.*)$", block.group(1), re.MULTILINE)
    if not match:
        return ""
    return re.sub(r"\s+#.*$", "", match.group(1)).strip().strip("\"'").strip()


def fixture_names_agent(spec: object, agent: str) -> bool:
    if not isinstance(spec, dict):
        return False
    agents = spec.get("agents")
    applicable = spec.get("applicableAgents")
    return (isinstance(agents, dict) and agent in agents) or (
        isinstance(applicable, list) and agent in applicable
    )


def agent_fixtures(root: Path, agent: str) -> list[str]:
    """The `fixture` value of every readable expected file that names the agent."""
    fixtures = []
    for path in sorted((root / EXPECTED_RELATIVE).glob("*.json")):
        try:
            spec = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if fixture_names_agent(spec, agent):
            fixtures.append(str(spec.get("fixture") or path.stem))
    return fixtures


def keep_reason(root: Path, fixtures: list[str]) -> str:
    if not fixtures:
        return REASON_NO_FIXTURE
    if len(fixtures) < MIN_FIXTURES:
        return REASON_INSUFFICIENT_FIXTURES
    if all((root / FIXTURES_RELATIVE / name).is_dir() for name in fixtures):
        return REASON_DIRECTORY_FIXTURES_ONLY
    return REASON_NOT_SELECTED


def split_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def find_table(lines: list[str]) -> tuple[int, int, list[str]] | None:
    """(first row index, end index, header cells) of the table with a Source column."""
    for index, line in enumerate(lines):
        if not line.startswith("|"):
            continue
        header = split_cells(line)
        if AGENT_COLUMN not in header or SOURCE_COLUMN not in header:
            continue
        first_row = index + 2
        end = first_row
        while end < len(lines) and lines[end].startswith("|"):
            end += 1
        return first_row, end, header
    return None


def insertion_index(
    rows: list[list[str]], header: list[str], name: str, directory: str
) -> int | None:
    """Row offset that keeps the agent's directory in name order; None if untracked."""
    agent_col, source_col = header.index(AGENT_COLUMN), header.index(SOURCE_COLUMN)
    same_directory = [
        offset
        for offset, cells in enumerate(rows)
        if len(cells) > source_col
        and str(PurePosixPath(cells[source_col]).parent) == directory
    ]
    if not same_directory:
        return None
    for offset in same_directory:
        if rows[offset][agent_col] > name:
            return offset
    return same_directory[-1] + 1


def build_row(header: list[str], values: dict[str, str]) -> str:
    return "| " + " | ".join(values.get(column, "") for column in header) + " |"


def append_row(agent_file: Path, root: Path) -> int:
    log_path = root / LOG_RELATIVE
    if not log_path.is_file():
        return 0
    text = agent_file.read_text(encoding="utf-8")
    model, effort = frontmatter_field(text, "model"), frontmatter_field(text, "effort")
    missing = [
        field for field, value in (("model", model), ("effort", effort)) if not value
    ]
    if missing:
        print(
            f"{agent_file}: frontmatter has no {' or '.join(missing)} value",
            file=sys.stderr,
        )
        return 1
    if model not in LOG_MODELS or effort not in LOG_EFFORTS:
        print(
            f"{agent_file}: model '{model}' / effort '{effort}' has no rank in "
            f"{LOG_RELATIVE.as_posix()}; add the row by hand",
            file=sys.stderr,
        )
        return 1
    source = agent_file.resolve().relative_to(root.resolve()).as_posix()
    name = agent_file.stem
    lines = log_path.read_text(encoding="utf-8").splitlines(keepends=True)
    table = find_table(lines)
    if table is None:
        print(
            f"{LOG_RELATIVE.as_posix()}: no decision table with an Agent and Source column"
        )
        return 0
    first_row, end, header = table
    rows = [split_cells(line) for line in lines[first_row:end]]
    source_col = header.index(SOURCE_COLUMN)
    if any(len(cells) > source_col and cells[source_col] == source for cells in rows):
        print(f"{source} already listed in {LOG_RELATIVE.as_posix()}")
        return 0
    directory = str(PurePosixPath(source).parent)
    offset = insertion_index(rows, header, name, directory)
    if offset is None:
        print(f"{LOG_RELATIVE.as_posix()} does not track {directory}/; no row added")
        return 0
    fixtures = agent_fixtures(root, name)
    row = build_row(
        header,
        {
            AGENT_COLUMN: name,
            SOURCE_COLUMN: source,
            "Baseline model": model,
            "Baseline effort": effort,
            "Final model": model,
            "Final effort": effort,
            "Decision": "keep",
            "Fixtures": str(len(fixtures)),
            "Evidence or reason": keep_reason(root, fixtures),
        },
    )
    if not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    lines.insert(first_row + offset, row + "\n")
    log_path.write_text("".join(lines), encoding="utf-8")
    print(row)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("agent_file", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    return append_row(args.agent_file, args.repo_root)


if __name__ == "__main__":
    sys.exit(main())
