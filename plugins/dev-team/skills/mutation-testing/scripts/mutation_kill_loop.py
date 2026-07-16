#!/usr/bin/env python3
"""mutation_kill_loop.py — config-driven, deterministic survivor-kill loop.

Migrated from the ACI ``nextgen-test-upgrade-process`` mutation agent and
de-hardcoded: nothing repo-specific lives here. Project / test-project /
mutate targets come from ``stryker-config.json``; ``DOTNET_ROOT`` resolution
and ``.sln`` hide/restore reuse the shipped ``csharp_stryker_net_wrapper``;
scoring and survivor extraction reuse ``mutation_report``.

Generic, stdlib-only, cross-platform (macOS, Linux, Windows). The only
non-stdlib imports are the two sibling plugin modules in this same
``scripts/`` directory.

**Generation is a seam, not a mechanism.** The loop never decides *what*
tests to write — a caller supplies a ``generate`` callable that returns the
new test-method text. The default (interactive) path is agent-driven: the
``mutation-kill`` agent calls :func:`run_for_file` directly, passing a
``generate`` hook backed by a live agent turn. A ``--headless`` CLI mode
shells to ``claude --print`` for unattended (CI / shard-pipeline) runs.
Invoking the CLI with neither an injected generator nor ``--headless`` fails
fast at startup — before any Stryker run or file mutation.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Sequence

import csharp_stryker_net_wrapper as wrapper
import mutation_report

# A generator is any callable the agent (or, in Slice 3, the headless CLI)
# supplies: given the source filename, the surviving mutants, the source
# text, and the current test text, it returns the raw text of new test
# methods to insert. The loop owns everything *around* this call; the
# callable owns the single genuinely-LLM step.
Generator = Callable[[str, List[dict], str, str], str]

# The exact message the bare-CLI startup preflight prints. Pinned so the
# contract test can assert it verbatim.
NO_GENERATOR_MESSAGE = (
    "no test generator available — invoke via the mutation-kill agent "
    "or pass --headless"
)

# The Claude CLI binary. Overridable via CLAUDE_BIN so a non-PATH install can
# be pointed at without editing this module.
CLAUDE_CLI = os.environ.get("CLAUDE_BIN", "claude")

# Pinned default generation model for --headless. Resolution order (see
# :func:`resolve_model`): ``--model`` flag > ``DEV_TEAM_MUTATION_MODEL`` env
# var > this constant. Never an unstated literal — the effective model is
# always inspectable.
DEFAULT_MODEL = "claude-opus-4-8"

# Printed when --headless is requested but the Claude CLI can't be reached.
# Names exactly how to install and authenticate it, and mutates no files.
MISSING_CLAUDE_MESSAGE = (
    f"--headless requires the Claude CLI but '{CLAUDE_CLI}' is not available. "
    "Install Claude Code (`npm install -g @anthropic-ai/claude-code`) and "
    "authenticate it (run `claude` once to log in, or set ANTHROPIC_API_KEY) — "
    "or set CLAUDE_BIN to the CLI's path."
)


# =============================================================================
# Config — everything path-shaped comes from stryker-config.json.
# =============================================================================
@dataclass(frozen=True)
class LoopConfig:
    """The subset of a ``stryker-config.json`` the loop needs.

    ``project`` is the mutated project (optional — Stryker infers it from the
    solution when omitted). ``test_projects`` drives every ``dotnet build`` and
    ``dotnet test`` target — never a hardcoded path. ``solution`` is the main
    ``.sln`` hidden during a scoped run.
    """

    project: Optional[str]
    test_projects: List[str]
    mutate: List[str]
    solution: Optional[str]


def load_loop_config(config_path: Path) -> LoopConfig:
    """Parse ``stryker-config.json``, tolerating the wrapper shape.

    Stryker configs may nest everything under a top-level ``"stryker-config"``
    key (the shape the ACI configs use) or place the keys at the top level.
    Both are accepted.
    """
    raw = json.loads(Path(config_path).read_text(encoding="utf-8"))
    inner = raw.get("stryker-config", raw)
    return LoopConfig(
        project=inner.get("project"),
        test_projects=list(inner.get("test-projects", [])),
        mutate=list(inner.get("mutate", [])),
        solution=inner.get("solution"),
    )


def dotnet_build_targets(config: LoopConfig) -> List[str]:
    """Build targets are exactly the configured test-projects."""
    return list(config.test_projects)


def dotnet_test_targets(config: LoopConfig) -> List[str]:
    """Test targets are exactly the configured test-projects."""
    return list(config.test_projects)


# =============================================================================
# Scoped Stryker run — goes THROUGH the wrapper (AC4).
# =============================================================================
def make_scoped_config(config: LoopConfig, source_file: str) -> dict:
    """Build a Stryker config scoped to a single source file.

    Carries the configured solution / project / test-projects forward and
    narrows ``mutate`` to just the target file with per-test coverage for fast
    feedback. Keys whose configured value is ``None`` are dropped so Stryker
    infers them.
    """
    scoped = {
        "solution": config.solution,
        "project": config.project,
        "test-projects": config.test_projects,
        "mutate": [f"**/{source_file}"],
        "coverage-analysis": "perTest",
        "reporters": ["json"],
    }
    scoped = {k: v for k, v in scoped.items() if v is not None}
    return {"stryker-config": scoped}


def _write_scoped_config(config: LoopConfig, source_file: str) -> Path:
    tmp = tempfile.NamedTemporaryFile(
        suffix=".json", delete=False, mode="w", prefix="stryker-scoped-"
    )
    json.dump(make_scoped_config(config, source_file), tmp)
    tmp.close()
    return Path(tmp.name)


def run_scoped_stryker(
    config: LoopConfig,
    source_file: str,
    *,
    output_dir: Path,
    stryker_bin: str = "dotnet-stryker",
    cwd: Optional[Path] = None,
) -> Path:
    """Run Stryker scoped to one file; return the report path.

    DOTNET_ROOT resolution and ``.sln`` hide/restore are delegated to
    ``csharp_stryker_net_wrapper`` — this function never re-implements either
    (AC4). The ``.sln`` is hidden for the duration of the run and restored on
    every exit path via ``finally``.
    """
    dotnet_root, err = wrapper.resolve_dotnet_root(
        preset=os.environ.get("DOTNET_ROOT"),
        candidates=wrapper.default_probe_candidates(),
    )
    if err is not None:
        raise RuntimeError(err)
    assert dotnet_root is not None
    env = {**os.environ, "DOTNET_ROOT": dotnet_root}

    config_path = _write_scoped_config(config, source_file)
    sln = Path(config.solution) if config.solution else None
    sln_hidden = Path(f"{config.solution}.stryker-hidden") if config.solution else None
    try:
        if sln is not None and sln_hidden is not None:
            wrapper.hide_sln(sln, sln_hidden)
        subprocess.run(
            [
                stryker_bin,
                "--config-file",
                str(config_path),
                "--output",
                str(output_dir),
            ],
            env=env,
            cwd=cwd,
        )
    finally:
        if sln is not None and sln_hidden is not None:
            wrapper.restore_sln(sln, sln_hidden)
        config_path.unlink(missing_ok=True)

    return Path(output_dir) / "reports" / "mutation-report.json"


def extract_survivors(report_path: Path, source_file: str) -> List[dict]:
    """Return the surviving mutants for one source file (flattened).

    Delegates grouping/extraction to :func:`mutation_report.survivors_by_mutator`.
    """
    grouped = mutation_report.survivors_by_mutator(report_path, source_file)
    return [mutant for mutants in grouped.values() for mutant in mutants]


# =============================================================================
# Insert mechanics — detect-or-refuse, never a silent mis-insertion.
# =============================================================================
class InsertionRefused(Exception):
    """Raised when the class-closing brace can't be located safely.

    The insert heuristic only supports conventional block-namespace,
    4-space-indented C# test classes. For a file-scoped namespace (no wrapping
    braces) or non-4-space indentation, the loop refuses rather than append
    into a structurally wrong location.
    """


@dataclass(frozen=True)
class InsertOutcome:
    """Result of attempting to apply generated methods. ``inserted`` is False
    when the file was left untouched; ``reason`` says why."""

    inserted: bool
    reason: str


# Matches a public test-method declaration (async Task or void), capturing the
# method name. Framework-agnostic — no attribute or library name is assumed.
_METHOD_RE = re.compile(
    r"public\s+(?:async\s+)?(?:void|Task(?:<[^>]*>)?)\s+(\w+)\s*\("
)

# A file-scoped namespace declaration ends with a semicolon and has no
# wrapping braces: ``namespace Foo.Bar;``
_FILE_SCOPED_NS_RE = re.compile(r"^\s*namespace\s+[\w.]+\s*;", re.MULTILINE)


def detect_duplicate_methods(test_text: str, new_text: str) -> List[str]:
    """Return the method names in ``new_text`` that already exist in the file."""
    existing = set(_METHOD_RE.findall(test_text))
    incoming = _METHOD_RE.findall(new_text)
    return [name for name in incoming if name in existing]


def _find_block_namespace_class_close(lines: Sequence[str]) -> Optional[int]:
    """Return the index of the class-closing brace, or None to refuse.

    Walks from the end: finds the namespace-closing brace (a line whose
    stripped form is ``}``), then the last line that is exactly four spaces
    followed by ``}`` before it — the conventional block-namespace class
    close. Any other indentation yields None (refuse).
    """
    ns_idx = None
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip() == "}":
            ns_idx = i
            break
    if ns_idx is None:
        return None
    for i in range(ns_idx - 1, -1, -1):
        if lines[i].rstrip("\r\n") == "    }":
            return i
    return None


def insert_before_class_close(test_file: Path, new_methods: str) -> None:
    """Insert ``new_methods`` before the test class's closing brace.

    Raises :class:`InsertionRefused` for a file-scoped namespace or any
    non-4-space-indented class the heuristic can't safely locate. The file is
    left untouched on refusal.
    """
    text = test_file.read_text(encoding="utf-8")
    if _FILE_SCOPED_NS_RE.search(text):
        raise InsertionRefused(
            f"refusing to insert into {test_file.name}: file-scoped namespace "
            "detected — the class-close heuristic supports only block-namespace, "
            "4-space-indented classes"
        )

    lines = text.splitlines(keepends=True)
    cc_idx = _find_block_namespace_class_close(lines)
    if cc_idx is None:
        raise InsertionRefused(
            f"refusing to insert into {test_file.name}: could not locate a "
            "conventional 4-space class-closing brace (non-standard indentation?)"
        )

    block = (
        ["\n"]
        + [l if l.endswith("\n") else l + "\n" for l in new_methods.strip().splitlines()]
        + ["\n"]
    )
    lines = lines[:cc_idx] + block + lines[cc_idx:]
    test_file.write_text("".join(lines), encoding="utf-8")


def apply_generated_methods(test_file: Path, new_methods: str) -> InsertOutcome:
    """Insert generated methods, guarding duplicates and unsafe structure.

    Returns an :class:`InsertOutcome`; the file is only ever written on the
    ``inserted=True`` path. Empty generation, duplicate method names, and a
    refused insert all leave the file untouched.
    """
    if not new_methods.strip():
        return InsertOutcome(False, "no methods generated")

    dupes = detect_duplicate_methods(test_file.read_text(encoding="utf-8"), new_methods)
    if dupes:
        return InsertOutcome(False, f"duplicate method names: {dupes}")

    try:
        insert_before_class_close(test_file, new_methods)
    except InsertionRefused as exc:
        return InsertOutcome(False, str(exc))
    return InsertOutcome(True, "inserted")


# =============================================================================
# Verify / commit / revert — all dotnet & git go through subprocess.
# =============================================================================
def dotnet_build(targets: Sequence[str], *, cwd: Optional[Path] = None) -> bool:
    """Build every configured test-project. False if any target fails."""
    for target in targets:
        rc = subprocess.run(
            ["dotnet", "build", target, "-c", "Debug", "--nologo"],
            capture_output=True,
            text=True,
            cwd=cwd,
        ).returncode
        if rc != 0:
            return False
    return True


def dotnet_test(
    targets: Sequence[str], test_filter: str, *, cwd: Optional[Path] = None
) -> bool:
    """Run the scoped test filter across every test-project. False on any
    non-zero exit or reported failure."""
    for target in targets:
        result = subprocess.run(
            [
                "dotnet",
                "test",
                target,
                "-c",
                "Debug",
                "--no-build",
                "--filter",
                f"FullyQualifiedName~{test_filter}",
            ],
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        failed = 0
        for line in (result.stdout + result.stderr).splitlines():
            match = re.search(r"Failed:\s*(\d+)", line)
            if match:
                failed = int(match.group(1))
        if result.returncode != 0 or failed > 0:
            return False
    return True


def git_revert(test_file: Path, *, cwd: Optional[Path] = None) -> None:
    """Discard working-tree changes to one file (``git checkout -- <file>``)."""
    subprocess.run(["git", "checkout", "--", str(test_file)], cwd=cwd)


def git_commit(message: str, test_file: Path, *, cwd: Optional[Path] = None) -> bool:
    """Stage and commit only ``test_file``. Returns True on a successful commit."""
    subprocess.run(["git", "add", str(test_file)], cwd=cwd)
    rc = subprocess.run(
        ["git", "commit", "-m", message],
        capture_output=True,
        text=True,
        cwd=cwd,
    ).returncode
    return rc == 0


def _commit_message(round_num: int, source_file: str, survivors: int, new_methods: str) -> str:
    count = len(_METHOD_RE.findall(new_methods))
    return (
        f"test(mutation): kill round {round_num} — {source_file}\n\n"
        f"{count} new test method(s) targeting {survivors} surviving mutant(s)"
    )


# =============================================================================
# Per-file loop — run → score → check → generate → insert → verify → commit.
# =============================================================================
def run_for_file(
    source_file: str,
    *,
    config: LoopConfig,
    test_file: Path,
    source_path: Path,
    output_dir: Path,
    generate: Generator,
    max_rounds: int = 5,
    initial_report_path: Optional[Path] = None,
    stryker_bin: str = "dotnet-stryker",
    cwd: Optional[Path] = None,
    log: Callable[[str], None] = print,
) -> None:
    """Drive the deterministic survivor-kill loop for one source file.

    ``generate`` is the sole non-deterministic step: given survivors + context
    it returns the raw new-method text. Everything else — scoped run, scoring,
    duplicate/insert guards, build/test verification, revert-on-failure,
    commit-on-green, and the no-improvement stop — is mechanical.
    """
    prev_survivors: Optional[int] = None

    for round_num in range(1, max_rounds + 1):
        if initial_report_path is not None and round_num == 1:
            report_path = Path(initial_report_path)
        else:
            report_path = run_scoped_stryker(
                config,
                source_file,
                output_dir=output_dir,
                stryker_bin=stryker_bin,
                cwd=cwd,
            )

        survivors = extract_survivors(report_path, source_file)
        survivor_count = len(survivors)
        summary = mutation_report.score_report(report_path)
        log(
            f"  round {round_num}: honest={summary.honest_score:.1f}% "
            f"survivors={survivor_count}"
        )

        if survivor_count == 0:
            log("  no survivors — done")
            return
        if prev_survivors is not None and survivor_count >= prev_survivors:
            log("  no improvement this round — stopping")
            return
        prev_survivors = survivor_count

        new_methods = generate(
            source_file,
            survivors,
            source_path.read_text(encoding="utf-8"),
            test_file.read_text(encoding="utf-8"),
        )

        outcome = apply_generated_methods(test_file, new_methods)
        if not outcome.inserted:
            log(f"  not inserted ({outcome.reason}) — stopping")
            return

        if not dotnet_build(dotnet_build_targets(config), cwd=cwd):
            log("  build failed — reverting")
            git_revert(test_file, cwd=cwd)
            return
        if not dotnet_test(dotnet_test_targets(config), test_file.stem, cwd=cwd):
            log("  tests failed — reverting")
            git_revert(test_file, cwd=cwd)
            return

        log("  green — committing")
        git_commit(
            _commit_message(round_num, source_file, survivor_count, new_methods),
            test_file,
            cwd=cwd,
        )


# =============================================================================
# Headless generation — shell to `claude --print` for unattended runs.
# =============================================================================
def resolve_model(explicit: Optional[str] = None) -> str:
    """Resolve the generation model: ``--model`` > ``DEV_TEAM_MUTATION_MODEL``
    > the pinned :data:`DEFAULT_MODEL`. Never an unstated literal."""
    if explicit:
        return explicit
    return os.environ.get("DEV_TEAM_MUTATION_MODEL") or DEFAULT_MODEL


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


def build_survivor_summary(survivors: List[dict], *, limit: int = 40) -> str:
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
    survivors: List[dict],
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
            [CLAUDE_CLI, "--version"], capture_output=True, text=True
        )
    except (FileNotFoundError, OSError):
        return False
    return result.returncode == 0


def make_headless_generator(model: str, *, cwd: Optional[Path] = None) -> Generator:
    """Return a :data:`Generator` that shells to ``claude --print --model <model>``.

    The returned callable builds the prompt from the existing test file (the
    pattern) plus the survivor summary, invokes the Claude CLI, and strips
    markdown code fences from the result before it is inserted.
    """

    def generate(
        source_file: str,
        survivors: List[dict],
        source_text: str,
        test_text: str,
    ) -> str:
        prompt = build_generation_prompt(source_file, survivors, source_text, test_text)
        result = subprocess.run(
            [CLAUDE_CLI, "--print", "--model", model, prompt],
            capture_output=True,
            text=True,
            cwd=cwd,
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
            "env var, else the pinned DEFAULT_MODEL."
        ),
    )
    p.add_argument("--test-file", help="Test file to extend (required with --headless)")
    p.add_argument("--source-path", help="Source file under test (required with --headless)")
    p.add_argument("--report", help="Initial mutation report to seed round 1 (--headless)")
    return p.parse_args(list(argv))


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry point.

    The CLI has no way to inject an agent generator (that path calls
    :func:`run_for_file` directly). So without ``--headless`` there is no
    generator, and we fail fast **at startup** — before resolving config,
    probing DOTNET_ROOT, running Stryker, or touching any file.

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

    run_for_file(
        args.file,
        config=load_loop_config(Path(args.config)),
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
