#!/usr/bin/env python3
"""pre_commit_review — Claude Code PreToolUse:Bash hook (Python port).

Python port of hooks/pre-commit-review.sh (#583 / #572 Cluster B).
Extended under #709 to require and durably log a reason when the
`--no-verify`/`-n` bypass is used, closing the frictionless-bypass gap
identified by the gate-correlation evidence (bypassed commits correlate
with materially higher rework).

Blocks `git commit` (exit 2) unless a `.review-passed` file exists in
cwd with a hash matching the currently staged content. The /code-review
command auto-scopes to uncommitted changes and writes this file when
review passes.

Issue #1461 (raised bar, not full closure): the hash match alone (via
`review_gate_hash()` — see that module's own docstring for the full account)
only proves the staged content is unchanged since `.review-passed` was
written — it does not by itself prove an independent review agent actually
ran, since a caller could compute and write the same hash itself. That gap
was real and observed in production: an orchestrating agent with no
Agent/Task dispatch tool available silently self-applied review checklists
inline instead of hard-failing, then wrote a matching `.review-passed` and
committed/opened a PR off a self-certified pass that a later genuine
multi-agent review showed had missed real defects.

`_evaluate_gate()` now additionally requires the hash-matching write to be
corroborated by `hooks/lib/review_gate_corroboration.py`: >= 2 DISTINCT
registered review-agent dispatches recorded (via `hooks/agent_dispatch_ledger.py`)
in the `WINDOW_SECONDS` recency window before the gate file's own mtime, OR a
contemporaneous doc-only exemption event. This is a materially raised bar —
an agent can no longer merely *write plausible text* to pass the gate, it
must cause the harness to actually dispatch real review-agent types — but
not a cryptographic proof: a sufficiently motivated bypass could still
dispatch trivial/no-op review-agent calls purely to clear the gate without a
substantive review having occurred. Full closure needs harness-level
provenance (e.g. a signed dispatch receipt) outside this repo's control. The
upstream mitigation still matters too: `skills/code-review/SKILL.md`,
`skills/plan/SKILL.md`, and `skills/build/SKILL.md` each hard-require
confirming `Agent`/`Task` tool availability before dispatching any review
agent, and STOP — no self-applied review, no `.review-passed` write — when
that capability is absent.

Non-commit Bash commands pass through immediately (exit 0).
`git commit --no-verify` (or bare `-n`) is still allowed through — but
only when the process environment carries a non-empty `GATE_BYPASS_REASON`.
When present, the bypass is appended as one line to
`.claude/metrics/gate-bypass-audit.jsonl` (unconditional — not gated by
`DEV_TEAM_TELEMETRY`) and the commit proceeds. When absent, the commit is
blocked with a message naming `GATE_BYPASS_REASON` as the required
mechanism.

Contract (docs/python-hook-contract.md):
    Input : JSON on stdin (Claude Code PreToolUse:Bash payload)
    Exit 0: allow the tool call
    Exit 2: block the tool call (feedback returned to Claude on stdout,
            mirrored to stderr — some hook-error wrappers only surface
            stderr, and a stdout-only block message was going unseen)

Stdlib-only. Python 3.8+.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_HOOK_DIR = Path(__file__).resolve().parent
_LIB_DIR = _HOOK_DIR / "lib"

sys.path.insert(0, str(_LIB_DIR))
try:
    from artifact_paths import (
        resolve_file as _resolve_file,  # type: ignore[import-not-found]
    )
    from boundary_events import (  # type: ignore[import-not-found]
        emit_boundary_event as _emit_boundary_event,
    )
    from pre_commit_detect import (  # type: ignore[import-not-found]
        bypass_flag_name,
        has_bypass_flag,
        is_git_commit_command,
    )
    from review_gate_corroboration import (  # type: ignore[import-not-found]
        evaluate as _evaluate_ledger,
    )
    from review_gate_corroboration import (  # type: ignore[import-not-found]
        has_doc_only_exemption as _has_doc_only_exemption,
    )
    from review_gate_corroboration import (  # type: ignore[import-not-found]
        has_single_agent_exemption as _has_single_agent_exemption,
    )
    from review_gate_corroboration import (  # type: ignore[import-not-found]
        mtime_to_iso as _mtime_to_iso,
    )
    from review_gate_hash import review_gate_hash  # type: ignore[import-not-found]
    from stdin_json import read_stdin_json  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover

    def _resolve_file(  # type: ignore[misc]
        category: str, filename: str, root=None, migrate: bool = True
    ) -> Path:
        # Degraded-import fallback (artifact_paths itself failed to import).
        # The bare `Path(category) / filename` this used to return is the
        # exact bare-relative-path bug Step 4.4 fixed for the normal path —
        # reproduce that fix's `.claude/<category>/<filename>` shape here
        # too. `parents[3]` walks up from
        # `plugins/dev-team/hooks/pre_commit_review.py` to this repo's
        # root (hooks -> dev-team -> plugins -> repo root).
        repo_root = Path(__file__).resolve().parents[3]
        return repo_root / ".claude" / category / filename

    def is_git_commit_command(_: str) -> bool:  # type: ignore[misc]
        return False

    def has_bypass_flag(_: str) -> bool:  # type: ignore[misc]
        return False

    def bypass_flag_name(_: str) -> str | None:  # type: ignore[misc]
        return None

    def review_gate_hash(cwd=None) -> str:  # type: ignore[misc]
        return ""

    def read_stdin_json() -> dict | None:  # type: ignore[misc]
        return None

    def _emit_boundary_event(*_args, **_kwargs) -> None:  # type: ignore[misc]
        return None

    class _DegradedLedgerEvidence:  # type: ignore[misc]
        """Degraded-import stand-in for `review_gate_corroboration.LedgerEvidence`.

        A failed import means this module can't corroborate anything —
        fails CLOSED the same way the real module does on a read failure,
        reported as "unreadable" so the caller's rejection message points
        at an infra problem rather than implying no review happened.
        """

        agents_in_window: frozenset = frozenset()
        any_dispatch_ever = False
        read_failure_reason = "unreadable"

    def _evaluate_ledger(cwd, before_ts, window_seconds, subject_hash):  # type: ignore[misc]
        return _DegradedLedgerEvidence()

    def _has_doc_only_exemption(  # type: ignore[misc]
        cwd, before_ts, window_seconds, subject_hash
    ) -> bool:
        return False

    def _has_single_agent_exemption(  # type: ignore[misc]
        cwd, before_ts, window_seconds, subject_hash
    ) -> bool:
        return False

    def _mtime_to_iso(mtime: float) -> str:  # type: ignore[misc]
        return datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def emit_boundary_event(*args, **kwargs) -> None:
    """Local safety net (#859): even a misbehaving helper must never affect
    this hook's exit code, stdout, or stderr."""
    try:
        _emit_boundary_event(*args, **kwargs)
    except Exception:  # noqa: BLE001, S110 - fail-open by design
        pass


_BLOCK_MESSAGE = (
    "BLOCKED: Code review required before committing.\n"
    "\n"
    "Run /code-review to review staged files.\n"
    "If review passes, the commit will be allowed on the next attempt.\n"
    "\n"
    "To bypass: use git commit --no-verify\n"
)

_BYPASS_BLOCK_MESSAGE = (
    "BLOCKED: git commit --no-verify (or -n) requires a reason.\n"
    "\n"
    "Set GATE_BYPASS_REASON to a non-empty explanation and retry, e.g.:\n"
    '  GATE_BYPASS_REASON="hotfix, review to follow" git commit --no-verify -m ...\n'
    "\n"
    "The bypass is logged to .claude/metrics/gate-bypass-audit.jsonl once a\n"
    "reason is supplied.\n"
)

# Recency window (#1461): how far back before the gate file's own mtime a
# genuine review-agent dispatch still counts as corroborating evidence.
# Pinned at 30 minutes — generous enough to cover a real multi-agent
# /code-review pass's typical wall-clock duration without inviting stale
# evidence to satisfy the gate long after the fact. See the plan's Risks &
# Open Questions section for the rationale; not a tunable env var — a fixed
# security-relevant constant.
WINDOW_SECONDS = 1800

# Minimum number of DISTINCT registered review-agent dispatches required in
# the recency window (#1461). code-review/SKILL.md's change-size gate keeps
# at least 4 agents (security-review, correctness-review,
# spec-compliance-review, doc-review) even on its narrowest fast-path run, so
# a legitimately small, non-doc-only change already clears this bar under
# existing behavior. A sanctioned single-agent run (`--agent <name>`) is
# exempted separately below, since it deliberately dispatches exactly 1.
_MIN_DISTINCT_DISPATCHES = 2

# Pinned rejection message templates (#1461 plan) — each names the problem
# and ends in a stated next action. The hash-mismatch message (_BLOCK_MESSAGE
# above) is unchanged/untouched; these four are additive, dispatch-ledger-
# corroboration-specific rejections.
_NO_DISPATCH_MESSAGE = (
    f"BLOCKED: No genuine review-agent dispatch found in the last "
    f"{WINDOW_SECONDS}s — run /code-review before committing.\n"
)

_STALE_MESSAGE = (
    f"BLOCKED: Review-agent dispatch evidence found but outside the "
    f"{WINDOW_SECONDS}s window — run /code-review again before committing.\n"
)

_READ_FAILURE_MESSAGE = (
    "BLOCKED: Could not read the dispatch ledger "
    "(.claude/metrics/boundary-events.jsonl) — check hook registration; "
    "this is an infra problem, not evidence that no review happened.\n"
)


def _insufficient_message(n: int) -> str:
    return (
        f"BLOCKED: Only {n} distinct review agent(s) dispatched (need >= "
        f"{_MIN_DISTINCT_DISPATCHES}) — run /code-review before committing.\n"
    )


def _emit_block(message: str) -> None:
    """Write a block message to both stdout and stderr (#1367).

    Stdout stays the canonical UI channel; stderr is mirrored because some
    hook-error wrappers surface only stderr on a nonzero hook exit.
    """
    sys.stdout.write(message)
    sys.stderr.write(message)


def _staged_names() -> list[str]:
    try:
        completed = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            check=False,
            text=True,
        )
    except (FileNotFoundError, OSError):
        return []
    if completed.returncode != 0:
        return []
    return [line for line in completed.stdout.splitlines() if line]


def _current_branch() -> str:
    try:
        completed = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            check=False,
            text=True,
        )
    except (FileNotFoundError, OSError):
        return ""
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def _plugin_version() -> str:
    manifest = _HOOK_DIR / ".." / ".claude-plugin" / "plugin.json"
    try:
        data = json.loads(manifest.read_text())
        version = data.get("version")
        if isinstance(version, str) and version:
            return version
    except (OSError, ValueError):
        pass
    return "unknown"


def _record_bypass_audit(flag: str, reason: str, staged_count: int, cwd: str) -> None:
    """Append one accountability line to <project-root>/.claude/metrics/gate-bypass-audit.jsonl.

    Unconditional (not gated by DEV_TEAM_TELEMETRY) — mirrors the existing
    metrics/override-audit.jsonl precedent for a bypass a human/agent
    actively chose, not passive usage telemetry.

    Resolves against `cwd` (the payload's project cwd) via the shared
    artifact_paths helper — not a bare relative path, which previously
    resolved against the process's real OS cwd and could disagree with the
    project root when this hook is invoked from a subdirectory. Fail-open:
    any failure to resolve the path, create the directory, or write the
    line logs a diagnostic to stderr and never blocks the commit.
    """
    entry = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "branch": _current_branch(),
        "triggeredBy": flag,
        "reason": reason,
        "stagedFileCount": staged_count,
        "pluginVersion": _plugin_version(),
    }
    try:
        audit_log_path = _resolve_file("metrics", "gate-bypass-audit.jsonl", cwd)
        audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(audit_log_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, separators=(",", ":")) + "\n")
    except OSError as exc:
        sys.stderr.write(f"[pre_commit_review] failed to record bypass audit: {exc}\n")


class GateVerdict:
    """One evaluated outcome of `_evaluate_gate`: whether the gate passes,
    and — when it doesn't — the message and `matched_rule` to report."""

    __slots__ = ("passed", "message", "matched_rule")

    def __init__(self, passed: bool, message: str = "", matched_rule: str = "") -> None:
        self.passed = passed
        self.message = message
        self.matched_rule = matched_rule


def _evaluate_gate(gate_file: Path, current_hash: str, cwd: str) -> GateVerdict:
    """Decide whether `.review-passed` corroborates a genuine, recent,
    multi-agent review (#1461) — extracted from `main()` so the decision
    logic is unit-testable independent of stdin/subprocess plumbing.

    The existing hash-match check is preserved unchanged and evaluated
    FIRST, independent of dispatch-ledger evidence — a hash mismatch (or a
    missing/unreadable gate file) always rejects with the original,
    untouched `_BLOCK_MESSAGE`/`"pre-commit-review"` rule, regardless of how
    much genuine dispatch evidence exists (Gherkin: "Gate still rejects on
    hash mismatch even with ample genuine dispatch evidence"). Only once the
    hash matches does this function consult the dispatch ledger — as
    additive corroboration, never a substitute for the hash check.
    """
    if not gate_file.is_file():
        return GateVerdict(False, _BLOCK_MESSAGE, "pre-commit-review")
    try:
        stored = gate_file.read_text().strip()
    except OSError:
        stored = ""
    if not stored or stored != current_hash:
        return GateVerdict(False, _BLOCK_MESSAGE, "pre-commit-review")

    # Hash matches — everything from here on is the dispatch-ledger
    # corroboration path (#1461 security review): wrapped in its own
    # exception handler so this stays fail-CLOSED on any unexpected error
    # (a stat race if the gate file is unlinked between is_file() and
    # stat(), an out-of-range mtime, a malformed timestamp, a MemoryError
    # from an oversized ledger, ...) — none of those should silently fall
    # through to main()'s top-level `except Exception: sys.exit(0)`, which
    # would convert a should-reject into an allow. Contrast with
    # `emit_boundary_event`'s write-side fail-open: this is the read/verdict
    # side, and it must never let "something went wrong evaluating
    # corroboration" look the same as "corroboration passed".
    try:
        # Anchor the recency window on the gate file's OWN mtime, not "when
        # the diff was staged" (git has no such native value). A later
        # rewrite of .review-passed (new mtime, no fresh dispatch) is
        # therefore evaluated against ITS OWN new anchor, never the original
        # write's — so a hash rewrite alone is never itself dispatch
        # evidence.
        before_ts = _mtime_to_iso(gate_file.stat().st_mtime)

        if _has_doc_only_exemption(cwd, before_ts, WINDOW_SECONDS, current_hash):
            return GateVerdict(True)
        if _has_single_agent_exemption(cwd, before_ts, WINDOW_SECONDS, current_hash):
            return GateVerdict(True)

        evidence = _evaluate_ledger(cwd, before_ts, WINDOW_SECONDS, current_hash)
        if evidence.read_failure_reason is not None:
            return GateVerdict(False, _READ_FAILURE_MESSAGE, "dispatch-ledger-read-failure")

        n = len(evidence.agents_in_window)
        if n >= _MIN_DISTINCT_DISPATCHES:
            return GateVerdict(True)
        if n >= 1:
            return GateVerdict(
                False, _insufficient_message(n), "dispatch-evidence-insufficient"
            )
        if evidence.any_dispatch_ever:
            return GateVerdict(False, _STALE_MESSAGE, "dispatch-evidence-stale")
        return GateVerdict(False, _NO_DISPATCH_MESSAGE, "dispatch-evidence-missing")
    except Exception:  # noqa: BLE001 - fail CLOSED: an unexpected error is not a pass
        return GateVerdict(False, _READ_FAILURE_MESSAGE, "dispatch-ledger-read-failure")


def main() -> int:
    payload = read_stdin_json()
    if payload is None:
        return 0

    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return 0
    command = str(tool_input.get("command") or "")

    cwd = payload.get("cwd") or "."
    session_id = payload.get("session_id")

    if not is_git_commit_command(command):
        return 0

    staged = _staged_names()
    # Nothing staged → nothing to gate.
    if not staged:
        return 0

    if has_bypass_flag(command):
        flag = bypass_flag_name(command) or "--no-verify"
        reason = os.environ.get("GATE_BYPASS_REASON", "").strip()
        if reason:
            _record_bypass_audit(flag, reason, len(staged), cwd)
            emit_boundary_event(
                cwd, "pre_commit_review", "Bash", "bypass", flag, session_id
            )
            return 0
        _emit_block(_BYPASS_BLOCK_MESSAGE)
        return 2

    current_hash = review_gate_hash(cwd)

    # Resolved via the shared artifact_paths helper (#1461 security review),
    # not a bare relative path — the latter resolves against the process's
    # real OS cwd, which can silently disagree with `cwd` (the payload's
    # project root) when this hook runs from a subdirectory. This now
    # matters beyond cosmetics: the gate file's mtime anchors the dispatch-
    # ledger recency window, and the ledger itself resolves through this
    # same helper — a root mismatch here would let the two silently compare
    # against different projects.
    gate_file = _resolve_file("memory", ".review-passed", cwd)
    gate_file.parent.mkdir(parents=True, exist_ok=True)

    verdict = _evaluate_gate(gate_file, current_hash, cwd)
    if verdict.passed:
        # Review passed for these exact files, corroborated by genuine
        # dispatch evidence (or a doc-only exemption) — consume + allow.
        try:
            gate_file.unlink()
        except OSError:
            pass
        return 0

    # Block. Message goes to stdout (matching the .sh's `printf` — the .sh
    # writes to stdout, not stderr, so Claude sees it in the tool-call
    # feedback stream).
    _emit_block(verdict.message)
    emit_boundary_event(
        cwd, "pre_commit_review", "Bash", "block", verdict.matched_rule, session_id
    )
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001 - fail-open: a hook bug must never block a commit
        sys.exit(0)
