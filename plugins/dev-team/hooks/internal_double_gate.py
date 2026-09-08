#!/usr/bin/env python3
"""internal_double_gate — Claude Code PreToolUse:Bash hook (#2128).

Wires `skills/test-design/scripts/internal_double_detector.py` (#2127) into
a blocking position: an unwaived `high`-severity internal-collaborator
double, found among the files changed in the current branch's diff, blocks
`gh pr create` until it's fixed or waived.

Same trigger point as `hooks/pre_pr_review.py`
(`gh_pr_create_detect.is_gh_pr_create_command`) — issue #2128's own body
cites `hooks/pre_commit_review.py` as precedent, but that file is a
documented no-op superseded by `pre_pr_review.py` per #1886 (the review
gate moved from `git commit` to `gh pr create` time). This hook follows
`pre_pr_review.py`'s actual current architecture instead.

**Scoped for precision, not completeness — by design, not by accident.**
Only `high` findings among files changed in the branch diff are grounds to
block (`internal_double_detector.changed_files_since`/`analyze_since`
filter the findings, not the scan — `analyze()` itself still walks the
whole tree every run, so this scoping buys precision, not latency: don't
describe it as a speed optimization). This hook is NOT the correctness
backstop: the required `"Plugin content & hooks"` CI check
(`plugins/dev-team/tests/skills/test_internal_double_detector.py::
test_full_repo_scan_has_no_high_severity_findings`) re-resolves the full
first-party index and re-scans every test file, unfiltered, on every PR —
including the one case this hook cannot see (a `high` finding whose target
collaborator only just became resolvable because of a *new production
file* in this same diff, while the double's own test file is untouched).
That disclosed gap is why both enforcement points exist; this hook's block
message says so rather than implying it is the only guarantee.

On any setup failure — base-ref resolution fails, the branch-diff git call
itself fails independently of that, or the detector module cannot be
imported at all — this hook ALWAYS fails open to no-block (an ADVISORY
line, exit 0). It never falls back to evaluating the unfiltered/unscoped
findings as grounds to block: that would block on files the current PR
never touched, inverting the whole point of scoping. (Contrast this with
`internal_double_detector.py`'s own `--changed-since --strict` CLI flag,
which deliberately makes the OPPOSITE choice on a git failure — falling
back to the unscoped result for a human running the CLI interactively, who
can read the ADVISORY and judge for themselves. That CLI-only exception is
tested in `test_internal_double_detector.py` and never applies here.)

Bypass: `INTERNAL_DOUBLE_GATE_BYPASS_REASON` (non-empty) allows the PR and
is audit-logged to the SAME `.claude/metrics/gate-bypass-audit.jsonl`
stream `pre_pr_review.py` writes to (distinguished by `triggeredBy`) —
established shared-stream convention, not a new audit file per gate.

Contract (docs/python-hook-contract.md):
    Input : PreToolUse JSON on stdin
    Exit 0: allow the tool call (silent-pass, or an ADVISORY line)
    Exit 2: block the tool call (feedback returned to Claude on stdout,
            mirrored to stderr)

Stdlib-only.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_HOOK_DIR = Path(__file__).resolve().parent
_PLUGIN_DIR = _HOOK_DIR.parent
_LIB_DIR = _HOOK_DIR / "lib"

sys.path.insert(0, str(_LIB_DIR))
try:
    from stdin_json import read_stdin_json  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - fallback keeps the hook self-contained

    def read_stdin_json() -> dict | None:  # type: ignore[misc]
        try:
            return json.loads(sys.stdin.read() or "{}")
        except (ValueError, OSError):
            return None


try:
    from gh_pr_create_detect import (  # type: ignore[import-not-found]
        is_gh_pr_create_command,
    )
except ImportError:  # pragma: no cover - degraded fallback: never trigger

    def is_gh_pr_create_command(_command: str) -> bool:  # type: ignore[misc]
        return False


try:
    from review_gate_hash import default_base_ref  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - degraded fallback: always advisory

    def default_base_ref(_cwd=None):  # type: ignore[misc]
        return None


try:
    from boundary_events import (  # type: ignore[import-not-found]
        emit_boundary_event as _emit_boundary_event,
    )
except ImportError:  # pragma: no cover

    def _emit_boundary_event(*_args, **_kwargs) -> None:  # type: ignore[misc]
        return None


def emit_boundary_event(*args, **kwargs) -> None:
    """Local safety net (#859): even a misbehaving helper must never affect
    this hook's exit code, stdout, or stderr."""
    try:
        _emit_boundary_event(*args, **kwargs)
    except Exception:  # noqa: BLE001, S110 - fail-open by design
        pass


try:
    from atomic_state import (  # type: ignore[import-not-found]
        append_line_locked,
    )
except ImportError:  # pragma: no cover

    def append_line_locked(  # type: ignore[misc]
        path: Path, line: str, *, delay_env_var=None, fail_open: bool = True
    ) -> None:
        if not fail_open:
            raise OSError("atomic_state unavailable (degraded import)")


try:
    from artifact_paths import (
        resolve_file as _resolve_file,  # type: ignore[import-not-found]
    )
except ImportError:  # pragma: no cover

    def _resolve_file(category, filename, root=None):  # type: ignore[misc]
        return Path(root or ".") / ".claude" / category / filename


# The detector lives with the test-design skill, not hooks/lib — this hook
# reuses it rather than keeping a second, drifting copy of the extraction
# logic (same reuse convention `stryker_xunit_shim_guard.py` follows for
# `xunit_v3_feature_detector`, from `skills/mutation-testing/scripts`).
_DETECTOR_DIR = _PLUGIN_DIR / "skills" / "test-design" / "scripts"
if str(_DETECTOR_DIR) not in sys.path:
    sys.path.insert(0, str(_DETECTOR_DIR))

try:
    from internal_double_detector import (  # type: ignore[import-not-found]
        _RECALL_BOUNDS_STATEMENT,
        analyze_since,
    )
except ImportError:  # pragma: no cover - degraded fallback, skill tree unreachable

    def analyze_since(_root, _ref):  # type: ignore[misc]
        return [], "internal_double_detector unavailable"

    _RECALL_BOUNDS_STATEMENT = ""  # type: ignore[misc]


def _record_bypass_audit(reason: str, cwd: str) -> None:
    """Append one accountability line to the SAME
    `.claude/metrics/gate-bypass-audit.jsonl` stream `pre_pr_review.py`
    writes to, distinguished by `triggeredBy`. Fail-open: any failure to
    resolve the path, create the directory, or write the line logs a
    diagnostic to stderr and never blocks the PR."""
    entry = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "hook": "internal_double_gate",
        "triggeredBy": "INTERNAL_DOUBLE_GATE_BYPASS_REASON",
        "reason": reason,
        "cwd": cwd,
    }
    try:
        audit_log_path = _resolve_file("metrics", "gate-bypass-audit.jsonl", cwd)
        audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        append_line_locked(
            audit_log_path,
            json.dumps(entry, separators=(",", ":")) + "\n",
            fail_open=False,
        )
    except OSError as exc:
        sys.stderr.write(f"[internal_double_gate] failed to record bypass audit: {exc}\n")


def _emit_block(message: str) -> None:
    sys.stdout.write(message)
    sys.stderr.write(message)


def _block_message(high_findings: list[dict]) -> str:
    lines = "\n".join(f["message"] for f in high_findings)
    return (
        "[BLOCK] internal-double-gate: unwaived internal-collaborator "
        "double(s) in this diff\n\n"
        f"{lines}\n\n"
        f"{_RECALL_BOUNDS_STATEMENT}\n\n"
        "This hook only flags findings among files changed in this diff; "
        "the required \"Plugin content & hooks\" CI check re-scans the "
        "whole repo unfiltered on every PR and is the actual completeness "
        "guarantee, not this hook. Fix the double, or add an inline "
        "`double-waiver: B<n> — <reason>` comment naming one of the three "
        "blockers — see knowledge/internal-collaborator-doubling.md.\n\n"
        "To bypass this gate for a legitimate exception, set "
        "INTERNAL_DOUBLE_GATE_BYPASS_REASON in the environment "
        "(audit-logged)."
    )


def _evaluate(cwd: str, base_ref: str | None) -> tuple[int, str]:
    """Core evaluation, callable directly (no stdin/exit) so it's testable
    without going through `main()`. Returns (exit_code, message) — message
    may be empty (true silent-pass), an ADVISORY line (exit 0, printed),
    or a [BLOCK] body (exit 2, printed to stdout+stderr by the caller)."""
    if base_ref is None:
        message = (
            "ADVISORY: internal-double-gate: could not resolve the "
            "branch's base ref — gate not enforced this run"
        )
        return 0, message

    try:
        findings, reason = analyze_since(Path(cwd), base_ref)
    except Exception as exc:  # noqa: BLE001 - fail-open: a detector bug must
        # always surface as ADVISORY, never as silence AND never as a block.
        # Without this boundary, any exception other than the three named
        # setup failures above would propagate to main()'s own top-level
        # `except Exception: sys.exit(0)` — still non-blocking, but with NO
        # stdout at all, leaving no signal that the gate didn't run.
        message = (
            f"ADVISORY: internal-double-gate: detector raised {exc!r} — "
            "gate not enforced this run"
        )
        return 0, message
    if reason is not None:
        message = (
            f"ADVISORY: internal-double-gate: {reason} — gate not "
            "enforced this run (never falls back to blocking on the "
            "unscoped/unfiltered result)"
        )
        return 0, message

    high = [f for f in findings if f["verdict"] == "high"]
    if not high:
        return 0, ""

    return 2, _block_message(high)


def main() -> int:
    payload = read_stdin_json()
    if payload is None:
        return 0

    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return 0
    command = str(tool_input.get("command") or "")

    if not is_gh_pr_create_command(command):
        return 0

    cwd = payload.get("cwd") or "."
    session_id = payload.get("session_id")

    reason = os.environ.get("INTERNAL_DOUBLE_GATE_BYPASS_REASON", "").strip()
    if reason:
        _record_bypass_audit(reason, cwd)
        emit_boundary_event(
            cwd, "internal_double_gate", "Bash", "bypass",
            "INTERNAL_DOUBLE_GATE_BYPASS_REASON", session_id,
        )
        return 0

    base_ref = default_base_ref(cwd)
    exit_code, message = _evaluate(cwd, base_ref)

    if exit_code == 2:
        _emit_block(message)
        emit_boundary_event(
            cwd, "internal_double_gate", "Bash", "block",
            "unwaived-high-finding", session_id,
        )
    elif message:
        print(message)

    return exit_code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001 - fail-open: a hook bug must never block a PR
        sys.exit(0)
