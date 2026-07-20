#!/usr/bin/env python3
"""orchestrator.py — Python dispatcher for the dev-team three-phase pipeline.

CLI: python3 scripts/orchestrator.py [--resume] [--skip-llm] [--memory-dir <path>]
     [--classify trivial|standard|complex] [--fail-wave] [--dispatch-personas]

Flags:
  --resume            Skip phases whose state files already exist in memory-dir.
  --skip-llm          Use stubs for classify() and all LLM dispatch.
  --memory-dir <path> Where to read/write phase state (default: memory/ relative to CWD).
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
import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent

# Default personas for plan review
DEFAULT_PERSONAS = [
    "acceptance-test-critic",
    "design-architecture-critic",
]


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
        result = await asyncio.to_thread(
            subprocess.run,
            [
                "claude",
                "-p",
                f"Classify this task as exactly one of: trivial, standard, or complex. "
                f"Reply with only one word. Task: {request}",
            ],
            capture_output=True,
            text=True,
            timeout=30,
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
# Phase stubs
# ---------------------------------------------------------------------------


async def _default_phase_research(task: dict, skip_llm: bool) -> dict:
    """Default research phase stub (returns minimal result)."""
    return {"result": "research_done", "files": [], "skip_llm": skip_llm}


# ---------------------------------------------------------------------------
# Persona dispatch and wave barrier
# ---------------------------------------------------------------------------


class WaveError(Exception):
    """Raised when a wave barrier fails (a slice returned status='failed')."""

    def __init__(self, failing_slice: str, succeeded: list):
        self.failing_slice = failing_slice
        self.succeeded = succeeded
        super().__init__(f"Wave barrier failed on slice '{failing_slice}'")


async def dispatch_persona(persona: str, plan: dict, skip_llm: bool = False) -> dict:
    """Dispatch a plan-review persona. In --skip-llm mode, returns a stub approval."""
    print(f"INFO: dispatching plan-review persona {persona}", file=sys.stderr)
    if skip_llm:
        return {"persona": persona, "verdict": "approve", "issues": []}
    # Real dispatch via claude -p (not tested in unit tests)
    try:
        prompt = (
            f"You are the {persona}. Review this plan and return approve or needs-revision "
            f'with findings as JSON: {{"verdict": "approve|needs-revision", "issues": []}}. '
            f"Plan: {json.dumps(plan)}"
        )
        # Offload to a thread so asyncio.gather over multiple personas actually
        # overlaps instead of blocking the event loop on subprocess.run (#1213).
        result = await asyncio.to_thread(
            subprocess.run,
            ["claude", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0 and result.stdout.strip():
            raw = result.stdout.strip()
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(raw[start:end])
                data["persona"] = persona
                return data
    except (
        FileNotFoundError,
        subprocess.TimeoutExpired,
        OSError,
        json.JSONDecodeError,
    ):
        pass
    return {
        "persona": persona,
        "verdict": "approve",
        "issues": [],
        "error": "llm_unavailable",
    }


async def dispatch_personas(personas: list, plan: dict, skip_llm: bool = False) -> list:
    """Dispatch all personas concurrently and return their results."""
    tasks = [dispatch_persona(p, plan, skip_llm) for p in personas]
    return list(await asyncio.gather(*tasks))


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
        print("Resume with: python3 scripts/orchestrator.py --resume", file=sys.stderr)
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
        research_state = await phase_research_fn(task, skip_llm)
        write_progress("research", research_state, memory_dir)

    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


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
        default="memory",
        metavar="PATH",
        help="Where to read/write phase state (default: memory/)",
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

    request = sys.stdin.read().strip() if not sys.stdin.isatty() else "default request"
    memory_dir = Path(args.memory_dir)

    # Build classify_fn: use CLI override if provided
    classify_fn = None
    if args.classify:
        size = args.classify
        classify_fn = lambda req, _size=size: {"size": _size}

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
