#!/usr/bin/env python3
"""Integration eval tier runner (issue #313).

Unit evals ask "did the reviewer flag the right thing?". The integration tier
asks the validation question: does a plan from our orchestrator yield code that
actually compiles and whose tests pass? For each integration fixture this:

  1. checks prerequisites (git, the #309 grader registry, the #311 cache, and —
     unless --skip-dispatch — the `claude` CLI), failing with a clear error that
     names the missing component;
  2. builds an **ephemeral git worktree** from the fixture's golden-repo tarball;
  3. dispatches the orchestrator against the frozen spec to implement it
     (skipped with --skip-dispatch, e.g. for harness self-tests);
  4. runs each declared test command in the worktree, recording exit code and
     the first line of stderr;
  5. tears the worktree down **unconditionally** (even on error/interrupt);
  6. writes actuals.json in the grader's shape so the deterministic
     `integration` grader (eval_graders/integration.py) can score it.

The runner produces actuals only — grading stays in eval_grade.py, model-free.
This tier is opt-in (run-integration label / force_integration); it is never in
the default PR suite because each run dispatches the orchestrator.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent

# Hard ceiling per declared testCommand so a hung fixture test (deadlock,
# server that never exits) can't block the harness indefinitely. Fixture
# specs are trusted (evals/expected/*.json), but "trusted" isn't "always
# terminates". Override (test-only injection seam) via
# RUN_INTEGRATION_EVAL_CMD_TIMEOUT.
_DEFAULT_CMD_TIMEOUT_SECONDS = 1800.0

# Characters that require real shell interpretation (pipes, chaining,
# redirects, expansion, globs, backticks). A testCommand containing none of
# these is a plain word list and can run directly (no shell hop needed).
_SHELL_METACHARACTERS_RE = re.compile(r"[|&;<>$`*?~]")


def _cmd_timeout_seconds() -> float:
    raw = os.environ.get("RUN_INTEGRATION_EVAL_CMD_TIMEOUT")
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return _DEFAULT_CMD_TIMEOUT_SECONDS


def _fail(msg: str) -> int:
    print(f"error: {msg}", file=sys.stderr)
    return 2


def check_prerequisites(skip_dispatch: bool) -> list[str]:
    """Return a list of missing-prerequisite messages (empty == all present)."""
    missing: list[str] = []
    if shutil.which("git") is None:
        missing.append("git (needed for the ephemeral worktree)")
    registry = SCRIPTS / "eval_graders" / "__init__.py"
    if not registry.exists():
        missing.append(
            "the grader registry scripts/eval_graders/ (#309) — integration is "
            "a registered grader"
        )
    else:
        try:
            sys.path.insert(0, str(SCRIPTS))
            from eval_graders import is_registered  # noqa: E402

            if not is_registered("integration"):
                missing.append("the 'integration' grader in the registry (#309/#313)")
        except ImportError:
            missing.append("an importable grader registry (#309)")
    if not (SCRIPTS / "eval_cache.py").exists():
        missing.append(
            "scripts/eval_cache.py, the fingerprint replay cache (#311) — "
            "without replay every integration run pays full orchestrator cost"
        )
    if not skip_dispatch and shutil.which("claude") is None:
        missing.append(
            "the `claude` CLI (needed to dispatch the orchestrator; pass "
            "--skip-dispatch to run the harness without a model)"
        )
    return missing


def _is_within(dest: Path, target: Path) -> bool:
    """True iff `target` is dest itself or a real descendant of dest.

    Both paths must already be resolved (absolute, symlinks/`..` collapsed).
    Deliberately NOT `str(target).startswith(str(dest))`: that naive
    string-prefix check has no separator boundary, so a sibling directory
    whose name merely starts with dest's name (e.g. dest=".../out", target
    ".../out-evil/pwned.txt") would incorrectly pass — the classic
    zip-slip-guard-bypass pattern. `relative_to` enforces a real path-segment
    containment check.
    """
    try:
        target.relative_to(dest)
        return True
    except ValueError:
        return False


def extract_golden_repo(tarball: Path, dest: Path) -> None:
    """Extract the golden-repo snapshot into dest (created fresh)."""
    dest.mkdir(parents=True, exist_ok=True)
    resolved_dest = dest.resolve()
    with tarfile.open(tarball) as tf:
        # Guard against path traversal in the archive.
        for member in tf.getmembers():
            target = (dest / member.name).resolve()
            if not _is_within(resolved_dest, target):
                raise RuntimeError(f"unsafe path in tarball: {member.name}")
        tf.extractall(dest)  # noqa: S202 - members validated above


def init_worktree(workdir: Path) -> None:
    """Make the extracted snapshot a git worktree (baseline commit)."""
    quiet = {
        "cwd": str(workdir),
        "check": True,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    subprocess.run(["git", "init"], **quiet)
    subprocess.run(["git", "add", "-A"], **quiet)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=eval@dev-team",
            "-c",
            "user.name=eval",
            "commit",
            "-m",
            "golden-repo baseline",
            "--allow-empty",
        ],
        **quiet,
    )


def _tokens_from_claude_json(stdout: str) -> int:
    """Best-effort token-usage extraction from `claude -p --output-format json`.

    The envelope shape has varied across CLI versions; this stays defensive
    (never raises) since token accounting is a reporting nicety, not a
    correctness requirement of the integration tier.
    """
    if not stdout:
        return 0
    try:
        payload = json.loads(stdout)
    except (json.JSONDecodeError, ValueError):
        return 0
    usage = payload.get("usage") if isinstance(payload, dict) else None
    if isinstance(usage, dict):
        total = 0
        for key in ("input_tokens", "output_tokens", "cache_creation_input_tokens",
                    "cache_read_input_tokens"):
            val = usage.get(key)
            if isinstance(val, (int, float)):
                total += int(val)
        if total:
            return total
    for key in ("total_tokens", "tokens"):
        val = payload.get(key) if isinstance(payload, dict) else None
        if isinstance(val, (int, float)):
            return int(val)
    return 0


def _count_issues_caught(workdir: Path) -> int:
    """Sum `issues_found` from a review-value log written inside the worktree.

    `/build`'s inline review checkpoints append one JSON line per checkpoint to
    `metrics/review-value.jsonl` (#348) — this is the same "issues caught at
    review checkpoints" signal the ablation feature (#868) diffs between arms.
    Absent file/malformed lines count as zero rather than erroring: a build
    that never triggers a checkpoint is a legitimate (if uninteresting) result.
    """
    log = workdir / "metrics" / "review-value.jsonl"
    if not log.exists():
        return 0
    total = 0
    for line in log.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        found = entry.get("issues_found")
        if isinstance(found, (int, float)):
            total += int(found)
    return total


def dispatch_orchestrator(
    workdir: Path, spec_path: Path, model: str, ablate_agent: str = ""
) -> int:
    """Dispatch the orchestrator to implement the frozen spec in the worktree.

    When `ablate_agent` is set, `DEV_TEAM_ABLATE_AGENT` is injected into the
    subprocess environment only (never written to disk) so the orchestrator's
    inline review dispatch can exclude that agent for the lifetime of this one
    dispatch (#868 agent-ablation mode). Returns the best-effort token count
    reported by `--output-format json` (0 if unavailable/unparseable).
    """
    prompt = (
        f"Implement the spec in {spec_path.name} using the full plan -> build -> "
        f"review pipeline. The working directory is a fresh git worktree; make "
        f"the declared test commands pass."
    )
    env = os.environ.copy()
    if ablate_agent:
        env["DEV_TEAM_ABLATE_AGENT"] = ablate_agent
    else:
        env.pop("DEV_TEAM_ABLATE_AGENT", None)
    # The orchestrator must edit files and run test/build commands to implement
    # the spec. In headless `claude -p` mode with default permissions those tool
    # calls are denied ("write was denied by permission settings"), so the build
    # silently no-ops and every fixture's testCommands fail. The worktree is
    # ephemeral and torn down unconditionally, so bypass the permission prompts
    # for this dispatch. (#integration-eval-perms)
    proc = subprocess.run(
        ["claude", "-p", prompt, "--model", model, "--output-format", "json",
         "--dangerously-skip-permissions"],
        cwd=str(workdir),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return _tokens_from_claude_json(proc.stdout)


def run_commands(workdir: Path, commands: list[str]) -> list[dict]:
    """Run each command in the worktree; record exit code + stderr first line.

    Bounded by a hard timeout so a hung fixture command can't block the
    harness indefinitely. A command with no shell metacharacters is a plain
    word list and runs directly (list-form, shell=False); a command that
    chains, pipes, redirects, or expands still needs the shell to interpret
    it, so it runs via shell=True as before.
    """
    timeout = _cmd_timeout_seconds()
    results = []
    for cmd in commands:
        use_shell = bool(_SHELL_METACHARACTERS_RE.search(cmd))
        args = cmd if use_shell else shlex.split(cmd)
        try:
            proc = subprocess.run(
                args,
                cwd=str(workdir),
                shell=use_shell,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            stderr_first = ""
            if proc.stderr:
                stderr_first = (
                    proc.stderr.strip().splitlines()[0] if proc.stderr.strip() else ""
                )
            results.append(
                {
                    "command": cmd,
                    "exit_code": proc.returncode,
                    "stderr_first_line": stderr_first,
                }
            )
        except subprocess.TimeoutExpired:
            results.append(
                {
                    "command": cmd,
                    "exit_code": -1,
                    "stderr_first_line": f"command timed out after {timeout:g}s",
                }
            )
    return results


def run_fixture(
    stem: str,
    target: str,
    ispec: dict,
    fixtures_dir: Path,
    skip_dispatch: bool,
    model: str,
    ablate_agent: str = "",
) -> dict:
    """Run one integration target; return its recorded actual.

    Shape: ``{"results": [...], "tokens": N, "issues_caught": N}``. `results`
    is graded by the `integration` grader (unchanged shape); `tokens` and
    `issues_caught` are additive fields the grader ignores but the #868
    agent-ablation delta computation consumes.
    """
    fixture_dir = fixtures_dir / stem
    tarball = fixture_dir / ispec["goldenRepo"]
    spec_path = fixture_dir / ispec["spec"]
    commands = ispec.get("testCommands", [])

    workdir = Path(tempfile.mkdtemp(prefix=f"int-{stem}-"))
    try:
        extract_golden_repo(tarball, workdir)
        init_worktree(workdir)
        tokens = 0
        issues_caught = 0
        if not skip_dispatch:
            # Stage the frozen spec into the worktree so the orchestrator sees it.
            if spec_path.exists():
                shutil.copy2(spec_path, workdir / spec_path.name)
            tokens = dispatch_orchestrator(workdir, spec_path, model, ablate_agent)
            issues_caught = _count_issues_caught(workdir)
        results = run_commands(workdir, commands)
        return {"results": results, "tokens": tokens, "issues_caught": issues_caught}
    finally:
        # Tear the worktree down unconditionally (acceptance: even on failure).
        shutil.rmtree(workdir, ignore_errors=True)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--expected-dir", default="evals/expected")
    ap.add_argument("--fixtures-dir", default="evals/fixtures")
    ap.add_argument("--out", default="actuals.json")
    ap.add_argument(
        "--only", default="", help="comma-separated integration target names to run"
    )
    ap.add_argument("--model", default="claude-sonnet-4-6")
    ap.add_argument(
        "--skip-dispatch",
        action="store_true",
        help="do not dispatch the orchestrator (harness self-test); "
        "test commands run against the golden repo as-is",
    )
    ap.add_argument(
        "--ablate-agent",
        default="",
        help="(#868) exclude this review agent from the orchestrator's inline "
        "review dispatch for this run only, via the DEV_TEAM_ABLATE_AGENT "
        "env var scoped to the dispatch subprocess. Empty (default) runs the "
        "full roster.",
    )
    args = ap.parse_args(argv)

    missing = check_prerequisites(args.skip_dispatch)
    if missing:
        print("error: integration tier prerequisites missing:", file=sys.stderr)
        for m in missing:
            print(f"  - {m}", file=sys.stderr)
        return 2

    expected_dir = Path(args.expected_dir)
    fixtures_dir = Path(args.fixtures_dir)
    if not expected_dir.is_dir():
        return _fail(f"expected dir not found: {expected_dir}")
    only = {s.strip() for s in args.only.split(",") if s.strip()} or None

    actuals: dict = {}
    ran = 0
    for ef in sorted(expected_dir.glob("*.json")):
        try:
            spec = json.loads(ef.read_text())
        except json.JSONDecodeError as exc:
            return _fail(f"{ef.name}: invalid JSON ({exc})")
        integration = spec.get("integration")
        if not integration:
            continue
        stem = ef.stem
        for target, ispec in integration.items():
            if only and target not in only:
                continue
            print(
                f"· integration {stem}::{target} "
                f"({'no-dispatch' if args.skip_dispatch else 'dispatch'})",
                file=sys.stderr,
            )
            actual = run_fixture(
                stem,
                target,
                ispec,
                fixtures_dir,
                args.skip_dispatch,
                args.model,
                args.ablate_agent,
            )
            actuals.setdefault(stem, {}).setdefault("integration", {})[target] = actual
            ran += 1

    Path(args.out).write_text(json.dumps(actuals, indent=2) + "\n")
    print(f"integration runner: {ran} target(s) → {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
