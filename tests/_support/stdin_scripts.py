"""Shared table of the eight entry points that read stdin by default.

Each row names a script (path relative to ``plugins/dev-team``), the argv that
invokes it with its input flag absent, that input flag, and whether a call
needs the flag at all. ``orchestrator.py`` has no input flag and falls back to
a default request, so its ``flag`` is ``None`` and ``needs_flag`` is False.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StdinScript:
    script: str
    argv: tuple[str, ...]
    flag: str | None
    needs_flag: bool


STDIN_SCRIPTS: tuple[StdinScript, ...] = (
    StdinScript(
        "skills/code-review/scripts/change_impact.py",
        ("--files", "a.py"),
        "--diff-from",
        True,
    ),
    StdinScript(
        "skills/code-review/scripts/finding_signature.py",
        ("--round", "1"),
        "--findings",
        True,
    ),
    StdinScript(
        "skills/code-review/scripts/review_context_pack.py",
        (),
        "--files-from",
        True,
    ),
    StdinScript(
        "skills/code-review/scripts/render_tiered_findings.py",
        (),
        "--findings",
        True,
    ),
    StdinScript(
        "scripts/checkpoint_abort.py",
        (),
        "--cheap-results-from",
        True,
    ),
    StdinScript(
        "scripts/pr_close_keyword_lint.py",
        (),
        "--body-file",
        True,
    ),
    StdinScript(
        "scripts/autoship_queue.py",
        ("--max-issues", "5"),
        "--input-file",
        True,
    ),
    StdinScript(
        "scripts/orchestrator.py",
        ("--skip-llm",),
        None,
        False,
    ),
)
