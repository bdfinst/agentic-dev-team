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

COSMETIC-DELTA CARRY-FORWARD (#1627). Hashing the raw staged patch means ANY
re-stage after the corroborating dispatches — a whitespace fix, a markdown
edit alongside code — voids the evidence and forces fresh dispatches that
review nothing new and exist only to feed the ledger; 4 of the last ~5
sessions to reach this gate hit that (#1623 §2). `_cosmetic_carry_forward_verdict()`
adds one lens, evaluated ONLY after `_hash_verdict()` has already rejected on
a raw-hash mismatch: it passes iff `.review-passed`'s optional second line
(the `normalized_gate_hash()` value) equals the one THIS HOOK recomputes from
the current staged content, AND `>= 2` distinct in-window dispatches carry
that same `subject_hash_normalized`. The `>= 2` floor and the recency window
are untouched — only *which* hash binds the evidence changes. This is not a
self-certification hole: the exemption is a property of CONTENT recomputed
here at gate time, not a claim written by the gated party, and the
normalization refuses to treat `agents/`, `skills/`, `.claude/`, `CLAUDE.md`,
string-literal edits, or indentation in indentation-significant languages as
cosmetic. Every pass on this path emits a mandatory
`cosmetic-delta-carry-forward` boundary event. See
`hooks/lib/review_gate_normalized_hash.py` for the full argument.

`git commit -a`/`--all` and pathspec-form commits (e.g. `git commit -am
...` or `git commit path/to/file.txt -m ...`) commit tracked-file changes
that were never staged via `git add` (#1476, closed here). `_staged_names()`
seeing an empty index used to make `main()` return 0 ("nothing to gate")
before any corroboration logic ran — silently skipping this entire
mechanism with no bypass-audit entry. `main()` now also checks
`_working_tree_modified_names()`: when the index is empty but tracked files
differ from HEAD in the working tree, that combination is the `-a`/
pathspec-form-commit signature, and the commit is routed through the exact
same `_evaluate_gate()` pipeline (hash match, dispatch-ledger corroboration,
doc-only/single-agent exemptions) using an EFFECTIVE content hash —
`review_gate_hash.working_tree_gate_hash()`, `git diff HEAD` — instead of
`review_gate_hash()`'s `git diff --cached`, so the hash-binding/
corroboration machinery runs against the content that would actually be
committed rather than exempting it. A genuinely empty commit (nothing
staged AND no tracked-file working-tree changes at all) still passes
through untouched.

KNOWN RESIDUAL GAPS (#1461 security re-review), disclosed rather than
silently accepted:

1. `hooks/agent_dispatch_ledger.py` is itself directly executable from Bash
   with a hand-crafted stdin payload — see that module's own docstring for
   the full account. Locking down `boundary_events.py`'s CLI closed one
   forgery path but not this sibling one; genuine harness-level provenance
   (a signed dispatch receipt) is still needed for full closure and is
   outside this repo's control.
2. The recency window's anchor (`before_ts`, `.claude/memory/.review-passed`'s
   own mtime) is a filesystem timestamp fully controlled by the same party
   the gate constrains — `os.utime()`/`touch -d` can backdate it without
   touching the file's content or hash. Backdating the anchor into the past
   can shift the `WINDOW_SECONDS` window to overlap an old, otherwise-stale
   genuine dispatch for the SAME subject_hash (e.g. a review of this exact
   content from hours ago, correctly rejected today as stale), re-admitting
   it without any ledger forgery. No fix applied here: the mtime anchor is
   also what lets `test_rewritten_gate_file_anchors_on_its_own_new_mtime_not_
   original_dispatch` simulate time passage hermetically (without a real
   `sleep`), so switching to wall-clock `now()` isn't a drop-in improvement —
   it would need a redesign of that test contract too.
3. The `staged is None` fail-closed check runs BEFORE `has_bypass_flag()` in
   `main()`, so a gate-setup failure (corrupt/locked git index) also blocks
   the audited `GATE_BYPASS_REASON` escape hatch — unlike the sibling
   mkdir/hash-resolution failure further down, which still allows the
   audited bypass. Errs toward blocking, never toward a silent allow, but
   the two `gate-setup-failure` sites are inconsistent about whether the
   sanctioned escape stays reachable. Not restructured here to avoid
   weakening the fail-closed guarantee under time pressure.
4. `evidence.same_subject_dispatch_ever` in `review_gate_corroboration.py`
   is computed before the live-registry filter, so a same-subject,
   in-window dispatch whose `matched_rule` is no longer a registered agent
   (renamed/removed) reports `_STALE_MESSAGE` ("outside the window")
   instead of a more accurate "review agent no longer registered" message.
   The gate decision itself is still correctly fail-closed; only the
   operator-facing message and the `dispatch-evidence-stale` audit rule are
   imprecise in this one edge case.

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

Module scope (#1477 structure review): this file is deliberately kept to
the hook stdin/exit-code CONTRACT — stdin parsing, exit codes, and wiring
the pieces below together. The doc-only classification predicate lives in
`hooks/lib/pre_commit_doc_classifier.py` (its shared literal tables in
`hooks/lib/doc_classification.py`, alongside `change_shape.py`'s copy — see
those modules' docstrings), and the security-critical git safety flags
`_staged_names()` needs live in `hooks/lib/git_safe_diff.py`, shared with
`review_gate_hash.py`. `_evaluate_gate()` and `main()` are each a short
pipeline of named decision-lens functions rather than one long branch-laden
body — see each function's own docstring for its lens breakdown.

Stdlib-only.
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
    from git_safe_diff import run_safe_git_diff  # type: ignore[import-not-found]
    from pre_commit_detect import (  # type: ignore[import-not-found]
        bypass_flag_name,
        has_bypass_flag,
        is_git_commit_command,
    )
    from pre_commit_doc_classifier import (  # type: ignore[import-not-found]
        is_doc_only_changeset as _is_doc_only_changeset,
    )
    from review_gate_corroboration import (  # type: ignore[import-not-found]
        distinct_normalized_dispatches as _distinct_normalized_dispatches,
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
    from review_gate_hash import (  # type: ignore[import-not-found]
        review_gate_hash,
        working_tree_gate_hash,
    )
    from review_gate_normalized_hash import (  # type: ignore[import-not-found]
        normalized_gate_hash,
    )
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

    def working_tree_gate_hash(cwd=None) -> str:  # type: ignore[misc]
        return ""

    def read_stdin_json() -> dict | None:  # type: ignore[misc]
        return None

    def _emit_boundary_event(*_args, **_kwargs) -> None:  # type: ignore[misc]
        return None

    def run_safe_git_diff(extra_flags, cwd=None, text=False):  # type: ignore[misc]
        # Degraded-import fallback: behave like a git launch failure so
        # every caller's own except-clause handles it the same way a real
        # missing/broken git would.
        raise OSError("git_safe_diff unavailable (degraded import)")

    def _is_doc_only_changeset(files: list[str]) -> bool:  # type: ignore[misc]
        # Degraded-import fallback: never grant the doc-only exemption when
        # the real classifier couldn't even be imported — fails CLOSED the
        # same way the rest of this degraded block does.
        return False

    class _DegradedLedgerEvidence:  # type: ignore[misc]
        """Degraded-import stand-in for `review_gate_corroboration.LedgerEvidence`.

        A failed import means this module can't corroborate anything —
        fails CLOSED the same way the real module does on a read failure,
        reported as "unreadable" so the caller's rejection message points
        at an infra problem rather than implying no review happened.

        Field shape (names, order) is asserted to stay in sync with the
        real `LedgerEvidence` NamedTuple by
        `test_degraded_ledger_evidence_field_shape_matches_real_ledger_evidence`
        (#1477) — a future field added to the real shape without updating
        this stand-in now fails a test instead of silently drifting.
        """

        agents_in_window: frozenset = frozenset()
        any_dispatch_ever = False
        same_subject_dispatch_ever = False
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

    def normalized_gate_hash(cwd=None, target: str = "--cached"):  # type: ignore[misc]
        # Degraded-import fallback: no normalized hash means the
        # carry-forward lens is never decisive, so the gate behaves exactly
        # as it did before #1627. Fails CLOSED like the rest of this block.
        return None

    def _distinct_normalized_dispatches(  # type: ignore[misc]
        cwd, before_ts, window_seconds, subject_hash_normalized
    ) -> set:
        return set()


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

# #1476: `git commit -a`/`--all` and pathspec-form `git commit <path> -m ...`
# commit tracked-file changes that were never `git add`-ed — distinct from
# `_BLOCK_MESSAGE` (missing/mismatched gate file on an ordinary staged
# commit) so the operator is pointed at the actual remediation (`git add`
# first) rather than a generic "review required" that doesn't explain why
# no gate file could possibly have matched.
_UNSTAGED_BLOCK_MESSAGE = (
    "BLOCKED: Code review required before committing.\n"
    "\n"
    "This looks like `git commit -a`/`--all` or a pathspec-form commit —\n"
    "tracked file changes were modified but never explicitly staged with\n"
    "`git add`, so no `.review-passed` gate could have been written for\n"
    "them.\n"
    "\n"
    "Run `git add` on the files you intend to commit, then /code-review,\n"
    "then retry the commit.\n"
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
    "\n"
    "To bypass: use git commit --no-verify\n"
)

_STALE_MESSAGE = (
    f"BLOCKED: Review-agent dispatch evidence found but outside the "
    f"{WINDOW_SECONDS}s window — run /code-review again before committing.\n"
    "\n"
    "To bypass: use git commit --no-verify\n"
)

# Distinct from _STALE_MESSAGE (#1461 second security re-review, correctness
# finding): _STALE_MESSAGE means "a genuine dispatch for THIS content
# happened, just too long ago" — this means "genuine dispatches exist, but
# only for DIFFERENT staged content" (the diff changed since that review).
# Conflating the two under _STALE_MESSAGE told the operator to wait/re-run
# for a staleness problem they didn't have, without naming the actual cause
# (the staged content changed).
_DIFFERENT_CONTENT_MESSAGE = (
    "BLOCKED: Review-agent dispatch evidence found, but for different "
    "staged content (the diff changed since that review) — run "
    "/code-review again before committing.\n"
    "\n"
    "To bypass: use git commit --no-verify\n"
)

_READ_FAILURE_MESSAGE = (
    "BLOCKED: Could not read the dispatch ledger "
    "(.claude/metrics/boundary-events.jsonl) — check hook registration; "
    "this is an infra problem, not evidence that no review happened.\n"
    "\n"
    "To bypass: use git commit --no-verify\n"
)

# Distinct from _READ_FAILURE_MESSAGE (#1461 security re-review, A09
# finding): the ledger read failure above means "the gate decision itself
# ran, but couldn't read the corroboration evidence"; this one means "the
# hook couldn't even determine the gate's own preconditions" — resolving
# the staged-file list or the gate-file path failed (a corrupt/locked git
# index, a `.claude/memory` path that exists as a non-directory, a
# read-only project tree). Reporting both under one rule ID would
# mislabel every gate-path-setup failure as a ledger problem in the audit
# trail (`.claude/metrics/boundary-events.jsonl` itself), pointing anyone
# reading it at the wrong file to fix.
_GATE_SETUP_FAILURE_MESSAGE = (
    "BLOCKED: Could not determine the review-gate's own state (staged "
    "files or the .claude/memory/.review-passed path) — check that "
    ".claude/memory is a writable directory and the git index is healthy; "
    "this is an infra problem, not evidence that no review happened.\n"
    "\n"
    "To bypass: use git commit --no-verify\n"
)


def _insufficient_message(n: int) -> str:
    return (
        f"BLOCKED: Only {n} distinct review agent(s) dispatched (need >= "
        f"{_MIN_DISTINCT_DISPATCHES}) — run /code-review before committing.\n"
        "\n"
        "To bypass: use git commit --no-verify\n"
    )


def _emit_block(message: str) -> None:
    """Write a block message to both stdout and stderr (#1367).

    Stdout stays the canonical UI channel; stderr is mirrored because some
    hook-error wrappers surface only stderr on a nonzero hook exit.
    """
    sys.stdout.write(message)
    sys.stderr.write(message)


def _staged_names(cwd: str | None = None) -> list[str] | None:
    """Return the staged file list, or `None` when git could not be asked at
    all (#1461 security re-review, correctness finding): a `None` return
    means "couldn't determine", a `[]` return means "genuinely nothing
    staged" — `main()` must fail CLOSED on the former and only silently
    pass through on the latter. A broad `except Exception` (not just
    `FileNotFoundError`/`OSError`) is deliberate here: any unexpected
    failure to even run `git` must be reported as "couldn't determine",
    never silently folded into "nothing staged".

    The security-critical safety flags (`-c diff.relative=false`,
    `--ignore-submodules=none`) are shared with `review_gate_hash()` via
    `hooks/lib/git_safe_diff.run_safe_git_diff` (#1477) — see that module's
    docstring for the full rationale of each flag; only the `--name-only`
    extra flag is unique to this call site.
    """
    try:
        completed = run_safe_git_diff(["--name-only"], cwd=(cwd or None), text=True)
    except Exception:  # noqa: BLE001 - "couldn't determine", not "nothing staged"
        return None
    if completed.returncode != 0:
        return None
    return [line for line in completed.stdout.splitlines() if line]


def _working_tree_modified_names(cwd: str | None = None) -> list[str] | None:
    """Return tracked files whose content differs between the index and the
    working tree (bare `git diff --name-only`, no `--cached`), or `None`
    when git could not be asked at all — same `None`-vs-`[]` fail-closed
    contract as `_staged_names()` (see its docstring).

    Used to detect the `git commit -a`/pathspec-form-commit signature
    (#1476): `main()` calls this only after `_staged_names()` has already
    returned `[]` (genuinely nothing staged). If THIS also returns `[]`,
    nothing changed for any tracked file and there is truly nothing to
    gate. If it returns a non-empty list, tracked files were modified in
    the working tree without ever being `git add`-ed — exactly what `git
    commit -a`/`--all` and pathspec-form `git commit <path> -m ...` commit
    directly, bypassing `git add` (and this hook's ordinary staged-content
    gate) entirely.

    Shares `_staged_names()`'s safety flags via `git_safe_diff.run_safe_git_diff`
    (`target=None` — a bare `git diff`, index vs. working tree, rather than
    the default `--cached`).
    """
    try:
        completed = run_safe_git_diff(
            ["--name-only"], cwd=(cwd or None), text=True, target=None
        )
    except Exception:  # noqa: BLE001 - "couldn't determine", not "nothing modified"
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
        "branch": _current_branch(cwd),
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

    __slots__ = ("matched_rule", "message", "passed")

    def __init__(self, passed: bool, message: str = "", matched_rule: str = "") -> None:
        self.passed = passed
        self.message = message
        self.matched_rule = matched_rule


def _hash_verdict(
    gate_file: Path, current_hash: str, *, unstaged_commit: bool = False
) -> GateVerdict | None:
    """Lens 1/4: the original hash-match check, unchanged, evaluated FIRST
    and independent of dispatch-ledger evidence — a hash mismatch (or a
    missing/unreadable gate file) always rejects with the original,
    untouched `_BLOCK_MESSAGE`/`"pre-commit-review"` rule, regardless of how
    much genuine dispatch evidence exists (Gherkin: "Gate still rejects on
    hash mismatch even with ample genuine dispatch evidence").

    `unstaged_commit` (#1476): True when `main()` detected the `git commit
    -a`/pathspec-form-commit signature. The check itself is identical —
    only the rejection message/rule swaps to `_UNSTAGED_BLOCK_MESSAGE`/
    `"pre-commit-review-unstaged"`, pointing the operator at `git add`
    instead of a generic "review required" that wouldn't explain why no
    gate file could possibly have matched an empty staged index.

    Returns a rejecting `GateVerdict` when the hash doesn't match; `None`
    when it does, meaning "hash OK, continue to the dispatch-ledger
    corroboration lenses".

    Reads the stored hash via `_stored_gate_hashes()` (issue #1646) rather
    than its own raw `.strip()` of the whole file: `.review-passed` gained
    an optional second line in #1627 (the normalization-invariant hash), and
    stripping the WHOLE file compared `"line1\\nline2"` against a single-line
    `current_hash` — never equal, so a 2-line gate file always mismatched
    here regardless of whether the first line's hash was correct. That made
    `_single_agent_exemption_verdict()` (only reached once this lens returns
    `None`) structurally unreachable for any gate file carrying the optional
    second line. `_stored_gate_hashes()` already parses just the first line
    correctly; reuse it instead of duplicating (and mis-duplicating) that
    parse here.
    """
    block_message = _UNSTAGED_BLOCK_MESSAGE if unstaged_commit else _BLOCK_MESSAGE
    block_rule = "pre-commit-review-unstaged" if unstaged_commit else "pre-commit-review"
    if not gate_file.is_file():
        return GateVerdict(False, block_message, block_rule)
    stored, _normalized = _stored_gate_hashes(gate_file)
    if not stored or stored != current_hash:
        return GateVerdict(False, block_message, block_rule)
    return None


def _stored_gate_hashes(gate_file: Path) -> tuple[str, str | None]:
    """Read `.review-passed`'s hashes: `(raw, normalized_or_None)`.

    The file gained an optional SECOND line in #1627 (raw hash, then
    normalized hash). A 1-line file stays raw-only and returns `None` for the
    normalized value — fully backward compatible, and such a file can never
    satisfy the carry-forward lens below.
    """
    try:
        lines = [ln.strip() for ln in gate_file.read_text().splitlines()]
    except OSError:
        return "", None
    raw = lines[0] if lines else ""
    normalized = lines[1] if len(lines) > 1 and lines[1] else None
    return raw, normalized


def _cosmetic_carry_forward_verdict(
    gate_file: Path, cwd: str, *, unstaged_commit: bool = False
) -> GateVerdict | None:
    """Lens 1b/5: cosmetic-delta carry-forward (#1627).

    Runs ONLY after `_hash_verdict` has already rejected on a raw-hash
    mismatch. Passes iff ALL of:

      (a) `.review-passed` carries a stored normalized hash (its optional
          second line), AND
      (b) that stored normalized hash equals the one recomputed HERE, by this
          hook, from the current staged content, AND
      (c) at least `_MIN_DISTINCT_DISPATCHES` distinct registered review
          agents dispatched in the recency window carrying that same
          `subject_hash_normalized`.

    Why this does not reopen #1461: the exemption is a property of CONTENT,
    recomputed by the hook itself at gate time from `git diff --cached` —
    there is no claim by the gated party to trust. `normalize_patch` drops
    doc-classified hunks using the gate's own STRICT classifier (so a
    "cosmetic" edit to `agents/`, `skills/`, `.claude/`, or `CLAUDE.md` can
    never ride this path) and collapses only leading/trailing-whitespace
    changes on lines carrying no quote character (so a string-literal change
    is never cosmetic). The `>= 2` distinct-dispatch floor and the recency
    window are unchanged — this lens relaxes WHICH hash binds the evidence,
    never how much evidence is required.

    Emits a mandatory `cosmetic-delta-carry-forward` audit event on the pass
    path, so every use is visible in the same boundary-events stream the gate
    itself is audited from.

    Returns a passing `GateVerdict` when all three hold; `None` otherwise —
    "not decisive", meaning `_evaluate_gate` returns the original rejection
    unchanged. Fails CLOSED on any error.
    """
    try:
        _, stored_normalized = _stored_gate_hashes(gate_file)
        if not stored_normalized:
            return None

        target = "HEAD" if unstaged_commit else "--cached"
        current_normalized = normalized_gate_hash(cwd, target)
        if not current_normalized or current_normalized != stored_normalized:
            return None

        before_ts = _mtime_to_iso(gate_file.stat().st_mtime)
        agents = _distinct_normalized_dispatches(
            cwd, before_ts, WINDOW_SECONDS, current_normalized
        )
        if len(agents) < _MIN_DISTINCT_DISPATCHES:
            return None

        emit_boundary_event(
            cwd,
            "pre_commit_review",
            "Bash",
            "bypass",
            "cosmetic-delta-carry-forward",
            None,
            subject_hash_normalized=current_normalized,
        )
        return GateVerdict(True, matched_rule="cosmetic-delta-carry-forward")
    except Exception:  # noqa: BLE001 - fail CLOSED: not decisive, keep the rejection
        return None


def _doc_only_exemption_verdict(
    cwd: str, before_ts: str, subject_hash: str, staged: list[str]
) -> GateVerdict | None:
    """Lens 2/4: the doc-only short-circuit exemption (#1461 security
    review). The ledger event alone is a self-asserted claim from the same
    party the gate constrains — re-derive the predicate here against the
    ACTUAL staged files before honoring it. A claimed-but-unproven exemption
    does not block outright; it just falls through (`None`) to the normal
    dispatch-evidence requirement, same as if no exemption were claimed.

    Returns a passing `GateVerdict` when both the ledger event AND the
    re-derived predicate agree; `None` otherwise (not decisive — continue).
    """
    if _has_doc_only_exemption(
        cwd, before_ts, WINDOW_SECONDS, subject_hash
    ) and _is_doc_only_changeset(staged):
        return GateVerdict(True)
    return None


def _single_agent_exemption_verdict(
    cwd: str, before_ts: str, subject_hash: str, n: int
) -> GateVerdict | None:
    """Lens 3/4: the sanctioned `--agent <name>` single-agent exemption,
    which deliberately dispatches exactly 1 review agent and so can never
    clear the `>= 2` distinct-dispatch floor on its own. Requiring `n >= 1`
    here (#1461 security review) closes the gap where the exemption event
    alone, with zero dispatch evidence, passed the gate for an arbitrary
    changeset.

    Returns a passing `GateVerdict` when both the exemption event and at
    least 1 genuine dispatch are present; `None` otherwise (not decisive —
    continue to the final dispatch-count lens).
    """
    if n >= 1 and _has_single_agent_exemption(cwd, before_ts, WINDOW_SECONDS, subject_hash):
        return GateVerdict(True)
    return None


def _dispatch_count_verdict(evidence, n: int) -> GateVerdict:
    """Lens 4/4: the terminal decision once no exemption applies — always
    returns a concrete verdict (never `None`). `n >= _MIN_DISTINCT_DISPATCHES`
    passes outright; `n == 1` reports "insufficient" (a single dispatch,
    typically without the single-agent exemption event, is genuinely close
    but not enough); `n == 0` picks between "stale" (a genuine dispatch for
    THIS subject_hash exists, just outside the recency window) and
    "different content" (genuine dispatches exist, but never for this
    subject_hash) and "no dispatch at all" — see each message constant's own
    comment for why the three are kept distinct rather than folded into one.
    """
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
    gate_file: Path,
    current_hash: str,
    cwd: str,
    staged: list[str],
    *,
    unstaged_commit: bool = False,
) -> GateVerdict:
    """Decide whether `.review-passed` corroborates a genuine, recent,
    multi-agent review (#1461) — extracted from `main()` so the decision
    logic is unit-testable independent of stdin/subprocess plumbing.

    A short pipeline over four named decision lenses (#1477 structure
    review — this function used to be one ~90-line body with all four
    inlined): `_hash_verdict` (always evaluated first — a hash mismatch
    rejects regardless of dispatch evidence), then, only once the hash
    matches, `_doc_only_exemption_verdict`, `_single_agent_exemption_verdict`,
    and finally `_dispatch_count_verdict` as the terminal fallback. Each
    lens after the hash check returns `None` to mean "not decisive, try the
    next lens" or a concrete `GateVerdict` to short-circuit the pipeline.

    `unstaged_commit` (#1476) is True when `main()` detected the `git
    commit -a`/pathspec-form-commit signature — nothing staged, but tracked
    files modified in the working tree. `staged` is then `main()`'s
    working-tree-modified list (not the empty staged-index list) and
    `current_hash` is `working_tree_gate_hash()` (`git diff HEAD`) rather
    than `review_gate_hash()` (`git diff --cached`) — but every check below
    this point (dispatch-ledger corroboration, doc-only/single-agent
    exemptions) is identical either way; only `_hash_verdict`'s
    message/rule differ, pointing the operator at `git add` instead of a
    generic "review required". See `_hash_verdict()`'s own docstring.

    `staged` is `main()`'s own already-computed staged-file (or, for an
    `unstaged_commit`, working-tree-modified) list (#1461 fifth structure
    re-review) — this function used to re-derive it with a second
    `_staged_names(cwd)` call (a second `git diff --cached` per commit) for
    data the caller already had. Passing it through is cheaper and correct
    for every non-concurrent path; it does shift *when* the doc-only
    exemption's file list is sampled to slightly before, rather than
    slightly after, the current-hash function's own read — an inherent,
    low-severity commit-time TOCTOU of any PreToolUse hook (the hook
    observes state at invocation time; the actual `git commit` subprocess
    runs afterward) that only matters under concurrent staging in the same
    working tree.
    """
    verdict = _hash_verdict(gate_file, current_hash, unstaged_commit=unstaged_commit)
    if verdict is not None:
        # The raw hash mismatched. Before returning that rejection, give the
        # cosmetic-delta carry-forward lens (#1627) its chance: a re-stage
        # that provably changed no behavior (doc hunks, indentation) should
        # not force fresh dispatches whose only purpose is to feed the
        # ledger. The lens returns None unless it can prove the case, so the
        # rejection below is the default, not the exception.
        carry_forward = _cosmetic_carry_forward_verdict(
            gate_file, cwd, unstaged_commit=unstaged_commit
        )
        if carry_forward is not None:
            return carry_forward
        return verdict

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
        #
        # This is intentional, not a bug (issue #1646): it means a
        # dispatch/exemption event timestamped AFTER the gate file's own
        # mtime falls outside the window and will not corroborate it. The
        # natural human workflow — write the gate, then realize one more
        # check is needed and dispatch it — silently produces evidence
        # outside the window this way, with no error pointing at why. Gate
        # writes must happen strictly after every dispatch/exemption event
        # they're meant to corroborate.
        before_ts = _mtime_to_iso(gate_file.stat().st_mtime)

        evidence = _evaluate_ledger(cwd, before_ts, WINDOW_SECONDS, current_hash)
        if evidence.read_failure_reason is not None:
            return GateVerdict(False, _READ_FAILURE_MESSAGE, "dispatch-ledger-read-failure")

        n = len(evidence.agents_in_window)

        verdict = _doc_only_exemption_verdict(cwd, before_ts, current_hash, staged)
        if verdict is not None:
            return verdict

        verdict = _single_agent_exemption_verdict(cwd, before_ts, current_hash, n)
        if verdict is not None:
            return verdict

        return _dispatch_count_verdict(evidence, n)
    except Exception:  # noqa: BLE001 - fail CLOSED: an unexpected error is not a pass
        return GateVerdict(False, _READ_FAILURE_MESSAGE, "dispatch-ledger-read-failure")


def _handle_bypass(
    command: str, cwd: str, staged: list[str], session_id
) -> int | None:
    """`main()` lens: the `--no-verify`/`-n` bypass branch. Returns the
    hook's exit code (0 allow, 2 block) when `command` carries a bypass
    flag; `None` when it doesn't (not applicable — `main()` continues to
    the normal review-gate evaluation)."""
    if not has_bypass_flag(command):
        return None
    flag = bypass_flag_name(command) or "--no-verify"
    reason = os.environ.get("GATE_BYPASS_REASON", "").strip()
    if reason:
        _record_bypass_audit(flag, reason, len(staged), cwd)
        emit_boundary_event(cwd, "pre_commit_review", "Bash", "bypass", flag, session_id)
        return 0
    _emit_block(_BYPASS_BLOCK_MESSAGE)
    return 2


def _prepare_gate(
    cwd: str, session_id, *, unstaged_commit: bool = False
) -> tuple[str, Path] | None:
    """`main()` lens: resolve the current staged-content hash and the
    `.review-passed` gate-file path, creating its parent directory.
    Everything here is wrapped in its own exception handler (#1461 security
    review) so a failure resolving or preparing the gate path can never
    escape to this module's top-level `except Exception: sys.exit(0)` in
    `__main__` — that top-level handler exists to protect against a bug in
    the pre-detection stdin/argument plumbing, not to swallow a failure in
    the actual gate decision. Before this fix, `gate_file.parent.mkdir(...)`
    ran unguarded: a `.claude/memory` path that exists as a regular file
    (not a directory), or a read-only project tree, raised
    `FileExistsError`/`NotADirectoryError`/`PermissionError` here, which
    propagated straight past `_evaluate_gate`'s own fail-closed try/except
    (never entered) to the top-level fail-open — deterministically turning
    a should-block commit into an allow, with no gate file written and no
    bypass-audit entry recorded at all.

    `unstaged_commit` (#1476): for the `git commit -a`/pathspec-form-commit
    signature, `current_hash` must be the EFFECTIVE content such a commit
    would actually commit — `working_tree_gate_hash()` (`git diff HEAD`) —
    rather than `review_gate_hash()`'s `git diff --cached`, which is empty
    by definition here (nothing was ever `git add`-ed).

    Returns `(current_hash, gate_file)` on success; `None` on failure,
    having already emitted the block message and boundary event — the
    caller returns exit code 2.
    """
    try:
        current_hash = (
            working_tree_gate_hash(cwd) if unstaged_commit else review_gate_hash(cwd)
        )

        # Resolved via the shared artifact_paths helper (#1461 security
        # review), not a bare relative path — the latter resolves against
        # the process's real OS cwd, which can silently disagree with `cwd`
        # (the payload's project root) when this hook runs from a
        # subdirectory. This now matters beyond cosmetics: the gate file's
        # mtime anchors the dispatch-ledger recency window, and the ledger
        # itself resolves through this same helper — a root mismatch here
        # would let the two silently compare against different projects.
        gate_file = _resolve_file("memory", ".review-passed", cwd)
        gate_file.parent.mkdir(parents=True, exist_ok=True)
        return current_hash, gate_file
    except Exception:  # noqa: BLE001 - fail CLOSED: setup failure is not a pass
        _emit_block(_GATE_SETUP_FAILURE_MESSAGE)
        emit_boundary_event(
            cwd, "pre_commit_review", "Bash", "block", "gate-setup-failure", session_id
        )
        return None


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

    # Resolved with the payload's own `cwd` (#1461 security review) — a bare
    # `git diff --cached` without `cwd=` runs against this process's real OS
    # cwd, which can silently disagree with the payload's project root when
    # this hook is invoked from a subdirectory. Before this fix, that
    # divergence meant `_staged_names()` could return `[]` (nothing staged
    # in the process's cwd) even though the payload's project root had a
    # real staged commit in flight — silently skipping the entire review
    # gate, corroboration included, with no audit trail at all.
    staged = _staged_names(cwd)
    # `None` means git itself could not answer this question (corrupt/locked
    # index, bad cwd, ...) — that must fail CLOSED, never be folded into
    # "nothing staged" (#1461 security re-review): a should-block commit
    # must not slip through just because the precondition check itself
    # broke.
    if staged is None:
        _emit_block(_GATE_SETUP_FAILURE_MESSAGE)
        emit_boundary_event(
            cwd, "pre_commit_review", "Bash", "block", "gate-setup-failure", session_id
        )
        return 2

    # Nothing staged via `git add` — could be genuinely nothing to gate, OR
    # the `git commit -a`/pathspec-form-commit signature (#1476): tracked
    # files modified in the working tree without ever being staged that
    # way. `_staged_names()` alone can't tell the two apart; check the
    # working tree too before deciding.
    unstaged_commit = False
    if not staged:
        working_modified = _working_tree_modified_names(cwd)
        # Same fail-CLOSED contract as `_staged_names()` above: "couldn't
        # determine" must never be folded into "nothing to gate".
        if working_modified is None:
            _emit_block(_GATE_SETUP_FAILURE_MESSAGE)
            emit_boundary_event(
                cwd, "pre_commit_review", "Bash", "block", "gate-setup-failure", session_id
            )
            return 2
        if not working_modified:
            # Genuinely nothing staged AND no tracked-file working-tree
            # changes at all → nothing to gate.
            return 0
        # The `-a`/pathspec-form signature: route through the gate on the
        # working-tree file list, exactly as `staged` would normally carry
        # it (used below for the bypass audit's file count and for the
        # doc-only exemption's `_is_doc_only_changeset` check).
        unstaged_commit = True
        staged = working_modified

    bypass_exit_code = _handle_bypass(command, cwd, staged, session_id)
    if bypass_exit_code is not None:
        return bypass_exit_code

    prepared = _prepare_gate(cwd, session_id, unstaged_commit=unstaged_commit)
    if prepared is None:
        return 2
    current_hash, gate_file = prepared

    verdict = _evaluate_gate(
        gate_file, current_hash, cwd, staged, unstaged_commit=unstaged_commit
    )
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
