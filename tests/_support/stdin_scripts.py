"""Shared table of the eight entry points that read stdin by default.

Each row names a script (path relative to ``plugins/dev-team``), the argv that
invokes it with its input flag absent, and that input flag. ``orchestrator.py``
has no input flag and falls back to a default request, so its ``flag`` is
``None`` and ``needs_flag`` is False.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StdinScript:
    script: str
    argv: tuple[str, ...]
    flag: str | None

    @property
    def needs_flag(self) -> bool:
        return self.flag is not None


STDIN_SCRIPTS: tuple[StdinScript, ...] = (
    StdinScript(
        "skills/code-review/scripts/change_impact.py",
        ("--files", "a.py"),
        "--diff-from",
    ),
    StdinScript(
        "skills/code-review/scripts/finding_signature.py",
        ("--round", "1"),
        "--findings",
    ),
    StdinScript(
        "skills/code-review/scripts/review_context_pack.py",
        (),
        "--files-from",
    ),
    StdinScript(
        "skills/code-review/scripts/render_tiered_findings.py",
        (),
        "--findings",
    ),
    StdinScript(
        "scripts/checkpoint_abort.py",
        (),
        "--cheap-results-from",
    ),
    StdinScript(
        "scripts/pr_close_keyword_lint.py",
        (),
        "--body-file",
    ),
    StdinScript(
        "scripts/autoship_queue.py",
        ("--max-issues", "5"),
        "--input-file",
    ),
    StdinScript(
        "scripts/orchestrator.py",
        ("--skip-llm",),
        None,
    ),
)
