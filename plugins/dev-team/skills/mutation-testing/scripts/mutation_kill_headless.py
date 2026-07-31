#!/usr/bin/env python3
"""mutation_kill_headless.py — unattended generation + CLI entry point.

Split out of ``mutation_kill_loop.py`` (#1562): the ``--headless`` CLI
argument parsing and entry point for the C#/Stryker.NET loop. The
agent-driven (default, interactive) path never touches this module — the
mutation-kill agent calls :func:`mutation_kill_loop.run_for_file` directly
with its own ``generate`` hook.

The ``claude --print`` invocation glue itself (``run_claude_headless``,
``resolve_model``, ``strip_code_fences``, ``claude_cli_available``,
``CLAUDE_CLI``) lives in ``mutation_kill_shared.py``, not here (#1601) — it's
reused verbatim by ``mutation_kill_loop_python.py``, and none of it is
C#-specific. This module only builds the C#-flavored prompt
(``build_generation_prompt``) and imports the handful of shared names it
actually calls (``CLAUDE_CLI``, ``resolve_model``, ``claude_cli_available``,
``run_claude_headless``); ``mutation_kill_loop_python.py`` now imports the
same names directly from ``mutation_kill_shared`` too, rather than through
this module, which previously dragged the whole C#/Stryker.NET stack
(``mutation_kill_loop`` and everything it imports) into the Python loop just
to reuse five language-neutral names.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from mutation_kill_loop import Generator, RunContext, load_loop_config, run_for_file
from mutation_kill_shared import (
    CLAUDE_CLI,
    claude_cli_available,
    resolve_model,
    run_claude_headless,
)

# The exact message the bare-CLI startup preflight prints. Pinned so the
# contract test can assert it verbatim.
NO_GENERATOR_MESSAGE = (
    "no test generator available — invoke via the mutation-kill agent "
    "or pass --headless"
)

# Printed when --headless is requested but the Claude CLI can't be reached.
# Names exactly how to install and authenticate it, and mutates no files.
MISSING_CLAUDE_MESSAGE = (
    f"--headless requires the Claude CLI but '{CLAUDE_CLI}' is not available. "
    "Install Claude Code (`npm install -g @anthropic-ai/claude-code`) and "
    "authenticate it (run `claude` once to log in, or set ANTHROPIC_API_KEY) — "
    "or set CLAUDE_BIN to the CLI's path."
)


def build_survivor_summary(survivors: list[dict], *, limit: int = 40) -> str:
    """Render surviving mutants as a compact, framework-agnostic list."""
    lines = []
    for mutant in survivors[:limit]:
        line = mutant.get("location", {}).get("start", {}).get("line", "?")
        mutator = mutant.get("mutatorName", "?")
        replacement = mutant.get("replacement", "")
        lines.append(f"- L{line} {mutator}: {replacement}".rstrip())
    if len(survivors) > limit:
        lines.append(f"- … and {len(survivors) - limit} more")
    return "\n".join(lines)


def build_generation_prompt(
    source_file: str,
    survivors: list[dict],
    source_text: str,
    test_text: str,
    *,
    source_limit: int = 8000,
) -> str:
    """Build the generation prompt.

    The existing test file is the *only* pattern — assertion library, mocking
    approach, fixtures, and naming conventions are all inferred from it. No
    library name is hardcoded here, so the prompt is repo-agnostic (AC1).
    """
    return (
        f"You are adding new test methods that KILL surviving mutations in "
        f"{source_file}.\n\n"
        "Match the existing test file exactly: its imports, assertion style, "
        "mocking approach, fixtures, and naming conventions are the pattern to "
        "follow. Do not introduce any library, helper, or convention that does "
        "not already appear in it.\n\n"
        f"## Surviving mutations ({len(survivors)})\n"
        f"{build_survivor_summary(survivors)}\n\n"
        f"## Source under test\n{source_text[:source_limit]}\n\n"
        f"## Existing test file (the pattern to match)\n{test_text}\n\n"
        "## Rules\n"
        "1. Return ONLY the new test methods — no class wrapper, namespace, or "
        "imports.\n"
        "2. Each must compile against the helpers already in the existing test "
        "file.\n"
        "3. Reuse the existing file's assertion, mocking, and fixture patterns "
        "exactly.\n"
        "4. Match the existing naming convention.\n"
        "5. Do not redeclare fields or helpers already present.\n"
        "6. Do not emit closing braces for the class or namespace.\n"
    )


def make_headless_generator(
    model: str | None = None, *, cwd: Path | None = None
) -> Generator:
    """Return a :data:`mutation_kill_loop.Generator` that shells to
    ``claude --print``.

    The returned callable builds the prompt from the existing test file (the
    pattern) plus the survivor summary, then delegates everything else to
    :func:`run_claude_headless`.
    """

    def generate(
        source_file: str,
        survivors: list[dict],
        source_text: str,
        test_text: str,
    ) -> str:
        prompt = build_generation_prompt(source_file, survivors, source_text, test_text)
        return run_claude_headless(prompt, model=model, cwd=cwd)

    return generate


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="mutation_kill_loop.py",
        description=(
            "Config-driven survivor-kill loop. Agent-driven by default; "
            "--headless enables unattended generation via the Claude CLI."
        ),
    )
    p.add_argument("--config", default="stryker-config.json", help="stryker-config.json path")
    p.add_argument("--file", help="Source file to target (basename or path)")
    p.add_argument("--output", default="StrykerOutput/agent", help="Scoped-run output dir")
    p.add_argument("--max-rounds", type=int, default=5, help="Max rounds per file")
    p.add_argument("--stryker-bin", default="dotnet-stryker", help="Stryker executable")
    p.add_argument(
        "--headless",
        action="store_true",
        help="Unattended generation via `claude --print` (CI / shard pipeline).",
    )
    p.add_argument(
        "--model",
        help=(
            "Generation model for --headless. Default: DEV_TEAM_MUTATION_MODEL "
            "env var, else omitted so `claude --print` uses its own default."
        ),
    )
    p.add_argument("--test-file", help="Test file to extend (required with --headless)")
    p.add_argument("--source-path", help="Source file under test (required with --headless)")
    p.add_argument("--report", help="Initial mutation report to seed round 1 (--headless)")
    return p.parse_args(list(argv))


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point.

    The CLI has no way to inject an agent generator (that path calls
    :func:`mutation_kill_loop.run_for_file` directly). So without
    ``--headless`` there is no generator, and we fail fast **at startup** —
    before resolving config, probing DOTNET_ROOT, running Stryker, or
    touching any file.

    With ``--headless`` the generator shells to ``claude --print``. The Claude
    CLI is preflight-checked *before* any file argument validation, so a
    missing CLI fails cleanly at startup and mutates nothing.
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    args = parse_args(argv)

    if not args.headless:
        sys.stderr.write(f"error: {NO_GENERATOR_MESSAGE}\n")
        return 1

    model = resolve_model(args.model)

    # Preflight the CLI first — a missing CLI must fail before we touch any
    # file or validate run arguments.
    if not claude_cli_available():
        sys.stderr.write(f"error: {MISSING_CLAUDE_MESSAGE}\n")
        return 3

    if not (args.file and args.test_file and args.source_path):
        sys.stderr.write(
            "error: --headless requires --file, --test-file, and --source-path\n"
        )
        return 2

    try:
        run_for_file(
            args.file,
            RunContext(
                config=load_loop_config(Path(args.config)),
                test_file=Path(args.test_file),
                source_path=Path(args.source_path),
                output_dir=Path(args.output),
                stryker_bin=args.stryker_bin,
                initial_report_path=Path(args.report) if args.report else None,
                generator_label=f"headless ({model or 'default'})",
            ),
            generate=make_headless_generator(model),
            max_rounds=args.max_rounds,
        )
    except RuntimeError as exc:
        # A failed revert or a failed-commit round-abandonment raises
        # RuntimeError (#1598) — without this, that either propagated as a
        # raw traceback or (before the fix) was silently absorbed and this
        # CLI still exited 0. Fits the existing 1/2/3 exit-code taxonomy
        # above with the next unused code.
        sys.stderr.write(f"error: {exc}\n")
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
