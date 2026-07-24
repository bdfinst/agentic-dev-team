#!/usr/bin/env python3
"""mutation_kill_loop_python.py — deterministic survivor-kill loop for
Python/mutmut, the Python counterpart to ``mutation_kill_loop.py`` (#1357).

mutmut has no project/solution structure to load from a config file the way
Stryker.NET does — a scoped run only needs the source file and a test
command, so there is no config-file abstraction here (unlike
``mutation_kill_loop.py``'s ``LoopConfig``/``stryker-config.json``). Scoring
and survivor extraction reuse ``mutation_report``'s mutmut-junitxml support
(#1357); the two generic (non-.NET) headless-generation helpers —
``strip_code_fences``, ``resolve_model``, ``claude_cli_available``,
``CLAUDE_CLI`` — are imported from ``mutation_kill_loop`` rather than
duplicated, since neither depends on anything C#-specific.

**Generation is a seam, not a mechanism** (same contract as the C# loop):
the loop never decides *what* tests to write — a caller supplies a
``generate`` callable that returns the new pytest function text. The
default (interactive) path is agent-driven: the ``mutation-kill`` agent
calls :func:`run_for_file` directly, passing a ``generate`` hook backed by a
live agent turn. A ``--headless`` CLI mode shells to ``claude --print`` for
unattended (CI) runs.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import mutation_kill_loop as _cs_loop
import mutation_report

Generator = Callable[[str, list[dict], str, str], str]

# Mirrors mutation_kill_loop.NO_GENERATOR_MESSAGE — pinned so a contract test
# can assert it verbatim.
NO_GENERATOR_MESSAGE = (
    "no test generator available — invoke via the mutation-kill agent "
    "or pass --headless"
)

# Reused verbatim — neither helper is C#-specific.
strip_code_fences = _cs_loop.strip_code_fences
resolve_model = _cs_loop.resolve_model
claude_cli_available = _cs_loop.claude_cli_available
CLAUDE_CLI = _cs_loop.CLAUDE_CLI

MISSING_CLAUDE_MESSAGE = (
    f"--headless requires the Claude CLI but '{CLAUDE_CLI}' is not available. "
    "Install Claude Code (`npm install -g @anthropic-ai/claude-code`) and "
    "authenticate it (run `claude` once to log in, or set ANTHROPIC_API_KEY) — "
    "or set CLAUDE_BIN to the CLI's path."
)


# =============================================================================
# Scoped mutmut run — mutmut has no native JSON report; junitxml is it.
# =============================================================================
def _mutmut_argv() -> list[str]:
    """Return the argv prefix for invoking mutmut — `mutmut` or `python3 -m mutmut`."""
    if shutil.which("mutmut") is not None:
        return ["mutmut"]
    return [sys.executable, "-m", "mutmut"]


def run_scoped_mutmut(
    source_file: str,
    *,
    test_command: str,
    test_file: Path | None = None,
    cwd: Path | None = None,
) -> str:
    """Run mutmut scoped to one file; return the ``mutmut junitxml`` output.

    Clears any stale ``.mutmut-cache`` first — a cache from a *different*
    scope (a prior run against another file, or a stale run from before this
    file changed) is silently reused otherwise, which was a real trap hit
    manually while dogfooding this loop by hand (#1354): every run must see
    its own fresh baseline, not a leftover one.

    **Always reverts ``source_file`` (and ``test_file``, when given) in a
    ``finally``.** mutmut mutates the real source file on disk for the
    duration of each mutant's test run and restores it when that mutant
    finishes — but an internal mutmut crash (a real, reproducible one: mutmut
    2.5.1's own cache layer raises ``AssertionError``/``ValueError`` on some
    files, confirmed while dogfooding this exact function against
    ``hooks/mutation_adapters/mutmut.py`` — see #1357) skips that restore
    and leaves the mutated content on disk. Unlike Stryker.NET (which
    instruments a separate build, never the real file), mutmut's crash
    failure mode is "corrupt the file under test," so every scoped run must
    unconditionally `git checkout --` it afterward — succeeding, failing, or
    raising.

    The **test file** the ``--runner`` command exercises is exposed to the
    same failure mode — mutmut 2.5.1 has also been observed to truncate the
    runner's test file to empty via a crashed ``.bak``-restore (#1359),
    which silently breaks the *next* round's baseline (mutmut then reports
    zero mutants — a false "converged" positive, not real coverage). Passing
    ``test_file`` reverts it alongside ``source_file`` in the same
    ``finally``; each round's ``git checkout --`` restores exactly the
    state committed at the end of the previous round, which is always the
    correct baseline for the round about to run.
    """
    root = cwd or Path(".")
    (root / ".mutmut-cache").unlink(missing_ok=True)

    prefix = _mutmut_argv()
    argv = [
        *prefix,
        "run",
        f"--paths-to-mutate={source_file}",
        "--runner",
        test_command,
        "--no-progress",
        "--simple-output",
    ]
    try:
        try:
            subprocess.run(argv, cwd=cwd, capture_output=True, text=True)
        except (FileNotFoundError, OSError) as exc:
            raise RuntimeError(f"mutmut run failed to start: {exc}") from exc

        junit = subprocess.run(
            [*prefix, "junitxml"], cwd=cwd, capture_output=True, text=True
        )
        return junit.stdout or ""
    finally:
        git_revert(Path(source_file), cwd=cwd)
        if test_file is not None:
            git_revert(test_file, cwd=cwd)


def extract_survivors(junitxml_text: str, source_file: str) -> list[dict]:
    """Return the surviving mutants for one source file (flattened).

    Delegates parsing to :func:`mutation_report.survivors_from_mutmut_junitxml`
    — mutmut names no per-mutation operator, so every survivor's
    ``mutatorName`` is the fixed literal ``"mutmut"`` (a single group).
    """
    grouped = mutation_report.survivors_from_mutmut_junitxml(
        junitxml_text, source_file
    )
    return [mutant for mutants in grouped.values() for mutant in mutants]


# =============================================================================
# Insert mechanics — detect-or-refuse, never a silent mis-insertion.
# =============================================================================
class InsertionRefused(Exception):
    """Raised when the file isn't in the flat top-level ``def test_*():``
    shape this heuristic supports.

    Unlike the C# loop's "find the class-closing brace" problem, a flat
    pytest module has no enclosing structure to locate — the safe insertion
    point is simply end-of-file, PROVIDED the file already follows that flat
    convention. A file with no top-level ``def test_`` function at all (e.g.
    tests organized as ``class Test...:`` methods) doesn't match this
    convention, and the loop refuses rather than guess.
    """


@dataclass(frozen=True)
class InsertOutcome:
    """Result of attempting to apply generated tests. ``inserted`` is False
    when the file was left untouched; ``reason`` says why."""

    inserted: bool
    reason: str


# A top-level (unindented) pytest test function declaration, capturing the name.
_FUNC_RE = re.compile(r"^def\s+(test_\w+)\s*\(", re.MULTILINE)


def detect_duplicate_functions(test_text: str, new_text: str) -> list[str]:
    """Return the function names in ``new_text`` that already exist in the file."""
    existing = set(_FUNC_RE.findall(test_text))
    incoming = _FUNC_RE.findall(new_text)
    return [name for name in incoming if name in existing]


def append_at_end_of_file(test_file: Path, new_tests: str) -> None:
    """Append ``new_tests`` to the end of the file, with one blank line of
    separation, and a trailing newline.

    Raises :class:`InsertionRefused` when the file has no existing top-level
    ``def test_*():`` — the flat-module convention this heuristic supports.
    The file is left untouched on refusal.
    """
    text = test_file.read_text(encoding="utf-8")
    if not _FUNC_RE.search(text):
        raise InsertionRefused(
            f"refusing to insert into {test_file.name}: no top-level "
            "`def test_*():` found — this heuristic supports only the flat "
            "module convention (a class-based test file needs a different "
            "insertion point, not appended at end-of-file)"
        )

    body = new_tests.strip()
    separator = "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
    test_file.write_text(text + separator + body + "\n", encoding="utf-8")


def apply_generated_tests(test_file: Path, new_tests: str) -> InsertOutcome:
    """Insert generated tests, guarding duplicates and unsafe structure.

    Returns an :class:`InsertOutcome`; the file is only ever written on the
    ``inserted=True`` path. Empty generation, duplicate function names, and
    a refused insert all leave the file untouched.
    """
    if not new_tests.strip():
        return InsertOutcome(False, "no tests generated")

    dupes = detect_duplicate_functions(test_file.read_text(encoding="utf-8"), new_tests)
    if dupes:
        return InsertOutcome(False, f"duplicate function names: {dupes}")

    try:
        append_at_end_of_file(test_file, new_tests)
    except InsertionRefused as exc:
        return InsertOutcome(False, str(exc))
    return InsertOutcome(True, "inserted")


# =============================================================================
# Verify / commit / revert.
# =============================================================================
def python_compiles(test_file: Path, *, cwd: Path | None = None) -> bool:
    """Syntax-check the test file — Python's equivalent of a build step."""
    rc = subprocess.run(
        [sys.executable, "-m", "py_compile", str(test_file)],
        capture_output=True,
        text=True,
        cwd=cwd,
    ).returncode
    return rc == 0


def run_scoped_pytest(test_file: Path, *, cwd: Path | None = None) -> bool:
    """Run the test file under pytest. False on any non-zero exit."""
    rc = subprocess.run(
        [sys.executable, "-m", "pytest", str(test_file), "-q"],
        capture_output=True,
        text=True,
        cwd=cwd,
    ).returncode
    return rc == 0


def git_revert(test_file: Path, *, cwd: Path | None = None) -> None:
    """Discard working-tree changes to one file (``git checkout -- <file>``)."""
    subprocess.run(["git", "checkout", "--", str(test_file)], cwd=cwd)


def git_commit(message: str, test_file: Path, *, cwd: Path | None = None) -> bool:
    """Stage and commit only ``test_file``. Returns True on a successful commit."""
    subprocess.run(["git", "add", str(test_file)], cwd=cwd)
    rc = subprocess.run(
        ["git", "commit", "-m", message],
        capture_output=True,
        text=True,
        cwd=cwd,
    ).returncode
    return rc == 0


def _commit_message(round_num: int, source_file: str, survivors: int, new_tests: str) -> str:
    count = len(_FUNC_RE.findall(new_tests))
    return (
        f"test(mutation): kill round {round_num} — {source_file}\n\n"
        f"{count} new test(s) targeting {survivors} surviving mutant(s)"
    )


# =============================================================================
# Per-file loop — run → score → check → generate → insert → verify → commit.
# =============================================================================
def run_for_file(
    source_file: str,
    *,
    test_file: Path,
    source_path: Path,
    test_command: str,
    generate: Generator,
    max_rounds: int = 5,
    initial_junitxml: str | None = None,
    cwd: Path | None = None,
    log: Callable[[str], None] = print,
) -> None:
    """Drive the deterministic survivor-kill loop for one Python source file.

    ``generate`` is the sole non-deterministic step: given survivors +
    context it returns the raw new-test text. Everything else — scoped run,
    scoring, duplicate/insert guards, compile/test verification,
    revert-on-failure, commit-on-green, and the no-improvement stop — is
    mechanical, mirroring :func:`mutation_kill_loop.run_for_file`'s contract.
    """
    prev_survivors: int | None = None

    for round_num in range(1, max_rounds + 1):
        if initial_junitxml is not None and round_num == 1:
            junitxml_text = initial_junitxml
        else:
            junitxml_text = run_scoped_mutmut(
                source_file, test_command=test_command, test_file=test_file, cwd=cwd
            )

        survivors = extract_survivors(junitxml_text, source_file)
        survivor_count = len(survivors)
        summary = mutation_report.score_mutmut_junitxml(junitxml_text)
        log(
            f"  round {round_num}: honest={summary.honest_score:.1f}% "
            f"survivors={survivor_count}"
        )

        total_mutants = (
            summary.killed + summary.survived + summary.timeout + summary.no_coverage
        )
        if total_mutants == 0:
            log(
                "  zero mutants generated — this is NOT convergence. mutmut "
                "produced no results at all (a real internal crash — e.g. "
                "the known Python 3.13+ pickle incompatibility, 'TypeError: "
                "cannot pickle itertools.count object' — or a file with no "
                "executable statements). Stopping without declaring "
                "survivors == 0 (#1359)."
            )
            return
        if survivor_count == 0:
            log("  no survivors — done")
            return
        if prev_survivors is not None and survivor_count >= prev_survivors:
            log("  no improvement this round — stopping")
            return
        prev_survivors = survivor_count

        new_tests = generate(
            source_file,
            survivors,
            source_path.read_text(encoding="utf-8"),
            test_file.read_text(encoding="utf-8"),
        )

        outcome = apply_generated_tests(test_file, new_tests)
        if not outcome.inserted:
            log(f"  not inserted ({outcome.reason}) — stopping")
            return

        if not python_compiles(test_file, cwd=cwd):
            log("  compile check failed — reverting")
            git_revert(test_file, cwd=cwd)
            return
        if not run_scoped_pytest(test_file, cwd=cwd):
            log("  tests failed — reverting")
            git_revert(test_file, cwd=cwd)
            return

        log("  green — committing")
        git_commit(
            _commit_message(round_num, source_file, survivor_count, new_tests),
            test_file,
            cwd=cwd,
        )


# =============================================================================
# Headless generation — shell to `claude --print` for unattended runs.
# =============================================================================
def build_survivor_summary(survivors: list[dict], *, limit: int = 40) -> str:
    """Render surviving mutants as a compact list."""
    lines = []
    for mutant in survivors[:limit]:
        line = mutant.get("location", {}).get("start", {}).get("line", "?")
        lines.append(f"- L{line}")
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

    The existing test file is the *only* pattern — assertion style and
    fixture usage are inferred from it, never hardcoded here (mirrors
    ``mutation_kill_loop.build_generation_prompt``, adapted for pytest's flat
    ``def test_*():`` convention rather than a class/namespace-wrapped one).
    """
    return (
        f"You are adding new pytest test functions that KILL surviving "
        f"mutations in {source_file}.\n\n"
        "Match the existing test file exactly: its imports, assertion style "
        "(plain `assert`, pytest.approx, monkeypatch, etc.), fixtures, and "
        "naming conventions are the pattern to follow. Do not introduce any "
        "library, helper, or convention that does not already appear in it.\n\n"
        f"## Surviving mutations ({len(survivors)})\n"
        f"{build_survivor_summary(survivors)}\n\n"
        f"## Source under test\n{source_text[:source_limit]}\n\n"
        f"## Existing test file (the pattern to match)\n{test_text}\n\n"
        "## Rules\n"
        "1. Return ONLY the new top-level `def test_*():` function(s) — no "
        "class wrapper, no imports, no module-level fixtures.\n"
        "2. Each must run against the helpers/fixtures already in the "
        "existing test file.\n"
        "3. Reuse the existing file's assertion and fixture patterns exactly.\n"
        "4. Match the existing naming convention.\n"
        "5. Do not redeclare fixtures or helpers already present.\n"
        "6. Every assertion must check a specific value — not just that a "
        "call didn't raise.\n"
    )


def make_headless_generator(
    model: str | None = None, *, cwd: Path | None = None
) -> Generator:
    """Return a :data:`Generator` that shells to ``claude --print``.

    Identical contract to ``mutation_kill_loop.make_headless_generator``, but
    with the Python-flavored prompt above.
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
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
        if result.returncode != 0:
            raise RuntimeError(
                f"claude CLI failed (exit {result.returncode}): {result.stderr[:500]}"
            )
        return strip_code_fences(result.stdout)

    return generate


# =============================================================================
# CLI — startup preflight + --headless generation.
# =============================================================================
def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="mutation_kill_loop_python.py",
        description=(
            "Deterministic survivor-kill loop for Python/mutmut. Agent-driven "
            "by default; --headless enables unattended generation via the "
            "Claude CLI."
        ),
    )
    p.add_argument("--file", required=False, help="Source file to target")
    p.add_argument(
        "--test-command",
        default=None,
        help="Scoped pytest command mutmut runs per mutant (required)",
    )
    p.add_argument("--max-rounds", type=int, default=5, help="Max rounds per file")
    p.add_argument(
        "--headless",
        action="store_true",
        help="Unattended generation via `claude --print` (CI runs).",
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
    return p.parse_args(list(argv))


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point — see :func:`mutation_kill_loop.main` for the contract
    this mirrors."""
    argv = list(sys.argv[1:] if argv is None else argv)
    args = parse_args(argv)

    if not args.headless:
        sys.stderr.write(f"error: {NO_GENERATOR_MESSAGE}\n")
        return 1

    model = resolve_model(args.model)

    if not claude_cli_available():
        sys.stderr.write(f"error: {MISSING_CLAUDE_MESSAGE}\n")
        return 3

    if not (args.file and args.test_file and args.source_path and args.test_command):
        sys.stderr.write(
            "error: --headless requires --file, --test-file, --source-path, "
            "and --test-command\n"
        )
        return 2

    run_for_file(
        args.file,
        test_file=Path(args.test_file),
        source_path=Path(args.source_path),
        test_command=args.test_command,
        generate=make_headless_generator(model),
        max_rounds=args.max_rounds,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
