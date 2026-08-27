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

Module split: see ADR 0040.
"""

# Module split (dispatch_primitives / phase_functions): evaluated and
# declined for now — see ADR 0040
# (docs/adr/0040-evaluate-splitting-orchestrator-py-no-go.md, issue #1723).
# The blocker is 58 `patch.object(orch, "dispatch_persona"/"dispatch_personas",
# ...)` sites in tests/scripts/test_orchestrator.py (multiline-aware count —
# a single-line grep undercounts to 45) that would stop intercepting dispatch
# calls if the phase functions imported those names from a separate module.
# Revisit if dispatch_primitives or phase_functions grows independently.

from __future__ import annotations

import argparse
import asyncio
import functools
import json
import re
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
# exists (see follow-up #2067).
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
# re-typed at each call/test site. A tuple (like SECURITY_KEYWORDS), not a
# list: this is a fixed roster, so `list(RESEARCH_PERSONAS)` at its one call
# site is a genuine type conversion into a mutable working copy, not a
# defensive copy guarding against accidental in-place mutation of the
# constant itself.
RESEARCH_PERSONAS = ("codebase-recon", "architect", "data-flow-tracer")

# Plan-phase core-trio roster (see agents/orchestrator.md § Phase 2: Plan).
# Dispatched first, before the plan-review-* critics in DEFAULT_PERSONAS —
# see _default_phase_plan below. A tuple, matching RESEARCH_PERSONAS's own
# convention; unlike RESEARCH_PERSONAS, nothing is ever conditionally
# appended to this roster, so no defensive-copy note is needed here.
# agents/orchestrator.md's "Plan persona roster" section restates this same
# trio (and CRITICS_SKIPPED_ALL_CORE_FAILED's value) in prose; that
# restatement is not mechanically bound to this tuple today — keep the two
# in sync by hand until a content-guard test exists (see follow-up #2067).
PLAN_CORE_PERSONAS = ("product-manager", "architect", "qa-engineer")

# Persisted-state vocabulary for _default_phase_plan's all-core-failed guard
# (see below) — named alongside the module's other cross-process vocabulary
# constants (SECURITY_KEYWORDS, RESEARCH_PERSONAS) so the sentinel has one
# definition instead of being re-typed at the production site and in tests.
CRITICS_SKIPPED_ALL_CORE_FAILED = "all_core_personas_failed"

# The conditionally-dispatched fourth Research persona (see _touches_security
# below). Named for the same reason RESEARCH_PERSONAS is: avoid re-typing the
# literal at each call/test site.
SECURITY_ENGINEER_PERSONA = "security-engineer"

# The Implement-phase wave persona and its post-success doc-verification
# persona (see _default_phase_implement below). Named for the same reason
# SECURITY_ENGINEER_PERSONA is: avoid re-typing the literal at each
# call/test site.
SOFTWARE_ENGINEER_PERSONA = "software-engineer"
TECH_WRITER_PERSONA = "tech-writer"

# Implement-phase wave slice roster (see _dispatch_implement_wave below). A
# tuple, matching RESEARCH_PERSONAS/PLAN_CORE_PERSONAS's own convention.
# Load-bearing, not decorative: persisted into orchestrator-implement.json
# and printed verbatim in the operator-facing "wave barrier failed on slice
# '<name>'" message. One definition on the production side (test_orchestrator
# pins its exact value directly below, alongside SOFTWARE_ENGINEER_PERSONA/
# TECH_WRITER_PERSONA's own pinning tests) — most test sites deliberately
# still pin the literal value independently rather than importing this
# constant, matching how this file's persona constants are pinned rather
# than merely referenced. A single synthetic slice representing "the whole
# task" today (see the Script gap in agents/orchestrator.md for why); the
# --fail-wave simulation branch below deliberately prints a different,
# unrelated slice name ("slice-1") since it doesn't go through this
# constant at all.
IMPLEMENT_WAVE_SLICES = ("implement-1",)

# Timeouts (seconds) for the two `claude -p` subprocess dispatch sites below.
# Unverified placeholders, not measured against a real dispatch — pinned by
# a direct test (test_orchestrator.py) per follow-up #1716 so an accidental
# edit fails fast instead of surfacing only as a flaky/slow-CLI symptom;
# the underlying values themselves remain unverified against real latency.
CLASSIFY_TIMEOUT_S = 30
PERSONA_DISPATCH_TIMEOUT_S = 60


def _warn_on_failed_personas(phase_label: str, results: list, fatal: bool = False) -> None:
    """Print a single stderr WARNING naming every failed persona in results,
    or nothing at all if none failed.

    Shared by _default_phase_research, _default_phase_plan, and
    _default_phase_implement so the WARNING message has one normative
    formatting/behavior definition instead of independently maintained
    copies. Research/Plan's failures (and Implement's post-success review
    group) are genuinely recorded and non-fatal, which is the default
    wording — but the Implement wave dispatch is a different case: a
    failure there is about to raise WaveError uncaught (the state file is
    never written) and end the process with exit code 1, so `fatal=True`
    selects wording that says so instead of falsely claiming
    "(recorded, non-fatal)".
    """
    failed_personas = [r["persona"] for r in results if r.get("status") == "failed"]
    if failed_personas:
        suffix = "wave barrier will fail" if fatal else "recorded, non-fatal"
        print(
            f"WARNING: {phase_label} persona dispatch failed ({suffix}): {', '.join(failed_personas)}",
            file=sys.stderr,
        )


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


def _derive_recon_slug(root: Path) -> str:
    """Kebab-safe, lowercase repo-root directory name.

    Duplicates codebase_recon.py's own `_derive_slug` (same algorithm)
    rather than importing it. Both are hand-kept in sync by
    `test_derive_recon_slug_matches_codebase_recon_algorithm`, which already
    exists (this is not a "keep in sync until a guard test exists" gap —
    tracked instead as a cleanup: promote both to a shared `scripts/lib/`
    module, matching codebase_recon.py's own existing `from lib import ...`
    convention, and delete this copy — see follow-up #2068).
    """
    name = root.resolve().name.lower()
    name = re.sub(r"[^a-z0-9._-]", "-", name)
    name = re.sub(r"-{2,}", "-", name)
    return name.strip("-") or "repo"


def _recon_artifact_path(root: Path) -> Path:
    """Path to codebase-recon's JSON artifact for the repo at `root`.

    Per agents/codebase-recon.md's Contract section: always
    `.claude/memory/recon-<slug>.json`. `root` is deliberately the caller's
    own CWD, not a git-root resolution (e.g.
    hooks/lib/artifact_paths.py::memory_dir, used by other scripts in this
    directory for that purpose) — the recon *agent*'s prompt writes this
    path relative to its own CWD, which is orchestrator.py's CWD since
    dispatch_persona's subprocess.run inherits it unchanged. Resolving
    against the git root instead would disagree with the recon agent's own
    write location whenever they differ (e.g. orchestrator.py invoked from
    a subdirectory), which is the opposite of this function's purpose.
    Also independent of orchestrator.py's own (configurable) --memory-dir;
    if that flag points elsewhere, this path and the phase-state directory
    diverge — inherent to the recon agent's contract, not something this
    function can paper over.
    """
    return root / ".claude" / "memory" / f"recon-{_derive_recon_slug(root)}.json"


async def _resolve_recon_artifact(personas: list, results: list, cwd: Path) -> str | None:
    """Link codebase-recon's own artifact (agents/codebase-recon.md's
    Contract — .claude/memory/recon-<slug>.json) into Research state, so a
    Plan-phase consumer doesn't need to independently know that naming
    convention (follow-up #1716). Returns `None` when codebase-recon wasn't
    dispatched, didn't succeed, or its artifact file isn't on disk (e.g.
    --skip-llm, where no real agent ran).

    `cwd` is captured by the caller before its own `await` rather than read
    here via `Path.cwd()` directly — process-global state should not be
    re-read across an await boundary in case a future concurrent coroutine
    ever changes it.
    """
    if "codebase-recon" not in personas:
        return None
    recon_result = next((r for r in results if r.get("persona") == "codebase-recon"), None)
    if recon_result is None or recon_result.get("status") != "success":
        return None
    candidate = _recon_artifact_path(cwd)
    # Offload to a thread, matching classify()'s own run_in_executor use for
    # its blocking call — the event loop shouldn't block on a filesystem
    # stat any more than it should on subprocess.run.
    loop = asyncio.get_running_loop()
    if not await loop.run_in_executor(None, candidate.is_file):
        return None
    return str(candidate)


async def _default_phase_research(request: str, task: dict, skip_llm: bool) -> dict:
    """Dispatch the Research-phase personas and aggregate their results.

    Always dispatches RESEARCH_PERSONAS (codebase-recon, architect,
    data-flow-tracer); additionally dispatches security-engineer when the
    request text touches auth/secrets/crypto per _touches_security(). A
    status: "failed" entry among the dispatched results is recorded
    verbatim — reconcile()/WaveError are scoped to the Implement phase's
    wave loop, not Research.
    """
    # Captured before the await below (see _resolve_recon_artifact's
    # docstring) rather than read via Path.cwd() after it.
    cwd = Path.cwd()
    # RESEARCH_PERSONAS is an immutable tuple; list() converts it into the
    # mutable working copy the conditional security-engineer append below
    # needs (see the constant's own definition for why it's a tuple).
    personas = list(RESEARCH_PERSONAS)
    if _touches_security(request):
        personas.append(SECURITY_ENGINEER_PERSONA)
    # "task" here is the classify() output dict (e.g. {"size": "standard"}),
    # not the request text — kept as a distinct key from "request" so a
    # later Plan-phase slice reading this precedent doesn't conflate them.
    results = await dispatch_personas(
        personas, plan={"task": task, "request": request}, skip_llm=skip_llm
    )
    # Research records failures verbatim and never raises (see docstring
    # above) — but a run where any persona failed must not look identical,
    # on the console, to one that succeeded fully. Mirrors classify()'s own
    # degraded-but-non-fatal WARNING.
    _warn_on_failed_personas("Research", results)
    return {
        "personas": personas,
        "results": results,
        "skip_llm": skip_llm,
        "recon_artifact": await _resolve_recon_artifact(personas, results, cwd),
    }


# ---------------------------------------------------------------------------
# Plan phase
# ---------------------------------------------------------------------------


def _all_personas_failed(results: list) -> bool:
    """True if results is non-empty and every entry has status "failed".

    Deliberately False on an empty list: an empty core_results would make a
    bare all(...) vacuously True and wrongly skip critic dispatch, so the
    emptiness check is load-bearing, not defensive noise — unreachable
    today (dispatch_personas always returns one entry per persona and
    PLAN_CORE_PERSONAS is a fixed 3-tuple), but would matter the moment a
    future slice makes the core roster dynamic.
    """
    return bool(results) and all(r.get("status") == "failed" for r in results)


async def _default_phase_plan(
    request: str, task: dict, research_state: dict, skip_llm: bool
) -> dict:
    """Dispatch the Plan-phase core trio, then the plan-review-* critics.

    Two-stage dispatch: PLAN_CORE_PERSONAS (product-manager, architect,
    qa-engineer) drafts a plan using the Research phase's aggregated state
    as context, then DEFAULT_PERSONAS (the five plan-review-* critics)
    critiques that draft — unless every core-trio result has
    status: "failed", in which case critic dispatch is skipped entirely
    (see the all-core-failed guard below). A status: "failed" entry among
    either group's results is recorded verbatim — reconcile()/WaveError
    stay scoped to the Implement phase's wave loop, not Plan. Note this
    phase still dispatches the core trio even when research_state's own
    results are entirely failed: the raw request text is sufficient context
    for the trio to draft from, unlike the critics, which genuinely have
    nothing to critique when the trio itself produced nothing.
    """
    core_personas = list(PLAN_CORE_PERSONAS)
    core_results = await dispatch_personas(
        core_personas,
        plan={"task": task, "request": request, "research": research_state},
        skip_llm=skip_llm,
    )
    critics_skipped_reason = None
    if _all_personas_failed(core_results):
        # Every core-trio persona failed (most plausibly: the claude CLI is
        # unreachable) — skip the five critic dispatches entirely rather
        # than spend real LLM cost critiquing identical failure stubs.
        critic_results = []
        critics_skipped_reason = CRITICS_SKIPPED_ALL_CORE_FAILED
        print(
            "INFO: all Plan core personas failed — skipping critic dispatch",
            file=sys.stderr,
        )
    else:
        critic_results = await dispatch_personas(
            DEFAULT_PERSONAS,
            plan={"task": task, "request": request, "plan_draft": core_results},
            skip_llm=skip_llm,
        )
    # Exactly one merged WARNING per Plan-phase run, naming every failed
    # persona across both groups — not one line per group.
    _warn_on_failed_personas("Plan", core_results + critic_results)
    return {
        "core_personas": core_personas,
        "core_results": core_results,
        # list(...), not a bare reference: critic_personas is persisted
        # (json.dumps doesn't care, but a future in-memory consumer
        # mutating this list would otherwise corrupt the shared module
        # constant DEFAULT_PERSONAS for the rest of the process).
        "critic_personas": list(DEFAULT_PERSONAS),
        "critic_results": critic_results,
        "critics_skipped_reason": critics_skipped_reason,
        "skip_llm": skip_llm,
    }


# ---------------------------------------------------------------------------
# Implement phase
# ---------------------------------------------------------------------------


async def _dispatch_implement_wave(
    request: str, task: dict, plan_state: dict, skip_llm: bool
) -> list:
    """Dispatch the Implement-phase wave and reconcile its results.

    Dispatches SOFTWARE_ENGINEER_PERSONA once per IMPLEMENT_WAVE_SLICES entry
    via dispatch_personas — reused verbatim rather than a hand-rolled second
    copy of its gather/BaseException-normalization logic. The `* len(...)`
    below is what keeps `personas` index-aligned with IMPLEMENT_WAVE_SLICES
    for the "slice" tagging that follows — a real invariant, not decorative,
    even though both are length 1 today (see IMPLEMENT_WAVE_SLICES's own
    comment for why). reconcile() raises WaveError uncaught (no try/except
    here) on any failed slice, so _run_phase's write_progress call never
    runs for a failed wave — the phase's state file stays absent and a
    subsequent --resume run retries Implement from scratch.
    """
    results = await dispatch_personas(
        [SOFTWARE_ENGINEER_PERSONA] * len(IMPLEMENT_WAVE_SLICES),
        plan={"task": task, "request": request, "plan_state": plan_state},
        skip_llm=skip_llm,
    )
    for slice_name, result in zip(IMPLEMENT_WAVE_SLICES, results):
        result["slice"] = slice_name
    # fatal=True: this failure is about to raise WaveError uncaught (state
    # never persisted, exit code 1) — the opposite of the "recorded,
    # non-fatal" wording _warn_on_failed_personas defaults to.
    _warn_on_failed_personas("Implement", results, fatal=True)
    await reconcile(results, list(IMPLEMENT_WAVE_SLICES))  # raises WaveError; propagates uncaught
    return results


async def _dispatch_implement_verification(
    request: str, task: dict, results: list, skip_llm: bool
) -> tuple:
    """Dispatch post-success review-panel + tech-writer verification.

    Only reached after _dispatch_implement_wave's reconcile() succeeds.
    Both go through dispatch_personas (never a bare dispatch_persona call),
    so an unexpected throwable from either is normalized to a failure stub
    rather than escaping past run_pipeline's `except WaveError` and
    discarding a successful wave's results. A second, independent
    _warn_on_failed_personas call ("Implement review", genuinely non-fatal)
    surfaces a failed member of either dispatch as a stderr WARNING,
    mirroring Research/Plan's own non-fatal-failure-visibility convention.
    """
    verification_payload = {
        "task": task,
        "request": request,
        "implement_results": results,
    }
    review_results = await dispatch_personas(
        CODE_REVIEW_PANEL, plan=verification_payload, skip_llm=skip_llm
    )
    (tech_writer_result,) = await dispatch_personas(
        [TECH_WRITER_PERSONA],
        plan=verification_payload,
        skip_llm=skip_llm,
    )
    _warn_on_failed_personas("Implement review", review_results + [tech_writer_result])
    return review_results, tech_writer_result


async def _default_phase_implement(
    request: str, task: dict, plan_state: dict, skip_llm: bool
) -> dict:
    """Dispatch the Implement-phase wave, reconcile it, then verify on success.

    Composes two independently-changing concerns (see their own docstrings):
    _dispatch_implement_wave (the wave-dispatch/reconcile barrier, whose
    per-step decomposition is tracked future work — see the Script gap in
    agents/orchestrator.md) and _dispatch_implement_verification (a stable
    concern that shouldn't need to move when that lands).
    """
    results = await _dispatch_implement_wave(request, task, plan_state, skip_llm)
    review_results, tech_writer_result = await _dispatch_implement_verification(
        request, task, results, skip_llm
    )
    return {
        "wave_slices": list(IMPLEMENT_WAVE_SLICES),
        "results": results,
        # list(...), not a bare reference: review_personas is persisted,
        # and a future in-memory consumer mutating this list would
        # otherwise corrupt the shared module constant CODE_REVIEW_PANEL
        # for the rest of the process (same rationale as critic_personas
        # in _default_phase_plan above).
        "review_personas": list(CODE_REVIEW_PANEL),
        "review_results": review_results,
        "tech_writer_result": tech_writer_result,
        "skip_llm": skip_llm,
    }


# ---------------------------------------------------------------------------
# Persona dispatch and wave barrier
# ---------------------------------------------------------------------------


class WaveError(Exception):
    """Raised when a wave barrier fails (a slice returned status='failed')."""

    def __init__(self, failing_slice: str, succeeded: list):
        self.failing_slice = failing_slice
        self.succeeded = succeeded
        super().__init__(f"Wave barrier failed on slice '{failing_slice}'")


def _failed_result(persona: str, error: str) -> dict:
    """Return the canonical dispatch-failure stub shared by every failure site.

    One normative shape for {persona, status: "failed", error} so a future
    change to the shape (e.g. adding a distinguishing field) touches one
    definition instead of the four call sites that used to hand-construct it
    independently. `error` is required, not defaulted, so a new call site
    must name its cause rather than silently inheriting one that doesn't
    describe it — the four callers today: a malformed dispatch envelope
    ("malformed_envelope"), a non-serializable plan payload
    ("unserializable_plan"), a subprocess/CLI failure ("llm_unavailable"),
    and an unexpected throwable surfaced by asyncio.gather
    ("dispatch_exception").
    """
    return {"persona": persona, "status": "failed", "error": error}


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
    rather than raising: a bad envelope maps to a `"malformed_envelope"`
    failure stub (see `_failed_result`) with no `verdict` key, and a bad
    inner `result` maps to `output` plus a
    `parse_error: True` marker while the already-derived status is left
    untouched.
    """
    try:
        envelope = json.loads(stdout)
        if not isinstance(envelope, dict):
            raise TypeError("envelope is not a JSON object")
    except (json.JSONDecodeError, TypeError, ValueError):
        return _failed_result(persona, error="malformed_envelope")

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
        # A non-serializable plan value degrades to a failure stub, scoped
        # to this one call, instead of raising out of this coroutine and
        # breaking the asyncio.gather() fan-out in dispatch_personas() for
        # every sibling persona in the same wave. Kept as its own try/except
        # (distinct from the subprocess dispatch below) so a TypeError/
        # ValueError from a genuine bug in the dispatch machinery itself is
        # never mislabeled as this same, narrower serialization failure.
        task_prompt = json.dumps(plan)
    except (TypeError, ValueError):
        return _failed_result(persona, error="unserializable_plan")
    try:
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
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return _failed_result(persona, error="llm_unavailable")

    return _parse_dispatch_envelope(result.stdout, persona)


async def dispatch_personas(personas: list, plan: dict, skip_llm: bool = False) -> list:
    """Dispatch all personas concurrently and return their results.

    return_exceptions=True keeps one persona's unexpected exception (any
    throwable dispatch_persona's own try/except doesn't already convert to a
    failure stub) from cancelling its siblings' in-flight dispatches —
    Research's contract is to aggregate and persist every persona's outcome,
    never to let one bad result silently discard the rest. Matched here on
    BaseException, not Exception: asyncio.CancelledError has subclassed
    BaseException directly (not Exception) since Python 3.8, and a cancelled
    child task's result is exactly what return_exceptions=True aggregates
    here rather than propagates — an Exception-only guard would let it
    through un-normalized and fail JSON serialization downstream.
    """
    tasks = [dispatch_persona(p, plan, skip_llm) for p in personas]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return [
        # Distinct from "llm_unavailable" (a CLI/subprocess-level failure,
        # already handled inside dispatch_persona's own try/except): this
        # branch means something threw out of the coroutine itself — a
        # cancellation or an unforeseen bug — which is not evidence the LLM
        # was unreachable, and the persisted research state must keep the
        # two distinguishable.
        _failed_result(p, error="dispatch_exception") if isinstance(r, BaseException) else r
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


def _print_wave_failure(failing_slice: str) -> None:
    """Print the shared two-line wave-barrier-failure message to stderr.

    Shared by the --fail-wave simulation branch and the real WaveError-catch
    site in run_pipeline so the resume-hint message has one normative
    definition instead of two independently maintained copies of the same
    two print() calls.
    """
    print(f"ERROR: wave barrier failed on slice '{failing_slice}'", file=sys.stderr)
    print(f"Resume with: python3 {SCRIPTS / 'orchestrator.py'} --resume", file=sys.stderr)


def _resolve_default(fn, default_fn):
    """Return fn if the caller supplied one, else default_fn.

    Shared by run_pipeline's phase_research_fn/phase_plan_fn/
    phase_implement_fn injection points so each doesn't add its own
    hand-written `if X_fn is None: X_fn = ...` branch to run_pipeline's own
    body, each one pushing its cyclomatic complexity and parameter count
    higher.
    """
    return fn if fn is not None else default_fn


async def _run_phase(
    phase_name: str, phase_fn, memory_dir: Path, resume: bool, *fn_args
) -> dict:
    """Resume-check/dispatch/write a phase's state, shared by every phase.

    Reads the phase's prior state from disk when resuming; otherwise calls
    phase_fn with fn_args and persists the result via write_progress. This is
    the shape run_pipeline previously hand-inlined once for Research
    (Slice 2) — extracted here so the Plan and Implement call sites reuse
    one definition instead of re-copying it.
    """
    state = read_progress(phase_name, memory_dir) if resume else None
    if state is None:
        state = await phase_fn(*fn_args)
        write_progress(phase_name, state, memory_dir)
    return state


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
    phase_plan_fn=None,
    phase_implement_fn=None,
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

    phase_research_fn = _resolve_default(phase_research_fn, _default_phase_research)
    phase_plan_fn = _resolve_default(phase_plan_fn, _default_phase_plan)
    phase_implement_fn = _resolve_default(phase_implement_fn, _default_phase_implement)

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
        _print_wave_failure("slice-1")
        return 1

    # Persona dispatch (for testing --dispatch-personas flag)
    if dispatch_personas_flag:
        await dispatch_personas(
            DEFAULT_PERSONAS,
            plan={"task": task, "request": request},
            skip_llm=skip_llm,
        )
        return 0

    # Phase 1: Research
    research_state = await _run_phase(
        "research", phase_research_fn, memory_dir, resume, request, task, skip_llm
    )

    # Phase 2: Plan
    plan_state = await _run_phase(
        "plan", phase_plan_fn, memory_dir, resume, request, task, research_state, skip_llm
    )

    # Phase 3: Implement
    try:
        await _run_phase(
            "implement", phase_implement_fn, memory_dir, resume, request, task, plan_state, skip_llm
        )
    except WaveError as exc:
        _print_wave_failure(exc.failing_slice)
        return 1

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
