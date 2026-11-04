"""doctor_report.py - the check/report model and renderers for ``/doctor``.

Holds everything about *presenting* a diagnosis: the ``Status`` ordering, the
``Check`` and ``Report`` dataclasses, the versioned ``--json`` schema and the
human-readable text. The checks themselves live in ``scripts/doctor.py``.

Stdlib only. The top level stays parseable by Python 3.8 (``from __future__
import annotations``, no ``match``) so a too-old interpreter reaches
``doctor.py --probe`` and reports its version instead of a SyntaxError.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from operator import attrgetter
from typing import Any

SCHEMA_VERSION = 1


class Status(enum.Enum):
    """A check result. Declaration order is severity order: ok < warn < fail."""

    OK = "ok"
    WARN = "warn"
    FAIL = "fail"

    @property
    def rank(self) -> int:
        return list(Status).index(self)


@dataclass(frozen=True)
class Check:
    id: str
    status: Status
    summary: str
    fix: str | None = None


@dataclass(frozen=True)
class Report:
    plugin_root: str
    project_root: str
    checks: list[Check]
    fixed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def overall(self) -> Status:
        return max(
            (c.status for c in self.checks), key=attrgetter("rank"), default=Status.OK
        )

    def to_json(self) -> dict[str, Any]:
        """The ``--json`` payload; key order is the documented schema order."""
        return {
            "schema_version": SCHEMA_VERSION,
            "plugin_root": self.plugin_root,
            "project_root": self.project_root,
            "checks": [
                {
                    "id": c.id,
                    "status": c.status.value,
                    "summary": c.summary,
                    "fix": c.fix,
                }
                for c in self.checks
            ],
            "fixed": list(self.fixed),
            "overall": self.overall.value,
        }


def format_human(report: Report, git_toplevel: bool, fix_ran: bool = False) -> str:
    """Render the report as text; ``fix_ran`` adds the ``fixed:`` block."""
    lines = [
        f"plugin: {report.plugin_root}",
        f"project: {report.project_root}",
    ]
    if not git_toplevel:
        lines.append(f"note: {report.project_root} is not inside a git repository")
    for check in report.checks:
        lines.append(f"{check.status.value:<4}  {check.id}  {check.summary}")
        if check.fix is not None:
            lines.append(f"      fix: {check.fix}")
    if fix_ran:
        lines.extend(_block("fixed", report.fixed))
    if report.errors:
        lines.extend(_block("errors", report.errors))
    lines.append(f"overall: {report.overall.value}")
    return "\n".join(lines) + "\n"


def _block(title: str, entries: list[str]) -> list[str]:
    """``title: none`` for no entries, else ``title:`` and one indented line each."""
    if not entries:
        return [f"{title}: none"]
    return [f"{title}:"] + [f"  {entry}" for entry in entries]
