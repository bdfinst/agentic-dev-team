#!/usr/bin/env python3
"""orchestrator.py — Python dispatcher for the dev-team three-phase pipeline.

CLI: python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestrator.py [--resume] [--skip-llm]
     [--memory-dir <path>] [--classify trivial|standard|complex] [--fail-wave]
     [--dispatch-personas]

Flags:
  --resume            Skip phases whose state files already exist in memory-dir.
  --skip-llm          Use stubs for classify() and all LLM dispatch.
  --memory-dir <path> Where to read/write phase state (default: .claude/memory/ relative to CWD).
  --classify <size>   Override classification (trivial|standard|complex). For testing only.
  --fail-wave         Simulate a wave barrier failure (for testing).
  --dispatch-personas Dispatch plan-review personas (for testing).

Exit codes:
  0 = success
  1 = error (no prior state with --resume, wave barrier failure, etc.)
"""

from __future__ import annotations

import argparse
import asyncio
import functools
import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent

# Default personas for plan review — the five plan-review-* critics.
DEFAULT_PERSONAS = [
    "plan-review-acceptance",
    "plan-review-design",
    "plan-review-ux",
    "plan-review-strategic",
    "plan-review-parallelization",
]

# Language-agnostic always-run code-review trio per docs/team-structure.md's
# review-dispatch fan-out. Conditional language-specific reviewers are out
# of scope for this iteration.
CODE_REVIEW_PANEL = ["doc-review", "arch-review", "token-efficiency-review"]

# Personas whose --output-format json envelope's "result" field is itself
# documented structured JSON (per knowledge/review-agent-output-contract.md)
# and should be parsed rather than stored as freeform prose.
JSON_CONTRACT_PERSONAS = DEFAULT_PERSONAS + CODE_REVIEW_PANEL

# Keyword heuristic for the Research phase's security-engineer dispatch
# decision. This tuple is the one normative source in CODE for the keyword
# list — _touches_security() consumes it, it is not duplicated in any other
# .py module. agents/orchestrator.md's Security Engineer dispatch section
# restates the same seven keywords in prose for its own (agent-facing,
# standalone) audience; that restatement is not mechanically bound to this
# tuple today — keep the two in sync by hand until a content-guard test
# exists (see the follow-up tracked against this slice).
SECURITY_KEYWORDS = (
    "auth",
    "secret",
    "crypto",
    "password",
    "token",
    "credential",
    "encrypt",
)

# Research-phase always-on persona roster (see agents/orchestrator.md §
# Phase 1: Research). Named module constant, matching the DEFAULT_PERSONAS/
# CODE_REVIEW_PANEL pattern above, so it has one definition instead of being
# re-typed at each call/test site.
RESEARCH_PERSONAS = ["codebase-recon", "architect", "data-flow-tracer"]

# The conditionally-dispatched fourth Research persona (see _touches_security
# below). Named for the same reason RESEARCH_PERSONAS is: avoid re-typing the
# literal at each call/test site.
SECURITY_ENGINEER_PERSONA = "security-engineer"

# Timeouts (seconds) for the two `claude -p` subprocess dispatch sites below.
# Unverified placeholders, not measured against a real dispatch — see the
# follow-up tracked against this slice.
CLASSIFY_TIMEOUT_S = 30
PERSONA_DISPATCH_TIMEOUT_S = 60


def _touches_security(request: str) -> bool:
    """Return True if request case-insensitively contains a security keyword.

    Heuristic, not a precise classifier: substring matching means false
    positives are expected and accepted (e.g. "cryptocurrency" matches via
    "crypto") per the plan's Risks section.
    """
    lowered = request.lower()
    return any(keyword in lowered for keyword in SECURITY_KEYWORDS)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def phase_state_path(phase: str, memory_dir: Path) -> Path:
    """Return the canonical path for a phase's state file."""
    return memory_dir / f"orchestrator-{phase}.json"


def write_progress(phase: str, result: dict, memory_dir: Path) -> None:
    """Write phase result as JSON to memory_dir/orchestrator-<phase>.json."""
    memory_dir.mkdir(parents=True, exist_ok=True)
    phase_state_path(phase, memory_dir).write_text(json.dumps(result))


def read_progress(phase: str, memory_dir: Path):
    """Return the parsed JSON for phase, or None if no state file exists."""
    path = phase_state_path(phase, memory_dir)
    if path.exists():
        return json.loads(path.read_text())
    return None


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


async def classify(request: str, skip_llm: bool = False) -> dict:
    """Return {size: trivial|standard|complex}. Falls back to standard on failure."""
    if skip_llm:
        return {"size": "standard"}
    try:
        # Offload the blocking call to a thread so an awaiting/gathered caller
        # keeps a free event loop instead of serializing on subprocess.run (#1213).
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            functools.partial(
                subprocess.run,
                [
                    "claude",
                    "-p",
                    (
                        "Classify this task as exactly one of: trivial, standard, or complex. "
                        f"Reply with only one word. Task: {request}"
                    ),
                ],
                capture_output=True,
                text=True,
                timeout=CLASSIFY_TIMEOUT_S,
            ),
        )
        if result.returncode == 0 and result.stdout.strip():
            raw = result.stdout.strip().lower()
            for size in ("trivial", "standard", "complex"):
                if size in raw:
                    return {"size": size}
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        print(
            "WARNING: LLM classify failed; defaulting to full pipeline",
            file=sys.stderr,
        )
    return {"size": "standard"}


# ---------------------------------------------------------------------------
# Research phase
# ---------------------------------------------------------------------------


async def _default_phase_research(request: str, task: dict, skip_llm: bool) -> dict:
    """Dispatch the Research-phase personas and aggregate their results.

    Always dispatches RESEARCH_PERSONAS (codebase-recon, architect,
    data-flow-tracer); additionally dispatches security-engineer when the
    request text touches auth/secrets/crypto per _touches_security(). A
    status: "failed" entry among the dispatched results is recorded
    verbatim — reconcile()/WaveError are scoped to the Implement phase's
    wave loop, not Research.
    """
    # Defensive copy: RESEARCH_PERSONAS is a module-level constant shared
    # across every call/test in this process — appending directly to it
    # would permanently mutate it for every subsequent request.
    personas = list(RESEARCH_PERSONAS)
    if _touches_security(request):
        personas.append(SECURITY_ENGINEER_PERSONA)
    # "task" here is the classify() output dict (e.g. {"size": "standard"}),
    # not the request text — kept as a distinct key from "request" so a
    # later Plan-phase slice reading this precedent doesn't conflate them.
    results = await dispatch_personas(
        personas, plan={"task": task, "request": request}, skip_llm=skip_llm
    )
    return {"personas": personas, "results": results, "skip_llm": skip_llm}


# ---------------------------------------------------------------------------
# Persona dispatch and wave barrier
# ---------------------------------------------------------------------------


class WaveError(Exception):
    """Raised when a wave barrier fails (a slice returned status='failed')."""

    def __init__(self, failing_slice: str, succeeded: list):
        self.failing_slice = failing_slice
        self.succeeded = succeeded
        super().__init__(f"Wave barrier failed on slice '{failing_slice}'")


def _parse_dispatch_envelope(stdout: str, persona: str) -> dict:
    """Parse a `claude -p --output-format json` envelope into a dispatch result.

    Status is derived solely from the envelope's `is_error` field and is
    never overwritten by the parsed payload. For personas in
    JSON_CONTRACT_PERSONAS, the envelope's `result` field is additionally
    parsed as JSON and its keys merged in, except `status` (exposed
    separately as `review_status`, since CODE_REVIEW_PANEL's own contract
    reuses that key name for an unrelated pass/warn/fail/skip vocabulary)
    and `persona` (discarded — already dispatch-owned). For every other
    persona, `result` is always stored verbatim under `output`. A malformed
    or non-object payload — the top-level envelope itself, or (for a
    JSON_CONTRACT_PERSONAS member) the inner `result` — degrades gracefully
    rather than raising: a bad envelope maps to the generalized failure stub
    with no `verdict` key, and a bad inner `result` maps to `output` plus a
    `parse_error: True` marker while the already-derived status is left
    untouched.
    """
    try:
        envelope = json.loads(stdout)
        if not isinstance(envelope, dict):
            raise TypeError("envelope is not a JSON object")
    except (json.JSONDecodeError, TypeError, ValueError):
        return {"persona": persona, "status": "failed", "error": "llm_unavailable"}

    data = {
        "persona": persona,
        # default True: an envelope that doesn't state whether it errored
        # is not evidence of success.
        "status": "failed" if envelope.get("is_error", True) else "success",
    }
    result_text = envelope.get("result", "")
    if persona in JSON_CONTRACT_PERSONAS:
        try:
            parsed = json.loads(result_text)
            if not isinstance(parsed, dict):
                raise TypeError("parsed result is not a JSON object")
        except (json.JSONDecodeError, TypeError, ValueError):
            data["output"] = result_text
            data["parse_error"] = True
        else:
            # status/persona stay dispatch-owned (AC #3): dispatch status is
            # derived only from the envelope's is_error, never from the
            # parsed payload. CODE_REVIEW_PANEL's own contract reuses the
            # key name "status" for an unrelated pass/warn/fail/skip
            # vocabulary, so expose it separately rather than merge it over.
            for key, value in parsed.items():
                if key == "status":
                    data["review_status"] = value
                elif key == "persona":
                    continue
                else:
                    data[key] = value
    else:
        data["output"] = result_text
    return data


async def dispatch_persona(persona: str, plan: dict, skip_llm: bool = False) -> dict:
    """Dispatch a persona via `claude -p --agent <persona> --output-format json`.

    In --skip-llm mode, returns a stub success result without invoking the CLI.
    """
    print(f"INFO: dispatching persona {persona}", file=sys.stderr)
    if skip_llm:
        return {"persona": persona, "status": "success"}
    try:
        # json.dumps(plan) lives inside this try so a non-serializable plan
        # value degrades to the same failure stub as a CLI/subprocess error,
        # instead of raising out of this coroutine and breaking the
        # asyncio.gather() fan-out in dispatch_personas() for every sibling
        # persona in the same wave.
        task_prompt = json.dumps(plan)
        # Offload to a thread so asyncio.gather over multiple personas actually
        # overlaps instead of blocking the event loop on subprocess.run (#1213).
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            functools.partial(
                subprocess.run,
                [
                    "claude",
                    "-p",
                    "--agent",
                    persona,
                    "--output-format",
                    "json",
                    task_prompt,
                ],
                capture_output=True,
                text=True,
                timeout=PERSONA_DISPATCH_TIMEOUT_S,
            ),
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError, TypeError, ValueError):
        return {"persona": persona, "status": "failed", "error": "llm_unavailable"}

    return _parse_dispatch_envelope(result.stdout, persona)


async def dispatch_personas(personas: list, plan: dict, skip_llm: bool = False) -> list:
    """Dispatch all personas concurrently and return their results.

    return_exceptions=True keeps one persona's unexpected exception (any
    error class dispatch_persona's own try/except doesn't already convert to
    a failure stub) from cancelling its siblings' in-flight dispatches —
    Research's contract is to aggregate and persist every persona's outcome,
    never to let one bad result silently discard the rest.
    """
    tasks = [dispatch_persona(p, plan, skip_llm) for p in personas]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return [
        {"persona": p, "status": "failed", "error": "llm_unavailable"}
        if isinstance(r, Exception)
        else r
        for p, r in zip(personas, results)
    ]


async def reconcile(results: list, wave_slices: list) -> None:
    """Check wave results; raise WaveError if any slice failed."""
    failed = [r for r in results if r.get("status") == "failed"]
    if failed:
        raise WaveError(
            failing_slice=failed[0]["slice"],
            succeeded=[r["slice"] for r in results if r.get("status") == "success"],
        )


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


async def run_pipeline(
    request: str,
    memory_dir: Path,
    skip_llm: bool = False,
    resume: bool = False,
    classify_fn=None,
    phase_research_fn=None,
    fail_wave: bool = False,
    dispatch_personas_flag: bool = False,
) -> int:
    """Main orchestration pipeline. Returns exit code (0=success, 1=error)."""
    # Resolve inject-able dependencies
    if classify_fn is None:
        task = await classify(request, skip_llm)
    else:
        task = classify_fn(request)
        if asyncio.iscoroutine(task):
            task = await task

    if phase_research_fn is None:
        phase_research_fn = _default_phase_research

    # Fast path for trivial tasks
    if task.get("size") == "trivial":
        print("INFO: trivial task — taking fast path", file=sys.stderr)
        return 0

    # --resume guard: fail if no state exists at all
    if resume:
        state_files = list(memory_dir.glob("orchestrator-*.json"))
        if not state_files:
            print(
                "ERROR: No prior phase state found; run without --resume to start a new pipeline",
                file=sys.stderr,
            )
            return 1

    # Wave barrier failure simulation (for testing)
    if fail_wave:
        print("ERROR: wave barrier failed on slice 'slice-1'", file=sys.stderr)
        print(
            f"Resume with: python3 {SCRIPTS / 'orchestrator.py'} --resume",
            file=sys.stderr,
        )
        return 1

    # Persona dispatch (for testing --dispatch-personas flag)
    if dispatch_personas_flag:
        await dispatch_personas(
            DEFAULT_PERSONAS, plan={"task": task}, skip_llm=skip_llm
        )
        return 0

    # Phase 1: Research
    research_state = read_progress("research", memory_dir) if resume else None
    if research_state is None:
        research_state = await phase_research_fn(request, task, skip_llm)
        write_progress("research", research_state, memory_dir)

    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _resolve_request_from_stdin() -> str:
    """Return the piped stdin request, or "default request" as fallback.

    Tests stdin CONTENT, not just whether it's a tty: a piped-but-empty
    stdin (e.g. `< /dev/null` in a hook/CI invocation) must still resolve
    to "default request" — an empty request now drives live persona
    dispatch (the Research phase), not just classify().
    """
    piped_text = sys.stdin.read().strip() if not sys.stdin.isatty() else ""
    return piped_text or "default request"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--resume",
        action="store_true",
        help="Skip phases whose state files already exist",
    )
    ap.add_argument(
        "--skip-llm",
        action="store_true",
        help="Use stubs for classify() and all LLM dispatch",
    )
    ap.add_argument(
        "--memory-dir",
        default=".claude/memory",
        metavar="PATH",
        help="Where to read/write phase state (default: .claude/memory/)",
    )
    ap.add_argument(
        "--classify",
        default=None,
        metavar="SIZE",
        choices=["trivial", "standard", "complex"],
        help="Override classification (for testing)",
    )
    ap.add_argument(
        "--fail-wave",
        action="store_true",
        help="Simulate a wave barrier failure (for testing)",
    )
    ap.add_argument(
        "--dispatch-personas",
        action="store_true",
        help="Dispatch plan-review personas (for testing)",
    )
    args = ap.parse_args(argv)

    request = _resolve_request_from_stdin()
    memory_dir = Path(args.memory_dir)

    # Build classify_fn: use CLI override if provided
    classify_fn = None
    if args.classify:
        size = args.classify

        def classify_fn(req, _size=size):
            return {"size": _size}

    exit_code = asyncio.run(
        run_pipeline(
            request=request,
            memory_dir=memory_dir,
            skip_llm=args.skip_llm,
            resume=args.resume,
            classify_fn=classify_fn,
            fail_wave=args.fail_wave,
            dispatch_personas_flag=args.dispatch_personas,
        )
    )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
