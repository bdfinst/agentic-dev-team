"""Rule registry for the SQL anti-pattern detector.

Public interface for a rule family
----------------------------------

A family lives in one module, ``sql_rules_<family>.py``, next to this file.
The module exposes a module-level ``RULES`` sequence of ``Rule`` entries.
``discover_rules()`` imports every ``sql_rules_*.py`` file and collects them.
No other file lists the rules, so a new family needs no edit here.

A ``Rule`` carries:

- ``id``: ``sql.<family>.<slug>``, for example ``sql.schema.positional-insert``
- ``family``: the middle segment of the id
- ``dialect``: ``ansi``, ``tsql``, or ``postgres``
- ``owner``: ``script`` (decided by ``check``) or ``agent`` (decided by the
  ``sql-review`` agent; no ``check``)
- ``severity``: ``error``, ``warning``, or ``suggestion``, the scale in
  ``knowledge/review-agent-output-contract.md``
- ``message`` and ``fix``: one line each
- ``positive`` and ``negative``: fixtures. A script-owned rule lists
  ``Fixture`` objects (``positive`` names the lines that must fire).
  An agent-owned rule lists eval fixture file names under ``evals/fixtures/``.
- ``check``: ``check(ctx) -> Iterable[Hit]`` for script-owned rules

Every rule also needs one ``### <id>`` entry in a catalog file under
``knowledge/sql-anti-patterns/``. ``tests/scripts/test_sql_rule_registry.py``
enforces fixtures, behavior, and catalog parity.

Stdlib-only. Python 3.10+.
"""

from __future__ import annotations

import importlib
import re
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from sql_dialect import DIALECTS
from sql_tokenize import Token

LIB_DIR = Path(__file__).resolve().parent
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

OWNER_SCRIPT = "script"
OWNER_AGENT = "agent"
OWNERS = (OWNER_SCRIPT, OWNER_AGENT)
SEVERITIES = ("error", "warning", "suggestion")
RULE_ID_RE = re.compile(r"^sql\.([a-z][a-z0-9]*)\.([a-z0-9]+(?:-[a-z0-9]+)*)$")


@dataclass(frozen=True)
class Fixture:
    """Inline SQL for a script-owned rule. ``lines`` are the expected hit lines."""

    name: str
    sql: str
    lines: tuple[int, ...] = ()


@dataclass(frozen=True)
class Hit:
    """One match from a rule's ``check``. ``line`` is 1-based."""

    line: int
    text: str


@dataclass(frozen=True)
class Context:
    """What a rule's ``check`` sees. ``tokens`` excludes comments."""

    tokens: Sequence[Token]
    dialect: str


@dataclass(frozen=True)
class Rule:
    id: str
    family: str
    dialect: str
    owner: str
    severity: str
    message: str
    fix: str
    positive: tuple = ()
    negative: tuple = ()
    check: Callable[[Context], Iterable[Hit]] | None = None


def discover_rules(rules_dir: Path | None = None) -> list[Rule]:
    """Import every ``sql_rules_*.py`` in ``rules_dir`` and collect its ``RULES``.

    Raises ``ValueError`` on a duplicate rule id.
    """
    directory = Path(rules_dir) if rules_dir else LIB_DIR
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))
    rules: list[Rule] = []
    seen: dict[str, str] = {}
    for path in sorted(directory.glob("sql_rules_*.py")):
        module = importlib.import_module(path.stem)
        for rule in getattr(module, "RULES", ()):
            if rule.id in seen:
                raise ValueError(
                    f"duplicate rule id {rule.id} in {path.stem} and {seen[rule.id]}"
                )
            seen[rule.id] = path.stem
            rules.append(rule)
    return rules


def _one_line(value: str) -> bool:
    return bool(value.strip()) and "\n" not in value


def validate_rule(rule: Rule) -> list[str]:
    """Return the structural problems of one registry entry. Empty means valid."""
    problems: list[str] = []
    match = RULE_ID_RE.match(rule.id)
    if not match:
        problems.append(f"{rule.id}: id must match sql.<family>.<slug>")
    elif match.group(1) != rule.family:
        problems.append(f"{rule.id}: family {rule.family!r} differs from the id")
    if rule.dialect not in DIALECTS:
        problems.append(f"{rule.id}: unknown dialect {rule.dialect!r}")
    if rule.owner not in OWNERS:
        problems.append(f"{rule.id}: unknown owner {rule.owner!r}")
    if rule.severity not in SEVERITIES:
        problems.append(f"{rule.id}: unknown severity {rule.severity!r}")
    if not _one_line(rule.message):
        problems.append(f"{rule.id}: message must be one non-empty line")
    if not _one_line(rule.fix):
        problems.append(f"{rule.id}: fix must be one non-empty line")
    if not rule.positive:
        problems.append(f"{rule.id}: no positive fixture")
    if not rule.negative:
        problems.append(f"{rule.id}: no negative fixture")
    if rule.owner == OWNER_SCRIPT:
        if rule.check is None:
            problems.append(f"{rule.id}: script-owned rule has no check")
        for fixture in rule.positive:
            if not isinstance(fixture, Fixture) or not fixture.lines:
                problems.append(
                    f"{rule.id}: positive fixture must be a Fixture with expected lines"
                )
        for fixture in rule.negative:
            if not isinstance(fixture, Fixture) or fixture.lines:
                problems.append(
                    f"{rule.id}: negative fixture must be a Fixture with no lines"
                )
    elif rule.owner == OWNER_AGENT:
        if rule.check is not None:
            problems.append(f"{rule.id}: agent-owned rule must not have a check")
        for fixture in (*rule.positive, *rule.negative):
            if not isinstance(fixture, str) or not fixture:
                problems.append(f"{rule.id}: agent-owned fixtures are eval file names")
    return problems
