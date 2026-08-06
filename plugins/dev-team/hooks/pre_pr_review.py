#!/usr/bin/env python3
"""pre_pr_review — Claude Code PreToolUse:Bash hook (#1886).

Successor to `hooks/pre_commit_review.py`'s review-corroboration gate.
Design decision (issue #1886, resolved): the gate moves from `git commit` to
`gh pr create` — a branch is now free to accumulate any number of local
commits without paying the review-panel cost at each one; the hard block
fires once, against the branch's FULL diff vs. its base, at PR-creation
time.

WHY A NEW MODULE RATHER THAN REPURPOSING `pre_commit_review.py` IN PLACE
(documenting the choice the issue explicitly left open): `pre_commit_review.py`
grew, across #1461/#1476/#1627/#1763/#1801 and further re-reviews, an enormous
amount of machinery specific to `git commit`'s command shape — per-target
`-C`/`--git-dir`/`--work-tree` resolution, `-a`/pathspec-form-commit detection,
cosmetic-delta carry-forward across re-stages, and a `--no-verify`/`-n`
flag-based bypass. None of that transfers to `gh pr create`, which has no `-C`
equivalent, no pathspec-commit-shaped ambiguity, and no native
`--no-verify`-shaped flag to key a bypass off. Reusing that file's own
git-commit-specific detector/hash pair in place would have meant either
carrying dead complexity forward or performing a much larger, riskier
in-place rewrite than standing up a new, deliberately leaner module that
reuses the SHARED library pieces (`review_gate_hash.py`,
`review_gate_corroboration.py`, `boundary_events.py`, `atomic_state.py`,
`artifact_paths.py`) both hooks depend on. `pre_commit_review.py` itself is
now a documented no-op (see its own module docstring) rather than deleted,
since deleting it would strand the many docs/tests/skills that still name it
in prose describing this exact migration.

WHAT CHANGED, MECHANICALLY, FROM THE COMMIT-TIME GATE:

- **Trigger**: `gh pr create` (`hooks/lib/gh_pr_create_detect.py`) instead of
  `git commit`. Any other Bash command passes through immediately (exit 0).
- **Hash**: `hooks/lib/review_gate_hash.py`'s `branch_diff_gate_hash(base_ref,
  cwd)` — `git diff <base>...HEAD`, the WHOLE branch diff against its
  merge-base with the resolved default branch (`default_base_ref()`) —
  instead of `git diff --cached` (one commit's staged patch).
- **Recency window anchor**: `before_ts` is the CURRENT time at
  `gh pr create` invocation, not a gate file's own mtime (design decision,
  #1886: "anchor to before PR creation"). A multi-commit branch may have been
  reviewed well before its final commit; anchoring on "now" rather than on
  when some earlier `/code-review` run happened to write the gate file means
  the window's only real question is "did genuine, distinct review-agent
  dispatches occur recently, for THIS exact branch-diff content" — not "did
  they happen within `WINDOW_SECONDS` of an arbitrary earlier file write".
- **Gate file**: `.claude/memory/.pr-review-passed` (new; distinct from
  `.claude/memory/.review-passed`, whose only remaining writer/reader is now
  historical prose — see `pre_commit_review.py`'s docstring).
- **Bypass**: `PR_GATE_BYPASS_REASON` (an env var, not a `--no-verify`/`-n`
  command-line flag — `gh pr create` has no such native flag to key off).
  Mirrors #709's pattern for the ORIGINAL commit-time gate: when set to a
  non-empty value, the PR is allowed and the bypass is durably logged to
  `.claude/metrics/gate-bypass-audit.jsonl` (the SAME stream, distinguished
  by `triggeredBy: "PR_GATE_BYPASS_REASON"`); when unset, the ordinary gate
  evaluation applies — there is no separate "you tried to bypass but forgot
  the reason" message, because there is no separate flag to detect trying
  without one.

WHAT DID NOT CHANGE: the underlying corroboration architecture is reused
as-is from `hooks/lib/review_gate_corroboration.py` — >= 2 distinct,
registered review-agent dispatches (or a sanctioned doc-only/single-agent
exemption) recorded in the recency window, live-registry re-validated, with
the same #1763 dispatch-failure veto taking priority over every exemption.
See that module's own docstring for the full account of why this raises the
bar without cryptographically closing #1461's self-certification gap.

DELIBERATELY DROPPED, not carried forward from `pre_commit_review.py`
(explicit scope decisions, not oversights):

1. **Cosmetic-delta carry-forward** (#1627): existed to stop a whitespace-only
   re-stage from forcing a fresh review-agent dispatch before the NEXT commit.
   That friction was a direct consequence of gating every commit; since this
   gate fires once, at PR-creation time, against the branch's cumulative
   diff, the scenario it existed to relieve no longer arises here.
2. **Multi-target `-C`/`--git-dir`/`--work-tree` resolution** (#1801): a
   `git commit` can retarget which repository it commits to; `gh pr create`
   has no equivalent multi-repository ambiguity — it always targets the
   current repository's configured remote.
3. **`-a`/pathspec-form-commit detection** (#1476): specific to `git commit`
   committing tracked-file changes that were never `git add`-ed; has no
   `gh pr create` analogue (a PR is always opened against whatever is
   already committed to the branch).

CLOSED (#1886 follow-up, extended by #1904 Bug 2b): `skills/code-review/SKILL.md`
step 9 WRITES `.claude/memory/.pr-review-passed` with a hash bound to the
branch diff (`branch_diff_gate_hash(default_base_ref(cwd), cwd)`, via this
module's own `review_gate_hash.py --branch-diff` CLI mode), for an
auto-scoped uncommitted-changes review OR a `--since <base>`-scoped one
that passed — the latter is the shape `/pr`'s own `/code-review --since
"$BASE" --json` call actually takes, the only real path to `gh pr create`.
`review_gate_hash.py`'s sibling `review_gate_hash()` (the staged-diff hash)
is no longer written to any gate file at all — `.review-passed` is retired.
`hooks/agent_dispatch_ledger.py` now stamps a dispatch's `subject_hash` with
this same branch-diff hash whenever nothing is staged (the routine state
during a `--since <base>`-scoped review, since `/pr`'s step 1 requires a
clean working tree first) — closing the mismatch for that shape completely,
since every dispatch during it and step 9's own write agree on one content
domain.

KNOWN RESIDUAL GAP, disclosed rather than silently accepted (narrower than
before #1904, still out of this fix's own scope): for an **auto-scoped
uncommitted-changes** review, `agent_dispatch_ledger.py` still stamps the
staged-diff hash (something IS staged in that mode), which is mathematically
identical to step 9's branch-diff write only in the common
single-commit-then-PR shape (a branch cut from its base, reviewed once while
staged, committed, then a PR opened immediately). On a branch with multiple
separate review-and-commit cycles in THAT mode, the branch-diff hash written
at step 9 won't match an earlier cycle's dispatch `subject_hash`, and this
gate correctly falls through to the "no dispatch found" block on a real
`gh pr create`, requiring a fresh `/code-review` run — a `--since <base>`
re-review now closes cleanly per the paragraph above, or the audited
`PR_GATE_BYPASS_REASON` escape hatch remains available — before it opens.

`gh_pr_create_detect.is_gh_pr_create_command`'s own docstring discloses its
detection gap (no `<shell> -c` unwrapping, no command-substitution
unwrapping, ...) — a much lighter heuristic than
`pre_commit_detect.is_git_commit_command`'s five-round-hardened one; see
that module's own docstring for why that difference is a deliberate,
disclosed scope decision, not an oversight.

Contract (docs/python-hook-contract.md):
    Input : JSON on stdin (Claude Code PreToolUse:Bash payload)
    Exit 0: allow the tool call
    Exit 2: block the tool call (feedback returned to Claude on stdout,
            mirrored to stderr — see `_emit_block`)

Stdlib-only.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# The digest `sha256(b"")` produces — never treated as a valid subject-hash
# match here (issue #1904 Bug 1). Computed locally via hashlib rather than
# imported from `review_gate_hash.EMPTY_DIGEST` so this constant is available
# even on the degraded-import fallback path below.
_EMPTY_DIGEST = hashlib.sha256(b"").hexdigest()

_HOOK_DIR = Path(__file__).resolve().parent
_LIB_DIR = _HOOK_DIR / "lib"

sys.path.insert(0, str(_LIB_DIR))
try:
    from artifact_paths import (
        resolve_file as _resolve_file,  # type: ignore[import-not-found]
    )
    from atomic_state import (  # type: ignore[import-not-found]
        append_line_locked as _append_line_locked,
    )
    from boundary_events import (  # type: ignore[import-not-found]
        emit_boundary_event as _emit_boundary_event,
    )
    from gh_pr_create_detect import (  # type: ignore[import-not-found]
        is_gh_pr_create_command,
    )
    from git_safe_diff import run_safe_git_diff  # type: ignore[import-not-found]
    from pre_commit_doc_classifier import (  # type: ignore[import-not-found]
        is_doc_only_changeset as _is_doc_only_changeset,
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
    from review_gate_hash import (  # type: ignore[import-not-found]
        branch_diff_gate_hash,
        default_base_ref,
    )
    from stdin_json import read_stdin_json  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - degraded-import fallback

    def read_stdin_json() -> dict | None:  # type: ignore[misc]
        return None

    def is_gh_pr_create_command(_command: str) -> bool:  # type: ignore[misc]
        return False

    def _resolve_file(  # type: ignore[misc]
        category: str, filename: str, root=None, migrate: bool = True
    ) -> Path:
        repo_root = Path(__file__).resolve().parents[3]
        return repo_root / ".claude" / category / filename

    def _emit_boundary_event(*_args, **_kwargs) -> None:  # type: ignore[misc]
        return None

    def _append_line_locked(  # type: ignore[misc]
        path: Path, line: str, *, delay_env_var=None, fail_open: bool = True
    ) -> None:
        # Degraded-import fallback: atomic_state itself couldn't be
        # imported, so no hardened append is available. Unlike the OLD
        # pre_commit_review.py fallback this replaces, this does NOT fall
        # back to a plain unlocked `open(path, "a")` (#1904 item 5's own
        # disclosed gap for that pattern) — a failed audit write is already
        # fail-open by design (a bypass proceeds either way), so degrading
        # further to "don't write at all" costs nothing beyond the audit
        # trail entry itself, and avoids reintroducing the O_NOFOLLOW gap
        # the shared helper exists to close.
        if not fail_open:
            raise OSError("atomic_state unavailable (degraded import)")

    def run_safe_git_diff(extra_flags, cwd=None, text=False, target=None):  # type: ignore[misc]
        raise OSError("git_safe_diff unavailable (degraded import)")

    def _is_doc_only_changeset(files: list[str]) -> bool:  # type: ignore[misc]
        return False

    def branch_diff_gate_hash(base_ref: str, cwd=None) -> str:  # type: ignore[misc]
        return ""

    def default_base_ref(cwd=None) -> str:  # type: ignore[misc]
        return "HEAD"

    class _DegradedLedgerEvidence:  # type: ignore[misc]
        agents_in_window: frozenset = frozenset()
        any_dispatch_ever = False
        same_subject_dispatch_ever = False
        read_failure_reason = "unreadable"
        dispatch_failure_agents: frozenset | None = None

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


def emit_boundary_event(*args, **kwargs) -> None:
    """Local safety net (#859): even a misbehaving helper must never affect
    this hook's exit code, stdout, or stderr."""
    try:
        _emit_boundary_event(*args, **kwargs)
    except Exception:  # noqa: BLE001, S110 - fail-open by design
        pass


_GATE_FILE_NAME = ".pr-review-passed"

_BLOCK_MESSAGE = (
    "BLOCKED: Code review required before opening a PR.\n"
    "\n"
    "Run /code-review scoped to this branch's diff vs. its base, then\n"
    "retry `gh pr create` — the PR will be allowed once review passes.\n"
    "\n"
    "To bypass: set PR_GATE_BYPASS_REASON to a non-empty reason.\n"
)

# Recency window (#1886, mirrors #1461's WINDOW_SECONDS): how far back before
# `gh pr create`'s own invocation time a genuine review-agent dispatch still
# counts as corroborating evidence. Anchored on NOW (see module docstring's
# "Recency window anchor" bullet), not a gate file's mtime.
WINDOW_SECONDS = 1800

_MIN_DISTINCT_DISPATCHES = 2

_NO_DISPATCH_MESSAGE = (
    f"BLOCKED: No genuine review-agent dispatch found in the last "
    f"{WINDOW_SECONDS}s — run /code-review (scoped to this branch's diff "
    f"vs. its base) before opening a PR.\n"
    "\n"
    "To bypass: set PR_GATE_BYPASS_REASON to a non-empty reason.\n"
)

_STALE_MESSAGE = (
    f"BLOCKED: Review-agent dispatch evidence found but outside the "
    f"{WINDOW_SECONDS}s window — run /code-review again before opening a "
    "PR.\n"
    "\n"
    "To bypass: set PR_GATE_BYPASS_REASON to a non-empty reason.\n"
)

_DIFFERENT_CONTENT_MESSAGE = (
    "BLOCKED: Review-agent dispatch evidence found, but for different "
    "branch-diff content (the branch changed since that review) — run "
    "/code-review again before opening a PR.\n"
    "\n"
    "To bypass: set PR_GATE_BYPASS_REASON to a non-empty reason.\n"
)

_READ_FAILURE_MESSAGE = (
    "BLOCKED: Could not read the dispatch ledger "
    "(.claude/metrics/boundary-events.jsonl) — check hook registration; "
    "this is an infra problem, not evidence that no review happened.\n"
    "\n"
    "To bypass: set PR_GATE_BYPASS_REASON to a non-empty reason.\n"
)

_GATE_SETUP_FAILURE_MESSAGE = (
    "BLOCKED: Could not determine the review-gate's own state (the branch "
    "diff or the .claude/memory/.pr-review-passed path) — check that "
    ".claude/memory is a writable directory and the git repository is "
    "healthy; this is an infra problem, not evidence that no review "
    "happened.\n"
    "\n"
    "To bypass: set PR_GATE_BYPASS_REASON to a non-empty reason.\n"
)

_REGISTRY_READ_FAILURE_MESSAGE = (
    "BLOCKED: Could not read the registered review-agent set — cannot "
    "prove no dispatch failure exists for this content; this is an infra "
    "problem, not evidence that no review happened.\n"
    "\n"
    "To bypass: set PR_GATE_BYPASS_REASON to a non-empty reason.\n"
)


def _insufficient_message(n: int) -> str:
    return (
        f"BLOCKED: Only {n} distinct review agent(s) dispatched (need >= "
        f"{_MIN_DISTINCT_DISPATCHES}) — run /code-review before opening a "
        "PR.\n"
        "\n"
        "To bypass: set PR_GATE_BYPASS_REASON to a non-empty reason.\n"
    )


def _dispatch_failure_message(agents: frozenset) -> str:
    names = ", ".join(sorted(agents)) or "an unnamed review agent"
    return (
        f"BLOCKED: Dispatch failure recorded for {names} — this is a "
        "dispatch/infra failure, not a code-review finding.\n"
        "\n"
        "Run /code-review again against this same, unchanged branch diff — "
        "a clean rerun clears this block.\n"
        "\n"
        "To bypass: set PR_GATE_BYPASS_REASON to a non-empty reason.\n"
    )


def _emit_block(message: str) -> None:
    sys.stdout.write(message)
    sys.stderr.write(message)


def _branch_diff_names(base_ref: str, cwd: str | None) -> list[str] | None:
    """Return the branch-diff file list (`git diff <base>...HEAD
    --name-only`), or `None` when git could not be asked at all — same
    `None`-means-"couldn't determine" contract `pre_commit_review.py`'s own
    `_staged_names()` established."""
    try:
        completed = run_safe_git_diff(
            ["--name-only"], cwd=(cwd or None), text=True, target=f"{base_ref}...HEAD"
        )
    except Exception:  # noqa: BLE001 - "couldn't determine", not "nothing changed"
        return None
    if completed.returncode != 0:
        return None
    return [line for line in completed.stdout.splitlines() if line]


def _current_branch(cwd: str | None = None) -> str:
    try:
        completed = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=cwd or None,
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


def _record_bypass_audit(reason: str, file_count: int, cwd: str) -> None:
    """Append one accountability line to
    <project-root>/.claude/metrics/gate-bypass-audit.jsonl — the SAME
    stream `pre_commit_review.py`'s `--no-verify` bypass used, distinguished
    by `triggeredBy`. Fail-open: any failure to resolve the path, create the
    directory, or write the line logs a diagnostic to stderr and never
    blocks the PR."""
    entry = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "branch": _current_branch(cwd),
        "triggeredBy": "PR_GATE_BYPASS_REASON",
        "reason": reason,
        "stagedFileCount": file_count,
        "pluginVersion": _plugin_version(),
    }
    try:
        audit_log_path = _resolve_file("metrics", "gate-bypass-audit.jsonl", cwd)
        audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        _append_line_locked(
            audit_log_path,
            json.dumps(entry, separators=(",", ":")) + "\n",
            fail_open=False,
        )
    except OSError as exc:
        sys.stderr.write(f"[pre_pr_review] failed to record bypass audit: {exc}\n")


class GateVerdict:
    __slots__ = ("matched_rule", "message", "passed")

    def __init__(self, passed: bool, message: str = "", matched_rule: str = "") -> None:
        self.passed = passed
        self.message = message
        self.matched_rule = matched_rule


def _stored_gate_hash(gate_file: Path) -> str:
    """Read `.pr-review-passed`'s single line: the raw branch-diff hash.

    Fails CLOSED on ANY read/decode error (mirrors `pre_commit_review.py`'s
    own `_stored_gate_hashes()` — an unreadable gate file is not a pass).
    """
    try:
        lines = gate_file.read_text(errors="replace").strip().splitlines()
    except Exception:  # noqa: BLE001 - fail CLOSED
        return ""
    return lines[0].strip() if lines else ""


def _hash_verdict(gate_file: Path, current_hash: str) -> GateVerdict | None:
    """Lens: the hash-match check, evaluated first — a mismatch (or a
    missing/unreadable gate file) always rejects with `_BLOCK_MESSAGE`,
    regardless of how much genuine dispatch evidence exists.

    `current_hash == _EMPTY_DIGEST` is rejected with `_GATE_SETUP_FAILURE_MESSAGE`
    rather than treated as an ordinary mismatch (issue #1904 Bug 1) — defense
    in depth alongside `_prepare_gate()`'s own guard, which already refuses to
    hand out an empty-digest `current_hash` in the first place, so this branch
    is not expected to fire via `main()`'s normal call path; it exists so a
    future caller of this function directly can't reintroduce the constant-hash
    collapse by skipping `_prepare_gate()`.

    Returns a rejecting `GateVerdict` when the hash doesn't match; `None`
    when it matches, meaning "continue to the dispatch-ledger corroboration
    lenses".
    """
    if current_hash == _EMPTY_DIGEST:
        return GateVerdict(False, _GATE_SETUP_FAILURE_MESSAGE, "gate-setup-failure-empty-digest")
    if not gate_file.is_file():
        return GateVerdict(False, _BLOCK_MESSAGE, "pre-pr-review")
    stored = _stored_gate_hash(gate_file)
    if not stored or stored != current_hash:
        return GateVerdict(False, _BLOCK_MESSAGE, "pre-pr-review")
    return None


def _dispatch_failure_verdict(evidence) -> GateVerdict | None:
    """Lens (#1763, reused as-is): the mechanical dispatch-failure veto.
    Takes priority over every exemption AND the terminal distinct-dispatch
    count."""
    if evidence.dispatch_failure_agents is None:
        return GateVerdict(False, _REGISTRY_READ_FAILURE_MESSAGE, "registry-read-failure")
    if evidence.dispatch_failure_agents:
        return GateVerdict(
            False,
            _dispatch_failure_message(evidence.dispatch_failure_agents),
            "dispatch-failure-veto",
        )
    return None


def _doc_only_exemption_verdict(
    cwd: str, before_ts: str, subject_hash: str, files: list[str]
) -> GateVerdict | None:
    if _has_doc_only_exemption(
        cwd, before_ts, WINDOW_SECONDS, subject_hash
    ) and _is_doc_only_changeset(files):
        return GateVerdict(True)
    return None


def _single_agent_exemption_verdict(
    cwd: str, before_ts: str, subject_hash: str, n: int
) -> GateVerdict | None:
    if n >= 1 and _has_single_agent_exemption(cwd, before_ts, WINDOW_SECONDS, subject_hash):
        return GateVerdict(True)
    return None


def _dispatch_count_verdict(evidence, n: int) -> GateVerdict:
    if n >= _MIN_DISTINCT_DISPATCHES:
        return GateVerdict(True)
    if n >= 1:
        return GateVerdict(False, _insufficient_message(n), "dispatch-evidence-insufficient")
    if evidence.same_subject_dispatch_ever:
        return GateVerdict(False, _STALE_MESSAGE, "dispatch-evidence-stale")
    if evidence.any_dispatch_ever:
        return GateVerdict(
            False, _DIFFERENT_CONTENT_MESSAGE, "dispatch-evidence-different-content"
        )
    return GateVerdict(False, _NO_DISPATCH_MESSAGE, "dispatch-evidence-missing")


def _evaluate_gate(
    gate_file: Path, current_hash: str, cwd: str, files: list[str]
) -> GateVerdict:
    """Decide whether `.pr-review-passed` corroborates a genuine, recent,
    multi-agent review of the branch's full diff vs. its base (#1886).

    A short pipeline over named decision lenses, mirroring
    `pre_commit_review.py`'s own (now-retired) pipeline shape: `_hash_verdict`
    first (always decisive on mismatch), then — only once the hash matches
    and the ledger read succeeds — `_dispatch_failure_verdict`,
    `_doc_only_exemption_verdict`, `_single_agent_exemption_verdict`, and
    finally `_dispatch_count_verdict` as the terminal fallback.
    """
    verdict = _hash_verdict(gate_file, current_hash)
    if verdict is not None:
        return verdict

    try:
        before_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        evidence = _evaluate_ledger(cwd, before_ts, WINDOW_SECONDS, current_hash)
        if evidence.read_failure_reason is not None:
            return GateVerdict(False, _READ_FAILURE_MESSAGE, "dispatch-ledger-read-failure")

        verdict = _dispatch_failure_verdict(evidence)
        if verdict is not None:
            return verdict

        n = len(evidence.agents_in_window)

        verdict = _doc_only_exemption_verdict(cwd, before_ts, current_hash, files)
        if verdict is not None:
            return verdict

        verdict = _single_agent_exemption_verdict(cwd, before_ts, current_hash, n)
        if verdict is not None:
            return verdict

        return _dispatch_count_verdict(evidence, n)
    except Exception:  # noqa: BLE001 - fail CLOSED: an unexpected error is not a pass
        return GateVerdict(False, _READ_FAILURE_MESSAGE, "dispatch-ledger-read-failure")


def _handle_bypass(cwd: str, file_count: int, session_id) -> int | None:
    """`main()` lens: the `PR_GATE_BYPASS_REASON` bypass. Returns 0 when a
    non-empty reason is set (allowing and auditing the bypass); `None`
    otherwise (not applicable — `main()` continues to the normal gate
    evaluation). There is no separate flag to detect "tried to bypass
    without a reason" (see module docstring) — an unset/empty env var simply
    means the ordinary gate applies."""
    reason = os.environ.get("PR_GATE_BYPASS_REASON", "").strip()
    if not reason:
        return None
    _record_bypass_audit(reason, file_count, cwd)
    emit_boundary_event(cwd, "pre_pr_review", "Bash", "bypass", "PR_GATE_BYPASS_REASON", session_id)
    return 0


def _prepare_gate(cwd: str) -> tuple[str, list[str], Path] | None:
    """`main()` lens: resolve the branch's base ref, the current branch-diff
    hash, its file list, and the `.pr-review-passed` gate-file path,
    creating its parent directory. Returns `(current_hash, files, gate_file)`
    on success; `None` on failure (message/event already emitted).

    Two additional failure modes, both issue #1904 Bug 1:

    - `default_base_ref()` returning `None` (the base ref could not be
      resolved at all — a routine state in a shallow/single-branch clone) is
      a hard setup failure, not a reason to fall back to `"HEAD"` and
      evaluate `git diff HEAD...HEAD`, which would succeed with an
      empty-input digest and silently pass the gate.
    - `current_hash == _EMPTY_DIGEST` — whether from the `None`-base-ref
      case above, a genuinely empty branch diff, or any other git failure
      `branch_diff_gate_hash()` fails closed to — is refused outright rather
      than handed to `_hash_verdict()` as an ordinary hash to compare: the
      empty digest is a CONSTANT, and treating it as comparable evidence
      would let one dispatch recorded while nothing was staged corroborate
      any later PR whose gate hash also happens to be empty.
    """
    try:
        base_ref = default_base_ref(cwd)
        if base_ref is None:
            raise OSError("could not resolve the branch's base ref")
        current_hash = branch_diff_gate_hash(base_ref, cwd)
        if current_hash == _EMPTY_DIGEST:
            raise OSError("branch diff hashed to the empty-input digest")
        files = _branch_diff_names(base_ref, cwd)
        if files is None:
            raise OSError("could not determine the branch diff's file list")
        gate_file = _resolve_file("memory", _GATE_FILE_NAME, cwd)
        gate_file.parent.mkdir(parents=True, exist_ok=True)
        return current_hash, files, gate_file
    except Exception:  # noqa: BLE001 - fail CLOSED: setup failure is not a pass
        return None


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

    prepared = _prepare_gate(cwd)

    # Bug 2a (#1904): check the bypass BEFORE a gate-setup failure returns —
    # `_GATE_SETUP_FAILURE_MESSAGE` itself documents `PR_GATE_BYPASS_REASON`
    # as the way out, but that was previously unreachable on this path since
    # `_prepare_gate()`'s failure short-circuited before `_handle_bypass()`
    # ever ran. `-1` (module docstring: "branch diff unavailable") is the
    # sentinel file count for the audit record when setup itself failed —
    # there is no real file list to report a count for.
    file_count = len(prepared[1]) if prepared is not None else -1
    bypass_exit_code = _handle_bypass(cwd, file_count, session_id)
    if bypass_exit_code is not None:
        return bypass_exit_code

    if prepared is None:
        _emit_block(_GATE_SETUP_FAILURE_MESSAGE)
        emit_boundary_event(cwd, "pre_pr_review", "Bash", "block", "gate-setup-failure", session_id)
        return 2
    current_hash, files, gate_file = prepared

    verdict = _evaluate_gate(gate_file, current_hash, cwd, files)
    if verdict.passed:
        try:
            gate_file.unlink()
        except OSError:
            pass
        return 0

    _emit_block(verdict.message)
    emit_boundary_event(cwd, "pre_pr_review", "Bash", "block", verdict.matched_rule, session_id)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001 - fail-open: a hook bug must never block a PR
        sys.exit(0)
