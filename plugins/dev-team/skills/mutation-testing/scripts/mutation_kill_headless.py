#!/usr/bin/env python3
"""mutation_kill_headless.py — unattended generation via `claude --print` + CLI.

Extracted from ``mutation_kill_loop.py`` (#1562): headless generation (prompt
building, fence stripping, shelling to the Claude CLI) and the script's CLI
argument parsing / entry point are one responsibility cluster — a change to
the Claude prompt wording and a change to a ``--headless`` CLI flag are two
unrelated reasons to touch this file, but neither has anything to do with the
scoped-Stryker-run or insertion mechanics that live in the sibling modules.

This module is the executable entry point (``python3 mutation_kill_headless.py
--headless ...``) invoked by ``stryker_shard_pipeline.py``'s forced-headless
per-shard survivor-fix loop; the agent-driven default path still calls
:func:`mutation_kill_loop.run_for_file` directly with its own ``generate`` hook
and never touches this file.

Generic, stdlib-only, cross-platform (macOS, Linux, Windows).
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import mutation_kill_loop as loop

# The exact message the bare-CLI startup preflight prints. Pinned so the
# contract test can assert it verbatim.
NO_GENERATOR_MESSAGE = (
    "no test generator available — invoke via the mutation-kill agent "
    "or pass --headless"
)

# The Claude CLI binary. Overridable via CLAUDE_BIN so a non-PATH install can
# be pointed at without editing this module.
CLAUDE_CLI = os.environ.get("CLAUDE_BIN", "claude")

# Printed when --headless is requested but the Claude CLI can't be reached.
# Names exactly how to install and authenticate it, and mutates no files.
MISSING_CLAUDE_MESSAGE = (
    f"--headless requires the Claude CLI but '{CLAUDE_CLI}' is not available. "
    "Install Claude Code (`npm install -g @anthropic-ai/claude-code`) and "
    "authenticate it (run `claude` once to log in, or set ANTHROPIC_API_KEY) — "
    "or set CLAUDE_BIN to the CLI's path."
)


# =============================================================================
# Headless generation — shell to `claude --print` for unattended runs.
# =============================================================================
def resolve_model(explicit: str | None = None) -> str | None:
    """Resolve the generation model: ``--model`` > ``DEV_TEAM_MUTATION_MODEL``
    > ``None``. When ``None``, ``--model`` is omitted from the ``claude --print``
    invocation and the Claude CLI uses its own default — the plugin never pins a
    model snapshot id in source (models are resolved dynamically, not literalized;
    cf. ADR 0008 and the no-pinned-snapshots guard)."""
    if explicit:
        return explicit
    return os.environ.get("DEV_TEAM_MUTATION_MODEL") or None


_FENCE_OPEN_RE = re.compile(r"^```[\w-]*\n?")
_FENCE_CLOSE_RE = re.compile(r"\n?```$")


def strip_code_fences(text: str) -> str:
    """Strip one leading and one trailing markdown code fence, if present.

    Claude may wrap generated methods in a ```` ```csharp ```` block; the loop
    inserts raw method text, so the fence is removed on both ends.
    """
    text = _FENCE_OPEN_RE.sub("", text.strip())
    text = _FENCE_CLOSE_RE.sub("", text.strip())
    return text.strip()


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


def claude_cli_available() -> bool:
    """True if the Claude CLI responds to ``--version``."""
    try:
        result = subprocess.run(
            [CLAUDE_CLI, "--version"], capture_output=True, text=True, check=False
        )
    except (FileNotFoundError, OSError):
        return False
    return result.returncode == 0


def make_headless_generator(
    model: str | None = None, *, cwd: Path | None = None
) -> loop.Generator:
    """Return a :data:`loop.Generator` that shells to ``claude --print``.

    The returned callable builds the prompt from the existing test file (the
    pattern) plus the survivor summary, invokes the Claude CLI, and strips
    markdown code fences from the result before it is inserted. ``--model`` is
    passed only when ``model`` is set; when ``None`` the Claude CLI uses its own
    default (the plugin pins no model snapshot id).
    """

    def generate(
        source_file: str,
        survivors: list[dict],
        source_text: str,
        test_text: str,
    ) -> str:
        prompt = build_generation_prompt(source_file, survivors, source_text, test_text)
        cmd = [CLAUDE_CLI, "--print"]
        if model:
            cmd += ["--model", model]
        cmd.append(prompt)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"claude CLI failed (exit {result.returncode}): {result.stderr[:500]}"
            )
        return strip_code_fences(result.stdout)

    return generate


# =============================================================================
# CLI — startup preflight (Slice 2) + --headless generation (Slice 3).
# =============================================================================
def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="mutation_kill_headless.py",
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
    ``mutation_kill_loop.run_for_file`` directly). So without ``--headless``
    there is no generator, and we fail fast **at startup** — before resolving
    config, probing DOTNET_ROOT, running Stryker, or touching any file.

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

    loop.run_for_file(
        args.file,
        config=loop.load_loop_config(Path(args.config)),
        test_file=Path(args.test_file),
        source_path=Path(args.source_path),
        output_dir=Path(args.output),
        generate=make_headless_generator(model),
        max_rounds=args.max_rounds,
        initial_report_path=Path(args.report) if args.report else None,
        stryker_bin=args.stryker_bin,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
